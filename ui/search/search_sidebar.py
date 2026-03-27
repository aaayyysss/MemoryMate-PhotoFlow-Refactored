from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFrame

from ui.search.sections.search_hub_section import SearchHubSection
from ui.search.sections.discover_section import DiscoverSection
from ui.search.sections.people_quick_section import PeopleQuickSection
from ui.search.sections.filter_section import FilterSection
from ui.search.sections.browse_section import BrowseSection
from ui.search.sections.activity_mini_section import ActivityMiniSection


class SearchSidebar(QWidget):
    folderSelected = Signal(int)
    selectBranch = Signal(str)
    selectDate = Signal(str)
    selectVideos = Signal(str)
    selectGroup = Signal(int)
    openActivityCenterRequested = Signal()

    def __init__(self, store, controller=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.controller = controller

        self.search_hub_section = SearchHubSection()
        self.discover_section = DiscoverSection()
        self.people_quick_section = PeopleQuickSection()
        self.browse_section = BrowseSection()
        self.filter_section = FilterSection()
        self.activity_mini_section = ActivityMiniSection()

        self._build_ui()
        self._wire_signals()

        self.store.stateChanged.connect(self._on_state_changed)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QFrame()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(6, 6, 6, 6)
        self.content_layout.setSpacing(10)

        self.content_layout.addWidget(self.search_hub_section)
        self.content_layout.addWidget(self.discover_section)
        self.content_layout.addWidget(self.people_quick_section)
        self.content_layout.addWidget(self.browse_section)
        self.content_layout.addWidget(self.filter_section)
        self.content_layout.addWidget(self.activity_mini_section)
        self.content_layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _wire_signals(self):
        if self.controller:
            self.discover_section.presetSelected.connect(self.controller.set_preset)

            self.search_hub_section.recentSearchClicked.connect(self.controller.submit_query)
            self.search_hub_section.suggestionClicked.connect(self.controller.submit_query)
            self.search_hub_section.clearRecentRequested.connect(self.controller.clear_recent_queries)

            self.people_quick_section.personSelected.connect(self.controller.apply_people_filter)
            self.people_quick_section.showAllPeopleRequested.connect(self._emit_show_all_people)
            self.people_quick_section.mergeReviewRequested.connect(self._emit_merge_review)
            self.people_quick_section.unnamedRequested.connect(self._emit_unnamed_people)

            self.browse_section.browseNodeSelected.connect(self.controller.apply_browse_mode)

            self.filter_section.filterChanged.connect(self.controller.apply_filter)
            self.filter_section.clearAllFiltersRequested.connect(self.controller.clear_filters)

            self.activity_mini_section.openActivityCenterRequested.connect(self.openActivityCenterRequested.emit)

    def _emit_show_all_people(self):
        self.selectBranch.emit("people")

    def _emit_merge_review(self):
        self.selectBranch.emit("people_merge_review")

    def _emit_unnamed_people(self):
        self.selectBranch.emit("people_unnamed")

    def _on_state_changed(self, state):
        enabled = state.has_active_project
        self.discover_section.setEnabled(enabled)
        self.people_quick_section.setEnabled(enabled)

        # placeholder sections if they exist in state - search_sidebar doesn't
        # directly expose placeholder_filters etc by those names in __init__
        # but the request implies we should gate sections.
        # Following the request exactly:
        if hasattr(self, "placeholder_people"):
            self.placeholder_people.setEnabled(enabled)
        if hasattr(self, "placeholder_filters"):
            self.placeholder_filters.setEnabled(enabled)

        # Maintain existing UX-2+ functionality while applying UX-1 state gating
        self.search_hub_section.set_enabled_for_project(enabled)
        self.browse_section.set_enabled_for_project(enabled)

        self.search_hub_section.set_recent_queries(getattr(state, "recent_queries", []))
        self.search_hub_section.set_suggestions(getattr(state, "suggestions", []))

        self.discover_section.update_counts(getattr(state, "discover_counts", {}))
        self.discover_section.set_active_preset(getattr(state, "preset_id", None))
        self.discover_section.update_previews(getattr(state, "discover_previews", {}))

        self.people_quick_section.set_people(getattr(state, "people_quick_payload", {}))
        self.browse_section.set_active_mode(getattr(state, "browse_mode", None))

        # UX Rule 3: show filters only when a search/preset/query is active
        has_search_context = bool(
            getattr(state, "query_text", "")
            or getattr(state, "preset_id", None)
            or getattr(state, "active_filters", {})
            or getattr(state, "browse_mode", None)
        )
        result_facets = getattr(state, "result_facets", {}) or {}
        active_filters = getattr(state, "active_filters", {}) or {}

        if has_search_context:
            self.filter_section.set_facets(result_facets, active_filters)
            self.filter_section.setVisible(True)
        else:
            self.filter_section.setVisible(False)

        self.activity_mini_section.set_activity(getattr(state, "activity_snapshot", {}) or {})

    def reload_date_tree(self):
        pass

    def set_project(self, project_id: int):
        pass

    def toggle_fold(self, folded: bool):
        self.setVisible(not folded)

    def _effective_display_mode(self):
        return "list"

    def switch_display_mode(self, mode: str):
        pass
