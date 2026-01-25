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
from typing import Optional, Tuple
from PIL import Image

from repository.base_repository import DatabaseConnection
from logging_config import get_logger

logger = get_logger(__name__)

# Thread-safe singleton lock
_service_lock = threading.Lock()


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
                 model_name: str = "clip-vit-b32",
                 db_connection: Optional[DatabaseConnection] = None):
        """
        Initialize semantic embedding service.

        Args:
            model_name: CLIP/SigLIP model variant
                       'clip-vit-b32', 'clip-vit-b16', 'clip-vit-l14'
            db_connection: Optional database connection
        """
        self.model_name = model_name
        self.db = db_connection or DatabaseConnection()

        # Model cache (lazy loading)
        self._model = None
        self._processor = None
        self._device = None
        self._load_attempted = False  # Track if we've tried to load (prevents retrying on every photo)
        self._load_error = None  # Store error if loading failed
        self._load_lock = threading.Lock()  # Thread-safe model loading

        # Try to import dependencies
        self._available = False
        try:
            import torch
            from transformers import CLIPProcessor, CLIPModel
            self._torch = torch
            self._CLIPProcessor = CLIPProcessor
            self._CLIPModel = CLIPModel
            self._available = True
            logger.info(f"[SemanticEmbeddingService] Initialized with model={model_name}")
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

            # Map model name to HuggingFace ID
            model_map = {
                'clip-vit-b32': 'openai/clip-vit-base-patch32',
                'clip-vit-b16': 'openai/clip-vit-base-patch16',
                'clip-vit-l14': 'openai/clip-vit-large-patch14',
            }
            hf_model = model_map.get(self.model_name, self.model_name)

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
                    if clip_path_obj.exists() and (clip_path_obj / 'config.json').exists():
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
                            if not has_config and (model_folder / 'snapshots').exists():
                                # HF cache structure: models--xxx/snapshots/hash/
                                try:
                                    snapshots_dir = model_folder / 'snapshots'
                                    snapshot_folders = [d for d in snapshots_dir.iterdir() if d.is_dir()]
                                    if snapshot_folders:
                                        # Use the most recent snapshot
                                        latest_snapshot = max(snapshot_folders, key=lambda p: p.stat().st_mtime)
                                        if (latest_snapshot / 'config.json').exists():
                                            logger.info(f"[SemanticEmbeddingService]     → ✓ VALID MODEL FOUND in HF cache snapshot!")
                                            local_model_path = str(latest_snapshot)
                                            break
                                except Exception as e:
                                    logger.warning(f"[SemanticEmbeddingService]     → Error checking snapshots: {e}")

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

    def store_embedding(self,
                       photo_id: int,
                       embedding: np.ndarray,
                       source_hash: Optional[str] = None,
                       source_mtime: Optional[str] = None):
        """
        Store semantic embedding in database.

        Args:
            photo_id: Photo ID
            embedding: Normalized embedding vector
            source_hash: Optional SHA256 hash of source image
            source_mtime: Optional mtime of source file
        """
        # Validate normalization
        norm = float(np.linalg.norm(embedding))
        if not (0.99 <= norm <= 1.01):
            logger.warning(
                f"[SemanticEmbeddingService] Embedding not normalized! "
                f"norm={norm:.4f}, normalizing now..."
            )
            embedding = embedding / norm
            norm = 1.0

        # Serialize
        embedding_blob = embedding.astype('float32').tobytes()
        dim = len(embedding)

        with self.db.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO semantic_embeddings
                (photo_id, model, embedding, dim, norm, source_photo_hash, source_photo_mtime, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (photo_id, self.model_name, embedding_blob, dim, norm, source_hash, source_mtime))
            conn.commit()  # CRITICAL: Explicit commit to persist embeddings

            logger.debug(f"[SemanticEmbeddingService] Stored embedding for photo {photo_id}")

    def get_embedding(self, photo_id: int) -> Optional[np.ndarray]:
        """
        Retrieve semantic embedding from database.

        Args:
            photo_id: Photo ID

        Returns:
            Embedding vector or None if not found
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT embedding, dim
                FROM semantic_embeddings
                WHERE photo_id = ? AND model = ?
            """, (photo_id, self.model_name))

            row = cursor.fetchone()
            if row is None:
                return None

            embedding_blob = row['embedding']
            dim = row['dim']

            # Deserialize
            if isinstance(embedding_blob, str):
                embedding_blob = embedding_blob.encode('latin1')

            embedding = np.frombuffer(embedding_blob, dtype='float32')

            if len(embedding) != dim:
                logger.warning(
                    f"[SemanticEmbeddingService] Dimension mismatch for photo {photo_id}: "
                    f"expected {dim}, got {len(embedding)}"
                )
                return None

            return embedding

    def has_embedding(self, photo_id: int) -> bool:
        """Check if photo has semantic embedding."""
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT 1 FROM semantic_embeddings
                WHERE photo_id = ? AND model = ?
                LIMIT 1
            """, (photo_id, self.model_name))

            return cursor.fetchone() is not None

    def get_embeddings_batch(self, photo_ids: list) -> dict:
        """
        Retrieve multiple embeddings in a single database query.

        This is much more efficient than calling get_embedding() N times,
        reducing database round-trips from N to 1.

        Args:
            photo_ids: List of photo IDs to retrieve

        Returns:
            Dictionary mapping photo_id -> embedding (np.ndarray)
            Missing photos are not included in the result.
        """
        if not photo_ids:
            return {}

        embeddings = {}

        with self.db.get_connection() as conn:
            # Use parameterized query with IN clause
            placeholders = ','.join('?' * len(photo_ids))
            query = f"""
                SELECT photo_id, embedding, dim
                FROM semantic_embeddings
                WHERE photo_id IN ({placeholders}) AND model = ?
            """
            params = list(photo_ids) + [self.model_name]

            cursor = conn.execute(query, params)

            for row in cursor.fetchall():
                photo_id = row['photo_id']
                embedding_blob = row['embedding']
                dim = row['dim']

                # Deserialize
                if isinstance(embedding_blob, str):
                    embedding_blob = embedding_blob.encode('latin1')

                embedding = np.frombuffer(embedding_blob, dtype='float32')

                if len(embedding) == dim:
                    embeddings[photo_id] = embedding
                else:
                    logger.warning(
                        f"[SemanticEmbeddingService] Dimension mismatch for photo {photo_id}: "
                        f"expected {dim}, got {len(embedding)}"
                    )

        logger.debug(f"[SemanticEmbeddingService] Batch loaded {len(embeddings)} embeddings for {len(photo_ids)} photos")
        return embeddings

    def get_all_embeddings_for_project(self, project_id: int) -> dict:
        """
        Get all embeddings for photos in a project (single query).

        Efficient batch load for similarity detection across entire project.

        Args:
            project_id: Project ID

        Returns:
            Dictionary mapping photo_id -> embedding (np.ndarray)
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
                dim = row['dim']

                if isinstance(embedding_blob, str):
                    embedding_blob = embedding_blob.encode('latin1')

                embedding = np.frombuffer(embedding_blob, dtype='float32')

                if len(embedding) == dim:
                    embeddings[photo_id] = embedding

        logger.info(f"[SemanticEmbeddingService] Loaded {len(embeddings)} embeddings for project {project_id}")
        return embeddings

    def get_embedding_count(self) -> int:
        """Get total number of semantic embeddings for this model."""
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM semantic_embeddings
                WHERE model = ?
            """, (self.model_name,))

            return cursor.fetchone()['count']


# Singleton instance
_semantic_embedding_service = None


def get_semantic_embedding_service(model_name: str = "clip-vit-b32") -> SemanticEmbeddingService:
    """
    Get singleton semantic embedding service (thread-safe).

    Uses double-checked locking pattern for thread safety without
    acquiring lock on every call.

    Args:
        model_name: CLIP/SigLIP model variant

    Returns:
        SemanticEmbeddingService instance
    """
    global _semantic_embedding_service

    # Fast path: check without lock (most common case)
    if _semantic_embedding_service is not None:
        return _semantic_embedding_service

    # Slow path: acquire lock and double-check
    with _service_lock:
        # Another thread may have created instance while we waited for lock
        if _semantic_embedding_service is None:
            _semantic_embedding_service = SemanticEmbeddingService(model_name=model_name)
        return _semantic_embedding_service
