## services\semantic_embedding_service.py
## Version: 1.1.1 dated 20260126
 
"""
SemanticEmbeddingService - Clean Architectural Separation

Version: 1.1.0
Date: 2026-01-22

This service handles SEMANTIC embeddings ONLY.
Face embeddings are handled separately by face services.

Core Principle (non-negotiable):
Face recognition and semantic understanding are TWO ORTHOGONAL AI systems.
They must share photos, not meaning.

Architecture:
- Uses semantic_embeddings table (NOT photo_embedding)
- CLIP/SigLIP models ONLY (no face models)
- Normalized vectors (mandatory for cosine similarity)
- Minimal but correct implementation

Usage:
    from services.semantic_embedding_service import get_semantic_embedding_service

    service = get_semantic_embedding_service()

    # Extract from image
    embedding = service.encode_image('/path/to/photo.jpg')

    # Extract from text
    query_embedding = service.encode_text('sunset beach')
"""

import threading
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from PIL import Image

from repository.base_repository import DatabaseConnection
from logging_config import get_logger

logger = get_logger(__name__)

# Thread-safe singleton lock
_service_lock = threading.Lock()

# Optional FAISS import for fast similarity search on large collections
# Falls back to brute-force numpy when FAISS is not available
_faiss_available = False
_faiss = None
try:
    import faiss as _faiss
    _faiss_available = True
    logger.info("[SemanticEmbeddingService] FAISS available - fast ANN search enabled")
except ImportError:
    logger.debug("[SemanticEmbeddingService] FAISS not installed - using numpy fallback for similarity search")


def _has_model_weights(model_dir: str) -> bool:
    """Check if a local model directory contains valid weight files."""
    p = Path(model_dir)
    if not (p / "config.json").exists():
        return False
    weight_candidates = [
        p / "model.safetensors",
        p / "pytorch_model.bin",
        p / "pytorch_model.bin.index.json",
        p / "tf_model.h5",
        p / "flax_model.msgpack",
    ]
    return any(x.exists() for x in weight_candidates)


class SemanticEmbeddingService:
    """
    Service for semantic visual embeddings (CLIP/SigLIP).

    Handles:
    - Image → embedding (512-D or 768-D normalized vectors)
    - Text → embedding (for semantic search)
    - Storage in semantic_embeddings table

    Does NOT handle:
    - Face embeddings (use FaceEmbeddingService)
    - Face clustering (use FaceClusteringService)
    """

    def __init__(self,
                 model_name: str = "openai/clip-vit-base-patch32",
                 db_connection: Optional[DatabaseConnection] = None):
        """
        Initialize semantic embedding service.

        IMPORTANT: Always use get_semantic_embedding_service() instead of
        instantiating directly. Direct instantiation bypasses the per-model
        cache and can create duplicate instances.

        Args:
            model_name: CLIP/SigLIP model variant (canonical HuggingFace ID preferred)
                       Default: "openai/clip-vit-base-patch32"
            db_connection: Optional database connection
        """
        from utils.clip_model_registry import normalize_model_id, all_aliases_for
        self.model_name = normalize_model_id(model_name)
        self._model_aliases = all_aliases_for(self.model_name)
        self.db = db_connection or DatabaseConnection()

        # Model cache (lazy loading — torch/transformers imported on first use)
        self._model = None
        self._processor = None
        self._device = None
        self._load_attempted = False
        self._load_error = None
        self._load_lock = threading.Lock()

        # TTL cache for stale-embeddings query (avoids re-querying every 30s)
        self._stale_cache = {}       # {project_id: (timestamp, result_list)}
        self._stale_cache_ttl = 300  # seconds (5 minutes)

        # Defer heavy imports to _load_model(); just probe availability here
        self._available = False
        self._torch = None
        self._CLIPProcessor = None
        self._CLIPModel = None
        try:
            import importlib
            importlib.import_module("torch")
            importlib.import_module("transformers")
            self._available = True
            logger.info(f"[SemanticEmbeddingService] Initialized (lazy) with model={model_name}")
        except ImportError:
            logger.warning("[SemanticEmbeddingService] PyTorch/Transformers not available")

    @property
    def available(self) -> bool:
        """Check if service is available."""
        return self._available


    def _load_model(self):
        """
        Lazy load CLIP model with offline-first approach.

        Best Practices (based on Lightroom, Capture One, Google Photos):
        1. Check for offline models first
        2. Inform user if model is missing
        3. Let user choose model variant
        4. Request explicit download consent
        5. Store preference to avoid repeated prompts

        This prevents unexpected downloads and gives users control.
        Thread-safe: Uses double-checked locking pattern.
        """
        # Fast path: If model already loaded, return immediately (no lock needed)
        if self._model is not None:
            return

        # CRITICAL: If we already tried and failed, don't retry on every photo!
        # This prevents repeated model checking for each of 27 photos
        if self._load_attempted and self._load_error:
            raise self._load_error

        # Acquire lock for thread-safe loading
        with self._load_lock:
            # Double-check after acquiring lock (another thread may have loaded)
            if self._model is not None:
                return

            if self._load_attempted and self._load_error:
                raise self._load_error

            # Mark that we're attempting to load
            self._load_attempted = True

            if not self._available:
                error = RuntimeError("PyTorch/Transformers not available")
                self._load_error = error
                raise error

            # Import heavy dependencies now (deferred from __init__)
            if self._torch is None:
                import torch
                from transformers import CLIPProcessor, CLIPModel
                self._torch = torch
                self._CLIPProcessor = CLIPProcessor
                self._CLIPModel = CLIPModel

            logger.info(f"[SemanticEmbeddingService] Loading model: {self.model_name}")

            # Detect device
            if self._torch.cuda.is_available():
                self._device = self._torch.device("cuda")
                logger.info("[SemanticEmbeddingService] Using CUDA GPU")
            elif hasattr(self._torch.backends, 'mps') and self._torch.backends.mps.is_available():
                self._device = self._torch.device("mps")
                logger.info("[SemanticEmbeddingService] Using Apple MPS GPU")
            else:
                self._device = self._torch.device("cpu")
                logger.info("[SemanticEmbeddingService] Using CPU")

            # model_name is already a canonical HuggingFace ID
            # (normalized in __init__ via clip_model_registry)
            hf_model = self.model_name

            # STEP 1: Check for stored preference first
            local_model_path = None
            try:
                from pathlib import Path
                from settings_manager_qt import SettingsManager
                settings = SettingsManager()

                # Check if user has already chosen a model path
                clip_path = settings.get("clip_model_path", "").strip()
                if clip_path:
                    clip_path_obj = Path(clip_path)

                    # Handle both absolute and relative paths
                    if not clip_path_obj.is_absolute():
                        # Relative path - resolve relative to app root
                        app_root = Path(__file__).parent.parent.absolute()
                        clip_path_obj = app_root / clip_path_obj
                        logger.debug(f"[SemanticEmbeddingService] Resolving relative path: {clip_path} → {clip_path_obj}")

                    # Validate model path
#                    if clip_path_obj.exists() and (clip_path_obj / 'config.json').exists():
                    if clip_path_obj.exists() and _has_model_weights(str(clip_path_obj)):    
                        local_model_path = str(clip_path_obj)
                        logger.info(f"[SemanticEmbeddingService] ✓ Using stored preference: {local_model_path}")
                    else:
                        logger.warning(
                            f"[SemanticEmbeddingService] Stored preference path invalid:\n"
                            f"  Path: {clip_path_obj}\n"
                            f"  Exists: {clip_path_obj.exists()}\n"
                            f"  Has config.json: {(clip_path_obj / 'config.json').exists() if clip_path_obj.exists() else False}"
                        )
            except Exception as e:
                logger.warning(f"[SemanticEmbeddingService] Could not check stored preference: {e}")

            # STEP 2: Check for offline models in standard locations
            if not local_model_path:
                try:
                    from pathlib import Path
                    import os
                    app_root = Path(__file__).parent.parent.absolute()
                    folder_name = hf_model.replace('/', '--')

                    logger.info(f"[SemanticEmbeddingService] Searching for offline model...")
                    logger.info(f"[SemanticEmbeddingService]   App root: {app_root}")
                    logger.info(f"[SemanticEmbeddingService]   Looking for: {folder_name}")

                    # Check multiple possible locations
                    possible_locations = [
                        app_root / 'Model' / folder_name,      # Uppercase M, singular
                        app_root / 'model' / folder_name,      # Lowercase m, singular
                        app_root / 'models' / folder_name,     # Lowercase m, plural
                    ]

                    # CRITICAL: Also check HuggingFace default cache location
                    # This is where transformers downloads models by default
                    # HF cache uses format: models--{org}--{model} e.g., models--openai--clip-vit-base-patch32
                    home = Path.home()
                    hf_cache_locations = [
                        home / '.cache' / 'huggingface' / 'hub' / f'models--{folder_name}',
                        home / '.cache' / 'huggingface' / 'transformers' / folder_name,
                    ]
                    possible_locations.extend(hf_cache_locations)

                    for model_folder in possible_locations:
                        logger.info(f"[SemanticEmbeddingService]   Checking: {model_folder}")

                        exists = model_folder.exists()
                        has_config = (model_folder / 'config.json').exists() if exists else False

                        logger.info(f"[SemanticEmbeddingService]     → Exists: {exists}")
                        if exists:
                            logger.info(f"[SemanticEmbeddingService]     → Has config.json: {has_config}")

                            # For HuggingFace cache, also check for snapshots folder
                            snapshots_dir = model_folder / 'snapshots'
                            snapshots_exists = snapshots_dir.exists()
                            logger.info(f"[SemanticEmbeddingService]     → Has snapshots folder: {snapshots_exists}")

                            if not has_config and snapshots_exists:
                                # HF cache structure: models--xxx/snapshots/hash/
                                # Also check refs/main for the current snapshot reference
                                try:
                                    snapshot_folders = [d for d in snapshots_dir.iterdir() if d.is_dir()]
                                    logger.info(f"[SemanticEmbeddingService]     → Found {len(snapshot_folders)} snapshot(s)")

                                    if snapshot_folders:
                                        # Try to use refs/main to find the correct snapshot first
                                        refs_main = model_folder / 'refs' / 'main'
                                        latest_snapshot = None

                                        if refs_main.exists():
                                            try:
                                                ref_hash = refs_main.read_text().strip()
                                                logger.info(f"[SemanticEmbeddingService]     → refs/main points to: {ref_hash}")
                                                ref_snapshot = snapshots_dir / ref_hash
                                                if ref_snapshot.exists():
                                                    latest_snapshot = ref_snapshot
                                            except Exception as ref_err:
                                                logger.warning(f"[SemanticEmbeddingService]     → Could not read refs/main: {ref_err}")

                                        # Fallback: use the most recent snapshot by mtime
                                        if latest_snapshot is None:
                                            latest_snapshot = max(snapshot_folders, key=lambda p: p.stat().st_mtime)

                                        logger.info(f"[SemanticEmbeddingService]     → Using snapshot: {latest_snapshot.name}")

                                        snapshot_has_config = (latest_snapshot / 'config.json').exists()
                                        logger.info(f"[SemanticEmbeddingService]     → Snapshot has config.json: {snapshot_has_config}")

                                        if snapshot_has_config:
                                            logger.info(f"[SemanticEmbeddingService]     → ✓ VALID MODEL FOUND in HF cache snapshot!")
                                            local_model_path = str(latest_snapshot)
                                            break
                                        else:
                                            # List files in snapshot to debug
                                            try:
                                                snapshot_files = list(latest_snapshot.iterdir())
                                                logger.warning(f"[SemanticEmbeddingService]     → Snapshot contents: {[f.name for f in snapshot_files[:15]]}")
                                            except Exception as list_err:
                                                logger.warning(f"[SemanticEmbeddingService]     → Could not list snapshot: {list_err}")
                                    else:
                                        logger.warning(f"[SemanticEmbeddingService]     → Snapshots folder exists but is empty")
                                except Exception as e:
                                    logger.warning(f"[SemanticEmbeddingService]     → Error checking snapshots: {e}", exc_info=True)

                            elif has_config:
                                logger.info(f"[SemanticEmbeddingService]     → ✓ VALID MODEL FOUND!")
                                local_model_path = str(model_folder)
                                break
                            else:
                                # List what files ARE in the folder
                                try:
                                    files = list(model_folder.iterdir())
                                    logger.warning(f"[SemanticEmbeddingService]     → Folder exists but no config.json. Contents: {[f.name for f in files[:10]]}")
                                except Exception as e:
                                    logger.warning(f"[SemanticEmbeddingService]     → Could not list contents: {e}")

                    if not local_model_path:
                        logger.warning(f"[SemanticEmbeddingService] ✗ No valid model found in any location")

                except Exception as e:
                    logger.error(f"[SemanticEmbeddingService] Error checking for local models: {e}", exc_info=True)

            # STEP 3: If no offline model found, handle appropriately
            if not local_model_path:
                logger.warning(f"[SemanticEmbeddingService] No offline model found for {hf_model}")

                # CRITICAL: Check if we're on the main thread
                # Background workers should NOT show dialogs (causes UI freeze)
                try:
                    from PySide6.QtWidgets import QApplication
                    from PySide6.QtCore import QThread

                    app = QApplication.instance()
                    is_main_thread = QThread.currentThread() == app.thread() if app else False

                    if not is_main_thread:
                        # We're in a background worker - DO NOT show dialog
                        logger.error(
                            f"[SemanticEmbeddingService] Model not found and running in background thread. "
                            f"Cannot show dialog during background processing."
                        )
                        error = RuntimeError(
                            f"CLIP model '{hf_model}' not found offline.\n\n"
                            f"The model is required for similar photo detection.\n\n"
                            f"Please ensure model is installed at one of:\n"
                            f"  • ./Model/{hf_model.replace('/', '--')}/\n"
                            f"  • ./model/{hf_model.replace('/', '--')}/\n"
                            f"  • ./models/{hf_model.replace('/', '--')}/\n\n"
                            f"Or set path in: Preferences → Visual Embeddings → Model Path\n\n"
                            f"Note: Model check performed once and cached - will not retry for each photo."
                        )
                        self._load_error = error  # Cache the error to avoid retrying
                        raise error

                except ImportError:
                    is_main_thread = False  # Assume not main thread if Qt not available
                except Exception as thread_check_error:
                    # If thread checking fails, assume we're in background thread
                    logger.warning(f"[SemanticEmbeddingService] Thread check failed: {thread_check_error}")
                    is_main_thread = False

                # Show dialog only if on main thread AND GUI available
                if is_main_thread:
                    logger.info("[SemanticEmbeddingService] On main thread, showing model selection dialog")
                    try:
                        from ui.clip_model_dialog import show_clip_model_dialog

                        result = show_clip_model_dialog()

                        if result:
                            selected_model_name, selected_model_path = result
                            logger.info(f"[SemanticEmbeddingService] User selected: {selected_model_name} → {selected_model_path}")

                            # Update to use selected model
                            self.model_name = selected_model_name
                            local_model_path = selected_model_path

                            # Update hf_model for consistency
                            hf_model = model_map.get(self.model_name, self.model_name)
                        else:
                            # User cancelled - raise error
                            error = RuntimeError(
                                f"CLIP model '{hf_model}' not found offline.\n\n"
                                f"To use visual embedding features, you need to download a model.\n"
                                f"Please try again and select a model to download."
                            )
                            self._load_error = error
                            raise error

                    except ImportError as e:
                        logger.error(f"[SemanticEmbeddingService] Could not import model dialog: {e}")
                        error = RuntimeError(
                            f"CLIP model '{hf_model}' not found offline.\n\n"
                            f"For offline use:\n"
                            f"1. Download the model to: ./Model/{hf_model.replace('/', '--')}/\n"
                            f"2. Or set custom path in Preferences → Visual Embeddings → Model Path"
                        )
                        self._load_error = error
                        raise error
                    except Exception as dialog_error:
                        logger.error(f"[SemanticEmbeddingService] Dialog error: {dialog_error}")
                        error = RuntimeError(
                            f"CLIP model '{hf_model}' not found offline.\n\n"
                            f"For offline use, place model files at one of:\n"
                            f"  • ./Model/{hf_model.replace('/', '--')}/\n"
                            f"  • ./model/{hf_model.replace('/', '--')}/\n"
                            f"  • ./models/{hf_model.replace('/', '--')}/\n\n"
                            f"Or set custom path in: Preferences → Visual Embeddings → Model Path"
                        )
                        self._load_error = error
                        raise error
                else:
                    # No GUI or not main thread - raise error without showing dialog
                    logger.error("[SemanticEmbeddingService] Cannot show dialog (no GUI or background thread)")
                    error = RuntimeError(
                        f"CLIP model '{hf_model}' not found offline.\n\n"
                        f"For offline use, place model files at one of:\n"
                        f"  • ./Model/{hf_model.replace('/', '--')}/\n"
                        f"  • ./model/{hf_model.replace('/', '--')}/\n"
                        f"  • ./models/{hf_model.replace('/', '--')}/\n\n"
                        f"Or set custom path in: Preferences → Visual Embeddings → Model Path"
                    )
                    self._load_error = error
                    raise error

            # STEP 4: Load model from local path (offline mode)
            try:
                logger.info(f"[SemanticEmbeddingService] Loading from local path (offline mode): {local_model_path}")
                self._processor = self._CLIPProcessor.from_pretrained(
                    local_model_path,
                    local_files_only=True
                )
                self._model = self._CLIPModel.from_pretrained(
                    local_model_path,
                    local_files_only=True
                )

                logger.info(f"[SemanticEmbeddingService] Model loaded successfully: {hf_model}")

            except Exception as e:
                logger.error(f"[SemanticEmbeddingService] Failed to load model from {local_model_path}: {e}")
                error = RuntimeError(
                    f"Failed to load CLIP model from:\n{local_model_path}\n\n"
                    f"The model files may be corrupted or incomplete.\n"
                    f"Please delete the folder and download again.\n\n"
                    f"Error: {str(e)}"
                )
                self._load_error = error
                raise error

            self._model.to(self._device)
            self._model.eval()

            # Successfully loaded - clear any previous error
            self._load_error = None
            logger.info(f"[SemanticEmbeddingService] Model ready on {self._device}")

    def encode_image(self, image_path: str) -> np.ndarray:
        """
        Extract semantic embedding from image.

        Args:
            image_path: Path to image file

        Returns:
            Normalized embedding vector (float32, L2 norm = 1.0)

        Note:
            Normalization is MANDATORY for cosine similarity.
            Without it, similarity scores are meaningless.
        """
        self._load_model()

        # Load image
        image = Image.open(image_path).convert('RGB')

        # Preprocess
        inputs = self._processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        # Extract features
        with self._torch.no_grad():
            image_features = self._model.get_image_features(**inputs)

        # Convert to numpy and normalize (CRITICAL)
        vec = image_features.cpu().numpy()[0].astype('float32')
        vec = vec / np.linalg.norm(vec)  # L2 normalization

        return vec

    def encode_text(self, text: str) -> np.ndarray:
        """
        Extract semantic embedding from text query.

        Args:
            text: Query text (e.g., "sunset beach")

        Returns:
            Normalized embedding vector (float32, L2 norm = 1.0)
        """
        self._load_model()

        # Preprocess
        inputs = self._processor(text=[text], return_tensors="pt", padding=True)
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        # Extract features
        with self._torch.no_grad():
            text_features = self._model.get_text_features(**inputs)

        # Convert to numpy and normalize (CRITICAL)
        vec = text_features.cpu().numpy()[0].astype('float32')
        vec = vec / np.linalg.norm(vec)  # L2 normalization

        return vec

    # =========================================================================
    # GPU MEMORY MANAGEMENT
    # =========================================================================

    def get_gpu_memory_info(self) -> dict:
        """
        Get GPU memory information for the current device.

        Returns:
            Dictionary with:
            - device_type: 'cuda', 'mps', or 'cpu'
            - total_memory_mb: Total GPU memory (0 for CPU)
            - free_memory_mb: Available GPU memory (0 for CPU)
            - used_memory_mb: Used GPU memory (0 for CPU)
            - utilization_percent: Memory utilization percentage
        """
        info = {
            'device_type': 'cpu',
            'total_memory_mb': 0,
            'free_memory_mb': 0,
            'used_memory_mb': 0,
            'utilization_percent': 0.0
        }

        if not self._available:
            return info

        # Ensure model is loaded to know the device
        try:
            self._load_model()
        except Exception:
            return info

        if self._device is None:
            return info

        device_type = self._device.type
        info['device_type'] = device_type

        if device_type == 'cuda':
            try:
                # Get CUDA memory info
                total = self._torch.cuda.get_device_properties(self._device).total_memory
                reserved = self._torch.cuda.memory_reserved(self._device)
                allocated = self._torch.cuda.memory_allocated(self._device)

                # Free memory = total - reserved (reserved includes allocated + cached)
                free = total - reserved

                info['total_memory_mb'] = total / (1024 * 1024)
                info['used_memory_mb'] = allocated / (1024 * 1024)
                info['free_memory_mb'] = free / (1024 * 1024)
                info['utilization_percent'] = (allocated / total) * 100 if total > 0 else 0

            except Exception as e:
                logger.warning(f"[SemanticEmbeddingService] Error getting CUDA memory: {e}")

        elif device_type == 'mps':
            # MPS (Apple Silicon) - limited memory info available
            try:
                # MPS doesn't expose detailed memory info like CUDA
                # We can estimate based on system memory
                import psutil
                vm = psutil.virtual_memory()
                # Assume we can use up to 50% of system memory for GPU
                info['total_memory_mb'] = vm.total / (1024 * 1024) * 0.5
                info['free_memory_mb'] = vm.available / (1024 * 1024) * 0.5
                info['used_memory_mb'] = info['total_memory_mb'] - info['free_memory_mb']
                info['utilization_percent'] = (info['used_memory_mb'] / info['total_memory_mb']) * 100
            except ImportError:
                # psutil not available
                info['total_memory_mb'] = 8192  # Assume 8GB
                info['free_memory_mb'] = 4096  # Assume 4GB free
            except Exception as e:
                logger.warning(f"[SemanticEmbeddingService] Error getting MPS memory: {e}")

        return info

    def get_optimal_batch_size(self, target_memory_usage: float = 0.7) -> int:
        """
        Calculate optimal batch size based on available GPU memory.

        Uses heuristics based on model size and image dimensions to estimate
        memory requirements per image.

        Args:
            target_memory_usage: Target GPU memory utilization (0.0-1.0, default 0.7)

        Returns:
            Recommended batch size (minimum 1, maximum 64)
        """
        # Model memory estimates (approximate, in MB)
        model_memory_estimates = {
            'clip-vit-b32': 350,   # ~350MB for ViT-B/32
            'clip-vit-b16': 350,   # ~350MB for ViT-B/16
            'clip-vit-l14': 900,   # ~900MB for ViT-L/14
        }

        # Memory per image during inference (approximate, in MB)
        # Includes input tensor, intermediate activations, output
        per_image_memory = {
            'clip-vit-b32': 50,   # ~50MB per 224x224 image
            'clip-vit-b16': 80,   # ~80MB per 224x224 image
            'clip-vit-l14': 150,  # ~150MB per 224x224 image
        }

        mem_info = self.get_gpu_memory_info()

        # CPU mode - use reasonable defaults
        if mem_info['device_type'] == 'cpu':
            logger.debug("[SemanticEmbeddingService] CPU mode - using batch size 4")
            return 4

        available_mb = mem_info['free_memory_mb']
        model_mb = model_memory_estimates.get(self.model_name, 400)
        per_image_mb = per_image_memory.get(self.model_name, 60)

        # Calculate available memory for batching (after model overhead)
        usable_memory = (available_mb * target_memory_usage) - model_mb

        if usable_memory <= 0:
            logger.warning(f"[SemanticEmbeddingService] Low GPU memory ({available_mb:.0f}MB free), using batch size 1")
            return 1

        # Calculate batch size
        batch_size = int(usable_memory / per_image_mb)

        # Clamp to reasonable range
        batch_size = max(1, min(batch_size, 64))

        logger.info(f"[SemanticEmbeddingService] Auto-tuned batch size: {batch_size} "
                    f"(GPU: {available_mb:.0f}MB free, {mem_info['device_type']})")

        return batch_size

    def encode_images_batch(self, image_paths: List[str],
                            batch_size: Optional[int] = None,
                            on_progress: Optional[callable] = None) -> List[Tuple[str, Optional[np.ndarray]]]:
        """
        Extract embeddings from multiple images with GPU memory management.

        Automatically batches images based on available GPU memory to prevent
        OOM errors. Includes automatic retry with smaller batch sizes on failure.

        Args:
            image_paths: List of image file paths
            batch_size: Optional batch size (auto-tuned if None)
            on_progress: Optional callback(processed, total, message)

        Returns:
            List of (image_path, embedding) tuples. embedding is None if failed.
        """
        self._load_model()

        if batch_size is None:
            batch_size = self.get_optimal_batch_size()

        results = []
        total = len(image_paths)
        processed = 0

        # Process in batches
        for i in range(0, total, batch_size):
            batch_paths = image_paths[i:i + batch_size]
            batch_results = self._process_image_batch(batch_paths, batch_size)

            results.extend(batch_results)
            processed += len(batch_paths)

            if on_progress:
                on_progress(processed, total, f"Processed {processed}/{total} images")

            # Clear GPU cache between batches to prevent memory buildup
            if self._device and self._device.type == 'cuda':
                self._torch.cuda.empty_cache()

        return results

    def _process_image_batch(self, image_paths: List[str],
                             max_batch_size: int) -> List[Tuple[str, Optional[np.ndarray]]]:
        """
        Process a batch of images with automatic retry on OOM.

        Args:
            image_paths: List of image paths to process
            max_batch_size: Maximum batch size to try

        Returns:
            List of (path, embedding) tuples
        """
        current_batch_size = min(len(image_paths), max_batch_size)
        results = []

        while current_batch_size >= 1:
            try:
                # Load images
                images = []
                valid_paths = []

                for path in image_paths:
                    try:
                        img = Image.open(path).convert('RGB')
                        images.append(img)
                        valid_paths.append(path)
                    except Exception as e:
                        logger.warning(f"[SemanticEmbeddingService] Failed to load {path}: {e}")
                        results.append((path, None))

                if not images:
                    return results

                # Process in sub-batches
                for j in range(0, len(images), current_batch_size):
                    batch_images = images[j:j + current_batch_size]
                    batch_valid_paths = valid_paths[j:j + current_batch_size]

                    # Preprocess batch
                    inputs = self._processor(images=batch_images, return_tensors="pt", padding=True)
                    inputs = {k: v.to(self._device) for k, v in inputs.items()}

                    # Extract features
                    with self._torch.no_grad():
                        image_features = self._model.get_image_features(**inputs)

                    # Convert to numpy and normalize
                    embeddings = image_features.cpu().numpy().astype('float32')
                    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
                    embeddings = embeddings / np.maximum(norms, 1e-8)

                    # Add to results
                    for path, emb in zip(batch_valid_paths, embeddings):
                        results.append((path, emb))

                    # Clear intermediate tensors
                    del inputs, image_features
                    if self._device and self._device.type == 'cuda':
                        self._torch.cuda.empty_cache()

                return results

            except RuntimeError as e:
                if 'out of memory' in str(e).lower() or 'CUDA' in str(e):
                    # OOM error - reduce batch size and retry
                    if self._device and self._device.type == 'cuda':
                        self._torch.cuda.empty_cache()

                    old_batch_size = current_batch_size
                    current_batch_size = max(1, current_batch_size // 2)

                    logger.warning(f"[SemanticEmbeddingService] OOM with batch size {old_batch_size}, "
                                   f"retrying with {current_batch_size}")

                    if current_batch_size == old_batch_size:
                        # Already at minimum, process one by one
                        break
                else:
                    # Other error - re-raise
                    raise

        # Fallback: process one by one
        logger.info("[SemanticEmbeddingService] Falling back to single-image processing")
        for path in image_paths:
            if any(r[0] == path for r in results):
                continue  # Already processed
            try:
                emb = self.encode_image(path)
                results.append((path, emb))
            except Exception as e:
                logger.warning(f"[SemanticEmbeddingService] Failed to encode {path}: {e}")
                results.append((path, None))

        return results

    def clear_gpu_cache(self):
        """
        Clear GPU memory cache to free up memory.

        Call this after processing large batches or when memory is low.
        """
        if self._available and self._device:
            if self._device.type == 'cuda':
                self._torch.cuda.empty_cache()
                self._torch.cuda.synchronize()
                logger.debug("[SemanticEmbeddingService] Cleared CUDA cache")
            elif self._device.type == 'mps':
                # MPS doesn't have explicit cache clearing
                import gc
                gc.collect()
                logger.debug("[SemanticEmbeddingService] Triggered garbage collection for MPS")

    def store_embedding(self,
                       photo_id: int,
                       embedding: np.ndarray,
                       source_hash: Optional[str] = None,
                       source_mtime: Optional[str] = None,
                       use_half_precision: bool = True,
                       project_id: Optional[int] = None,
                       enforce_canonical_model: bool = True):
        """
        Store semantic embedding in database.

        Uses float16 (half-precision) by default for 50% storage savings.
        The precision loss is negligible for similarity search (cosine similarity).

        WRITE BOUNDARY GUARD (Google Photos/Lightroom best practice):
        When project_id is provided and enforce_canonical_model is True,
        this method will reject writes if the embedding model doesn't match
        the project's canonical model. This prevents vector space contamination
        where embeddings from different models are silently mixed.

        Args:
            photo_id: Photo ID
            embedding: Normalized embedding vector
            source_hash: Optional SHA256 hash of source image
            source_mtime: Optional mtime of source file
            use_half_precision: If True, store as float16 (default). If False, use float32.
            project_id: Optional project ID for canonical model enforcement
            enforce_canonical_model: If True and project_id is provided, reject writes
                                   that don't match the project's canonical model

        Raises:
            ValueError: If enforce_canonical_model is True and model doesn't match
                       the project's canonical model
        """
        # WRITE BOUNDARY GUARD: Enforce canonical model per project
        # This is critical to prevent vector space contamination
        if project_id is not None and enforce_canonical_model:
            from repository.project_repository import ProjectRepository
            project_repo = ProjectRepository()
            canonical_model = project_repo.get_semantic_model(project_id)

            if self.model_name != canonical_model:
                error_msg = (
                    f"[SemanticEmbeddingService] WRITE BLOCKED: Cannot store embedding "
                    f"with model '{self.model_name}' for project {project_id}. "
                    f"Project's canonical model is '{canonical_model}'. "
                    f"Either use the canonical model or change the project's semantic_model setting."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

        # Validate normalization
        norm = float(np.linalg.norm(embedding))
        if not (0.99 <= norm <= 1.01):
            logger.warning(
                f"[SemanticEmbeddingService] Embedding not normalized! "
                f"norm={norm:.4f}, normalizing now..."
            )
            embedding = embedding / norm
            norm = 1.0

        # Serialize with half-precision for 50% storage savings
        # float16 has enough precision for similarity search (cosine similarity)
        # Precision: float32 = ~7 decimal digits, float16 = ~3 decimal digits
        # For normalized vectors, this is more than sufficient
        dim = len(embedding)

        if use_half_precision:
            embedding_blob = embedding.astype('float16').tobytes()
            # Store negative dim to indicate float16 format (backward compatible marker)
            stored_dim = -dim
        else:
            embedding_blob = embedding.astype('float32').tobytes()
            stored_dim = dim

        with self.db.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO semantic_embeddings
                (photo_id, model, embedding, dim, norm, source_photo_hash, source_photo_mtime, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (photo_id, self.model_name, embedding_blob, stored_dim, norm, source_hash, source_mtime))
            conn.commit()  # CRITICAL: Explicit commit to persist embeddings

            precision = "float16" if use_half_precision else "float32"
            logger.debug(f"[SemanticEmbeddingService] Stored {precision} embedding for photo {photo_id}")

    def get_embedding(self, photo_id: int) -> Optional[np.ndarray]:
        """
        Retrieve semantic embedding from database.

        Automatically handles both float16 (half-precision) and float32 (legacy) formats.
        Returns float32 for computation compatibility.

        Args:
            photo_id: Photo ID

        Returns:
            Embedding vector (float32) or None if not found
        """
        with self.db.get_connection() as conn:
            # Query all known aliases for backward compatibility
            # (old rows may use short key 'clip-vit-b32', new rows use HF name)
            placeholders = ",".join("?" for _ in self._model_aliases)
            cursor = conn.execute(f"""
                SELECT embedding, dim
                FROM semantic_embeddings
                WHERE photo_id = ? AND model IN ({placeholders})
            """, (photo_id, *self._model_aliases))

            row = cursor.fetchone()
            if row is None:
                return None

            embedding_blob = row['embedding']
            stored_dim = row['dim']

            # Deserialize
            if isinstance(embedding_blob, str):
                embedding_blob = embedding_blob.encode('latin1')

            # Detect precision from dim sign:
            # - Negative dim = float16 (new format, 50% smaller)
            # - Positive dim = float32 (legacy format)
            if stored_dim < 0:
                # Half-precision format
                actual_dim = -stored_dim
                embedding = np.frombuffer(embedding_blob, dtype='float16').astype('float32')
            else:
                # Legacy full-precision format
                actual_dim = stored_dim
                embedding = np.frombuffer(embedding_blob, dtype='float32')

            if len(embedding) != actual_dim:
                logger.warning(
                    f"[SemanticEmbeddingService] Dimension mismatch for photo {photo_id}: "
                    f"expected {actual_dim}, got {len(embedding)}"
                )
                return None

            return embedding

    def has_embedding(self, photo_id: int) -> bool:
        """Check if photo has semantic embedding."""
        with self.db.get_connection() as conn:
            placeholders = ",".join("?" for _ in self._model_aliases)
            cursor = conn.execute(f"""
                SELECT 1 FROM semantic_embeddings
                WHERE photo_id = ? AND model IN ({placeholders})
                LIMIT 1
            """, (photo_id, *self._model_aliases))

            return cursor.fetchone() is not None

    def get_embeddings_batch(self, photo_ids: list) -> dict:
        """
        Retrieve multiple embeddings in a single database query.

        This is much more efficient than calling get_embedding() N times,
        reducing database round-trips from N to 1.

        Automatically handles both float16 (half-precision) and float32 (legacy) formats.

        Args:
            photo_ids: List of photo IDs to retrieve

        Returns:
            Dictionary mapping photo_id -> embedding (np.ndarray, float32)
            Missing photos are not included in the result.
        """
        if not photo_ids:
            return {}

        embeddings = {}

        with self.db.get_connection() as conn:
            # Use parameterized query with IN clause
            # Include all model aliases for backward compatibility
            id_ph = ','.join('?' * len(photo_ids))
            model_ph = ','.join('?' * len(self._model_aliases))
            query = f"""
                SELECT photo_id, embedding, dim
                FROM semantic_embeddings
                WHERE photo_id IN ({id_ph}) AND model IN ({model_ph})
            """
            params = list(photo_ids) + list(self._model_aliases)

            cursor = conn.execute(query, params)

            for row in cursor.fetchall():
                photo_id = row['photo_id']
                embedding_blob = row['embedding']
                stored_dim = row['dim']

                # Deserialize
                if isinstance(embedding_blob, str):
                    embedding_blob = embedding_blob.encode('latin1')

                # Detect precision from dim sign
                if stored_dim < 0:
                    # Half-precision format
                    actual_dim = -stored_dim
                    embedding = np.frombuffer(embedding_blob, dtype='float16').astype('float32')
                else:
                    # Legacy full-precision format
                    actual_dim = stored_dim
                    embedding = np.frombuffer(embedding_blob, dtype='float32')

                if len(embedding) == actual_dim:
                    embeddings[photo_id] = embedding
                else:
                    logger.warning(
                        f"[SemanticEmbeddingService] Dimension mismatch for photo {photo_id}: "
                        f"expected {actual_dim}, got {len(embedding)}"
                    )

        logger.debug(f"[SemanticEmbeddingService] Batch loaded {len(embeddings)} embeddings for {len(photo_ids)} photos")
        return embeddings

    def get_all_embeddings_for_project(self, project_id: int) -> dict:
        """
        Get all embeddings for photos in a project (single query).

        Efficient batch load for similarity detection across entire project.
        Automatically handles both float16 (half-precision) and float32 (legacy) formats.

        Args:
            project_id: Project ID

        Returns:
            Dictionary mapping photo_id -> embedding (np.ndarray, float32)
        """
        embeddings = {}

        with self.db.get_connection() as conn:
            query = """
                SELECT se.photo_id, se.embedding, se.dim
                FROM semantic_embeddings se
                JOIN photo_metadata p ON se.photo_id = p.id
                WHERE p.project_id = ? AND se.model = ?
            """

            cursor = conn.execute(query, (project_id, self.model_name))

            for row in cursor.fetchall():
                photo_id = row['photo_id']
                embedding_blob = row['embedding']
                stored_dim = row['dim']

                if isinstance(embedding_blob, str):
                    embedding_blob = embedding_blob.encode('latin1')

                # Detect precision from dim sign
                if stored_dim < 0:
                    # Half-precision format
                    actual_dim = -stored_dim
                    embedding = np.frombuffer(embedding_blob, dtype='float16').astype('float32')
                else:
                    # Legacy full-precision format
                    actual_dim = stored_dim
                    embedding = np.frombuffer(embedding_blob, dtype='float32')

                if len(embedding) == actual_dim:
                    embeddings[photo_id] = embedding

        logger.info(f"[SemanticEmbeddingService] Loaded {len(embeddings)} embeddings for project {project_id}")
        return embeddings

    # =========================================================================
    # STALENESS DETECTION (v9.3.0: Pixel-based using dHash)
    # =========================================================================

    def is_embedding_stale(self, photo_id: int, file_path: str) -> bool:
        """
        Check if an embedding is stale (source image pixels have changed).

        v9.3.0: Uses pixel-based detection via perceptual hash (dHash).
        Compares the stored source_photo_hash against the current image_content_hash.

        An embedding is stale if:
        - The image pixels have changed (different content hash)
        - The stored hash is missing (legacy embedding)
        - The current content hash is missing (legacy scan)

        CRITICAL ADVANTAGE over mtime-based detection:
        - EXIF-only edits (rating, tags, GPS) do NOT cause false-positive staleness
        - Only actual pixel changes trigger re-embedding
        - Saves compute and storage by avoiding unnecessary re-processing

        Args:
            photo_id: Photo ID
            file_path: Current path to the photo file (unused but kept for API compatibility)

        Returns:
            True if embedding is stale and needs regeneration
        """
        try:
            with self.db.get_connection() as conn:
                # Get stored embedding hash AND current image content hash in single query
                cursor = conn.execute("""
                    SELECT se.source_photo_hash, pm.image_content_hash
                    FROM semantic_embeddings se
                    LEFT JOIN photo_metadata pm ON se.photo_id = pm.id
                    WHERE se.photo_id = ? AND se.model = ?
                """, (photo_id, self.model_name))

                row = cursor.fetchone()
                if row is None:
                    # No embedding exists - not stale, just missing
                    return False

                stored_hash = row['source_photo_hash']
                current_hash = row['image_content_hash']

            # If no stored hash (legacy embedding), consider it stale
            if stored_hash is None:
                logger.debug(f"[SemanticEmbeddingService] Photo {photo_id} has no stored hash - marking stale (legacy)")
                return True

            # If no current content hash (legacy scan), consider it stale
            # This will trigger re-scan which will compute the hash
            if current_hash is None:
                logger.debug(f"[SemanticEmbeddingService] Photo {photo_id} has no content hash in metadata - marking stale (needs rescan)")
                return True

            # Compare content hashes
            is_stale = stored_hash != current_hash
            if is_stale:
                logger.debug(f"[SemanticEmbeddingService] Photo {photo_id} is stale: stored_hash={stored_hash[:8]}..., current_hash={current_hash[:8]}...")

            return is_stale

        except Exception as e:
            logger.warning(f"[SemanticEmbeddingService] Error checking staleness for photo {photo_id}: {e}")
            return False

    def get_stale_embeddings_for_project(self, project_id: int, force: bool = False) -> list:
        """
        Get list of photo IDs with stale embeddings in a project.

        v9.3.0: Uses pixel-based detection via perceptual hash (dHash).
        Results are cached with a 5-minute TTL to avoid hammering the DB
        from the 30-second status-bar timer.  Pass ``force=True`` (or call
        ``invalidate_stale_cache``) to bypass the cache after a scan.

        Args:
            project_id: Project ID
            force: Skip cache and re-query the database

        Returns:
            List of (photo_id, file_path) tuples for photos with stale embeddings
        """
        import time

        # --- TTL cache check ---
        if not force and project_id in self._stale_cache:
            ts, cached = self._stale_cache[project_id]
            if (time.time() - ts) < self._stale_cache_ttl:
                return cached

        stale_photos = []

        with self.db.get_connection() as conn:
            query = """
                SELECT se.photo_id, p.path, se.source_photo_hash, p.image_content_hash
                FROM semantic_embeddings se
                JOIN photo_metadata p ON se.photo_id = p.id
                WHERE p.project_id = ? AND se.model = ?
                AND (
                    se.source_photo_hash IS NULL
                    OR p.image_content_hash IS NULL
                    OR se.source_photo_hash != p.image_content_hash
                )
            """

            cursor = conn.execute(query, (project_id, self.model_name))

            for row in cursor.fetchall():
                photo_id = row['photo_id']
                file_path = row['path']
                stale_photos.append((photo_id, file_path))

        # Store in cache
        self._stale_cache[project_id] = (time.time(), stale_photos)

        if stale_photos:
            logger.info(f"[SemanticEmbeddingService] Found {len(stale_photos)} stale embeddings in project {project_id} (pixel-hash based)")
        else:
            logger.debug(f"[SemanticEmbeddingService] No stale embeddings in project {project_id}")

        return stale_photos

    def invalidate_stale_cache(self, project_id: int = None):
        """Clear the stale-embeddings TTL cache (call after a scan or asset change)."""
        if project_id is not None:
            self._stale_cache.pop(project_id, None)
        else:
            self._stale_cache.clear()

    def invalidate_stale_embeddings(self, project_id: int) -> int:
        """
        Delete stale embeddings so they will be regenerated on next scan.

        Args:
            project_id: Project ID

        Returns:
            Number of embeddings invalidated (deleted)
        """
        stale_photos = self.get_stale_embeddings_for_project(project_id)

        if not stale_photos:
            return 0

        photo_ids = [photo_id for photo_id, _ in stale_photos]

        with self.db.get_connection() as conn:
            placeholders = ','.join('?' * len(photo_ids))
            query = f"""
                DELETE FROM semantic_embeddings
                WHERE photo_id IN ({placeholders}) AND model = ?
            """
            params = photo_ids + [self.model_name]
            conn.execute(query, params)
            conn.commit()

        logger.info(f"[SemanticEmbeddingService] Invalidated {len(photo_ids)} stale embeddings")
        # Bust TTL cache since we just deleted rows
        self.invalidate_stale_cache(project_id)
        return len(photo_ids)

    def get_staleness_stats(self, project_id: int) -> dict:
        """
        Get statistics about embedding staleness for a project.

        v9.3.0: Uses pixel-based detection via perceptual hash (dHash).

        Args:
            project_id: Project ID

        Returns:
            Dictionary with stats: total, fresh, stale, missing_hash (legacy embeddings)
        """
        stats = {
            'total': 0,
            'fresh': 0,
            'stale': 0,
            'missing_hash': 0  # Renamed from missing_mtime for v9.3.0
        }

        with self.db.get_connection() as conn:
            # Count total embeddings
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM semantic_embeddings se
                JOIN photo_metadata p ON se.photo_id = p.id
                WHERE p.project_id = ? AND se.model = ?
            """, (project_id, self.model_name))
            stats['total'] = cursor.fetchone()['count']

            # Count embeddings without source hash (legacy)
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM semantic_embeddings se
                JOIN photo_metadata p ON se.photo_id = p.id
                WHERE p.project_id = ? AND se.model = ?
                AND se.source_photo_hash IS NULL
            """, (project_id, self.model_name))
            stats['missing_hash'] = cursor.fetchone()['count']

        # Get staleness info using the efficient query
        stale_photos = self.get_stale_embeddings_for_project(project_id)
        stats['stale'] = len(stale_photos)
        stats['fresh'] = stats['total'] - stats['stale']

        return stats

    # =========================================================================
    # STORAGE STATISTICS
    # =========================================================================

    def get_storage_stats(self) -> dict:
        """
        Get storage statistics for embeddings.

        Returns breakdown of float16 vs float32 embeddings and space savings.

        Returns:
            Dictionary with:
            - total_embeddings: Total count
            - float16_count: Embeddings stored as float16 (new format)
            - float32_count: Embeddings stored as float32 (legacy)
            - total_bytes: Actual storage used
            - float32_equivalent_bytes: What storage would be with all float32
            - space_saved_bytes: Bytes saved by using float16
            - space_saved_percent: Percentage of space saved
        """
        stats = {
            'total_embeddings': 0,
            'float16_count': 0,
            'float32_count': 0,
            'total_bytes': 0,
            'float32_equivalent_bytes': 0,
            'space_saved_bytes': 0,
            'space_saved_percent': 0.0
        }

        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT dim, LENGTH(embedding) as blob_size
                FROM semantic_embeddings
                WHERE model = ?
            """, (self.model_name,))

            for row in cursor.fetchall():
                stored_dim = row['dim']
                blob_size = row['blob_size']

                stats['total_embeddings'] += 1
                stats['total_bytes'] += blob_size

                if stored_dim < 0:
                    # float16 format
                    stats['float16_count'] += 1
                    actual_dim = -stored_dim
                    # float32 would use 4 bytes per dimension
                    stats['float32_equivalent_bytes'] += actual_dim * 4
                else:
                    # float32 format (legacy)
                    stats['float32_count'] += 1
                    stats['float32_equivalent_bytes'] += blob_size

        if stats['float32_equivalent_bytes'] > 0:
            stats['space_saved_bytes'] = stats['float32_equivalent_bytes'] - stats['total_bytes']
            stats['space_saved_percent'] = (stats['space_saved_bytes'] / stats['float32_equivalent_bytes']) * 100

        return stats

    def migrate_to_half_precision(self, batch_size: int = 100) -> int:
        """
        Migrate existing float32 embeddings to float16 format.

        This is a one-time migration that saves ~50% storage space.
        Safe to run multiple times - only affects float32 embeddings.

        Args:
            batch_size: Number of embeddings to process per batch

        Returns:
            Number of embeddings migrated
        """
        migrated = 0

        with self.db.get_connection() as conn:
            # Find float32 embeddings (positive dim)
            cursor = conn.execute("""
                SELECT photo_id, embedding, dim
                FROM semantic_embeddings
                WHERE model = ? AND dim > 0
                LIMIT ?
            """, (self.model_name, batch_size))

            rows = cursor.fetchall()

            for row in rows:
                photo_id = row['photo_id']
                embedding_blob = row['embedding']
                dim = row['dim']

                if isinstance(embedding_blob, str):
                    embedding_blob = embedding_blob.encode('latin1')

                # Deserialize float32
                embedding = np.frombuffer(embedding_blob, dtype='float32')

                if len(embedding) != dim:
                    logger.warning(f"[SemanticEmbeddingService] Skipping corrupted embedding for photo {photo_id}")
                    continue

                # Convert to float16 and store
                new_blob = embedding.astype('float16').tobytes()
                new_dim = -dim  # Negative dim indicates float16

                conn.execute("""
                    UPDATE semantic_embeddings
                    SET embedding = ?, dim = ?
                    WHERE photo_id = ? AND model = ?
                """, (new_blob, new_dim, photo_id, self.model_name))

                migrated += 1

            conn.commit()

        if migrated > 0:
            logger.info(f"[SemanticEmbeddingService] Migrated {migrated} embeddings to float16 format")

        return migrated

    # =========================================================================
    # EMBEDDING STATISTICS DASHBOARD
    # =========================================================================

    def get_project_embedding_stats(self, project_id: int) -> dict:
        """
        Get comprehensive embedding statistics for a project (for UI dashboard).

        Provides all metrics needed for the embedding statistics dashboard.

        Args:
            project_id: Project ID

        Returns:
            Dictionary with comprehensive stats for UI display
        """
        stats = {
            # Coverage
            'total_photos': 0,
            'photos_with_embeddings': 0,
            'photos_without_embeddings': 0,
            'coverage_percent': 0.0,

            # Staleness (v9.3.0: pixel-hash based)
            'fresh_embeddings': 0,
            'stale_embeddings': 0,
            'missing_hash': 0,

            # Storage
            'storage_bytes': 0,
            'storage_mb': 0.0,
            'float16_count': 0,
            'float32_count': 0,
            'space_saved_percent': 0.0,

            # Model info
            'model_name': self.model_name,
            'embedding_dimension': 512,  # Default for CLIP ViT-B/32

            # GPU info
            'gpu_device': 'unknown',
            'gpu_memory_mb': 0,

            # Job status
            'has_incomplete_job': False,
            'job_progress_percent': 0.0,

            # Performance
            'faiss_available': _faiss_available,
        }

        with self.db.get_connection() as conn:
            # Get total photos in project
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM photo_metadata WHERE project_id = ?
            """, (project_id,))
            stats['total_photos'] = cursor.fetchone()['count']

            # Get photos with embeddings
            cursor = conn.execute("""
                SELECT COUNT(DISTINCT se.photo_id) as count
                FROM semantic_embeddings se
                JOIN photo_metadata p ON se.photo_id = p.id
                WHERE p.project_id = ? AND se.model = ?
            """, (project_id, self.model_name))
            stats['photos_with_embeddings'] = cursor.fetchone()['count']

            stats['photos_without_embeddings'] = stats['total_photos'] - stats['photos_with_embeddings']

            if stats['total_photos'] > 0:
                stats['coverage_percent'] = (stats['photos_with_embeddings'] / stats['total_photos']) * 100

            # Get storage stats for project
            cursor = conn.execute("""
                SELECT se.dim, LENGTH(se.embedding) as blob_size
                FROM semantic_embeddings se
                JOIN photo_metadata p ON se.photo_id = p.id
                WHERE p.project_id = ? AND se.model = ?
            """, (project_id, self.model_name))

            float32_equivalent = 0
            for row in cursor.fetchall():
                stored_dim = row['dim']
                blob_size = row['blob_size']
                stats['storage_bytes'] += blob_size

                if stored_dim < 0:
                    stats['float16_count'] += 1
                    stats['embedding_dimension'] = -stored_dim
                    float32_equivalent += (-stored_dim) * 4
                else:
                    stats['float32_count'] += 1
                    stats['embedding_dimension'] = stored_dim
                    float32_equivalent += blob_size

            stats['storage_mb'] = stats['storage_bytes'] / (1024 * 1024)

            if float32_equivalent > 0:
                saved = float32_equivalent - stats['storage_bytes']
                stats['space_saved_percent'] = (saved / float32_equivalent) * 100

            # Get embeddings without source hash (legacy - v9.3.0)
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM semantic_embeddings se
                JOIN photo_metadata p ON se.photo_id = p.id
                WHERE p.project_id = ? AND se.model = ?
                AND se.source_photo_hash IS NULL
            """, (project_id, self.model_name))
            stats['missing_hash'] = cursor.fetchone()['count']

        # Get staleness info (may be slow for large projects)
        try:
            stale_photos = self.get_stale_embeddings_for_project(project_id)
            stats['stale_embeddings'] = len(stale_photos)
            stats['fresh_embeddings'] = stats['photos_with_embeddings'] - stats['stale_embeddings']
        except Exception as e:
            logger.warning(f"[SemanticEmbeddingService] Could not check staleness: {e}")
            stats['fresh_embeddings'] = stats['photos_with_embeddings']

        # Get GPU info
        try:
            gpu_info = self.get_gpu_memory_info()
            stats['gpu_device'] = gpu_info['device_type']
            stats['gpu_memory_mb'] = gpu_info['total_memory_mb']
        except Exception:
            pass

        # Get job status
        try:
            stats['has_incomplete_job'] = self.has_incomplete_job(project_id)
            if stats['has_incomplete_job']:
                progress = self.get_job_progress(project_id)
                if progress:
                    stats['job_progress_percent'] = progress.get('progress_percent', 0)
        except Exception:
            pass

        return stats

    def get_all_projects_embedding_stats(self) -> List[dict]:
        """
        Get embedding statistics for all projects.

        Returns:
            List of stats dictionaries, one per project
        """
        all_stats = []

        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT DISTINCT id, name FROM projects ORDER BY name
            """)

            for row in cursor.fetchall():
                project_id = row['id']
                project_name = row['name']

                try:
                    stats = self.get_project_embedding_stats(project_id)
                    stats['project_id'] = project_id
                    stats['project_name'] = project_name
                    all_stats.append(stats)
                except Exception as e:
                    logger.warning(f"[SemanticEmbeddingService] Error getting stats for project {project_id}: {e}")

        return all_stats

    # =========================================================================
    # APPROXIMATE NEAREST NEIGHBOR (ANN) SEARCH
    # =========================================================================

    def build_similarity_index(self, embeddings: Dict[int, np.ndarray]) -> Tuple[object, List[int]]:
        """
        Build a similarity index for fast nearest neighbor search.

        Uses FAISS for large collections (500+ embeddings), falls back to
        numpy for smaller collections or when FAISS isn't available.

        Args:
            embeddings: Dictionary mapping photo_id -> embedding vector

        Returns:
            Tuple of (index, photo_ids_list) where index is either FAISS index
            or numpy array, and photo_ids_list maps index positions to photo IDs
        """
        if not embeddings:
            return None, []

        # Convert to numpy array and track photo_id mapping
        photo_ids = list(embeddings.keys())
        vectors = np.array([embeddings[pid] for pid in photo_ids], dtype='float32')

        # Normalize vectors for cosine similarity (FAISS uses inner product)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / np.maximum(norms, 1e-8)

        n_vectors = len(photo_ids)
        dim = vectors.shape[1]

        # Use FAISS for large collections if available
        if _faiss_available and n_vectors >= 500:
            # Use IndexFlatIP (inner product = cosine similarity for normalized vectors)
            index = _faiss.IndexFlatIP(dim)
            index.add(vectors)
            logger.info(f"[SemanticEmbeddingService] Built FAISS index with {n_vectors} vectors (dim={dim})")
            return ('faiss', index, vectors), photo_ids
        else:
            # Use numpy array for brute force (small collections or no FAISS)
            logger.debug(f"[SemanticEmbeddingService] Using numpy for similarity search ({n_vectors} vectors)")
            return ('numpy', None, vectors), photo_ids

    def find_similar_photos(self,
                           query_embedding: np.ndarray,
                           embeddings: Dict[int, np.ndarray],
                           top_k: int = 10,
                           threshold: float = 0.75,
                           exclude_photo_id: Optional[int] = None) -> List[Tuple[int, float]]:
        """
        Find photos most similar to a query embedding.

        Uses FAISS for O(log n) search on large collections, falls back to
        numpy brute force O(n) for small collections.

        Args:
            query_embedding: Query embedding vector (normalized)
            embeddings: Dictionary mapping photo_id -> embedding vector
            top_k: Maximum number of results to return
            threshold: Minimum similarity score (0-1)
            exclude_photo_id: Optional photo ID to exclude from results

        Returns:
            List of (photo_id, similarity_score) tuples, sorted by similarity descending
        """
        if not embeddings:
            return []

        # Normalize query
        query = query_embedding.astype('float32')
        query = query / np.maximum(np.linalg.norm(query), 1e-8)
        query = query.reshape(1, -1)

        # Build index
        index_data, photo_ids = self.build_similarity_index(embeddings)
        if index_data is None:
            return []

        index_type, index, vectors = index_data
        results = []

        if index_type == 'faiss' and _faiss_available:
            # FAISS search (fast for large collections)
            k = min(top_k + 1, len(photo_ids))  # +1 in case we need to exclude self
            similarities, indices = index.search(query, k)

            for sim, idx in zip(similarities[0], indices[0]):
                if idx < 0 or idx >= len(photo_ids):
                    continue
                photo_id = photo_ids[idx]
                if exclude_photo_id and photo_id == exclude_photo_id:
                    continue
                if sim >= threshold:
                    results.append((photo_id, float(sim)))
                if len(results) >= top_k:
                    break

        else:
            # Numpy brute force (for small collections or no FAISS)
            similarities = np.dot(vectors, query.T).flatten()

            # Get top-k indices
            if len(similarities) > top_k + 1:
                top_indices = np.argpartition(similarities, -top_k - 1)[-top_k - 1:]
                top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]
            else:
                top_indices = np.argsort(similarities)[::-1]

            for idx in top_indices:
                photo_id = photo_ids[idx]
                sim = similarities[idx]
                if exclude_photo_id and photo_id == exclude_photo_id:
                    continue
                if sim >= threshold:
                    results.append((photo_id, float(sim)))
                if len(results) >= top_k:
                    break

        return results

    def find_all_similar_pairs(self,
                               embeddings: Dict[int, np.ndarray],
                               threshold: float = 0.75,
                               max_pairs_per_photo: int = 5) -> Dict[int, List[Tuple[int, float]]]:
        """
        Find all similar photo pairs in a collection (for clustering/stacking).

        Efficiently finds similar pairs using FAISS batch search.

        Args:
            embeddings: Dictionary mapping photo_id -> embedding vector
            threshold: Minimum similarity score (0-1)
            max_pairs_per_photo: Maximum similar photos per source photo

        Returns:
            Dictionary mapping photo_id -> [(similar_photo_id, similarity), ...]
        """
        if len(embeddings) < 2:
            return {}

        # Build index
        index_data, photo_ids = self.build_similarity_index(embeddings)
        if index_data is None:
            return {}

        index_type, index, vectors = index_data
        similar_pairs = {}

        n_photos = len(photo_ids)
        k = min(max_pairs_per_photo + 1, n_photos)  # +1 to exclude self

        if index_type == 'faiss' and _faiss_available:
            # FAISS batch search (much faster for large collections)
            similarities, indices = index.search(vectors, k)

            for i, photo_id in enumerate(photo_ids):
                pairs = []
                for sim, idx in zip(similarities[i], indices[i]):
                    if idx < 0 or idx >= n_photos:
                        continue
                    other_id = photo_ids[idx]
                    if other_id == photo_id:  # Skip self
                        continue
                    if sim >= threshold:
                        pairs.append((other_id, float(sim)))
                if pairs:
                    similar_pairs[photo_id] = pairs

            logger.info(f"[SemanticEmbeddingService] FAISS found {sum(len(v) for v in similar_pairs.values())} "
                        f"similar pairs among {n_photos} photos")

        else:
            # Numpy batch computation
            # Compute all pairwise similarities at once
            similarity_matrix = np.dot(vectors, vectors.T)

            for i, photo_id in enumerate(photo_ids):
                sims = similarity_matrix[i]
                # Get top-k (excluding self)
                sims[i] = -1  # Exclude self

                if n_photos > k:
                    top_indices = np.argpartition(sims, -k)[-k:]
                    top_indices = top_indices[np.argsort(sims[top_indices])[::-1]]
                else:
                    top_indices = np.argsort(sims)[::-1]

                pairs = []
                for idx in top_indices:
                    if sims[idx] >= threshold:
                        pairs.append((photo_ids[idx], float(sims[idx])))
                    if len(pairs) >= max_pairs_per_photo:
                        break

                if pairs:
                    similar_pairs[photo_id] = pairs

            logger.debug(f"[SemanticEmbeddingService] Numpy found {sum(len(v) for v in similar_pairs.values())} "
                         f"similar pairs among {n_photos} photos")

        return similar_pairs

    @staticmethod
    def is_faiss_available() -> bool:
        """Check if FAISS is available for fast similarity search."""
        return _faiss_available

    def get_embedding_count(self) -> int:
        """Get total number of semantic embeddings for this model (including aliases)."""
        with self.db.get_connection() as conn:
            placeholders = ",".join("?" for _ in self._model_aliases)
            cursor = conn.execute(f"""
                SELECT COUNT(*) as count
                FROM semantic_embeddings
                WHERE model IN ({placeholders})
            """, tuple(self._model_aliases))

            return cursor.fetchone()['count']

    # =========================================================================
    # RESUMABLE JOB TRACKING
    # =========================================================================

    def save_job_progress(self, project_id: int, last_photo_id: int, total_photos: int,
                          processed_count: int, status: str = "in_progress"):
        """
        Save embedding job progress for resumability.

        Allows interrupted jobs to resume from where they stopped,
        preventing wasted work on large imports.

        Args:
            project_id: Project being processed
            last_photo_id: Last successfully processed photo ID
            total_photos: Total photos in the job
            processed_count: Number of photos processed so far
            status: Job status ('in_progress', 'completed', 'failed')
        """
        import json
        from datetime import datetime

        progress_data = {
            'project_id': project_id,
            'last_photo_id': last_photo_id,
            'total_photos': total_photos,
            'processed_count': processed_count,
            'status': status,
            'model': self.model_name,
            'updated_at': datetime.now().isoformat()
        }

        with self.db.get_connection() as conn:
            # Create job_progress table if not exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embedding_job_progress (
                    project_id INTEGER PRIMARY KEY,
                    model TEXT NOT NULL,
                    last_photo_id INTEGER,
                    total_photos INTEGER,
                    processed_count INTEGER,
                    status TEXT DEFAULT 'in_progress',
                    started_at TEXT,
                    updated_at TEXT,
                    completed_at TEXT
                )
            """)

            # Check if job exists
            cursor = conn.execute("""
                SELECT 1 FROM embedding_job_progress
                WHERE project_id = ? AND model = ?
            """, (project_id, self.model_name))

            if cursor.fetchone():
                # Update existing job
                if status == 'completed':
                    conn.execute("""
                        UPDATE embedding_job_progress
                        SET last_photo_id = ?, total_photos = ?, processed_count = ?,
                            status = ?, updated_at = ?, completed_at = ?
                        WHERE project_id = ? AND model = ?
                    """, (last_photo_id, total_photos, processed_count, status,
                          progress_data['updated_at'], progress_data['updated_at'],
                          project_id, self.model_name))
                else:
                    conn.execute("""
                        UPDATE embedding_job_progress
                        SET last_photo_id = ?, total_photos = ?, processed_count = ?,
                            status = ?, updated_at = ?
                        WHERE project_id = ? AND model = ?
                    """, (last_photo_id, total_photos, processed_count, status,
                          progress_data['updated_at'], project_id, self.model_name))
            else:
                # Insert new job
                conn.execute("""
                    INSERT INTO embedding_job_progress
                    (project_id, model, last_photo_id, total_photos, processed_count,
                     status, started_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (project_id, self.model_name, last_photo_id, total_photos,
                      processed_count, status, progress_data['updated_at'],
                      progress_data['updated_at']))

            conn.commit()

        logger.debug(f"[SemanticEmbeddingService] Saved job progress: project={project_id}, "
                     f"processed={processed_count}/{total_photos}, status={status}")

    def get_job_progress(self, project_id: int) -> Optional[dict]:
        """
        Get saved job progress for a project.

        Args:
            project_id: Project ID

        Returns:
            Progress dict or None if no saved progress
        """
        with self.db.get_connection() as conn:
            # Check if table exists
            cursor = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='embedding_job_progress'
            """)
            if not cursor.fetchone():
                return None

            cursor = conn.execute("""
                SELECT project_id, model, last_photo_id, total_photos, processed_count,
                       status, started_at, updated_at, completed_at
                FROM embedding_job_progress
                WHERE project_id = ? AND model = ?
            """, (project_id, self.model_name))

            row = cursor.fetchone()
            if row is None:
                return None

            return {
                'project_id': row['project_id'],
                'model': row['model'],
                'last_photo_id': row['last_photo_id'],
                'total_photos': row['total_photos'],
                'processed_count': row['processed_count'],
                'status': row['status'],
                'started_at': row['started_at'],
                'updated_at': row['updated_at'],
                'completed_at': row['completed_at'],
                'progress_percent': (row['processed_count'] / row['total_photos'] * 100)
                                    if row['total_photos'] > 0 else 0
            }

    def get_resumable_photo_ids(self, project_id: int, all_photo_ids: List[int]) -> List[int]:
        """
        Get photo IDs that still need processing (for job resume).

        Filters out already-processed photos to resume from where we left off.

        Args:
            project_id: Project ID
            all_photo_ids: Full list of photo IDs that need embeddings

        Returns:
            Filtered list of photo IDs still needing processing
        """
        progress = self.get_job_progress(project_id)

        if progress is None or progress['status'] == 'completed':
            # No saved progress or job completed - process all
            return all_photo_ids

        last_photo_id = progress.get('last_photo_id')
        if last_photo_id is None:
            return all_photo_ids

        # Find the index of last processed photo and return remaining
        try:
            last_index = all_photo_ids.index(last_photo_id)
            remaining = all_photo_ids[last_index + 1:]
            logger.info(f"[SemanticEmbeddingService] Resuming job: skipping {last_index + 1} already processed, "
                        f"{len(remaining)} remaining")
            return remaining
        except ValueError:
            # last_photo_id not in list - process all
            logger.warning(f"[SemanticEmbeddingService] Last photo ID {last_photo_id} not in current list, "
                           "starting fresh")
            return all_photo_ids

    def clear_job_progress(self, project_id: int):
        """
        Clear saved job progress (call when job completes or user cancels).

        Args:
            project_id: Project ID
        """
        with self.db.get_connection() as conn:
            # Check if table exists
            cursor = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='embedding_job_progress'
            """)
            if cursor.fetchone():
                conn.execute("""
                    DELETE FROM embedding_job_progress
                    WHERE project_id = ? AND model = ?
                """, (project_id, self.model_name))
                conn.commit()

        logger.debug(f"[SemanticEmbeddingService] Cleared job progress for project {project_id}")

    def has_incomplete_job(self, project_id: int) -> bool:
        """
        Check if there's an incomplete job that can be resumed.

        Args:
            project_id: Project ID

        Returns:
            True if there's an in-progress job
        """
        progress = self.get_job_progress(project_id)
        return progress is not None and progress['status'] == 'in_progress'


# Per-model service cache (singleton per model, not global singleton)
# This prevents model mismatch bugs when different code paths request different models
_semantic_services: Dict[str, SemanticEmbeddingService] = {}


def get_semantic_embedding_service(model_name: str = "openai/clip-vit-base-patch32") -> SemanticEmbeddingService:
    """
    Get semantic embedding service for a specific model (thread-safe).

    Uses per-model caching: each model gets its own singleton instance.
    This is safer than a global singleton because:
    - Different code paths can use different models without conflict
    - The model_name parameter is actually respected
    - Prevents subtle bugs where first caller "wins" with their model choice

    Args:
        model_name: CLIP/SigLIP model variant (canonical HuggingFace ID or short alias)
                   Default: "openai/clip-vit-base-patch32" (canonical ID for CLIP ViT-B/32)

    Returns:
        SemanticEmbeddingService instance for the specified model
    """
    global _semantic_services

    # Normalize to canonical model ID for consistent cache keys
    from utils.clip_model_registry import normalize_model_id
    canonical_key = normalize_model_id(model_name)

    # Fast path: check without lock
    if canonical_key in _semantic_services:
        return _semantic_services[canonical_key]

    # Slow path: acquire lock and double-check
    with _service_lock:
        if canonical_key not in _semantic_services:
            logger.info(f"[SemanticEmbeddingService] Creating service for model: {canonical_key}")
            _semantic_services[canonical_key] = SemanticEmbeddingService(model_name=canonical_key)
        return _semantic_services[canonical_key]
