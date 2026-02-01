"""
JobManager - Central Background Jobs Orchestration Service

Version: 1.0.0
Date: 2026-02-01

Best-practice background jobs system inspired by Google Photos, iPhone Photos, and Lightroom.
Provides non-blocking UI, resumable jobs, prioritization, and incremental results.

Key Principles:
1. Never run heavy work on UI thread
2. Work in small chunks with checkpoints
3. Make jobs resumable + cancelable
4. Prioritize user-visible content
5. Surface partial results immediately

Architecture:
    JobManager (singleton)
    ├── WorkerPool (QThreadPool)
    ├── ActiveJobs (tracking running workers)
    ├── Signals (progress, partial_results, completed)
    └── Database (ml_job table via JobService)

Usage:
    from services.job_manager import get_job_manager

    job_manager = get_job_manager()

    # Enqueue a face detection job
    job_id = job_manager.enqueue(
        job_type='face_scan',
        project_id=1,
        priority=JobPriority.NORMAL
    )

    # Connect to signals for UI updates
    job_manager.signals.progress.connect(on_progress)
    job_manager.signals.partial_results.connect(on_partial_results)
    job_manager.signals.job_completed.connect(on_completed)

    # Pause/Resume/Cancel
    job_manager.pause(job_id)
    job_manager.resume(job_id)
    job_manager.cancel(job_id)

    # Pause all background work
    job_manager.pause_all()
"""

import os
import time
import uuid
import json
from enum import IntEnum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable, Set
from threading import Lock

from PySide6.QtCore import QObject, Signal, QThreadPool, QTimer, QRunnable, Slot

from services.job_service import get_job_service, Job
from logging_config import get_logger

logger = get_logger(__name__)


class JobPriority(IntEnum):
    """
    Job priority levels.

    Higher priority jobs run first. Use CRITICAL for user-initiated
    actions and LOW for background library scanning.
    """
    LOW = 0           # Deep archive scanning
    NORMAL = 50       # Standard background processing
    HIGH = 100        # Recent imports, visible folders
    CRITICAL = 200    # User-initiated action (e.g., clicked "Scan Faces")


class JobType:
    """Job type constants."""
    FACE_SCAN = 'face_scan'
    FACE_EMBED = 'face_embed'
    FACE_CLUSTER = 'face_cluster'
    EMBEDDING = 'embedding'
    DUPLICATE_HASH = 'duplicate_hash'
    DUPLICATE_GROUP = 'duplicate_group'


class JobStatus:
    """Job status constants."""
    QUEUED = 'queued'
    RUNNING = 'running'
    PAUSED = 'paused'
    COMPLETED = 'done'
    FAILED = 'failed'
    CANCELED = 'canceled'


@dataclass
class JobProgress:
    """Progress information for a job."""
    job_id: int
    job_type: str
    processed: int
    total: int
    rate: float = 0.0  # items per second
    eta_seconds: float = 0.0
    message: str = ""
    started_at: Optional[float] = None


@dataclass
class PartialResults:
    """Partial results emitted during job execution."""
    job_id: int
    job_type: str
    # Counts
    new_items_count: int = 0
    total_items_count: int = 0
    # Recent items (for UI preview)
    recent_items: List[Dict[str, Any]] = field(default_factory=list)
    # Type-specific data
    extra_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActiveJob:
    """Tracks an active job and its worker."""
    job_id: int
    job_type: str
    project_id: int
    worker: Optional[QRunnable] = None
    worker_id: str = ""
    started_at: float = 0.0
    processed: int = 0
    total: int = 0
    paused: bool = False
    cancel_requested: bool = False


class JobManagerSignals(QObject):
    """
    Qt signals for job manager events.

    Connect to these signals for UI updates.
    """
    # progress(job_id, processed, total, rate, eta, message)
    progress = Signal(int, int, int, float, float, str)

    # partial_results(job_type, new_count, total_count, recent_items_json)
    partial_results = Signal(str, int, int, str)

    # job_started(job_id, job_type, total_items)
    job_started = Signal(int, str, int)

    # job_completed(job_id, job_type, success, stats_json)
    job_completed = Signal(int, str, bool, str)

    # job_failed(job_id, job_type, error_message)
    job_failed = Signal(int, str, str)

    # job_canceled(job_id, job_type)
    job_canceled = Signal(int, str)

    # job_paused(job_id, job_type)
    job_paused = Signal(int, str)

    # job_resumed(job_id, job_type)
    job_resumed = Signal(int, str)

    # all_jobs_completed()
    all_jobs_completed = Signal()

    # active_jobs_changed(active_count)
    active_jobs_changed = Signal(int)


class JobManager(QObject):
    """
    Central job orchestration service.

    Manages background workers, provides pause/resume/cancel,
    tracks progress, and emits signals for UI updates.
    """

    # Singleton instance
    _instance: Optional['JobManager'] = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        super().__init__()

        # Initialize signals
        self.signals = JobManagerSignals()

        # Worker pool (bounded concurrency)
        self._thread_pool = QThreadPool.globalInstance()
        self._max_workers = min(4, self._thread_pool.maxThreadCount())

        # Active jobs tracking
        self._active_jobs: Dict[int, ActiveJob] = {}
        self._jobs_lock = Lock()

        # Paused jobs (waiting to resume)
        self._paused_jobs: Set[int] = set()

        # Global pause flag
        self._global_pause = False

        # Job service (persistent queue)
        self._job_service = get_job_service()

        # Heartbeat timer (keep leases alive)
        self._heartbeat_timer = QTimer()
        self._heartbeat_timer.timeout.connect(self._send_heartbeats)
        self._heartbeat_timer.start(30000)  # Every 30 seconds

        # Progress debounce timer (avoid UI flood)
        self._progress_timer = QTimer()
        self._progress_timer.timeout.connect(self._emit_debounced_progress)
        self._progress_timer.start(250)  # 4 updates per second max

        # Pending progress updates (debounced)
        self._pending_progress: Dict[int, JobProgress] = {}
        self._progress_lock = Lock()

        self._initialized = True
        logger.info(f"[JobManager] Initialized with max {self._max_workers} workers")

    # ─────────────────────────────────────────────────────────────────────────
    # Public API: Job Operations
    # ─────────────────────────────────────────────────────────────────────────

    def enqueue(
        self,
        job_type: str,
        project_id: int,
        priority: JobPriority = JobPriority.NORMAL,
        payload: Optional[Dict[str, Any]] = None,
        start_immediately: bool = True
    ) -> int:
        """
        Enqueue a new background job.

        Args:
            job_type: Type of job (face_scan, embedding, etc.)
            project_id: Project ID to process
            priority: Job priority (higher = runs first)
            payload: Additional job parameters
            start_immediately: Start job now (False = just queue)

        Returns:
            int: Job ID

        Example:
            job_id = job_manager.enqueue(
                job_type=JobType.FACE_SCAN,
                project_id=1,
                priority=JobPriority.HIGH
            )
        """
        # Build payload
        job_payload = payload or {}
        job_payload['project_id'] = project_id
        job_payload['job_type'] = job_type

        # Enqueue in persistent queue
        job_id = self._job_service.enqueue_job(
            kind=job_type,
            payload=job_payload,
            priority=int(priority),
            project_id=project_id
        )

        logger.info(
            f"[JobManager] Enqueued job {job_id}: {job_type} "
            f"(project={project_id}, priority={priority.name})"
        )

        # Start immediately unless paused or deferred
        if start_immediately and not self._global_pause:
            self._try_start_next_job()

        return job_id

    def pause(self, job_id: int) -> bool:
        """
        Pause a running job.

        The job will stop at the next checkpoint and save its progress.
        Resume with resume(job_id).

        Args:
            job_id: Job ID to pause

        Returns:
            bool: True if paused, False if not running
        """
        with self._jobs_lock:
            if job_id not in self._active_jobs:
                logger.warning(f"[JobManager] Cannot pause job {job_id}: not running")
                return False

            active = self._active_jobs[job_id]
            active.paused = True
            self._paused_jobs.add(job_id)

            # Signal worker to pause (if it supports it)
            if hasattr(active.worker, 'pause'):
                active.worker.pause()

            logger.info(f"[JobManager] Paused job {job_id}")
            self.signals.job_paused.emit(job_id, active.job_type)
            return True

    def resume(self, job_id: int) -> bool:
        """
        Resume a paused job.

        Args:
            job_id: Job ID to resume

        Returns:
            bool: True if resumed, False if not paused
        """
        if job_id not in self._paused_jobs:
            logger.warning(f"[JobManager] Cannot resume job {job_id}: not paused")
            return False

        self._paused_jobs.discard(job_id)

        with self._jobs_lock:
            if job_id in self._active_jobs:
                active = self._active_jobs[job_id]
                active.paused = False

                # Signal worker to resume (if it supports it)
                if hasattr(active.worker, 'resume'):
                    active.worker.resume()

        logger.info(f"[JobManager] Resumed job {job_id}")

        # Get job type from database if not in active jobs
        job = self._job_service.get_job(job_id)
        job_type = job.kind if job else 'unknown'
        self.signals.job_resumed.emit(job_id, job_type)

        # Try to start next job in case we have capacity
        self._try_start_next_job()
        return True

    def cancel(self, job_id: int) -> bool:
        """
        Cancel a queued or running job.

        Running jobs will stop at the next checkpoint.
        Progress is saved and can be resumed later.

        Args:
            job_id: Job ID to cancel

        Returns:
            bool: True if canceled
        """
        # Mark in database
        self._job_service.cancel_job(job_id)

        # Remove from paused set
        self._paused_jobs.discard(job_id)

        with self._jobs_lock:
            if job_id in self._active_jobs:
                active = self._active_jobs[job_id]
                active.cancel_requested = True

                # Signal worker to cancel
                if hasattr(active.worker, 'cancel'):
                    active.worker.cancel()

                logger.info(f"[JobManager] Canceled running job {job_id}")
                self.signals.job_canceled.emit(job_id, active.job_type)
            else:
                logger.info(f"[JobManager] Canceled queued job {job_id}")
                # Get job type from database
                job = self._job_service.get_job(job_id)
                job_type = job.kind if job else 'unknown'
                self.signals.job_canceled.emit(job_id, job_type)

        return True

    def pause_all(self):
        """Pause all background processing."""
        self._global_pause = True
        with self._jobs_lock:
            for job_id, active in self._active_jobs.items():
                active.paused = True
                self._paused_jobs.add(job_id)
                if hasattr(active.worker, 'pause'):
                    active.worker.pause()

        logger.info("[JobManager] Paused all background jobs")

    def resume_all(self):
        """Resume all background processing."""
        self._global_pause = False

        # Resume paused jobs
        for job_id in list(self._paused_jobs):
            self.resume(job_id)

        # Start any queued jobs
        self._try_start_next_job()
        logger.info("[JobManager] Resumed all background jobs")

    def cancel_all(self, project_id: Optional[int] = None):
        """
        Cancel all jobs (optionally filtered by project).

        Args:
            project_id: If specified, only cancel jobs for this project
        """
        with self._jobs_lock:
            jobs_to_cancel = [
                job_id for job_id, active in self._active_jobs.items()
                if project_id is None or active.project_id == project_id
            ]

        for job_id in jobs_to_cancel:
            self.cancel(job_id)

        logger.info(
            f"[JobManager] Canceled {len(jobs_to_cancel)} jobs"
            + (f" for project {project_id}" if project_id else "")
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API: Priority Management
    # ─────────────────────────────────────────────────────────────────────────

    def boost_priority(self, job_id: int, priority: JobPriority = JobPriority.HIGH):
        """
        Boost priority of a queued job.

        Use when user focuses on content that needs this job's results.

        Args:
            job_id: Job ID
            priority: New priority level
        """
        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            with db.get_connection() as conn:
                conn.execute(
                    "UPDATE ml_job SET priority = ? WHERE job_id = ?",
                    (int(priority), job_id)
                )
                conn.commit()
            logger.info(f"[JobManager] Boosted job {job_id} to priority {priority.name}")
        except Exception as e:
            logger.error(f"[JobManager] Failed to boost priority: {e}")

    def prioritize_paths(self, paths: List[str], project_id: int):
        """
        Prioritize processing for specific paths.

        Use when user views a folder - its content should be processed first.

        Args:
            paths: File paths to prioritize
            project_id: Project ID
        """
        # TODO: Implement path-based prioritization
        # This would require tracking which paths each job covers
        # and reordering the queue accordingly
        logger.debug(f"[JobManager] Prioritize {len(paths)} paths (not yet implemented)")

    # ─────────────────────────────────────────────────────────────────────────
    # Public API: Status & Info
    # ─────────────────────────────────────────────────────────────────────────

    def get_active_jobs(self) -> List[Dict[str, Any]]:
        """
        Get list of active jobs.

        Returns:
            List of job info dicts with progress
        """
        with self._jobs_lock:
            return [
                {
                    'job_id': active.job_id,
                    'job_type': active.job_type,
                    'project_id': active.project_id,
                    'processed': active.processed,
                    'total': active.total,
                    'paused': active.paused,
                    'started_at': active.started_at,
                    'progress_pct': (active.processed / active.total * 100) if active.total > 0 else 0
                }
                for active in self._active_jobs.values()
            ]

    def get_queued_jobs(self, limit: int = 20) -> List[Job]:
        """Get queued jobs ordered by priority."""
        return self._job_service.get_jobs(status='queued', limit=limit)

    def get_job_stats(self) -> Dict[str, Any]:
        """
        Get job statistics.

        Returns:
            Dict with counts by status, active count, etc.
        """
        stats = self._job_service.get_job_stats()
        stats['active_count'] = len(self._active_jobs)
        stats['paused_count'] = len(self._paused_jobs)
        stats['global_pause'] = self._global_pause
        return stats

    def is_job_running(self, job_type: str, project_id: int) -> bool:
        """Check if a job of given type is running for a project."""
        with self._jobs_lock:
            for active in self._active_jobs.values():
                if active.job_type == job_type and active.project_id == project_id:
                    return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Worker Management (Internal)
    # ─────────────────────────────────────────────────────────────────────────

    def _try_start_next_job(self):
        """Try to start the next queued job if we have capacity."""
        if self._global_pause:
            return

        with self._jobs_lock:
            active_count = len([j for j in self._active_jobs.values() if not j.paused])
            if active_count >= self._max_workers:
                return

        # Get next queued job
        queued_jobs = self._job_service.get_jobs(status='queued', limit=1)
        if not queued_jobs:
            return

        job = queued_jobs[0]
        self._start_job(job)

    def _start_job(self, job: Job):
        """Start a job with its appropriate worker."""
        worker_id = f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"

        # Claim the job
        if not self._job_service.claim_job(job.job_id, worker_id):
            logger.warning(f"[JobManager] Failed to claim job {job.job_id}")
            return

        # Create appropriate worker
        worker = self._create_worker(job)
        if not worker:
            logger.error(f"[JobManager] No worker available for job type: {job.kind}")
            self._job_service.complete_job(job.job_id, success=False, error="No worker for job type")
            return

        # Track active job
        payload = job.payload
        active = ActiveJob(
            job_id=job.job_id,
            job_type=job.kind,
            project_id=job.project_id or payload.get('project_id', 0),
            worker=worker,
            worker_id=worker_id,
            started_at=time.time(),
            total=payload.get('total', 0)
        )

        with self._jobs_lock:
            self._active_jobs[job.job_id] = active

        # Connect worker signals
        self._connect_worker_signals(job.job_id, worker)

        # Start worker
        self._thread_pool.start(worker)

        logger.info(f"[JobManager] Started job {job.job_id}: {job.kind}")
        self.signals.job_started.emit(job.job_id, job.kind, active.total)
        self.signals.active_jobs_changed.emit(len(self._active_jobs))

    def _create_worker(self, job: Job) -> Optional[QRunnable]:
        """Create appropriate worker for job type."""
        payload = job.payload
        project_id = job.project_id or payload.get('project_id')

        if job.kind == JobType.FACE_SCAN:
            from workers.face_detection_worker import FaceDetectionWorker
            return FaceDetectionWorker(
                project_id=project_id,
                skip_processed=payload.get('skip_processed', True),
                photo_paths=payload.get('photo_paths')
            )

        elif job.kind == JobType.EMBEDDING:
            from workers.embedding_worker import EmbeddingWorker
            return EmbeddingWorker(
                job_id=job.job_id,
                photo_ids=payload.get('photo_ids', []),
                model_variant=payload.get('model_variant'),
                device=payload.get('device', 'auto'),
                project_id=project_id
            )

        elif job.kind in ('embed', 'semantic_embedding'):
            from workers.semantic_embedding_worker import SemanticEmbeddingWorker
            return SemanticEmbeddingWorker(
                photo_ids=payload.get('photo_ids', []),
                model_name=payload.get('model_name'),
                project_id=project_id,
                force_recompute=payload.get('force_recompute', False)
            )

        # Add more job types as needed
        return None

    def _connect_worker_signals(self, job_id: int, worker: QRunnable):
        """Connect worker signals to job manager handlers."""
        if hasattr(worker, 'signals'):
            signals = worker.signals

            # Progress signal
            if hasattr(signals, 'progress'):
                signals.progress.connect(
                    lambda cur, total, msg, jid=job_id: self._on_worker_progress(jid, cur, total, msg)
                )

            # Finished signal
            if hasattr(signals, 'finished'):
                # Handle different signal signatures
                try:
                    signals.finished.connect(
                        lambda *args, jid=job_id: self._on_worker_finished(jid, True, args)
                    )
                except Exception:
                    pass

            # Error signal
            if hasattr(signals, 'error'):
                signals.error.connect(
                    lambda *args, jid=job_id: self._on_worker_error(jid, args)
                )

            # Face detected signal (for partial results)
            if hasattr(signals, 'face_detected'):
                signals.face_detected.connect(
                    lambda path, count, jid=job_id: self._on_face_detected(jid, path, count)
                )

    def _on_worker_progress(self, job_id: int, current: int, total: int, message: str):
        """Handle worker progress update."""
        with self._jobs_lock:
            if job_id in self._active_jobs:
                active = self._active_jobs[job_id]
                active.processed = current
                active.total = total

        # Calculate rate and ETA
        with self._jobs_lock:
            active = self._active_jobs.get(job_id)
            if active:
                elapsed = time.time() - active.started_at
                rate = current / elapsed if elapsed > 0 else 0
                remaining = total - current
                eta = remaining / rate if rate > 0 else 0
            else:
                rate = 0
                eta = 0

        # Debounce progress updates
        with self._progress_lock:
            self._pending_progress[job_id] = JobProgress(
                job_id=job_id,
                job_type=active.job_type if active else 'unknown',
                processed=current,
                total=total,
                rate=rate,
                eta_seconds=eta,
                message=message,
                started_at=active.started_at if active else None
            )

    def _on_worker_finished(self, job_id: int, success: bool, args: tuple):
        """Handle worker completion."""
        with self._jobs_lock:
            active = self._active_jobs.pop(job_id, None)

        if active:
            # Complete in database
            self._job_service.complete_job(job_id, success=success)

            # Build stats
            stats = {}
            if len(args) >= 3:
                stats = {
                    'success_count': args[0],
                    'failed_count': args[1],
                    'total_count': args[2]
                }

            logger.info(f"[JobManager] Job {job_id} completed: {stats}")
            self.signals.job_completed.emit(job_id, active.job_type, success, json.dumps(stats))
            self.signals.active_jobs_changed.emit(len(self._active_jobs))

            # Check if all jobs are done
            if len(self._active_jobs) == 0:
                self.signals.all_jobs_completed.emit()

        # Try to start next job
        self._try_start_next_job()

    def _on_worker_error(self, job_id: int, args: tuple):
        """Handle worker error."""
        error_msg = str(args[0]) if args else "Unknown error"

        with self._jobs_lock:
            active = self._active_jobs.pop(job_id, None)

        if active:
            self._job_service.complete_job(job_id, success=False, error=error_msg)
            logger.error(f"[JobManager] Job {job_id} failed: {error_msg}")
            self.signals.job_failed.emit(job_id, active.job_type, error_msg)
            self.signals.active_jobs_changed.emit(len(self._active_jobs))

        # Try to start next job
        self._try_start_next_job()

    def _on_face_detected(self, job_id: int, path: str, count: int):
        """Handle face detection partial result."""
        with self._jobs_lock:
            active = self._active_jobs.get(job_id)
            if not active:
                return

        # Emit partial results for UI update
        recent_items = [{'path': path, 'face_count': count}]
        self.signals.partial_results.emit(
            JobType.FACE_SCAN,
            count,  # new count
            0,      # total count (not tracked here)
            json.dumps(recent_items)
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Timers & Maintenance
    # ─────────────────────────────────────────────────────────────────────────

    def _send_heartbeats(self):
        """Send heartbeats for all active jobs."""
        with self._jobs_lock:
            for job_id, active in self._active_jobs.items():
                if not active.paused:
                    progress = active.processed / active.total if active.total > 0 else 0
                    self._job_service.heartbeat(job_id, progress)

    def _emit_debounced_progress(self):
        """Emit debounced progress updates to avoid flooding UI."""
        with self._progress_lock:
            pending = self._pending_progress.copy()
            self._pending_progress.clear()

        for job_id, progress in pending.items():
            self.signals.progress.emit(
                job_id,
                progress.processed,
                progress.total,
                progress.rate,
                progress.eta_seconds,
                progress.message
            )


# ─────────────────────────────────────────────────────────────────────────────
# Singleton Accessor
# ─────────────────────────────────────────────────────────────────────────────

_job_manager_instance: Optional[JobManager] = None
_job_manager_lock = Lock()


def get_job_manager() -> JobManager:
    """
    Get the singleton JobManager instance.

    Returns:
        JobManager: Singleton instance

    Example:
        from services.job_manager import get_job_manager

        manager = get_job_manager()
        job_id = manager.enqueue(JobType.FACE_SCAN, project_id=1)
    """
    global _job_manager_instance
    with _job_manager_lock:
        if _job_manager_instance is None:
            _job_manager_instance = JobManager()
        return _job_manager_instance
