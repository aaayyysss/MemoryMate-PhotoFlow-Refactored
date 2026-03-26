import logging
from typing import Optional, List, Dict, Any

from PySide6.QtCore import QObject, Signal, QTimer
from ui.search.search_state_store import SearchState, SearchStateStore

logger = logging.getLogger(__name__)


class SearchController(QObject):
    """
    UX-1 Search Controller.
    Centralizes search logic and state management.
    """

    searchRequested = Signal(dict)  # payload: {query_text, preset_id, filters, ...}

    def __init__(self, store: SearchStateStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(400)
        self._debounce_timer.timeout.connect(self._do_search)

    def set_active_project(self, project_id: Optional[int]):
        """Sync with project changes from MainWindow."""
        self.store.reset_for_project(project_id)
        if project_id:
            # Load discovery counts (placeholder for now)
            self.store.update(discover_counts={
                "beach": 12, "mountains": 5, "city": 24,
                "forest": 8, "documents": 15, "screenshots": 42
            })
            # Generate initial suggestions
            self.generate_suggestions("")

    def set_query_text(self, text: str, **kwargs):
        """Update query text, optionally triggering a debounced search."""
        state = self.store.get_state()
        if state.query_text == text:
            return

        self.store.update(query_text=text)
        self.generate_suggestions(text)

        if kwargs.get("debounce", False):
            self._debounce_timer.start()

    def submit_query(self, text: str):
        """User explicitly submitted a query (Enter or click)."""
        self._debounce_timer.stop()
        self.store.update(query_text=text)
        self._add_to_history(text)
        self._update_chips_from_filters()
        self._do_search()

    def set_preset(self, preset_id: str):
        """User clicked a Discovery preset."""
        state = self.store.get_state()
        if state.preset_id == preset_id:
            # Toggle off if already active
            self.store.update(preset_id=None, intent_summary="")
        else:
            self.store.update(preset_id=preset_id, query_text="", intent_summary=f"Showing {preset_id}")

        self._update_chips_from_filters()
        self._do_search()

    def apply_filter(self, kind: str, value: str):
        """User clicked a facet in FilterSection."""
        state = self.store.get_state()
        filters = dict(state.active_filters)

        if filters.get(kind) == value:
            del filters[kind]
        else:
            filters[kind] = value

        self.store.update(active_filters=filters)
        self._update_chips_from_filters()
        self._do_search()

    def remove_chip(self, kind: str, value: Any):
        """User removed a chip from the ActiveChipsBar."""
        state = self.store.get_state()

        if kind == "query":
            self.store.update(query_text="")
        elif kind == "preset":
            self.store.update(preset_id=None)
        else:
            filters = dict(state.active_filters)
            if kind in filters:
                del filters[kind]
            self.store.update(active_filters=filters)
            self._update_chips_from_filters()

        self._do_search()

    def clear_search(self):
        """Reset search state to 'All Photos'."""
        self.store.clear_search()
        self._do_search()

    def clear_recent_queries(self):
        """Clear search history."""
        self.store.update(recent_queries=[])

    def clear_filters(self):
        """Clear only the active facets."""
        self.store.update(active_filters={}, active_chips=[])
        self._update_chips_from_filters()
        self._do_search()

    def apply_result_summary(self, **kwargs):
        """Update state with search results from backend."""
        self.store.update(
            result_paths=kwargs.get("result_paths", []),
            result_count=kwargs.get("result_count", 0),
            result_facets=kwargs.get("result_facets", {}),
            search_in_progress=False,
            warnings=kwargs.get("warnings", []),
        )

    def generate_suggestions(self, text: str):
        """Generate dummy suggestions based on text."""
        if not text:
            self.store.update(suggestions=["Recent photos", "Last month", "Nature"])
            return

        t = text.lower()
        if "b" in t: self.store.update(suggestions=["Beach", "Blue water", "Birthday"])
        elif "m" in t: self.store.update(suggestions=["Mountains", "Morning", "Mexico"])
        else: self.store.update(suggestions=[f"{text} 1", f"{text} 2"])

    def _do_search(self):
        """Package state into a payload and emit searchRequested."""
        state = self.store.get_state()
        if not state.has_active_project:
            return

        self.store.update(search_in_progress=True)

        payload = {
            "query_text": state.query_text,
            "preset_id": state.preset_id,
            "filters": state.active_filters,
        }
        self.searchRequested.emit(payload)

    def _add_to_history(self, text: str):
        if not text or len(text) < 2: return
        state = self.store.get_state()
        history = list(state.recent_queries)
        if text in history: history.remove(text)
        history.insert(0, text)
        self.store.update(recent_queries=history[:10])

    def _update_chips_from_filters(self):
        state = self.store.get_state()
        chips = []

        # Free text query chip
        if state.query_text:
            chips.append({"kind": "query", "label": state.query_text, "value": state.query_text})

        # Preset chip
        if state.preset_id:
            chips.append({"kind": "preset", "label": state.preset_id.capitalize(), "value": state.preset_id})

        # Facet chips
        for kind, val in state.active_filters.items():
            chips.append({"kind": kind, "label": f"{kind.capitalize()}: {val}", "value": val})

        self.store.update(active_chips=chips)
