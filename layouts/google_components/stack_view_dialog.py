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
    QGroupBox, QSlider
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

        # Smart action: Keep Best (auto-select all except representative)
        self.btn_keep_best = QPushButton("⭐ Keep Best")
        self.btn_keep_best.clicked.connect(self._on_keep_best)
        self.btn_keep_best.setToolTip("Automatically keep the best quality photo and select others for deletion")
        self.btn_keep_best.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        button_layout.addWidget(self.btn_keep_best)

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

    def _on_keep_best(self):
        """
        Handle 'Keep Best' button click.

        Automatically selects all photos except the representative for deletion.
        This is a smart action based on Google Photos and iPhone Photos best practices.
        """
        rep_photo_id = self.stack.get('representative_photo_id')

        if not rep_photo_id:
            QMessageBox.warning(
                self,
                "No Representative",
                "Cannot use 'Keep Best' - no representative photo is set for this stack."
            )
            return

        # Find all member widgets and select them (except representative)
        selected_count = 0
        for i in range(self.members_grid.count()):
            item = self.members_grid.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, StackMemberWidget):
                    # Select if not representative
                    if not widget.is_representative:
                        widget.checkbox.setChecked(True)
                        selected_count += 1

        # Show confirmation
        if selected_count > 0:
            QMessageBox.information(
                self,
                "Photos Selected",
                f"Selected {selected_count} photo(s) for deletion.\n\n"
                f"The best quality photo (representative) will be kept.\n"
                f"Click 'Delete Selected' to proceed."
            )
        else:
            QMessageBox.information(
                self,
                "No Photos to Select",
                "All photos in this stack are already optimal (only representative exists)."
            )

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


# =============================================================================
# STACK BROWSER DIALOG
# =============================================================================

class StackBrowserDialog(QDialog):
    """
    Dialog for browsing all similar shot stacks.

    Features:
    - Grid view of all stack thumbnails
    - Similarity threshold slider (50-100%)
    - Real-time filtering based on similarity
    - Click to open detailed StackViewDialog
    - Total count indicator

    Based on best practices from Google Photos and iPhone Photos.
    """

    def __init__(self, project_id: int, stack_type: str = "similar", parent=None):
        """
        Initialize StackBrowserDialog.

        Args:
            project_id: Project ID
            stack_type: Stack type ("similar" or other)
            parent: Parent widget
        """
        super().__init__(parent)
        self.project_id = project_id
        self.stack_type = stack_type
        self.all_stacks = []  # All stacks from DB
        self.filtered_stacks = []  # Filtered by similarity threshold
        self.similarity_threshold = 0.92  # Default 92% (matches StackGenParams)

        self.setWindowTitle("Similar Photos" if stack_type == "similar" else "Photo Stacks")
        self.setMinimumSize(1000, 700)

        self._init_ui()
        self._load_stacks()

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header_layout = QHBoxLayout()

        # Title
        title_label = QLabel("📸 Similar Photos")
        title_label.setStyleSheet("font-size: 18pt; font-weight: bold; color: #2196F3;")
        header_layout.addWidget(title_label)

        header_layout.addStretch(1)

        # Count indicator
        self.count_label = QLabel("Loading...")
        self.count_label.setStyleSheet("font-size: 11pt; color: #666;")
        header_layout.addWidget(self.count_label)

        layout.addLayout(header_layout)

        # Similarity threshold slider
        slider_container = self._create_similarity_slider()
        layout.addWidget(slider_container)

        # Stack grid (scroll area)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ddd;
                border-radius: 8px;
                background-color: #f9f9f9;
            }
        """)

        # Grid container
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(16)
        self.grid_layout.setContentsMargins(16, 16, 16, 16)

        self.scroll_area.setWidget(self.grid_container)
        layout.addWidget(self.scroll_area, 1)  # Stretch to fill

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _create_similarity_slider(self) -> QWidget:
        """Create similarity threshold slider."""
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setSpacing(8)

        # Label row
        label_row = QHBoxLayout()
        label = QLabel("🎚️ Similarity Threshold:")
        label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        label_row.addWidget(label)

        self.threshold_value_label = QLabel(f"{int(self.similarity_threshold * 100)}%")
        self.threshold_value_label.setStyleSheet("font-size: 11pt; color: #2196F3; font-weight: bold;")
        label_row.addWidget(self.threshold_value_label)

        label_row.addStretch(1)

        # Help text
        help_label = QLabel("Lower = more photos (includes less similar) • Higher = fewer photos (only very similar)")
        help_label.setStyleSheet("font-size: 9pt; color: #999;")
        label_row.addWidget(help_label)

        layout.addLayout(label_row)

        # Slider row
        slider_row = QHBoxLayout()

        min_label = QLabel("50%")
        min_label.setStyleSheet("font-size: 9pt; color: #666;")
        slider_row.addWidget(min_label)

        self.similarity_slider = QSlider(Qt.Horizontal)
        self.similarity_slider.setMinimum(50)  # 50% minimum
        self.similarity_slider.setMaximum(100)  # 100% maximum
        self.similarity_slider.setValue(int(self.similarity_threshold * 100))
        self.similarity_slider.setTickPosition(QSlider.TicksBelow)
        self.similarity_slider.setTickInterval(10)
        self.similarity_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #bbb;
                background: #e0e0e0;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #2196F3;
                border: 2px solid #1976D2;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #1976D2;
            }
        """)
        self.similarity_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.similarity_slider, 1)

        max_label = QLabel("100%")
        max_label.setStyleSheet("font-size: 9pt; color: #666;")
        slider_row.addWidget(max_label)

        layout.addLayout(slider_row)

        return container

    def _on_slider_changed(self, value: int):
        """Handle slider value change."""
        self.similarity_threshold = value / 100.0
        self.threshold_value_label.setText(f"{value}%")

        # Re-filter and display stacks
        self._filter_and_display_stacks()

    def _load_stacks(self):
        """Load all stacks from database."""
        try:
            from repository.stack_repository import StackRepository
            from repository.base_repository import DatabaseConnection

            db_conn = DatabaseConnection()
            stack_repo = StackRepository(db_conn)

            # Get all stacks of the specified type for this project
            stacks = stack_repo.list_stacks(
                project_id=self.project_id,
                stack_type=self.stack_type
            )

            # Load members for each stack
            self.all_stacks = []
            for stack in stacks:
                stack_id = stack['stack_id']
                members = stack_repo.list_stack_members(
                    project_id=self.project_id,
                    stack_id=stack_id
                )
                stack['members'] = members
                self.all_stacks.append(stack)

            logger.info(f"Loaded {len(self.all_stacks)} {self.stack_type} stacks")

            # Filter and display
            self._filter_and_display_stacks()

        except Exception as e:
            logger.error(f"Failed to load stacks: {e}", exc_info=True)
            self.count_label.setText("Error loading stacks")
            QMessageBox.critical(self, "Error", f"Failed to load stacks:\n{e}")

    def _filter_and_display_stacks(self):
        """
        Filter stacks by similarity threshold and display.

        Based on Google Photos / iPhone Photos best practices:
        - Always show all stack groups (don't hide groups)
        - Filter MEMBERS within each stack based on similarity threshold
        - Lower threshold = MORE photos visible (includes less similar)
        - Higher threshold = FEWER photos visible (only very similar)
        - Hide stacks that have no members after filtering
        """
        # Filter members within each stack based on similarity threshold
        self.filtered_stacks = []

        for stack in self.all_stacks:
            members = stack.get('members', [])
            if not members:
                continue

            # Filter members by similarity threshold
            filtered_members = []
            for member in members:
                similarity = member.get('similarity_score', 0.0)
                # Include member if similarity >= threshold OR if it's the representative
                # Representative should always be included regardless of score
                photo_id = member.get('photo_id')
                is_representative = (photo_id == stack.get('representative_photo_id'))

                if is_representative or similarity >= self.similarity_threshold:
                    filtered_members.append(member)

            # Only include stack if it has at least 2 photos after filtering
            # (representative + at least 1 similar photo)
            if len(filtered_members) >= 2:
                # Create a copy of the stack with filtered members
                filtered_stack = stack.copy()
                filtered_stack['members'] = filtered_members
                self.filtered_stacks.append(filtered_stack)

        # Update count label
        total_photos = sum(len(stack.get('members', [])) for stack in self.filtered_stacks)
        self.count_label.setText(
            f"{len(self.filtered_stacks)} groups • {total_photos} photos"
        )

        # Display stacks
        self._display_stacks()

    def _display_stacks(self):
        """Display filtered stacks in grid."""
        # Clear existing widgets
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # If no stacks, show message
        if not self.filtered_stacks:
            no_stacks_label = QLabel(
                "No similar photo groups found.\n\n"
                f"At {int(self.similarity_threshold * 100)}% threshold, groups need at least 2 photos.\n"
                "Try lowering the threshold to see more photos in each group."
            )
            no_stacks_label.setAlignment(Qt.AlignCenter)
            no_stacks_label.setStyleSheet("color: #999; font-size: 12pt; padding: 40px;")
            self.grid_layout.addWidget(no_stacks_label, 0, 0)
            return

        # Add stack cards to grid (3 columns)
        for i, stack in enumerate(self.filtered_stacks):
            row = i // 3
            col = i % 3

            card = self._create_stack_card(stack)
            self.grid_layout.addWidget(card, row, col)

    def _create_stack_card(self, stack: dict) -> QWidget:
        """Create a clickable card for a stack."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 8px;
            }
            QFrame:hover {
                border-color: #2196F3;
                background-color: #f5f9ff;
            }
        """)
        card.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        # Representative thumbnail
        thumbnail_label = QLabel()
        thumbnail_label.setFixedSize(200, 200)
        thumbnail_label.setAlignment(Qt.AlignCenter)
        thumbnail_label.setStyleSheet("""
            QLabel {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)

        # Load representative photo thumbnail
        rep_photo_id = stack.get('representative_photo_id')
        if rep_photo_id:
            try:
                from repository.photo_repository import PhotoRepository
                from repository.base_repository import DatabaseConnection
                from app_services import get_thumbnail

                db_conn = DatabaseConnection()
                photo_repo = PhotoRepository(db_conn)
                photo = photo_repo.get_by_id(rep_photo_id)

                if photo:
                    path = photo.get('path', '')
                    if path and Path(path).exists():
                        pixmap = get_thumbnail(path, 200)
                        if pixmap:
                            thumbnail_label.setPixmap(pixmap)
                        else:
                            thumbnail_label.setText("No Preview")
                    else:
                        thumbnail_label.setText("File Not Found")
                else:
                    thumbnail_label.setText("No Photo")
            except Exception as e:
                logger.warning(f"Failed to load thumbnail: {e}")
                thumbnail_label.setText("Preview Error")
        else:
            thumbnail_label.setText("No Representative")

        layout.addWidget(thumbnail_label)

        # Stack info
        members = stack.get('members', [])
        info_label = QLabel(f"📸 {len(members)} similar photos")
        info_label.setStyleSheet("font-weight: bold; font-size: 10pt; color: #333;")
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)

        # Max similarity
        max_similarity = 0.0
        for member in members:
            similarity = member.get('similarity_score', 0.0)
            if similarity > max_similarity:
                max_similarity = similarity

        if max_similarity > 0:
            similarity_label = QLabel(f"🔗 Up to {int(max_similarity * 100)}% similar")
            similarity_label.setStyleSheet("font-size: 9pt; color: #2196F3;")
            similarity_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(similarity_label)

        # Make clickable
        stack_id = stack.get('stack_id')
        card.mousePressEvent = lambda event: self._on_stack_clicked(stack_id)

        return card

    def _on_stack_clicked(self, stack_id: int):
        """Handle stack card click - open detailed view."""
        try:
            # Open detailed StackViewDialog
            dialog = StackViewDialog(
                project_id=self.project_id,
                stack_id=stack_id,
                parent=self
            )

            # Connect signal to refresh this browser
            dialog.stack_action_taken.connect(self._on_stack_action)

            dialog.exec()

        except Exception as e:
            logger.error(f"Failed to open stack view: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to open stack view:\n{e}")

    def _on_stack_action(self, action: str, stack_id: int):
        """Handle action taken in stack view dialog."""
        logger.info(f"Stack action: {action} on stack {stack_id}")

        # Reload stacks to reflect changes
        self._load_stacks()
