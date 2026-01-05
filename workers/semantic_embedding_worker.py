"""
SemanticEmbeddingWorker - Offline Batch Embedding

Version: 1.0.0
Date: 2026-01-05

Offline batch embedding extraction for semantic search.

Properties (non-negotiable):
- Offline (no blocking UI)
- Idempotent (safe to restart)
- Restart-safe (skips already processed)
- Progress reporting
- Per-photo error handling (doesn't fail entire batch)

Usage:
    worker = SemanticEmbeddingWorker(photo_ids=[1, 2, 3], model_name="clip-vit-b32")
    worker.signals.progress.connect(on_progress)
    worker.signals.finished.connect(on_finished)
    QThreadPool.globalInstance().start(worker)
"""

import time
import hashlib
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QRunnable, QObject, Signal

from services.semantic_embedding_service import get_semantic_embedding_service
from repository.photo_repository import PhotoRepository
from logging_config import get_logger

logger = get_logger(__name__)


class SemanticEmbeddingSignals(QObject):
    """Signals for semantic embedding worker."""
    progress = Signal(int, int, str)  # (current, total, message)
    finished = Signal(dict)  # stats
    error = Signal(str)  # error message


class SemanticEmbeddingWorker(QRunnable):
    """
    Worker for batch semantic embedding extraction.

    Properties:
    - ✔ Offline (runs in background thread)
    - ✔ Idempotent (skip already processed)
    - ✔ Restart-safe (no state corruption on crash)
    - ✔ Per-photo error handling
    - ✔ Progress reporting
    """

    def __init__(self,
                 photo_ids: List[int],
                 model_name: str = "clip-vit-b32",
                 force_recompute: bool = False):
        """
        Initialize semantic embedding worker.

        Args:
            photo_ids: List of photo IDs to process
            model_name: CLIP/SigLIP model variant
            force_recompute: If True, recompute even if embedding exists
        """
        super().__init__()
        self.photo_ids = photo_ids
        self.model_name = model_name
        self.force_recompute = force_recompute

        self.signals = SemanticEmbeddingSignals()

        # Statistics
        self.success_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.start_time = None

    def run(self):
        """Execute batch embedding extraction."""
        self.start_time = time.time()

        logger.info(
            f"[SemanticEmbeddingWorker] Starting batch: {len(self.photo_ids)} photos, "
            f"model={self.model_name}, force={self.force_recompute}"
        )

        try:
            # Initialize services
            embedder = get_semantic_embedding_service(model_name=self.model_name)
            photo_repo = PhotoRepository()

            # Check availability
            if not embedder.available:
                error_msg = "PyTorch/Transformers not available. Cannot extract embeddings."
                logger.error(f"[SemanticEmbeddingWorker] {error_msg}")
                self.signals.error.emit(error_msg)
                return

            total = len(self.photo_ids)

            for i, photo_id in enumerate(self.photo_ids, 1):
                try:
                    self._process_photo(photo_id, embedder, photo_repo)
                except Exception as e:
                    logger.error(f"[SemanticEmbeddingWorker] Failed to process photo {photo_id}: {e}")
                    self.failed_count += 1

                # Progress reporting (every 10 photos or last)
                if i % 10 == 0 or i == total:
                    self.signals.progress.emit(
                        i,
                        total,
                        f"Processing {i}/{total} photos... (✓{self.success_count}, ⊘{self.skipped_count}, ✗{self.failed_count})"
                    )

            # Finish
            duration = time.time() - self.start_time
            stats = {
                'total': total,
                'success': self.success_count,
                'skipped': self.skipped_count,
                'failed': self.failed_count,
                'duration_sec': duration,
            }

            logger.info(
                f"[SemanticEmbeddingWorker] Batch complete: "
                f"{self.success_count} success, {self.skipped_count} skipped, "
                f"{self.failed_count} failed in {duration:.1f}s"
            )

            self.signals.finished.emit(stats)

        except Exception as e:
            logger.error(f"[SemanticEmbeddingWorker] Fatal error: {e}", exc_info=True)
            self.signals.error.emit(str(e))

    def _process_photo(self,
                      photo_id: int,
                      embedder,
                      photo_repo: PhotoRepository):
        """
        Process single photo (idempotent).

        Args:
            photo_id: Photo ID
            embedder: SemanticEmbeddingService instance
            photo_repo: PhotoRepository instance
        """
        # Check if already processed (idempotent)
        if not self.force_recompute and embedder.has_embedding(photo_id):
            logger.debug(f"[SemanticEmbeddingWorker] Photo {photo_id} already has embedding, skipping")
            self.skipped_count += 1
            return

        # Get photo metadata
        photo = photo_repo.get_photo_by_id(photo_id)
        if photo is None:
            logger.warning(f"[SemanticEmbeddingWorker] Photo {photo_id} not found in database")
            self.failed_count += 1
            return

        file_path = photo.get('file_path') or photo.get('path')
        if not file_path:
            logger.warning(f"[SemanticEmbeddingWorker] Photo {photo_id} has no file_path")
            self.failed_count += 1
            return

        # Check if file exists
        if not Path(file_path).exists():
            logger.warning(f"[SemanticEmbeddingWorker] Photo {photo_id} file not found: {file_path}")
            self.failed_count += 1
            return

        # Compute hash for freshness tracking
        source_hash = self._compute_hash(file_path)
        source_mtime = str(Path(file_path).stat().st_mtime)

        # Extract embedding
        try:
            embedding = embedder.encode_image(file_path)
        except Exception as e:
            logger.error(f"[SemanticEmbeddingWorker] Failed to encode photo {photo_id}: {e}")
            self.failed_count += 1
            return

        # Store embedding
        try:
            embedder.store_embedding(
                photo_id=photo_id,
                embedding=embedding,
                source_hash=source_hash,
                source_mtime=source_mtime
            )
            self.success_count += 1
            logger.debug(f"[SemanticEmbeddingWorker] ✓ Photo {photo_id} processed")
        except Exception as e:
            logger.error(f"[SemanticEmbeddingWorker] Failed to store embedding for photo {photo_id}: {e}")
            self.failed_count += 1

    def _compute_hash(self, file_path: str) -> str:
        """
        Compute SHA256 hash of file (for freshness tracking).

        Args:
            file_path: Path to file

        Returns:
            Hex digest of SHA256 hash
        """
        try:
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(4096), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.warning(f"[SemanticEmbeddingWorker] Failed to compute hash for {file_path}: {e}")
            return ""
