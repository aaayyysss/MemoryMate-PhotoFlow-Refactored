import logging
from typing import Optional, Dict, Any, List
from PySide6.QtCore import QObject, QTimer, Signal
from ui.search.search_state_store import SearchStateStore
from services.search_orchestrator import get_search_orchestrator

logger = logging.getLogger(__name__)

class SearchController(QObject):
    searchStarted = Signal()
    searchFinished = Signal(object) # OrchestratorResult

    def __init__(self, state_store: SearchStateStore):
        super().__init__()
        self.store = state_store
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self.run_search)

        # To handle cancellation/stale results
        self._current_search_id = 0

    def set_active_project(self, project_id: Optional[int]):
        logger.info(f"[SearchController] Setting active project: {project_id}")
        self.store.reset_for_project(project_id)
        if project_id:
            # Maybe trigger initial "All Photos" or default view
            self.run_search()

    def set_query_text(self, text: str, debounce: bool = True):
        state = self.store.get_state()
        if state.query_text == text:
            return

        self.store.update(query_text=text, preset_id=None) # Clear preset when typing

        if debounce:
            self._search_timer.start(300)
        else:
            self.run_search()

    def set_preset(self, preset_id: str):
        logger.info(f"[SearchController] Setting preset: {preset_id}")
        self.store.update(preset_id=preset_id, query_text="") # Clear text when choosing preset
        self.run_search()

    def apply_people_filter(self, person_id: str):
        state = self.store.get_state()
        people = list(state.active_people)
        if person_id in people:
            people.remove(person_id)
        else:
            people.append(person_id)

        self.store.update(active_people=people)
        self.run_search()

    def toggle_filter(self, key: str, value: Any):
        state = self.store.get_state()
        filters = dict(state.active_filters)

        if key in filters and filters[key] == value:
            del filters[key]
        else:
            filters[key] = value

        self.store.update(active_filters=filters)
        self.run_search()

    def remove_chip(self, kind: str, value: Any):
        state = self.store.get_state()
        if kind == "preset":
            self.store.update(preset_id=None)
        elif kind == "query":
            self.store.update(query_text="")
        elif kind == "person":
            people = [p for p in state.active_people if p != value]
            self.store.update(active_people=people)
        else:
            # Assume it's a generic filter
            filters = dict(state.active_filters)
            if kind in filters:
                del filters[kind]
            self.store.update(active_filters=filters)

        self.run_search()

    def apply_sort(self, mode: str):
        self.store.update(sort_mode=mode)
        self.run_search()

    def clear_search(self):
        self.store.clear_search()
        self.run_search()

    def refresh_results(self):
        self.run_search()

    def run_search(self):
        state = self.store.get_state()
        if not state.has_active_project:
            return

        self._current_search_id += 1
        search_id = self._current_search_id

        self.store.update(search_in_progress=True)
        self.searchStarted.emit()

        project_id = state.active_project_id
        orch = get_search_orchestrator(project_id)

        # Gather all constraints
        query = state.query_text
        preset = state.preset_id
        filters = dict(state.active_filters)

        # Add people to filters if present
        if state.active_people:
            filters["person_ids"] = state.active_people

        try:
            if preset:
                result = orch.search_by_preset(preset, extra_filters=filters)
            else:
                result = orch.search(query, extra_filters=filters)

            # Check if this search is still relevant
            if search_id != self._current_search_id:
                return

            # Update store with results
            new_chips = self._build_chips(state, result)

            # Map OrchestratorResult family
            family = result.family

            self.store.update(
                result_paths=result.paths,
                result_count=len(result.paths),
                result_facets=result.facets,
                active_chips=new_chips,
                family=family,
                intent_summary=result.label,
                search_in_progress=False,
                empty_state_reason="no_results" if not result.paths else None
            )

            self.searchFinished.emit(result)

        except Exception as e:
            logger.error(f"[SearchController] Search failed: {e}", exc_info=True)
            if search_id == self._current_search_id:
                self.store.update(search_in_progress=False)

    def _build_chips(self, state, result) -> List[Dict[str, Any]]:
        chips = []
        if state.preset_id:
            chips.append({"kind": "preset", "label": state.preset_id.title(), "value": state.preset_id})

        if state.query_text:
            chips.append({"kind": "query", "label": state.query_text, "value": state.query_text})

        for person_id in state.active_people:
            chips.append({"kind": "person", "label": person_id, "value": person_id})

        for key, val in state.active_filters.items():
            if key == "person_ids": continue
            chips.append({"kind": key, "label": f"{key}: {val}", "value": val})

        return chips
