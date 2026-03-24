from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton, QToolButton
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QIcon, QAction

class TopSearchBar(QWidget):
    querySubmitted = Signal(str)
    queryChanged = Signal(str)
    searchCleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search photos, people, places, screenshots...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                border-radius: 20px;
                border: 1px solid #ddd;
                background-color: #f8f9fa;
                font-size: 11pt;
            }
            QLineEdit:focus {
                border: 1px solid #1a73e8;
                background-color: white;
            }
        """)

        # Connect signals
        self.search_input.textChanged.connect(self.queryChanged)
        self.search_input.returnPressed.connect(self._on_return_pressed)

        # Detect clear button click (LineEdit clear signal is not exposed directly, but text becomes empty)
        self.search_input.textChanged.connect(self._check_cleared)

        layout.addWidget(self.search_input)

    def _on_return_pressed(self):
        self.querySubmitted.emit(self.search_input.text())

    def _check_cleared(self, text):
        if not text:
            self.searchCleared.emit()

    def set_text(self, text):
        self.search_input.setText(text)

    def clear(self):
        self.search_input.clear()
