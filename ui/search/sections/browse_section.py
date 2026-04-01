from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QPushButton, QLabel, QWidget


class BrowseSection(QGroupBox):
    browseNodeSelected = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__("Browse", parent)
        self.setObjectName("BrowseSection")

        self._counts = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ---- Library ----
        root.addWidget(self._make_group_label("Library"))
        self.btn_all_photos = self._make_button("All Photos", "all")
        self.btn_years = self._make_button("Years", "years")
        self.btn_months = self._make_button("Months", "months")
        self.btn_days = self._make_button("Days", "days")
        root.addWidget(self.btn_all_photos)
        root.addWidget(self.btn_years)
        root.addWidget(self.btn_months)
        root.addWidget(self.btn_days)

        # ---- Sources ----
        root.addWidget(self._make_group_label("Sources"))
        self.btn_folders = self._make_button("Folders", "folders")
        self.btn_devices = self._make_button("Devices", "devices")
        root.addWidget(self.btn_folders)
        root.addWidget(self.btn_devices)

        self.devices_container = QWidget(self)
        self.devices_layout = QVBoxLayout(self.devices_container)
        self.devices_layout.setContentsMargins(18, 2, 0, 2)
        self.devices_layout.setSpacing(4)
        root.addWidget(self.devices_container)
        self.devices_container.setVisible(False)

        # ---- Collections ----
        root.addWidget(self._make_group_label("Collections"))
        self.btn_favorites = self._make_button("Favorites", "favorites")
        self.btn_videos = self._make_button("Videos", "videos")
        self.btn_documents = self._make_button("Documents", "documents")
        self.btn_screenshots = self._make_button("Screenshots", "screenshots")
        self.btn_duplicates = self._make_button("Duplicates", "duplicates")
        root.addWidget(self.btn_favorites)
        root.addWidget(self.btn_videos)
        root.addWidget(self.btn_documents)
        root.addWidget(self.btn_screenshots)
        root.addWidget(self.btn_duplicates)

        # ---- Places ----
        root.addWidget(self._make_group_label("Places"))
        self.btn_locations = self._make_button("Locations", "locations")
        root.addWidget(self.btn_locations)

        # ---- Quick Access ----
        root.addWidget(self._make_group_label("Quick Access"))
        self.btn_today = self._make_button("Today", "today")
        self.btn_yesterday = self._make_button("Yesterday", "yesterday")
        self.btn_last_7 = self._make_button("Last 7 days", "last_7_days")
        self.btn_last_30 = self._make_button("Last 30 days", "last_30_days")
        self.btn_this_month = self._make_button("This month", "this_month")
        self.btn_last_month = self._make_button("Last month", "last_month")
        self.btn_this_year = self._make_button("This year", "this_year")
        self.btn_last_year = self._make_button("Last year", "last_year")

        root.addWidget(self.btn_today)
        root.addWidget(self.btn_yesterday)
        root.addWidget(self.btn_last_7)
        root.addWidget(self.btn_last_30)
        root.addWidget(self.btn_this_month)
        root.addWidget(self.btn_last_month)
        root.addWidget(self.btn_this_year)
        root.addWidget(self.btn_last_year)

        root.addStretch(1)

    def _make_group_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: 600; color: #5f6368; margin-top: 4px;")
        return lbl

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
