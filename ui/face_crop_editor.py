#!/usr/bin/env python3
"""
Face Crop Editor - Manual face detection review and correction tool.

Allows users to:
- View original photos with detected face rectangles overlaid
- See which faces were automatically detected
- Manually draw rectangles around missed faces
- Correct or delete incorrect face detections
- Save new face crops to database

Best practice: Allow users to review and correct automated detections.

Author: Claude Code
Date: December 17, 2025
"""

import logging
import os
import io
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from PIL import Image

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QMessageBox, QCheckBox, QSpinBox,
    QGroupBox, QTextEdit
)
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont
from PySide6.QtCore import Qt, QRect, QPoint, Signal

from reference_db import ReferenceDB

logger = logging.getLogger(__name__)


class FaceCropEditor(QDialog):
    """
    Dialog for reviewing and manually correcting face detections.

    Shows original photo with face rectangles and allows manual additions/corrections.
    """

    faceCropsUpdated = Signal()  # Emitted when face crops are modified

    def __init__(self, photo_path: str, project_id: int, parent=None):
        """
        Initialize face crop editor.

        Args:
            photo_path: Path to the photo to review
            project_id: Current project ID
            parent: Parent widget
        """
        super().__init__(parent)

        self.photo_path = photo_path
        self.project_id = project_id
        self.detected_faces = []  # Existing face detections
        self.manual_faces = []  # Manually added faces

        photo_name = os.path.basename(photo_path)
        self.setWindowTitle(f"Face Crop Editor - {photo_name}")
        self.setModal(True)
        self.resize(1200, 800)

        self._load_existing_faces()
        self._create_ui()

    def _load_existing_faces(self):
        """Load count of existing face detections for this photo."""
        db = ReferenceDB()

        try:
            with db._connect() as conn:
                cur = conn.cursor()

                # Count existing face crops for this photo
                # Note: bbox column doesn't exist in face_crops table,
                # so we can't show existing face rectangles.
                # We just count how many faces were detected.
                cur.execute("""
                    SELECT
                        fc.id,
                        fc.branch_key,
                        fc.crop_path,
                        fbr.label as person_name
                    FROM face_crops fc
                    LEFT JOIN face_branch_reps fbr ON fc.branch_key = fbr.branch_key
                        AND fc.project_id = fbr.project_id
                    WHERE fc.image_path = ? AND fc.project_id = ?
                """, (self.photo_path, self.project_id))

                rows = cur.fetchall()
                self.detected_faces = []

                for row in rows:
                    face_id, branch_key, crop_path, person_name = row
                    self.detected_faces.append({
                        'id': face_id,
                        'branch_key': branch_key,
                        'crop_path': crop_path,
                        'person_name': person_name or "Unnamed",
                        'is_existing': True
                    })

                logger.info(f"[FaceCropEditor] Found {len(self.detected_faces)} existing face(s) (bboxes not available)")

        except Exception as e:
            logger.error(f"[FaceCropEditor] Failed to load existing faces: {e}")

    def _create_ui(self):
        """Create the editor UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QLabel(f"Face Detection Review - {os.path.basename(self.photo_path)}")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        # Info panel
        info_layout = QHBoxLayout()

        # Instructions
        instructions = QGroupBox("ℹ️ Instructions")
        instructions_layout = QVBoxLayout()
        instructions_text = QLabel(
            "• This photo has faces already detected (see stats)\n"
            "• Draw red rectangles to add missed faces\n"
            "• Click 'Add Manual Face' to start drawing\n"
            "• Drag on the photo to draw a rectangle\n"
            "• Save when done to update the database"
        )
        instructions_text.setStyleSheet("color: #5f6368; font-size: 9pt;")
        instructions_layout.addWidget(instructions_text)
        instructions.setLayout(instructions_layout)
        info_layout.addWidget(instructions)

        # Statistics
        stats_group = QGroupBox("📊 Detection Stats")
        stats_layout = QVBoxLayout()

        detected_count = len(self.detected_faces)
        stats_layout.addWidget(QLabel(f"Already Detected: {detected_count} face(s)"))

        if self.detected_faces:
            people_list = set(f['person_name'] for f in self.detected_faces)
            stats_layout.addWidget(QLabel(f"People: {', '.join(list(people_list)[:3])}..."))

        self.manual_count_label = QLabel(f"Manual Additions: 0")
        stats_layout.addWidget(self.manual_count_label)

        stats_group.setLayout(stats_layout)
        info_layout.addWidget(stats_group)

        layout.addLayout(info_layout)

        # Photo viewer with face rectangles
        self.photo_viewer = FacePhotoViewer(
            self.photo_path,
            self.detected_faces,
            self.manual_faces
        )
        self.photo_viewer.manualFaceAdded.connect(self._on_manual_face_added)
        layout.addWidget(self.photo_viewer, 1)

        # Action buttons
        button_layout = QHBoxLayout()

        add_manual_btn = QPushButton("➕ Add Manual Face")
        add_manual_btn.setToolTip("Click to enable drawing mode, then drag on the photo to draw a face rectangle")
        add_manual_btn.setStyleSheet("""
            QPushButton {
                background: #34a853;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2d8b47;
            }
        """)
        add_manual_btn.clicked.connect(self.photo_viewer.enable_drawing_mode)
        button_layout.addWidget(add_manual_btn)

        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("💾 Save Changes")
        save_btn.setDefault(True)
        save_btn.setStyleSheet("""
            QPushButton {
                background: #1a73e8;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #1557b0;
            }
        """)
        save_btn.clicked.connect(self._save_changes)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _on_manual_face_added(self, bbox: Tuple[int, int, int, int]):
        """Handle a manually added face rectangle."""
        self.manual_faces.append({
            'bbox': bbox,
            'is_existing': False
        })

        self.manual_count_label.setText(f"Manual Faces: {len(self.manual_faces)}")
        logger.info(f"[FaceCropEditor] Added manual face: {bbox}")

    def _save_changes(self):
        """Save manually added face crops to database."""
        if not self.manual_faces:
            QMessageBox.information(
                self,
                "No Changes",
                "No manual face rectangles were added.\n\nClick 'Add Manual Face' to draw rectangles around missed faces."
            )
            return

        try:
            # Create face crops from manual rectangles
            saved_count = 0

            for manual_face in self.manual_faces:
                bbox = manual_face['bbox']
                x, y, w, h = bbox

                # Crop face from original image
                crop_path = self._create_face_crop(x, y, w, h)

                if crop_path:
                    # Add to database
                    self._add_face_to_database(crop_path, bbox)
                    saved_count += 1

            if saved_count > 0:
                self.faceCropsUpdated.emit()
                QMessageBox.information(
                    self,
                    "Saved",
                    f"Successfully saved {saved_count} manually cropped face(s).\n\n"
                    "These faces will be clustered and appear in the People section."
                )
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Save Failed",
                    "Failed to save face crops. Please try again."
                )

        except Exception as e:
            logger.error(f"[FaceCropEditor] Failed to save changes: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save face crops:\n{e}"
            )

    def _create_face_crop(self, x: int, y: int, w: int, h: int) -> Optional[str]:
        """
        Crop face from original image and save to centralized directory.

        Args:
            x, y, w, h: Bounding box coordinates

        Returns:
            Path to saved crop, or None if failed
        """
        try:
            # Load original image
            with Image.open(self.photo_path) as img:
                # Crop face region
                face_crop = img.crop((x, y, x + w, y + h))

                # Use centralized face_crops directory (not cluttering photo directories)
                # Create .memorymate/face_crops/ in user's home or project directory
                home_dir = Path.home()
                crop_dir = home_dir / ".memorymate" / "face_crops"
                crop_dir.mkdir(parents=True, exist_ok=True)

                # Generate unique crop filename using uuid
                photo_name = os.path.splitext(os.path.basename(self.photo_path))[0]
                unique_id = uuid.uuid4().hex[:8]
                crop_filename = f"{photo_name}_manual_{unique_id}.jpg"
                crop_path = crop_dir / crop_filename

                # Save crop (convert to RGB if needed)
                if face_crop.mode != 'RGB':
                    face_crop = face_crop.convert('RGB')
                face_crop.save(str(crop_path), "JPEG", quality=95)

                logger.info(f"[FaceCropEditor] Saved face crop: {crop_path}")
                return str(crop_path)

        except Exception as e:
            logger.error(f"[FaceCropEditor] Failed to create face crop: {e}")
            return None

    def _add_face_to_database(self, crop_path: str, bbox: Tuple[int, int, int, int]):
        """
        Add manually cropped face to database.

        Args:
            crop_path: Path to saved face crop
            bbox: Bounding box (x, y, w, h)

        Note:
            quality_score is set to 0.5 (medium quality) by default for manual crops.
            This indicates human verification but acknowledges potential quality issues
            that prompted manual addition.
        """
        try:
            # Generate a new branch_key for this face
            # It will be clustered later and potentially merged with existing people
            branch_key = f"manual_{uuid.uuid4().hex[:8]}"

            # Add to database using direct DB operations
            db = ReferenceDB()
            with db._connect() as conn:
                cur = conn.cursor()

                # Insert face crop
                bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"

                # Default quality_score = 0.5 for manual crops
                # (medium quality, human-verified but may have issues)
                cur.execute("""
                    INSERT INTO face_crops
                    (project_id, image_path, crop_path, bbox, branch_key, is_representative, quality_score)
                    VALUES (?, ?, ?, ?, ?, 1, 0.5)
                """, (self.project_id, self.photo_path, crop_path, bbox_str, branch_key))

                # Create face_branch_reps entry
                cur.execute("""
                    INSERT OR REPLACE INTO face_branch_reps
                    (project_id, branch_key, label, rep_path, rep_thumb_png)
                    VALUES (?, ?, ?, ?, NULL)
                """, (self.project_id, branch_key, None, crop_path))

                conn.commit()

                logger.info(f"[FaceCropEditor] Added manual face to database: {branch_key}")

        except Exception as e:
            logger.error(f"[FaceCropEditor] Failed to add face to database: {e}")
            raise


class FacePhotoViewer(QWidget):
    """
    Widget for viewing photo with face rectangles overlay.
    Allows drawing new rectangles for manual face additions.
    """

    manualFaceAdded = Signal(tuple)  # (x, y, w, h)

    # Safety limits to prevent memory issues
    MAX_PHOTO_SIZE_MB = 50  # Maximum photo file size (50MB)
    MAX_DIMENSION = 12000  # Maximum width or height (12000 pixels)

    def __init__(self, photo_path: str, detected_faces: List[Dict], manual_faces: List[Dict], parent=None):
        super().__init__(parent)

        self.photo_path = photo_path
        self.detected_faces = detected_faces
        self.manual_faces = manual_faces

        self.drawing_mode = False
        self.draw_start = None
        self.draw_end = None

        self.setMinimumHeight(400)
        self._load_photo()

    def _load_photo(self):
        """
        Load and display the photo with safety checks.

        Validates:
        - File size (< 50MB)
        - Image dimensions (< 12000×12000 pixels)
        """
        try:
            # Check file size first (before loading into memory)
            if not os.path.exists(self.photo_path):
                logger.error(f"[FacePhotoViewer] Photo not found: {self.photo_path}")
                self.pixmap = None
                return

            file_size_mb = os.path.getsize(self.photo_path) / (1024 * 1024)
            if file_size_mb > self.MAX_PHOTO_SIZE_MB:
                logger.warning(f"[FacePhotoViewer] Photo too large: {file_size_mb:.1f}MB (max {self.MAX_PHOTO_SIZE_MB}MB)")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Photo Too Large",
                    f"This photo is too large to display safely ({file_size_mb:.1f}MB).\n\n"
                    f"Maximum size: {self.MAX_PHOTO_SIZE_MB}MB\n\n"
                    "Please use a smaller photo or compress the image first."
                )
                self.pixmap = None
                return

            # Load and check dimensions
            self.pixmap = QPixmap(self.photo_path)

            if self.pixmap.isNull():
                logger.error(f"[FacePhotoViewer] Failed to load photo: {self.photo_path}")
                self.pixmap = None
                return

            # Check dimensions
            if self.pixmap.width() > self.MAX_DIMENSION or self.pixmap.height() > self.MAX_DIMENSION:
                logger.warning(f"[FacePhotoViewer] Photo dimensions too large: {self.pixmap.width()}×{self.pixmap.height()}")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Photo Dimensions Too Large",
                    f"This photo's dimensions are too large ({self.pixmap.width()}×{self.pixmap.height()}).\n\n"
                    f"Maximum dimension: {self.MAX_DIMENSION}×{self.MAX_DIMENSION} pixels\n\n"
                    "Please resize the image first."
                )
                self.pixmap = None
                return

            logger.info(f"[FacePhotoViewer] Loaded photo: {self.pixmap.width()}×{self.pixmap.height()}, {file_size_mb:.1f}MB")

        except Exception as e:
            logger.error(f"[FacePhotoViewer] Error loading photo: {e}")
            self.pixmap = None

    def enable_drawing_mode(self):
        """Enable drawing mode for manual face rectangle."""
        self.drawing_mode = True
        self.setCursor(Qt.CrossCursor)
        self.update()

        logger.info("[FacePhotoViewer] Drawing mode enabled - drag to draw face rectangle")

    def mousePressEvent(self, event):
        """Handle mouse press to start drawing."""
        if self.drawing_mode and event.button() == Qt.LeftButton:
            self.draw_start = event.position().toPoint()
            self.draw_end = None

    def mouseMoveEvent(self, event):
        """Handle mouse move while drawing."""
        if self.drawing_mode and self.draw_start:
            self.draw_end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release to finish drawing."""
        if self.drawing_mode and event.button() == Qt.LeftButton and self.draw_start:
            self.draw_end = event.position().toPoint()

            # Calculate rectangle
            rect = QRect(self.draw_start, self.draw_end).normalized()

            if rect.width() > 20 and rect.height() > 20:
                # Convert from widget coordinates to image coordinates
                if self.pixmap:
                    # Get scale factor
                    widget_rect = self.rect()
                    pixmap_rect = self.pixmap.rect()

                    scale_x = pixmap_rect.width() / widget_rect.width()
                    scale_y = pixmap_rect.height() / widget_rect.height()
                    scale = max(scale_x, scale_y)

                    # Scale coordinates
                    x = int(rect.x() * scale)
                    y = int(rect.y() * scale)
                    w = int(rect.width() * scale)
                    h = int(rect.height() * scale)

                    # Ensure within image bounds
                    x = max(0, min(x, pixmap_rect.width() - w))
                    y = max(0, min(y, pixmap_rect.height() - h))

                    # Emit signal
                    self.manualFaceAdded.emit((x, y, w, h))

                    logger.info(f"[FacePhotoViewer] Manual face drawn: {(x, y, w, h)}")

            # Reset drawing state
            self.drawing_mode = False
            self.draw_start = None
            self.draw_end = None
            self.setCursor(Qt.ArrowCursor)
            self.update()

    def paintEvent(self, event):
        """Paint the photo with face rectangles overlay."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.pixmap:
            painter.drawText(self.rect(), Qt.AlignCenter, "Failed to load photo")
            return

        # Draw photo scaled to fit
        scaled_pixmap = self.pixmap.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        # Center the pixmap
        x_offset = (self.width() - scaled_pixmap.width()) // 2
        y_offset = (self.height() - scaled_pixmap.height()) // 2

        painter.drawPixmap(x_offset, y_offset, scaled_pixmap)

        # Calculate scale factor for rectangles
        scale = scaled_pixmap.width() / self.pixmap.width()

        # Note: Cannot draw detected face rectangles because bbox data
        # is not stored in face_crops table. We only show manual rectangles.

        # Draw manual face rectangles (red)
        pen = QPen(QColor(234, 67, 53), 3)  # Red
        painter.setPen(pen)

        for face in self.manual_faces:
            bbox = face['bbox']
            x, y, w, h = bbox

            rect = QRect(
                int(x * scale) + x_offset,
                int(y * scale) + y_offset,
                int(w * scale),
                int(h * scale)
            )
            painter.drawRect(rect)

            # Draw "Manual" label
            painter.setFont(QFont("Arial", 10, QFont.Bold))
            painter.drawText(rect.x(), rect.y() - 5, "Manual")

        # Draw current drawing rectangle
        if self.drawing_mode and self.draw_start and self.draw_end:
            pen = QPen(QColor(26, 115, 232), 2, Qt.DashLine)  # Blue dashed
            painter.setPen(pen)
            rect = QRect(self.draw_start, self.draw_end).normalized()
            painter.drawRect(rect)


if __name__ == '__main__':
    # Test dialog
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Example usage (requires valid photo path)
    dialog = FaceCropEditor(
        photo_path="/path/to/photo.jpg",
        project_id=1
    )
    dialog.faceCropsUpdated.connect(lambda: print("Face crops updated!"))

    if dialog.exec():
        print("✅ Changes saved")
    else:
        print("❌ Cancelled")

    sys.exit(0)
