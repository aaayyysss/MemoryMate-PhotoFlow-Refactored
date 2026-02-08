"""
SemanticSearchWorker - Async Semantic Search

Version: 1.0.0
Date: 2026-02-08

Qt QThread worker that performs semantic search in the background,
following Google Photos / iOS Photos patterns for responsive search UX.

Architecture:
    - Called from SemanticSearchWidget when user types a query
    - Debounced at the widget level (250-350ms)
    - Cancellable if user types new query
    - Reports progress for model warmup and search stages
    - Integrates with JobManager for visibility

Usage:
    from workers.semantic_search_worker import SemanticSearchWorker

    worker = SemanticSearchWorker(
        project_id=1,
        query="sunset beach",
        limit=100,
        threshold=0.25
    )
    worker.signals.results_ready.connect(on_results)
    worker.signals.status.connect(on_status)
    worker.start()
"""

import time
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict, Any

import numpy as np
from PySide6.QtCore import QThread, Signal, QObject

from logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """Individual search result with metadata."""
    photo_id: int
    file_path: str
    score: float
    thumbnail_path: Optional[str] = None
    kind: str = "photo"  # "photo" or "video"


@dataclass
class SearchResponse:
    """Complete search response with results and diagnostics."""
    results: List[SearchResult] = field(default_factory=list)
    query: str = ""
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.results)

    @property
    def is_empty(self) -> bool:
        return len(self.results) == 0


class SemanticSearchWorkerSignals(QObject):
    """
    Signals for SemanticSearchWorker.

    Qt signals must be defined in a QObject, not QThread directly.
    """
    # Status updates during search
    status = Signal(str)

    # Search complete with results
    results_ready = Signal(object)  # SearchResponse

    # Error occurred
    error = Signal(str)

    # Worker finished (success or error)
    finished = Signal()

    # Progress for long operations (0-100)
    progress = Signal(int, str)


class SemanticSearchWorker(QThread):
    """
    QThread worker for background semantic search.

    Follows Google Photos patterns:
    - Fast cancellation on new query
    - Progress feedback for model warmup
    - Structured response with diagnostics
    - No UI thread blocking

    Thread Safety:
    - Uses threading.Event for cancellation
    - All UI updates via signals
    - Service handles its own thread safety
    """

    def __init__(self,
                 project_id: int,
                 query: str,
                 limit: int = 100,
                 threshold: float = 0.25,
                 model_name: Optional[str] = None,
                 parent=None):
        """
        Initialize semantic search worker.

        Args:
            project_id: Project to search within
            query: Search query text
            limit: Maximum results to return
            threshold: Minimum similarity score (0-1)
            model_name: Optional model override (uses project canonical if None)
            parent: Optional parent QObject
        """
        super().__init__(parent)

        self.project_id = project_id
        self.query = query.strip()
        self.limit = limit
        self.threshold = threshold
        self.model_name = model_name

        self.signals = SemanticSearchWorkerSignals()
        self._cancelled = threading.Event()
        self._start_time = None

    def cancel(self):
        """Cancel the search operation."""
        logger.info(f"[SemanticSearchWorker] Cancel requested for query: {self.query[:30]}...")
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancelled.is_set()

    def run(self):
        """
        Execute semantic search in background thread.

        Called automatically when thread starts.
        """
        self._start_time = time.time()
        response = SearchResponse(query=self.query)

        try:
            # Validate query
            if len(self.query) < 2:
                logger.debug(f"[SemanticSearchWorker] Query too short: {self.query}")
                self.signals.results_ready.emit(response)
                self.signals.finished.emit()
                return

            logger.info(f"[SemanticSearchWorker] Starting search: '{self.query}' (project={self.project_id})")
            self.signals.status.emit("Preparing search...")

            if self.is_cancelled():
                logger.info("[SemanticSearchWorker] Cancelled before service init")
                self.signals.finished.emit()
                return

            # Step 1: Get embedding service and check readiness
            self.signals.progress.emit(10, "Loading search service...")

            from services.semantic_embedding_service import get_semantic_embedding_service
            from repository.project_repository import ProjectRepository

            # Get canonical model for project
            if self.model_name is None:
                proj_repo = ProjectRepository()
                self.model_name = proj_repo.get_semantic_model(self.project_id)
                if not self.model_name:
                    self.model_name = "openai/clip-vit-base-patch32"

            service = get_semantic_embedding_service(model_name=self.model_name)

            if self.is_cancelled():
                logger.info("[SemanticSearchWorker] Cancelled after service init")
                self.signals.finished.emit()
                return

            # Step 2: Check if model needs loading (first-run scenario)
            if not service._available:
                self.signals.error.emit("Semantic search not available (missing dependencies)")
                self.signals.finished.emit()
                return

            # Check embedding coverage
            self.signals.progress.emit(20, "Checking embeddings...")
            index_state = self._get_index_state(service)

            if index_state['embeddings_count'] == 0:
                logger.warning(f"[SemanticSearchWorker] No embeddings for project {self.project_id}")
                response.stats = {
                    'no_embeddings': True,
                    'total_photos': index_state['total_photos'],
                    'message': "No embeddings found. Use Tools → Extract Embeddings first."
                }
                self.signals.results_ready.emit(response)
                self.signals.finished.emit()
                return

            if self.is_cancelled():
                logger.info("[SemanticSearchWorker] Cancelled after index check")
                self.signals.finished.emit()
                return

            # Step 3: Warm up model if needed
            model_load_start = time.time()
            if service._model is None:
                self.signals.status.emit("Loading AI model (first search)...")
                self.signals.progress.emit(30, "Loading CLIP model...")
                logger.info("[SemanticSearchWorker] Model not loaded, triggering load...")

            # Step 4: Encode query text
            self.signals.progress.emit(50, "Encoding query...")
            encode_start = time.time()

            try:
                query_embedding = service.encode_text(self.query)
            except Exception as e:
                logger.error(f"[SemanticSearchWorker] Failed to encode query: {e}")
                self.signals.error.emit(f"Failed to encode query: {e}")
                self.signals.finished.emit()
                return

            encode_time = time.time() - encode_start
            model_load_time = time.time() - model_load_start

            if self.is_cancelled():
                logger.info("[SemanticSearchWorker] Cancelled after query encoding")
                self.signals.finished.emit()
                return

            # Step 5: Search embeddings in database
            self.signals.status.emit("Searching...")
            self.signals.progress.emit(70, "Comparing embeddings...")

            db_start = time.time()
            results = self._search_embeddings(
                service,
                query_embedding,
                cancelled_check=self.is_cancelled
            )
            db_time = time.time() - db_start

            if self.is_cancelled():
                logger.info("[SemanticSearchWorker] Cancelled during search")
                self.signals.finished.emit()
                return

            # Step 6: Build response
            self.signals.progress.emit(90, "Preparing results...")

            total_time = time.time() - self._start_time

            response.results = results
            response.stats = {
                'query_time_ms': int(total_time * 1000),
                'encode_time_ms': int(encode_time * 1000),
                'db_time_ms': int(db_time * 1000),
                'model_load_time_ms': int(model_load_time * 1000),
                'results_count': len(results),
                'threshold': self.threshold,
                'model': self.model_name,
                'embeddings_searched': index_state['embeddings_count'],
                'coverage_percent': index_state.get('coverage_percent', 0)
            }

            logger.info(
                f"[SemanticSearchWorker] Search complete: '{self.query}' → "
                f"{len(results)} results in {total_time:.2f}s "
                f"(encode={encode_time:.2f}s, db={db_time:.2f}s)"
            )

            self.signals.progress.emit(100, "Done")
            self.signals.results_ready.emit(response)

        except Exception as e:
            logger.error(f"[SemanticSearchWorker] Search failed: {e}", exc_info=True)
            self.signals.error.emit(str(e))

        finally:
            self.signals.finished.emit()

    def _get_index_state(self, service) -> dict:
        """
        Get embedding index state for the project.

        Returns:
            Dict with total_photos, embeddings_count, coverage_percent, ready_for_search
        """
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            with db.get_connection() as conn:
                # Total photos
                cursor = conn.execute(
                    "SELECT COUNT(*) as count FROM photo_metadata WHERE project_id = ?",
                    (self.project_id,)
                )
                total_photos = cursor.fetchone()['count']

                # Photos with embeddings
                cursor = conn.execute("""
                    SELECT COUNT(DISTINCT pm.id) as count
                    FROM photo_metadata pm
                    JOIN semantic_embeddings se ON pm.id = se.photo_id
                    WHERE pm.project_id = ?
                """, (self.project_id,))
                embeddings_count = cursor.fetchone()['count']

            coverage = (embeddings_count / total_photos * 100) if total_photos > 0 else 0

            return {
                'total_photos': total_photos,
                'embeddings_count': embeddings_count,
                'coverage_percent': coverage,
                'ready_for_search': embeddings_count > 0
            }

        except Exception as e:
            logger.warning(f"[SemanticSearchWorker] Failed to get index state: {e}")
            return {
                'total_photos': 0,
                'embeddings_count': 0,
                'coverage_percent': 0,
                'ready_for_search': False
            }

    def _search_embeddings(self,
                           service,
                           query_embedding: np.ndarray,
                           cancelled_check: Callable[[], bool] = None) -> List[SearchResult]:
        """
        Search embeddings in database using cosine similarity.

        Args:
            service: SemanticEmbeddingService instance
            query_embedding: Query embedding vector (normalized)
            cancelled_check: Optional callable to check for cancellation

        Returns:
            List of SearchResult sorted by score descending
        """
        results = []

        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            with db.get_connection() as conn:
                # Get all embeddings for project
                cursor = conn.execute("""
                    SELECT se.photo_id, se.embedding, pm.file_path, pm.thumbnail_path
                    FROM semantic_embeddings se
                    JOIN photo_metadata pm ON se.photo_id = pm.id
                    WHERE pm.project_id = ?
                """, (self.project_id,))

                rows = cursor.fetchall()

                if not rows:
                    return results

                # Batch process for efficiency
                photo_ids = []
                embeddings = []
                paths = []
                thumb_paths = []

                for row in rows:
                    if cancelled_check and cancelled_check():
                        return results

                    try:
                        emb = np.frombuffer(row['embedding'], dtype=np.float32)
                        # Handle float16 storage
                        if len(emb) == 0:
                            emb = np.frombuffer(row['embedding'], dtype=np.float16).astype(np.float32)

                        if len(emb) > 0:
                            photo_ids.append(row['photo_id'])
                            embeddings.append(emb)
                            paths.append(row['file_path'])
                            thumb_paths.append(row['thumbnail_path'])
                    except Exception as e:
                        logger.debug(f"[SemanticSearchWorker] Skip embedding {row['photo_id']}: {e}")
                        continue

                if not embeddings:
                    return results

                # Vectorized similarity computation
                embeddings_matrix = np.vstack(embeddings)

                # Normalize embeddings if needed
                norms = np.linalg.norm(embeddings_matrix, axis=1, keepdims=True)
                norms = np.where(norms > 0, norms, 1)  # Avoid division by zero
                embeddings_matrix = embeddings_matrix / norms

                # Normalize query
                query_norm = np.linalg.norm(query_embedding)
                if query_norm > 0:
                    query_embedding = query_embedding / query_norm

                # Cosine similarity (dot product of normalized vectors)
                similarities = embeddings_matrix @ query_embedding

                # Filter and sort
                for i, score in enumerate(similarities):
                    if cancelled_check and cancelled_check():
                        break

                    if score >= self.threshold:
                        results.append(SearchResult(
                            photo_id=photo_ids[i],
                            file_path=paths[i],
                            score=float(score),
                            thumbnail_path=thumb_paths[i],
                            kind="photo"
                        ))

                # Sort by score descending and limit
                results.sort(key=lambda x: x.score, reverse=True)
                results = results[:self.limit]

        except Exception as e:
            logger.error(f"[SemanticSearchWorker] Embedding search failed: {e}", exc_info=True)

        return results


def create_semantic_search_worker(
    project_id: int,
    query: str,
    limit: int = 100,
    threshold: float = 0.25,
    model_name: Optional[str] = None
) -> SemanticSearchWorker:
    """
    Factory function to create SemanticSearchWorker.

    Args:
        project_id: Project to search
        query: Search query
        limit: Max results
        threshold: Min similarity
        model_name: Optional model override

    Returns:
        SemanticSearchWorker instance (not started)
    """
    return SemanticSearchWorker(
        project_id=project_id,
        query=query,
        limit=limit,
        threshold=threshold,
        model_name=model_name
    )
