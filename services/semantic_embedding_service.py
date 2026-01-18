"""
SemanticEmbeddingService - Clean Architectural Separation

Version: 1.0.0
Date: 2026-01-05

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

import numpy as np
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

from repository.base_repository import DatabaseConnection
from logging_config import get_logger

logger = get_logger(__name__)


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
        """
        if self._model is not None:
            return

        if not self._available:
            raise RuntimeError("PyTorch/Transformers not available")

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
                if clip_path_obj.exists() and (clip_path_obj / 'config.json').exists():
                    local_model_path = str(clip_path_obj)
                    logger.info(f"[SemanticEmbeddingService] Using stored preference: {local_model_path}")
        except Exception as e:
            logger.warning(f"[SemanticEmbeddingService] Could not check stored preference: {e}")

        # STEP 2: Check for offline models in standard locations
        if not local_model_path:
            try:
                from pathlib import Path
                app_root = Path(__file__).parent.parent.absolute()
                folder_name = hf_model.replace('/', '--')

                # Check Model folder (uppercase)
                model_folder = app_root / 'Model' / folder_name
                if model_folder.exists() and (model_folder / 'config.json').exists():
                    local_model_path = str(model_folder)
                    logger.info(f"[SemanticEmbeddingService] Found in Model folder: {local_model_path}")
                else:
                    # Check models folder (lowercase)
                    model_folder = app_root / 'models' / folder_name
                    if model_folder.exists() and (model_folder / 'config.json').exists():
                        local_model_path = str(model_folder)
                        logger.info(f"[SemanticEmbeddingService] Found in models folder: {local_model_path}")
            except Exception as e:
                logger.warning(f"[SemanticEmbeddingService] Could not check for local models: {e}")

        # STEP 3: If no offline model found, show user dialog for model selection
        if not local_model_path:
            logger.warning(f"[SemanticEmbeddingService] No offline model found for {hf_model}")
            logger.info("[SemanticEmbeddingService] Showing model selection dialog to user")

            # Show dialog (only if we have GUI context)
            try:
                from ui.clip_model_dialog import show_clip_model_dialog
                from PySide6.QtWidgets import QApplication

                # Only show dialog if we're in a GUI application
                if QApplication.instance():
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
                        raise RuntimeError(
                            f"CLIP model '{hf_model}' not found offline.\n\n"
                            f"To use visual embedding features, you need to download a model.\n"
                            f"Please try again and select a model to download."
                        )
                else:
                    # No GUI - can't show dialog
                    logger.error("[SemanticEmbeddingService] No GUI available to show model selection dialog")
                    raise RuntimeError(
                        f"CLIP model '{hf_model}' not found offline.\n\n"
                        f"For offline use:\n"
                        f"1. Download the model to: ./Model/{hf_model.replace('/', '--')}/\n"
                        f"2. Or run the application in GUI mode to download via the model dialog"
                    )

            except ImportError as e:
                logger.error(f"[SemanticEmbeddingService] Could not import model dialog: {e}")
                raise RuntimeError(
                    f"CLIP model '{hf_model}' not found offline.\n\n"
                    f"For offline use:\n"
                    f"1. Download the model to: ./Model/{hf_model.replace('/', '--')}/\n"
                    f"2. Or set custom path in Preferences → Visual Embeddings → Model Path"
                )

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
            raise RuntimeError(
                f"Failed to load CLIP model from:\n{local_model_path}\n\n"
                f"The model files may be corrupted or incomplete.\n"
                f"Please delete the folder and download again.\n\n"
                f"Error: {str(e)}"
            )

        self._model.to(self._device)
        self._model.eval()

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
    Get singleton semantic embedding service.

    Args:
        model_name: CLIP/SigLIP model variant

    Returns:
        SemanticEmbeddingService instance
    """
    global _semantic_embedding_service
    if _semantic_embedding_service is None:
        _semantic_embedding_service = SemanticEmbeddingService(model_name=model_name)
    return _semantic_embedding_service
