from PySide6.QtWidgets import (
    QWidget, QGridLayout
)
from PySide6.QtCore import Signal
from ui.search.search_sidebar import SidebarSection
from ui.search.widgets.smart_find_card import SmartFindCard

class DiscoverSection(SidebarSection):
    presetSelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Discover", parent)
        self._setup_content()

    def _setup_content(self):
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setContentsMargins(8, 4, 8, 4)

        presets = [
            ("beach", "Beach", "🌊"),
            ("mountains", "Mountains", "🏔"),
            ("city", "City", "🌆"),
            ("forest", "Forest", "🌲"),
            ("documents", "Documents", "📄"),
            ("screenshots", "Screenshots", "📱")
        ]

        for i, (pid, title, icon) in enumerate(presets):
            card = SmartFindCard(pid, title, icon)
            card.clicked.connect(self.presetSelected)
            grid.addWidget(card, i // 2, i % 2)

        self.content_layout.addLayout(grid)
