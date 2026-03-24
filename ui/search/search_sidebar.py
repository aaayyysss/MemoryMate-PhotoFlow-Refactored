from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFrame, QGroupBox, QLabel

from ui.search.sections.discover_section import DiscoverSection


class SearchSidebar(QWidget):
    def __init__(self, store, controller=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.controller = controller

        self.discover_section = DiscoverSection()
        self.placeholder_search = self._make_placeholder_group("Search Hub", "UX-2")
        self.placeholder_filters = self._make_placeholder_group("Filters", "UX-3")
        self.placeholder_people = self._make_placeholder_group("People", "UX-4")

        self._build_ui()
        self._wire_signals()

    def _make_placeholder_group(self, title: str, subtitle: str):
        grp = QGroupBox(title)
        lay = QVBoxLayout(grp)
        lay.addWidget(QLabel(f"Coming in {subtitle}"))
        return grp

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QFrame()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(6, 6, 6, 6)
        self.content_layout.setSpacing(10)

        self.content_layout.addWidget(self.placeholder_search)
        self.content_layout.addWidget(self.discover_section)
        self.content_layout.addWidget(self.placeholder_people)
        self.content_layout.addWidget(self.placeholder_filters)
        self.content_layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _wire_signals(self):
        if self.controller:
            self.discover_section.presetSelected.connect(self.controller.set_preset)
