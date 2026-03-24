from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QStackedWidget
)
from PySide6.QtCore import Signal
from ui.search.search_state_store import SearchStateStore, SearchState
from ui.search.search_results_header import SearchResultsHeader
from ui.search.active_chips_bar import ActiveChipsBar
from ui.search.empty_state_view import EmptyStateView

class ResultsPane(QWidget):
    def __init__(self, state_store: SearchStateStore, parent=None):
        super().__init__(parent)
        self.store = state_store
        self._setup_ui()
        self.store.stateChanged.connect(self._on_state_changed)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = SearchResultsHeader(self.store)
        self.chips_bar = ActiveChipsBar(self.store)

        # This will contain either the Grid or the Empty State
        self.stack = QStackedWidget()

        self.empty_state = EmptyStateView()
        self.grid_container = QWidget() # Placeholder for actual grid
        self.grid_layout = QVBoxLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)

        self.stack.addWidget(self.grid_container)
        self.stack.addWidget(self.empty_state)

        layout.addWidget(self.header)
        layout.addWidget(self.chips_bar)
        layout.addWidget(self.stack, 1)

    def set_grid_widget(self, widget: QWidget):
        # Clear existing grid layout
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        if widget:
            self.grid_layout.addWidget(widget)

    def _on_state_changed(self, state: SearchState):
        if state.empty_state_reason:
            self.empty_state.set_state(state.empty_state_reason)
            self.stack.setCurrentWidget(self.empty_state)
        else:
            self.stack.setCurrentWidget(self.grid_container)
