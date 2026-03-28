from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton


class EmptyStateView(QWidget):
    actionRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # UX-10: Icon for visual polish
        self.lbl_icon = QLabel("\U0001f4f7")
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        self.lbl_icon.setStyleSheet("font-size: 36px; padding: 0;")

        self.label = QLabel("No results")
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setObjectName("EmptyStateLabel")
        self.label.setStyleSheet("""
            QLabel#EmptyStateLabel {
                font-size: 20px;
                font-weight: 600;
                color: #202124;
                padding: 12px 24px;
            }
        """)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setStyleSheet("color: #666; font-size: 13px; padding: 0 24px;")
        self.hint_label.setVisible(False)

        self.action_btn = QPushButton()
        self.action_btn.setVisible(False)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background: #1a73e8; color: white;
                border: none; border-radius: 6px;
                padding: 8px 20px; font-size: 13px;
            }
            QPushButton:hover { background: #1765cc; }
        """)
        self.action_btn.clicked.connect(self._on_action_clicked)
        self._pending_action = ""

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.lbl_icon, 0, Qt.AlignCenter)
        layout.addWidget(self.label, 0, Qt.AlignCenter)
        layout.addWidget(self.hint_label, 0, Qt.AlignCenter)
        layout.addWidget(self.action_btn, 0, Qt.AlignCenter)
        layout.addStretch(1)

    def set_message(self, text: str):
        self.label.setText(text or "No results")

    def set_state(self, reason: str, warnings=None):
        """
        UX-10A full empty-state handler:
        - no_project: no project loaded
        - no_results: search returned nothing
        - loading: search in progress (previous results may remain visible)
        - indexing / indexing_in_progress: background indexing running
        - embeddings_missing: embeddings not yet extracted
        - face_clustering_incomplete: face pipeline still running
        """
        warnings = list(warnings or [])
        self.hint_label.setVisible(False)
        self.action_btn.setVisible(False)
        self._pending_action = ""

        if reason == "no_project":
            self.set_message("No active project")
            self._show_hint("Create or select a project to begin browsing and searching.")
            self._show_action("Select Project", "create_or_select_project")

        elif reason == "loading":
            self.set_message("Searching")
            self._show_hint(
                "Preparing refined results. Previous results may remain "
                "visible while the new result set is computed."
            )

        elif reason == "no_results":
            extra = f"\n\n{warnings[0]}" if warnings else ""
            self.set_message("No results found")
            self._show_hint(
                "Try removing filters, using a broader term, or "
                "selecting a different category." + extra
            )

        elif reason in ("indexing", "indexing_in_progress"):
            self.set_message("Indexing in progress")
            self._show_hint(
                "Background indexing is still running. Results may "
                "improve as processing completes."
            )

        elif reason == "embeddings_missing":
            self.set_message("Semantic search unavailable")
            self._show_hint(
                "Run Tools > Extract Embeddings to enable AI-powered search "
                "for scenes, objects, and concepts."
            )
            self._show_action("Extract Embeddings", "extract_embeddings")

        elif reason == "face_clustering_incomplete":
            self.set_message("Face clustering in progress")
            self._show_hint("People results will appear once face detection and clustering complete.")

        else:
            self.set_message(f"No results ({reason})")

    def _show_hint(self, text: str):
        self.hint_label.setText(text)
        self.hint_label.setVisible(True)

    def _show_action(self, label: str, action_key: str):
        self.action_btn.setText(label)
        self._pending_action = action_key
        self.action_btn.setVisible(True)

    def _on_action_clicked(self):
        if self._pending_action:
            self.actionRequested.emit(self._pending_action)
