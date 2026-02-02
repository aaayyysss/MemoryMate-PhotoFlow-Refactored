# services/face_pipeline_service.py
# Central orchestrator for face detection + clustering.
#
# All UI entry points (scan controller, main window button, sidebar button)
# call this service instead of creating workers directly.
# The service guarantees:
#   - Only one pipeline runs per project at a time
#   - project_id is validated before workers start
#   - Progress is forwarded through unified Qt signals
#   - Cancellation is clean and idempotent
#   - Incremental batch_committed events drive progressive People refresh

import logging
import threading
from typing import Optional, List

from PySide6.QtCore import QObject, Signal, QThreadPool

logger = logging.getLogger(__name__)


class FacePipelineService(QObject):
    """
    Central face-pipeline orchestrator.

    Usage (from any UI entry point):
        svc = FacePipelineService.instance()
        svc.start(project_id=1)
        svc.start(project_id=1, photo_paths=[...])  # scoped run
        svc.cancel(project_id=1)
    """

    # ── Signals ──────────────────────────────────────────────
    # (step_name: str, message: str, project_id: int)
    progress = Signal(str, str, int)

    # (processed: int, total: int, faces_so_far: int, project_id: int)
    batch_committed = Signal(int, int, int, int)

    # (results: dict, project_id: int)
    finished = Signal(dict, int)

    # (message: str, project_id: int)
    error = Signal(str, int)

    # Emitted when pipeline starts (project_id)
    started = Signal(int)

    # ── Singleton ────────────────────────────────────────────
    _instance: Optional["FacePipelineService"] = None

    @classmethod
    def instance(cls) -> "FacePipelineService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        # project_id → worker reference (for cancellation / duplicate guard)
        self._running: dict[int, object] = {}
        self._lock = threading.Lock()

    # ── Public API ───────────────────────────────────────────

    def is_running(self, project_id: int) -> bool:
        with self._lock:
            return project_id in self._running

    def start(
        self,
        project_id: int,
        photo_paths: Optional[List[str]] = None,
        model: str = "buffalo_l",
    ) -> bool:
        """
        Launch face detection + clustering for *project_id*.

        Args:
            project_id:   Must be a valid, non-None project id.
            photo_paths:  Optional scope — subset of photos to process.
            model:        InsightFace model name.

        Returns True if pipeline was started, False if already running or
        project_id is invalid.
        """
        if not project_id:
            logger.warning("[FacePipelineService] Refusing to start — project_id is None/0")
            self.error.emit("No project selected", 0)
            return False

        with self._lock:
            if project_id in self._running:
                logger.info(
                    "[FacePipelineService] Pipeline already running for project %d, ignoring",
                    project_id,
                )
                return False

        # Validate project exists in DB
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            with db._connect() as conn:
                row = conn.execute(
                    "SELECT id FROM projects WHERE id = ?", (project_id,)
                ).fetchone()
                if not row:
                    logger.error("[FacePipelineService] project_id=%d not found", project_id)
                    self.error.emit(f"Project {project_id} not found", project_id)
                    return False
        except Exception as e:
            logger.error("[FacePipelineService] DB check failed: %s", e)
            self.error.emit(str(e), project_id)
            return False

        logger.info(
            "[FacePipelineService] Starting pipeline for project %d (scope=%s, model=%s)",
            project_id,
            f"{len(photo_paths)} photos" if photo_paths else "all",
            model,
        )

        from workers.face_pipeline_worker import FacePipelineWorker

        worker = FacePipelineWorker(
            project_id=project_id,
            model=model,
        )
        # If scoped paths were given, pass them through to the inner detection worker
        if photo_paths:
            worker._scoped_photo_paths = photo_paths

        # ── Connect worker signals → service signals ─────────
        def _on_progress(step_name, message):
            self.progress.emit(step_name, message, project_id)

        def _on_finished(results):
            with self._lock:
                self._running.pop(project_id, None)
            self.finished.emit(results, project_id)

        def _on_error(msg):
            with self._lock:
                self._running.pop(project_id, None)
            self.error.emit(msg, project_id)

        worker.signals.progress.connect(_on_progress)
        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(_on_error)

        with self._lock:
            self._running[project_id] = worker

        self.started.emit(project_id)
        QThreadPool.globalInstance().start(worker)
        return True

    def cancel(self, project_id: int):
        """Cancel the running pipeline for *project_id* (idempotent)."""
        with self._lock:
            worker = self._running.get(project_id)
        if worker and hasattr(worker, "cancel"):
            logger.info("[FacePipelineService] Cancelling pipeline for project %d", project_id)
            worker.cancel()
        else:
            logger.debug("[FacePipelineService] No running pipeline for project %d", project_id)
