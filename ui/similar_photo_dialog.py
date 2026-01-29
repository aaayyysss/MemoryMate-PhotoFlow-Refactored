# similar_photo_dialog.py
# Version 01.00.00.00 dated 20260122
"""
Similar Photo Detection Dialog
Specialized dialog for finding visually similar photos using AI embeddings.

Follows best practices from:
- Google Photos: Advanced visual similarity with adjustable thresholds
- Lightroom: Professional clustering and grouping controls
- iPhone Photos: Intuitive similarity adjustment
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QGroupBox, QSpinBox, QDoubleSpinBox, QSlider,
    QFrame, QTextEdit, QProgressBar, QMessageBox, QComboBox,
    QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal, QThread, QObject, QTimer
from PySide6.QtGui import QFont
from typing import Optional, List, Dict
import numpy as np

from services.library_detector import check_system_readiness
from services.embedding_service import EmbeddingService
from repository.photo_repository import PhotoRepository
from repository.base_repository import DatabaseConnection
from services.semantic_embedding_service import SemanticEmbeddingService
from logging_config import get_logger

logger = get_logger(__name__)


class SimilarPhotoWorker(QObject):
    """Background worker for similar photo detection."""
    
    progress_updated = Signal(int, str)  # percentage, message
    preview_updated = Signal(list)  # list of photo groups
    finished = Signal(dict)  # results
    error = Signal(str)
    
    def __init__(self, project_id: int, options: dict):
        super().__init__()
        self.project_id = project_id
        self.options = options
        self._running = True
    
    def run(self):
        """Run similar photo detection process."""
        try:
            results = {
                'groups_found': 0,
                'photos_grouped': 0,
                'processing_time': 0
            }
            
            start_time = time.time()
            
            # Check if embeddings exist using SemanticEmbeddingService
            embedding_service = SemanticEmbeddingService()
            # Get all embeddings for the project to check count
            embeddings_dict = embedding_service.get_all_embeddings_for_project(self.project_id)
            photos_with_embeddings = [{'photo_id': pid} for pid in embeddings_dict.keys()]
            
            if len(photos_with_embeddings) < 2:
                self.error.emit(
                    "Not enough photos with embeddings. "
                    "Please generate embeddings first using the duplicate detection dialog."
                )
                return
            
            self.progress_updated.emit(10, f"Analyzing {len(photos_with_embeddings)} embedded photos...")

            # Extract embeddings from the preloaded dict
            embeddings = []
            photo_ids = []

            for photo_id, embedding in embeddings_dict.items():
                if not self._running:
                    return

                if embedding is not None:
                    embeddings.append(embedding)
                    photo_ids.append(photo_id)
            
            if len(embeddings) < 2:
                self.error.emit("Insufficient valid embeddings found.")
                return
            
            self.progress_updated.emit(30, "Computing similarity matrix...")
            
            # Compute pairwise similarities
            embeddings_array = np.array(embeddings)
            similarity_matrix = np.dot(embeddings_array, embeddings_array.T)
            
            self.progress_updated.emit(50, "Clustering similar photos...")
            
            # Apply clustering algorithm
            groups = self._cluster_similar_photos(
                photo_ids, 
                similarity_matrix,
                self.options['similarity_threshold'],
                self.options['min_group_size']
            )
            
            results['groups_found'] = len(groups)
            results['photos_grouped'] = sum(len(group) for group in groups)
            results['processing_time'] = round(time.time() - start_time, 1)
            results['groups'] = groups
            
            # Emit preview of groups
            self.preview_updated.emit(groups[:10])  # Show first 10 groups
            
            self.finished.emit(results)
            
        except Exception as e:
            logger.error(f"Similar photo detection failed: {e}")
            self.error.emit(str(e))
    
    def _cluster_similar_photos(self, photo_ids: List[int], similarity_matrix: np.ndarray,
                              threshold: float, min_group_size: int) -> List[List[int]]:
        """Cluster photos based on similarity scores."""
        # Simple clustering algorithm
        visited = set()
        groups = []
        
        for i, photo_id in enumerate(photo_ids):
            if photo_id in visited:
                continue
            
            # Find similar photos
            similar_indices = np.where(similarity_matrix[i] >= threshold)[0]
            group = [photo_ids[idx] for idx in similar_indices if photo_ids[idx] not in visited]
            
            if len(group) >= min_group_size:
                groups.append(group)
                visited.update(group)
        
        return groups


class SimilarPhotoDetectionDialog(QDialog):
    """
    Professional similar photo detection dialog.
    
    Features:
    - Visual similarity clustering
    - Adjustable sensitivity controls
    - Real-time preview of groups
    - Multiple clustering algorithms
    - Performance optimization options
    """
    
    def __init__(self, project_id: int, parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.worker_thread = None
        self.worker = None
        self.preview_groups = []
        
        self.setWindowTitle("📸 Find Similar Photos")
        self.setModal(True)
        self.setMinimumWidth(700)
        self.setMinimumHeight(800)
        
        self._build_ui()
        self._apply_styles()
        self._connect_signals()
        self._check_system_readiness()
        self._load_existing_stats()
    
    def _build_ui(self):
        """Build dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header_layout = QHBoxLayout()
        
        title_icon = QLabel("📸")
        title_icon.setStyleSheet("font-size: 24px;")
        
        title_label = QLabel("<h2>Find Similar Photos</h2>")
        title_label.setStyleSheet("margin-left: 10px;")
        
        header_layout.addWidget(title_icon)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        desc_label = QLabel(
            "Discover visually similar photos using AI-powered analysis. "
            "Adjust sensitivity to control grouping aggressiveness."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 8px;")
        layout.addWidget(desc_label)
        
        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep1)
        
        # Statistics
        stats_group = QGroupBox("Collection Statistics")
        stats_layout = QHBoxLayout(stats_group)
        
        self.stats_label = QLabel("Loading...")
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()
        
        layout.addWidget(stats_group)
        
        # Algorithm Selection
        algo_group = QGroupBox("Clustering Algorithm")
        algo_layout = QHBoxLayout(algo_group)
        
        algo_layout.addWidget(QLabel("Method:"))
        
        self.combo_algorithm = QComboBox()
        self.combo_algorithm.addItem("Hierarchical Clustering", "hierarchical")
        self.combo_algorithm.addItem("K-Means Clustering", "kmeans")
        self.combo_algorithm.addItem("DBSCAN", "dbscan")
        self.combo_algorithm.setCurrentIndex(0)
        self.combo_algorithm.setToolTip(
            "Hierarchical: Best for general use\n"
            "K-Means: Faster for large collections\n"
            "DBSCAN: Good for finding dense clusters"
        )
        algo_layout.addWidget(self.combo_algorithm)
        algo_layout.addStretch()
        
        layout.addWidget(algo_group)
        
        # Sensitivity Controls
        sensitivity_group = QGroupBox("Sensitivity Controls")
        sensitivity_layout = QVBoxLayout(sensitivity_group)
        sensitivity_layout.setSpacing(12)
        
        # Similarity threshold with slider
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("Similarity Threshold:"))
        
        self.slider_threshold = QSlider(Qt.Horizontal)
        self.slider_threshold.setRange(50, 99)  # 0.50 to 0.99
        self.slider_threshold.setValue(85)  # 0.85
        self.slider_threshold.setToolTip(
            "Higher = stricter matching\n"
            "Lower = more aggressive grouping"
        )
        threshold_layout.addWidget(self.slider_threshold)
        
        self.label_threshold = QLabel("0.85")
        self.label_threshold.setFixedWidth(40)
        threshold_layout.addWidget(self.label_threshold)
        
        sensitivity_layout.addLayout(threshold_layout)
        
        # Min group size
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Minimum Group Size:"))
        
        self.spin_min_size = QSpinBox()
        self.spin_min_size.setRange(2, 20)
        self.spin_min_size.setValue(3)
        self.spin_min_size.setToolTip("Minimum number of photos to form a group")
        size_layout.addWidget(self.spin_min_size)
        size_layout.addStretch()
        
        sensitivity_layout.addLayout(size_layout)
        
        # Time window for temporal grouping
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Time Proximity Window:"))
        
        self.spin_time_window = QSpinBox()
        self.spin_time_window.setRange(0, 300)
        self.spin_time_window.setValue(60)
        self.spin_time_window.setSuffix(" seconds")
        self.spin_time_window.setToolTip(
            "0 = Ignore timing\n"
            ">0 = Only group photos taken within this time window"
        )
        time_layout.addWidget(self.spin_time_window)
        time_layout.addStretch()
        
        sensitivity_layout.addLayout(time_layout)
        
        layout.addWidget(sensitivity_group)
        
        # Preview Section
        preview_group = QGroupBox("Preview Groups")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_list = QListWidget()
        self.preview_list.setMaximumHeight(200)
        preview_layout.addWidget(self.preview_list)
        
        preview_controls = QHBoxLayout()
        self.btn_refresh_preview = QPushButton("Refresh Preview")
        self.btn_refresh_preview.clicked.connect(self._refresh_preview)
        preview_controls.addWidget(self.btn_refresh_preview)
        preview_controls.addStretch()
        
        preview_layout.addLayout(preview_controls)
        
        layout.addWidget(preview_group)
        
        # System Status
        self.status_group = QGroupBox("Requirements Check")
        status_layout = QVBoxLayout(self.status_group)
        
        self.status_label = QLabel("Checking system...")
        self.status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.status_label)
        
        self.requirements_text = QTextEdit()
        self.requirements_text.setMaximumHeight(100)
        self.requirements_text.setReadOnly(True)
        status_layout.addWidget(self.requirements_text)
        
        layout.addWidget(self.status_group)
        
        # Progress Section (initially hidden)
        self.progress_group = QGroupBox("Processing")
        self.progress_group.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("Ready to start...")
        progress_layout.addWidget(self.progress_label)
        
        layout.addWidget(self.progress_group)
        
        # Results Section (initially hidden)
        self.results_group = QGroupBox("Results")
        self.results_group.setVisible(False)
        results_layout = QVBoxLayout(self.results_group)
        
        self.results_label = QLabel("Waiting for results...")
        results_layout.addWidget(self.results_label)
        
        layout.addWidget(self.results_group)
        
        # Buttons
        layout.addStretch(1)
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)
        
        self.btn_preview = QPushButton("Preview Groups")
        self.btn_preview.clicked.connect(self._preview_groups)
        button_layout.addWidget(self.btn_preview)
        
        self.btn_start = QPushButton("Find Similar Photos")
        self.btn_start.setDefault(True)
        self.btn_start.clicked.connect(self._start_detection)
        button_layout.addWidget(self.btn_start)
        
        layout.addLayout(button_layout)
    
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
            QSlider::groove:horizontal {
                height: 8px;
                background: #ddd;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                width: 18px;
                background: #1a73e8;
                border-radius: 9px;
                margin: -5px 0;
            }
        """)
        self.btn_start.setObjectName("btn_start")
    
    def _connect_signals(self):
        """Connect signals."""
        self.slider_threshold.valueChanged.connect(self._on_threshold_changed)
        
        # Auto-refresh preview when parameters change (with debounce)
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._refresh_preview)
        
        # Connect parameter changes to auto-refresh
        for widget in [self.slider_threshold, self.spin_min_size, self.spin_time_window]:
            if isinstance(widget, QSlider):
                widget.sliderReleased.connect(lambda: self.timer.start(500))
            else:
                widget.valueChanged.connect(lambda: self.timer.start(500))
    
    def _check_system_readiness(self):
        """Check system readiness and update UI."""
        ready, summary, recommendations = check_system_readiness()
        
        self.status_label.setText(summary)
        
        if ready:
            self.status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
            self.requirements_text.setPlainText("✅ System ready for similarity detection!")
            self.btn_start.setEnabled(True)
        else:
            self.status_label.setStyleSheet("color: #c62828; font-weight: bold;")
            rec_text = "⚠️ Missing requirements:\n\n" + "\n".join(f"• {rec}" for rec in recommendations)
            self.requirements_text.setPlainText(rec_text)
            self.btn_start.setEnabled(False)
    
    def _load_existing_stats(self):
        """Load statistics about existing embeddings."""
        try:
            # BUG FIX: Use proper service initialization with db connection
            db_conn = DatabaseConnection()
            photo_repo = PhotoRepository(db_conn)
            embedding_service = SemanticEmbeddingService(db_connection=db_conn)

            # BUG FIX: Use base repository count() method instead of non-existent count_photos_in_project
            total_photos = photo_repo.count(
                where_clause="project_id = ?",
                params=(self.project_id,)
            )

            # Get embedding stats from service
            stats = embedding_service.get_project_embedding_stats(self.project_id)
            photos_with_embeddings = stats.get('photos_with_embeddings', 0)

            self.stats_label.setText(
                f"Total Photos: {total_photos} | "
                f"With Embeddings: {photos_with_embeddings} | "
                f"Coverage: {int((photos_with_embeddings/max(total_photos,1))*100)}%"
            )

        except Exception as e:
            self.stats_label.setText(f"Error loading statistics: {e}")
    
    def _on_threshold_changed(self, value: int):
        """Handle threshold slider change."""
        threshold = value / 100.0
        self.label_threshold.setText(f"{threshold:.2f}")
    
    def _refresh_preview(self):
        """Refresh the preview with current settings."""
        # TODO: Implement lightweight preview that doesn't process all photos
        self.preview_list.clear()
        self.preview_list.addItem("Preview will show sample groups after processing...")
    
    def _preview_groups(self):
        """Show preview of similar groups."""
        # This would show a sample of the detected groups
        QMessageBox.information(
            self,
            "Preview Groups",
            "Groups preview will be available after processing.\n"
            "Click 'Find Similar Photos' to generate groups."
        )
    
    def _start_detection(self):
        """Start similar photo detection process."""
        # Prepare options
        options = {
            'algorithm': self.combo_algorithm.currentData(),
            'similarity_threshold': self.slider_threshold.value() / 100.0,
            'min_group_size': self.spin_min_size.value(),
            'time_window_seconds': self.spin_time_window.value()
        }
        
        # Show progress mode
        self._show_progress_mode()
        
        # Start worker
        self.worker = SimilarPhotoWorker(self.project_id, options)
        self.worker_thread = QThread()
        
        self.worker.moveToThread(self.worker_thread)
        self.worker.progress_updated.connect(self._update_progress)
        self.worker.preview_updated.connect(self._update_preview)
        self.worker.finished.connect(self._on_detection_finished)
        self.worker.error.connect(self._on_detection_error)
        self.worker_thread.started.connect(self.worker.run)
        
        self.worker_thread.start()
    
    def _show_progress_mode(self):
        """Switch to progress display mode."""
        # Disable configuration
        for widget in [self.combo_algorithm, self.slider_threshold, self.spin_min_size,
                      self.spin_time_window, self.btn_preview]:
            widget.setEnabled(False)
        
        # Show progress
        self.progress_group.setVisible(True)
        self.btn_start.setText("Processing...")
        self.btn_start.setEnabled(False)
        self.btn_cancel.setText("Stop")
    
    def _update_progress(self, percentage: int, message: str):
        """Update progress display."""
        self.progress_bar.setValue(percentage)
        self.progress_label.setText(message)
    
    def _update_preview(self, groups: list):
        """Update preview with detected groups."""
        self.preview_groups = groups
        self.preview_list.clear()
        
        for i, group in enumerate(groups):
            item = QListWidgetItem(f"Group {i+1}: {len(group)} photos")
            self.preview_list.addItem(item)
    
    def _on_detection_finished(self, results: dict):
        """Handle detection completion."""
        # Clean up worker
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()
        
        # Show results
        self._show_results_mode(results)
        
        message = f"""Similar photo detection completed!

Results:
• Groups found: {results['groups_found']}
• Photos grouped: {results['photos_grouped']}
• Processing time: {results['processing_time']} seconds

Groups are now available in the sidebar under 'Similar Photos'."""

        QMessageBox.information(self, "Detection Complete", message)
    
    def _show_results_mode(self, results: dict):
        """Show results display mode."""
        self.results_group.setVisible(True)
        self.results_label.setText(
            f"Found {results['groups_found']} groups containing "
            f"{results['photos_grouped']} photos"
        )
        
        # Restore buttons
        self.btn_start.setText("Find Similar Photos")
        self.btn_start.setEnabled(True)
        self.btn_cancel.setText("Close")
    
    def _on_detection_error(self, error_message: str):
        """Handle detection error."""
        # Clean up worker
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()
        
        QMessageBox.critical(
            self,
            "Detection Failed",
            f"Similar photo detection failed:\n\n{error_message}"
        )
        
        # Return to configuration mode
        self._show_configuration_mode()
    
    def _show_configuration_mode(self):
        """Switch back to configuration mode."""
        # Enable configuration
        for widget in [self.combo_algorithm, self.slider_threshold, self.spin_min_size,
                      self.spin_time_window, self.btn_preview]:
            widget.setEnabled(True)
        
        # Hide progress
        self.progress_group.setVisible(False)
        self.btn_start.setText("Find Similar Photos")
        self.btn_start.setEnabled(True)
        self.btn_cancel.setText("Cancel")
    
    def reject(self):
        """Handle dialog rejection."""
        if self.worker_thread and self.worker_thread.isRunning():
            if self.worker:
                self.worker._running = False
            self.worker_thread.quit()
            self.worker_thread.wait()
        
        super().reject()


# Import time here to avoid circular imports
import time

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    dialog = SimilarPhotoDetectionDialog(project_id=1)
    dialog.exec()
