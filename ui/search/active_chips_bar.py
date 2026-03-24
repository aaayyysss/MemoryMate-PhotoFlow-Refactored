from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton


class ActiveChipsBar(QWidget):
    chipRemoved = Signal(str, object)
    clearAllRequested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

        self.store.stateChanged.connect(self._on_state_changed)

    def _clear_layout(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_state_changed(self, state):
        self._clear_layout()

        for chip in state.active_chips:
            label = chip.get("label", "Chip")
            kind = chip.get("kind")
            value = chip.get("value")

            btn = QPushButton(f"{label} ✕")
            btn.clicked.connect(lambda checked=False, k=kind, v=value: self.chipRemoved.emit(k, v))
            self.layout.addWidget(btn)

        if state.active_chips:
            clear_btn = QPushButton("Clear")
            clear_btn.clicked.connect(self.clearAllRequested.emit)
            self.layout.addWidget(clear_btn)

        self.layout.addStretch(1)
