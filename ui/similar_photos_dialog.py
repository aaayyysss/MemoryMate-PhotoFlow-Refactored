"""
SimilarPhotosDialog - Visual Similarity Browser

Version: 1.0.0
Date: 2026-01-05

Show visually similar photos with threshold control.

Features:
- Grid view of similar photos
- Similarity score display
- Threshold slider (0.0 to 1.0)
- Real-time filtering
- Double-click to open photo

Usage:
    dialog = SimilarPhotosDialog(reference_photo_id=123, parent=parent_widget)
    dialog.exec()
"""

from typing import Optional, List
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QSlider, QPushButton, QWidget, QScrollArea,
    QFrame, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QMouseEvent

from services.photo_similarity_service import get_photo_similarity_service, SimilarPhoto
from logging_config import get_logger

logger = get_logger(__name__)


class PhotoThumbnail(QFrame):
    """
    Thumbnail widget for similar photo.

    Shows thumbnail, similarity score, and handles click events.
    """

    clicked = Signal(int)  # photo_id

    def __init__(self, similar_photo: SimilarPhoto, parent=None):
        super().__init__(parent)
        self.photo_id = similar_photo.photo_id
        self.similarity_score = similar_photo.similarity_score

        self.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.setLineWidth(1)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setFixedSize(150, 150)
        self.thumbnail_label.setStyleSheet("background-color: #f0f0f0;")

        # Load thumbnail
        if similar_photo.thumbnail_path and Path(similar_photo.thumbnail_path).exists():
            pixmap = QPixmap(similar_photo.thumbnail_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.thumbnail_label.setPixmap(pixmap)
            else:
                self.thumbnail_label.setText("No Preview")
        else:
            self.thumbnail_label.setText("No Thumbnail")

        # Score label
        score_percent = int(self.similarity_score * 100)
        self.score_label = QLabel(f"{score_percent}% similar")
        self.score_label.setAlignment(Qt.AlignCenter)

        # Color-code by similarity
        if self.similarity_score >= 0.9:
            color = "#2ecc71"  # Green
        elif self.similarity_score >= 0.8:
            color = "#3498db"  # Blue
        elif self.similarity_score >= 0.7:
            color = "#f39c12"  # Orange
        else:
            color = "#95a5a6"  # Gray

        self.score_label.setStyleSheet(f"color: {color}; font-weight: bold;")

        layout.addWidget(self.thumbnail_label)
        layout.addWidget(self.score_label)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double-click to open photo."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.photo_id)
        super().mouseDoubleClickEvent(event)


class SimilarPhotosDialog(QDialog):
    """
    Dialog for browsing visually similar photos.

    Shows grid of similar photos with threshold control.
    """

    photo_clicked = Signal(int)  # photo_id

    def __init__(self, reference_photo_id: int, parent=None):
        super().__init__(parent)
        self.reference_photo_id = reference_photo_id
        self.similarity_service = get_photo_similarity_service()
        self.all_results: List[SimilarPhoto] = []
        self.current_threshold = 0.7

        self.setWindowTitle(f"Similar Photos (Reference: Photo #{reference_photo_id})")
        self.resize(900, 700)

        self._init_ui()
        self._load_similar_photos()

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()

        self.title_label = QLabel("Finding similar photos...")
        self.title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        # Coverage info
        self.coverage_label = QLabel()
        header_layout.addWidget(self.coverage_label)

        layout.addLayout(header_layout)

        # Threshold control
        threshold_layout = QHBoxLayout()

        threshold_layout.addWidget(QLabel("Similarity Threshold:"))

        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setMinimum(50)  # 0.5
        self.threshold_slider.setMaximum(100)  # 1.0
        self.threshold_slider.setValue(70)  # 0.7
        self.threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_slider.setTickInterval(10)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        threshold_layout.addWidget(self.threshold_slider, 1)

        self.threshold_value_label = QLabel("70%")
        self.threshold_value_label.setMinimumWidth(50)
        threshold_layout.addWidget(self.threshold_value_label)

        layout.addLayout(threshold_layout)

        # Results info
        self.results_label = QLabel()
        layout.addWidget(self.results_label)

        # Scroll area for thumbnails
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self.grid_widget)
        layout.addWidget(scroll, 1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _load_similar_photos(self):
        """Load similar photos from service."""
        try:
            # Check coverage
            coverage = self.similarity_service.get_embedding_coverage()
            self.coverage_label.setText(
                f"{coverage['embedded_photos']}/{coverage['total_photos']} photos embedded "
                f"({coverage['coverage_percent']:.1f}%)"
            )

            if coverage['embedded_photos'] < 2:
                self.title_label.setText("Not enough photos with embeddings")
                self.results_label.setText(
                    "Run embedding extraction to enable similarity search"
                )
                return

            # Load all results (we'll filter by threshold in UI)
            self.all_results = self.similarity_service.find_similar(
                photo_id=self.reference_photo_id,
                top_k=100,  # Get more results for threshold filtering
                threshold=0.5,  # Lower threshold to get more candidates
                include_metadata=True
            )

            self.title_label.setText(f"Similar Photos (Photo #{self.reference_photo_id})")

            # Display filtered results
            self._update_display()

        except Exception as e:
            logger.error(f"[SimilarPhotosDialog] Failed to load similar photos: {e}", exc_info=True)
            self.title_label.setText("Error loading similar photos")
            self.results_label.setText(str(e))

    def _on_threshold_changed(self, value: int):
        """Handle threshold slider change."""
        self.current_threshold = value / 100.0
        self.threshold_value_label.setText(f"{value}%")
        self._update_display()

    def _update_display(self):
        """Update thumbnail grid based on current threshold."""
        # Clear existing thumbnails
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Filter by threshold
        filtered_results = [
            photo for photo in self.all_results
            if photo.similarity_score >= self.current_threshold
        ]

        # Update results label
        self.results_label.setText(
            f"Showing {len(filtered_results)} similar photos "
            f"(threshold ≥ {int(self.current_threshold * 100)}%)"
        )

        if not filtered_results:
            no_results_label = QLabel("No photos meet the similarity threshold")
            no_results_label.setAlignment(Qt.AlignCenter)
            no_results_label.setStyleSheet("color: #7f8c8d; font-size: 12pt;")
            self.grid_layout.addWidget(no_results_label, 0, 0)
            return

        # Add thumbnails to grid (4 columns)
        for i, photo in enumerate(filtered_results):
            row = i // 4
            col = i % 4

            thumbnail = PhotoThumbnail(photo)
            thumbnail.clicked.connect(self._on_photo_clicked)
            self.grid_layout.addWidget(thumbnail, row, col)

    def _on_photo_clicked(self, photo_id: int):
        """Handle photo thumbnail click."""
        self.photo_clicked.emit(photo_id)
        logger.info(f"[SimilarPhotosDialog] Photo {photo_id} clicked")

        # Optionally: Open photo in main window or show details
        # For now, just emit signal
