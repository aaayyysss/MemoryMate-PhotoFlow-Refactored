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
        """Lazy load CLIP model from local cache."""
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

        # Get local model path from settings if available
        local_model_path = None
        try:
            from settings_manager_qt import SettingsManager
            settings = SettingsManager()
            # Check for custom CLIP model path
            clip_path = settings.get("clip_model_path", "").strip()
            if clip_path:
                from pathlib import Path
                clip_path_obj = Path(clip_path)
                if clip_path_obj.exists() and clip_path_obj.is_dir():
                    local_model_path = str(clip_path_obj)
                    logger.info(f"[SemanticEmbeddingService] Using custom model path: {local_model_path}")

            # Fallback to Model folder in root
            if not local_model_path:
                app_root = Path(__file__).parent.parent.absolute()
                model_folder = app_root / 'Model' / hf_model.replace('/', '--')
                if model_folder.exists():
                    local_model_path = str(model_folder)
                    logger.info(f"[SemanticEmbeddingService] Using Model folder: {local_model_path}")
                else:
                    # Try models folder (lowercase)
                    model_folder = app_root / 'models' / hf_model.replace('/', '--')
                    if model_folder.exists():
                        local_model_path = str(model_folder)
                        logger.info(f"[SemanticEmbeddingService] Using models folder: {local_model_path}")
        except Exception as e:
            logger.warning(f"[SemanticEmbeddingService] Could not check for local models: {e}")

        # Load model and processor with offline support
        try:
            if local_model_path:
                # Load from local path with offline mode
                logger.info(f"[SemanticEmbeddingService] Loading from local path (offline mode): {local_model_path}")
                self._processor = self._CLIPProcessor.from_pretrained(
                    local_model_path,
                    local_files_only=True
                )
                self._model = self._CLIPModel.from_pretrained(
                    local_model_path,
                    local_files_only=True
                )
            else:
                # Fallback to HuggingFace with local cache (will download if needed)
                logger.warning(f"[SemanticEmbeddingService] No local models found, attempting to load from cache: {hf_model}")
                logger.warning(f"[SemanticEmbeddingService] If offline, this will fail. Place models in: ./Model/{hf_model.replace('/', '--')}/")
                self._processor = self._CLIPProcessor.from_pretrained(
                    hf_model,
                    local_files_only=False  # Allow download if not cached
                )
                self._model = self._CLIPModel.from_pretrained(
                    hf_model,
                    local_files_only=False  # Allow download if not cached
                )
        except Exception as e:
            logger.error(f"[SemanticEmbeddingService] Failed to load model: {e}")
            raise RuntimeError(
                f"Failed to load CLIP model '{hf_model}'.\n\n"
                f"For offline use:\n"
                f"1. Download the model to: ./Model/{hf_model.replace('/', '--')}/\n"
                f"2. Or set custom path in Preferences → Visual Embeddings → Model Path\n\n"
                f"Error: {str(e)}"
            )

        self._model.to(self._device)
        self._model.eval()

        logger.info(f"[SemanticEmbeddingService] Model loaded successfully: {hf_model}")

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
