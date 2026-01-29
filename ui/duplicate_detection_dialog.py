# duplicate_detection_dialog.py
# Version 1.01.00.00 dated 20260129

"""
Duplicate Detection Dialog
Professional dialog for configuring and running duplicate detection.

Design follows best practices from:
- Google Photos: Clean interface, smart defaults, progressive disclosure
- Lightroom: Professional workflow with clear parameter controls
- iPhone Photos: Simple yet powerful, clear visual hierarchy

Unified dialog for both menu and toolbar access.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QGroupBox, QSpinBox, QDoubleSpinBox, QRadioButton,
    QButtonGroup, QFrame, QProgressBar, QMessageBox, QWidget
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QFont
from typing import Optional, List
import time

from services.library_detector import check_system_readiness
from repository.asset_repository import AssetRepository
from repository.photo_repository import PhotoRepository
from repository.video_repository import VideoRepository
from services.embedding_service import EmbeddingService
from services.job_service import JobService
from ui.embedding_scope_widget import EmbeddingScopeWidget
from logging_config import get_logger

logger = get_logger(__name__)


class DuplicateDetectionWorker(QObject):
    """Background worker for duplicate detection."""

    progress_updated = Signal(int, str)  # percentage, message
    finished = Signal(dict)  # results
    error = Signal(str)

    def __init__(self, project_id: int, options: dict, photo_ids: Optional[List[int]] = None):
        super().__init__()
        self.project_id = project_id
        self.options = options
        self.photo_ids = photo_ids  # If None, process all photos
        self._running = True

    def run(self):
        """Run duplicate detection process."""
        try:
            results = {
                'exact_duplicates': 0,
                'similar_stacks': 0,
                'photos_processed': 0,
                'embeddings_generated': 0,
                'scope': self.options.get('scope_description', 'All photos')
            }

            total_steps = 0
            current_step = 0

            # Determine photo count for progress estimation
            if self.photo_ids:
                photo_count = len(self.photo_ids)
            else:
                photo_repo = PhotoRepository()
                photo_count = photo_repo.count_photos_in_project(self.project_id)

            results['photos_processed'] = photo_count

            # Step 1: Exact duplicate detection
            if self.options.get('detect_exact', False):
                total_steps += 1

            # Step 2: Embedding generation
            if self.options.get('generate_embeddings', False):
                total_steps += max(1, photo_count // 50)  # Batches of 50

            # Step 3: Similar detection
            if self.options.get('detect_similar', False):
                total_steps += 2

            if total_steps == 0:
                total_steps = 1  # Prevent division by zero

            # Execute steps
            if self.options.get('detect_exact', False):
                if not self._running:
                    return
                self.progress_updated.emit(
                    int((current_step / total_steps) * 100),
                    "Finding exact duplicates..."
                )

                asset_repo = AssetRepository()
                # Pass photo_ids if we have a specific scope
                if self.photo_ids:
                    exact_count = asset_repo.find_exact_duplicates_for_photos(
                        self.project_id, self.photo_ids
                    ) if hasattr(asset_repo, 'find_exact_duplicates_for_photos') else \
                        asset_repo.find_exact_duplicates(self.project_id)
                else:
                    exact_count = asset_repo.find_exact_duplicates(self.project_id)
                results['exact_duplicates'] = exact_count or 0
                current_step += 1

            # Generate embeddings if requested
            if self.options.get('generate_embeddings', False):
                if not self._running:
                    return
                self.progress_updated.emit(
                    int((current_step / total_steps) * 100),
                    "Generating AI embeddings..."
                )

                embedding_service = EmbeddingService()
                try:
                    # Load model
                    model_id = embedding_service.load_clip_model()

                    # Get photos to process
                    photo_repo = PhotoRepository()
                    if self.photo_ids:
                        # Get photo details for specified IDs
                        photos = photo_repo.get_photos_by_ids(self.photo_ids)
                        # Filter to only those needing embeddings if not forcing regeneration
                        if not self.options.get('force_regenerate', False):
                            photos_needing = photo_repo.get_photos_needing_embeddings(
                                self.project_id, limit=10000
                            )
                            needed_ids = {p.get('photo_id') or p.get('id') for p in photos_needing}
                            photos = [p for p in photos if (p.get('photo_id') or p.get('id')) in needed_ids]
                    else:
                        photos = photo_repo.get_photos_needing_embeddings(self.project_id, limit=10000)

                    batch_size = 50
                    total_photos = len(photos)

                    for i in range(0, total_photos, batch_size):
                        if not self._running:
                            return

                        batch = photos[i:i + batch_size]
                        for photo in batch:
                            try:
                                file_path = photo.get('file_path') or photo.get('path')
                                photo_id = photo.get('photo_id') or photo.get('id')
                                if not file_path or not photo_id:
                                    logger.warning(f"Photo missing file_path or id: {photo}")
                                    continue
                                embedding = embedding_service.extract_image_embedding(file_path)
                                embedding_service.store_embedding(
                                    photo_id, embedding, model_id
                                )
                                results['embeddings_generated'] += 1
                            except Exception as e:
                                photo_id = photo.get('photo_id') or photo.get('id')
                                logger.warning(f"Failed to process photo {photo_id}: {e}")

                        current_step += 1
                        progress = min(95, int((current_step / total_steps) * 100))
                        processed = results['embeddings_generated']
                        self.progress_updated.emit(
                            progress,
                            f"Generated embeddings: {processed:,}/{total_photos:,}"
                        )

                except Exception as e:
                    logger.error(f"Embedding generation failed: {e}")
                    self.error.emit(f"Embedding generation failed: {e}")
                    return

            # Similar detection
            if self.options.get('detect_similar', False):
                if not self._running:
                    return
                self.progress_updated.emit(
                    int((current_step / total_steps) * 100),
                    "Finding similar shots..."
                )

                # Use similar shot detection with specified photo IDs
                try:
                    from services.stack_generation_service import StackGenerationService
                    from repository.stack_repository import StackRepository
                    from services.semantic_embedding_service import SemanticEmbeddingService

                    stack_repo = StackRepository()
                    embedding_svc = SemanticEmbeddingService()
                    stack_svc = StackGenerationService(photo_repo, stack_repo, embedding_svc)

                    threshold = self.options.get('similarity_threshold', 0.85)
                    time_window = self.options.get('time_window_seconds', 30)

                    if self.photo_ids:
                        similar_count = stack_svc.generate_stacks_for_photos(
                            self.project_id,
                            self.photo_ids,
                            similarity_threshold=threshold,
                            time_window_seconds=time_window
                        )
                    else:
                        similar_count = stack_svc.generate_stacks(
                            self.project_id,
                            similarity_threshold=threshold,
                            time_window_seconds=time_window
                        )

                    results['similar_stacks'] = similar_count or 0
                except Exception as e:
                    logger.warning(f"Similar detection service not available: {e}")
                    results['similar_stacks'] = 0

                current_step += 2

            self.progress_updated.emit(100, "Detection complete!")
            self.finished.emit(results)

        except Exception as e:
            logger.error(f"Duplicate detection failed: {e}")
            self.error.emit(str(e))


class DuplicateDetectionDialog(QDialog):
    """
    Professional duplicate detection dialog with clean Google/iPhone-inspired design.

    Features:
    - Exact duplicate detection (hash-based)
    - Similar shot detection (AI-powered)
    - Scope selection (all/folders/dates/recent/quantity)
    - Configurable parameters
    - Real-time progress
    - System readiness checking
    """

    def __init__(self, project_id: int, parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.worker_thread = None
        self.worker = None
        self.selected_photo_ids: List[int] = []

        self.setWindowTitle("🔍 Duplicate Detection - Select Scope")
        self.setModal(True)
        self.resize(720, 680)

        self._build_ui()
        self._connect_signals()
        self._check_system_readiness()

    def _build_ui(self):
        """Build dialog UI with clean, professional design."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # === HEADER ===
        title = QLabel("Find Duplicates & Similar Photos")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; color: #333; padding-bottom: 4px;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Detect exact duplicates and visually similar photos in your collection. "
            "Select which photos to scan and configure detection settings."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #666; font-size: 10pt; padding-bottom: 8px;")
        layout.addWidget(subtitle)

        # Separator
        self._add_separator(layout)

        # === SCOPE SELECTION ===
        self.scope_widget = EmbeddingScopeWidget(self.project_id, self)
        self.scope_widget.scopeChanged.connect(self._on_scope_changed)
        layout.addWidget(self.scope_widget)

        # Separator
        self._add_separator(layout)

        # === DETECTION METHODS ===
        methods_group = QGroupBox("🔍 Detection Methods")
        methods_group.setStyleSheet(self._groupbox_style())
        methods_layout = QVBoxLayout(methods_group)
        methods_layout.setSpacing(10)

        # Exact duplicates
        self.chk_exact = QCheckBox("Exact Duplicates (Fast)")
        self.chk_exact.setChecked(True)
        self.chk_exact.setToolTip(
            "Find photos with identical content using SHA256 hashing.\n"
            "Very fast, catches perfect copies and backups."
        )
        self.chk_exact.setStyleSheet("font-weight: bold;")
        methods_layout.addWidget(self.chk_exact)

        exact_desc = QLabel("Identical file content - No false positives")
        exact_desc.setStyleSheet("color: #888; font-size: 9pt; margin-left: 24px; margin-bottom: 8px;")
        methods_layout.addWidget(exact_desc)

        # Similar shots
        self.chk_similar = QCheckBox("Similar Shots (AI-Powered)")
        self.chk_similar.setToolTip(
            "Find visually similar photos using AI embeddings.\n"
            "Catches burst shots, edited versions, and similar compositions."
        )
        self.chk_similar.setStyleSheet("font-weight: bold;")
        methods_layout.addWidget(self.chk_similar)

        similar_desc = QLabel("Visually similar content - May have false positives")
        similar_desc.setStyleSheet("color: #888; font-size: 9pt; margin-left: 24px;")
        methods_layout.addWidget(similar_desc)

        layout.addWidget(methods_group)

        # === ADVANCED SETTINGS (collapsible feel) ===
        settings_group = QGroupBox("⚙️ Advanced Settings")
        settings_group.setStyleSheet(self._groupbox_style())
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(10)

        # Generate embeddings checkbox
        self.chk_generate_embeddings = QCheckBox("Generate AI Embeddings (required for similar detection)")
        self.chk_generate_embeddings.setToolTip(
            "Extract visual embeddings using CLIP model.\n"
            "Takes 2-5 seconds per photo depending on hardware."
        )
        settings_layout.addWidget(self.chk_generate_embeddings)

        # Sensitivity settings container
        self.sensitivity_widget = QWidget()
        sensitivity_layout = QHBoxLayout(self.sensitivity_widget)
        sensitivity_layout.setContentsMargins(0, 8, 0, 0)
        sensitivity_layout.setSpacing(20)

        # Similarity threshold
        sim_container = QHBoxLayout()
        sim_container.addWidget(QLabel("Similarity:"))
        self.spin_similarity = QDoubleSpinBox()
        self.spin_similarity.setRange(0.50, 0.99)
        self.spin_similarity.setSingleStep(0.05)
        self.spin_similarity.setValue(0.85)
        self.spin_similarity.setToolTip("Minimum visual similarity (0.50-0.99)")
        self.spin_similarity.setFixedWidth(70)
        sim_container.addWidget(self.spin_similarity)
        sensitivity_layout.addLayout(sim_container)

        # Time window
        time_container = QHBoxLayout()
        time_container.addWidget(QLabel("Time Window:"))
        self.spin_time_window = QSpinBox()
        self.spin_time_window.setRange(5, 120)
        self.spin_time_window.setValue(30)
        self.spin_time_window.setSuffix("s")
        self.spin_time_window.setToolTip("Compare photos taken within this time period")
        self.spin_time_window.setFixedWidth(70)
        time_container.addWidget(self.spin_time_window)
        sensitivity_layout.addLayout(time_container)

        sensitivity_layout.addStretch()
        settings_layout.addWidget(self.sensitivity_widget)

        layout.addWidget(settings_group)

        # === SYSTEM STATUS ===
        status_group = QGroupBox("📊 System Status")
        status_group.setStyleSheet(self._groupbox_style())
        self.status_group = status_group
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel("Checking system...")
        self.status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.status_label)

        self.status_detail = QLabel("")
        self.status_detail.setWordWrap(True)
        self.status_detail.setStyleSheet("color: #666; font-size: 9pt;")
        status_layout.addWidget(self.status_detail)

        layout.addWidget(status_group)

        # === PROGRESS (hidden initially) ===
        self.progress_group = QGroupBox("⏳ Progress")
        self.progress_group.setStyleSheet(self._groupbox_style())
        self.progress_group.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                text-align: center;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #1a73e8;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("Ready to start...")
        self.progress_label.setStyleSheet("color: #666;")
        progress_layout.addWidget(self.progress_label)

        layout.addWidget(self.progress_group)

        # Add stretch
        layout.addStretch()

        # === BUTTONS ===
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        # Help/info button (left side)
        help_btn = QPushButton("ℹ️ Help")
        help_btn.setStyleSheet(self._secondary_button_style())
        help_btn.clicked.connect(self._show_help)
        button_layout.addWidget(help_btn)

        button_layout.addStretch()

        # Cancel button
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet(self._secondary_button_style())
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)

        # Start button
        self.btn_start = QPushButton("▶ Start Detection")
        self.btn_start.setStyleSheet(self._primary_button_style())
        self.btn_start.clicked.connect(self._start_detection)
        button_layout.addWidget(self.btn_start)

        layout.addLayout(button_layout)

    def _add_separator(self, layout):
        """Add a subtle separator line."""
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #e0e0e0; max-height: 1px;")
        layout.addWidget(sep)

    def _groupbox_style(self) -> str:
        """Return consistent GroupBox styling."""
        return """
            QGroupBox {
                font-weight: bold;
                font-size: 10pt;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 12px;
                padding: 12px;
                padding-top: 24px;
                background-color: #fafafa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 4px 12px;
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """

    def _primary_button_style(self) -> str:
        """Return primary button styling (blue)."""
        return """
            QPushButton {
                background-color: #1a73e8;
                color: white;
                padding: 10px 24px;
                font-weight: bold;
                font-size: 10pt;
                border: none;
                border-radius: 6px;
                min-width: 140px;
            }
            QPushButton:hover {
                background-color: #1557b0;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #888;
            }
        """

    def _secondary_button_style(self) -> str:
        """Return secondary button styling (outlined)."""
        return """
            QPushButton {
                background-color: white;
                color: #333;
                padding: 10px 20px;
                font-weight: normal;
                font-size: 10pt;
                border: 1px solid #ddd;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border-color: #ccc;
            }
            QPushButton:pressed {
                background-color: #e8e8e8;
            }
        """

    def _connect_signals(self):
        """Connect signals."""
        self.chk_similar.toggled.connect(self._on_similar_toggled)
        self.chk_generate_embeddings.toggled.connect(self._on_embedding_toggled)

        # Initial state
        self._on_similar_toggled(self.chk_similar.isChecked())

    def _on_scope_changed(self, photo_ids: List[int], count: int):
        """Handle scope selection change from widget."""
        self.selected_photo_ids = photo_ids
        logger.debug(f"Scope changed: {count} photos selected")

    def _check_system_readiness(self):
        """Check system readiness and update UI."""
        ready, summary, recommendations = check_system_readiness()

        self.status_label.setText(summary)

        if ready:
            self.status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
            self.status_detail.setText("✓ System ready for duplicate detection")
            self.status_detail.setStyleSheet("color: #2e7d32;")
            self.btn_start.setEnabled(True)
        else:
            self.status_label.setStyleSheet("color: #c62828; font-weight: bold;")
            rec_text = " | ".join(recommendations[:2]) if recommendations else "System check failed"
            self.status_detail.setText(f"⚠ {rec_text}")
            self.status_detail.setStyleSheet("color: #c62828;")
            self.btn_start.setEnabled(False)

    def _on_similar_toggled(self, checked: bool):
        """Handle similar detection toggle."""
        self.chk_generate_embeddings.setEnabled(checked)
        self.sensitivity_widget.setEnabled(checked)

        if checked and not self.chk_generate_embeddings.isChecked():
            self.chk_generate_embeddings.setChecked(True)

    def _on_embedding_toggled(self, checked: bool):
        """Handle embedding generation toggle."""
        if not checked and self.chk_similar.isChecked():
            reply = QMessageBox.question(
                self,
                "Disable Embeddings?",
                "Disabling embedding generation will prevent similar shot detection.\n\n"
                "Continue anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                self.chk_generate_embeddings.setChecked(True)

    def _show_help(self):
        """Show help information."""
        QMessageBox.information(
            self,
            "Duplicate Detection Help",
            "<b>Exact Duplicates</b><br>"
            "Finds identical photos using file content hashing (SHA256). "
            "Very fast and has zero false positives.<br><br>"
            "<b>Similar Shots</b><br>"
            "Uses AI (CLIP) to find visually similar photos like burst shots, "
            "edited versions, or similar compositions. Requires embeddings.<br><br>"
            "<b>Tips:</b><br>"
            "• Start with 'Exact Duplicates' for quick results<br>"
            "• Use 'Similar Shots' for burst photography cleanup<br>"
            "• Lower similarity threshold = more aggressive grouping<br>"
            "• Time window helps group burst shots taken within seconds"
        )

    def _start_detection(self):
        """Start duplicate detection process."""
        # Validate options
        if not self.chk_exact.isChecked() and not self.chk_similar.isChecked():
            QMessageBox.warning(
                self,
                "No Detection Method",
                "Please select at least one detection method:\n\n"
                "• Exact Duplicates\n"
                "• Similar Shots"
            )
            return

        # Get selected photo IDs from scope widget
        photo_ids = self.scope_widget.get_selected_photo_ids()

        if not photo_ids:
            QMessageBox.warning(
                self,
                "No Photos Selected",
                "Please select photos to scan using the options above."
            )
            return

        # Prepare options
        options = {
            'detect_exact': self.chk_exact.isChecked(),
            'detect_similar': self.chk_similar.isChecked(),
            'generate_embeddings': self.chk_generate_embeddings.isChecked(),
            'similarity_threshold': self.spin_similarity.value(),
            'time_window_seconds': self.spin_time_window.value(),
            'scope_description': self.scope_widget.get_scope_description(),
            'processing_order': self.scope_widget.get_processing_order()
        }

        logger.info(f"Starting duplicate detection: {len(photo_ids)} photos, scope: {options['scope_description']}")

        # Show progress mode
        self._show_progress_mode()

        # Start worker thread with photo_ids
        self.worker = DuplicateDetectionWorker(self.project_id, options, photo_ids)
        self.worker_thread = QThread()

        self.worker.moveToThread(self.worker_thread)
        self.worker.progress_updated.connect(self._update_progress)
        self.worker.finished.connect(self._on_detection_finished)
        self.worker.error.connect(self._on_detection_error)
        self.worker_thread.started.connect(self.worker.run)

        self.worker_thread.start()

    def _show_progress_mode(self):
        """Switch to progress display mode."""
        # Disable configuration
        for widget in [self.scope_widget, self.chk_exact, self.chk_similar,
                       self.chk_generate_embeddings, self.sensitivity_widget,
                       self.status_group]:
            widget.setEnabled(False)

        # Show progress
        self.progress_group.setVisible(True)
        self.btn_start.setText("Running...")
        self.btn_start.setEnabled(False)
        self.btn_cancel.setText("Stop")

    def _update_progress(self, percentage: int, message: str):
        """Update progress display."""
        self.progress_bar.setValue(percentage)
        self.progress_label.setText(message)

    def _on_detection_finished(self, results: dict):
        """Handle detection completion."""
        # Clean up worker
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()

        # Show results
        scope = results.get('scope', 'All photos')
        message = (
            f"<b>Detection Complete!</b><br><br>"
            f"<b>Scope:</b> {scope}<br><br>"
            f"<b>Results:</b><br>"
            f"• Exact duplicates: {results.get('exact_duplicates', 0):,}<br>"
            f"• Similar stacks: {results.get('similar_stacks', 0):,}<br>"
            f"• Photos processed: {results.get('photos_processed', 0):,}<br>"
            f"• Embeddings generated: {results.get('embeddings_generated', 0):,}<br><br>"
            f"<i>Browse duplicates in the sidebar under 'Duplicates' section.</i>"
        )

        QMessageBox.information(self, "Detection Complete", message)
        self.accept()

    def _on_detection_error(self, error_message: str):
        """Handle detection error."""
        # Clean up worker
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()

        QMessageBox.critical(
            self,
            "Detection Failed",
            f"Duplicate detection failed:\n\n{error_message}"
        )

        # Return to configuration mode
        self._show_configuration_mode()

    def _show_configuration_mode(self):
        """Switch back to configuration mode."""
        # Re-enable configuration
        for widget in [self.scope_widget, self.chk_exact, self.chk_similar,
                       self.chk_generate_embeddings, self.sensitivity_widget,
                       self.status_group]:
            widget.setEnabled(True)

        # Hide progress
        self.progress_group.setVisible(False)
        self.btn_start.setText("▶ Start Detection")
        self.btn_start.setEnabled(True)
        self.btn_cancel.setText("Cancel")

    def reject(self):
        """Handle dialog rejection (cancel/escape)."""
        if self.worker_thread and self.worker_thread.isRunning():
            # Stop worker
            if self.worker:
                self.worker._running = False
            self.worker_thread.quit()
            self.worker_thread.wait()

        super().reject()


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    dialog = DuplicateDetectionDialog(project_id=1)
    dialog.exec()
