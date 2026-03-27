from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QComboBox
from shiboken6 import isValid


class SearchResultsHeader(QWidget):
    clearRequested = Signal()
    sortChanged = Signal(str)

    def __init__(self, store, controller=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.controller = controller
        self.setObjectName("SearchResultsHeader")
        self.setFixedHeight(72)

        # Top row: summary, badges, sort, count
        self.lbl_summary = QLabel("All Photos")
        self.lbl_summary.setStyleSheet("font-size: 18px; font-weight: 500; color: #202124;")

        self.badge_status = QLabel("Searching...")
        self.badge_status.setStyleSheet("""
            background: #fbbc04; color: black; border-radius: 10px;
            padding: 2px 10px; font-size: 11px; font-weight: bold;
        """)
        self.badge_status.setVisible(False)

        self.badge_model = QLabel("Low-tier model")
        self.badge_model.setToolTip("Upgrade model in Tools > Extract Embeddings for better results.")
        self.badge_model.setStyleSheet("""
            background: #fce8e6; color: #c5221f; border-radius: 4px;
            padding: 4px 8px; font-size: 11px;
        """)
        self.badge_model.setVisible(False)

        self.badge_warning = QLabel("")
        self.badge_warning.setObjectName("SearchWarningBadge")
        self.badge_warning.setStyleSheet("""
            background: #fff3e0; color: #e65100; border-radius: 4px;
            padding: 4px 8px; font-size: 11px;
        """)
        self.badge_warning.setVisible(False)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Relevance", "relevance")
        self.sort_combo.addItem("Date (Newest)", "date_desc")
        self.sort_combo.addItem("Date (Oldest)", "date_asc")
        self.sort_combo.addItem("Name", "name")
        self.sort_combo.setFixedWidth(140)
        self.sort_combo.setStyleSheet("QComboBox { font-size: 12px; }")
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)

        self.lbl_count = QLabel("0 photos")
        self.lbl_count.setStyleSheet("color: #5f6368; font-size: 13px;")

        top_row = QHBoxLayout()
        top_row.setContentsMargins(16, 0, 16, 0)
        top_row.addWidget(self.lbl_summary)
        top_row.addWidget(self.badge_status)
        top_row.addStretch(1)
        top_row.addWidget(self.badge_warning)
        top_row.addWidget(self.badge_model)
        top_row.addWidget(self.sort_combo)
        top_row.addWidget(self.lbl_count)

        # Bottom row: explanation + selection
        self.lbl_explanation = QLabel("")
        self.lbl_explanation.setObjectName("SearchExplanationLabel")
        self.lbl_explanation.setWordWrap(True)
        self.lbl_explanation.setStyleSheet("color: #5f6368; font-size: 12px; padding: 0 16px;")
        self.lbl_explanation.setVisible(False)

        self.lbl_selection = QLabel("")
        self.lbl_selection.setObjectName("SearchSelectionLabel")
        self.lbl_selection.setStyleSheet("color: #1a73e8; font-size: 12px; padding: 0 16px;")
        self.lbl_selection.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        outer.addLayout(top_row)
        outer.addWidget(self.lbl_explanation)
        outer.addWidget(self.lbl_selection)

        self.store.stateChanged.connect(self._on_state_changed)

    def _on_state_changed(self, state):
        if not isValid(self):
            return

        if state.onboarding_mode:
            self.lbl_summary.setText("No active project")
            self.lbl_count.setText("")
            self.badge_status.setVisible(False)
            self.badge_model.setVisible(False)
            self.badge_warning.setVisible(False)
            self.lbl_explanation.setVisible(False)
            self.lbl_selection.setVisible(False)
            return

        # Status badge
        if state.search_in_progress:
            self.lbl_summary.setText(state.intent_summary or "Searching...")
            self.badge_status.setText("Searching")
            self.badge_status.setVisible(True)
        else:
            self.lbl_summary.setText(state.intent_summary or "All Photos")
            self.badge_status.setVisible(False)

        self.lbl_count.setText(f"{state.result_count} result(s)")

        # Model warning badge
        has_model_warning = bool(state.model_warning)
        self.badge_model.setVisible(has_model_warning)
        if has_model_warning:
            self.badge_model.setToolTip(state.model_warning)

        # General warnings
        warnings = list(getattr(state, "warnings", []) or [])
        if warnings:
            self.badge_warning.setText(str(warnings[0]))
            self.badge_warning.setVisible(True)
        else:
            self.badge_warning.setVisible(False)

        # Selection indicator
        selected_ids = list(getattr(state, "selected_result_ids", []) or [])
        if selected_ids:
            self.lbl_selection.setText(f"{len(selected_ids)} item(s) selected")
            self.lbl_selection.setVisible(True)
        else:
            self.lbl_selection.setVisible(False)

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
