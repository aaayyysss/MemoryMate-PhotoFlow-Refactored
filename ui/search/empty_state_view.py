from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from shiboken6 import isValid


class EmptyStateView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel("No results")
        self.label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.label)
        layout.addStretch(1)

    def set_message(self, text: str):
        if hasattr(self, 'label') and isValid(self.label):
            self.label.setText(text or "No results")

    def set_state(self, reason: str):
        """Compatibility method for SearchState integration."""
        if not isValid(self):
            return

        mapping = {
            "no_project": "No project selected. Please create or open a project.",
            "no_results": "No results found for your search.",
            "indexing": "Indexing in progress...",
        }
        self.set_message(mapping.get(reason, "No results"))
