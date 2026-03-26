from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QPushButton, QHBoxLayout, QLabel


class DiscoverSection(QGroupBox):
    presetSelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Discovery", parent)
        self.setObjectName("DiscoverSection")

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
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 8px;
                    border: 1px solid #dadce0;
                    border-radius: 6px;
                    background: white;
                }
                QPushButton:hover { background: #f8f9fa; }
                QPushButton:checked {
                    background: #e8f0fe;
                    border-color: #1a73e8;
                    color: #1a73e8;
                    font-weight: bold;
                }
            """)
            btn.clicked.connect(lambda checked, p=preset_id: self.presetSelected.emit(p))
            self.layout.addWidget(btn)
            self.cards[preset_id] = btn

        self.layout.addStretch(1)

    def update_counts(self, counts: dict):
        for preset_id, btn in self.cards.items():
            count = counts.get(preset_id)
            # Remove existing count if any
            base_text = btn.text().split(" (")[0]
            if count is not None and count > 0:
                btn.setText(f"{base_text} ({count})")
            else:
                btn.setText(base_text)

    def set_active_preset(self, preset_id: str | None):
        self._active_preset = preset_id
        for pid, btn in self.cards.items():
            btn.blockSignals(True)
            btn.setChecked(pid == preset_id)
            btn.blockSignals(False)
