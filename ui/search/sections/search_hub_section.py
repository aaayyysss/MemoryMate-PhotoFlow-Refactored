from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel


class SearchHubSection(QGroupBox):
    recentSearchClicked = Signal(str)
    suggestionClicked = Signal(str)
    clearRecentRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("Search", parent)

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(6)

        self.lbl_recent = QLabel("Recent Searches")
        self.list_recent = QListWidget()
        self.list_recent.setMaximumHeight(120)

        self.lbl_suggestions = QLabel("Suggestions")
        self.list_suggestions = QListWidget()
        self.list_suggestions.setMaximumHeight(150)

        self.btn_clear_recent = QPushButton("Clear Recent")
        self.btn_clear_recent.setObjectName("SearchHubClearButton")

        self.layout.addWidget(self.lbl_recent)
        self.layout.addWidget(self.list_recent)
        self.layout.addWidget(self.btn_clear_recent)
        self.layout.addWidget(self.lbl_suggestions)
        self.layout.addWidget(self.list_suggestions)
        self.layout.addStretch(1)

        self.list_recent.itemClicked.connect(self._on_recent_clicked)
        self.list_suggestions.itemClicked.connect(self._on_suggestion_clicked)
        self.btn_clear_recent.clicked.connect(self.clearRecentRequested.emit)

    def _on_recent_clicked(self, item: QListWidgetItem):
        self.recentSearchClicked.emit(item.text().strip())

    def _on_suggestion_clicked(self, item: QListWidgetItem):
        self.suggestionClicked.emit(item.text().strip())

    def set_recent_queries(self, queries):
        self.list_recent.clear()
        for q in list(queries or [])[:10]:
            self.list_recent.addItem(QListWidgetItem(str(q)))

        visible = self.list_recent.count() > 0
        self.lbl_recent.setVisible(visible)
        self.list_recent.setVisible(visible)
        self.btn_clear_recent.setVisible(visible)

    def set_suggestions(self, suggestions):
        self.list_suggestions.clear()
        for s in list(suggestions or [])[:12]:
            self.list_suggestions.addItem(QListWidgetItem(str(s)))

        visible = self.list_suggestions.count() > 0
        self.lbl_suggestions.setVisible(visible)
        self.list_suggestions.setVisible(visible)

    def set_enabled_for_project(self, enabled: bool):
        self.setEnabled(enabled)
