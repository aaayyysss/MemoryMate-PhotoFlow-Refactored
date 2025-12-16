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

Version: 09.20.00.00
"""

import logging
from datetime import datetime
from typing import List
from PySide6.QtCore import QThread, Qt, QTimer, QThreadPool
from PySide6.QtWidgets import (
    QProgressDialog, QMessageBox, QDialog, QVBoxLayout,
    QLabel, QProgressBar, QApplication
)
#from translations import tr
from translation_manager import tr


class ScanController:
    """
    Wraps scan orchestration: start, cancel, cleanup, progress wiring.
    Keeps MainWindow slimmer.
    """
    def __init__(self, main):
        self.main = main
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

    def start_scan(self, folder, incremental: bool):
        """Entry point called from MainWindow toolbar action."""
        self.cancel_requested = False
        self.main.statusBar().showMessage(f"📸 Scanning repository: {folder} (incremental={incremental})")
        self.main._committed_total = 0

        # PHASE 2 Task 2.2: Initialize pending operations tracker
        # Main scan will mark these complete as each operation finishes
        self._scan_operations_pending = {"main_scan", "date_branches"}
        self._scan_refresh_scheduled = False
        self._scan_result_cached = None
        self._progress_events = []

        # Progress dialog - REVERT TO OLD WORKING VERSION
        # Create and show dialog IMMEDIATELY (no threshold, no lazy creation)
        # This is simpler and avoids Qt threading issues
        from translation_manager import tr
        self.main._scan_progress = QProgressDialog(
            tr("messages.scan_preparing"),
            tr("messages.scan_cancel_button"),
            0, 100, self.main
        )
        self.main._scan_progress.setWindowTitle(tr("messages.scan_dialog_title"))
        self.main._scan_progress.setWindowModality(Qt.WindowModal)
        self.main._scan_progress.setAutoClose(False)
        self.main._scan_progress.setAutoReset(False)
        self.main._scan_progress.setMinimumDuration(0)  # CRITICAL: Show immediately, no timer delay (prevents Qt timer thread errors)
        self.main._scan_progress.setMinimumWidth(520)
        self.main._scan_progress.show()

        # DB writer
        # NOTE: Schema creation handled automatically by repository layer
        from db_writer import DBWriter
        self.db_writer = DBWriter(batch_size=200, poll_interval_ms=150)
        self.db_writer.error.connect(lambda msg: print(f"[DBWriter] {msg}"))
        self.db_writer.committed.connect(self._on_committed)
        self.db_writer.start()

        # CRITICAL: Initialize database schema before starting scan
        # This ensures the repository layer has created all necessary tables
        try:
            from repository.base_repository import DatabaseConnection
            db_conn = DatabaseConnection("reference_data.db", auto_init=True)
            print("[Schema] Database schema initialized successfully")
        except Exception as e:
            print(f"[Schema] ERROR: Failed to initialize database schema: {e}")
            import traceback
            traceback.print_exc()
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
            print(f"[ScanController] Using project_id: {current_project_id}")

        # Scan worker
        try:
            print(f"[ScanController] Creating ScanWorker for folder: {folder}")
            from services.scan_worker_adapter import ScanWorkerAdapter as ScanWorker
            print(f"[ScanController] ScanWorker imported successfully")

            self.thread = QThread(self.main)
            print(f"[ScanController] QThread created")

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

            self.worker = ScanWorker(folder, current_project_id, incremental, self.main.settings,
                                    db_writer=self.db_writer,
                                    on_video_metadata_finished=on_video_metadata_finished)
            print(f"[ScanController] ScanWorker instance created with project_id={current_project_id}")

            self.worker.moveToThread(self.thread)
            print(f"[ScanController] Worker moved to thread")

            # CRITICAL FIX: Use Qt.QueuedConnection explicitly to prevent deadlock
            # When progress is emitted from worker thread via synchronous callback,
            # we need to ensure the emit() returns immediately without blocking
            self.worker.progress.connect(self._on_progress, Qt.QueuedConnection)
            self.worker.finished.connect(self._on_finished, Qt.QueuedConnection)
            self.worker.error.connect(self._on_error, Qt.QueuedConnection)
            self.thread.started.connect(lambda: print("[ScanController] QThread STARTED!"))
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(lambda f, p, v=0: self.thread.quit())
            self.thread.finished.connect(self._cleanup)
            print(f"[ScanController] Signals connected")

            # Start scan thread immediately - DBWriter is already running from line 178
            print("[ScanController] Starting scan thread...")
            self.thread.start()
            print("[ScanController] thread.start() called")

            self.main.act_cancel_scan.setEnabled(True)
        except Exception as e:
            print(f"[ScanController] CRITICAL ERROR creating scan worker: {e}")
            import traceback
            traceback.print_exc()
            self.main.statusBar().showMessage(f"❌ Failed to create scan worker: {e}")
            from translations import tr
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
        from translations import tr
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
        QApplication.processEvents()

        # Check for cancellation
        if self.main._scan_progress.wasCanceled():
            self.cancel()

    def _on_finished(self, folders, photos, videos=0):
        print(f"[ScanController] scan finished: {folders} folders, {photos} photos, {videos} videos")
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

        try:
            title = tr("messages.scan_complete") if callable(tr) else "Scan complete"
            QMessageBox.information(self.main, title, summary)
        except Exception:
            pass

    def _on_error(self, err_text: str):
        try:
            from translations import tr
            QMessageBox.critical(self.main, tr("messages.scan_error"), err_text)
        except Exception:
            print(f"[ScanController] {err_text}")
        if self.thread and self.thread.isRunning():
            self.thread.quit()

    def _cleanup(self):
        """
        Cleanup after scan completes.
        P1-7 FIX: Ensure cleanup runs in main thread to avoid Qt thread violations.
        """
        print("[ScanController] cleanup after scan")
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

        # Show completion message IMMEDIATELY (before heavy operations)
        # This prevents UI freeze perception and gives user feedback
        msg = f"Indexed {p} photos"
        if v > 0:
            msg += f" and {v} videos"
        msg += f" in {f} folders.\n\n"
        msg += "📊 Processing metadata and updating views...\nThis may take a few seconds."

        # CRITICAL FIX: Create and show message box explicitly, then close it properly
        # Using QMessageBox.information() can cause issues with multiple scans
        #from translations import tr
        from translation_manager import tr
        msgbox = QMessageBox(self.main)
        msgbox.setWindowTitle(tr("messages.scan_complete_title"))
        msgbox.setText(msg)
        msgbox.setIcon(QMessageBox.Information)
        msgbox.setStandardButtons(QMessageBox.Ok)
        msgbox.setModal(True)
        msgbox.show()
        QApplication.processEvents()

        # Store reference to close it later
        self.main._scan_complete_msgbox = msgbox

        # Show progress indicator for post-scan processing
        progress = QProgressDialog(tr("messages.progress_building_branches"), None, 0, 4, self.main)
        progress.setWindowTitle(tr("messages.progress_processing"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setAutoClose(True)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        # Build date branches after scan completes
        sidebar_was_updated = False
        try:
            progress.setLabelText(tr("messages.progress_building_photo_branches"))
            progress.setValue(1)
            QApplication.processEvents()

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
            QApplication.processEvents()

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

            # PHASE 3: Face Detection Integration (Optional Post-Scan Step)
            # Check if face detection is enabled in configuration
            try:
                # NOTE: QMessageBox is already imported at module level (line 64)
                # Do NOT re-import here as it makes QMessageBox a local variable
                from config.face_detection_config import get_face_config
                face_config = get_face_config()

                if face_config.is_enabled() and face_config.get("auto_cluster_after_scan", True):
                    self.logger.info("Face detection is enabled - starting face detection worker...")

                    # Check if backend is available
                    from services.face_detection_service import FaceDetectionService
                    availability = FaceDetectionService.check_backend_availability()
                    backend = face_config.get_backend()

                    if availability.get(backend, False):
                        # Ask user for confirmation if required
                        if face_config.get("require_confirmation", True):
                            reply = QMessageBox.question(
                                self.main,
                                "Face Detection",
                                f"Scan completed!\n\nWould you like to detect faces in the scanned images?\n\n"
                                f"Backend: {backend}\n"
                                f"This may take a few minutes depending on the number of images.",
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.Yes
                            )

                            if reply != QMessageBox.Yes:
                                self.logger.info("User declined face detection")
                                face_detection_enabled = False
                            else:
                                face_detection_enabled = True
                        else:
                            face_detection_enabled = True

                        if face_detection_enabled:
                            self.logger.info(f"Starting face detection with backend: {backend}")

                            # CRITICAL FIX: Show progress dialog to prevent frozen UI appearance
                            # Create non-modal progress dialog
                            # Note: All required widgets already imported at module level

                            progress_dialog = QDialog(self.main)
                            progress_dialog.setWindowTitle(tr("messages.progress_processing_photos"))
                            progress_dialog.setModal(False)  # Non-modal allows UI to stay responsive
                            progress_dialog.setMinimumWidth(500)
                            progress_dialog.setWindowFlags(
                                progress_dialog.windowFlags() & ~Qt.WindowCloseButtonHint
                            )

                            layout = QVBoxLayout()
                            status_label = QLabel("Initializing face detection...")
                            status_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
                            progress_bar = QProgressBar()
                            progress_bar.setMinimum(0)
                            progress_bar.setMaximum(100)
                            progress_bar.setValue(0)
                            detail_label = QLabel("Please wait...")
                            detail_label.setWordWrap(True)

                            layout.addWidget(status_label)
                            layout.addWidget(progress_bar)
                            layout.addWidget(detail_label)
                            progress_dialog.setLayout(layout)

                            # Show dialog immediately
                            progress_dialog.show()
                            QApplication.processEvents()  # Force UI update

                            # Run face detection worker
                            from workers.face_detection_worker import FaceDetectionWorker
                            face_worker = FaceDetectionWorker(current_project_id)

                            # Connect progress signals to update dialog
                            def update_progress(current, total, filename):
                                percent = int((current / total) * 80) if total > 0 else 0  # 80% for detection
                                progress_bar.setValue(percent)
                                status_label.setText(tr("messages.progress_detecting_faces", current=current, total=total))
                                detail_label.setText(tr("messages.progress_processing_file", filename=filename))
                                QApplication.processEvents()

                            face_worker.signals.progress.connect(update_progress)

                            # Update initial status
                            status_label.setText(tr("messages.progress_loading_models"))
                            detail_label.setText(tr("messages.progress_models_first_run"))
                            QApplication.processEvents()

                            # CRITICAL FIX: Run face detection asynchronously using QThreadPool
                            # DO NOT call face_worker.run() directly - it blocks the main thread!

                            def on_face_detection_finished(success_count, failed_count, total_faces):
                                """Handle face detection completion"""
                                try:
                                    self.logger.info(f"Face detection completed: {total_faces} faces detected in {success_count} images")

                                    # Update for clustering phase
                                    if face_config.get("clustering_enabled", True) and total_faces > 0:
                                        progress_bar.setValue(85)
                                        status_label.setText(tr("messages.progress_grouping_faces"))
                                        detail_label.setText(tr("messages.progress_clustering_faces", total_faces=total_faces))
                                        QApplication.processEvents()

                                        self.logger.info("Starting face clustering...")

                                        from workers.face_cluster_worker import cluster_faces
                                        cluster_params = face_config.get_clustering_params()

                                        # CRITICAL FIX: Run clustering asynchronously to avoid UI freeze
                                        # DO NOT call cluster_faces() directly - it blocks during DBSCAN computation!

                                        def run_clustering_async():
                                            """Run clustering in background thread"""
                                            try:
                                                cluster_faces(
                                                    current_project_id,
                                                    eps=cluster_params["eps"],
                                                    min_samples=cluster_params["min_samples"]
                                                )
                                                self.logger.info("Face clustering completed")
                                            except Exception as e:
                                                self.logger.error(f"Error during clustering: {e}", exc_info=True)

                                        def on_clustering_finished():
                                            """Handle clustering completion on main thread"""
                                            try:
                                                # Final update
                                                progress_bar.setValue(100)
                                                status_label.setText(tr("messages.progress_complete"))
                                                detail_label.setText(tr("messages.progress_faces_found", total_faces=total_faces, success_count=success_count))
                                                QApplication.processEvents()

                                                # CRITICAL FIX: Refresh Google Photos layout People grid after clustering
                                                # Without this, user must manually toggle layouts to see faces
                                                self.logger.info("Refreshing People grid after face clustering...")
                                                try:
                                                    if hasattr(self.main, 'layout_manager') and self.main.layout_manager:
                                                        current_layout_id = self.main.layout_manager._current_layout_id
                                                        if current_layout_id == "google":
                                                            current_layout = self.main.layout_manager._current_layout
                                                            if current_layout and hasattr(current_layout, '_build_people_tree'):
                                                                # Refresh People grid with newly clustered faces
                                                                current_layout._build_people_tree()
                                                                self.logger.info("✓ People grid refreshed with detected faces")
                                                except Exception as refresh_err:
                                                    self.logger.error(f"Failed to refresh People grid: {refresh_err}", exc_info=True)

                                                # Close dialog after short delay
                                                QTimer.singleShot(1500, progress_dialog.accept)
                                            except Exception as e:
                                                self.logger.error(f"Error in clustering completion handler: {e}", exc_info=True)
                                                progress_dialog.accept()

                                        # Run clustering in thread pool (NON-BLOCKING!)
                                        from PySide6.QtCore import QRunnable, QThreadPool, pyqtSignal, QObject

                                        class ClusterSignals(QObject):
                                            finished = pyqtSignal()

                                        class ClusterRunnable(QRunnable):
                                            def __init__(self, cluster_func):
                                                super().__init__()
                                                self.cluster_func = cluster_func
                                                self.signals = ClusterSignals()

                                            def run(self):
                                                self.cluster_func()
                                                self.signals.finished.emit()

                                        cluster_runnable = ClusterRunnable(run_clustering_async)
                                        cluster_runnable.signals.finished.connect(on_clustering_finished)
                                        QThreadPool.globalInstance().start(cluster_runnable)

                                    else:
                                        # No clustering needed, finish immediately
                                        progress_bar.setValue(100)
                                        status_label.setText(tr("messages.progress_complete"))
                                        detail_label.setText(tr("messages.progress_faces_found", total_faces=total_faces, success_count=success_count))
                                        QApplication.processEvents()

                                        # Close dialog after short delay
                                        QTimer.singleShot(1500, progress_dialog.accept)

                                except Exception as e:
                                    self.logger.error(f"Error in face detection completion handler: {e}", exc_info=True)
                                    progress_dialog.accept()

                            # Connect finished signal
                            face_worker.signals.finished.connect(on_face_detection_finished)

                            # Run asynchronously in background thread (NON-BLOCKING!)
                            QThreadPool.globalInstance().start(face_worker)
                    else:
                        self.logger.warning(f"Face detection backend '{backend}' is not available")
                        self.logger.warning(f"Available backends: {[k for k, v in availability.items() if v]}")
                else:
                    self.logger.debug("Face detection is disabled or auto-clustering is off")

            except ImportError as e:
                self.logger.debug(f"Face detection modules not available: {e}")
            except Exception as e:
                self.logger.error(f"Face detection error: {e}", exc_info=True)
                # Don't fail the entire scan if face detection fails
                QMessageBox.warning(
                    self.main,
                    "Face Detection Error",
                    f"Face detection failed:\n{str(e)}\n\nThe scan completed successfully, but faces were not detected."
                )

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
            QApplication.processEvents()

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
                            current_layout.accordion_sidebar.reload_all_sections()
                            self.logger.debug("AccordionSidebar reload completed")
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
            QApplication.processEvents()

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

        # CRITICAL FIX: Close scan completion message box if still open
        try:
            if hasattr(self.main, '_scan_complete_msgbox') and self.main._scan_complete_msgbox:
                self.main._scan_complete_msgbox.close()
                self.main._scan_complete_msgbox.deleteLater()
                self.main._scan_complete_msgbox = None
        except Exception as e:
            self.logger.error(f"Error closing scan message box: {e}")

        # Close progress dialog
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


