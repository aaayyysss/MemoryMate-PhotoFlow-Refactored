from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFrame, QGroupBox, QLabel

from ui.search.sections.search_hub_section import SearchHubSection
from ui.search.sections.discover_section import DiscoverSection
from ui.search.sections.filter_section import FilterSection


class SearchSidebar(QWidget):
    def __init__(self, store, controller=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.controller = controller

        self.search_hub_section = SearchHubSection()
        self.discover_section = DiscoverSection()
        self.filter_section = FilterSection()
        self.placeholder_people = self._make_placeholder_group("People Quick Pick", "UX-4")

        self._build_ui()
        self._wire_signals()

        self.store.stateChanged.connect(self._on_state_changed)

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
        scroll.setFrameShape(QFrame.NoFrame)

        content = QFrame()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(6, 6, 6, 6)
        self.content_layout.setSpacing(12)

        self.content_layout.addWidget(self.search_hub_section)
        self.content_layout.addWidget(self.discover_section)
        self.content_layout.addWidget(self.placeholder_people)
        self.content_layout.addWidget(self.filter_section)
        self.content_layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _wire_signals(self):
        if self.controller:
            self.discover_section.presetSelected.connect(self.controller.set_preset)

            self.search_hub_section.recentSearchClicked.connect(self.controller.submit_query)
            self.search_hub_section.suggestionClicked.connect(self.controller.submit_query)
            self.search_hub_section.clearRecentRequested.connect(self.controller.clear_recent_queries)

            self.filter_section.filterSelected.connect(self.controller.apply_filter)
            self.filter_section.clearFiltersRequested.connect(self.controller.clear_filters)

    def _on_state_changed(self, state):
        enabled = state.has_active_project

        self.search_hub_section.set_enabled_for_project(enabled)
        self.discover_section.setEnabled(enabled)
        self.filter_section.set_enabled_for_project(enabled)
        self.placeholder_people.setEnabled(enabled)

        self.search_hub_section.set_recent_queries(getattr(state, "recent_queries", []))
        self.search_hub_section.set_suggestions(getattr(state, "suggestions", []))

        self.discover_section.update_counts(getattr(state, "discover_counts", {}))
        self.discover_section.set_active_preset(getattr(state, "preset_id", None))

        self.filter_section.set_active_filters(getattr(state, "active_filters", {}))
        self.filter_section.update_facets(getattr(state, "result_facets", {}))
