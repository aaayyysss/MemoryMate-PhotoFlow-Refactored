from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from PySide6.QtCore import QObject, Signal

@dataclass
class SearchState:
    # Project context
    active_project_id: Optional[int] = None
    has_active_project: bool = False
    onboarding_mode: bool = False

    # Query / intent
    query_text: str = ""
    preset_id: Optional[str] = None
    family: Optional[str] = None
    intent_summary: str = ""

    # Active refinement
    active_people: List[str] = field(default_factory=list)
    active_filters: Dict[str, Any] = field(default_factory=dict)
    active_chips: List[Dict[str, Any]] = field(default_factory=list)

    # Result state
    result_paths: List[str] = field(default_factory=list)
    result_count: int = 0
    result_facets: Dict[str, Any] = field(default_factory=dict)

    # Sort / mode
    sort_mode: str = "relevance"
    media_scope: str = "all"   # all | photos | videos
    search_mode: str = "hybrid"  # hybrid | browse | people | discover

    # Runtime status
    search_in_progress: bool = False
    indexing_in_progress: bool = False
    embeddings_ready: bool = False
    face_clusters_ready: bool = False

    # UX messaging
    warnings: List[str] = field(default_factory=list)
    empty_state_reason: Optional[str] = None  # no_project | no_results | indexing | embeddings_missing

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
        self._state.result_facets.clear()
        self._state.empty_state_reason = None
        self.stateChanged.emit(self._state)
