# duplicate_detection_dialog.py
# Version 1.00.00.00 dated 20260122

"""
Duplicate Detection Dialog
Professional dialog for configuring and running duplicate detection.

Follows best practices from:
- Google Photos: Clear parameter controls and progress indication
- Lightroom: Professional workflow with preview options  
- iPhone Photos: Simple yet powerful interface
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QGroupBox, QSpinBox, QDoubleSpinBox, QRadioButton,
    QButtonGroup, QFrame, QTextEdit, QProgressBar, QMessageBox,
    QScrollArea, QWidget
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QFont
from typing import Optional, List
import time

from services.library_detector import check_system_readiness
from repository.asset_repository import AssetRepository
from repository.base_repository import DatabaseConnection
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
            photo_count = len(self.photo_ids) if self.photo_ids else 0

            results['photos_processed'] = photo_count

            # Step 1: Exact duplicate detection
            if self.options.get('detect_exact', False):
                total_steps += 1

            # Step 2: Embedding generation
            if self.options.get('generate_embeddings', False):
                # Estimate based on photo count (reuse already computed value)
                total_steps += max(1, photo_count // 100 + 1)  # Rough estimate
            
            # Step 3: Similar detection
            if self.options.get('detect_similar', False):
                total_steps += 2

            if total_steps == 0:
                total_steps = 1  # Prevent division by zero

            # Execute steps
            if self.options.get('detect_exact', False):
                if not self._running:
                    return

                # Step 1a: Run hash backfill to compute file hashes and link assets
                self.progress_updated.emit(
                    int((current_step / total_steps) * 100),
                    "Computing file hashes..."
                )

                try:
                    from services.asset_service import AssetService

                    db_conn = DatabaseConnection()
                    photo_repo = PhotoRepository(db_conn)
                    asset_repo = AssetRepository(db_conn)
                    asset_service = AssetService(photo_repo, asset_repo)

                    # Run hash backfill - this creates media_asset and media_instance records
                    # Note: backfill processes all photos without instance links (idempotent)
                    # This ensures duplicate detection works even for legacy photos
                    backfill_stats = asset_service.backfill_hashes_and_link_assets(
                        project_id=self.project_id
                    )
                    logger.info(f"Hash backfill complete: {backfill_stats.scanned} scanned, {backfill_stats.hashed} hashed, {backfill_stats.linked} linked")
                except Exception as e:
                    logger.error(f"Hash backfill failed: {e}")
                    # Continue anyway - we can still query existing duplicates

                # Step 1b: Query for duplicates
                self.progress_updated.emit(
                    int((current_step / total_steps) * 100),
                    "Finding exact duplicates..."
                )

                db_conn = DatabaseConnection()
                asset_repo = AssetRepository(db_conn)
                duplicate_assets = asset_repo.list_duplicate_assets(self.project_id, min_instances=2)
                exact_count = len(duplicate_assets)
                results['exact_duplicates'] = exact_count
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

                    # Process photos in batches
                    db_conn = DatabaseConnection()
                    photo_repo = PhotoRepository(db_conn)
                    photos = photo_repo.get_photos_needing_embeddings(self.project_id, limit=1000)
                    
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

                    # BUG FIX: Create db_conn for similar detection if not already created
                    # (may not exist if detect_exact and generate_embeddings were both False)
                    if 'db_conn' not in dir() or db_conn is None:
                        db_conn = DatabaseConnection()

                    # BUG FIX: Create photo_repo if not already created
                    if 'photo_repo' not in dir() or photo_repo is None:
                        photo_repo = PhotoRepository(db_conn)

                    # BUG FIX: StackRepository requires db parameter
                    stack_repo = StackRepository(db_conn)
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
    Professional duplicate detection dialog.

    Features:
    - Exact duplicate detection (hash-based)
    - Similar shot detection (AI-powered)
    - Scope selection (all/folders/dates/recent/quantity)
    - Configurable parameters
    - Real-time progress
    - System readiness checking

    Best practices from:
    - Google Photos: Simple defaults with smart suggestions
    - iPhone Photos: Automatic background processing
    - Lightroom: Professional folder/collection selection
    """

    def __init__(self, project_id: int, parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.worker_thread = None
        self.worker = None
        self.selected_photo_ids: List[int] = []

        self.setWindowTitle("Detect Duplicates & Similar Photos")
        self.setModal(True)
        self.setMinimumWidth(650)
        self.setMinimumHeight(800)

        self._build_ui()
        self._apply_styles()
        self._connect_signals()
        self._check_system_readiness()
    
    def _build_ui(self):
        """Build dialog UI."""
        # Main layout with scroll area for smaller screens
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header_layout = QHBoxLayout()

        title_label = QLabel("<h2>Detect Duplicates & Similar Photos</h2>")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        desc_label = QLabel(
            "Find duplicate and similar photos in your collection. "
            "Select which photos to scan, choose detection methods, and configure settings."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 8px;")
        layout.addWidget(desc_label)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep1)

        # === SCOPE SELECTION WIDGET ===
        self.scope_widget = EmbeddingScopeWidget(self.project_id, self)
        self.scope_widget.scopeChanged.connect(self._on_scope_changed)
        layout.addWidget(self.scope_widget)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep2)

        # Detection Types
        detection_group = QGroupBox("Detection Methods")
        detection_layout = QVBoxLayout(detection_group)
        detection_layout.setSpacing(12)
        
        # Exact duplicates
        self.chk_exact = QCheckBox("🔍 Exact Duplicates (Fast)")
        self.chk_exact.setToolTip(
            "Find photos with identical content using SHA256 hashing.\n"
            "Very fast, catches perfect copies and backups."
        )
        self.chk_exact.setChecked(True)
        detection_layout.addWidget(self.chk_exact)
        
        exact_desc = QLabel("    Identical file content - No false positives")
        exact_desc.setStyleSheet("color: #666; font-size: 9pt; margin-left: 24px;")
        detection_layout.addWidget(exact_desc)
        
        # Similar shots
        self.chk_similar = QCheckBox("📸 Similar Shots (AI-Powered)")
        self.chk_similar.setToolTip(
            "Find visually similar photos using AI embeddings.\n"
            "Catches burst shots, edited versions, and similar compositions."
        )
        detection_layout.addWidget(self.chk_similar)
        
        similar_desc = QLabel("    Visually similar content - May have false positives")
        similar_desc.setStyleSheet("color: #666; font-size: 9pt; margin-left: 24px;")
        detection_layout.addWidget(similar_desc)
        
        layout.addWidget(detection_group)
        
        # Parameters Group
        params_group = QGroupBox("Parameters")
        params_layout = QVBoxLayout(params_group)
        params_layout.setSpacing(12)
        
        # Embedding generation
        self.chk_generate_embeddings = QCheckBox("🤖 Generate AI Embeddings")
        self.chk_generate_embeddings.setToolTip(
            "Extract visual embeddings using CLIP model.\n"
            "Required for similar shot detection.\n"
            "Takes 2-5 seconds per photo depending on hardware."
        )
        params_layout.addWidget(self.chk_generate_embeddings)
        
        # Sensitivity settings (only enabled when similar detection is checked)
        sensitivity_widget = QFrame()
        sensitivity_layout = QVBoxLayout(sensitivity_widget)
        sensitivity_layout.setContentsMargins(24, 8, 0, 0)
        sensitivity_layout.setSpacing(8)
        
        # Similarity threshold
        sim_row = QHBoxLayout()
        sim_row.addWidget(QLabel("Similarity Threshold:"))
        self.spin_similarity = QDoubleSpinBox()
        self.spin_similarity.setRange(0.50, 0.99)
        self.spin_similarity.setSingleStep(0.05)
        self.spin_similarity.setValue(0.85)
        self.spin_similarity.setToolTip(
            "Minimum visual similarity (0.50-0.99)\n"
            "Lower = more aggressive grouping\n"
            "Higher = stricter matching"
        )
        sim_row.addWidget(self.spin_similarity)
        sim_row.addStretch(1)
        sensitivity_layout.addLayout(sim_row)
        
        # Time window for burst detection
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Time Window:"))
        self.spin_time_window = QSpinBox()
        self.spin_time_window.setRange(5, 120)
        self.spin_time_window.setValue(30)
        self.spin_time_window.setSuffix(" seconds")
        self.spin_time_window.setToolTip(
            "Only compare photos taken within this time period\n"
            "Good for burst mode photography (5-10s) or events (30-120s)"
        )
        time_row.addWidget(self.spin_time_window)
        time_row.addStretch(1)
        sensitivity_layout.addLayout(time_row)
        
        sensitivity_widget.setLayout(sensitivity_layout)
        params_layout.addWidget(sensitivity_widget)
        self.sensitivity_widget = sensitivity_widget
        
        layout.addWidget(params_group)
        
        # System Status
        self.status_group = QGroupBox("System Status")
        status_layout = QVBoxLayout(self.status_group)
        
        self.status_label = QLabel("Checking system...")
        self.status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.status_label)
        
        self.recommendations_text = QTextEdit()
        self.recommendations_text.setMaximumHeight(100)
        self.recommendations_text.setReadOnly(True)
        status_layout.addWidget(self.recommendations_text)
        
        layout.addWidget(self.status_group)
        
        # Progress Section (initially hidden)
        self.progress_group = QGroupBox("Progress")
        self.progress_group.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("Ready to start...")
        progress_layout.addWidget(self.progress_label)
        
        layout.addWidget(self.progress_group)
        
        # Add stretch before buttons
        layout.addStretch(1)

        # Set up scroll area
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        # Buttons (outside scroll area for always visible)
        button_widget = QWidget()
        button_widget.setStyleSheet("background-color: white; border-top: 1px solid #ddd;")
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(20, 12, 20, 12)
        button_layout.addStretch(1)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)

        self.btn_start = QPushButton("Start Detection")
        self.btn_start.setDefault(True)
        self.btn_start.clicked.connect(self._start_detection)
        button_layout.addWidget(self.btn_start)

        main_layout.addWidget(button_widget)
    
    def _apply_styles(self):
        """Apply custom styles."""
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ddd;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background-color: white;
            }
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                background-color: #f5f5f5;
                color: #333333;
                border: 1px solid #cccccc;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
            QPushButton#btn_start {
                background-color: #1a73e8;
                color: white;
                border: none;
            }
            QPushButton#btn_start:hover {
                background-color: #1557b0;
            }
            QPushButton#btn_start:pressed {
                background-color: #0d47a1;
            }
        """)
        self.btn_start.setObjectName("btn_start")
    
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
            self.recommendations_text.setPlainText("✅ System ready for duplicate detection!")
            self.btn_start.setEnabled(True)
        else:
            self.status_label.setStyleSheet("color: #c62828; font-weight: bold;")
            rec_text = "⚠️ System issues detected:\n\n" + "\n".join(f"• {rec}" for rec in recommendations)
            self.recommendations_text.setPlainText(rec_text)
            self.btn_start.setEnabled(False)
    
    def _on_similar_toggled(self, checked: bool):
        """Handle similar detection toggle."""
        self.chk_generate_embeddings.setEnabled(checked)
        self.sensitivity_widget.setEnabled(checked)
        
        if checked and not self.chk_generate_embeddings.isChecked():
            self.chk_generate_embeddings.setChecked(True)
    
    def _on_embedding_toggled(self, checked: bool):
        """Handle embedding generation toggle."""
        # If embeddings are disabled but similar detection is enabled, warn user
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
    
    def _start_detection(self):
        """Start duplicate detection process."""
        # Validate options
        if not self.chk_exact.isChecked() and not self.chk_similar.isChecked():
            QMessageBox.warning(
                self,
                "No Detection Method Selected",
                "Please select at least one detection method:\n"
                "  Exact Duplicates\n"
                "  Similar Shots"
            )
            return

        # Get selected photo IDs from scope widget
        photo_ids = self.scope_widget.get_selected_photo_ids()

        if not photo_ids:
            QMessageBox.warning(
                self,
                "No Photos Selected",
                "Please select at least some photos to scan.\n\n"
                "Use the 'Photo Selection' options above to choose which photos to analyze."
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

        # Hide configuration, show progress
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
        # Disable configuration elements
        for widget in [self.scope_widget, self.chk_exact, self.chk_similar,
                       self.chk_generate_embeddings, self.sensitivity_widget,
                       self.status_group]:
            widget.setEnabled(False)

        # Show progress elements
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
        message = f"""Duplicate detection completed!

Scope: {scope}

Results:
  Exact duplicates found: {results.get('exact_duplicates', 0):,}
  Similar stacks created: {results.get('similar_stacks', 0):,}
  Photos processed: {results.get('photos_processed', 0):,}
  Embeddings generated: {results.get('embeddings_generated', 0):,}

You can now browse duplicates in the sidebar under 'Duplicates' section."""

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
        # Re-enable configuration elements
        for widget in [self.scope_widget, self.chk_exact, self.chk_similar,
                       self.chk_generate_embeddings, self.sensitivity_widget,
                       self.status_group]:
            widget.setEnabled(True)

        # Hide progress elements
        self.progress_group.setVisible(False)
        self.btn_start.setText("Start Detection")
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
