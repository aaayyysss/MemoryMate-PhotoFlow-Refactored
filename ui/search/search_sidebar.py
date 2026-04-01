from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFrame

from ui.search.sections.search_hub_section import SearchHubSection
from ui.search.sections.discover_section import DiscoverSection
from ui.search.sections.people_quick_section import PeopleQuickSection
from ui.search.sections.browse_section import BrowseSection
from ui.search.sections.filter_section import FilterSection
from ui.search.sections.activity_mini_section import ActivityMiniSection


class SearchSidebar(QWidget):
    """
    Production Google-shell sidebar with six sections:

    1. Search Hub   — recent searches, suggestions, quick scopes
    2. Discover     — smart-find presets
    3. People       — top people, merge review, unnamed clusters
    4. Browse       — all photos, favorites, videos, folders, dates, locations
    5. Filters      — facet chips, clear-all
    6. Activity     — background job summary, open activity center
    """

    # Parity signals for MainWindow/Controller integration
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

        # ── Section widgets ──
        self.search_hub = SearchHubSection()
        self.discover_section = DiscoverSection()
        self.people_section = PeopleQuickSection()
        self.browse_section = BrowseSection()
        self.filter_section = FilterSection()
        self.activity_section = ActivityMiniSection()

        self._build_ui()
        self._wire_signals()

        # React to search state changes
        self.store.stateChanged.connect(self._on_state_changed)

    # ── Layout ────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QFrame()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(6, 6, 6, 6)
        self.content_layout.setSpacing(10)

        self.content_layout.addWidget(self.search_hub)
        self.content_layout.addWidget(self.discover_section)
        self.content_layout.addWidget(self.people_section)
        self.content_layout.addWidget(self.browse_section)
        self.content_layout.addWidget(self.filter_section)
        self.content_layout.addWidget(self.activity_section)
        self.content_layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── Signal wiring ─────────────────────────────────────

    def _wire_signals(self):
        # Discover → controller
        if self.controller:
            self.discover_section.presetSelected.connect(self.controller.set_preset)
            self.search_hub.recentSearchClicked.connect(self.controller.submit_query)
            self.search_hub.suggestionClicked.connect(self.controller.submit_query)

        # Browse section → branch selection
        self.browse_section.browseRequested.connect(self._on_browse_requested)

        # People section → branch selection and person actions
        self.people_section.personRequested.connect(
            lambda person_id: self.selectBranch.emit(f"person_{person_id}")
        )
        self.people_section.reviewMergesRequested.connect(
            lambda: self.selectBranch.emit("people_review_merges")
        )
        self.people_section.reviewUnnamedRequested.connect(
            lambda: self.selectBranch.emit("people_review_unnamed")
        )
        self.people_section.showAllPeopleRequested.connect(
            lambda: self.selectBranch.emit("people_show_all")
        )
        self.people_section.peopleToolsRequested.connect(
            lambda: self.selectBranch.emit("people_tools")
        )

        # Legacy People row actions
        self.people_section.mergeHistoryRequested.connect(
            lambda: self.selectBranch.emit("people_merge_history")
        )
        self.people_section.undoMergeRequested.connect(
            lambda: self.selectBranch.emit("people_undo_merge")
        )
        self.people_section.redoMergeRequested.connect(
            lambda: self.selectBranch.emit("people_redo_merge")
        )
        self.people_section.expandPeopleRequested.connect(
            lambda: self.selectBranch.emit("people_expand")
        )

        # Activity → outbound
        self.activity_section.openActivityCenterRequested.connect(
            self.openActivityCenterRequested.emit
        )

    # ── State reactivity ──────────────────────────────────

    def _on_state_changed(self, state):
        enabled = state.has_active_project

        # Search Hub and Activity stay visible always
        self.search_hub.set_enabled_for_project(enabled)
        self.discover_section.setEnabled(enabled)
        self.browse_section.set_enabled_for_project(enabled)
        self.filter_section.set_enabled_for_project(enabled)
        self.activity_section.setEnabled(True)

        # People visibility controlled by its own set_people()

    # ── Public API for MainWindow bridge ──────────────────

    def set_people_payload(self, payload):
        """Update the People section from the people quick payload."""
        self.people_section.set_people(payload)

    def set_people_quick_payload(self, payload: dict) -> None:
        """Update People section with full parity payload."""
        payload = payload or {}

        self.people_section.set_people_rows(payload.get("top_people", []))
        self.people_section.set_counts(
            int(payload.get("merge_candidates", 0) or 0),
            int(payload.get("unnamed_count", 0) or 0),
        )

        self.people_section.set_legacy_actions_enabled(
            bool(payload.get("people_tools_enabled", True))
        )

    def set_browse_payload(self, payload: dict) -> None:
        """Update Browse section with counts and devices."""
        payload = payload or {}

        self.browse_section.set_counts(payload.get("counts", {}))
        self.browse_section.set_devices(payload.get("devices", []))

    def set_activity(self, activity):
        """Update the Activity section from job manager snapshot."""
        self.activity_section.set_activity(activity)

    def set_search_hub_recent(self, queries):
        """Update Search Hub recent queries."""
        self.search_hub.set_recent_queries(queries)

    def set_search_hub_suggestions(self, suggestions):
        """Update Search Hub suggestions."""
        self.search_hub.set_suggestions(suggestions)

    def set_facets(self, facets, active_filters, visible_keys=None):
        """Update the Filter section with search facets."""
        self.filter_section.set_facets(facets, active_filters, visible_keys)

    # ── Browse section handlers ──────────────────────────

    def _on_browse_requested(self, key: str) -> None:
        """Map browse key to selectBranch signal."""
        mapping = {
            "all": "all",
            "years": "dates",
            "months": "dates",
            "days": "dates",
            "folders": "folders",
            "devices": "devices",
            "favorites": "favorites",
            "videos": "videos",
            "documents": "documents",
            "screenshots": "screenshots",
            "duplicates": "duplicates",
            "locations": "locations",
            "today": "dates",
            "yesterday": "dates",
            "last_7_days": "dates",
            "last_30_days": "dates",
            "this_month": "dates",
            "last_month": "dates",
            "this_year": "dates",
            "last_year": "dates",
        }
        self.selectBranch.emit(mapping.get(key, "all"))

    # ── Parity methods for MainWindow deferred init ───────

    def reload_date_tree(self):
        pass

    def set_project(self, project_id: int):
        """Update sidebar context for new project."""
        pass

    def toggle_fold(self, folded: bool):
        """Handle sidebar collapse/expand."""
        self.setVisible(not folded)

    def _effective_display_mode(self):
        return "list"

    def switch_display_mode(self, mode: str):
        pass
