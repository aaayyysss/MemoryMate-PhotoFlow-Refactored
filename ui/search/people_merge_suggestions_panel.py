from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem


class PeopleMergeSuggestionsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.lbl_title = QLabel("Possible People Merges")
        self.list_widget = QListWidget()

        layout = QVBoxLayout(self)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.list_widget)

    def set_suggestions(self, suggestions):
        self.list_widget.clear()
        for s in list(suggestions or []):
            text = s if isinstance(s, str) else str(s)
            self.list_widget.addItem(QListWidgetItem(text))
