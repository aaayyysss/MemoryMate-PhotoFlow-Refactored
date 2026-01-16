# layouts/google_components/duplicates_dialog.py
# Version 01.01.00.00 dated 20260115
# Duplicate review and management dialog for Google Layout

"""
DuplicatesDialog - Review and manage exact duplicates

This dialog shows a list of duplicate assets and allows users to:
- Review duplicate groups
- Compare instances side-by-side
- Keep/delete specific instances
- Set representative photo
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QWidget, QScrollArea,
    QGridLayout, QFrame, QCheckBox, QMessageBox, QSplitter,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Signal, Qt, QSize, Slot, QThreadPool
from PySide6.QtGui import QPixmap, QFont, QColor
from typing import Optional, List, Dict, Any
from pathlib import Path
from logging_config import get_logger

logger = get_logger(__name__)


class PhotoInstanceWidget(QWidget):
    """
    Widget displaying a single photo instance with thumbnail and metadata.

    Shows:
    - Thumbnail
    - Resolution
    - File size
    - Date taken
    - File path
    - Checkbox for selection
    - Representative indicator
    """

    selection_changed = Signal(int, bool)  # photo_id, is_selected

    def __init__(self, photo: Dict[str, Any], is_representative: bool = False, parent=None):
        super().__init__(parent)
        self.photo = photo
        self.is_representative = is_representative

        self._init_ui()
        self._load_thumbnail_async()

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # Thumbnail placeholder
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(200, 200)
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
            rep_label.setStyleSheet("color: #FFA500; font-weight: bold; font-size: 12px;")
            metadata_layout.addWidget(rep_label)

        # Resolution
        width = self.photo.get('width', 0)
        height = self.photo.get('height', 0)
        res_label = QLabel(f"📐 {width}×{height}")
        res_label.setStyleSheet("font-size: 11px; color: #666;")
        metadata_layout.addWidget(res_label)

        # File size
        size_kb = self.photo.get('size_kb', 0)
        if size_kb >= 1024:
            size_str = f"{size_kb/1024:.1f} MB"
        else:
            size_str = f"{size_kb:.1f} KB"
        size_label = QLabel(f"💾 {size_str}")
        size_label.setStyleSheet("font-size: 11px; color: #666;")
        metadata_layout.addWidget(size_label)

        # Date taken
        date_taken = self.photo.get('date_taken', 'Unknown')
        date_label = QLabel(f"📅 {date_taken}")
        date_label.setStyleSheet("font-size: 11px; color: #666;")
        metadata_layout.addWidget(date_label)

        # File path (truncated)
        path = self.photo.get('path', '')
        filename = Path(path).name
        path_label = QLabel(f"📄 {filename}")
        path_label.setToolTip(path)
        path_label.setStyleSheet("font-size: 11px; color: #666;")
        path_label.setWordWrap(True)
        metadata_layout.addWidget(path_label)

        layout.addLayout(metadata_layout)

        # Selection checkbox (disabled for representative)
        self.checkbox = QCheckBox("Select for deletion")
        self.checkbox.setEnabled(not self.is_representative)
        if self.is_representative:
            self.checkbox.setToolTip("Cannot delete representative photo")
        self.checkbox.stateChanged.connect(self._on_selection_changed)
        layout.addWidget(self.checkbox)

        # Add border
        self.setStyleSheet("""
            PhotoInstanceWidget {
                background-color: white;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
            }
        """)

    def _load_thumbnail_async(self):
        """Load thumbnail asynchronously."""
        try:
            from app_services import get_thumbnail
            path = self.photo.get('path', '')

            if path and Path(path).exists():
                pixmap = get_thumbnail(path, 200)
                if pixmap and not pixmap.isNull():
                    self.thumbnail_label.setPixmap(pixmap)
                else:
                    self.thumbnail_label.setText("No preview")
            else:
                self.thumbnail_label.setText("File not found")
                self.thumbnail_label.setStyleSheet("""
                    QLabel {
                        background-color: #fee;
                        border: 1px solid #fcc;
                        border-radius: 4px;
                        color: #c00;
                    }
                """)
        except Exception as e:
            logger.error(f"Failed to load thumbnail for {self.photo.get('id')}: {e}")
            self.thumbnail_label.setText("Error loading")

    def _on_selection_changed(self, state):
        """Handle selection change."""
        is_selected = state == Qt.Checked
        photo_id = self.photo['id']
        logger.debug(f"PhotoInstanceWidget emitting selection_changed: photo_id={photo_id}, is_selected={is_selected}, state={state}")
        self.selection_changed.emit(photo_id, is_selected)

    def is_selected(self) -> bool:
        """Check if this instance is selected for deletion."""
        return self.checkbox.isChecked()


class DuplicatesDialog(QDialog):
    """
    Dialog for reviewing and managing exact duplicates.

    Displays:
    - List of duplicate assets (left panel)
    - Instance details for selected asset (right panel)
    - Actions: Keep All, Delete Selected, Set Representative

    Signals:
    - duplicate_action_taken: Emitted when user takes action on duplicates
    """

    # Signals
    duplicate_action_taken = Signal(str, int)  # action, asset_id

    def __init__(self, project_id: int, parent=None):
        """
        Initialize DuplicatesDialog.

        Args:
            project_id: Project ID
            parent: Parent widget
        """
        super().__init__(parent)
        self.project_id = project_id
        self.duplicates = []
        self.selected_asset_id = None
        self.selected_photos = set()  # Set of photo_ids selected for deletion

        self.setWindowTitle("Review Duplicates")
        self.setMinimumSize(1200, 700)

        self._init_ui()
        self._load_duplicates()

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel("📸 Duplicate Photo Review")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Subtitle
        self.subtitle = QLabel("Loading duplicates...")
        self.subtitle.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.subtitle)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Main content: Splitter with list and details
        splitter = QSplitter(Qt.Horizontal)

        # Left panel: Duplicate assets list
        left_panel = self._create_assets_list_panel()
        splitter.addWidget(left_panel)

        # Right panel: Instance details
        right_panel = self._create_instance_details_panel()
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator2)

        # Bottom action buttons
        button_layout = QHBoxLayout()
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

    def _create_assets_list_panel(self) -> QWidget:
        """Create left panel with duplicate assets list."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # Title
        title = QLabel("Duplicate Groups")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        # List widget
        self.assets_list = QListWidget()
        self.assets_list.setIconSize(QSize(80, 80))
        self.assets_list.itemClicked.connect(self._on_asset_selected)
        self.assets_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: black;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        layout.addWidget(self.assets_list)

        return panel

    def _create_instance_details_panel(self) -> QWidget:
        """Create right panel with instance details."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # Title
        self.details_title = QLabel("Select a duplicate group")
        self.details_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.details_title)

        # Scroll area for instances
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #fafafa;
            }
        """)

        # Container for instance widgets
        self.instances_container = QWidget()
        self.instances_layout = QGridLayout(self.instances_container)
        self.instances_layout.setSpacing(16)
        self.instances_layout.setContentsMargins(16, 16, 16, 16)

        scroll.setWidget(self.instances_container)
        layout.addWidget(scroll)

        return panel

    def _load_duplicates(self):
        """Load duplicate assets from database."""
        try:
            from services.asset_service import AssetService
            from repository.asset_repository import AssetRepository
            from repository.photo_repository import PhotoRepository
            from repository.base_repository import DatabaseConnection

            # Initialize services
            db_conn = DatabaseConnection()
            photo_repo = PhotoRepository(db_conn)
            asset_repo = AssetRepository(db_conn)
            asset_service = AssetService(photo_repo, asset_repo)

            # Load duplicates
            self.duplicates = asset_service.list_duplicates(self.project_id, min_instances=2)

            logger.info(f"Loaded {len(self.duplicates)} duplicate assets")

            # Update UI
            if not self.duplicates:
                self.subtitle.setText("No duplicates found. All photos are unique!")
                self.assets_list.setEnabled(False)
            else:
                self.subtitle.setText(f"Found {len(self.duplicates)} duplicate groups affecting {sum(d['instance_count'] for d in self.duplicates)} photos")
                self._populate_assets_list()

        except Exception as e:
            logger.error(f"Failed to load duplicates: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error Loading Duplicates",
                f"Failed to load duplicate assets:\n{e}"
            )

    def _populate_assets_list(self):
        """Populate the assets list with duplicate groups."""
        self.assets_list.clear()

        for asset in self.duplicates:
            asset_id = asset['asset_id']
            instance_count = asset['instance_count']
            content_hash = asset.get('content_hash', '')[:16]  # First 16 chars

            # Create list item
            item = QListWidgetItem()
            item.setText(f"Asset #{asset_id}\n{instance_count} copies\nHash: {content_hash}...")
            item.setData(Qt.UserRole, asset_id)

            # Try to load representative photo thumbnail
            rep_photo_id = asset.get('representative_photo_id')
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
                            pixmap = get_thumbnail(path, 80)
                            if pixmap and not pixmap.isNull():
                                item.setIcon(pixmap)
                except Exception as e:
                    logger.warning(f"Failed to load thumbnail for asset {asset_id}: {e}")

            self.assets_list.addItem(item)

    @Slot(QListWidgetItem)
    def _on_asset_selected(self, item: QListWidgetItem):
        """Handle asset selection."""
        asset_id = item.data(Qt.UserRole)
        self.selected_asset_id = asset_id
        self.selected_photos.clear()
        self.btn_delete_selected.setEnabled(False)

        self._load_asset_instances(asset_id)

    def _load_asset_instances(self, asset_id: int):
        """Load and display instances for selected asset."""
        try:
            from services.asset_service import AssetService
            from repository.asset_repository import AssetRepository
            from repository.photo_repository import PhotoRepository
            from repository.base_repository import DatabaseConnection

            # Initialize services
            db_conn = DatabaseConnection()
            photo_repo = PhotoRepository(db_conn)
            asset_repo = AssetRepository(db_conn)
            asset_service = AssetService(photo_repo, asset_repo)

            # Get duplicate details
            details = asset_service.get_duplicate_details(self.project_id, asset_id)

            if not details:
                return

            asset = details['asset']
            photos = details['photos']
            instance_count = details['instance_count']

            # Update title
            self.details_title.setText(f"Asset #{asset_id} - {instance_count} Copies")

            # Clear existing instances
            while self.instances_layout.count():
                item = self.instances_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            # Add instance widgets in grid (2 columns)
            rep_photo_id = asset.get('representative_photo_id')

            for idx, photo in enumerate(photos):
                is_representative = (photo['id'] == rep_photo_id)

                widget = PhotoInstanceWidget(photo, is_representative, self)
                widget.selection_changed.connect(self._on_instance_selection_changed)

                row = idx // 2
                col = idx % 2
                self.instances_layout.addWidget(widget, row, col)

        except Exception as e:
            logger.error(f"Failed to load asset instances: {e}", exc_info=True)
            QMessageBox.warning(
                self,
                "Error Loading Instances",
                f"Failed to load instance details:\n{e}"
            )

    @Slot(int, bool)
    def _on_instance_selection_changed(self, photo_id: int, is_selected: bool):
        """Handle instance selection change."""
        logger.debug(f"Selection changed: photo_id={photo_id}, is_selected={is_selected}")

        if is_selected:
            self.selected_photos.add(photo_id)
        else:
            self.selected_photos.discard(photo_id)

        # Enable delete button if any photos selected
        enabled = len(self.selected_photos) > 0
        logger.debug(f"Setting delete button enabled={enabled}, selected_photos={self.selected_photos}")
        self.btn_delete_selected.setEnabled(enabled)

    def _on_delete_selected(self):
        """Handle delete selected button click."""
        if not self.selected_photos:
            return

        photo_ids = list(self.selected_photos)

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete {len(photo_ids)} selected photo(s)?\n\n"
            "This will:\n"
            "• Delete photo files from disk\n"
            "• Remove photos from database\n"
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
                logger.info(f"Deleting {len(photo_ids)} photos: {photo_ids}")
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
                if self.selected_asset_id:
                    self.duplicate_action_taken.emit("delete", self.selected_asset_id)

                # Reload the view
                self._load_duplicates()

            except Exception as e:
                logger.error(f"Failed to delete photos: {e}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Deletion Failed",
                    f"Failed to delete photos:\n{e}\n\nPlease check the log for details."
                )
