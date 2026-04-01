from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QPushButton, QLabel, QWidget, QToolButton, QFrame
)


class _ExpandableSubsection(QFrame):
    """
    Simple collapsible subsection within BrowseSection.
    """
    def __init__(self, title: str, parent=None, expanded: bool = True):
        super().__init__(parent)
        self.content = QWidget(self)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 2, 0, 2)
        self.content_layout.setSpacing(4)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        self.toggle_btn = QToolButton()
        self.toggle_btn.setText(title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(expanded)
        self.toggle_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.toggle_btn.clicked.connect(self._on_toggled)

        root.addWidget(self.toggle_btn)
        root.addWidget(self.content)
        self.content.setVisible(expanded)

    def _on_toggled(self):
        expanded = self.toggle_btn.isChecked()
        self.toggle_btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.content.setVisible(expanded)

    def addWidget(self, widget: QWidget):
        self.content_layout.addWidget(widget)


class BrowseSection(QGroupBox):
    browseNodeSelected = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__("Browse", parent)
        self.setObjectName("BrowseSection")

        self._counts = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ---- Library (expanded by default) ----
        self.library_group = _ExpandableSubsection("Library", expanded=True)
        self.btn_all_photos = self._make_button("All Photos", "all")
        self.btn_years = self._make_button("Years", "years")
        self.btn_months = self._make_button("Months", "months")
        self.btn_days = self._make_button("Days", "days")
        self.library_group.addWidget(self.btn_all_photos)
        self.library_group.addWidget(self.btn_years)
        self.library_group.addWidget(self.btn_months)
        self.library_group.addWidget(self.btn_days)
        root.addWidget(self.library_group)

        # ---- Sources (expanded by default) ----
        self.sources_group = _ExpandableSubsection("Sources", expanded=True)
        self.btn_folders = self._make_button("Folders", "folders")
        self.btn_devices = self._make_button("Devices", "devices")
        self.sources_group.addWidget(self.btn_folders)
        self.sources_group.addWidget(self.btn_devices)

        self.devices_container = QWidget(self)
        self.devices_layout = QVBoxLayout(self.devices_container)
        self.devices_layout.setContentsMargins(18, 2, 0, 2)
        self.devices_layout.setSpacing(4)
        self.sources_group.addWidget(self.devices_container)
        self.devices_container.setVisible(False)
        root.addWidget(self.sources_group)

        # ---- Collections (collapsed by default) ----
        self.collections_group = _ExpandableSubsection("Collections", expanded=False)
        self.btn_favorites = self._make_button("Favorites", "favorites")
        self.btn_videos = self._make_button("Videos", "videos")
        self.btn_documents = self._make_button("Documents", "documents")
        self.btn_screenshots = self._make_button("Screenshots", "screenshots")
        self.btn_duplicates = self._make_button("Duplicates", "duplicates")
        self.collections_group.addWidget(self.btn_favorites)
        self.collections_group.addWidget(self.btn_videos)
        self.collections_group.addWidget(self.btn_documents)
        self.collections_group.addWidget(self.btn_screenshots)
        self.collections_group.addWidget(self.btn_duplicates)
        root.addWidget(self.collections_group)

        # ---- Places (collapsed by default) ----
        self.places_group = _ExpandableSubsection("Places", expanded=False)
        self.btn_locations = self._make_button("Locations", "locations")
        self.places_group.addWidget(self.btn_locations)
        root.addWidget(self.places_group)

        # ---- Quick Access (collapsed by default) ----
        self.quick_group = _ExpandableSubsection("Quick Access", expanded=False)
        self.btn_today = self._make_button("Today", "today")
        self.btn_yesterday = self._make_button("Yesterday", "yesterday")
        self.btn_last_7 = self._make_button("Last 7 days", "last_7_days")
        self.btn_last_30 = self._make_button("Last 30 days", "last_30_days")
        self.btn_this_month = self._make_button("This month", "this_month")
        self.btn_last_month = self._make_button("Last month", "last_month")
        self.btn_this_year = self._make_button("This year", "this_year")
        self.btn_last_year = self._make_button("Last year", "last_year")

        self.quick_group.addWidget(self.btn_today)
        self.quick_group.addWidget(self.btn_yesterday)
        self.quick_group.addWidget(self.btn_last_7)
        self.quick_group.addWidget(self.btn_last_30)
        self.quick_group.addWidget(self.btn_this_month)
        self.quick_group.addWidget(self.btn_last_month)
        self.quick_group.addWidget(self.btn_this_year)
        self.quick_group.addWidget(self.btn_last_year)
        root.addWidget(self.quick_group)

        root.addStretch(1)

    def _make_button(self, text: str, key: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda checked=False, k=key: self.browseNodeSelected.emit(k, None))
        btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 6px 10px;
            }
        """)
        return btn

    def set_counts(self, counts: dict | None) -> None:
        """
        counts keys supported:
            all, years, months, days, folders, favorites, videos,
            documents, screenshots, duplicates, locations, devices
        """
        self._counts = counts or {}
        self._apply_button_texts()

    def set_devices(self, devices: list[dict] | None) -> None:
        """
        devices example:
            [
                {"label": "iPhone", "key": "device_iphone"},
                {"label": "SD Card", "key": "device_sd"},
            ]
        """
        devices = devices or []

        # clear existing
        while self.devices_layout.count():
            item = self.devices_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self.devices_container.setVisible(bool(devices))

        for dev in devices:
            label = dev.get("label", "Device")
            key = dev.get("key", "devices")
            btn = self._make_button(f"• {label}", key)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 4px 8px;
                    color: #444;
                }
            """)
            btn.clicked.disconnect()
            btn.clicked.connect(lambda checked=False, k=key: self.browseNodeSelected.emit(k, None))
            self.devices_layout.addWidget(btn)

    def _apply_button_texts(self) -> None:
        def fmt(label: str, key: str) -> str:
            v = self._counts.get(key, None)
            return f"{label} ({v})" if v is not None else label

        self.btn_all_photos.setText(fmt("All Photos", "all"))
        self.btn_years.setText(fmt("Years", "years"))
        self.btn_months.setText(fmt("Months", "months"))
        self.btn_days.setText(fmt("Days", "days"))
        self.btn_folders.setText(fmt("Folders", "folders"))
        self.btn_devices.setText(fmt("Devices", "devices"))
        self.btn_favorites.setText(fmt("Favorites", "favorites"))
        self.btn_videos.setText(fmt("Videos", "videos"))
        self.btn_documents.setText(fmt("Documents", "documents"))
        self.btn_screenshots.setText(fmt("Screenshots", "screenshots"))
        self.btn_duplicates.setText(fmt("Duplicates", "duplicates"))
        self.btn_locations.setText(fmt("Locations", "locations"))

    def set_enabled_for_project(self, enabled: bool):
        self.setEnabled(enabled)
