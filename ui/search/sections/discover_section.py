from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout

from ui.search.widgets.smart_find_card import SmartFindCard


class DiscoverSection(QGroupBox):
    presetSelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Discover", parent)

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(8)
        self.cards = {}
        self._active_preset = None

        self._build_cards()

    def _build_cards(self):
        presets = [
            ("beach", "Beach", "🌊"),
            ("mountains", "Mountains", "🏔"),
            ("city", "City", "🌆"),
            ("forest", "Forest", "🌲"),
            ("documents", "Documents", "📄"),
            ("screenshots", "Screenshots", "📱"),
        ]

        for preset_id, title, icon_text in presets:
            card = SmartFindCard(preset_id, title, icon_text)
            card.clicked.connect(self.presetSelected.emit)
            self.layout.addWidget(card)
            self.cards[preset_id] = card

        self.layout.addStretch(1)

    def update_counts(self, counts: dict):
        counts = counts or {}
        for preset_id, card in self.cards.items():
            card.set_count(counts.get(preset_id))

    def set_active_preset(self, preset_id):
        self._active_preset = preset_id
        for pid, card in self.cards.items():
            card.set_active(pid == preset_id)

    def update_previews(self, preview_map: dict):
        preview_map = preview_map or {}
        for preset_id, card in self.cards.items():
            card.set_preview_labels(preview_map.get(preset_id, []))
