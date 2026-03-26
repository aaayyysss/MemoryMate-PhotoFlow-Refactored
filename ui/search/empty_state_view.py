from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame


class EmptyStateView(QFrame):
    actionRequested = Signal(str)  # "select_project", "scan", "extract_embeddings"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EmptyStateView")
        self.setStyleSheet("QFrame#EmptyStateView { background: white; }")

        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignCenter)
        self.layout.setSpacing(16)

        # Icon/Illustration Placeholder
        self.lbl_icon = QLabel("🖼️")
        self.lbl_icon.setStyleSheet("font-size: 64px; margin-bottom: 8px;")
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.lbl_icon)

        # Title
        self.lbl_title = QLabel("No Photos Yet")
        self.lbl_title.setStyleSheet("font-size: 20px; font-weight: 500; color: #202124;")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.lbl_title)

        # Message
        self.lbl_message = QLabel("Get started by scanning a folder or selecting a project.")
        self.lbl_message.setStyleSheet("font-size: 14px; color: #5f6368;")
        self.lbl_message.setWordWrap(True)
        self.lbl_message.setFixedWidth(400)
        self.lbl_message.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.lbl_message)

        # Warnings (hidden by default)
        self.lbl_warnings = QLabel("")
        self.lbl_warnings.setStyleSheet("color: #d93025; font-size: 12px; font-style: italic;")
        self.lbl_warnings.setWordWrap(True)
        self.lbl_warnings.setFixedWidth(400)
        self.lbl_warnings.setAlignment(Qt.AlignCenter)
        self.lbl_warnings.setVisible(False)
        self.layout.addWidget(self.lbl_warnings)

        # Action Button
        self.btn_action = QPushButton("Select Project")
        self.btn_action.setCursor(Qt.PointingHandCursor)
        self.btn_action.setStyleSheet("""
            QPushButton {
                background: #1a73e8; color: white; border: none;
                border-radius: 4px; padding: 10px 24px; font-weight: 500;
            }
            QPushButton:hover { background: #1765cc; }
        """)
        self.btn_action.clicked.connect(self._on_action_clicked)
        self.layout.addWidget(self.btn_action, 0, Qt.AlignCenter)

    def set_state(self, reason: str, warnings: list = None):
        """Configure view for different empty states."""
        self._current_reason = reason

        if reason == "no_project":
            self.lbl_icon.setText("📁")
            self.lbl_title.setText("Welcome to MemoryMate")
            self.lbl_message.setText("Create a new project or select an existing one to see your photos.")
            self.btn_action.setText("Select Project")
            self.btn_action.setVisible(True)
        elif reason == "no_results":
            self.lbl_icon.setText("🔍")
            self.lbl_title.setText("No matching photos")
            self.lbl_message.setText("Try a different search, preset, or filter.")
            self.btn_action.setVisible(False)
        elif reason == "needs_embeddings":
            self.lbl_icon.setText("🧠")
            self.lbl_title.setText("AI Search Not Ready")
            self.lbl_message.setText("To search by description, you need to extract AI embeddings first.")
            self.btn_action.setText("Extract Embeddings")
            self.btn_action.setVisible(True)
        else:
            self.lbl_icon.setText("🖼️")
            self.lbl_title.setText("No results")
            self.lbl_message.setText(reason)
            self.btn_action.setVisible(False)

        if warnings:
            self.lbl_warnings.setText("\n".join(warnings))
            self.lbl_warnings.setVisible(True)
        else:
            self.lbl_warnings.setVisible(False)

    def _on_action_clicked(self):
        if self.btn_action.text() == "Select Project":
            self.actionRequested.emit("select_project")
        elif self.btn_action.text() == "Extract Embeddings":
            self.actionRequested.emit("extract_embeddings")
