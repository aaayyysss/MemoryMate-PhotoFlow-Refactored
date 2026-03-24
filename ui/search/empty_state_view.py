from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QSizePolicy
)
from PySide6.QtCore import Qt

class EmptyStateView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        self.lbl_icon = QLabel("🔍")
        self.lbl_icon.setStyleSheet("font-size: 64pt;")
        self.lbl_icon.setAlignment(Qt.AlignCenter)

        self.lbl_title = QLabel("No results found")
        self.lbl_title.setStyleSheet("font-size: 16pt; font-weight: bold; color: #333;")
        self.lbl_title.setAlignment(Qt.AlignCenter)

        self.lbl_message = QLabel("Try adjusting your search or filters to find what you're looking for.")
        self.lbl_message.setStyleSheet("font-size: 11pt; color: #666;")
        self.lbl_message.setAlignment(Qt.AlignCenter)
        self.lbl_message.setWordWrap(True)
        self.lbl_message.setMaximumWidth(400)

        layout.addWidget(self.lbl_icon)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_message)

    def set_state(self, reason: str):
        if reason == "no_project":
            self.lbl_icon.setText("📂")
            self.lbl_title.setText("No project selected")
            self.lbl_message.setText("Create or select a project to begin exploring your photos.")
        elif reason == "no_results":
            self.lbl_icon.setText("🔍")
            self.lbl_title.setText("No matches found")
            self.lbl_message.setText("We couldn't find any photos matching your current search and filters.")
        elif reason == "indexing":
            self.lbl_icon.setText("⏳")
            self.lbl_title.setText("Indexing in progress")
            self.lbl_message.setText("We're still processing your photos. Results will appear here soon.")
        elif reason == "embeddings_missing":
            self.lbl_icon.setText("🧠")
            self.lbl_title.setText("AI search not ready")
            self.lbl_message.setText("Extract embeddings to enable powerful semantic search across your library.")
        else:
            self.lbl_icon.setText("🔍")
            self.lbl_title.setText("Ready to search")
            self.lbl_message.setText("Start typing above or explore the presets in the sidebar.")
