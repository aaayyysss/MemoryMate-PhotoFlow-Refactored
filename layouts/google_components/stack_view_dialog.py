# layouts/google_components/stack_view_dialog.py
# Version 01.01.00.00 dated 20260115
# Stack comparison dialog for Google Layout

"""
StackViewDialog - Compare and manage stack members

This dialog shows a stack's members in a comparison view:
- Representative image highlighted
- Side-by-side thumbnails
- Metadata comparison table with similarity scores
- Actions: Keep All, Delete Selected, Set Representative, Unstack
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout, QFrame, QCheckBox,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox
)
from PySide6.QtCore import Signal, Qt, Slot
from PySide6.QtGui import QFont, QColor, QPixmap
from typing import Optional, List, Dict, Any
from pathlib import Path
from logging_config import get_logger

logger = get_logger(__name__)


class StackMemberWidget(QWidget):
    """
    Widget displaying a single stack member with thumbnail and key metadata.

    Shows:
    - Thumbnail (larger than PhotoInstanceWidget)
    - Similarity score
    - Rank
    - Resolution
    - File size
    - Checkbox for selection
    - Representative indicator
    """

    selection_changed = Signal(int, bool)  # photo_id, is_selected

    def __init__(
        self,
        photo: Dict[str, Any],
        similarity_score: Optional[float] = None,
        rank: Optional[int] = None,
        is_representative: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.photo = photo
        self.similarity_score = similarity_score
        self.rank = rank
        self.is_representative = is_representative

        self._init_ui()
        self._load_thumbnail()

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(180, 180)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("""
            QLabel {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)
        self.thumbnail_label.setText("Loading...")
        layout.addWidget(self.thumbnail_label, alignment=Qt.AlignCenter)

        # Metadata
        metadata_layout = QVBoxLayout()
        metadata_layout.setSpacing(4)

        # Representative badge
        if self.is_representative:
            rep_label = QLabel("⭐ Representative")
            rep_label.setStyleSheet("color: #FFA500; font-weight: bold; font-size: 11px;")
            metadata_layout.addWidget(rep_label)

        # Similarity score (if available)
        if self.similarity_score is not None:
            score_pct = self.similarity_score * 100
            score_label = QLabel(f"🔗 Similarity: {score_pct:.1f}%")
            score_label.setStyleSheet("font-size: 11px; color: #2196F3; font-weight: bold;")
            metadata_layout.addWidget(score_label)

        # Rank (if available)
        if self.rank is not None:
            rank_label = QLabel(f"📊 Rank: #{self.rank}")
            rank_label.setStyleSheet("font-size: 11px; color: #666;")
            metadata_layout.addWidget(rank_label)

        # Resolution
        width = self.photo.get('width', 0)
        height = self.photo.get('height', 0)
        res_label = QLabel(f"📐 {width}×{height}")
        res_label.setStyleSheet("font-size: 10px; color: #666;")
        metadata_layout.addWidget(res_label)

        # File size
        size_kb = self.photo.get('size_kb', 0)
        if size_kb >= 1024:
            size_str = f"{size_kb/1024:.1f} MB"
        else:
            size_str = f"{size_kb:.1f} KB"
        size_label = QLabel(f"💾 {size_str}")
        size_label.setStyleSheet("font-size: 10px; color: #666;")
        metadata_layout.addWidget(size_label)

        # Filename (truncated)
        path = self.photo.get('path', '')
        filename = Path(path).name
        if len(filename) > 20:
            filename = filename[:17] + "..."
        path_label = QLabel(f"📄 {filename}")
        path_label.setToolTip(path)
        path_label.setStyleSheet("font-size: 10px; color: #666;")
        metadata_layout.addWidget(path_label)

        layout.addLayout(metadata_layout)

        # Selection checkbox
        self.checkbox = QCheckBox("Select")
        self.checkbox.setEnabled(not self.is_representative)
        if self.is_representative:
            self.checkbox.setToolTip("Cannot select representative")
        self.checkbox.stateChanged.connect(self._on_selection_changed)
        layout.addWidget(self.checkbox)

        # Style
        border_color = "#FFA500" if self.is_representative else "#e0e0e0"
        self.setStyleSheet(f"""
            StackMemberWidget {{
                background-color: white;
                border: 2px solid {border_color};
                border-radius: 8px;
            }}
        """)

    def _load_thumbnail(self):
        """Load thumbnail synchronously."""
        try:
            from app_services import get_thumbnail
            path = self.photo.get('path', '')

            if path and Path(path).exists():
                pixmap = get_thumbnail(path, 180)
                if pixmap and not pixmap.isNull():
                    self.thumbnail_label.setPixmap(pixmap)
                else:
                    self.thumbnail_label.setText("No preview")
            else:
                self.thumbnail_label.setText("Not found")
                self.thumbnail_label.setStyleSheet("""
                    QLabel {
                        background-color: #fee;
                        border: 1px solid #fcc;
                        color: #c00;
                    }
                """)
        except Exception as e:
            logger.error(f"Failed to load thumbnail: {e}")
            self.thumbnail_label.setText("Error")

    def _on_selection_changed(self, state):
        """Handle selection change."""
        is_selected = state == Qt.Checked
        self.selection_changed.emit(self.photo['id'], is_selected)

    def is_selected(self) -> bool:
        """Check if selected."""
        return self.checkbox.isChecked()


class StackViewDialog(QDialog):
    """
    Dialog for viewing and managing stack members.

    Displays:
    - Stack info (type, member count)
    - Representative image highlighted
    - Grid of all stack members with similarity scores
    - Metadata comparison table
    - Actions: Keep All, Delete Selected, Set Representative, Unstack

    Signals:
    - stack_action_taken: Emitted when user takes action on stack
    """

    # Signals
    stack_action_taken = Signal(str, int)  # action, stack_id

    def __init__(self, project_id: int, stack_id: int, parent=None):
        """
        Initialize StackViewDialog.

        Args:
            project_id: Project ID
            stack_id: Stack ID to display
            parent: Parent widget
        """
        super().__init__(parent)
        self.project_id = project_id
        self.stack_id = stack_id
        self.stack = None
        self.members = []
        self.photos = {}  # Map photo_id -> photo dict
        self.selected_photos = set()

        self.setWindowTitle("Stack Comparison")
        self.setMinimumSize(1100, 750)

        self._init_ui()
        self._load_stack()

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title section
        title_layout = QHBoxLayout()

        self.title_label = QLabel("📚 Stack Comparison")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        title_layout.addWidget(self.title_label)

        title_layout.addStretch()

        # Stack info
        self.info_label = QLabel("Loading...")
        self.info_label.setStyleSheet("color: #666; font-size: 12px;")
        title_layout.addWidget(self.info_label)

        layout.addLayout(title_layout)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Members grid
        members_group = QGroupBox("Stack Members")
        members_layout = QVBoxLayout(members_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ddd;
                background-color: #fafafa;
            }
        """)

        self.members_container = QWidget()
        self.members_grid = QGridLayout(self.members_container)
        self.members_grid.setSpacing(16)
        self.members_grid.setContentsMargins(16, 16, 16, 16)

        scroll.setWidget(self.members_container)
        members_layout.addWidget(scroll)

        layout.addWidget(members_group, stretch=3)

        # Comparison table
        table_group = QGroupBox("Detailed Comparison")
        table_layout = QVBoxLayout(table_group)

        self.comparison_table = QTableWidget()
        self.comparison_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                gridline-color: #eee;
            }
            QHeaderView::section {
                background-color: #f5f5f5;
                padding: 4px;
                border: 1px solid #ddd;
                font-weight: bold;
            }
        """)
        table_layout.addWidget(self.comparison_table)

        layout.addWidget(table_group, stretch=2)

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator2)

        # Action buttons
        button_layout = QHBoxLayout()

        self.btn_unstack = QPushButton("🔓 Unstack All")
        self.btn_unstack.setToolTip("Remove all members from this stack (keeps photos)")
        self.btn_unstack.clicked.connect(self._on_unstack_all)
        self.btn_unstack.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                background-color: #FF9800;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        button_layout.addWidget(self.btn_unstack)

        button_layout.addStretch()

        self.btn_delete_selected = QPushButton("🗑️ Delete Selected")
        self.btn_delete_selected.setEnabled(False)
        self.btn_delete_selected.clicked.connect(self._on_delete_selected)
        self.btn_delete_selected.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #999;
            }
        """)
        button_layout.addWidget(self.btn_delete_selected)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                background-color: #f5f5f5;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
        """)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _load_stack(self):
        """Load stack and members from database."""
        try:
            from repository.stack_repository import StackRepository
            from repository.photo_repository import PhotoRepository
            from repository.base_repository import DatabaseConnection

            # Initialize repositories
            db_conn = DatabaseConnection()
            stack_repo = StackRepository(db_conn)
            photo_repo = PhotoRepository(db_conn)

            # Load stack
            self.stack = stack_repo.get_stack_by_id(self.project_id, self.stack_id)
            if not self.stack:
                QMessageBox.warning(self, "Stack Not Found", f"Stack #{self.stack_id} not found.")
                self.reject()
                return

            # Load members
            self.members = stack_repo.list_stack_members(self.project_id, self.stack_id)

            # Load photo details
            for member in self.members:
                photo_id = member['photo_id']
                photo = photo_repo.get_by_id(photo_id)
                if photo:
                    self.photos[photo_id] = photo

            logger.info(f"Loaded stack {self.stack_id} with {len(self.members)} members")

            # Update UI
            self._update_ui()

        except Exception as e:
            logger.error(f"Failed to load stack: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error Loading Stack",
                f"Failed to load stack:\n{e}"
            )
            self.reject()

    def _update_ui(self):
        """Update UI with loaded stack data."""
        # Update title and info
        stack_type = self.stack.get('stack_type', 'unknown')
        member_count = len(self.members)
        self.title_label.setText(f"📚 {stack_type.replace('_', ' ').title()} Stack")
        self.info_label.setText(f"Stack #{self.stack_id} • {member_count} members")

        # Populate members grid (3 columns)
        rep_photo_id = self.stack.get('representative_photo_id')

        for idx, member in enumerate(self.members):
            photo_id = member['photo_id']
            photo = self.photos.get(photo_id)

            if not photo:
                continue

            is_representative = (photo_id == rep_photo_id)

            widget = StackMemberWidget(
                photo=photo,
                similarity_score=member.get('similarity_score'),
                rank=member.get('rank'),
                is_representative=is_representative,
                parent=self
            )
            widget.selection_changed.connect(self._on_member_selection_changed)

            row = idx // 3
            col = idx % 3
            self.members_grid.addWidget(widget, row, col)

        # Populate comparison table
        self._populate_comparison_table()

    def _populate_comparison_table(self):
        """Populate metadata comparison table."""
        if not self.photos:
            return

        # Define columns
        headers = ["Photo", "Resolution", "File Size", "Date Taken", "Similarity", "Rank"]
        self.comparison_table.setColumnCount(len(headers))
        self.comparison_table.setHorizontalHeaderLabels(headers)
        self.comparison_table.setRowCount(len(self.members))

        # Populate rows
        rep_photo_id = self.stack.get('representative_photo_id')

        for row_idx, member in enumerate(self.members):
            photo_id = member['photo_id']
            photo = self.photos.get(photo_id)

            if not photo:
                continue

            is_representative = (photo_id == rep_photo_id)

            # Photo name
            path = photo.get('path', '')
            filename = Path(path).name
            item = QTableWidgetItem(filename)
            if is_representative:
                item.setBackground(QColor(255, 245, 230))  # Light orange
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            item.setToolTip(path)
            self.comparison_table.setItem(row_idx, 0, item)

            # Resolution
            width = photo.get('width', 0)
            height = photo.get('height', 0)
            item = QTableWidgetItem(f"{width}×{height}")
            item.setTextAlignment(Qt.AlignCenter)
            self.comparison_table.setItem(row_idx, 1, item)

            # File size
            size_kb = photo.get('size_kb', 0)
            if size_kb >= 1024:
                size_str = f"{size_kb/1024:.2f} MB"
            else:
                size_str = f"{size_kb:.1f} KB"
            item = QTableWidgetItem(size_str)
            item.setTextAlignment(Qt.AlignCenter)
            self.comparison_table.setItem(row_idx, 2, item)

            # Date taken
            date_taken = photo.get('date_taken', 'Unknown')
            item = QTableWidgetItem(date_taken)
            item.setTextAlignment(Qt.AlignCenter)
            self.comparison_table.setItem(row_idx, 3, item)

            # Similarity score
            similarity = member.get('similarity_score')
            if similarity is not None:
                item = QTableWidgetItem(f"{similarity*100:.1f}%")
            else:
                item = QTableWidgetItem("N/A")
            item.setTextAlignment(Qt.AlignCenter)
            self.comparison_table.setItem(row_idx, 4, item)

            # Rank
            rank = member.get('rank')
            if rank is not None:
                item = QTableWidgetItem(f"#{rank}")
            else:
                item = QTableWidgetItem("N/A")
            item.setTextAlignment(Qt.AlignCenter)
            self.comparison_table.setItem(row_idx, 5, item)

        # Resize columns
        self.comparison_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(headers)):
            self.comparison_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)

    @Slot(int, bool)
    def _on_member_selection_changed(self, photo_id: int, is_selected: bool):
        """Handle member selection change."""
        if is_selected:
            self.selected_photos.add(photo_id)
        else:
            self.selected_photos.discard(photo_id)

        self.btn_delete_selected.setEnabled(len(self.selected_photos) > 0)

    def _on_delete_selected(self):
        """Handle delete selected button click."""
        if not self.selected_photos:
            return

        photo_ids = list(self.selected_photos)

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Delete {len(photo_ids)} selected photo(s)?\n\n"
            "This will:\n"
            "• Delete photo files from disk\n"
            "• Remove photos from database\n"
            "• Remove from stack\n"
            "• Update asset representatives if needed\n\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # Import services
                from services.asset_service import AssetService
                from repository.asset_repository import AssetRepository
                from repository.photo_repository import PhotoRepository
                from repository.base_repository import DatabaseConnection

                # Initialize services
                db_conn = DatabaseConnection()
                photo_repo = PhotoRepository(db_conn)
                asset_repo = AssetRepository(db_conn)
                asset_service = AssetService(photo_repo, asset_repo)

                # Perform deletion
                logger.info(f"Deleting {len(photo_ids)} photos from stack {self.stack_id}: {photo_ids}")
                result = asset_service.delete_duplicate_photos(
                    project_id=self.project_id,
                    photo_ids=photo_ids,
                    delete_files=True
                )

                # Check for errors
                if not result.get('success', False):
                    error_msg = result.get('error', 'Unknown error')
                    raise Exception(error_msg)

                # Show success message
                photos_deleted = result.get('photos_deleted', 0)
                files_deleted = result.get('files_deleted', 0)
                updated_reps = result.get('updated_representatives', [])

                success_msg = f"Successfully deleted {photos_deleted} photo(s).\n\n"
                success_msg += f"• {files_deleted} file(s) removed from disk\n"

                if updated_reps:
                    success_msg += f"• Updated {len(updated_reps)} asset representative(s)\n"

                errors = result.get('errors', [])
                if errors:
                    success_msg += f"\n⚠️ {len(errors)} error(s) occurred:\n"
                    for error in errors[:3]:  # Show first 3 errors
                        success_msg += f"  • {error}\n"

                QMessageBox.information(
                    self,
                    "Deletion Complete",
                    success_msg
                )

                logger.info(f"Deletion complete: {result}")

                # Emit signal
                self.stack_action_taken.emit("delete", self.stack_id)

                # Reload the stack view
                self._load_stack()

            except Exception as e:
                logger.error(f"Failed to delete photos: {e}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Deletion Failed",
                    f"Failed to delete photos:\n{e}\n\nPlease check the log for details."
                )

    def _on_unstack_all(self):
        """Handle unstack all button click."""
        reply = QMessageBox.question(
            self,
            "Confirm Unstack",
            f"Remove all {len(self.members)} photos from this stack?\n\n"
            "Photos will not be deleted, only unstacked.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                from repository.stack_repository import StackRepository
                from repository.base_repository import DatabaseConnection

                db_conn = DatabaseConnection()
                stack_repo = StackRepository(db_conn)

                # Delete the stack (CASCADE will remove members)
                stack_repo.delete({"stack_id": self.stack_id, "project_id": self.project_id})

                QMessageBox.information(self, "Success", "Stack has been removed.")
                self.stack_action_taken.emit("unstack", self.stack_id)
                self.accept()

            except Exception as e:
                logger.error(f"Failed to unstack: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to unstack:\n{e}")
