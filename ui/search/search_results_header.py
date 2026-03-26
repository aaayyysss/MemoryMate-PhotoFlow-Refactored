from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame


class SearchResultsHeader(QWidget):
    clearRequested = Signal()

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
        self.badge_model = QLabel("⚠️ Low-tier model")
        self.badge_model.setToolTip("Upgrade model in Tools > Extract Embeddings for better results.")
        self.badge_model.setStyleSheet("""
            background: #fce8e6; color: #c5221f; border-radius: 4px;
            padding: 4px 8px; font-size: 11px;
        """)
        self.badge_model.setVisible(False)
        self.layout.addWidget(self.badge_model)

        # Right: Count
        self.lbl_count = QLabel("0 photos")
        self.lbl_count.setStyleSheet("color: #5f6368; font-size: 13px;")
        self.layout.addWidget(self.lbl_count)

        self.store.stateChanged.connect(self._on_state_changed)

    def _on_state_changed(self, state):
        # Update summary
        if state.onboarding_mode:
            self.lbl_summary.setText("No active project")
            self.lbl_count.setText("")
        elif state.preset_id:
            self.lbl_summary.setText(f"Showing {state.preset_id.capitalize()}")
        elif state.query_text:
            self.lbl_summary.setText(f'Results for "{state.query_text}"')
        elif state.active_filters:
            self.lbl_summary.setText("Filtered Results")
        else:
            self.lbl_summary.setText("All Photos")

        # Update count
        if not state.onboarding_mode:
            self.lbl_count.setText(f"{state.result_count:,} photo(s)")

        # Update Searching badge
        self.badge_status.setVisible(state.search_in_progress)

        # Update Model badge
        self.badge_model.setText(state.model_warning or "⚠️ Low-tier model")
        self.badge_model.setVisible(bool(state.model_warning))
