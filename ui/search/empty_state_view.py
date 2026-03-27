from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class EmptyStateView(QWidget):
    actionRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.label = QLabel("No results")
        self.label.setWordWrap(True)
        self.label.setObjectName("EmptyStateLabel")

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.label)
        layout.addStretch(1)

    def set_message(self, text: str):
        self.label.setText(text or "No results")

    def set_state(self, reason: str, warnings=None):
        """
        UX-1 compliant state switcher.
        Keeps the UI minimal while preventing AttributeErrors.
        """
        if reason == "no_project":
            self.set_message("No active project")
        elif reason == "loading":
            self.set_message("Searching...")
        elif reason == "no_results":
            self.set_message("No results found")
        else:
            self.set_message(f"No results ({reason})")
