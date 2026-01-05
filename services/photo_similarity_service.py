"""
PhotoSimilarityService - Visual Similarity Search

Version: 1.0.0
Date: 2026-01-05

Find visually similar photos using semantic embeddings.

Core Principle (non-negotiable):
Given photo_id A, show top_k similar photos using cosine similarity.

Architecture:
- Uses semantic_embeddings table (NOT face_crops)
- Cosine similarity on normalized vectors
- Threshold filtering for quality control
- Minimal but correct implementation

Usage:
    from services.photo_similarity_service import get_photo_similarity_service

    service = get_photo_similarity_service()

    # Find similar photos
    similar = service.find_similar(photo_id=123, top_k=20, threshold=0.7)
    # Returns: [(photo_id, similarity_score), ...]
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass

from services.semantic_embedding_service import get_semantic_embedding_service
from repository.base_repository import DatabaseConnection
from logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SimilarPhoto:
    """Similar photo result."""
    photo_id: int
    similarity_score: float
    file_path: Optional[str] = None
    thumbnail_path: Optional[str] = None


class PhotoSimilarityService:
    """
    Service for finding visually similar photos.

    Uses semantic embeddings (CLIP/SigLIP) for similarity computation.
    Does NOT use face embeddings.
    """

    def __init__(self,
                 model_name: str = "clip-vit-b32",
                 db_connection: Optional[DatabaseConnection] = None):
        """
        Initialize photo similarity service.

        Args:
            model_name: CLIP/SigLIP model variant (must match embeddings)
            db_connection: Optional database connection
        """
        self.model_name = model_name
        self.db = db_connection or DatabaseConnection()
        self.embedder = get_semantic_embedding_service(model_name=model_name)

        logger.info(f"[PhotoSimilarityService] Initialized with model={model_name}")

    def find_similar(self,
                    photo_id: int,
                    top_k: int = 20,
                    threshold: float = 0.7,
                    include_metadata: bool = False) -> List[SimilarPhoto]:
        """
        Find visually similar photos.

        Args:
            photo_id: Reference photo ID
            top_k: Number of similar photos to return
            threshold: Minimum similarity score (0.0 to 1.0)
            include_metadata: If True, fetch file paths for results

        Returns:
            List of SimilarPhoto objects, sorted by similarity descending

        Algorithm:
            1. Get reference embedding for photo_id
            2. Get all other embeddings from database
            3. Compute cosine similarity (dot product of normalized vectors)
            4. Filter by threshold
            5. Return top_k results
        """
        # Get reference embedding
        ref_embedding = self.embedder.get_embedding(photo_id)
        if ref_embedding is None:
            logger.warning(f"[PhotoSimilarityService] Photo {photo_id} has no embedding")
            return []

        # Get all other embeddings
        candidates = self._get_all_embeddings(exclude_photo_id=photo_id)
        if not candidates:
            logger.warning("[PhotoSimilarityService] No other embeddings found")
            return []

        # Compute similarities
        similarities = []
        for candidate_id, candidate_embedding in candidates:
            # Cosine similarity = dot product (vectors are normalized)
            score = float(np.dot(ref_embedding, candidate_embedding))

            # Filter by threshold
            if score >= threshold:
                similarities.append((candidate_id, score))

        # Sort by score descending and take top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        similarities = similarities[:top_k]

        logger.info(
            f"[PhotoSimilarityService] Found {len(similarities)} similar photos "
            f"(threshold={threshold:.2f}, top_k={top_k})"
        )

        # Convert to SimilarPhoto objects
        results = []
        for candidate_id, score in similarities:
            photo = SimilarPhoto(
                photo_id=candidate_id,
                similarity_score=score
            )
            results.append(photo)

        # Fetch metadata if requested
        if include_metadata:
            self._add_metadata(results)

        return results

    def _get_all_embeddings(self, exclude_photo_id: int) -> List[Tuple[int, np.ndarray]]:
        """
        Get all embeddings except reference photo.

        Args:
            exclude_photo_id: Photo ID to exclude

        Returns:
            List of (photo_id, embedding) tuples
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT photo_id, embedding, dim
                FROM semantic_embeddings
                WHERE photo_id != ? AND model = ?
            """, (exclude_photo_id, self.model_name))

            results = []
            for row in cursor.fetchall():
                photo_id = row['photo_id']
                embedding_blob = row['embedding']
                dim = row['dim']

                # Deserialize
                if isinstance(embedding_blob, str):
                    embedding_blob = embedding_blob.encode('latin1')

                embedding = np.frombuffer(embedding_blob, dtype='float32')

                if len(embedding) != dim:
                    logger.warning(
                        f"[PhotoSimilarityService] Dimension mismatch for photo {photo_id}: "
                        f"expected {dim}, got {len(embedding)}"
                    )
                    continue

                results.append((photo_id, embedding))

            return results

    def _add_metadata(self, results: List[SimilarPhoto]):
        """
        Add file paths and thumbnail paths to results.

        Args:
            results: List of SimilarPhoto objects (modified in-place)
        """
        if not results:
            return

        photo_ids = [r.photo_id for r in results]
        placeholders = ','.join(['?'] * len(photo_ids))

        with self.db.get_connection() as conn:
            cursor = conn.execute(f"""
                SELECT id, file_path, thumbnail_path
                FROM photo_metadata
                WHERE id IN ({placeholders})
            """, photo_ids)

            metadata = {row['id']: row for row in cursor.fetchall()}

        # Add metadata to results
        for result in results:
            meta = metadata.get(result.photo_id)
            if meta:
                result.file_path = meta.get('file_path')
                result.thumbnail_path = meta.get('thumbnail_path')

    def get_embedding_coverage(self) -> dict:
        """
        Get embedding coverage statistics.

        Returns:
            Dict with total_photos, embedded_photos, coverage_percent
        """
        with self.db.get_connection() as conn:
            # Total photos
            cursor = conn.execute("SELECT COUNT(*) as count FROM photo_metadata")
            total_photos = cursor.fetchone()['count']

            # Embedded photos
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM semantic_embeddings
                WHERE model = ?
            """, (self.model_name,))
            embedded_photos = cursor.fetchone()['count']

            coverage_percent = (embedded_photos / total_photos * 100) if total_photos > 0 else 0.0

            return {
                'total_photos': total_photos,
                'embedded_photos': embedded_photos,
                'coverage_percent': coverage_percent,
                'model': self.model_name
            }


# Singleton instance
_photo_similarity_service = None


def get_photo_similarity_service(model_name: str = "clip-vit-b32") -> PhotoSimilarityService:
    """
    Get singleton photo similarity service.

    Args:
        model_name: CLIP/SigLIP model variant

    Returns:
        PhotoSimilarityService instance
    """
    global _photo_similarity_service
    if _photo_similarity_service is None:
        _photo_similarity_service = PhotoSimilarityService(model_name=model_name)
    return _photo_similarity_service
