import logging
import time
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

    def _mark_interaction(self, action: str):
        """UX-11: record interaction timestamp for debounce and stability checks."""
        self.store.update(last_interaction_ts=time.time(), last_action=action)

    def set_active_project(self, project_id: Optional[int]):
        """UX-10: Sync with project changes using transition guard."""
        self.store.begin_project_transition()
        self.store.complete_project_transition(project_id)
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
        self._mark_interaction("query")
        state = self.store.get_state()
        if state.query_text == text:
            return

        self.store.update(query_text=text)
        self.generate_suggestions(text)

        if kwargs.get("debounce", False):
            self._debounce_timer.start()

    def submit_query(self, text: str):
        """User explicitly submitted a query (Enter or click)."""
        self._mark_interaction("submit")
        self._debounce_timer.stop()
        self.store.update(query_text=text)
        self._add_to_history(text)
        self._update_chips_from_filters()
        self._do_search()

    def set_preset(self, preset_id: str):
        self._mark_interaction("preset")
        state = self.store.get_state()

        # Preset selection exits explicit browse navigation mode
        browse_mode = None

        chips = [
            chip for chip in state.active_chips
            if chip.get("kind") not in {"preset", "browse"}
        ]
        chips.insert(0, {
            "kind": "preset",
            "label": preset_id.replace("_", " ").title(),
            "value": preset_id,
        })

        self.store.update(
            preset_id=preset_id,
            browse_mode=browse_mode,
            active_chips=chips,
            search_mode="hybrid",
            family=self._infer_family(),
            visible_facet_keys=self._compute_visible_facet_keys(),
            browse_scope_label="",
            intent_summary=preset_id.replace("_", " ").title(),
            search_in_progress=True,
        )
        self.run_search()

    def apply_filter(self, filter_key: str, value):
        """UX-9D: User clicked a facet in FilterSection."""
        self._mark_interaction("filter")
        state = self.store.get_state()
        new_filters = dict(state.active_filters or {})
        new_filters[filter_key] = value

        chips = []
        for chip in state.active_chips:
            if chip.get("kind") == "filter" and chip.get("filter_key") == filter_key:
                continue
            chips.append(chip)

        chips.append({
            "kind": "filter",
            "filter_key": filter_key,
            "label": f"{filter_key}: {value}",
            "value": value,
        })

        self.store.update(
            active_filters=new_filters,
            active_chips=chips,
            family=self._infer_family(),
            visible_facet_keys=self._compute_visible_facet_keys(),
            intent_summary=self._build_intent_summary(),
        )
        self.run_search()

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

    def set_merge_review_payloads(self, payloads):
        self.store.update(merge_review_payloads=list(payloads or []))

    def set_unnamed_cluster_payloads(self, payloads):
        self.store.update(unnamed_cluster_payloads=list(payloads or []))

    def set_unnamed_cluster_items(self, items):
        self.store.update(unnamed_cluster_items=list(items or []))

    def set_unnamed_clusters(self, items):
        self.store.update(unnamed_clusters=list(items or []))

    def set_named_identity_choices(self, items):
        self.store.update(named_identity_choices=list(items or []))

    def set_active_merge_review_pair(self, payload: dict):
        self.store.update(active_merge_review_pair=dict(payload or {}))

    def set_selected_result_ids(self, ids_):
        self.store.update(selected_result_ids=list(ids_ or []))

    def refresh_status(self):
        """UX-10F: refresh derived state without re-running search."""
        self.store.update(
            family=self._infer_family(),
            intent_summary=self._build_intent_summary(),
        )

    def begin_layout_reload(self):
        """UX-10: mark layout reload in progress."""
        self.store.update(layout_reload_pending=True, result_surface_busy=True)

    def complete_layout_reload(self):
        """UX-10: mark layout reload complete."""
        self.store.update(layout_reload_pending=False, result_surface_busy=False)

    def apply_browse_mode(self, browse_key: str, value):
        self._mark_interaction("browse")
        state = self.store.get_state()

        new_filters = dict(state.active_filters or {})
        chips = [chip for chip in state.active_chips if chip.get("kind") not in {"browse", "preset"}]

        preset_id = None
        browse_scope_label = browse_key.replace("_", " ").title()

        # Reset browse-related filters first
        new_filters.pop("favorites_only", None)
        new_filters.pop("media_type", None)
        new_filters.pop("with_location", None)

        if browse_key == "all_photos":
            browse_scope_label = "All Photos"

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
                "label": browse_scope_label,
                "value": browse_key,
            })

        self.store.update(
            browse_mode=browse_key,
            browse_scope_label=browse_scope_label,
            preset_id=preset_id,
            active_filters=new_filters,
            active_chips=chips,
            search_mode="browse",
            family=self._infer_family(),
            visible_facet_keys=self._compute_visible_facet_keys(),
            intent_summary=browse_scope_label,
        )
        self.run_search()

    def set_activity_snapshot(self, activity: dict):
        self.store.update(activity_snapshot=dict(activity or {}))

    def apply_sort(self, sort_mode: str):
        """User changed the sort order in the results header."""
        self.store.update(sort_mode=sort_mode)
        self._do_search()

    def remove_chip(self, kind: str, value: Any):
        """UX-9D: User removed a chip from the ActiveChipsBar."""
        state = self.store.get_state()

        if kind == "preset":
            state.preset_id = None

        elif kind == "person":
            state.active_people = [p for p in state.active_people if p != value]

        elif kind == "filter":
            remove_key = None
            for chip in state.active_chips:
                if chip.get("kind") == "filter" and chip.get("value") == value:
                    remove_key = chip.get("filter_key")
                    break
            if remove_key:
                state.active_filters.pop(remove_key, None)

        elif kind == "query":
            state.query_text = ""

        elif kind == "browse":
            state.browse_mode = None
            state.browse_scope_label = ""
            if value == "favorites":
                state.active_filters.pop("favorites_only", None)
            elif value == "videos":
                state.active_filters.pop("media_type", None)
            elif value == "with_location":
                state.active_filters.pop("with_location", None)

        state.active_chips = [
            chip for chip in state.active_chips
            if not (chip.get("kind") == kind and chip.get("value") == value)
        ]

        state.family = self._infer_family()
        state.visible_facet_keys = self._compute_visible_facet_keys()
        state.intent_summary = self._build_intent_summary()

        self.store.stateChanged.emit(state)
        self.run_search()

    def clear_search(self):
        """Reset search state to 'All Photos'."""
        self.store.clear_search()
        self._do_search()

    def clear_recent_queries(self):
        """Clear search history."""
        self.store.update(recent_queries=[])

    def clear_filters(self):
        """UX-9D: Clear only the active facets, keep other chips."""
        state = self.store.get_state()
        chips = [chip for chip in state.active_chips if chip.get("kind") != "filter"]

        self.store.update(
            active_filters={},
            active_chips=chips,
            family=self._infer_family(),
            visible_facet_keys=self._compute_visible_facet_keys(),
            intent_summary=self._build_intent_summary(),
        )
        self.run_search()

    def apply_result_summary(
        self,
        result_paths=None,
        result_count: int = 0,
        result_facets=None,
        family: Optional[str] = None,
        warnings=None,
    ):
        """UX-9D: Apply result summary with family-aware facet keys and explanation."""
        state = self.store.get_state()
        warning_list = list(warnings or [])
        model_warning = ""

        joined = " ".join(str(w) for w in warning_list).lower()
        if "clip-vit-large-patch14" in joined or "better model available" in joined:
            model_warning = "Better model available"

        discover_counts = dict(state.discover_counts or {})
        discover_previews = dict(state.discover_previews or {})
        new_paths = list(result_paths or [])
        effective_family = family or self._infer_family()

        if state.preset_id:
            discover_counts[state.preset_id] = result_count

            preview_labels = []
            for path in new_paths[:3]:
                try:
                    import os
                    preview_labels.append(os.path.basename(path))
                except Exception:
                    pass
            discover_previews[state.preset_id] = preview_labels

        explanation_parts = []
        if state.browse_scope_label:
            explanation_parts.append(state.browse_scope_label)
        if state.preset_id:
            explanation_parts.append(state.preset_id.replace("_", " ").title())
        if state.query_text.strip():
            explanation_parts.append(f'query "{state.query_text.strip()}"')
        if state.active_people:
            explanation_parts.append(f"{len(state.active_people)} people filter(s)")
        if state.active_filters:
            explanation_parts.append(f"{len(state.active_filters)} active filter(s)")

        result_explanation = ""
        if explanation_parts:
            result_explanation = "Results based on " + ", ".join(dict.fromkeys(explanation_parts))

        self.store.update(
            result_paths=new_paths,
            displayed_result_paths=new_paths,
            last_nonempty_result_paths=new_paths if new_paths else list(getattr(state, 'last_nonempty_result_paths', None) or []),
            result_count=result_count,
            result_facets=result_facets or {},
            family=effective_family,
            visible_facet_keys=self._compute_visible_facet_keys(),
            warnings=warning_list,
            model_warning=model_warning,
            discover_counts=discover_counts,
            discover_previews=discover_previews,
            search_in_progress=False,
            empty_state_reason=None if result_count > 0 else "no_results",
            intent_summary=self._build_intent_summary(),
            result_explanation=result_explanation,
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

        # UX-10: block search while project state is unresolved
        if not getattr(state, "active_project_id_resolved", True):
            self.store.update(
                search_in_progress=False,
                warnings=["Project switch still resolving"],
            )
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

    def _normalize_result_facets(self, facets: dict) -> dict:
        """UX-9A/9D: normalize all facet types — filter dead items, sort by count, cap to 12."""
        facets = dict(facets or {})
        for key in ("people", "locations", "years", "types", "location", "year", "type"):
            items = list(facets.get(key, []) or [])
            normalized = []
            for item in items:
                if isinstance(item, dict):
                    if int(item.get("count", 0)) <= 0:
                        continue
                    normalized.append(item)
                else:
                    normalized.append(item)
            normalized.sort(
                key=lambda x: x.get("count", 0) if isinstance(x, dict) else 0,
                reverse=True,
            )
            facets[key] = normalized[:12]
        return facets

    def _build_intent_summary(self) -> str:
        """UX-9D: Build intent summary with browse/search coexistence."""
        state = self.store.get_state()
        parts = []

        if state.browse_scope_label:
            parts.append(state.browse_scope_label)

        if state.preset_id:
            parts.append(state.preset_id.replace("_", " ").title())

        if state.query_text.strip():
            parts.append(state.query_text.strip())

        for person in state.active_people:
            parts.append(person)

        return " + ".join(dict.fromkeys(parts)) if parts else "All Photos"

    def _add_to_history(self, text: str):
        if not text or len(text) < 2: return
        state = self.store.get_state()
        history = list(state.recent_queries)
        if text in history: history.remove(text)
        history.insert(0, text)
        self.store.update(recent_queries=history[:10])

    def _infer_family(self) -> str:
        """UX-9D: Infer the current search family from state."""
        state = self.store.get_state()

        if state.preset_id in {"documents", "screenshots"}:
            return "type"

        if state.active_people:
            return "people"

        if state.preset_id in {"beach", "mountains", "city", "forest"}:
            return "scenic"

        if state.browse_mode in {"videos"}:
            return "utility"

        return state.family or "hybrid"

    def _compute_visible_facet_keys(self) -> list:
        """UX-9D: context-aware facet ordering based on browse mode and family."""
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
