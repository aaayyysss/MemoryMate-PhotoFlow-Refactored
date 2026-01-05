# workers/embedding_extraction_worker.py
# Background worker for extracting CLIP embeddings from photos

from PySide6.QtCore import QThread, Signal
import time
from typing import Optional

from logging_config import get_logger
from repository import PhotoRepository
from services.semantic_search_service import SemanticSearchService

logger = get_logger(__name__)


class EmbeddingExtractionWorker(QThread):
    """
    Background worker to extract CLIP embeddings for all photos.

    Processes photos in batches and updates database with embeddings.
    Emits progress signals for UI updates.
    """

    # Signals
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(bool, int)  # success, total_processed
    error = Signal(str)  # error_message

    def __init__(self, model_name: str = "large", batch_size: int = 10):
        """
        Initialize embedding extraction worker.

        Args:
            model_name: CLIP model variant ('base' or 'large')
            batch_size: Number of photos to process before updating progress
        """
        super().__init__()
        self.model_name = model_name
        self.batch_size = batch_size
        self._stop_requested = False

    def stop(self):
        """Request worker to stop processing."""
        logger.info("[EmbeddingWorker] Stop requested")
        self._stop_requested = True

    def run(self):
        """Main worker thread - extract embeddings for all photos."""
        photo_repo = PhotoRepository()
        total_processed = 0

        try:
            logger.info(f"[EmbeddingWorker] Starting extraction with model: {self.model_name}")

            # Initialize semantic search service (loads CLIP model)
            self.progress.emit(0, 100, "Loading CLIP model...")
            search_service = SemanticSearchService(model_name=self.model_name)

            # Get all photos without embeddings
            self.progress.emit(0, 100, "Finding photos to process...")
            photos = photo_repo.find_all(
                where_clause="embedding IS NULL",
                order_by="path ASC"
            )

            total_photos = len(photos)

            if total_photos == 0:
                logger.info("[EmbeddingWorker] No photos need embedding extraction")
                self.progress.emit(0, 0, "All photos already have embeddings")
                self.finished.emit(True, 0)
                return

            logger.info(f"[EmbeddingWorker] Found {total_photos} photos to process")

            # Process photos
            batch_start = time.time()
            for i, photo in enumerate(photos):
                if self._stop_requested:
                    logger.info(f"[EmbeddingWorker] Stopped by user at {total_processed}/{total_photos}")
                    self.finished.emit(False, total_processed)
                    return

                photo_path = photo['path']
                photo_id = photo.get('id')

                try:
                    # Extract embedding
                    embedding = search_service.extract_image_embedding(photo_path)

                    if embedding is not None:
                        # Store embedding in database
                        embedding_blob = embedding.tobytes()

                        # Update photo_metadata with embedding
                        photo_repo.db._connect()
                        with photo_repo.db._connect() as conn:
                            conn.execute(
                                "UPDATE photo_metadata SET embedding = ? WHERE id = ?",
                                (embedding_blob, photo_id)
                            )
                            conn.commit()

                        total_processed += 1

                        # Log progress every batch
                        if (i + 1) % self.batch_size == 0:
                            batch_time = time.time() - batch_start
                            photos_per_sec = self.batch_size / batch_time if batch_time > 0 else 0
                            eta_seconds = (total_photos - i - 1) / photos_per_sec if photos_per_sec > 0 else 0

                            logger.info(
                                f"[EmbeddingWorker] Progress: {i + 1}/{total_photos} "
                                f"({photos_per_sec:.1f} photos/sec, ETA: {eta_seconds:.0f}s)"
                            )

                            batch_start = time.time()

                    else:
                        logger.warning(f"[EmbeddingWorker] Failed to extract embedding: {photo_path}")

                    # Update progress UI
                    progress_pct = int((i + 1) / total_photos * 100)
                    self.progress.emit(
                        i + 1,
                        total_photos,
                        f"Processing photo {i + 1}/{total_photos}: {photo_path[-50:]}"
                    )

                except Exception as e:
                    logger.error(f"[EmbeddingWorker] Error processing {photo_path}: {e}")
                    continue

            # Complete
            logger.info(f"[EmbeddingWorker] Extraction complete: {total_processed}/{total_photos} photos")
            self.finished.emit(True, total_processed)

        except Exception as e:
            logger.error(f"[EmbeddingWorker] Fatal error: {e}")
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))
