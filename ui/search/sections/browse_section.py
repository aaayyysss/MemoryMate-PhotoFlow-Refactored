from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QHBoxLayout
)
from PySide6.QtCore import Signal, Qt
from ui.search.search_sidebar import SidebarSection

class BrowseItem(QPushButton):
    def __init__(self, icon, label, parent=None):
        super().__init__(parent)
        self.setFlat(True)
        self.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px 16px;
                border-radius: 4px;
                color: #3c4043;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #f1f3f4;
            }
        """)
        self.setText(f"{icon}  {label}")

class BrowseSection(SidebarSection):
    browseNodeSelected = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__("Browse", parent)
        self._setup_content()

    def _setup_content(self):
        items = [
            ("all_photos", "📸", "All Photos", None),
            ("favorites", "⭐", "Favorites", True),
            ("videos", "🎬", "Videos", True),
            ("with_location", "📍", "With Location", True),
            ("albums", "📖", "Albums", None),
            ("folders", "📁", "Folders", None),
            ("dates", "📅", "Dates", None)
        ]

        for node_id, icon, label, value in items:
            btn = BrowseItem(icon, label)
            btn.clicked.connect(lambda _, nid=node_id, val=value: self.browseNodeSelected.emit(nid, val))
            self.content_layout.addWidget(btn)
