from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from ui.search.search_state_store import SearchStateStore, SearchState

class SearchResultsHeader(QWidget):
    sortModeChanged = Signal(str)

    def __init__(self, state_store: SearchStateStore, parent=None):
        super().__init__(parent)
        self.store = state_store
        self._setup_ui()
        self.store.stateChanged.connect(self._on_state_changed)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)

        self.lbl_summary = QLabel("All Photos")
        self.lbl_summary.setStyleSheet("font-size: 14pt; font-weight: bold; color: #333;")

        self.lbl_count = QLabel("0 results")
        self.lbl_count.setStyleSheet("color: #666; margin-left: 8px;")

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Relevance", "Date (Newest)", "Date (Oldest)", "Size"])
        self.sort_combo.currentTextChanged.connect(self.sortModeChanged)

        layout.addWidget(self.lbl_summary)
        layout.addWidget(self.lbl_count)
        layout.addStretch()
        layout.addWidget(QLabel("Sort by:"))
        layout.addWidget(self.sort_combo)

    def _on_state_changed(self, state: SearchState):
        summary = state.intent_summary or "All Photos"
        self.lbl_summary.setText(summary)

        count_text = f"{state.result_count:,} result" + ("s" if state.result_count != 1 else "")
        self.lbl_count.setText(count_text)

        # Sync sort combo if needed
        # ...
