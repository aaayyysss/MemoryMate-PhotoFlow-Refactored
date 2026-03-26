from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QPushButton


class DiscoverSection(QGroupBox):
    presetSelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Discover", parent)

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(6)
        self.cards = {}
        self._active_preset = None

        self._build_default_cards()

    def _build_default_cards(self):
        presets = [
            ("beach", "🌊 Beach"),
            ("mountains", "🏔 Mountains"),
            ("city", "🌆 City"),
            ("forest", "🌲 Forest"),
            ("documents", "📄 Documents"),
            ("screenshots", "📱 Screenshots"),
        ]

        for preset_id, label in presets:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, p=preset_id: self.presetSelected.emit(p))
            self.layout.addWidget(btn)
            self.cards[preset_id] = btn

        self.layout.addStretch(1)

    def update_counts(self, counts: dict):
        for preset_id, btn in self.cards.items():
            count = counts.get(preset_id)
            base_text = btn.text().split(" (")[0]
            if count is None:
                btn.setText(base_text)
            else:
                btn.setText(f"{base_text} ({count})")

    def set_active_preset(self, preset_id: str | None):
        self._active_preset = preset_id
        for pid, btn in self.cards.items():
            if pid == preset_id:
                btn.setProperty("activePreset", True)
                btn.setStyleSheet("""
                    QPushButton {
                        background: #d2e3fc;
                        border: 1px solid #8ab4f8;
                        border-radius: 6px;
                        padding: 6px 10px;
                        font-weight: 600;
                    }
                """)
            else:
                btn.setProperty("activePreset", False)
                btn.setStyleSheet("")
