from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QFrame
)
from PySide6.QtCore import Signal, Qt
from ui.search.search_state_store import SearchStateStore, SearchState

class ChipWidget(QFrame):
    removed = Signal()

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Chip")
        self.setStyleSheet("""
            #Chip {
                background-color: #e8f0fe;
                border: 1px solid #d2e3fc;
                border-radius: 16px;
                padding: 2px 8px;
            }
            QLabel {
                color: #1967d2;
                font-weight: 500;
                font-size: 10pt;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #1967d2;
                font-weight: bold;
                font-size: 12pt;
                padding: 0 4px;
            }
            QPushButton:hover {
                color: #d93025;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        lbl = QLabel(label)
        btn_close = QPushButton("×")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.removed)

        layout.addWidget(lbl)
        layout.addWidget(btn_close)

class ActiveChipsBar(QWidget):
    chipRemoved = Signal(str, object) # kind, value
    clearAllRequested = Signal()

    def __init__(self, state_store: SearchStateStore, parent=None):
        super().__init__(parent)
        self.store = state_store
        self._setup_ui()
        self.store.stateChanged.connect(self._on_state_changed)

    def _setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(16, 4, 16, 4)
        self.main_layout.setSpacing(8)

        self.chips_container = QWidget()
        self.chips_layout = QHBoxLayout(self.chips_container)
        self.chips_layout.setContentsMargins(0, 0, 0, 0)
        self.chips_layout.setSpacing(8)

        self.btn_clear = QPushButton("Clear all")
        self.btn_clear.setStyleSheet("""
            QPushButton {
                color: #1a73e8;
                background: transparent;
                border: none;
                font-weight: 500;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        self.btn_clear.clicked.connect(self.clearAllRequested)
        self.btn_clear.hide()

        self.main_layout.addWidget(self.chips_container)
        self.main_layout.addWidget(self.btn_clear)
        self.main_layout.addStretch()

    def _on_state_changed(self, state: SearchState):
        # Clear existing chips
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        chips = state.active_chips
        for chip_data in chips:
            kind = chip_data["kind"]
            label = chip_data["label"]
            value = chip_data["value"]

            chip = ChipWidget(label)
            chip.removed.connect(lambda k=kind, v=value: self.chipRemoved.emit(k, v))
            self.chips_layout.addWidget(chip)

        self.btn_clear.setVisible(len(chips) > 0)
        self.setVisible(len(chips) > 0)
