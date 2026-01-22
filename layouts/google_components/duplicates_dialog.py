# layouts/google_components/duplicates_dialog.py
# Version 02.01.00.00 dated 20260122
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
        # stateChanged signal passes int: 0=Unchecked, 2=Checked
        # Compare with Qt.CheckState.Checked.value or just check if state == 2
        is_selected = (state == Qt.CheckState.Checked.value) or (state == 2)
        photo_id = self.photo['id']
        logger.info(f"[PhotoInstanceWidget] Checkbox state changed: photo_id={photo_id}, state={state}, is_selected={is_selected}, Qt.CheckState.Checked.value={Qt.CheckState.Checked.value}")
        logger.info(f"[PhotoInstanceWidget] Emitting selection_changed signal: photo_id={photo_id}, is_selected={is_selected}")
        self.selection_changed.emit(photo_id, is_selected)
        logger.info(f"[PhotoInstanceWidget] Signal emitted successfully")

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
        self.instance_widgets = []  # Phase 3C: Track instance widgets for batch operations
            
        # Async loading infrastructure (similar to photo grid pattern)
        self._load_generation = 0
        self._details_generation = 0
        self._loading_in_progress = False
            
        # Create signals for async operations
        from workers.duplicate_loading_worker import DuplicateLoadSignals
        self.duplicate_signals = DuplicateLoadSignals()
        self.duplicate_signals.duplicates_loaded.connect(self._on_duplicates_loaded)
        self.duplicate_signals.details_loaded.connect(self._on_details_loaded)
        self.duplicate_signals.error.connect(self._on_load_error)
            
        self.setWindowTitle("Review Duplicates")
        self.setMinimumSize(1200, 700)
    
        self._init_ui()
        self._load_duplicates_async()

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(8, 16, 16, 16)

        # Title
        title = QLabel("📸 Duplicate Photo Review")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Subtitle/loading indicator
        self.subtitle = QLabel("Loading duplicates...")
        self.subtitle.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.subtitle)
        
        # Loading indicator (hidden initially)
        self.loading_spinner = QLabel("⏳ Loading duplicate data...")
        self.loading_spinner.setStyleSheet("color: #444; font-style: italic;")
        self.loading_spinner.hide()
        layout.addWidget(self.loading_spinner)
        
        # Pagination controls
        self.pagination_widget = self._create_pagination_controls()
        layout.addWidget(self.pagination_widget)

        # Phase 3C: Toolbar with filtering, sorting, and batch operations
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

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

    def _create_toolbar(self) -> QWidget:
        """
        Create toolbar with filtering, sorting, and batch operations.

        Phase 3C: Enhanced UI Polish
        """
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 8, 0, 8)
        toolbar_layout.setSpacing(12)

        # Batch Selection Group
        batch_group = QGroupBox("Batch Selection")
        batch_layout = QHBoxLayout(batch_group)
        batch_layout.setContentsMargins(8, 8, 8, 8)
        batch_layout.setSpacing(8)

        btn_select_all = QPushButton("Select All")
        btn_select_all.setToolTip("Select all duplicates for deletion")
        btn_select_all.clicked.connect(self._on_select_all)
        batch_layout.addWidget(btn_select_all)

        btn_select_none = QPushButton("Select None")
        btn_select_none.setToolTip("Deselect all duplicates")
        btn_select_none.clicked.connect(self._on_select_none)
        batch_layout.addWidget(btn_select_none)

        btn_invert = QPushButton("Invert Selection")
        btn_invert.setToolTip("Invert current selection")
        btn_invert.clicked.connect(self._on_invert_selection)
        batch_layout.addWidget(btn_invert)

        toolbar_layout.addWidget(batch_group)

        # Smart Cleanup Group
        smart_group = QGroupBox("Smart Cleanup")
        smart_layout = QHBoxLayout(smart_group)
        smart_layout.setContentsMargins(8, 8, 8, 8)
        smart_layout.setSpacing(8)

        btn_auto_select = QPushButton("🎯 Auto-Select Lower Quality")
        btn_auto_select.setToolTip("Automatically select lower quality duplicates for deletion\n(Keeps highest resolution, largest file size)")
        btn_auto_select.clicked.connect(self._on_auto_select_duplicates)
        btn_auto_select.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
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
        smart_layout.addWidget(btn_auto_select)

        toolbar_layout.addWidget(smart_group)

        toolbar_layout.addStretch()

        return toolbar

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

    def _create_pagination_controls(self) -> QWidget:
        """Create pagination controls for loading more duplicates."""
        pagination = QWidget()
        pagination_layout = QHBoxLayout(pagination)
        pagination_layout.setContentsMargins(0, 8, 0, 8)
        
        # Load More button
        self.load_more_btn = QPushButton("Load More Duplicates")
        self.load_more_btn.clicked.connect(self._load_more_duplicates)
        self.load_more_btn.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #BBDEFB;
                color: #90CAF9;
            }
        """)
        self.load_more_btn.hide()  # Hidden initially
        
        # Items loaded counter
        self.items_counter = QLabel("0 items loaded")
        self.items_counter.setStyleSheet("color: #666; font-size: 11px;")
        
        pagination_layout.addWidget(self.load_more_btn)
        pagination_layout.addWidget(self.items_counter)
        pagination_layout.addStretch()
        
        return pagination
    
    def _load_duplicates_async(self):
        """Load duplicate assets asynchronously using background worker."""
        # Increment generation counter to track this load operation
        self._load_generation += 1
        current_generation = self._load_generation
        
        # Show loading state
        self._loading_in_progress = True
        self.subtitle.setText("Loading duplicates...")
        self.loading_spinner.show()
        self.assets_list.setEnabled(False)
        
        # Start async worker (non-blocking!)
        from workers.duplicate_loading_worker import load_duplicates_async
        load_duplicates_async(
            project_id=self.project_id,
            generation=current_generation,
            signals=self.duplicate_signals
        )
        
        logger.info(f"Started async duplicate loading (generation {current_generation})")
    
    def _on_duplicates_loaded(self, generation: int, duplicates: list):
        """Callback when async duplicate loading completes."""
        # Check if this is stale data
        if generation != self._load_generation:
            logger.info(f"Discarding stale duplicate data (gen {generation} vs current {self._load_generation})")
            return
        
        # Store results
        self.duplicates = duplicates
        
        # Clear loading state
        self._loading_in_progress = False
        self.loading_spinner.hide()
        
        # Update UI
        if not self.duplicates:
            self.subtitle.setText("No duplicates found. All photos are unique!")
            self.assets_list.setEnabled(False)
            self.load_more_btn.hide()
        else:
            self.subtitle.setText(f"Found {len(self.duplicates)} duplicate groups affecting {sum(d['instance_count'] for d in self.duplicates)} photos")
            self.assets_list.setEnabled(True)
            self._populate_assets_list()
            
            # Show pagination controls if we might have more data
            # (this is a simplified check - in reality we"d want to check total count)
            if len(duplicates) >= 50:  # Assuming batch size of 50
                self.load_more_btn.show()
            else:
                self.load_more_btn.hide()
            
            # Update counter
            self.items_counter.setText(f"{len(self.duplicates)} items loaded")
        
        logger.info(f"Async duplicate loading complete: {len(duplicates)} groups loaded")
    
    def _load_more_duplicates(self):
        """Load additional duplicates (pagination)."""
        # Disable button during loading
        self.load_more_btn.setEnabled(False)
        self.load_more_btn.setText("Loading...")
        
        # Load next batch (this would need to track offset)
        # For now, we"ll just reload everything but this demonstrates the concept
        self._load_duplicates_async()
        
        logger.info("Loading more duplicates...")
    
    def _on_details_loaded(self, generation: int, details: dict):
        """Callback when async details loading completes."""
        # Check if this is stale data
        if generation != self._details_generation:
            logger.info(f"Discarding stale details data (gen {generation} vs current {self._details_generation})")
            return
        
        # Display the loaded details
        self._display_asset_details(details)
        
        logger.info(f"Async details loading complete for asset")
    
    def _on_load_error(self, generation: int, error_message: str):
        """Callback when async loading encounters an error."""
        logger.error(f"Async loading failed (gen {generation}): {error_message}")
        
        # Clear loading state
        self._loading_in_progress = False
        self.loading_spinner.hide()
        
        # Show error to user
        self.subtitle.setText(f"❌ Error loading duplicates: {error_message}")
        self.assets_list.setEnabled(False)
        
        QMessageBox.critical(
            self,
            "Error Loading Duplicates",
            f"Failed to load duplicate assets:\n{error_message}\n\n"
            "Please check the log for details."
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
        """Handle asset selection with async details loading."""
        asset_id = item.data(Qt.UserRole)
        self.selected_asset_id = asset_id
        self.selected_photos.clear()
        self.btn_delete_selected.setEnabled(False)

        # Load asset details asynchronously
        self._load_asset_details_async(asset_id)
    
    def _load_asset_details_async(self, asset_id: int):
        """Load asset details asynchronously using background worker."""
        # Increment generation counter
        self._details_generation += 1
        current_generation = self._details_generation
        
        # Show loading state in details panel
        self.details_title.setText("Loading details...")
        
        # Clear existing instances
        while self.instances_layout.count():
            item = self.instances_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Start async worker
        from workers.duplicate_loading_worker import load_duplicate_details_async
        load_duplicate_details_async(
            project_id=self.project_id,
            asset_id=asset_id,
            generation=current_generation,
            signals=self.duplicate_signals
        )
        
        logger.info(f"Started async details loading for asset {asset_id} (generation {current_generation})")
    
    def _display_asset_details(self, details: dict):
        """Display loaded asset details in UI."""
        if not details:
            return

        asset = details['asset']
        photos = details['photos']
        instance_count = details['instance_count']
        asset_id = asset['asset_id']

        # Update title
        self.details_title.setText(f"Asset #{asset_id} - {instance_count} Copies")

        # Clear existing instances
        while self.instances_layout.count():
            item = self.instances_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Phase 3C: Clear instance widgets list
        self.instance_widgets = []

        # Add instance widgets in grid (2 columns)
        rep_photo_id = asset.get('representative_photo_id')

        for idx, photo in enumerate(photos):
            is_representative = (photo['id'] == rep_photo_id)

            widget = PhotoInstanceWidget(photo, is_representative, self)
            widget.selection_changed.connect(self._on_instance_selection_changed)

            # Phase 3C: Add to tracking list
            self.instance_widgets.append(widget)

            row = idx // 2
            col = idx % 2
            self.instances_layout.addWidget(widget, row, col)



    @Slot(int, bool)
    def _on_instance_selection_changed(self, photo_id: int, is_selected: bool):
        """Handle instance selection change."""
        logger.info(f"[DuplicatesDialog] Selection changed: photo_id={photo_id}, is_selected={is_selected}")

        if is_selected:
            self.selected_photos.add(photo_id)
            logger.info(f"[DuplicatesDialog] Added photo {photo_id} to selection")
        else:
            self.selected_photos.discard(photo_id)
            logger.info(f"[DuplicatesDialog] Removed photo {photo_id} from selection")

        # Enable delete button if any photos selected
        enabled = len(self.selected_photos) > 0
        logger.info(f"[DuplicatesDialog] Setting delete button enabled={enabled}, selected_photos count={len(self.selected_photos)}, ids={self.selected_photos}")
        logger.info(f"[DuplicatesDialog] Button state before setEnabled: {self.btn_delete_selected.isEnabled()}")
        self.btn_delete_selected.setEnabled(enabled)
        logger.info(f"[DuplicatesDialog] Button state after setEnabled: {self.btn_delete_selected.isEnabled()}")

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

    # Phase 3C: Batch Selection Handlers
    def _on_select_all(self):
        """Select all non-representative photos for deletion."""
        for widget in self.instance_widgets:
            if not widget.is_representative:
                widget.checkbox.setChecked(True)

    def _on_select_none(self):
        """Deselect all photos."""
        for widget in self.instance_widgets:
            widget.checkbox.setChecked(False)

    def _on_invert_selection(self):
        """Invert current selection."""
        for widget in self.instance_widgets:
            if not widget.is_representative:
                widget.checkbox.setChecked(not widget.checkbox.isChecked())

    # Phase 3C: Smart Cleanup Handler
    def _on_auto_select_duplicates(self):
        """
        Automatically select lower quality duplicates for deletion.

        Algorithm:
        1. For each duplicate group, keep the best photo (highest resolution, largest file size)
        2. Select all other photos in the group for deletion
        3. Never select the representative photo
        """
        if not self.selected_asset_id or not self.instance_widgets:
            QMessageBox.information(
                self,
                "No Selection",
                "Please select a duplicate group first."
            )
            return

        # Get all photos in current group
        photos = [widget.photo for widget in self.instance_widgets]

        # Find the best photo (highest resolution, then largest file size)
        best_photo = max(photos, key=lambda p: (
            p.get('width', 0) * p.get('height', 0),  # Resolution
            p.get('size_kb', 0)  # File size
        ))

        best_photo_id = best_photo['id']

        # Select all photos except the best one and the representative
        selected_count = 0
        for widget in self.instance_widgets:
            photo_id = widget.photo['id']
            is_representative = widget.is_representative

            # Don't select if it's the best photo or the representative
            if photo_id != best_photo_id and not is_representative:
                widget.checkbox.setChecked(True)
                selected_count += 1
            else:
                widget.checkbox.setChecked(False)

        # Show info message
        QMessageBox.information(
            self,
            "Smart Selection Complete",
            f"✅ Selected {selected_count} lower quality photo(s) for deletion.\n\n"
            f"🎯 Kept best photo: {best_photo['width']}×{best_photo['height']}, "
            f"{best_photo.get('size_kb', 0):.1f} KB\n\n"
            f"Review the selection and click 'Delete Selected' to proceed."
        )
