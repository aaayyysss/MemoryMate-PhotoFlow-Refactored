"""
SemanticSearchService - Text → Image Search

Version: 1.0.0
Date: 2026-01-05

Search photos using natural language queries.

Core Principle (non-negotiable):
Text query → embedding → cosine similarity → matching photos

Architecture:
- Uses semantic_embeddings table (NOT face_crops)
- CLIP text encoder for query understanding
- Cosine similarity on normalized vectors
- Threshold filtering for quality control

Usage:
    from services.semantic_search_service import get_semantic_search_service

    service = get_semantic_search_service()

    # Search by text
    results = service.search("sunset over ocean", top_k=20, threshold=0.25)
    # Returns: [SearchResult(photo_id, score, ...), ...]
"""

import numpy as np
from typing import List, Optional
from dataclasses import dataclass

from services.semantic_embedding_service import get_semantic_embedding_service
from repository.base_repository import DatabaseConnection
from logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """Semantic search result."""
    photo_id: int
    relevance_score: float
    file_path: Optional[str] = None
    thumbnail_path: Optional[str] = None


class SemanticSearchService:
    """
    Service for text-to-image semantic search.

    Enables natural language photo search:
    - "sunset over ocean"
    - "dog playing in park"
    - "mountain landscape with snow"

    IMPORTANT: Always use for_project() factory method to ensure
    the correct canonical model is used for the project.
    """

    def __init__(self,
                 model_name: str = "clip-vit-b32",
                 db_connection: Optional[DatabaseConnection] = None,
                 project_id: Optional[int] = None):
        """
        Initialize semantic search service.

        NOTE: Prefer using SemanticSearchService.for_project() factory method
        to automatically use the project's canonical model.

        Args:
            model_name: CLIP/SigLIP model variant (must match embeddings)
            db_connection: Optional database connection
            project_id: Optional project ID (used for filtering and model validation)
        """
        self.model_name = model_name
        self.project_id = project_id
        self.db = db_connection or DatabaseConnection()
        self.embedder = get_semantic_embedding_service(model_name=model_name)

        logger.info(f"[SemanticSearchService] Initialized with model={model_name}")

    @classmethod
    def for_project(cls, project_id: int, db_connection: Optional[DatabaseConnection] = None) -> 'SemanticSearchService':
        """
        Factory method to create a SemanticSearchService using the project's canonical model.

        This is the RECOMMENDED way to create a SemanticSearchService.
        It ensures that search uses the same model that was used
        to generate the embeddings for this project.

        Args:
            project_id: Project ID
            db_connection: Optional database connection

        Returns:
            SemanticSearchService configured with the project's canonical model
        """
        from repository.project_repository import ProjectRepository
        project_repo = ProjectRepository()
        canonical_model = project_repo.get_semantic_model(project_id)

        logger.info(
            f"[SemanticSearchService] Creating service for project {project_id} "
            f"with canonical model: {canonical_model}"
        )

        return cls(
            model_name=canonical_model,
            db_connection=db_connection,
            project_id=project_id
        )

    @property
    def available(self) -> bool:
        """Check if service is available."""
        return self.embedder.available

    def search(self,
              query: str,
              top_k: int = 20,
              threshold: float = 0.25,
              include_metadata: bool = False) -> List[SearchResult]:
        """
        Search photos using natural language query.

        Args:
            query: Natural language search query (e.g., "sunset beach")
            top_k: Number of results to return
            threshold: Minimum relevance score (0.0 to 1.0)
                      Note: Text-image similarity typically lower than image-image
            include_metadata: If True, fetch file paths for results

        Returns:
            List of SearchResult objects, sorted by relevance descending

        Algorithm:
            1. Encode query text to embedding
            2. Get all photo embeddings from database
            3. Compute cosine similarity (dot product of normalized vectors)
            4. Filter by threshold
            5. Return top_k results

        Note:
            Text-image similarity scores are typically lower than image-image.
            A threshold of 0.2-0.3 is reasonable for text queries.
        """
        if not query or not query.strip():
            logger.warning("[SemanticSearchService] Empty query")
            return []

        if not self.available:
            logger.error("[SemanticSearchService] Service not available (PyTorch/Transformers missing)")
            return []

        # Encode query
        try:
            query_embedding = self.embedder.encode_text(query.strip())
        except Exception as e:
            logger.error(f"[SemanticSearchService] Failed to encode query '{query}': {e}")
            return []

        # Get all photo embeddings
        photo_embeddings = self._get_all_embeddings()
        if not photo_embeddings:
            logger.warning("[SemanticSearchService] No photo embeddings found")
            return []

        # Compute similarities
        matches = []
        for photo_id, photo_embedding in photo_embeddings:
            # Cosine similarity = dot product (vectors are normalized)
            score = float(np.dot(query_embedding, photo_embedding))

            # Filter by threshold
            if score >= threshold:
                matches.append((photo_id, score))

        # Sort by score descending and take top_k
        matches.sort(key=lambda x: x[1], reverse=True)
        matches = matches[:top_k]

        logger.info(
            f"[SemanticSearchService] Query '{query}': {len(matches)} matches "
            f"(threshold={threshold:.2f}, top_k={top_k})"
        )

        # Convert to SearchResult objects
        results = []
        for photo_id, score in matches:
            result = SearchResult(
                photo_id=photo_id,
                relevance_score=score
            )
            results.append(result)

        # Fetch metadata if requested
        if include_metadata:
            self._add_metadata(results)

        return results

    def _get_all_embeddings(self) -> List[tuple]:
        """
        Get all photo embeddings for the current project (if set).

        Returns:
            List of (photo_id, embedding) tuples
        """
        with self.db.get_connection() as conn:
            # CRITICAL FIX: Filter by project_id when set
            # Without this, search returns photos from ALL projects!
            if self.project_id is not None:
                cursor = conn.execute("""
                    SELECT se.photo_id, se.embedding, se.dim
                    FROM semantic_embeddings se
                    JOIN photo_metadata pm ON se.photo_id = pm.id
                    WHERE se.model = ?
                      AND pm.project_id = ?
                """, (self.model_name, self.project_id))
            else:
                # Legacy behavior for non-project-aware callers
                cursor = conn.execute("""
                    SELECT photo_id, embedding, dim
                    FROM semantic_embeddings
                    WHERE model = ?
                """, (self.model_name,))

            results = []
            for row in cursor.fetchall():
                photo_id = row['photo_id']
                embedding_blob = row['embedding']
                dim = row['dim']

                # Deserialize
                if isinstance(embedding_blob, str):
                    embedding_blob = embedding_blob.encode('latin1')

                # CRITICAL FIX: Handle float16 vs float32 storage format
                # Negative dim indicates float16 format (new, 50% smaller)
                # Positive dim indicates float32 format (legacy)
                if dim < 0:
                    actual_dim = abs(dim)
                    embedding = np.frombuffer(embedding_blob, dtype='float16').astype('float32')
                else:
                    actual_dim = dim
                    embedding = np.frombuffer(embedding_blob, dtype='float32')

                if len(embedding) != actual_dim:
                    logger.warning(
                        f"[SemanticSearchService] Dimension mismatch for photo {photo_id}: "
                        f"expected {actual_dim}, got {len(embedding)}"
                    )
                    continue

                results.append((photo_id, embedding))

            return results

    def _add_metadata(self, results: List[SearchResult]):
        """
        Add file paths and thumbnail paths to results.

        Args:
            results: List of SearchResult objects (modified in-place)
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

    def get_search_statistics(self) -> dict:
        """
        Get search readiness statistics for the current project (if set).

        Returns:
            Dict with total_photos, embedded_photos, coverage_percent, model, project_id
        """
        with self.db.get_connection() as conn:
            # CRITICAL FIX: Filter by project_id when set
            if self.project_id is not None:
                # Total photos in project
                cursor = conn.execute(
                    "SELECT COUNT(*) as count FROM photo_metadata WHERE project_id = ?",
                    (self.project_id,)
                )
                total_photos = cursor.fetchone()['count']

                # Embedded photos in project
                cursor = conn.execute("""
                    SELECT COUNT(*) as count
                    FROM semantic_embeddings se
                    JOIN photo_metadata pm ON se.photo_id = pm.id
                    WHERE se.model = ?
                      AND pm.project_id = ?
                """, (self.model_name, self.project_id))
                embedded_photos = cursor.fetchone()['count']
            else:
                # Legacy behavior for non-project-aware callers
                cursor = conn.execute("SELECT COUNT(*) as count FROM photo_metadata")
                total_photos = cursor.fetchone()['count']

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
                'model': self.model_name,
                'project_id': self.project_id,
                'search_ready': embedded_photos > 0
            }


# Singleton instance
_semantic_search_service = None


# Per-project service cache
_project_search_services: dict = {}


def get_semantic_search_service(model_name: str = "clip-vit-b32") -> SemanticSearchService:
    """
    Get singleton semantic search service.

    NOTE: Prefer get_semantic_search_service_for_project() for project-aware service.

    Args:
        model_name: CLIP/SigLIP model variant

    Returns:
        SemanticSearchService instance
    """
    global _semantic_search_service
    if _semantic_search_service is None:
        _semantic_search_service = SemanticSearchService(model_name=model_name)
    return _semantic_search_service


def get_semantic_search_service_for_project(project_id: int) -> SemanticSearchService:
    """
    Get semantic search service configured with the project's canonical model.

    This is the RECOMMENDED way to get a SemanticSearchService.
    It ensures search uses the project's canonical embedding model.

    Args:
        project_id: Project ID

    Returns:
        SemanticSearchService configured with the project's canonical model
    """
    global _project_search_services

    if project_id not in _project_search_services:
        _project_search_services[project_id] = SemanticSearchService.for_project(project_id)

    return _project_search_services[project_id]


def invalidate_project_search_service(project_id: int):
    """
    Invalidate the cached search service for a project.

    Call this when the project's semantic_model changes to force
    recreation of the service with the new model.

    Args:
        project_id: Project ID
    """
    global _project_search_services

    if project_id in _project_search_services:
        del _project_search_services[project_id]
        logger.info(
            f"[SemanticSearchService] Invalidated cached service for project {project_id}. "
            f"Next access will recreate with current canonical model."
        )
