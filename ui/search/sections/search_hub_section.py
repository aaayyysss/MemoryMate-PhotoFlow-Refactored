from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Signal, Qt
from ui.search.search_sidebar import SidebarSection

class SearchHubSection(SidebarSection):
    recentSearchClicked = Signal(str)
    suggestionClicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Search", parent)
        self._setup_content()

    def _setup_content(self):
        # Recent Searches
        self.lbl_recent = QLabel("Recent Searches")
        self.lbl_recent.setStyleSheet("color: #70757a; font-size: 9pt; margin-top: 8px;")

        self.recent_list = QListWidget()
        self.recent_list.setStyleSheet("border: none; background: transparent;")
        self.recent_list.setFixedHeight(100)
        self.recent_list.itemClicked.connect(lambda item: self.recentSearchClicked.emit(item.text()))

        # Suggestions
        self.lbl_suggest = QLabel("Suggestions")
        self.lbl_suggest.setStyleSheet("color: #70757a; font-size: 9pt; margin-top: 8px;")

        self.suggest_list = QListWidget()
        self.suggest_list.setStyleSheet("border: none; background: transparent;")
        self.suggest_list.setFixedHeight(100)
        self.suggest_list.itemClicked.connect(lambda item: self.suggestionClicked.emit(item.text()))

        self.content_layout.addWidget(self.lbl_recent)
        self.content_layout.addWidget(self.recent_list)
        self.content_layout.addWidget(self.lbl_suggest)
        self.content_layout.addWidget(self.suggest_list)

    def set_recent_searches(self, searches):
        self.recent_list.clear()
        for s in searches:
            self.recent_list.addItem(s)

    def set_suggestions(self, suggestions):
        self.suggest_list.clear()
        for s in suggestions:
            self.suggest_list.addItem(s)
