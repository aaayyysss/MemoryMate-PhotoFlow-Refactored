from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame, QComboBox


class SearchResultsHeader(QWidget):
    clearRequested = Signal()
    sortChanged = Signal(str)

    def __init__(self, store, controller=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.controller = controller
        self.setObjectName("SearchResultsHeader")
        self.setFixedHeight(50)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(16, 0, 16, 0)

        # Left: Intent Summary
        self.lbl_summary = QLabel("All Photos")
        self.lbl_summary.setStyleSheet("font-size: 18px; font-weight: 500; color: #202124;")
        self.layout.addWidget(self.lbl_summary)

        # Status Badge (Searching...)
        self.badge_status = QLabel("Searching...")
        self.badge_status.setStyleSheet("""
            background: #fbbc04; color: black; border-radius: 10px;
            padding: 2px 10px; font-size: 11px; font-weight: bold;
        """)
        self.badge_status.setVisible(False)
        self.layout.addWidget(self.badge_status)

        self.layout.addStretch(1)

        # Model Warning Badge
        self.badge_model = QLabel("Low-tier model")
        self.badge_model.setToolTip("Upgrade model in Tools > Extract Embeddings for better results.")
        self.badge_model.setStyleSheet("""
            background: #fce8e6; color: #c5221f; border-radius: 4px;
            padding: 4px 8px; font-size: 11px;
        """)
        self.badge_model.setVisible(False)
        self.layout.addWidget(self.badge_model)

        # Sort Selector
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Relevance", "relevance")
        self.sort_combo.addItem("Date (Newest)", "date_desc")
        self.sort_combo.addItem("Date (Oldest)", "date_asc")
        self.sort_combo.addItem("Name", "name")
        self.sort_combo.setFixedWidth(140)
        self.sort_combo.setStyleSheet("QComboBox { font-size: 12px; }")
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self.layout.addWidget(self.sort_combo)

        # Right: Count
        self.lbl_count = QLabel("0 photos")
        self.lbl_count.setStyleSheet("color: #5f6368; font-size: 13px;")
        self.layout.addWidget(self.lbl_count)

        self.store.stateChanged.connect(self._on_state_changed)

    def _on_state_changed(self, state):
        if state.onboarding_mode:
            self.lbl_summary.setText("No active project")
            self.lbl_count.setText("")
            self.badge_status.setVisible(False)
            self.badge_model.setVisible(False)
            return

        # Status Badge (Searching...)
        self.badge_status.setVisible(state.search_in_progress)

        # Model Warning Badge
        has_model_warning = bool(state.model_warning)
        self.badge_model.setVisible(has_model_warning)
        if has_model_warning:
            self.badge_model.setToolTip(state.model_warning)

        if state.search_in_progress:
            self.lbl_summary.setText(state.intent_summary or "Searching...")
        else:
            self.lbl_summary.setText(state.intent_summary or "All Photos")

        self.lbl_count.setText(f"{state.result_count} result(s)")

        # Sync sort selector without re-triggering signal
        current_sort = getattr(state, "sort_mode", "relevance")
        idx = self.sort_combo.findData(current_sort)
        if idx >= 0 and idx != self.sort_combo.currentIndex():
            self.sort_combo.blockSignals(True)
            self.sort_combo.setCurrentIndex(idx)
            self.sort_combo.blockSignals(False)

    def _on_sort_changed(self, index: int):
        sort_mode = self.sort_combo.itemData(index)
        if sort_mode:
            self.sortChanged.emit(sort_mode)
            if self.controller and hasattr(self.controller, "apply_sort"):
                self.controller.apply_sort(sort_mode)
