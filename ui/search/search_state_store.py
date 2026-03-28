from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from PySide6.QtCore import QObject, Signal


@dataclass
class SearchState:
    active_project_id: Optional[int] = None
    has_active_project: bool = False
    onboarding_mode: bool = False

    query_text: str = ""
    preset_id: Optional[str] = None
    family: Optional[str] = None
    intent_summary: str = ""

    active_people: List[str] = field(default_factory=list)
    active_filters: Dict[str, Any] = field(default_factory=dict)
    active_chips: List[Dict[str, Any]] = field(default_factory=list)

    result_paths: List[str] = field(default_factory=list)
    result_count: int = 0
    result_facets: Dict[str, Any] = field(default_factory=dict)

    sort_mode: str = "relevance"
    media_scope: str = "all"
    search_mode: str = "hybrid"

    search_in_progress: bool = False
    indexing_in_progress: bool = False
    embeddings_ready: bool = False
    face_clusters_ready: bool = False

    warnings: List[str] = field(default_factory=list)
    empty_state_reason: Optional[str] = None

    recent_queries: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    discover_counts: Dict[str, int] = field(default_factory=dict)
    discover_previews: Dict[str, list] = field(default_factory=dict)
    people_quick_items: List[Dict[str, Any]] = field(default_factory=list)
    people_quick_loading: bool = False
    people_quick_payload: Dict[str, Any] = field(default_factory=dict)
    merge_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    merge_review_payload: Dict[str, Any] = field(default_factory=dict)
    unnamed_review_payload: Dict[str, Any] = field(default_factory=dict)
    selected_result_ids: List[str] = field(default_factory=list)
    merge_review_payloads: List[Dict[str, Any]] = field(default_factory=list)
    unnamed_cluster_payloads: List[Dict[str, Any]] = field(default_factory=list)
    unnamed_cluster_items: List[Dict[str, Any]] = field(default_factory=list)
    browse_mode: Optional[str] = None
    activity_snapshot: Dict[str, Any] = field(default_factory=dict)
    model_warning: str = ""
    last_interaction_ts: float = 0.0
    last_action: str = ""
    is_user_typing: bool = False


class SearchStateStore(QObject):
    stateChanged = Signal(object)

    def __init__(self):
        super().__init__()
        self._state = SearchState()

    def get_state(self) -> SearchState:
        return self._state

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self._state, key):
                setattr(self._state, key, value)
        self.stateChanged.emit(self._state)

    def reset_for_project(self, project_id: Optional[int]):
        self._state = SearchState(
            active_project_id=project_id,
            has_active_project=project_id is not None,
            onboarding_mode=project_id is None,
            empty_state_reason="no_project" if project_id is None else None,
        )
        self.stateChanged.emit(self._state)

    def clear_search(self):
        self._state.query_text = ""
        self._state.preset_id = None
        self._state.family = None
        self._state.intent_summary = ""
        self._state.active_people.clear()
        self._state.active_filters.clear()
        self._state.active_chips.clear()
        self._state.result_paths.clear()
        self._state.result_count = 0
        self._state.discover_previews.clear()
        self._state.result_facets.clear()
        self._state.search_in_progress = False
        self._state.people_quick_loading = False
        self._state.browse_mode = None
        self._state.empty_state_reason = None if self._state.has_active_project else "no_project"
        self._state.suggestions.clear()
        self._state.model_warning = ""
        self._state.selected_result_ids.clear()
        self.stateChanged.emit(self._state)
