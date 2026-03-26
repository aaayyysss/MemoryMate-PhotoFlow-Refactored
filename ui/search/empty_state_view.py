from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton


class EmptyStateView(QWidget):
    actionRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.lbl_title = QLabel("No results")
        self.lbl_title.setObjectName("EmptyStateTitle")

        self.lbl_message = QLabel("")
        self.lbl_message.setWordWrap(True)
        self.lbl_message.setObjectName("EmptyStateMessage")

        self.btn_primary = QPushButton()
        self.btn_primary.setVisible(False)
        self.btn_primary.clicked.connect(self._emit_primary)

        self._primary_action = ""

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_message)
        layout.addWidget(self.btn_primary)
        layout.addStretch(1)

        self.set_state("no_results")

    def _emit_primary(self):
        if self._primary_action:
            self.actionRequested.emit(self._primary_action)

    def set_state(self, reason: str, warnings=None):
        warnings = list(warnings or [])

        if reason == "no_project":
            self.lbl_title.setText("No active project")
            self.lbl_message.setText("Create or select a project to begin browsing and searching.")
            self._primary_action = "create_or_select_project"
            self.btn_primary.setText("Select Project")
            self.btn_primary.setVisible(True)

        elif reason == "embeddings_missing":
            self.lbl_title.setText("Embeddings not ready")
            self.lbl_message.setText("Smart search quality will improve after extracting embeddings.")
            self._primary_action = "extract_embeddings"
            self.btn_primary.setText("Extract Embeddings")
            self.btn_primary.setVisible(True)

        elif reason == "indexing":
            self.lbl_title.setText("Indexing in progress")
            self.lbl_message.setText("Background indexing is still running. Results may improve as processing completes.")
            self._primary_action = ""
            self.btn_primary.setVisible(False)

        elif reason == "loading":
            self.lbl_title.setText("Loading")
            self.lbl_message.setText("Preparing results...")
            self._primary_action = ""
            self.btn_primary.setVisible(False)

        else:
            self.lbl_title.setText("No results")
            extra = f"\n\n{warnings[0]}" if warnings else ""
            self.lbl_message.setText("No matches were found. Try a broader query or remove some filters." + extra)
            self._primary_action = ""
            self.btn_primary.setVisible(False)
