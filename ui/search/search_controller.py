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
        state = self.store.get_state()

        chips = [chip for chip in state.active_chips if chip.get("kind") != "preset"]
        chips.insert(0, {
            "kind": "preset",
            "label": preset_id.replace("_", " ").title(),
            "value": preset_id,
        })

        self.store.update(
            preset_id=preset_id,
            active_chips=chips,
            search_mode="hybrid",
            intent_summary=preset_id.replace("_", " ").title(),
            search_in_progress=True,
        )
        self.run_search()

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

    def apply_people_filter(self, person_id: str):
        state = self.store.get_state()

        active_people = [p for p in state.active_people if p != person_id]
        if person_id not in state.active_people:
            active_people.append(person_id)

        chips = [chip for chip in state.active_chips if not (chip.get("kind") == "person" and chip.get("value") == person_id)]

        if person_id in active_people:
            chips.append({
                "kind": "person",
                "label": person_id,
                "value": person_id,
            })

        self.store.update(
            active_people=active_people,
            active_chips=chips,
            intent_summary=self._build_intent_summary(),
        )
        self.run_search()

    def set_people_quick_items(self, items):
        self.store.update(people_quick_items=list(items or []))

    def set_people_quick_loading(self, loading: bool):
        self.store.update(people_quick_loading=bool(loading))

    def set_people_quick_payload(self, payload: dict):
        self.store.update(people_quick_payload=dict(payload or {}))

    def set_merge_suggestions(self, suggestions):
        self.store.update(merge_suggestions=list(suggestions or []))

    def set_merge_review_payload(self, payload: dict):
        self.store.update(merge_review_payload=dict(payload or {}))

    def set_unnamed_review_payload(self, payload: dict):
        self.store.update(unnamed_review_payload=dict(payload or {}))

    def apply_browse_mode(self, browse_key: str, value):
        state = self.store.get_state()

        new_filters = dict(state.active_filters or {})
        chips = [chip for chip in state.active_chips if chip.get("kind") not in {"browse", "preset"}]

        preset_id = None

        if browse_key == "all_photos":
            new_filters.pop("favorites_only", None)
            new_filters.pop("media_type", None)
            new_filters.pop("with_location", None)

        elif browse_key == "favorites":
            new_filters["favorites_only"] = True
            chips.append({
                "kind": "browse",
                "label": "Favorites",
                "value": "favorites",
            })

        elif browse_key == "videos":
            new_filters["media_type"] = "video"
            chips.append({
                "kind": "browse",
                "label": "Videos",
                "value": "videos",
            })

        elif browse_key == "with_location":
            new_filters["with_location"] = True
            chips.append({
                "kind": "browse",
                "label": "With Location",
                "value": "with_location",
            })

        elif browse_key in {"albums", "folders", "dates"}:
            chips.append({
                "kind": "browse",
                "label": browse_key.replace("_", " ").title(),
                "value": browse_key,
            })

        self.store.update(
            browse_mode=browse_key,
            preset_id=preset_id,
            active_filters=new_filters,
            active_chips=chips,
            search_mode="browse",
            intent_summary=browse_key.replace("_", " ").title(),
        )
        self.run_search()

    def set_activity_snapshot(self, activity: dict):
        self.store.update(activity_snapshot=dict(activity or {}))

    def apply_sort(self, sort_mode: str):
        """User changed the sort order in the results header."""
        self.store.update(sort_mode=sort_mode)
        self._do_search()

    def remove_chip(self, kind: str, value: Any):
        """User removed a chip from the ActiveChipsBar."""
        state = self.store.get_state()

        if kind == "query":
            self.store.update(query_text="")
        elif kind == "preset":
            self.store.update(preset_id=None)
        elif kind == "person":
            active_people = [p for p in state.active_people if p != value]
            self.store.update(active_people=active_people)
            self._update_chips_from_filters()
        elif kind == "browse":
            filters = dict(state.active_filters)
            if value == "favorites":
                filters.pop("favorites_only", None)
            elif value == "videos":
                filters.pop("media_type", None)
            elif value == "with_location":
                filters.pop("with_location", None)
            self.store.update(browse_mode=None, active_filters=filters)
            self._update_chips_from_filters()
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

    def apply_result_summary(
        self,
        result_paths=None,
        result_count: int = 0,
        result_facets=None,
        family: Optional[str] = None,
        warnings=None,
    ):
        state = self.store.get_state()
        warning_list = list(warnings or [])
        model_warning = ""

        joined = " ".join(str(w) for w in warning_list).lower()
        if "clip-vit-large-patch14" in joined or "better model available" in joined:
            model_warning = "Better model available"

        discover_counts = dict(state.discover_counts or {})
        discover_previews = dict(state.discover_previews or {})

        if state.preset_id:
            discover_counts[state.preset_id] = result_count

            preview_labels = []
            for path in list(result_paths or [])[:3]:
                try:
                    import os
                    preview_labels.append(os.path.basename(path))
                except Exception:
                    pass
            discover_previews[state.preset_id] = preview_labels

        self.store.update(
            result_paths=result_paths or [],
            result_count=result_count,
            result_facets=result_facets or {},
            family=family,
            warnings=warning_list,
            model_warning=model_warning,
            discover_counts=discover_counts,
            discover_previews=discover_previews,
            search_in_progress=False,
            empty_state_reason=None if result_count > 0 else "no_results",
            intent_summary=self._build_intent_summary(),
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

    def run_search(self):
        """Package state into a payload and emit searchRequested."""
        state = self.store.get_state()
        if not state.has_active_project:
            return

        self.store.update(search_in_progress=True)

        payload = {
            "query_text": state.query_text,
            "preset_id": state.preset_id,
            "filters": state.active_filters,
            "active_people": state.active_people,
            "sort_mode": state.sort_mode,
            "browse_mode": state.browse_mode,
            "search_mode": state.search_mode,
        }
        self.searchRequested.emit(payload)

    def _do_search(self):
        self.run_search()

    def _build_intent_summary(self) -> str:
        state = self.store.get_state()
        if state.preset_id:
            return state.preset_id.replace("_", " ").title()
        if state.query_text:
            return f'Results for "{state.query_text}"'
        if state.active_people:
            return f"Photos with {', '.join(state.active_people)}"
        if state.active_filters:
            return "Filtered Results"
        return "All Photos"

    def _add_to_history(self, text: str):
        if not text or len(text) < 2: return
        state = self.store.get_state()
        history = list(state.recent_queries)
        if text in history: history.remove(text)
        history.insert(0, text)
        self.store.update(recent_queries=history[:10])

    def _infer_family(self) -> str:
        """Infer the current search family from state."""
        state = self.store.get_state()
        if state.family:
            return state.family
        if state.active_people:
            return "people"
        query = (state.query_text or "").lower()
        if any(kw in query for kw in ("person", "face", "people", "who")):
            return "people"
        if any(kw in query for kw in ("document", "screenshot", "receipt")):
            return "type"
        if any(kw in query for kw in ("beach", "mountain", "sunset", "landscape", "nature", "forest", "ocean")):
            return "scenic"
        return ""

    def _compute_visible_facet_keys(self) -> list:
        """UX-9D: context-aware facet ordering for stronger people-first emphasis."""
        state = self.store.get_state()
        family = self._infer_family()

        if state.browse_mode == "favorites":
            return ["year", "location", "type"]
        if state.browse_mode == "videos":
            return ["year", "location"]
        if state.browse_mode == "with_location":
            return ["location", "year", "type"]

        if family == "people":
            return ["people", "year", "location", "type"]
        if family == "type":
            return ["type", "year", "location"]
        if family == "scenic":
            return ["location", "year", "type"]

        return ["people", "location", "year", "type"]

    def _update_chips_from_filters(self):
        state = self.store.get_state()
        chips = []

        # Free text query chip
        if state.query_text:
            chips.append({"kind": "query", "label": state.query_text, "value": state.query_text})

        # Preset chip
        if state.preset_id:
            chips.append({"kind": "preset", "label": state.preset_id.capitalize(), "value": state.preset_id})

        # Person chips
        for pid in state.active_people:
            chips.append({"kind": "person", "label": pid, "value": pid})

        # Facet chips
        for kind, val in state.active_filters.items():
            chips.append({"kind": kind, "label": f"{kind.capitalize()}: {val}", "value": val})

        self.store.update(active_chips=chips)
