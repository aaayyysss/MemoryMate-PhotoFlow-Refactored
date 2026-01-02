"""
EmbeddingService - Visual Semantic Embedding Extraction

Version: 1.0.0
Date: 2026-01-01

This service provides visual embedding extraction using CLIP/SigLIP models
for semantic search and image understanding.

Supported Models:
- CLIP (OpenAI): ViT-B/32, ViT-B/16, ViT-L/14
- SigLIP (Google): Base, Large

Features:
- Image → embedding (512-D or 768-D vectors)
- Text → embedding (for semantic search)
- Model caching (lazy loading)
- CPU/GPU support
- Batch processing

Usage:
    from services.embedding_service import get_embedding_service

    service = get_embedding_service()

    # Extract from image
    embedding = service.extract_image_embedding('/path/to/photo.jpg')

    # Extract from text
    query_embedding = service.extract_text_embedding('sunset beach')

    # Search similar images
    results = service.search_similar(query_embedding, top_k=10)
"""

import os
import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any, Union
from dataclasses import dataclass
from PIL import Image
import logging

from repository.base_repository import DatabaseConnection
from logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class EmbeddingModel:
    """Metadata for an embedding model."""
    model_id: int
    name: str
    variant: str
    version: str
    dimension: int
    runtime: str  # 'cpu', 'gpu_local', 'gpu_remote'


class EmbeddingService:
    """
    Service for extracting visual semantic embeddings.

    Architecture:
    - Lazy model loading (only load when first used)
    - Model caching (singleton pattern per model type)
    - Graceful fallback to CPU if GPU unavailable
    - Integration with ml_model registry

    Thread Safety:
    - Model loading is NOT thread-safe (use from main thread)
    - Inference is thread-safe once model loaded
    """

    def __init__(self,
                 db_connection: Optional[DatabaseConnection] = None,
                 device: str = 'auto'):
        """
        Initialize embedding service.

        Args:
            db_connection: Optional database connection
            device: Compute device ('auto', 'cpu', 'cuda', 'mps')
                   'auto' tries GPU first, falls back to CPU
        """
        self.db = db_connection or DatabaseConnection()
        self._device = None
        self._requested_device = device

        # Model cache
        self._clip_model = None
        self._clip_processor = None
        self._clip_model_id = None

        # Try to import dependencies
        self._torch_available = False
        self._transformers_available = False

        try:
            import torch
            self._torch = torch
            self._torch_available = True
            logger.info("[EmbeddingService] PyTorch available")
        except ImportError:
            logger.warning("[EmbeddingService] PyTorch not available - embeddings disabled")

        try:
            from transformers import CLIPProcessor, CLIPModel
            self._CLIPProcessor = CLIPProcessor
            self._CLIPModel = CLIPModel
            self._transformers_available = True
            logger.info("[EmbeddingService] Transformers available")
        except ImportError:
            logger.warning("[EmbeddingService] Transformers not available - embeddings disabled")

    @property
    def available(self) -> bool:
        """Check if embedding extraction is available."""
        return self._torch_available and self._transformers_available

    @property
    def device(self) -> str:
        """Get actual device being used."""
        if self._device is None:
            self._device = self._detect_device()
        return self._device

    def _detect_device(self) -> str:
        """Detect best available compute device."""
        if not self._torch_available:
            return 'cpu'

        if self._requested_device == 'cpu':
            return 'cpu'

        if self._requested_device == 'cuda' or self._requested_device == 'auto':
            if self._torch.cuda.is_available():
                logger.info("[EmbeddingService] Using CUDA GPU")
                return 'cuda'

        if self._requested_device == 'mps' or self._requested_device == 'auto':
            if hasattr(self._torch.backends, 'mps') and self._torch.backends.mps.is_available():
                logger.info("[EmbeddingService] Using Apple Metal GPU")
                return 'mps'

        logger.info("[EmbeddingService] Using CPU")
        return 'cpu'

    def load_clip_model(self, variant: str = 'openai/clip-vit-base-patch32') -> int:
        """
        Load CLIP model from local cache.

        Args:
            variant: Model variant (default: 'openai/clip-vit-base-patch32')
                    Options:
                    - 'openai/clip-vit-base-patch32' (512-D, fast)
                    - 'openai/clip-vit-base-patch16' (512-D, better quality)
                    - 'openai/clip-vit-large-patch14' (768-D, best quality)

        Returns:
            int: Model ID from ml_model table

        Raises:
            RuntimeError: If dependencies not available or model files not found
        """
        if not self.available:
            raise RuntimeError(
                "Embedding extraction not available. "
                "Install: pip install torch transformers pillow"
            )

        # Check if already loaded
        if self._clip_model is not None:
            logger.info(f"[EmbeddingService] CLIP model already loaded (ID: {self._clip_model_id})")
            return self._clip_model_id

        # Check if model files exist locally and get the actual path
        from utils.clip_check import check_clip_availability, get_clip_download_status
        available, message = check_clip_availability()

        if not available:
            logger.error(f"[EmbeddingService] CLIP model not available: {message}")
            raise RuntimeError(
                "CLIP model files not found.\n\n"
                "Please run: python download_clip_model_offline.py\n\n"
                "This will download the model files (~600MB) to ./models/clip-vit-base-patch32/"
            )

        # Get the actual model directory path
        status = get_clip_download_status()
        model_path = status.get('model_path')

        if not model_path:
            raise RuntimeError("CLIP model path not found")

        logger.info(f"[EmbeddingService] Loading CLIP model from local path: {model_path}")
        logger.info(message)

        try:
            # Set transformers to use local files only
            os.environ['TRANSFORMERS_OFFLINE'] = '1'

            # Load model and processor directly from the snapshot directory
            self._clip_processor = self._CLIPProcessor.from_pretrained(
                model_path,
                local_files_only=True
            )
            self._clip_model = self._CLIPModel.from_pretrained(
                model_path,
                local_files_only=True
            )
            self._clip_model.to(self.device)
            self._clip_model.eval()  # Set to evaluation mode

            # Get model dimension
            dimension = self._clip_model.config.projection_dim

            logger.info(
                f"[EmbeddingService] ✓ CLIP loaded from local cache: {variant} "
                f"({dimension}-D, device={self.device})"
            )

            # Register in ml_model table
            self._clip_model_id = self._register_model(
                name='clip',
                variant=variant,
                version='1.0',
                task='visual_embedding',
                runtime=self.device,
                dimension=dimension
            )

            return self._clip_model_id

        except Exception as e:
            logger.error(f"[EmbeddingService] Failed to load CLIP: {e}")
            raise

    def _register_model(self,
                       name: str,
                       variant: str,
                       version: str,
                       task: str,
                       runtime: str,
                       dimension: int) -> int:
        """
        Register model in ml_model table.

        Returns:
            int: Model ID
        """
        with self.db.get_connection() as conn:
            # Check if model already registered
            cursor = conn.execute("""
                SELECT model_id FROM ml_model
                WHERE name = ? AND variant = ? AND version = ?
            """, (name, variant, version))

            row = cursor.fetchone()
            if row:
                return row[0]

            # Register new model
            cursor = conn.execute("""
                INSERT INTO ml_model (
                    name, variant, version, task, runtime,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (
                name, variant, version, task, runtime
            ))

            model_id = cursor.lastrowid
            conn.commit()

            logger.info(f"[EmbeddingService] Registered model {model_id}: {name}/{variant}")
            return model_id

    def extract_image_embedding(self,
                               image_path: Union[str, Path],
                               model_id: Optional[int] = None) -> np.ndarray:
        """
        Extract embedding from image.

        Args:
            image_path: Path to image file
            model_id: Optional model ID (auto-loads CLIP if None)

        Returns:
            np.ndarray: Embedding vector (normalized, shape: [dimension])

        Raises:
            FileNotFoundError: If image doesn't exist
            RuntimeError: If extraction fails
        """
        # Ensure model loaded
        if self._clip_model is None:
            self.load_clip_model()

        # Load image
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        try:
            image = Image.open(image_path).convert('RGB')

            # Process image
            inputs = self._clip_processor(
                images=image,
                return_tensors="pt",
                padding=True
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Extract embedding
            with self._torch.no_grad():
                image_features = self._clip_model.get_image_features(**inputs)

                # Normalize to unit length for cosine similarity
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            # Convert to numpy
            embedding = image_features.cpu().numpy()[0]

            logger.debug(f"[EmbeddingService] Extracted embedding: {image_path.name} ({embedding.shape})")
            return embedding

        except Exception as e:
            logger.error(f"[EmbeddingService] Failed to extract from {image_path}: {e}")
            raise RuntimeError(f"Embedding extraction failed: {e}")

    def extract_text_embedding(self,
                              text: str,
                              model_id: Optional[int] = None) -> np.ndarray:
        """
        Extract embedding from text query.

        Args:
            text: Search query text
            model_id: Optional model ID (auto-loads CLIP if None)

        Returns:
            np.ndarray: Embedding vector (normalized, shape: [dimension])
        """
        # Ensure model loaded
        if self._clip_model is None:
            self.load_clip_model()

        try:
            # Process text
            inputs = self._clip_processor(
                text=[text],
                return_tensors="pt",
                padding=True
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Extract embedding
            with self._torch.no_grad():
                text_features = self._clip_model.get_text_features(**inputs)

                # Normalize to unit length
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

            # Convert to numpy
            embedding = text_features.cpu().numpy()[0]

            logger.debug(f"[EmbeddingService] Extracted text embedding: '{text}' ({embedding.shape})")
            return embedding

        except Exception as e:
            logger.error(f"[EmbeddingService] Failed to extract from text '{text}': {e}")
            raise RuntimeError(f"Text embedding extraction failed: {e}")

    def store_embedding(self,
                       photo_id: int,
                       embedding: np.ndarray,
                       model_id: Optional[int] = None) -> None:
        """
        Store embedding in photo_embedding table.

        Args:
            photo_id: Photo ID from photo_metadata table
            embedding: Embedding vector
            model_id: Model ID (uses current CLIP model if None)
        """
        if model_id is None:
            model_id = self._clip_model_id
            if model_id is None:
                raise ValueError("No model loaded - call load_clip_model() first")

        # Convert to blob
        embedding_blob = embedding.astype(np.float32).tobytes()

        with self.db.get_connection() as conn:
            # Get photo hash for freshness tracking
            cursor = conn.execute(
                "SELECT path FROM photo_metadata WHERE id = ?",
                (photo_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Photo {photo_id} not found")

            # TODO: Compute actual file hash (for now use path as placeholder)
            photo_path = row['path'] if isinstance(row, dict) else row[0]
            source_photo_hash = str(hash(photo_path))

            # Upsert embedding
            conn.execute("""
                INSERT OR REPLACE INTO photo_embedding (
                    photo_id, model_id, embedding_type, dim,
                    embedding, source_photo_hash, artifact_version,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                photo_id,
                model_id,
                'visual_semantic',
                len(embedding),  # dimension
                embedding_blob,
                source_photo_hash,
                '1.0'
            ))

            conn.commit()

            logger.debug(f"[EmbeddingService] Stored embedding for photo {photo_id}")

    def search_similar(self,
                      query_embedding: np.ndarray,
                      top_k: int = 10,
                      model_id: Optional[int] = None,
                      photo_ids: Optional[List[int]] = None) -> List[Tuple[int, float]]:
        """
        Search for similar images using cosine similarity.

        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            model_id: Model ID to filter by (uses current model if None)
            photo_ids: Optional list of photo IDs to search within

        Returns:
            List of (photo_id, similarity_score) tuples, sorted by score descending
        """
        if model_id is None:
            model_id = self._clip_model_id
            if model_id is None:
                raise ValueError("No model loaded")

        with self.db.get_connection() as conn:
            # Fetch all embeddings for this model
            query = """
                SELECT photo_id, embedding
                FROM photo_embedding
                WHERE model_id = ? AND embedding_type = 'visual_semantic'
            """
            params = [model_id]

            if photo_ids:
                placeholders = ','.join('?' * len(photo_ids))
                query += f" AND photo_id IN ({placeholders})"
                params.extend(photo_ids)

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            if not rows:
                logger.warning("[EmbeddingService] No embeddings found for search")
                return []

            # Debug: Check first row to diagnose data issue
            if rows:
                first_row = rows[0]
                logger.debug(
                    f"[EmbeddingService] First row debug - "
                    f"type: {type(first_row)}, "
                    f"length: {len(first_row) if hasattr(first_row, '__len__') else 'N/A'}, "
                    f"values: {first_row if len(str(first_row)) < 200 else str(first_row)[:200]+'...'}"
                )
                if hasattr(first_row, 'keys'):
                    logger.debug(f"[EmbeddingService] Row keys: {list(first_row.keys())}")

            # Compute cosine similarities
            results = []
            query_norm = query_embedding / np.linalg.norm(query_embedding)

            for photo_id, embedding_blob in rows:
                try:
                    # Deserialize embedding - handle both bytes and string formats
                    if isinstance(embedding_blob, str):
                        # SQLite returned as string - try multiple conversion methods
                        # Method 1: Try hex decoding
                        try:
                            embedding_blob = bytes.fromhex(embedding_blob)
                        except (ValueError, TypeError):
                            # Method 2: Raw binary string - encode to bytes
                            # Use latin1 which preserves byte values 0-255
                            embedding_blob = embedding_blob.encode('latin1')

                    # Validate buffer size
                    expected_size = 512 * 4  # 512 dimensions * 4 bytes per float32
                    if len(embedding_blob) != expected_size:
                        logger.warning(
                            f"[EmbeddingService] Photo {photo_id}: Invalid embedding size "
                            f"{len(embedding_blob)} bytes, expected {expected_size} bytes. Skipping."
                        )
                        continue

                    embedding = np.frombuffer(embedding_blob, dtype=np.float32)
                    embedding_norm = embedding / np.linalg.norm(embedding)

                    # Cosine similarity
                    similarity = float(np.dot(query_norm, embedding_norm))
                    results.append((photo_id, similarity))

                except Exception as e:
                    logger.warning(
                        f"[EmbeddingService] Failed to deserialize embedding for photo {photo_id}: {e}. "
                        f"Blob type: {type(embedding_blob)}, size: {len(embedding_blob) if hasattr(embedding_blob, '__len__') else 'N/A'}"
                    )
                    continue

            # Sort by similarity descending
            results.sort(key=lambda x: x[1], reverse=True)

            # Return top K
            top_results = results[:top_k]

            if top_results:
                logger.info(
                    f"[EmbeddingService] Search complete: "
                    f"{len(rows)} candidates, {len(top_results)} valid results, "
                    f"top score={top_results[0][1]:.3f}"
                )
            else:
                logger.warning(
                    f"[EmbeddingService] Search complete but NO valid embeddings found! "
                    f"Retrieved {len(rows)} rows from database, but all were invalid/corrupted. "
                    f"This suggests embeddings were stored incorrectly."
                )

            return top_results

    def get_embedding_count(self, model_id: Optional[int] = None) -> int:
        """Get count of stored embeddings."""
        with self.db.get_connection() as conn:
            if model_id:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM photo_embedding WHERE model_id = ?",
                    (model_id,)
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM photo_embedding")

            return cursor.fetchone()[0]

    def clear_embeddings(self, model_id: Optional[int] = None) -> int:
        """
        Clear embeddings (useful for model upgrades).

        Args:
            model_id: Optional model ID to filter by (clears all if None)

        Returns:
            int: Number of embeddings deleted
        """
        with self.db.get_connection() as conn:
            if model_id:
                cursor = conn.execute(
                    "DELETE FROM photo_embedding WHERE model_id = ?",
                    (model_id,)
                )
            else:
                cursor = conn.execute("DELETE FROM photo_embedding")

            deleted = cursor.rowcount
            conn.commit()

            logger.info(f"[EmbeddingService] Cleared {deleted} embeddings")
            return deleted


# Singleton instance
_embedding_service = None


def get_embedding_service(device: str = 'auto') -> EmbeddingService:
    """
    Get singleton embedding service instance.

    Args:
        device: Compute device ('auto', 'cpu', 'cuda', 'mps')

    Returns:
        EmbeddingService instance
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(device=device)
    return _embedding_service
