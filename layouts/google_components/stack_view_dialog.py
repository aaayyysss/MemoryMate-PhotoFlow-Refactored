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
    QGroupBox, QSlider, QTabWidget
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
        photo_id = self.photo.get('id')
        logger.debug(f"[SELECTION] StackMemberWidget checkbox changed: state={state}, is_selected={is_selected}, photo_id={photo_id}, photo_keys={list(self.photo.keys())}")

        if photo_id is None:
            logger.error(f"[SELECTION] ERROR: Photo dict has no 'id' field! Keys: {list(self.photo.keys())}, Photo: {self.photo}")
            return

        logger.debug(f"[SELECTION] Emitting selection_changed signal: photo_id={photo_id}, is_selected={is_selected}")
        self.selection_changed.emit(photo_id, is_selected)

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
            photo_id_for_log = photo.get('id', 'MISSING_ID')
            logger.debug(f"[SIGNAL_CONNECT] Connected selection signal for photo {photo_id_for_log} (rep={is_representative}), photo_keys={list(photo.keys())}")

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
        logger.debug(f"[HANDLER] ====== RECEIVED SELECTION SIGNAL ======")
        logger.debug(f"[HANDLER] photo_id={photo_id}, is_selected={is_selected}, type(photo_id)={type(photo_id)}")
        logger.debug(f"[HANDLER] Current selected_photos before update: {self.selected_photos}")

        if is_selected:
            self.selected_photos.add(photo_id)
            logger.debug(f"[HANDLER] Added {photo_id} to selected_photos")
        else:
            self.selected_photos.discard(photo_id)
            logger.debug(f"[HANDLER] Removed {photo_id} from selected_photos")

        # Update button state
        is_enabled = len(self.selected_photos) > 0
        logger.debug(f"[HANDLER] Current selected_photos after update: {self.selected_photos}")
        logger.debug(f"[HANDLER] Delete button enabled: {is_enabled} (selected count: {len(self.selected_photos)})")
        logger.debug(f"[HANDLER] Delete button object: {self.btn_delete_selected}, current enabled state: {self.btn_delete_selected.isEnabled()}")

        self.btn_delete_selected.setEnabled(is_enabled)

        logger.debug(f"[HANDLER] Delete button enabled state AFTER setEnabled({is_enabled}): {self.btn_delete_selected.isEnabled()}")
        logger.debug(f"[HANDLER] ====== END SELECTION SIGNAL ======\n")

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
            stack_type: Stack type ("similar" for time-based, ignored when tabs are used)
            parent: Parent widget
        """
        super().__init__(parent)
        self.project_id = project_id
        self.stack_type = stack_type

        # Similar Shots mode data
        self.all_stacks = []  # All stacks from DB
        self.filtered_stacks = []  # Filtered by similarity threshold

        # People mode data
        self.all_people = []  # All people from face detection
        self.selected_person = None  # Currently selected person for detail view

        self.similarity_threshold = 0.92  # Default 92% (matches StackGenParams)
        self.current_mode = "similar"  # "similar" or "people"

        # Track all threshold labels for updating when slider changes
        self.threshold_labels = []  # List of all QLabel widgets showing threshold

        self.setWindowTitle("Similar Photos & People")
        self.setMinimumSize(1000, 700)

        logger.debug("[__INIT__] Starting _init_ui()")
        self._init_ui()
        logger.debug("[__INIT__] Finished _init_ui(), starting _load_current_mode_data()")
        self._load_current_mode_data()
        logger.debug("[__INIT__] Finished initialization")

    def _init_ui(self):
        """Initialize UI components with tabs for Similar Shots and People."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header_layout = QHBoxLayout()

        # Title
        title_label = QLabel("📸 Similar Photos & People")
        title_label.setStyleSheet("font-size: 18pt; font-weight: bold; color: #2196F3;")
        header_layout.addWidget(title_label)

        header_layout.addStretch(1)

        # Count indicator
        self.count_label = QLabel("Loading...")
        self.count_label.setStyleSheet("font-size: 11pt; color: #666;")
        header_layout.addWidget(self.count_label)

        layout.addLayout(header_layout)

        # Tabs for Similar Shots vs People
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 4px;
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 2px solid #2196F3;
            }
            QTabBar::tab:hover {
                background-color: #e8f4f8;
            }
        """)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Tab 1: Similar Shots (time-based visual similarity)
        similar_tab = QWidget()
        similar_layout = QVBoxLayout(similar_tab)
        similar_layout.setSpacing(12)
        similar_layout.setContentsMargins(12, 12, 12, 12)

        # Similarity threshold slider
        self.slider_container = self._create_similarity_slider()
        similar_layout.addWidget(self.slider_container)

        # Info banner showing generation parameters
        # Store layout reference for proper banner updates
        self.similar_layout = similar_layout
        logger.debug(f"[INIT_UI] Creating initial info banner, layout has {similar_layout.count()} widgets")
        self.info_banner = self._create_info_banner()
        similar_layout.addWidget(self.info_banner)
        logger.debug(f"[INIT_UI] Added info banner, layout now has {similar_layout.count()} widgets")

        # Stack grid (scroll area)
        self.similar_scroll_area = QScrollArea()
        self.similar_scroll_area.setWidgetResizable(True)
        self.similar_scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ddd;
                border-radius: 8px;
                background-color: #f9f9f9;
            }
        """)

        self.similar_grid_container = QWidget()
        self.similar_grid_layout = QGridLayout(self.similar_grid_container)
        self.similar_grid_layout.setSpacing(16)
        self.similar_grid_layout.setContentsMargins(16, 16, 16, 16)

        self.similar_scroll_area.setWidget(self.similar_grid_container)
        similar_layout.addWidget(self.similar_scroll_area, 1)

        self.tabs.addTab(similar_tab, "⏱️ Similar Shots")

        # Tab 2: People (face-based grouping)
        people_tab = QWidget()
        people_layout = QVBoxLayout(people_tab)
        people_layout.setSpacing(12)
        people_layout.setContentsMargins(12, 12, 12, 12)

        # People slider (reuse similarity slider concept)
        self.people_slider_container = self._create_people_slider()
        people_layout.addWidget(self.people_slider_container)

        # People grid (scroll area)
        self.people_scroll_area = QScrollArea()
        self.people_scroll_area.setWidgetResizable(True)
        self.people_scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ddd;
                border-radius: 8px;
                background-color: #f9f9f9;
            }
        """)

        self.people_grid_container = QWidget()
        self.people_grid_layout = QGridLayout(self.people_grid_container)
        self.people_grid_layout.setSpacing(16)
        self.people_grid_layout.setContentsMargins(16, 16, 16, 16)

        self.people_scroll_area.setWidget(self.people_grid_container)
        people_layout.addWidget(self.people_scroll_area, 1)

        self.tabs.addTab(people_tab, "👤 People")

        layout.addWidget(self.tabs, 1)

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

        threshold_value_label = QLabel(f"{int(self.similarity_threshold * 100)}%")
        threshold_value_label.setStyleSheet("font-size: 11pt; color: #2196F3; font-weight: bold;")
        label_row.addWidget(threshold_value_label)

        # Register this label for updates when slider changes
        self.threshold_labels.append(threshold_value_label)

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

        # Update ALL threshold labels (both tabs have sliders)
        for label in self.threshold_labels:
            label.setText(f"{value}%")

        # Re-filter and display based on current mode
        if self.current_mode == "similar":
            self._filter_and_display_stacks()
        elif self.current_mode == "people":
            self._display_people()  # Re-filter people view

    def _create_info_banner(self) -> QWidget:
        """Create info banner showing generation parameters and tips."""
        logger.debug("[CREATE_BANNER] Creating new info banner widget")
        banner = QFrame()
        banner.setStyleSheet("""
            QFrame {
                background-color: #e8f4f8;
                border: 1px solid #b3d9e6;
                border-radius: 6px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(banner)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 8, 12, 8)

        # Title
        title_label = QLabel("ℹ️ How Similar Photos Work")
        title_label.setStyleSheet("font-weight: bold; font-size: 10pt; color: #0277bd;")
        layout.addWidget(title_label)

        # Explanation
        explanation_text = (
            "• Stacks are created during photo scanning with configurable similarity threshold (default 50%)\n"
            "• The slider above filters which photos to show within each stack\n"
            "• Lower slider = more photos visible | Higher slider = only very similar photos\n"
            "• If you don't see expected photos, they may have been excluded during scanning"
        )

        # Add generation threshold info if we can infer it
        if self.all_stacks:
            min_similarity = self._get_minimum_similarity_in_stacks()
            if min_similarity:
                generation_threshold = int(min_similarity * 100)
                explanation_text += f"\n\n📊 Estimated generation threshold: ~{generation_threshold}%"

                # Warn if viewing threshold is lower than generation
                if self.similarity_threshold < min_similarity:
                    warning_text = f" ⚠️ Your slider is at {int(self.similarity_threshold * 100)}%, but stacks were generated at ~{generation_threshold}%"
                    explanation_text += f"\n{warning_text}"

        explanation = QLabel(explanation_text)
        explanation.setStyleSheet("font-size: 9pt; color: #01579b; line-height: 1.4;")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        # Stale stack warning
        if hasattr(self, 'stale_photo_count') and self.stale_photo_count > 0:
            warning_frame = QFrame()
            warning_frame.setStyleSheet("""
                QFrame {
                    background-color: #fff3cd;
                    border: 1px solid #ffc107;
                    border-radius: 4px;
                    padding: 8px;
                    margin-top: 6px;
                }
            """)
            warning_layout = QHBoxLayout(warning_frame)
            warning_layout.setContentsMargins(8, 4, 8, 4)

            warning_label = QLabel(
                f"⚠️ {self.stale_photo_count} new photo(s) added since last stack generation. "
                f"Regenerate to include them in grouping."
            )
            warning_label.setStyleSheet("font-size: 9pt; color: #856404; font-weight: bold;")
            warning_label.setWordWrap(True)
            warning_layout.addWidget(warning_label, 1)

            layout.addWidget(warning_frame)

        # Action row
        action_row = QHBoxLayout()

        tip_label = QLabel("💡 Tip: To see more photos, regenerate stacks with lower similarity threshold")
        tip_label.setStyleSheet("font-size: 9pt; color: #0277bd; font-style: italic;")
        tip_label.setWordWrap(True)
        action_row.addWidget(tip_label, 1)

        # Regenerate button
        self.btn_regenerate = QPushButton("🔄 Regenerate Stacks")
        self.btn_regenerate.setToolTip("Re-scan photos and create new similarity stacks with optimized settings")
        self.btn_regenerate.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.btn_regenerate.clicked.connect(self._on_regenerate_clicked)
        action_row.addWidget(self.btn_regenerate)

        layout.addLayout(action_row)

        return banner

    def _get_minimum_similarity_in_stacks(self) -> Optional[float]:
        """
        Get the minimum similarity score across all stacks.
        This helps infer what threshold was used during generation.
        """
        if not self.all_stacks:
            return None

        min_sim = 1.0
        for stack in self.all_stacks:
            members = stack.get('members', [])
            for member in members:
                similarity = member.get('similarity_score', 1.0)
                if similarity < min_sim and similarity > 0:  # Exclude 0 scores
                    min_sim = similarity

        return min_sim if min_sim < 1.0 else None

    def _check_stale_stacks(self):
        """
        Check if stacks are stale (new photos added since generation).
        Shows a warning banner if stale.
        """
        try:
            from repository.photo_repository import PhotoRepository
            from repository.base_repository import DatabaseConnection

            # Get the newest stack's creation time
            if not self.all_stacks:
                return

            newest_stack_time = None
            for stack in self.all_stacks:
                created_at = stack.get('created_at')
                if created_at:
                    if newest_stack_time is None or created_at > newest_stack_time:
                        newest_stack_time = created_at

            if not newest_stack_time:
                return

            # Count photos added after stack generation
            db_conn = DatabaseConnection()
            photo_repo = PhotoRepository(db_conn)

            # Get count of photos created after the stack generation
            import sqlite3
            conn = sqlite3.connect(db_conn.db_file)
            cursor = conn.execute("""
                SELECT COUNT(*)
                FROM photo_metadata
                WHERE project_id = ?
                AND created_at > ?
                AND created_ts IS NOT NULL
            """, (self.project_id, newest_stack_time))

            new_photo_count = cursor.fetchone()[0]
            conn.close()

            if new_photo_count > 0:
                self.stale_photo_count = new_photo_count
                logger.info(f"Detected {new_photo_count} new photos since last stack generation")
            else:
                self.stale_photo_count = 0

        except Exception as e:
            logger.warning(f"Failed to check stale stacks: {e}")
            self.stale_photo_count = 0

    def _update_info_banner(self):
        """Update info banner with current stack information."""
        logger.debug("[UPDATE_BANNER] Called _update_info_banner()")
        logger.debug(f"[UPDATE_BANNER] Layout has {self.similar_layout.count()} widgets before update")

        if not hasattr(self, 'info_banner') or not hasattr(self, 'similar_layout'):
            logger.warning("[UPDATE_BANNER] Missing info_banner or similar_layout, skipping update")
            return

        # Find the index of the old banner
        index = self.similar_layout.indexOf(self.info_banner)
        logger.debug(f"[UPDATE_BANNER] Found old banner at index {index}")

        if index < 0:
            logger.warning("[UPDATE_BANNER] Could not find info banner in layout")
            return

        # Remove old banner
        logger.debug(f"[UPDATE_BANNER] Removing widget at index {index}")
        self.similar_layout.removeWidget(self.info_banner)
        logger.debug(f"[UPDATE_BANNER] Layout has {self.similar_layout.count()} widgets after removeWidget()")

        # CRITICAL: Must hide the widget before deleteLater() to prevent it from being visible
        # removeWidget() only removes from layout management, widget is still a child of parent widget
        self.info_banner.hide()
        self.info_banner.setParent(None)  # Remove from parent widget's children
        self.info_banner.deleteLater()

        # Create and insert new banner at same position
        logger.debug(f"[UPDATE_BANNER] Creating new banner and inserting at index {index}")
        self.info_banner = self._create_info_banner()
        self.similar_layout.insertWidget(index, self.info_banner)
        logger.debug(f"[UPDATE_BANNER] Layout now has {self.similar_layout.count()} widgets after insertWidget()")

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

            # Check for stale stacks (new photos added since generation)
            self._check_stale_stacks()

            # Update info banner with generation threshold info
            logger.debug("[LOAD_STACKS] About to call _update_info_banner()")
            self._update_info_banner()
            logger.debug("[LOAD_STACKS] Returned from _update_info_banner()")

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
        logger.debug(f"[DISPLAY_STACKS] Clearing grid with {self.similar_grid_layout.count()} widgets")

        # Clear existing widgets
        while self.similar_grid_layout.count():
            item = self.similar_grid_layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                logger.debug(f"[DISPLAY_STACKS] Removing widget: {type(widget).__name__}")
                # CRITICAL: Must hide and remove from parent before deleteLater()
                # takeAt() only removes from layout, widget is still visible as child of parent
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        logger.debug(f"[DISPLAY_STACKS] Grid cleared, displaying {len(self.filtered_stacks)} stacks")

        # If no stacks, show message
        if not self.filtered_stacks:
            no_stacks_label = QLabel(
                "No similar photo groups found.\n\n"
                f"At {int(self.similarity_threshold * 100)}% threshold, groups need at least 2 photos.\n"
                "Try lowering the threshold to see more photos in each group."
            )
            no_stacks_label.setAlignment(Qt.AlignCenter)
            no_stacks_label.setStyleSheet("color: #999; font-size: 12pt; padding: 40px;")
            self.similar_grid_layout.addWidget(no_stacks_label, 0, 0)
            return

        # Add stack cards to grid (3 columns)
        for i, stack in enumerate(self.filtered_stacks):
            row = i // 3
            col = i % 3

            card = self._create_stack_card(stack)
            self.similar_grid_layout.addWidget(card, row, col)

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

    def _on_regenerate_clicked(self):
        """Handle regenerate stacks button click."""
        try:
            # Confirm with user
            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self,
                "Regenerate Stacks",
                "This will:\n"
                "• Delete all existing similar photo stacks\n"
                "• Re-analyze all photos with optimized settings\n"
                "• Use lower similarity threshold (50%) to capture more photos\n"
                "• Use larger time window (30s) for better grouping\n\n"
                "This may take several minutes for large photo collections.\n\n"
                "Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

            # Import necessary modules
            from services.stack_generation_service import StackGenerationService, StackGenParams
            from services.photo_similarity_service import PhotoSimilarityService
            from repository.photo_repository import PhotoRepository
            from repository.stack_repository import StackRepository
            from repository.base_repository import DatabaseConnection

            # Initialize services
            db_conn = DatabaseConnection()
            photo_repo = PhotoRepository(db_conn)
            stack_repo = StackRepository(db_conn)
            similarity_service = PhotoSimilarityService()

            stack_gen_service = StackGenerationService(
                photo_repo=photo_repo,
                stack_repo=stack_repo,
                similarity_service=similarity_service
            )

            # Create optimized parameters
            params = StackGenParams(
                rule_version="1",
                time_window_seconds=30,  # Larger time window
                min_stack_size=2,  # Smaller minimum
                similarity_threshold=0.50,  # Lower threshold
                top_k=30,
                candidate_limit_per_photo=300
            )

            # Show progress dialog
            from PySide6.QtWidgets import QProgressDialog
            progress = QProgressDialog(
                "Regenerating similar photo stacks...\nThis may take a few minutes.",
                "Cancel",
                0,
                0,
                self
            )
            progress.setWindowTitle("Processing")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()

            # Run regeneration
            stats = stack_gen_service.regenerate_similar_shot_stacks(
                project_id=self.project_id,
                params=params
            )

            progress.close()

            # Show results
            QMessageBox.information(
                self,
                "Regeneration Complete",
                f"Successfully regenerated similar photo stacks:\n\n"
                f"• Photos analyzed: {stats.photos_considered}\n"
                f"• Stacks created: {stats.stacks_created}\n"
                f"• Photo memberships: {stats.memberships_created}\n"
                f"• Errors: {stats.errors}\n\n"
                f"The slider now controls filtering from 50-100%."
            )

            # Reload stacks
            self._load_stacks()

        except Exception as e:
            logger.error(f"Failed to regenerate stacks: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to regenerate stacks:\n{e}\n\n"
                f"Check the log for details."
            )

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

    # =========================================================================
    # PEOPLE MODE (Face-based grouping)
    # =========================================================================

    def _create_people_slider(self) -> QWidget:
        """Create similarity threshold slider for people view."""
        # Reuse the same slider creation logic
        return self._create_similarity_slider()

    def _on_tab_changed(self, index: int):
        """Handle tab change between Similar Shots and People."""
        if index == 0:
            self.current_mode = "similar"
        elif index == 1:
            self.current_mode = "people"

        # Load data for the new mode
        self._load_current_mode_data()

    def _load_current_mode_data(self):
        """Load data based on current mode (similar or people)."""
        if self.current_mode == "similar":
            self._load_stacks()
        elif self.current_mode == "people":
            self._load_people()

    def _load_people(self):
        """Load all people from face detection."""
        try:
            from services.person_stack_service import PersonStackService
            from reference_db import ReferenceDB

            db = ReferenceDB()
            person_service = PersonStackService(db)

            # Get all people in project
            self.all_people = person_service.get_all_people(self.project_id)

            logger.info(f"Loaded {len(self.all_people)} people")

            # Update count
            self.count_label.setText(f"{len(self.all_people)} people detected")

            # Display people
            self._display_people()

            # Note: ReferenceDB uses connection pooling - no need to close

        except Exception as e:
            logger.error(f"Failed to load people: {e}", exc_info=True)
            self.count_label.setText("Error loading people")
            QMessageBox.critical(self, "Error", f"Failed to load people:\n{e}")

    def _display_people(self):
        """Display people in grid."""
        logger.debug(f"[DISPLAY_PEOPLE] Clearing grid with {self.people_grid_layout.count()} widgets")

        # Clear existing widgets
        while self.people_grid_layout.count():
            item = self.people_grid_layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                logger.debug(f"[DISPLAY_PEOPLE] Removing widget: {type(widget).__name__}")
                # CRITICAL: Must hide and remove from parent before deleteLater()
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        logger.debug(f"[DISPLAY_PEOPLE] Grid cleared, displaying {len(self.all_people)} people")

        # If no people, show message
        if not self.all_people:
            no_people_label = QLabel(
                "No people detected in this project.\n\n"
                "Run face detection first to enable person-based grouping."
            )
            no_people_label.setAlignment(Qt.AlignCenter)
            no_people_label.setStyleSheet("color: #999; font-size: 12pt; padding: 40px;")
            self.people_grid_layout.addWidget(no_people_label, 0, 0)
            return

        # Add person cards to grid (3 columns)
        for i, person in enumerate(self.all_people):
            row = i // 3
            col = i % 3

            card = self._create_person_card(person)
            self.people_grid_layout.addWidget(card, row, col)

    def _create_person_card(self, person: dict) -> QWidget:
        """Create a clickable card for a person."""
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

        # Representative face thumbnail
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

        # Load representative face thumbnail
        rep_thumb_png = person.get('rep_thumb_png')
        if rep_thumb_png:
            try:
                from PySide6.QtCore import QByteArray
                from PySide6.QtGui import QImage, QPixmap

                # Convert blob to pixmap
                byte_array = QByteArray(rep_thumb_png)
                image = QImage()
                image.loadFromData(byte_array, "PNG")

                if not image.isNull():
                    pixmap = QPixmap.fromImage(image).scaled(
                        200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    thumbnail_label.setPixmap(pixmap)
                else:
                    thumbnail_label.setText("No Preview")
            except Exception as e:
                logger.warning(f"Failed to load person thumbnail: {e}")
                thumbnail_label.setText("Preview Error")
        else:
            thumbnail_label.setText("No Photo")

        layout.addWidget(thumbnail_label)

        # Person info
        display_name = person.get('display_name', 'Unknown')
        member_count = person.get('member_count', 0)

        name_label = QLabel(display_name)
        name_label.setStyleSheet("font-weight: bold; font-size: 11pt; color: #333;")
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)

        count_label = QLabel(f"📸 {member_count} photos")
        count_label.setStyleSheet("font-size: 9pt; color: #666;")
        count_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(count_label)

        # Make clickable - opens person detail view
        branch_key = person.get('branch_key')
        card.mousePressEvent = lambda event: self._on_person_clicked(branch_key, display_name)

        return card

    def _on_person_clicked(self, branch_key: str, display_name: str):
        """Handle person card click - open photos of this person with similarity filtering."""
        try:
            from services.person_stack_service import PersonStackService
            from reference_db import ReferenceDB

            db = ReferenceDB()
            person_service = PersonStackService(db)

            # Get person photos with similarity filtering
            person_data = person_service.get_person_photos(
                project_id=self.project_id,
                branch_key=branch_key,
                similarity_threshold=self.similarity_threshold
            )

            # Note: ReferenceDB uses connection pooling - no need to close

            # Open PersonPhotosDialog (simplified - show in message for now)
            photos = person_data.get('photos', [])
            if not photos:
                QMessageBox.information(
                    self,
                    f"No Photos - {display_name}",
                    f"No photos found for {display_name} at {int(self.similarity_threshold * 100)}% similarity threshold.\n\n"
                    f"Try lowering the slider to see more photos."
                )
                return

            # TODO: Open a detail dialog showing all photos of this person
            # For now, show count
            QMessageBox.information(
                self,
                f"Photos of {display_name}",
                f"Found {len(photos)} photos of {display_name} at {int(self.similarity_threshold * 100)}% similarity.\n\n"
                f"Detail view coming in next update!"
            )

        except Exception as e:
            logger.error(f"Failed to open person photos: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load person photos:\n{e}")
