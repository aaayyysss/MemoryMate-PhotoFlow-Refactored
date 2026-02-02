# scan_controller.py
# Version 10.01.01.05 dated 20260127

"""
ScanController - Photo/Video Scanning Orchestration

Extracted from main_window_qt.py (Phase 1, Step 1.3)

Responsibilities:
- Start/cancel scan operations
- Progress tracking and UI updates
- Post-scan cleanup and processing
- Database schema initialization
- Face detection integration
- Sidebar/grid refresh coordination

Version: 10.01.01.03
"""

import logging
from datetime import datetime
from typing import List
from PySide6.QtCore import QThread, Qt, QTimer, QThreadPool, Slot, QObject, Signal
from PySide6.QtWidgets import (
    QProgressDialog, QMessageBox, QDialog, QApplication
)
#from translations import tr
from translation_manager import tr


class ScanController(QObject):
    """
    Wraps scan orchestration: start, cancel, cleanup, progress wiring.
    Keeps MainWindow slimmer.
    """
    # Signal for cross-thread progress updates
    progress_update_signal = Signal(int, str)

    def __init__(self, main):
        super().__init__()  # CRITICAL: Initialize QObject
        self.main = main

        # Connect signal to handler with QueuedConnection for thread safety
        self.progress_update_signal.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        self.thread = None
        self.worker = None
        self.db_writer = None
        self.cancel_requested = False
        self.logger = logging.getLogger(__name__)

        # CRITICAL FIX: Progress dialog threshold to prevent UI freeze on tiny scans
        # Only show progress dialog if file count exceeds this threshold
        # Threshold of 20 shows dialog for medium/large scans
        self.PROGRESS_DIALOG_THRESHOLD = 20
        self._total_files_found = 0
        self._progress_events: List[str] = []

        # PHASE 2 Task 2.2: Debounce reload operations
        # Track pending async operations to coordinate single refresh after ALL complete
        self._scan_operations_pending = set()
        self._scan_refresh_scheduled = False
        self._scan_result_cached = None  # Cache scan results for final refresh

    def _test_progress_slot(self, pct: int, msg: str):
        """Test slot to verify Qt signal delivery is working."""
        # Removed verbose debug logging - signal delivery confirmed working
        pass

    @Slot(int, str)
    def update_progress_safe(self, pct: int, msg: str):
        """
        Thread-safe progress update method.

        Can be called from any thread - automatically marshals to main thread if needed.
        """
        from PySide6.QtCore import QThread, QMetaObject, Qt
        from PySide6.QtWidgets import QApplication

        # Check if we're in the main thread
        # CRITICAL: Use QThread.currentThread(), NOT self.thread (which is the worker thread object!)
        current_thread = QThread.currentThread()
        main_thread = QApplication.instance().thread()

        if current_thread != main_thread:
            # Called from worker thread - marshal to main thread via signal
            # Emit signal - QueuedConnection ensures it runs in main thread
            self.progress_update_signal.emit(pct, msg)
        else:
            # Already in main thread - direct call
            self._on_progress(pct, msg)

    @Slot(int, str)
    def _on_progress_main_thread(self, pct: int, msg: str):
        """Helper to ensure we're in main thread when calling _on_progress."""
        self._on_progress(pct, msg)

    def start_scan(self, folder, incremental: bool):
        """Entry point called from MainWindow toolbar action."""
        # Phase 3B: Show pre-scan options dialog
        from ui.prescan_options_dialog import PreScanOptionsDialog

        options_dialog = PreScanOptionsDialog(parent=self.main, default_incremental=incremental)
        if options_dialog.exec() != QDialog.Accepted:
            # User cancelled
            self.main.statusBar().showMessage("Scan cancelled")
            return

        # Get user-selected options
        scan_options = options_dialog.get_options()
        incremental = scan_options.incremental

        # Store duplicate detection options for post-scan processing
        self._duplicate_detection_enabled = scan_options.detect_duplicates
        self._detect_exact = scan_options.detect_exact
        self._detect_similar = scan_options.detect_similar
        self._generate_embeddings = scan_options.generate_embeddings
        self._time_window_seconds = scan_options.time_window_seconds
        self._similarity_threshold = scan_options.similarity_threshold
        self._min_stack_size = scan_options.min_stack_size

        self.cancel_requested = False
        self.main.statusBar().showMessage(f"📸 Scanning repository: {folder} (incremental={incremental})")
        self.main._committed_total = 0

        # PHASE 2 Task 2.2: Initialize pending operations tracker
        # Main scan will mark these complete as each operation finishes
        self._scan_operations_pending = {"main_scan", "date_branches"}
        self._scan_refresh_scheduled = False
        self._scan_result_cached = None
        self._progress_events = []

        # Progress dialog — non-modal so the user can still interact with the app
        from translation_manager import tr
        self.main._scan_progress = QProgressDialog(
            tr("messages.scan_preparing"),
            tr("messages.scan_cancel_button"),
            0, 100, self.main
        )
        self.main._scan_progress.setWindowTitle(tr("messages.scan_dialog_title"))
        self.main._scan_progress.setWindowModality(Qt.NonModal)
        self.main._scan_progress.setModal(False)
        self.main._scan_progress.setAutoClose(False)
        self.main._scan_progress.setAutoReset(False)
        self.main._scan_progress.setMinimumDuration(0)
        self.main._scan_progress.setMinimumWidth(520)
        self.main._scan_progress.show()

        # DB writer
        # NOTE: Schema creation handled automatically by repository layer
        from db_writer import DBWriter
        self.db_writer = DBWriter(batch_size=200, poll_interval_ms=150)
        self.db_writer.error.connect(lambda msg: self.logger.error(f"DBWriter error: {msg}"))
        self.db_writer.committed.connect(self._on_committed)
        self.db_writer.start()

        # CRITICAL: Initialize database schema before starting scan
        # This ensures the repository layer has created all necessary tables
        try:
            from repository.base_repository import DatabaseConnection
            db_conn = DatabaseConnection("reference_data.db", auto_init=True)
            self.logger.info("Database schema initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize database schema: {e}", exc_info=True)
            self.main.statusBar().showMessage(f"❌ Database initialization failed: {e}")
            return

        # Get current project_id
        current_project_id = self.main.grid.project_id
        if current_project_id is None:
            # Fallback to default project if grid doesn't have a project yet
            from app_services import get_default_project_id
            current_project_id = get_default_project_id()
            if current_project_id is None:
                # No projects exist - will be created during scan
                current_project_id = 1  # Default to first project
            self.logger.debug(f"Using project_id: {current_project_id}")

        # Scan worker
        try:
            from services.scan_worker_adapter import ScanWorkerAdapter as ScanWorker

            try:
                self.thread = QThread(self.main)
            except Exception as qthread_err:
                self.logger.error(f"Failed to create QThread: {qthread_err}", exc_info=True)
                raise

            # CRITICAL: Define callback for video metadata extraction completion
            # PHASE 2 Task 2.2: This now marks operation complete instead of refreshing immediately
            def on_video_metadata_finished(success, failed):
                """Mark video metadata extraction complete and trigger coordinated refresh."""
                self.logger.info(f"Video metadata extraction complete ({success} success, {failed} failed)")

                # CRITICAL FIX: ALWAYS run video date backfill after scan (not conditional)
                # Without this, video date branches show 0 count and no dates appear
                if success > 0:
                    # PHASE 2 Task 2.2: Track video backfill as separate operation
                    self._scan_operations_pending.add("video_backfill")
                    self.logger.info("Auto-running video metadata backfill...")
                    # Run backfill in background to populate date fields
                    from backfill_video_dates import backfill_video_dates
                    try:
                        stats = backfill_video_dates(
                            project_id=current_project_id,
                            dry_run=False,
                            progress_callback=lambda c, t, m: self.logger.info(f"[Backfill] {c}/{t}: {m}")
                        )
                        self.logger.info(f"✓ Video backfill complete: {stats['updated']} videos updated")
                    except Exception as e:
                        self.logger.error(f"Video backfill failed: {e}", exc_info=True)
                    finally:
                        # PHASE 2 Task 2.2: Mark backfill complete
                        self._scan_operations_pending.discard("video_backfill")
                        self._check_and_trigger_final_refresh()

                # PHASE 2 Task 2.2: Mark video metadata complete and check for final refresh
                # DON'T refresh immediately - let coordinator handle it
                self._scan_operations_pending.discard("video_metadata")
                self.logger.info(f"Video metadata operation complete. Remaining: {self._scan_operations_pending}")
                self._check_and_trigger_final_refresh()

            try:
                self.worker = ScanWorker(folder, current_project_id, incremental, self.main.settings,
                                        db_writer=self.db_writer,
                                        on_video_metadata_finished=on_video_metadata_finished,
                                        progress_receiver=self)  # CRITICAL: Pass self for thread-safe progress updates
            except Exception as worker_err:
                self.logger.error(f"Failed to create ScanWorker: {worker_err}", exc_info=True)
                raise

            try:
                self.worker.moveToThread(self.thread)
            except Exception as move_err:
                self.logger.error(f"Failed to move worker to thread: {move_err}", exc_info=True)
                raise

            try:
                # CRITICAL FIX: Use Qt.QueuedConnection explicitly to prevent deadlock
                # When progress is emitted from worker thread via synchronous callback,
                # we need to ensure the emit() returns immediately without blocking

                # Connect test slot to verify Qt signal delivery (using proper class method to avoid GC issues)
                self.worker.progress.connect(self._test_progress_slot, Qt.QueuedConnection)

                # Connect actual handler
                self.worker.progress.connect(self._on_progress, Qt.QueuedConnection)

                self.worker.finished.connect(self._on_finished, Qt.QueuedConnection)
                self.worker.error.connect(self._on_error, Qt.QueuedConnection)
                self.thread.started.connect(self.worker.run)
                self.worker.finished.connect(lambda f, p, v=0: self.thread.quit())
                self.thread.finished.connect(self._cleanup)
            except Exception as signal_err:
                self.logger.error(f"Failed to connect signals: {signal_err}", exc_info=True)
                import traceback
                traceback.print_exc()
                raise

            # Start scan thread immediately - DBWriter is already running from line 178
            try:
                self.thread.start()
            except Exception as start_err:
                self.logger.error(f"Failed to start scan thread: {start_err}", exc_info=True)
                raise

            self.main.act_cancel_scan.setEnabled(True)
        except Exception as e:
            self.logger.error(f"Critical error creating scan worker: {e}", exc_info=True)
            self.main.statusBar().showMessage(f"❌ Failed to create scan worker: {e}")
#            from translations import tr

            from translation_manager import tr

            QMessageBox.critical(self.main, tr("messages.scan_error"), tr("messages.scan_error_worker", error=str(e)))
            return

    def cancel(self):
        """Cancel triggered from toolbar."""
        self.cancel_requested = True
        if self.worker:
            try:
                self.worker.stop()
            except Exception:
                pass
#        from translations import tr

        from translation_manager import tr

        self.main.statusBar().showMessage(tr('status_messages.scan_cancel_requested'))
        self.main.act_cancel_scan.setEnabled(False)

    def _on_committed(self, n: int):
        self.main._committed_total += n
        try:
            if self.main._scan_progress:
                cur = self.main._scan_progress.labelText() or ""
                self.main._scan_progress.setLabelText(f"{cur}\nCommitted: {self.main._committed_total} rows")
        except Exception:
            pass

    def _log_progress_event(self, message: str) -> str:
        """Track recent progress lines so the dialog can show contextual history."""
        if not message:
            return "\n".join(self._progress_events)

        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        self._progress_events.append(entry)
        # Keep the most recent handful to avoid bloating the dialog
        self._progress_events = self._progress_events[-8:]
        return "\n".join(self._progress_events)

    def _on_progress(self, pct: int, msg: str):
        """
        Handle progress updates from scan worker thread.

        REVERT TO OLD WORKING VERSION - Simple and reliable.
        """
        if not self.main._scan_progress:
            return

        pct_i = max(0, min(100, int(pct or 0)))
        self.main._scan_progress.setValue(pct_i)

        if msg:
            # Enhanced progress display with file details
            history = self._log_progress_event(msg)
            label = f"{history}\nCommitted: {self.main._committed_total} rows"
        else:
            history = self._log_progress_event("")
            label = f"Progress: {pct_i}%\n{history}\nCommitted: {self.main._committed_total} rows"

        self.main._scan_progress.setLabelText(label)
        self.main._scan_progress.setWindowTitle(f"{tr('messages.scan_dialog_title')} ({pct_i}%)")

        # Check for cancellation (no processEvents — the signal is QueuedConnection
        # so this handler already runs inside the main-thread event loop)
        if self.main._scan_progress.wasCanceled():
            self.cancel()

    def _on_finished(self, folders, photos, videos=0):
        self.logger.info(f"Scan finished: {folders} folders, {photos} photos, {videos} videos")
        self.main._scan_result = (folders, photos, videos)
        summary = (
            f"Scan complete.\n"
            f"Folders: {folders}\n"
            f"Photos: {photos}\n"
            f"Videos: {videos}\n"
            f"Committed rows: {getattr(self.main, '_committed_total', 0)}"
        )

        try:
            if self.main._scan_progress:
                self.main._scan_progress.setValue(100)
                self.main._scan_progress.setLabelText(summary)
                self.main._scan_progress.setWindowTitle(f"{tr('messages.scan_dialog_title')} (100%)")
        except Exception:
            pass

        # Status bar notification instead of blocking QMessageBox
        try:
            self.main.statusBar().showMessage(
                f"Scan complete: {folders} folders, {photos} photos, {videos} videos", 8000
            )
        except Exception:
            pass

    def _on_error(self, err_text: str):
        self.logger.error(f"Scan error: {err_text}")
        try:
#            from translations import tr

            from translation_manager import tr

            QMessageBox.critical(self.main, tr("messages.scan_error"), err_text)
        except Exception:
            QMessageBox.critical(self.main, "Scan Error", err_text)
        if self.thread and self.thread.isRunning():
            self.threa_manager.quit()

    def _cleanup(self):
        """
        Cleanup after scan completes.
        P1-7 FIX: Ensure cleanup runs in main thread to avoid Qt thread violations.
        """
        # P1-7 FIX: Check if we're in the main thread
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        if self.main.thread() != QApplication.instance().thread():
            # Called from worker thread - marshal to main thread
            QTimer.singleShot(0, self._cleanup_impl)
        else:
            # Already in main thread
            self._cleanup_impl()

    def _cleanup_impl(self):
        """Actual cleanup implementation - must run in main thread."""
        try:
            self.main.act_cancel_scan.setEnabled(False)
            if self.main._scan_progress:
                self.main._scan_progress.setValue(100)
                self.main._scan_progress.close()
            if self.db_writer:
                self.db_writer.shutdown(wait=True)
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}", exc_info=True)

        # Get scan results BEFORE heavy operations
        f, p, v = self.main._scan_result if len(self.main._scan_result) == 3 else (*self.main._scan_result, 0)

        # Report post-scan progress via status bar (no modal dialogs)
        from translation_manager import tr
        self.main._scan_complete_msgbox = None  # no blocking msgbox
        self.main.statusBar().showMessage(tr("messages.progress_building_branches"), 0)

        # Lightweight progress tracker (no dialog — just a counter for _finalize_scan_refresh)
        class _ProgressStub:
            """Minimal stub so downstream code that calls progress.setValue/setLabelText/close
            still works but routes everything to the status bar."""
            def __init__(self, status_bar, logger):
                self._bar = status_bar
                self._log = logger
            def setValue(self, v):
                pass
            def setLabelText(self, text):
                try:
                    self._bar.showMessage(text, 0)
                except Exception:
                    pass
            def close(self):
                pass
            def show(self):
                pass

        progress = _ProgressStub(self.main.statusBar(), self.logger)

        # Build date branches after scan completes
        sidebar_was_updated = False
        try:
            progress.setLabelText(tr("messages.progress_building_photo_branches"))
            progress.setValue(1)

            self.logger.info("Building date branches...")
            from reference_db import ReferenceDB
            from app_services import get_default_project_id
            db = ReferenceDB()

            # CRITICAL FIX: Get current project_id to associate scanned photos with correct project
            # Without this, all photos go to project_id=1 regardless of which project is active
            current_project_id = self.main.grid.project_id
            if current_project_id is None:
                self.logger.warning("Grid project_id is None, using default project")
                current_project_id = get_default_project_id()

            if current_project_id is None:
                self.logger.error("No project found! Cannot build date branches.")
                raise ValueError("No project available to associate scanned photos")

            self.logger.info(f"Building date branches for project_id={current_project_id}")
            branch_count = db.build_date_branches(current_project_id)
            self.logger.info(f"Created {branch_count} photo date branch entries for project {current_project_id}")

            # CRITICAL FIX: Build video date branches too (videos need branches like photos!)
            self.logger.info(f"Building video date branches for project_id={current_project_id}")
            video_branch_count = db.build_video_date_branches(current_project_id)
            self.logger.info(f"Created {video_branch_count} video date branch entries for project {current_project_id}")

            progress.setLabelText(tr("messages.progress_backfilling_metadata"))
            progress.setValue(2)

            # CRITICAL: Backfill created_date field immediately after scan
            # This populates created_date from date_taken so get_date_hierarchy() works
            # Without this, the "By Date" section won't appear until app restart
            self.logger.info("Backfilling created_date fields for photos...")
            backfilled = db.single_pass_backfill_created_fields()
            if backfilled:
                self.logger.info(f"Backfilled {backfilled} photo rows with created_date")

            # SURGICAL FIX E: Backfill video created_date fields too
            self.logger.info("Backfilling created_date fields for videos...")
            video_backfilled = db.single_pass_backfill_created_fields_videos()
            if video_backfilled:
                self.logger.info(f"Backfilled {video_backfilled} video rows with created_date")

            # PHASE 3B: Duplicate Detection — dispatched to background thread
            # Instead of blocking the UI with QEventLoop / QProgressDialog,
            # we fire a PostScanPipelineWorker and let it run asynchronously.
            if hasattr(self, '_duplicate_detection_enabled') and self._duplicate_detection_enabled:
                self.logger.info("Enqueueing duplicate detection pipeline as background job...")

                try:
                    from workers.post_scan_pipeline_worker import PostScanPipelineWorker

                    pipeline_options = {
                        "detect_exact": getattr(self, '_detect_exact', False),
                        "detect_similar": getattr(self, '_detect_similar', False),
                        "generate_embeddings": getattr(self, '_generate_embeddings', False),
                        "time_window_seconds": getattr(self, '_time_window_seconds', None),
                        "similarity_threshold": getattr(self, '_similarity_threshold', None),
                        "min_stack_size": getattr(self, '_min_stack_size', None),
                    }

                    self._post_scan_worker = PostScanPipelineWorker(
                        project_id=current_project_id,
                        options=pipeline_options,
                    )

                    # Progress updates go to status bar (non-blocking)
                    def _on_pipeline_progress(step_name, step_num, total, message):
                        try:
                            self.main.statusBar().showMessage(
                                f"[{step_num}/{total}] {message}", 0
                            )
                        except Exception:
                            pass

                    def _on_pipeline_finished(results):
                        errors = results.get("errors", [])
                        exact = results.get("exact_duplicates", 0)
                        similar = results.get("similar_stacks", 0)
                        total = exact + similar

                        if total > 0:
                            parts = []
                            if exact > 0:
                                parts.append(f"{exact} exact duplicate groups")
                            if similar > 0:
                                parts.append(f"{similar} similar shot stacks")
                            self.main.statusBar().showMessage(
                                f"Duplicate detection complete: {', '.join(parts)}", 8000
                            )
                        else:
                            self.main.statusBar().showMessage(
                                "Duplicate detection complete — no duplicates found", 5000
                            )

                        if errors:
                            self.logger.warning("Pipeline completed with errors: %s", errors)

                        # Refresh duplicates section in sidebar
                        self._refresh_duplicates_section()

                    def _on_pipeline_error(msg):
                        self.logger.error("Post-scan pipeline error: %s", msg)
                        self.main.statusBar().showMessage(
                            f"Duplicate detection failed: {msg}", 8000
                        )

                    self._post_scan_worker.signals.progress.connect(_on_pipeline_progress)
                    self._post_scan_worker.signals.finished.connect(_on_pipeline_finished)
                    self._post_scan_worker.signals.error.connect(_on_pipeline_error)

                    QThreadPool.globalInstance().start(self._post_scan_worker)
                    self.logger.info("Post-scan pipeline dispatched to background thread pool")

                except Exception as e:
                    self.logger.error(f"Failed to start post-scan pipeline: {e}", exc_info=True)

            # PHASE 3: Face Detection — dispatched to background thread
            # No modal dialogs, no user confirmation, no QProgressDialog.
            # Runs face detection + clustering as a single background job and
            # reports progress via the status bar.
            try:
                from config.face_detection_config import get_face_config
                face_config = get_face_config()

                if face_config.is_enabled() and face_config.get("auto_cluster_after_scan", True):
                    # Verify backend availability (lightweight check)
                    from services.face_detection_service import FaceDetectionService
                    availability = FaceDetectionService.check_backend_availability()
                    backend = face_config.get_backend()

                    if availability.get(backend, False):
                        self.logger.info("Enqueueing face pipeline as background job (backend=%s)...", backend)

                        from workers.face_pipeline_worker import FacePipelineWorker

                        self._face_pipeline_worker = FacePipelineWorker(
                            project_id=current_project_id,
                            model=face_config.get("model", "buffalo_l"),
                        )

                        def _on_face_progress(step_name, message):
                            try:
                                self.main.statusBar().showMessage(message, 0)
                            except Exception:
                                pass

                        def _on_face_finished(results):
                            faces = results.get("faces_detected", 0)
                            clusters = results.get("clusters_created", 0)
                            errors = results.get("errors", [])

                            if faces > 0:
                                self.main.statusBar().showMessage(
                                    f"Face pipeline complete: {faces} faces, {clusters} clusters", 8000
                                )
                            else:
                                self.main.statusBar().showMessage(
                                    "Face pipeline complete — no faces detected", 5000
                                )

                            if errors:
                                self.logger.warning("Face pipeline errors: %s", errors)

                            # Safely refresh People section
                            self._safe_refresh_people_section()

                        def _on_face_error(msg):
                            self.logger.error("Face pipeline error: %s", msg)
                            self.main.statusBar().showMessage(
                                f"Face pipeline failed: {msg}", 8000
                            )

                        self._face_pipeline_worker.signals.progress.connect(_on_face_progress)
                        self._face_pipeline_worker.signals.finished.connect(_on_face_finished)
                        self._face_pipeline_worker.signals.error.connect(_on_face_error)

                        QThreadPool.globalInstance().start(self._face_pipeline_worker)
                        self.logger.info("Face pipeline dispatched to background thread pool")
                    else:
                        self.logger.warning("Face backend '%s' not available (available: %s)",
                                            backend, [k for k, v in availability.items() if v])
                else:
                    self.logger.debug("Face detection disabled or auto-clustering off")

            except ImportError as e:
                self.logger.debug("Face detection modules not available: %s", e)
            except Exception as e:
                self.logger.error("Face detection setup error: %s", e, exc_info=True)

            # CRITICAL: Update sidebar project_id if it was None (fresh database)
            # The scan creates the first project, so we need to tell the sidebar about it
            if self.main.sidebar.project_id is None:
                self.logger.info("Sidebar project_id was None, updating to default project")
                from app_services import get_default_project_id
                default_pid = get_default_project_id()
                self.logger.debug(f"Setting sidebar project_id to {default_pid}")
                self.main.sidebar.set_project(default_pid)
                if hasattr(self.main.sidebar, "tabs_controller"):
                    self.main.sidebar.tabs_controller.project_id = default_pid
                sidebar_was_updated = True

            # CRITICAL: Also update grid's project_id if it was None
            if self.main.grid.project_id is None:
                self.logger.info("Grid project_id was None, updating to default project")
                from app_services import get_default_project_id
                default_pid = get_default_project_id()
                self.logger.debug(f"Setting grid project_id to {default_pid}")
                self.main.grid.project_id = default_pid
        except Exception as e:
            self.logger.error(f"Error building date branches: {e}", exc_info=True)

        # PHASE 2 Task 2.2: Mark main_scan and date_branches as complete
        # This will check if all operations are done and trigger final refresh
        self._scan_operations_pending.discard("main_scan")
        self._scan_operations_pending.discard("date_branches")
        self._scan_result_cached = (f, p, v, sidebar_was_updated, progress)
        self.logger.info(f"Main scan operations complete. Remaining: {self._scan_operations_pending}")
        self._check_and_trigger_final_refresh()

        # PHASE 2 Task 2.2: OLD refresh_ui() moved to _finalize_scan_refresh()
        # This ensures only ONE refresh happens after ALL async operations complete

    def _safe_refresh_people_section(self):
        """Safely refresh the People section after face pipeline completes.

        Uses try/except to handle cases where widgets may have been
        destroyed since the background job started.
        """
        try:
            # Guard: check main window is still alive
            if not self.main or not hasattr(self.main, 'layout_manager'):
                return

            lm = self.main.layout_manager
            if not lm:
                return

            current_layout_id = lm._current_layout_id
            if current_layout_id == "google":
                current_layout = lm._current_layout
                if current_layout and hasattr(current_layout, 'accordion_sidebar'):
                    accordion = current_layout.accordion_sidebar
                    if hasattr(accordion, 'reload_people_section'):
                        accordion.reload_people_section()
                        self.logger.info("Refreshed people section after face pipeline")
                    if hasattr(current_layout, '_build_people_tree'):
                        current_layout._build_people_tree()
                        self.logger.debug("Refreshed people grid after face pipeline")
            elif hasattr(self.main, 'sidebar') and self.main.sidebar:
                try:
                    if self.main.sidebar.isVisible() and hasattr(self.main.sidebar, 'reload'):
                        self.main.sidebar.reload()
                        self.logger.debug("Refreshed sidebar after face pipeline")
                except RuntimeError:
                    # Widget was deleted — safe to ignore
                    self.logger.debug("Sidebar widget deleted, skipping refresh")
        except Exception as e:
            self.logger.warning("Failed to refresh people section: %s", e)

    def _refresh_duplicates_section(self):
        """Refresh the duplicates section/tab in the sidebar after background pipeline completes."""
        try:
            if hasattr(self.main, 'layout_manager') and self.main.layout_manager:
                current_layout_id = self.main.layout_manager._current_layout_id
                if current_layout_id == "google":
                    current_layout = self.main.layout_manager._current_layout
                    if current_layout and hasattr(current_layout, 'accordion_sidebar'):
                        accordion = current_layout.accordion_sidebar
                        if hasattr(accordion, 'reload_section'):
                            accordion.reload_section("duplicates")
                            self.logger.debug("Refreshed accordion duplicates section after pipeline")
                elif hasattr(self.main.sidebar, "tabs_controller"):
                    tabs = self.main.sidebar.tabs_controller
                    if hasattr(tabs, 'refresh_tab'):
                        tabs.refresh_tab("duplicates")
                        self.logger.debug("Refreshed sidebar duplicates tab after pipeline")
        except Exception as e:
            self.logger.warning(f"Failed to refresh duplicates section after pipeline: {e}")

    def _check_and_trigger_final_refresh(self):
        """
        PHASE 2 Task 2.2: Check if all scan operations are complete.
        If yes, trigger final debounced refresh. If no, wait for other operations.
        """
        if not self._scan_operations_pending and not self._scan_refresh_scheduled:
            self._scan_refresh_scheduled = True
            self.logger.info("✓ All scan operations complete. Triggering final refresh...")
            # Debounce with 100ms delay to ensure all signals propagate
            QTimer.singleShot(100, self._finalize_scan_refresh)
        elif self._scan_operations_pending:
            self.logger.info(f"⏳ Waiting for operations: {self._scan_operations_pending}")

    def _finalize_scan_refresh(self):
        """
        PHASE 2 Task 2.2: Perform ONE coordinated refresh after ALL scan operations complete.
        This replaces the old refresh_ui() function and eliminates duplicate reloads.
        """
        if not self._scan_result_cached:
            self.logger.warning("No cached scan results - cannot refresh")
            return

        f, p, v, sidebar_was_updated, progress = self._scan_result_cached
        self.logger.info("🔄 Starting final coordinated refresh...")

        # Sidebar & grid refresh
        # CRITICAL: Schedule UI updates in main thread (this method may run in worker thread)
        try:
            progress.setLabelText(tr("messages.progress_refreshing_sidebar"))
            progress.setValue(3)

            self.logger.info("Reloading sidebar after date branches built...")
            # CRITICAL FIX: Only reload sidebar if it wasn't just updated via set_project()
            # set_project() already calls reload(), so reloading again causes double refresh crash
            if not sidebar_was_updated:
                # Check which layout is active and reload appropriate sidebar
                if hasattr(self.main, 'layout_manager') and self.main.layout_manager:
                    current_layout_id = self.main.layout_manager._current_layout_id
                    if current_layout_id == "google":
                        # Google Layout uses AccordionSidebar
                        current_layout = self.main.layout_manager._current_layout
                        if current_layout and hasattr(current_layout, 'accordion_sidebar'):
                            self.logger.debug("Reloading AccordionSidebar for Google Layout...")
                            # CRITICAL FIX: Call set_project() to propagate project_id to ALL sections
                            # Simply setting accordion_sidebar.project_id is not enough - must call
                            # set_project() which updates all individual section modules
                            # This ensures that when sections are expanded later, they have valid project_id
                            if hasattr(self.main.grid, 'project_id') and self.main.grid.project_id is not None:
                                self.logger.debug(f"Setting accordion_sidebar project_id to {self.main.grid.project_id}")
                                current_layout.accordion_sidebar.set_project(self.main.grid.project_id)
                                self.logger.debug("AccordionSidebar project_id propagated to all sections")
                            else:
                                self.logger.warning("Cannot set accordion_sidebar project_id - grid.project_id is None")
                    elif hasattr(self.main.sidebar, "reload"):
                        # Current Layout uses old SidebarQt
                        self.main.sidebar.reload()
                        self.logger.debug("Sidebar reload completed (mode-aware)")
                elif hasattr(self.main.sidebar, "reload"):
                    # Fallback to old sidebar if layout manager not available
                    self.main.sidebar.reload()
                    self.logger.debug("Sidebar reload completed (fallback)")
            elif sidebar_was_updated:
                self.logger.debug("Skipping sidebar reload - already updated by set_project()")

            # Phase 3B: Duplicates section refresh is now handled by the
            # PostScanPipelineWorker's finished signal → _refresh_duplicates_section()

        except Exception as e:
            self.logger.error(f"Error reloading sidebar: {e}", exc_info=True)

        # CRITICAL FIX: Always reload grid - needed for Current layout even if Google is active
        try:
            if hasattr(self.main.grid, "reload"):
                self.main.grid.reload()
                self.logger.debug("Grid reload completed")
        except Exception as e:
            self.logger.error(f"Error reloading grid: {e}", exc_info=True)

        try:
            progress.setLabelText(tr("messages.progress_loading_thumbnails"))
            progress.setValue(4)

            # reload thumbnails after scan
            if self.main.thumbnails and hasattr(self.main.grid, "get_visible_paths"):
                self.main.thumbnails.load_thumbnails(self.main.grid.get_visible_paths())

            # CRITICAL FIX: Also refresh Google Photos layout if active
            # This is IN ADDITION to refreshing Current layout above
            # Both layouts are kept in sync after scan
            if hasattr(self.main, 'layout_manager') and self.main.layout_manager:
                current_layout_id = self.main.layout_manager._current_layout_id
                if current_layout_id == "google":
                    self.logger.info("Refreshing Google Photos layout after scan...")
                    current_layout = self.main.layout_manager._current_layout
                    if current_layout and hasattr(current_layout, '_load_photos'):
                        # PHASE 2 Task 2.2: Call directly instead of QTimer.singleShot
                        # All async operations already complete, no need for additional delay
                        current_layout._load_photos()
                        self.logger.info("✓ Google Photos layout refreshed")
        except Exception as e:
            # CRITICAL: Catch ALL exceptions to prevent scan cleanup from failing
            self.logger.error(f"Error refreshing Google Photos layout: {e}", exc_info=True)
            # Don't let layout refresh errors break scan completion

        # Close progress stub / status bar
        try:
            progress.close()
        except Exception as e:
            self.logger.error(f"Error closing progress dialog: {e}")

        # Final status message
        self.main.statusBar().showMessage(f"✓ Scan complete: {p} photos, {v} videos indexed", 5000)
        self.logger.info(f"✅ Final refresh complete: {p} photos, {v} videos")

        # PHASE 2 Task 2.2: Reset state for next scan
        self._scan_refresh_scheduled = False
        self._scan_result_cached = None

        # Note: Video metadata worker callback is now connected at worker creation time
        # in start_scan() to avoid race conditions with worker finishing before cleanup runs

    @Slot(int, str)
    def _on_stacks_updated(self, project_id: int, stack_type: str):
        """
        ✅ CRITICAL FIX: Handle stack updates from StackGenerationService.
        
        Called when stack operations complete to refresh UI components
        displaying stack badges to prevent "Stack not found" errors.
        
        Args:
            project_id: Project ID where stacks were updated
            stack_type: Type of stacks that were updated (similar, near_duplicate, etc.)
        """
        self.logger.info(f"Stacks updated notification received: project={project_id}, type={stack_type}")
        
        try:
            # Refresh current layout to update stack badges
            if hasattr(self.main, 'layout_manager') and self.main.layout_manager:
                current_layout = self.main.layout_manager._current_layout
                if current_layout and hasattr(current_layout, 'refresh_after_scan'):
                    self.logger.info("Refreshing current layout to update stack badges...")
                    current_layout.refresh_after_scan()
                    self.logger.info("✓ Layout refreshed with updated stack data")
                else:
                    # Fallback: refresh sidebar and grid directly
                    self.logger.info("Refreshing sidebar and grid to update stack badges...")
                    if hasattr(self.main.sidebar, "reload"):
                        self.main.sidebar.reload()
                    if hasattr(self.main.grid, "reload"):
                        self.main.grid.reload()
                    self.logger.info("✓ Sidebar and grid refreshed with updated stack data")
            else:
                # Legacy fallback
                self.logger.info("Refreshing legacy components to update stack badges...")
                if hasattr(self.main.sidebar, "reload"):
                    self.main.sidebar.reload()
                if hasattr(self.main.grid, "reload"):
                    self.main.grid.reload()
                self.logger.info("✓ Legacy components refreshed with updated stack data")
                
        except Exception as e:
            self.logger.error(f"Error refreshing UI after stack updates: {e}", exc_info=True)


