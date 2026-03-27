from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QScrollArea, QFrame


class ActiveChipsBar(QWidget):
    chipRemoved = Signal(str, object)
    clearAllRequested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.content = QWidget()
        self.layout = QHBoxLayout(self.content)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll)

        self.store.stateChanged.connect(self._on_state_changed)
        self.setVisible(False)

    def _clear_layout(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_state_changed(self, state):
        self._clear_layout()

        if not state.active_chips:
            self.setVisible(False)
            return

        self.setVisible(True)

        for chip in state.active_chips:
            label = chip.get("label", "Chip")
            kind = chip.get("kind")
            value = chip.get("value")

            btn = QPushButton(f"{label} ✕")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=kind, v=value: self.chipRemoved.emit(k, v))
            self.layout.addWidget(btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self.clearAllRequested.emit)
        self.layout.addWidget(clear_btn)

        self.layout.addStretch(1)
