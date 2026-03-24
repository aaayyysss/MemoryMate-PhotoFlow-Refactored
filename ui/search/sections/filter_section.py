from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
)
from PySide6.QtCore import Signal, Qt
from ui.search.search_sidebar import SidebarSection

class FilterGroup(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

        lbl = QLabel(title)
        lbl.setStyleSheet("color: #70757a; font-size: 8pt; font-weight: 500;")
        layout.addWidget(lbl)

        self.options_layout = QVBoxLayout()
        self.options_layout.setSpacing(1)
        layout.addLayout(self.options_layout)

class FilterSection(SidebarSection):
    filterChanged = Signal(str, object)
    filterRemoved = Signal(str, object)
    clearAllFiltersRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("Filters", parent)
        self._setup_content()
        self.hide() # Hidden until search is active

    def _setup_content(self):
        self.groups_container = QVBoxLayout()
        self.content_layout.addLayout(self.groups_container)

        self.btn_clear = QPushButton("Clear all filters")
        self.btn_clear.setFlat(True)
        self.btn_clear.setStyleSheet("color: #d93025; font-size: 9pt; text-align: left; margin-top: 8px;")
        self.btn_clear.clicked.connect(self.clearAllFiltersRequested)
        self.content_layout.addWidget(self.btn_clear)

    def update_facets(self, facets):
        # Clear existing
        while self.groups_container.count():
            item = self.groups_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not facets:
            self.hide()
            return

        self.show()

        # facets: { "media": {"Photos": 10, "Videos": 2}, "years": {"2024": 5, "2023": 7} }
        for group_name, options in facets.items():
            group = FilterGroup(group_name.title())
            for opt_name, count in options.items():
                btn = QPushButton(f"{opt_name} ({count})")
                btn.setFlat(True)
                btn.setStyleSheet("""
                    QPushButton {
                        text-align: left;
                        padding: 4px 8px;
                        font-size: 9pt;
                        color: #3c4043;
                    }
                    QPushButton:hover {
                        background-color: #f1f3f4;
                    }
                """)
                btn.clicked.connect(lambda _, k=group_name, v=opt_name: self.filterChanged.emit(k, v))
                group.options_layout.addWidget(btn)
            self.groups_container.addWidget(group)
