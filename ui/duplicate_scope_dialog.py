"""
Duplicate Detection Scope Selection Dialog
Allows users to select which photos to process for duplicate/similar detection.

FEATURE: Comprehensive scope selection with:
- All photos
- Specific folders (checkbox tree)
- Date range picker
- Recent Photos option
- Custom quantity slider
- Time estimation
- Skip already processed photos option
- Process order selection
- Detection Methods selection
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QTreeWidget, QTreeWidgetItem,
    QDateEdit, QSlider, QCheckBox, QGroupBox, QWidget,
    QProgressBar, QMessageBox, QComboBox, QSpinBox
)
from PySide6.QtCore import Qt, QDate, Signal

from reference_db import ReferenceDB
from translation_manager import tr

logger = logging.getLogger(__name__)


class DuplicateScopeDialog(QDialog):
    """
    Dialog for selecting duplicate/similar photo detection scope.

    Allows users to choose which photos to process, configure detection methods,
    and see statistics about processing estimates.
    """

    # Signal emitted when user clicks "Start Detection"
    # Emits (list of photo_ids, options dict)
    scopeSelected = Signal(list, dict)

    def __init__(self, project_id: int, parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.db = ReferenceDB()

        # Data
        self.all_photos: List[Dict[str, Any]] = []
        self.selected_photo_ids: List[int] = []
        self.folders: List[Dict[str, Any]] = []

        # UI state
        self.scope_mode = "all"  # "all", "folders", "dates", "recent", "quantity"

        self.setWindowTitle("Detect Duplicates & Similar Photos")
        self.resize(700, 750)

        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title = QLabel("Detect Duplicates & Similar Photos")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; padding: 8px 0;")
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Find duplicate and similar photos in your collection. Select which photos to scan, choose detection methods, and configure settings.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #666; font-size: 10pt; padding-bottom: 8px;")
        layout.addWidget(subtitle)

        # Photo Selection group
        selection_group = self._create_photo_selection()
        layout.addWidget(selection_group)

        # Options group
        options_group = self._create_options_section()
        layout.addWidget(options_group)

        # Summary panel
        self.summary_panel = self._create_summary_panel()
        layout.addWidget(self.summary_panel)

        # Detection Methods group
        detection_group = self._create_detection_methods()
        layout.addWidget(detection_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f5;
                color: #333333;
                padding: 8px 24px;
                font-weight: bold;
                border-radius: 4px;
                border: 1px solid #cccccc;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        start_btn = QPushButton("Proceed")
        start_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8;
                color: white;
                padding: 8px 24px;
                font-weight: bold;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1557b0;
            }
        """)
        start_btn.clicked.connect(self._start_detection)
        button_layout.addWidget(start_btn)

        layout.addLayout(button_layout)

    def _create_photo_selection(self) -> QGroupBox:
        """Create photo selection radio buttons and options."""
        group = QGroupBox("Photo Selection")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Radio button group
        self.button_group = QButtonGroup(self)

        # Option 1: All Photos
        self.radio_all = QRadioButton("All Photos")
        self.radio_all.setChecked(True)
        self.radio_all.toggled.connect(lambda checked: self._on_scope_changed("all") if checked else None)
        self.button_group.addButton(self.radio_all)
        layout.addWidget(self.radio_all)

        self.label_all_count = QLabel()
        self.label_all_count.setStyleSheet("color: #666; margin-left: 25px; font-size: 9pt;")
        layout.addWidget(self.label_all_count)

        # Option 2: Specific Folders
        self.radio_folders = QRadioButton("Specific Folders")
        self.radio_folders.toggled.connect(lambda checked: self._on_scope_changed("folders") if checked else None)
        self.button_group.addButton(self.radio_folders)
        layout.addWidget(self.radio_folders)

        # Folder tree (hidden by default)
        self.folder_container = QWidget()
        folder_layout = QVBoxLayout(self.folder_container)
        folder_layout.setContentsMargins(25, 4, 0, 4)

        folder_label = QLabel("Select Folders")
        folder_label.setStyleSheet("font-weight: bold; font-size: 9pt;")
        folder_layout.addWidget(folder_label)

        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setMaximumHeight(150)
        self.folder_tree.itemChanged.connect(self._on_folder_selection_changed)
        folder_layout.addWidget(self.folder_tree)

        self.folder_container.hide()
        layout.addWidget(self.folder_container)

        # Option 3: Date Range
        self.radio_dates = QRadioButton("Date Range")
        self.radio_dates.toggled.connect(lambda checked: self._on_scope_changed("dates") if checked else None)
        self.button_group.addButton(self.radio_dates)
        layout.addWidget(self.radio_dates)

        # Date range picker (hidden by default)
        self.date_widget = QWidget()
        date_layout = QHBoxLayout(self.date_widget)
        date_layout.setContentsMargins(25, 4, 0, 4)

        date_layout.addWidget(QLabel("From:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addYears(-1))
        self.date_from.dateChanged.connect(self._update_summary)
        date_layout.addWidget(self.date_from)

        date_layout.addWidget(QLabel("To:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self._update_summary)
        date_layout.addWidget(self.date_to)

        date_layout.addStretch()
        self.date_widget.hide()
        layout.addWidget(self.date_widget)

        # Option 4: Recent Photos
        self.radio_recent = QRadioButton("Recent Photos")
        self.radio_recent.toggled.connect(lambda checked: self._on_scope_changed("recent") if checked else None)
        self.button_group.addButton(self.radio_recent)
        layout.addWidget(self.radio_recent)

        # Recent photos options (hidden by default)
        self.recent_widget = QWidget()
        recent_layout = QHBoxLayout(self.recent_widget)
        recent_layout.setContentsMargins(25, 4, 0, 4)

        recent_layout.addWidget(QLabel("Last"))
        self.recent_days = QSpinBox()
        self.recent_days.setRange(1, 365)
        self.recent_days.setValue(30)
        self.recent_days.setSuffix(" days")
        self.recent_days.valueChanged.connect(self._update_summary)
        recent_layout.addWidget(self.recent_days)

        recent_layout.addStretch()
        self.recent_widget.hide()
        layout.addWidget(self.recent_widget)

        # Option 5: Custom Quantity
        self.radio_quantity = QRadioButton("Custom Quantity")
        self.radio_quantity.toggled.connect(lambda checked: self._on_scope_changed("quantity") if checked else None)
        self.button_group.addButton(self.radio_quantity)
        layout.addWidget(self.radio_quantity)

        # Quantity slider (hidden by default)
        self.quantity_widget = QWidget()
        quantity_layout = QVBoxLayout(self.quantity_widget)
        quantity_layout.setContentsMargins(25, 4, 0, 4)

        self.quantity_slider = QSlider(Qt.Horizontal)
        self.quantity_slider.setMinimum(1)
        self.quantity_slider.setMaximum(100)
        self.quantity_slider.setValue(50)
        self.quantity_slider.valueChanged.connect(self._update_summary)
        quantity_layout.addWidget(self.quantity_slider)

        self.quantity_label = QLabel()
        self.quantity_label.setStyleSheet("color: #1a73e8; font-weight: bold;")
        quantity_layout.addWidget(self.quantity_label)

        self.quantity_widget.hide()
        layout.addWidget(self.quantity_widget)

        return group

    def _create_options_section(self) -> QGroupBox:
        """Create options section."""
        group = QGroupBox("Options")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Skip already processed checkbox
        self.chk_skip_processed = QCheckBox("Skip photos that already have embeddings")
        self.chk_skip_processed.setChecked(True)
        self.chk_skip_processed.toggled.connect(self._update_summary)
        layout.addWidget(self.chk_skip_processed)

        # Process order
        order_layout = QHBoxLayout()
        order_layout.addWidget(QLabel("Process order:"))
        self.process_order = QComboBox()
        self.process_order.addItems(["Newest first", "Oldest first", "Random"])
        order_layout.addWidget(self.process_order)
        order_layout.addStretch()
        layout.addLayout(order_layout)

        return group

    def _create_summary_panel(self) -> QGroupBox:
        """Create summary panel showing selection statistics."""
        group = QGroupBox("Summary")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self.summary_selected = QLabel()
        self.summary_selected.setStyleSheet("font-size: 11pt; font-weight: bold;")
        layout.addWidget(self.summary_selected)

        self.summary_processed = QLabel()
        self.summary_processed.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addWidget(self.summary_processed)

        self.summary_to_process = QLabel()
        self.summary_to_process.setStyleSheet("color: #1a73e8; font-weight: bold;")
        layout.addWidget(self.summary_to_process)

        self.summary_time = QLabel()
        self.summary_time.setStyleSheet("color: #666; font-style: italic; font-size: 9pt;")
        layout.addWidget(self.summary_time)

        return group

    def _create_detection_methods(self) -> QGroupBox:
        """Create detection methods section."""
        group = QGroupBox("Detection Methods")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Exact duplicates
        self.chk_exact = QCheckBox("Exact Duplicates (hash-based)")
        self.chk_exact.setChecked(True)
        self.chk_exact.setToolTip("Find photos with identical content using SHA256 hashing")
        layout.addWidget(self.chk_exact)

        exact_desc = QLabel("    Fast detection of identical files")
        exact_desc.setStyleSheet("color: #666; font-size: 9pt; margin-left: 24px;")
        layout.addWidget(exact_desc)

        # Similar photos
        self.chk_similar = QCheckBox("Similar Photos (AI-powered)")
        self.chk_similar.setChecked(True)
        self.chk_similar.setToolTip("Find visually similar photos using AI embeddings")
        layout.addWidget(self.chk_similar)

        similar_desc = QLabel("    Detect burst shots, edited versions, similar compositions")
        similar_desc.setStyleSheet("color: #666; font-size: 9pt; margin-left: 24px;")
        layout.addWidget(similar_desc)

        # Similarity threshold (only when similar is checked)
        self.threshold_widget = QWidget()
        threshold_layout = QHBoxLayout(self.threshold_widget)
        threshold_layout.setContentsMargins(24, 4, 0, 4)
        threshold_layout.addWidget(QLabel("Similarity threshold:"))
        self.similarity_threshold = QSlider(Qt.Horizontal)
        self.similarity_threshold.setRange(50, 99)
        self.similarity_threshold.setValue(85)
        self.similarity_threshold.setMaximumWidth(150)
        threshold_layout.addWidget(self.similarity_threshold)
        self.threshold_label = QLabel("85%")
        threshold_layout.addWidget(self.threshold_label)
        threshold_layout.addStretch()
        layout.addWidget(self.threshold_widget)

        self.similarity_threshold.valueChanged.connect(
            lambda v: self.threshold_label.setText(f"{v}%")
        )
        self.chk_similar.toggled.connect(self.threshold_widget.setVisible)

        return group

    def load_data(self):
        """Load photos and folders from database."""
        try:
            # Load all photos
            self.all_photos = self.db.get_all_paths_with_dates(self.project_id) or []

            # Load folders
            self.folders = self.db.get_folders_with_counts(self.project_id) or []

            # Populate folder tree
            self._populate_folder_tree()

            # Update labels
            self.label_all_count.setText(f"{len(self.all_photos)} photos in library")

            # Update summary
            self._update_summary()

        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load photos:\n{str(e)}")

    def _populate_folder_tree(self):
        """Populate folder tree with checkboxes in hierarchical structure."""
        self.folder_tree.clear()

        # Build folder lookup by ID
        folder_lookup = {f['id']: f for f in self.folders}

        # Build tree recursively
        def add_folder(parent_item, parent_id):
            # Find children of this parent
            children = [f for f in self.folders if f.get('parent_id') == parent_id]

            for folder in children:
                item = QTreeWidgetItem(parent_item if parent_item else self.folder_tree)
                photo_count = folder.get('count', 0)
                item.setText(0, f"{folder['name']} ({photo_count} photos)")
                item.setCheckState(0, Qt.Unchecked)
                item.setData(0, Qt.UserRole, folder['id'])  # Store folder ID
                item.setExpanded(True)  # Expand by default

                # Recursively add children
                add_folder(item, folder['id'])

        # Start with root folders (parent_id is None)
        add_folder(None, None)

    def _on_scope_changed(self, mode: str):
        """Handle scope mode change."""
        self.scope_mode = mode

        # Show/hide relevant widgets
        self.folder_container.setVisible(mode == "folders")
        self.date_widget.setVisible(mode == "dates")
        self.recent_widget.setVisible(mode == "recent")
        self.quantity_widget.setVisible(mode == "quantity")

        self._update_summary()

    def _on_folder_selection_changed(self, item: QTreeWidgetItem, column: int):
        """Handle folder checkbox change."""
        self._update_summary()

    def _update_summary(self):
        """Update summary panel with current selection statistics."""
        # Calculate selected photos based on mode
        selected_count = 0
        self.selected_photo_ids = []

        if self.scope_mode == "all":
            selected_count = len(self.all_photos)
            self.selected_photo_ids = [p.get('id') for p in self.all_photos if p.get('id')]

        elif self.scope_mode == "folders":
            # Get checked folder IDs recursively
            selected_folder_ids = []

            def get_checked_folders(item):
                """Recursively collect checked folder IDs."""
                if item.checkState(0) == Qt.Checked:
                    folder_id = item.data(0, Qt.UserRole)
                    if folder_id is not None:
                        selected_folder_ids.append(folder_id)

                # Check children
                for i in range(item.childCount()):
                    get_checked_folders(item.child(i))

            # Check all top-level items
            for i in range(self.folder_tree.topLevelItemCount()):
                get_checked_folders(self.folder_tree.topLevelItem(i))

            # Get photos for selected folders
            if selected_folder_ids:
                try:
                    folder_photos = self.db.get_photos_for_folders(self.project_id, selected_folder_ids)
                    if isinstance(folder_photos, list):
                        # If it returns paths, we need to get IDs
                        if folder_photos and isinstance(folder_photos[0], str):
                            # Get photos by paths
                            for photo in self.all_photos:
                                if photo.get('path') in folder_photos:
                                    self.selected_photo_ids.append(photo.get('id'))
                        elif folder_photos and isinstance(folder_photos[0], dict):
                            self.selected_photo_ids = [p.get('id') for p in folder_photos if p.get('id')]
                        else:
                            self.selected_photo_ids = folder_photos
                except Exception as e:
                    logger.warning(f"Failed to get photos for folders: {e}")
                    self.selected_photo_ids = []

            selected_count = len(self.selected_photo_ids)

        elif self.scope_mode == "dates":
            # Filter by date range
            start_date = self.date_from.date().toPython()
            end_date = self.date_to.date().toPython()

            for photo in self.all_photos:
                photo_date = photo.get('date')
                if photo_date:
                    if isinstance(photo_date, datetime):
                        photo_date = photo_date.date()
                    if start_date <= photo_date <= end_date:
                        self.selected_photo_ids.append(photo.get('id'))

            selected_count = len(self.selected_photo_ids)

        elif self.scope_mode == "recent":
            # Filter by recent days
            days = self.recent_days.value()
            cutoff_date = datetime.now() - timedelta(days=days)

            for photo in self.all_photos:
                photo_date = photo.get('date')
                if photo_date:
                    if isinstance(photo_date, datetime):
                        if photo_date >= cutoff_date:
                            self.selected_photo_ids.append(photo.get('id'))
                    elif hasattr(photo_date, 'timetuple'):
                        photo_datetime = datetime.combine(photo_date, datetime.min.time())
                        if photo_datetime >= cutoff_date:
                            self.selected_photo_ids.append(photo.get('id'))

            selected_count = len(self.selected_photo_ids)

        elif self.scope_mode == "quantity":
            # Use slider percentage
            total = len(self.all_photos)
            percentage = self.quantity_slider.value()
            selected_count = int(total * percentage / 100)
            self.selected_photo_ids = [p.get('id') for p in self.all_photos[:selected_count] if p.get('id')]
            self.quantity_label.setText(f"{selected_count:,} photos ({percentage}%)")

        # Check which photos already have embeddings
        already_processed = 0
        if self.chk_skip_processed.isChecked():
            try:
                # Query semantic_embeddings table directly for photo IDs with embeddings
                with self.db._connect() as conn:
                    cur = conn.execute("""
                        SELECT DISTINCT se.photo_id
                        FROM semantic_embeddings se
                        JOIN photo_metadata p ON se.photo_id = p.id
                        WHERE p.project_id = ?
                    """, (self.project_id,))
                    processed_ids = {row[0] for row in cur.fetchall()}
                    already_processed = len([pid for pid in self.selected_photo_ids if pid in processed_ids])
            except Exception as e:
                logger.warning(f"Failed to get processed photos: {e}")

        to_process = selected_count - already_processed

        # Estimate time (average 0.5s per photo for embedding + 0.1s for hashing)
        avg_time_per_photo = 0.6  # seconds
        estimated_seconds = to_process * avg_time_per_photo

        if estimated_seconds < 60:
            time_str = f"~{int(estimated_seconds)} seconds"
        elif estimated_seconds < 3600:
            time_str = f"~{int(estimated_seconds / 60)} minutes"
        else:
            hours = int(estimated_seconds / 3600)
            minutes = int((estimated_seconds % 3600) / 60)
            time_str = f"~{hours}h {minutes}m"

        # Update summary labels
        self.summary_selected.setText(f"Selected: {selected_count:,} photos")
        self.summary_processed.setText(f"Already processed: {already_processed:,} (will skip)")
        self.summary_to_process.setText(f"To process: {to_process:,} photos")
        self.summary_time.setText(f"Estimated time: {time_str}")

    def _start_detection(self):
        """Start detection with selected scope and options."""
        if not self.selected_photo_ids:
            QMessageBox.warning(
                self,
                "No Photos Selected",
                "Please select at least one photo for duplicate detection."
            )
            return

        # Check if at least one detection method is selected
        if not self.chk_exact.isChecked() and not self.chk_similar.isChecked():
            QMessageBox.warning(
                self,
                "No Detection Method",
                "Please select at least one detection method:\n"
                "- Exact Duplicates\n"
                "- Similar Photos"
            )
            return

        # Filter out already processed if checkbox is checked
        photo_ids_to_process = self.selected_photo_ids
        if self.chk_skip_processed.isChecked():
            try:
                # Query semantic_embeddings table directly
                with self.db._connect() as conn:
                    cur = conn.execute("""
                        SELECT DISTINCT se.photo_id
                        FROM semantic_embeddings se
                        JOIN photo_metadata p ON se.photo_id = p.id
                        WHERE p.project_id = ?
                    """, (self.project_id,))
                    processed_ids = {row[0] for row in cur.fetchall()}
                    photo_ids_to_process = [pid for pid in self.selected_photo_ids if pid not in processed_ids]
            except Exception as e:
                logger.error(f"Failed to filter processed photos: {e}")

        # Build options dictionary
        options = {
            'detect_exact': self.chk_exact.isChecked(),
            'detect_similar': self.chk_similar.isChecked(),
            'similarity_threshold': self.similarity_threshold.value() / 100.0,
            'process_order': self.process_order.currentText(),
            'skip_processed': self.chk_skip_processed.isChecked(),
            'scope_mode': self.scope_mode
        }

        logger.info(f"Starting duplicate detection: {len(photo_ids_to_process)} photos, scope: {self.scope_mode}")

        # Emit signal with photo IDs and options
        self.scopeSelected.emit(photo_ids_to_process, options)
        self.accept()
