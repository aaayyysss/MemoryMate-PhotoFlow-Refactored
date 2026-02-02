# workers/face_pipeline_worker.py
# Version 02.00.00.00 dated 20260202
#
# Background pipeline worker that chains face detection + clustering
# as a single non-blocking job.  No modal dialogs, no UI coupling.
#
# Steps:
#   1. Face detection (InsightFace on all unprocessed photos)
#   2. Face clustering (DBSCAN on ArcFace embeddings)
#
# Incremental batch_committed events are forwarded so the UI can
# refresh People progressively while detection is still running.

import threading

from PySide6.QtCore import QRunnable, QObject, Signal

from logging_config import get_logger

logger = get_logger(__name__)


class FacePipelineSignals(QObject):
    """Signals emitted by the face pipeline worker."""
    # (step_name, message)
    progress = Signal(str, str)
    # Forwarded from FaceDetectionWorker after each DB batch commit
    # (processed, total, faces_so_far, project_id)
    batch_committed = Signal(int, int, int, int)
    # Emitted when pipeline finishes: {faces_detected, clusters_created, errors}
    finished = Signal(dict)
    # Fatal error
    error = Signal(str)


class FacePipelineWorker(QRunnable):
    """
    Background worker that runs face detection then clustering
    entirely off the UI thread.

    Usage:
        worker = FacePipelineWorker(project_id=1)
        worker.signals.progress.connect(on_progress)
        worker.signals.finished.connect(on_finished)
        QThreadPool.globalInstance().start(worker)
    """

    def __init__(self, project_id: int, model: str = "buffalo_l"):
        super().__init__()
        self.setAutoDelete(True)
        self.signals = FacePipelineSignals()
        self.project_id = project_id
        self.model = model
        self._cancelled = False
        # Optional: scoped photo paths (set by FacePipelineService)
        self._scoped_photo_paths = None

    def cancel(self):
        self._cancelled = True

    def run(self):
        """Execute face detection + clustering sequentially in background thread."""
        import threading
        _thread = threading.current_thread()
        _is_main = _thread is threading.main_thread()
        logger.info(
            "[FacePipelineWorker] Starting face pipeline for project %d "
            "(thread=%s, is_main=%s)",
            self.project_id, _thread.name, _is_main,
        )

        results = {
            "faces_detected": 0,
            "images_processed": 0,
            "clusters_created": 0,
            "errors": [],
        }

        # ── Step 1: Face Detection ────────────────────────────────
        if self._cancelled:
            self.signals.finished.emit(results)
            return

        self.signals.progress.emit("face_detection", "Detecting faces in photos...")

        try:
            from workers.face_detection_worker import FaceDetectionWorker

            worker_kwargs = {
                "project_id": self.project_id,
                "model": self.model,
                "skip_processed": True,
            }
            if self._scoped_photo_paths:
                worker_kwargs["photo_paths"] = self._scoped_photo_paths

            face_worker = FaceDetectionWorker(**worker_kwargs)

            detection_results = {}

            def _on_detect_progress(current, total, message):
                self.signals.progress.emit(
                    "face_detection",
                    f"Detecting faces: {current}/{total} — {message}",
                )

            def _on_detect_batch(processed, total, faces_so_far, pid):
                # Forward to pipeline-level signal for incremental UI refresh
                self.signals.batch_committed.emit(processed, total, faces_so_far, pid)

            def _on_detect_finished(success, failed, total_faces):
                detection_results["success"] = success
                detection_results["failed"] = failed
                detection_results["total_faces"] = total_faces

            def _on_detect_error(path, msg):
                logger.warning("[FacePipelineWorker] Detection error on %s: %s", path, msg)

            face_worker.signals.progress.connect(_on_detect_progress)
            face_worker.signals.batch_committed.connect(_on_detect_batch)
            face_worker.signals.finished.connect(_on_detect_finished)
            face_worker.signals.error.connect(_on_detect_error)

            # Execute directly in this thread (already off UI)
            face_worker.run()

            # Collect results (signals fire synchronously in same thread)
            results["faces_detected"] = detection_results.get("total_faces", 0)
            results["images_processed"] = detection_results.get("success", 0)

            logger.info(
                "[FacePipelineWorker] Detection complete: %d faces in %d images",
                results["faces_detected"], results["images_processed"],
            )

        except Exception as e:
            logger.error("[FacePipelineWorker] Face detection failed: %s", e, exc_info=True)
            results["errors"].append(f"Detection: {e}")

        # ── Step 2: Face Clustering ───────────────────────────────
        if self._cancelled or results["faces_detected"] == 0:
            if results["faces_detected"] == 0:
                logger.info("[FacePipelineWorker] No faces detected, skipping clustering")
            self.signals.finished.emit(results)
            return

        self.signals.progress.emit("face_clustering", "Clustering detected faces...")

        try:
            from config.face_detection_config import get_face_config
            face_config = get_face_config()
            cluster_params = face_config.get_clustering_params()

            from workers.face_cluster_worker import FaceClusterWorker

            cluster_worker = FaceClusterWorker(
                project_id=self.project_id,
                eps=cluster_params["eps"],
                min_samples=cluster_params["min_samples"],
                auto_tune=True,
            )

            cluster_results = {}

            def _on_cluster_progress(current, total, message):
                self.signals.progress.emit(
                    "face_clustering",
                    f"Clustering faces: {message}",
                )

            def _on_cluster_finished(cluster_count, total_faces):
                cluster_results["cluster_count"] = cluster_count
                cluster_results["total_faces"] = total_faces

            def _on_cluster_error(msg):
                results["errors"].append(f"Clustering: {msg}")

            cluster_worker.signals.progress.connect(_on_cluster_progress)
            cluster_worker.signals.finished.connect(_on_cluster_finished)
            cluster_worker.signals.error.connect(_on_cluster_error)

            # Execute directly in this thread
            cluster_worker.run()

            results["clusters_created"] = cluster_results.get("cluster_count", 0)

            logger.info(
                "[FacePipelineWorker] Clustering complete: %d clusters from %d faces",
                results["clusters_created"],
                cluster_results.get("total_faces", 0),
            )

        except Exception as e:
            logger.error("[FacePipelineWorker] Clustering failed: %s", e, exc_info=True)
            results["errors"].append(f"Clustering: {e}")

        self.signals.finished.emit(results)
