# services/search_orchestrator.py
# Unified Search Orchestrator - One search pipeline, one mental model
#
# This is the "one system" that Google Photos, Apple Photos, Lightroom,
# and Excire all converge on: a single entry point that understands
# free text, structured tokens, semantic similarity, metadata filters,
# and produces ranked results with explainability.
#
# All search entry points (SmartFind presets, toolbar widget, free text)
# route through this orchestrator so ranking is always consistent.

"""
SearchOrchestrator - Unified search pipeline.

Architecture:
1. QueryParser: Parse user input into a QueryPlan
   - Structured tokens (type:video, is:fav, has:location, date:2024, camera:iPhone)
   - Natural language tokens (dates, ratings via NLQueryParser)
   - Everything else becomes semantic text for CLIP

2. CandidateRetrieval: Get initial candidate sets
   - Semantic: multi-prompt CLIP search (via SmartFindService internals)
   - Metadata: SQL filter constraints

3. ScoringContract: Deterministic, explainable ranking
   - S = w_clip * clip_sim + w_recency * recency_boost + w_fav * is_favorite
       + w_face * face_match + w_loc * has_location + w_quality * aesthetic
   - All weights configurable, all components logged

4. FacetComputer: Compute result-set facets for chip display
   - Media type distribution, date buckets, people, locations
   - Only from current result set (not global)

5. ExplainabilityLogger: Top-10 score breakdown per query

Usage:
    from services.search_orchestrator import get_search_orchestrator

    orch = get_search_orchestrator(project_id=1)
    result = orch.search("wedding Munich 2023 screenshots")
    # result.facets -> {media: {photo: 5, video: 2}, years: {2023: 7}, ...}
    # result.explanations -> [{path, clip: 0.35, recency: 0.02, ...}, ...]
"""

import re
import time
import threading
import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from logging_config import get_logger

logger = get_logger(__name__)

# Optional FAISS import for ANN retrieval
try:
    import numpy as np
    _numpy_available = True
except ImportError:
    _numpy_available = False

try:
    import faiss as _faiss
    _faiss_available = True
except ImportError:
    _faiss_available = False


# ══════════════════════════════════════════════════════════════════════
# Query Plan - structured representation of parsed user intent
# ══════════════════════════════════════════════════════════════════════

@dataclass
class QueryPlan:
    """Structured representation of a parsed search query."""
    # Raw input
    raw_query: str = ""

    # Semantic text for CLIP (after token extraction)
    semantic_text: str = ""

    # Multi-prompt list (from presets or expanded synonyms)
    semantic_prompts: List[str] = field(default_factory=list)

    # Extracted structured filters
    filters: Dict[str, Any] = field(default_factory=dict)

    # Source: "text", "preset", "combined"
    source: str = "text"

    # Preset ID if from a preset
    preset_id: Optional[str] = None

    # Weights override (per-preset or default)
    semantic_weight: float = 0.8

    # Tokens that were extracted (for chip display)
    extracted_tokens: List[Dict[str, str]] = field(default_factory=list)

    def has_semantic(self) -> bool:
        return bool(self.semantic_text) or bool(self.semantic_prompts)

    def has_filters(self) -> bool:
        return bool(self.filters)


# ══════════════════════════════════════════════════════════════════════
# Scored Result - single result with full score breakdown
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ScoredResult:
    """A single search result with full score decomposition."""
    path: str
    final_score: float = 0.0
    # Score components (all in [0, 1])
    clip_score: float = 0.0
    recency_score: float = 0.0
    favorite_score: float = 0.0
    location_score: float = 0.0
    face_match_score: float = 0.0
    # Explanation
    matched_prompt: str = ""
    reasons: List[str] = field(default_factory=list)
    # Duplicate stacking: >0 means this is a stack representative
    duplicate_count: int = 0


# ══════════════════════════════════════════════════════════════════════
# Search Result - full orchestrator output
# ══════════════════════════════════════════════════════════════════════

@dataclass
class OrchestratorResult:
    """Complete search result with facets and explanations."""
    # Ranked paths
    paths: List[str] = field(default_factory=list)
    total_matches: int = 0

    # Full scored results (for explainability)
    scored_results: List[ScoredResult] = field(default_factory=list)

    # Score lookup
    scores: Dict[str, float] = field(default_factory=dict)

    # Facets computed from result set
    facets: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Query plan used
    query_plan: Optional[QueryPlan] = None

    # Performance
    execution_time_ms: float = 0.0
    label: str = ""

    # Backoff
    backoff_applied: bool = False

    # Progressive search phase: "metadata" (fast) or "full" (complete)
    phase: str = "full"

    # Phase label for UI transparency (e.g. "Metadata results", "Semantic refined")
    phase_label: str = ""

    # Duplicate stacking stats
    stacked_duplicates: int = 0  # how many results were folded into stacks


# ══════════════════════════════════════════════════════════════════════
# Scoring Weights - the deterministic contract
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ScoringWeights:
    """
    Deterministic scoring contract.

    S = w_clip * clip + w_recency * recency + w_fav * favorite
      + w_location * location + w_face * face_match

    All weights are explicit, testable, and logged.
    """
    w_clip: float = 0.75        # Semantic similarity (dominant signal)
    w_recency: float = 0.05     # Recency decay (recent photos slightly preferred)
    w_favorite: float = 0.08    # Favorited/rated photos boosted
    w_location: float = 0.04    # Photos with GPS data boosted
    w_face_match: float = 0.08  # Face match when person filter active

    # Guardrails
    max_recency_boost: float = 0.10   # Recency can't swamp relevance
    max_favorite_boost: float = 0.15  # Favorites can't float irrelevant items
    recency_halflife_days: int = 90   # How fast recency decays (half-life in days)

    # Canonical mapping: weight attr -> ScoredResult component attr.
    # Used by validate() to enforce that every weight has a matching
    # component and vice-versa.
    _WEIGHT_TO_COMPONENT = {
        "w_clip": "clip_score",
        "w_recency": "recency_score",
        "w_favorite": "favorite_score",
        "w_location": "location_score",
        "w_face_match": "face_match_score",
    }

    def validate(self):
        """Ensure weights sum to ~1.0, are reasonable, and match components."""
        # Structural check: every weight must have a ScoredResult field
        for w_attr, c_attr in self._WEIGHT_TO_COMPONENT.items():
            assert hasattr(self, w_attr), f"Missing weight: {w_attr}"
            assert hasattr(ScoredResult, c_attr), (
                f"Weight '{w_attr}' has no matching ScoredResult component '{c_attr}'"
            )

        total = self.w_clip + self.w_recency + self.w_favorite + self.w_location + self.w_face_match
        if abs(total - 1.0) > 0.01:
            logger.warning(
                f"[ScoringWeights] Weights sum to {total:.3f}, not 1.0. "
                f"Normalizing."
            )
            if total > 0:
                self.w_clip /= total
                self.w_recency /= total
                self.w_favorite /= total
                self.w_location /= total
                self.w_face_match /= total


# ══════════════════════════════════════════════════════════════════════
# Token Parser - structured token extraction
# ══════════════════════════════════════════════════════════════════════

class TokenParser:
    """
    Parse structured tokens from search queries.

    Supports:
        type:video, type:photo, type:screenshot
        is:fav, is:favorite, is:starred
        has:location, has:gps, has:faces
        date:2024, date:2024-06, date:last_month, date:this_year
        camera:iPhone, camera:Canon
        ext:heic, ext:jpg, ext:png
        rating:4, rating:5
        person:face_001 (for face-filtered search)

    Everything else is passed to CLIP as semantic text.
    """

    # Token patterns: key:value (no spaces in value)
    _TOKEN_PATTERN = re.compile(
        r'\b(type|is|has|date|camera|ext|rating|person|in|from)'
        r':(\S+)',
        re.IGNORECASE
    )

    # Also handle natural language via NLQueryParser
    _NL_PARSER = None

    @classmethod
    def _get_nl_parser(cls):
        if cls._NL_PARSER is None:
            from services.smart_find_service import NLQueryParser
            cls._NL_PARSER = NLQueryParser
        return cls._NL_PARSER

    @classmethod
    def parse(cls, raw_query: str) -> QueryPlan:
        """
        Parse a raw query string into a QueryPlan.

        Examples:
            "beach type:photo date:2024" ->
                semantic_text="beach", filters={media_type: photo, date_from: 2024-01-01}
            "wedding Munich is:fav" ->
                semantic_text="wedding Munich", filters={rating_min: 4}
            "sunset" ->
                semantic_text="sunset", filters={}
        """
        plan = QueryPlan(raw_query=raw_query, source="text")
        remaining = raw_query.strip()
        filters = {}
        tokens = []

        # Extract structured tokens
        for match in cls._TOKEN_PATTERN.finditer(remaining):
            key = match.group(1).lower()
            value = match.group(2).strip()
            token_info = cls._process_token(key, value, filters)
            if token_info:
                tokens.append(token_info)

        # Remove extracted tokens from remaining text
        remaining = cls._TOKEN_PATTERN.sub('', remaining).strip()
        remaining = re.sub(r'\s+', ' ', remaining).strip()

        # Run NL parser on remaining text for date/rating/media extraction
        nl_parser = cls._get_nl_parser()
        nl_remaining, nl_filters = nl_parser.parse(remaining)

        # Merge NL filters (structured tokens take priority)
        for k, v in nl_filters.items():
            if k not in filters:
                filters[k] = v
                if k == "date_from":
                    tokens.append({"type": "date", "label": f"Date: {v}", "key": k, "value": v})
                elif k == "rating_min":
                    tokens.append({"type": "rating", "label": f"Rating >= {v}", "key": k, "value": str(v)})
                elif k == "media_type":
                    tokens.append({"type": "type", "label": v.title(), "key": k, "value": v})

        # Resolve relative dates
        if "_relative_date" in filters:
            rel = filters.pop("_relative_date")
            date_filters = cls._resolve_relative_date(rel)
            filters.update(date_filters)
            tokens.append({"type": "date", "label": rel.replace('_', ' ').title(), "key": "date", "value": rel})

        plan.semantic_text = nl_remaining
        plan.semantic_prompts = [nl_remaining] if nl_remaining else []
        plan.filters = filters
        plan.extracted_tokens = tokens

        return plan

    @classmethod
    def _process_token(cls, key: str, value: str, filters: Dict) -> Optional[Dict]:
        """Process a single structured token."""
        value_lower = value.lower()

        if key == "type":
            if value_lower in ("video", "videos"):
                filters["media_type"] = "video"
                return {"type": "type", "label": "Videos", "key": "media_type", "value": "video"}
            elif value_lower in ("photo", "photos", "image", "images"):
                filters["media_type"] = "photo"
                return {"type": "type", "label": "Photos", "key": "media_type", "value": "photo"}
            elif value_lower in ("screenshot", "screenshots"):
                filters["media_type"] = "photo"
                filters["_is_screenshot"] = True
                return {"type": "type", "label": "Screenshots", "key": "media_type", "value": "screenshot"}

        elif key == "is":
            if value_lower in ("fav", "favorite", "favourite", "starred"):
                filters["rating_min"] = 4
                return {"type": "quality", "label": "Favorites", "key": "rating_min", "value": "4"}

        elif key == "has":
            if value_lower in ("location", "gps", "geo"):
                filters["has_gps"] = True
                return {"type": "meta", "label": "Has Location", "key": "has_gps", "value": "true"}
            elif value_lower in ("face", "faces", "people"):
                filters["has_faces"] = True
                return {"type": "meta", "label": "Has Faces", "key": "has_faces", "value": "true"}

        elif key in ("date", "in", "from"):
            return cls._process_date_token(value, filters)

        elif key == "ext":
            ext = value_lower if value_lower.startswith('.') else f".{value_lower}"
            filters["extension"] = ext
            return {"type": "ext", "label": f"Format: {ext}", "key": "extension", "value": ext}

        elif key == "rating":
            try:
                rating = int(value)
                if 1 <= rating <= 5:
                    filters["rating_min"] = rating
                    return {"type": "quality", "label": f"Rating >= {rating}", "key": "rating_min", "value": str(rating)}
            except ValueError:
                pass

        elif key == "person":
            filters["person_id"] = value
            return {"type": "person", "label": f"Person: {value}", "key": "person_id", "value": value}

        return None

    @classmethod
    def _process_date_token(cls, value: str, filters: Dict) -> Optional[Dict]:
        """Parse date token values."""
        value_lower = value.lower().replace('_', ' ')

        # Relative dates
        relative_map = {
            "today": "today", "yesterday": "yesterday",
            "this week": "this_week", "last week": "last_week",
            "thisweek": "this_week", "lastweek": "last_week",
            "this month": "this_month", "last month": "last_month",
            "thismonth": "this_month", "lastmonth": "last_month",
            "this year": "this_year", "last year": "last_year",
            "thisyear": "this_year", "lastyear": "last_year",
        }
        if value_lower in relative_map:
            filters["_relative_date"] = relative_map[value_lower]
            return None  # Will be processed after

        # Year: date:2024
        year_match = re.match(r'^(\d{4})$', value)
        if year_match:
            year = int(year_match.group(1))
            if 1990 <= year <= 2099:
                filters["date_from"] = f"{year}-01-01"
                filters["date_to"] = f"{year}-12-31"
                return {"type": "date", "label": str(year), "key": "date", "value": value}

        # Year-Month: date:2024-06
        ym_match = re.match(r'^(\d{4})-(\d{1,2})$', value)
        if ym_match:
            year = int(ym_match.group(1))
            month = int(ym_match.group(2))
            if 1990 <= year <= 2099 and 1 <= month <= 12:
                import calendar
                last_day = calendar.monthrange(year, month)[1]
                filters["date_from"] = f"{year}-{month:02d}-01"
                filters["date_to"] = f"{year}-{month:02d}-{last_day:02d}"
                return {"type": "date", "label": f"{year}-{month:02d}", "key": "date", "value": value}

        # Full date: date:2024-06-15
        date_match = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', value)
        if date_match:
            filters["date_from"] = value
            filters["date_to"] = value
            return {"type": "date", "label": value, "key": "date", "value": value}

        return None

    @classmethod
    def _resolve_relative_date(cls, relative: str) -> Dict:
        """Resolve relative date tokens to absolute date ranges."""
        today = datetime.now().date()
        filters = {}
        rel = relative.replace(' ', '_').lower()

        if rel == "today":
            filters["date_from"] = today.strftime("%Y-%m-%d")
            filters["date_to"] = today.strftime("%Y-%m-%d")
        elif rel == "yesterday":
            d = today - timedelta(days=1)
            filters["date_from"] = d.strftime("%Y-%m-%d")
            filters["date_to"] = d.strftime("%Y-%m-%d")
        elif rel == "this_week":
            start = today - timedelta(days=today.weekday())
            filters["date_from"] = start.strftime("%Y-%m-%d")
            filters["date_to"] = today.strftime("%Y-%m-%d")
        elif rel == "last_week":
            start = today - timedelta(days=today.weekday() + 7)
            end = start + timedelta(days=6)
            filters["date_from"] = start.strftime("%Y-%m-%d")
            filters["date_to"] = end.strftime("%Y-%m-%d")
        elif rel == "this_month":
            filters["date_from"] = today.replace(day=1).strftime("%Y-%m-%d")
            filters["date_to"] = today.strftime("%Y-%m-%d")
        elif rel == "last_month":
            first = today.replace(day=1)
            end = first - timedelta(days=1)
            start = end.replace(day=1)
            filters["date_from"] = start.strftime("%Y-%m-%d")
            filters["date_to"] = end.strftime("%Y-%m-%d")
        elif rel == "this_year":
            filters["date_from"] = f"{today.year}-01-01"
            filters["date_to"] = today.strftime("%Y-%m-%d")
        elif rel == "last_year":
            filters["date_from"] = f"{today.year - 1}-01-01"
            filters["date_to"] = f"{today.year - 1}-12-31"

        return filters


# ══════════════════════════════════════════════════════════════════════
# Facet Computer - compute chips from result set
# ══════════════════════════════════════════════════════════════════════

class FacetComputer:
    """
    Compute facets/chips from the current result set.

    Only shows what's actually present in results, not global.
    This is the Google Photos / Lightroom filter bar concept.
    """

    # Video extensions for media type detection
    _VIDEO_EXTS = frozenset({'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.webm', '.m4v', '.flv'})

    @classmethod
    def compute(cls, paths: List[str], project_meta: Dict[str, Dict]) -> Dict[str, Dict[str, int]]:
        """
        Compute facets from a result set.

        Returns:
            {
                "media": {"Photos": 15, "Videos": 3},
                "years": {"2024": 10, "2023": 5, "2025": 3},
                "has_location": {"Yes": 5, "No": 13},
                "rated": {"Rated": 4, "Unrated": 14},
            }
        """
        if not paths:
            return {}

        facets = {}

        # Media type
        media_counts = {"Photos": 0, "Videos": 0}
        for p in paths:
            ext = '.' + p.rsplit('.', 1)[-1].lower() if '.' in p else ''
            if ext in cls._VIDEO_EXTS:
                media_counts["Videos"] += 1
            else:
                media_counts["Photos"] += 1
        # Only include if there's a mix
        if media_counts["Videos"] > 0 and media_counts["Photos"] > 0:
            facets["media"] = media_counts
        elif media_counts["Videos"] > 0:
            facets["media"] = {"Videos": media_counts["Videos"]}

        # Year distribution
        year_counts = {}
        for p in paths:
            meta = project_meta.get(p, {})
            created = meta.get("created_date") or meta.get("date_taken", "")
            if created and len(str(created)) >= 4:
                year = str(created)[:4]
                if year.isdigit():
                    year_counts[year] = year_counts.get(year, 0) + 1
        if len(year_counts) > 1:
            # Sort descending
            facets["years"] = dict(sorted(year_counts.items(), reverse=True))

        # Location
        loc_yes = 0
        loc_no = 0
        for p in paths:
            meta = project_meta.get(p, {})
            if meta.get("has_gps"):
                loc_yes += 1
            else:
                loc_no += 1
        if loc_yes > 0 and loc_no > 0:
            facets["location"] = {"With Location": loc_yes, "No Location": loc_no}

        # Rating
        rated = 0
        unrated = 0
        for p in paths:
            meta = project_meta.get(p, {})
            rating = meta.get("rating", 0) or 0
            if rating >= 1:
                rated += 1
            else:
                unrated += 1
        if rated > 0 and unrated > 0:
            facets["rated"] = {"Rated": rated, "Unrated": unrated}

        return facets


# ══════════════════════════════════════════════════════════════════════
# Search Orchestrator - the unified pipeline
# ══════════════════════════════════════════════════════════════════════

class SearchOrchestrator:
    """
    Unified search pipeline.

    All search entry points route through here:
    - SmartFind presets
    - Toolbar semantic search widget
    - Free-text queries
    - Combined preset + text + filter queries

    Guarantees: same query always produces same ranking,
    regardless of entry point.
    """

    def __init__(self, project_id: int):
        self.project_id = project_id
        self._weights = ScoringWeights()
        self._weights.validate()
        self._smart_find_service = None  # Lazy
        self._project_meta_cache: Optional[Dict[str, Dict]] = None
        self._meta_cache_time: float = 0.0
        self._META_CACHE_TTL = 60.0  # Refresh metadata cache every 60s

    # ── Lazy Service Access ──

    @property
    def _smart_find(self):
        if self._smart_find_service is None:
            from services.smart_find_service import get_smart_find_service
            self._smart_find_service = get_smart_find_service(self.project_id)
        return self._smart_find_service

    # ── Public API ──

    def search(self, query: str, top_k: int = 200,
               extra_filters: Optional[Dict] = None) -> OrchestratorResult:
        """
        Unified search from free text.

        Handles: "wedding Munich 2023 screenshots is:fav type:photo"
        """
        start = time.time()
        plan = TokenParser.parse(query)
        if extra_filters:
            plan.filters.update(extra_filters)

        result = self._execute(plan, top_k)
        result.execution_time_ms = (time.time() - start) * 1000
        result.label = self._build_label(plan, result)

        self._log_explainability(plan, result)
        return result

    def search_by_preset(self, preset_id: str, top_k: int = 200,
                         extra_filters: Optional[Dict] = None) -> OrchestratorResult:
        """
        Search using a SmartFind preset. Routes through the same pipeline.
        """
        start = time.time()
        plan = self._plan_from_preset(preset_id, extra_filters)

        result = self._execute(plan, top_k)
        result.execution_time_ms = (time.time() - start) * 1000
        result.label = self._build_label(plan, result)

        self._log_explainability(plan, result)
        return result

    def search_combined(self, preset_ids: List[str],
                        text_query: Optional[str] = None,
                        extra_filters: Optional[Dict] = None,
                        top_k: int = 200) -> OrchestratorResult:
        """
        Combined search: multiple presets + text + filters.
        """
        start = time.time()
        plan = QueryPlan(raw_query=text_query or "", source="combined")

        for pid in preset_ids:
            preset = self._smart_find._lookup_preset(pid)
            if preset:
                plan.semantic_prompts.extend(preset.get("prompts", []))
                for k, v in preset.get("filters", {}).items():
                    plan.filters[k] = v

        if text_query:
            sub_plan = TokenParser.parse(text_query)
            if sub_plan.semantic_text:
                plan.semantic_prompts.append(sub_plan.semantic_text)
            plan.filters.update(sub_plan.filters)
            plan.extracted_tokens.extend(sub_plan.extracted_tokens)

        if extra_filters:
            plan.filters.update(extra_filters)

        result = self._execute(plan, top_k)
        result.execution_time_ms = (time.time() - start) * 1000
        result.label = self._build_label(plan, result)

        self._log_explainability(plan, result)
        return result

    # ── Internal Pipeline ──

    def _execute(self, plan: QueryPlan, top_k: int) -> OrchestratorResult:
        """Execute the full search pipeline from a QueryPlan."""
        cfg = self._smart_find._get_config()
        threshold = cfg["threshold"]
        fusion_mode = cfg["fusion_mode"]

        # Step 1: Semantic candidates
        semantic_hits = {}  # {photo_id: (score, prompt)}
        if plan.has_semantic() and self._smart_find.clip_available:
            prompts = plan.semantic_prompts if plan.semantic_prompts else [plan.semantic_text]
            semantic_hits = self._smart_find._run_clip_multi_prompt(
                prompts, top_k * 3, threshold, fusion_mode
            )

        # Step 2: Metadata filter candidates
        metadata_candidate_paths = None
        if plan.has_filters():
            metadata_paths = self._smart_find._run_metadata_filter(plan.filters)
            metadata_candidate_paths = set(metadata_paths)

        # Step 3: Resolve photo_id -> path
        path_lookup = {}
        if semantic_hits:
            try:
                from repository.base_repository import DatabaseConnection
                db = DatabaseConnection()
                photo_ids = list(semantic_hits.keys())
                placeholders = ','.join(['?'] * len(photo_ids))
                with db.get_connection() as conn:
                    cursor = conn.execute(
                        f"SELECT id, path FROM photo_metadata WHERE id IN ({placeholders})",
                        photo_ids
                    )
                    for row in cursor.fetchall():
                        path_lookup[row['id']] = row['path']
            except Exception as e:
                logger.error(f"[SearchOrchestrator] Path resolution failed: {e}")

        # Step 4: Load project metadata for scoring
        project_meta = self._get_project_meta()

        # Step 5: Score every candidate
        scored: List[ScoredResult] = []

        if semantic_hits:
            for photo_id, (sem_score, matched_prompt) in semantic_hits.items():
                path = path_lookup.get(photo_id)
                if not path:
                    continue
                if metadata_candidate_paths is not None and path not in metadata_candidate_paths:
                    continue

                sr = self._score_result(path, sem_score, matched_prompt, project_meta, plan.filters)
                scored.append(sr)

        elif metadata_candidate_paths is not None:
            for path in metadata_candidate_paths:
                sr = self._score_result(path, 0.0, "", project_meta, plan.filters)
                scored.append(sr)

        # Step 6: Sort by final_score
        scored.sort(key=lambda r: r.final_score, reverse=True)

        # Step 7: Backoff if empty and semantic was used
        backoff_applied = False
        if not scored and plan.has_semantic() and self._smart_find.clip_available:
            backoff_step = cfg.get("backoff_step", 0.04)
            max_retries = cfg.get("backoff_retries", 2)
            prompts = plan.semantic_prompts if plan.semantic_prompts else [plan.semantic_text]

            for retry in range(1, max_retries + 1):
                lowered = max(0.05, threshold - (backoff_step * retry))
                logger.info(f"[SearchOrchestrator] Backoff retry {retry}: {threshold:.2f} -> {lowered:.2f}")
                retry_hits = self._smart_find._run_clip_multi_prompt(
                    prompts, top_k * 3, lowered, fusion_mode
                )
                if retry_hits:
                    for photo_id, (sem_score, prompt) in retry_hits.items():
                        path = path_lookup.get(photo_id)
                        if not path:
                            # Resolve new photo IDs
                            try:
                                from repository.base_repository import DatabaseConnection
                                db = DatabaseConnection()
                                with db.get_connection() as conn:
                                    row = conn.execute(
                                        "SELECT path FROM photo_metadata WHERE id = ?",
                                        (photo_id,)
                                    ).fetchone()
                                    if row:
                                        path = row['path']
                                        path_lookup[photo_id] = path
                            except Exception:
                                continue
                        if not path:
                            continue
                        if metadata_candidate_paths is not None and path not in metadata_candidate_paths:
                            continue
                        sr = self._score_result(path, sem_score, prompt, project_meta, plan.filters)
                        sr.reasons.append("(backoff)")
                        scored.append(sr)

                    scored.sort(key=lambda r: r.final_score, reverse=True)
                    backoff_applied = True
                    break

        # Step 8: Deduplicate (stack duplicates behind representative)
        scored, stacked_count = self._deduplicate_results(scored)

        # Step 9: Limit to top_k
        scored = scored[:top_k]

        # Step 10: Compute facets from result set
        result_paths = [r.path for r in scored]
        facets = FacetComputer.compute(result_paths, project_meta)

        return OrchestratorResult(
            paths=result_paths,
            total_matches=len(result_paths),
            scored_results=scored,
            scores={r.path: r.final_score for r in scored},
            facets=facets,
            query_plan=plan,
            backoff_applied=backoff_applied,
            phase_label="Semantic refined" if plan.has_semantic() else "Filter results",
            stacked_duplicates=stacked_count,
        )

    def _score_result(self, path: str, clip_score: float,
                      matched_prompt: str,
                      project_meta: Dict[str, Dict],
                      active_filters: Optional[Dict] = None) -> ScoredResult:
        """
        Apply the deterministic scoring contract to a single result.

        S = w_clip * clip + w_recency * recency + w_fav * favorite
          + w_location * location + w_face * face_match
        """
        w = self._weights
        meta = project_meta.get(path, {})
        reasons = []

        # Clip score (already computed)
        if clip_score > 0 and matched_prompt:
            reasons.append(f"clip={clip_score:.3f} (\"{matched_prompt}\")")

        # Recency score
        recency = 0.0
        created = meta.get("created_date") or meta.get("date_taken")
        if created:
            try:
                if isinstance(created, str):
                    dt = datetime.strptime(created[:10], "%Y-%m-%d")
                else:
                    dt = created
                days_ago = max(0, (datetime.now() - dt).days)
                # Smooth exponential decay scaled to [0, max_boost]:
                # today = max_boost, half-life days ago = max_boost/2, etc.
                recency = w.max_recency_boost * (
                    2.0 ** (-days_ago / max(1, w.recency_halflife_days))
                )
                if recency > 0.001:
                    reasons.append(f"recency={recency:.4f} ({days_ago}d ago)")
            except (ValueError, TypeError):
                pass

        # Favorite score
        favorite = 0.0
        rating = meta.get("rating", 0) or 0
        if rating >= 4:
            favorite = min(w.max_favorite_boost, 1.0)
            reasons.append(f"favorite={favorite:.2f} (rating={rating})")
        elif rating >= 3:
            favorite = min(w.max_favorite_boost, 0.5)
            reasons.append(f"favorite={favorite:.2f} (rating={rating})")

        # Location score
        location = 0.0
        if meta.get("has_gps"):
            location = 1.0
            reasons.append("location=1.0 (GPS)")

        # Face match score: 1.0 when person filter is active (result
        # already passed the person filter, so it's a confirmed match)
        face_match = 0.0
        if active_filters and active_filters.get("person_id"):
            face_match = 1.0
            reasons.append(f"face=1.0 (person:{active_filters['person_id']})")

        # Final score
        final = (
            w.w_clip * clip_score
            + w.w_recency * recency
            + w.w_favorite * favorite
            + w.w_location * location
            + w.w_face_match * face_match
        )

        return ScoredResult(
            path=path,
            final_score=final,
            clip_score=clip_score,
            recency_score=recency,
            favorite_score=favorite,
            location_score=location,
            face_match_score=face_match,
            matched_prompt=matched_prompt,
            reasons=reasons,
        )

    def _get_project_meta(self) -> Dict[str, Dict]:
        """Get project photo metadata with caching."""
        now = time.time()
        if (self._project_meta_cache is not None
                and (now - self._meta_cache_time) < self._META_CACHE_TTL):
            return self._project_meta_cache

        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            with db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT path, rating, gps_latitude, gps_longitude, "
                    "created_date, date_taken "
                    "FROM photo_metadata WHERE project_id = ?",
                    (self.project_id,)
                )
                result = {}
                for row in cursor.fetchall():
                    path = row['path']
                    lat = row['gps_latitude']
                    lon = row['gps_longitude']
                    result[path] = {
                        "rating": row['rating'],
                        "has_gps": lat is not None and lon is not None and lat != 0 and lon != 0,
                        "created_date": row['created_date'],
                        "date_taken": row['date_taken'],
                    }
                self._project_meta_cache = result
                self._meta_cache_time = now
                return result
        except Exception as e:
            logger.warning(f"[SearchOrchestrator] Metadata load failed: {e}")
            return self._project_meta_cache or {}

    def _plan_from_preset(self, preset_id: str,
                          extra_filters: Optional[Dict]) -> QueryPlan:
        """Build a QueryPlan from a SmartFind preset."""
        preset = self._smart_find._lookup_preset(preset_id)
        if not preset:
            logger.warning(f"[SearchOrchestrator] Unknown preset: {preset_id}")
            return QueryPlan(raw_query=preset_id, source="preset")

        plan = QueryPlan(
            raw_query=preset.get("name", preset_id),
            source="preset",
            preset_id=preset_id,
            semantic_prompts=list(preset.get("prompts", [])),
            filters=dict(preset.get("filters", {})),
            semantic_weight=preset.get("semantic_weight", 0.8),
        )

        if extra_filters:
            plan.filters.update(extra_filters)

        return plan

    def _build_label(self, plan: QueryPlan, result: OrchestratorResult) -> str:
        """Build a human-readable label for the search result."""
        parts = []

        if plan.preset_id:
            preset = self._smart_find._lookup_preset(plan.preset_id)
            if preset:
                parts.append(f"{preset.get('icon', '')} {preset['name']}")
        elif plan.raw_query:
            parts.append(f"\U0001f50d {plan.raw_query}")

        if plan.extracted_tokens:
            token_labels = [t["label"] for t in plan.extracted_tokens]
            parts.append(f"[{', '.join(token_labels)}]")

        return ' '.join(parts) if parts else "Search"

    def _log_explainability(self, plan: QueryPlan, result: OrchestratorResult):
        """
        Log top-10 results with score components.

        This is the key debugging tool: every search produces
        a compact, reproducible log of why results ranked as they did.
        """
        top_n = min(10, len(result.scored_results))
        if top_n == 0:
            logger.info(
                f"[SearchOrchestrator] query=\"{plan.raw_query}\" "
                f"| 0 results | {result.execution_time_ms:.0f}ms"
                f"{' | filters=' + str(plan.filters) if plan.filters else ''}"
            )
            return

        # Compact summary line
        weights = self._weights
        logger.info(
            f"[SearchOrchestrator] query=\"{plan.raw_query}\" "
            f"| {result.total_matches} results | {result.execution_time_ms:.0f}ms "
            f"| weights=[clip={weights.w_clip:.2f} rec={weights.w_recency:.2f} "
            f"fav={weights.w_favorite:.2f} loc={weights.w_location:.2f} "
            f"face={weights.w_face_match:.2f}]"
            f"{'| backoff' if result.backoff_applied else ''}"
            f"{' | filters=' + str(plan.filters) if plan.filters else ''}"
        )

        # Top-N breakdown
        for i, sr in enumerate(result.scored_results[:top_n]):
            import os
            basename = os.path.basename(sr.path)
            components = (
                f"clip={sr.clip_score:.3f} rec={sr.recency_score:.4f} "
                f"fav={sr.favorite_score:.2f} loc={sr.location_score:.1f} "
                f"face={sr.face_match_score:.1f}"
            )
            dup_tag = f" [+{sr.duplicate_count}]" if sr.duplicate_count else ""
            logger.info(
                f"  #{i+1} {sr.final_score:.4f} | {components} | {basename}{dup_tag}"
            )

        # Facets summary
        if result.facets:
            facet_summary = {k: dict(v) for k, v in result.facets.items()}
            logger.info(f"  facets: {facet_summary}")

    def invalidate_meta_cache(self):
        """Invalidate the metadata cache (call after scans, rating changes, etc.)."""
        self._project_meta_cache = None
        self._meta_cache_time = 0.0

    # ── Duplicate Stacking (P0: fold duplicates into representative + badge) ──

    _dup_cache: Optional[Dict[str, Tuple[str, int]]] = None  # path -> (representative_path, group_size)
    _dup_cache_time: float = 0.0
    _DUP_CACHE_TTL = 120.0  # 2 minutes

    def _get_duplicate_map(self) -> Dict[str, Tuple[str, int]]:
        """
        Build a path -> (representative_path, group_size) map from media_asset model.

        Photos sharing the same content_hash are duplicates. The asset's
        representative_photo_id picks the preview; other instances are folded.
        """
        now = time.time()
        if self._dup_cache is not None and (now - self._dup_cache_time) < self._DUP_CACHE_TTL:
            return self._dup_cache

        dup_map: Dict[str, Tuple[str, int]] = {}
        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            with db.get_connection() as conn:
                # Find assets with >1 instance (= duplicates)
                rows = conn.execute("""
                    SELECT
                        mi.photo_id,
                        pm.path,
                        a.representative_photo_id,
                        a.asset_id
                    FROM media_instance mi
                    JOIN media_asset a ON mi.asset_id = a.asset_id
                        AND mi.project_id = a.project_id
                    JOIN photo_metadata pm ON mi.photo_id = pm.id
                    WHERE mi.project_id = ?
                    AND a.asset_id IN (
                        SELECT asset_id FROM media_instance
                        WHERE project_id = ? GROUP BY asset_id HAVING COUNT(*) > 1
                    )
                    ORDER BY a.asset_id
                """, (self.project_id, self.project_id)).fetchall()

                # Group by asset_id
                from collections import defaultdict
                asset_groups: Dict[int, List[Tuple[int, str]]] = defaultdict(list)
                rep_map: Dict[int, Optional[int]] = {}
                for row in rows:
                    asset_id = row['asset_id']
                    asset_groups[asset_id].append((row['photo_id'], row['path']))
                    if row['representative_photo_id'] is not None:
                        rep_map[asset_id] = row['representative_photo_id']

                for asset_id, members in asset_groups.items():
                    group_size = len(members)
                    rep_id = rep_map.get(asset_id)
                    # Find representative path
                    rep_path = None
                    for pid, ppath in members:
                        if pid == rep_id:
                            rep_path = ppath
                            break
                    if not rep_path:
                        rep_path = members[0][1]  # fallback to first

                    for _, ppath in members:
                        dup_map[ppath] = (rep_path, group_size)

        except Exception as e:
            logger.debug(f"[SearchOrchestrator] Duplicate map build failed: {e}")

        self._dup_cache = dup_map
        self._dup_cache_time = now
        return dup_map

    def _deduplicate_results(self, scored: List[ScoredResult]) -> Tuple[List[ScoredResult], int]:
        """
        Stack duplicate results: keep highest-scoring representative per
        duplicate group, annotate with duplicate_count badge.

        Returns (deduped_list, stacked_count).
        """
        dup_map = self._get_duplicate_map()
        if not dup_map:
            return scored, 0

        # Group results by representative path
        seen_reps: Dict[str, ScoredResult] = {}
        non_dup: List[ScoredResult] = []
        stacked = 0

        for sr in scored:
            entry = dup_map.get(sr.path)
            if entry is None:
                non_dup.append(sr)
                continue

            rep_path, group_size = entry
            if rep_path in seen_reps:
                # This is a duplicate of an already-seen representative
                existing = seen_reps[rep_path]
                if sr.final_score > existing.final_score:
                    # Swap: this instance scored higher, promote it
                    seen_reps[rep_path] = sr
                stacked += 1
            else:
                sr.duplicate_count = group_size - 1  # other copies
                seen_reps[rep_path] = sr

        result = non_dup + list(seen_reps.values())
        result.sort(key=lambda r: r.final_score, reverse=True)
        return result, stacked

    # ── Progressive Search (metadata first, then semantic) ──

    def search_metadata_only(self, query: str, top_k: int = 200,
                             extra_filters: Optional[Dict] = None) -> OrchestratorResult:
        """
        Phase 1 of progressive search: metadata-only results.

        Returns instantly (<50ms) with filter-matched results.
        No CLIP/semantic scoring - just structured tokens + NL date/rating
        extraction + SQL metadata filters. Results scored by recency/fav/location
        only (clip_score=0 for all).

        The UI should call this first, then call search() for full results.
        """
        start = time.time()
        plan = TokenParser.parse(query)
        if extra_filters:
            plan.filters.update(extra_filters)

        # Force metadata-only: even if there's semantic text, only use filters
        project_meta = self._get_project_meta()
        scored: List[ScoredResult] = []

        if plan.has_filters():
            metadata_paths = self._smart_find._run_metadata_filter(plan.filters)
            for path in metadata_paths[:top_k]:
                sr = self._score_result(path, 0.0, "", project_meta, plan.filters)
                scored.append(sr)
        else:
            # No explicit filters from tokens - show recent photos as baseline
            all_paths = list(project_meta.keys())
            # Sort by date (most recent first)
            def _date_key(p):
                m = project_meta.get(p, {})
                d = m.get("created_date") or m.get("date_taken") or ""
                return str(d)
            all_paths.sort(key=_date_key, reverse=True)
            for path in all_paths[:top_k]:
                sr = self._score_result(path, 0.0, "", project_meta, plan.filters)
                scored.append(sr)

        scored.sort(key=lambda r: r.final_score, reverse=True)
        scored = scored[:top_k]

        result_paths = [r.path for r in scored]
        facets = FacetComputer.compute(result_paths, project_meta)

        result = OrchestratorResult(
            paths=result_paths,
            total_matches=len(result_paths),
            scored_results=scored,
            scores={r.path: r.final_score for r in scored},
            facets=facets,
            query_plan=plan,
            execution_time_ms=(time.time() - start) * 1000,
            label=self._build_label(plan, OrchestratorResult(paths=result_paths)),
            phase="metadata",
            phase_label="Metadata results",
        )
        logger.info(
            f"[SearchOrchestrator] Progressive phase=metadata: "
            f"query=\"{query}\" → {len(result_paths)} results in "
            f"{result.execution_time_ms:.0f}ms"
        )
        return result

    # ── Find Similar (Excire-style image-to-image) ──

    def find_similar(self, photo_path: str, top_k: int = 50,
                     threshold: float = 0.5) -> OrchestratorResult:
        """
        Find photos visually similar to a reference photo.

        Uses CLIP embeddings + FAISS/numpy cosine similarity (not text query).
        Returns results through the same OrchestratorResult interface so
        facets, scoring, and UI all work identically.

        Args:
            photo_path: Path to the reference photo
            top_k: Maximum results
            threshold: Minimum similarity (0-1)
        """
        start = time.time()

        try:
            from services.semantic_embedding_service import get_semantic_embedding_service
            from repository.project_repository import ProjectRepository
            from repository.base_repository import DatabaseConnection

            # Get canonical model
            proj_repo = ProjectRepository()
            model_name = proj_repo.get_semantic_model(self.project_id) or \
                "openai/clip-vit-base-patch32"
            service = get_semantic_embedding_service(model_name=model_name)

            if not service._available:
                logger.warning("[SearchOrchestrator] find_similar: semantic service not available")
                return OrchestratorResult(label="Find Similar - AI not available")

            # Get reference photo's embedding
            db = DatabaseConnection()
            ref_photo_id = None
            ref_embedding = None

            with db.get_connection() as conn:
                # Look up photo_id from path
                row = conn.execute(
                    "SELECT id FROM photo_metadata WHERE path = ? AND project_id = ?",
                    (photo_path, self.project_id)
                ).fetchone()
                if not row:
                    return OrchestratorResult(label="Find Similar - Photo not found")
                ref_photo_id = row['id']

                # Get its embedding
                emb_row = conn.execute(
                    "SELECT embedding FROM semantic_embeddings WHERE photo_id = ?",
                    (ref_photo_id,)
                ).fetchone()
                if not emb_row:
                    return OrchestratorResult(label="Find Similar - No embedding (run Extract Embeddings)")
                ref_embedding = np.frombuffer(emb_row['embedding'], dtype=np.float32)
                if len(ref_embedding) == 0:
                    ref_embedding = np.frombuffer(emb_row['embedding'], dtype=np.float16).astype(np.float32)

                # Get all project embeddings
                rows = conn.execute("""
                    SELECT se.photo_id, se.embedding, pm.path
                    FROM semantic_embeddings se
                    JOIN photo_metadata pm ON se.photo_id = pm.id
                    WHERE pm.project_id = ?
                """, (self.project_id,)).fetchall()

            if not rows:
                return OrchestratorResult(label="Find Similar - No embeddings")

            # Build embedding dict
            embeddings = {}
            path_by_id = {}
            for row in rows:
                try:
                    emb = np.frombuffer(row['embedding'], dtype=np.float32)
                    if len(emb) == 0:
                        emb = np.frombuffer(row['embedding'], dtype=np.float16).astype(np.float32)
                    if len(emb) > 0:
                        embeddings[row['photo_id']] = emb
                        path_by_id[row['photo_id']] = row['path']
                except Exception:
                    continue

            # Use the embedding service's find_similar_photos
            similar_results = service.find_similar_photos(
                query_embedding=ref_embedding,
                embeddings=embeddings,
                top_k=top_k,
                threshold=threshold,
                exclude_photo_id=ref_photo_id,
            )

            # Score through orchestrator pipeline
            project_meta = self._get_project_meta()
            scored: List[ScoredResult] = []
            import os
            ref_basename = os.path.basename(photo_path)

            for photo_id, sim_score in similar_results:
                path = path_by_id.get(photo_id, "")
                if not path:
                    continue
                sr = self._score_result(path, sim_score, f"similar to {ref_basename}", project_meta)
                scored.append(sr)

            scored.sort(key=lambda r: r.final_score, reverse=True)

            result_paths = [r.path for r in scored]
            facets = FacetComputer.compute(result_paths, project_meta)

            result = OrchestratorResult(
                paths=result_paths,
                total_matches=len(result_paths),
                scored_results=scored,
                scores={r.path: r.final_score for r in scored},
                facets=facets,
                query_plan=QueryPlan(
                    raw_query=f"similar:{ref_basename}",
                    source="similar",
                    semantic_text=f"similar to {ref_basename}",
                ),
                execution_time_ms=(time.time() - start) * 1000,
                label=f"\U0001f3af Similar to {ref_basename}",
            )
            self._log_explainability(result.query_plan, result)
            return result

        except Exception as e:
            logger.error(f"[SearchOrchestrator] find_similar failed: {e}", exc_info=True)
            return OrchestratorResult(label=f"Find Similar - Error: {e}")

    # ── ANN Retrieval (two-stage: FAISS candidate → full scoring) ──

    _ann_index_cache: Dict[int, Tuple] = {}  # class-level: {project_id: (index, photo_ids, vectors, timestamp)}
    _ann_dirty: set = set()  # class-level: project_ids with new embeddings since last build
    _ANN_CACHE_TTL = 300.0  # 5 minutes

    def _get_or_build_ann_index(self):
        """
        Get or build a FAISS/numpy ANN index for the project.

        Caches the index for _ANN_CACHE_TTL seconds.
        Rebuilds immediately if marked dirty (new embeddings added).
        For projects with >500 embeddings and FAISS available,
        uses FAISS IndexFlatIP for O(log n) retrieval.
        """
        if not _numpy_available:
            return None, [], {}

        now = time.time()
        is_dirty = self.project_id in SearchOrchestrator._ann_dirty
        cached = SearchOrchestrator._ann_index_cache.get(self.project_id)
        if cached and not is_dirty and (now - cached[3]) < self._ANN_CACHE_TTL:
            return cached[0], cached[1], cached[2]

        if is_dirty:
            logger.info(f"[SearchOrchestrator] ANN index dirty (new embeddings) — rebuilding for project {self.project_id}")
            SearchOrchestrator._ann_dirty.discard(self.project_id)

        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()

            with db.get_connection() as conn:
                rows = conn.execute("""
                    SELECT se.photo_id, se.embedding, pm.path
                    FROM semantic_embeddings se
                    JOIN photo_metadata pm ON se.photo_id = pm.id
                    WHERE pm.project_id = ?
                """, (self.project_id,)).fetchall()

            if not rows:
                return None, [], {}

            photo_ids = []
            vectors = []
            path_lookup = {}

            for row in rows:
                try:
                    emb = np.frombuffer(row['embedding'], dtype=np.float32)
                    if len(emb) == 0:
                        emb = np.frombuffer(row['embedding'], dtype=np.float16).astype(np.float32)
                    if len(emb) > 0:
                        photo_ids.append(row['photo_id'])
                        vectors.append(emb)
                        path_lookup[row['photo_id']] = row['path']
                except Exception:
                    continue

            if not vectors:
                return None, [], {}

            vectors_np = np.vstack(vectors).astype('float32')
            # Normalize for cosine similarity
            norms = np.linalg.norm(vectors_np, axis=1, keepdims=True)
            vectors_np = vectors_np / np.maximum(norms, 1e-8)

            n_vectors = len(photo_ids)
            dim = vectors_np.shape[1]

            if _faiss_available and n_vectors >= 500:
                index = _faiss.IndexFlatIP(dim)
                index.add(vectors_np)
                index_data = ('faiss', index, vectors_np)
                logger.info(
                    f"[SearchOrchestrator] Built FAISS ANN index: "
                    f"{n_vectors} vectors, dim={dim}"
                )
            else:
                index_data = ('numpy', None, vectors_np)
                logger.debug(
                    f"[SearchOrchestrator] Using numpy brute-force: "
                    f"{n_vectors} vectors"
                )

            SearchOrchestrator._ann_index_cache[self.project_id] = (
                index_data, photo_ids, path_lookup, now
            )
            return index_data, photo_ids, path_lookup

        except Exception as e:
            logger.error(f"[SearchOrchestrator] ANN index build failed: {e}")
            return None, [], {}

    def search_ann(self, query_text: str, top_k: int = 200,
                   extra_filters: Optional[Dict] = None) -> OrchestratorResult:
        """
        Two-stage ANN search: FAISS candidate retrieval → full scoring.

        Stage 1: Encode query with CLIP, use FAISS for fast top-K candidates
        Stage 2: Apply full scoring contract (recency, favorites, etc.)

        Falls back to standard search() if no ANN index is available.
        """
        index_data, photo_ids, path_lookup = self._get_or_build_ann_index()
        if index_data is None or not photo_ids:
            # Fallback to standard search
            return self.search(query_text, top_k, extra_filters)

        start = time.time()
        plan = TokenParser.parse(query_text)
        if extra_filters:
            plan.filters.update(extra_filters)

        try:
            from services.semantic_embedding_service import get_semantic_embedding_service
            from repository.project_repository import ProjectRepository

            proj_repo = ProjectRepository()
            model_name = proj_repo.get_semantic_model(self.project_id) or \
                "openai/clip-vit-base-patch32"
            service = get_semantic_embedding_service(model_name=model_name)

            if not service._available or not plan.has_semantic():
                return self.search(query_text, top_k, extra_filters)

            # Stage 1: Encode query and retrieve candidates via ANN
            semantic_text = plan.semantic_text or (
                plan.semantic_prompts[0] if plan.semantic_prompts else ""
            )
            if not semantic_text:
                return self.search(query_text, top_k, extra_filters)

            query_emb = service.encode_text(semantic_text)
            query_emb = query_emb.astype('float32')
            query_norm = np.linalg.norm(query_emb)
            if query_norm > 0:
                query_emb = query_emb / query_norm
            query_emb = query_emb.reshape(1, -1)

            index_type, index, vectors = index_data
            candidate_k = min(top_k * 3, len(photo_ids))

            ann_hits = {}  # {photo_id: (score, query_text)}

            if index_type == 'faiss' and _faiss_available:
                sims, indices = index.search(query_emb, candidate_k)
                for sim, idx in zip(sims[0], indices[0]):
                    if 0 <= idx < len(photo_ids):
                        ann_hits[photo_ids[idx]] = (float(sim), semantic_text)
            else:
                sims = np.dot(vectors, query_emb.T).flatten()
                if len(sims) > candidate_k:
                    top_idx = np.argpartition(sims, -candidate_k)[-candidate_k:]
                else:
                    top_idx = np.arange(len(sims))
                for idx in top_idx:
                    ann_hits[photo_ids[idx]] = (float(sims[idx]), semantic_text)

            # Stage 2: Apply metadata filters + full scoring
            metadata_candidate_paths = None
            if plan.has_filters():
                metadata_paths = self._smart_find._run_metadata_filter(plan.filters)
                metadata_candidate_paths = set(metadata_paths)

            project_meta = self._get_project_meta()
            cfg = self._smart_find._get_config()
            threshold = cfg["threshold"]
            scored: List[ScoredResult] = []

            for photo_id, (sem_score, prompt) in ann_hits.items():
                if sem_score < threshold:
                    continue
                path = path_lookup.get(photo_id)
                if not path:
                    continue
                if metadata_candidate_paths is not None and path not in metadata_candidate_paths:
                    continue
                sr = self._score_result(path, sem_score, prompt, project_meta, plan.filters)
                scored.append(sr)

            scored.sort(key=lambda r: r.final_score, reverse=True)
            scored = scored[:top_k]

            result_paths = [r.path for r in scored]
            facets = FacetComputer.compute(result_paths, project_meta)

            result = OrchestratorResult(
                paths=result_paths,
                total_matches=len(result_paths),
                scored_results=scored,
                scores={r.path: r.final_score for r in scored},
                facets=facets,
                query_plan=plan,
                execution_time_ms=(time.time() - start) * 1000,
                label=self._build_label(plan, OrchestratorResult(paths=result_paths)),
            )
            self._log_explainability(plan, result)
            logger.info(
                f"[SearchOrchestrator] ANN search: "
                f"index_type={index_type}, candidates={len(ann_hits)}, "
                f"final={len(scored)}, {result.execution_time_ms:.0f}ms"
            )
            return result

        except Exception as e:
            logger.error(f"[SearchOrchestrator] ANN search failed, falling back: {e}")
            return self.search(query_text, top_k, extra_filters)

    def invalidate_ann_cache(self):
        """Invalidate ANN index cache (call after embedding extraction)."""
        SearchOrchestrator._ann_index_cache.pop(self.project_id, None)
        SearchOrchestrator._ann_dirty.discard(self.project_id)

    @classmethod
    def mark_ann_dirty(cls, project_id: int):
        """
        Mark ANN index as dirty for a project.

        Call this after new embeddings are generated or backfilled.
        The next search_ann() call will rebuild the index instead of
        serving a stale cached copy that's missing the new vectors.
        """
        cls._ann_dirty.add(project_id)
        logger.info(f"[SearchOrchestrator] ANN index marked dirty for project {project_id}")

    # ── Relevance Feedback (search_events + personal boost) ──

    @staticmethod
    def record_search_event(project_id: int, query_hash: str,
                            asset_path: str, action: str):
        """
        Record a user interaction with a search result for relevance feedback.

        Actions: 'click', 'open', 'add_to_album', 'favorite_toggle', 'share'.
        This data powers a future personal_relevance scoring term.
        """
        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            with db.get_connection() as conn:
                conn.execute("""
                    INSERT INTO search_events
                        (project_id, query_hash, asset_path, action)
                    VALUES (?, ?, ?, ?)
                """, (project_id, query_hash, asset_path, action))
                conn.commit()
        except Exception as e:
            # Table may not exist yet; log and move on
            logger.debug(f"[SearchOrchestrator] record_search_event: {e}")

    @staticmethod
    def get_personal_boost(project_id: int, query_hash: str,
                           path: str) -> float:
        """
        Compute a capped personal relevance boost from past interactions.

        Returns a value in [0.0, 0.15] based on how often this asset
        was clicked/opened for similar queries.
        """
        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            with db.get_connection() as conn:
                row = conn.execute("""
                    SELECT COUNT(*) as cnt FROM search_events
                    WHERE project_id = ? AND query_hash = ? AND asset_path = ?
                """, (project_id, query_hash, path)).fetchone()
                if row and row['cnt'] > 0:
                    # Capped log boost: 1 interaction = 0.05, 3 = 0.10, 10+ = 0.15
                    return min(0.15, 0.05 * math.log2(1 + row['cnt']))
        except Exception:
            pass
        return 0.0

    # ── Query Autocomplete (history + library stats) ──

    @staticmethod
    def autocomplete(project_id: int, prefix: str,
                     max_results: int = 8) -> List[Dict[str, str]]:
        """
        Generate autocomplete suggestions from search history + library stats.

        Returns a list of {"label": "...", "query": "...", "source": "..."} dicts
        combining:
        1. Recent queries matching the prefix (from search_history table)
        2. Library-based suggestions from LibraryAnalyzer
        3. Token completions (type:, date:, rating:, has:, is:, ext:, person:)
        """
        suggestions: List[Dict[str, str]] = []
        prefix_lower = prefix.strip().lower()

        if not prefix_lower:
            return suggestions

        # 1. Search history matches
        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            with db.get_connection() as conn:
                rows = conn.execute("""
                    SELECT DISTINCT query FROM search_history
                    WHERE project_id = ? AND LOWER(query) LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT 4
                """, (project_id, f"{prefix_lower}%")).fetchall()
                for row in rows:
                    suggestions.append({
                        "label": row['query'],
                        "query": row['query'],
                        "source": "history",
                    })
        except Exception:
            pass

        # 2. Token completions
        token_prefixes = {
            "type:": ["type:video", "type:photo"],
            "is:": ["is:fav", "is:favorite"],
            "has:": ["has:location", "has:gps", "has:faces"],
            "date:": ["date:2024", "date:2025", "date:2026"],
            "rating:": ["rating:3", "rating:4", "rating:5"],
            "ext:": ["ext:jpg", "ext:png", "ext:heic", "ext:raw"],
            "person:": [],
        }
        for tok_prefix, completions in token_prefixes.items():
            if tok_prefix.startswith(prefix_lower) or prefix_lower.startswith(tok_prefix):
                for comp in completions:
                    if comp.lower().startswith(prefix_lower) and len(suggestions) < max_results:
                        suggestions.append({
                            "label": comp,
                            "query": comp,
                            "source": "token",
                        })

        # 3. Library suggestions (if prefix is long enough for semantic matching)
        if len(prefix_lower) >= 3:
            try:
                lib_suggestions = LibraryAnalyzer.suggest(project_id, max_suggestions=4)
                for s in lib_suggestions:
                    label = s.get("label", "")
                    if prefix_lower in label.lower() and len(suggestions) < max_results:
                        suggestions.append({
                            "label": label,
                            "query": s.get("query", ""),
                            "source": "library",
                        })
            except Exception:
                pass

        return suggestions[:max_results]

    # ── OCR Search Integration Point ──

    @staticmethod
    def search_ocr_text(project_id: int, query: str,
                        limit: int = 50) -> List[str]:
        """
        Search photos by OCR text content using FTS5.

        Returns a list of photo paths matching the query in their
        extracted OCR text. The FTS5 table (ocr_fts5) is populated
        by the OCR pipeline during background processing.

        Falls back gracefully if the ocr_text column or FTS5 table
        doesn't exist yet.
        """
        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            with db.get_connection() as conn:
                rows = conn.execute("""
                    SELECT pm.path
                    FROM ocr_fts5 fts
                    JOIN photo_metadata pm ON fts.rowid = pm.id
                    WHERE fts.ocr_text MATCH ? AND pm.project_id = ?
                    LIMIT ?
                """, (query, project_id, limit)).fetchall()
                return [row['path'] for row in rows]
        except Exception:
            # FTS5 table not created yet — OCR pipeline hasn't run
            return []


# ══════════════════════════════════════════════════════════════════════
# Library Analyzer - suggested searches from library stats
# ══════════════════════════════════════════════════════════════════════

class LibraryAnalyzer:
    """
    Analyze library metadata to generate contextual search suggestions.

    Produces "suggested searches" chips based on what's actually in the
    library - inspired by Google Photos' auto-generated albums and
    Excire's tag suggestions.

    Only suggests what exists (no "Sunsets" if there are no sunset photos).
    """

    @staticmethod
    def suggest(project_id: int, max_suggestions: int = 8) -> List[Dict[str, str]]:
        """
        Generate search suggestions from library metadata stats.

        Returns list of suggestion dicts:
            [
                {"label": "2024 Photos (1,234)", "query": "date:2024", "icon": "📅"},
                {"label": "Favorites (56)", "query": "is:fav", "icon": "⭐"},
                {"label": "iPhone shots (890)", "query": "camera:iPhone", "icon": "📱"},
                ...
            ]
        """
        suggestions = []

        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()

            with db.get_connection() as conn:
                # 1. Year distribution - suggest top years
                year_rows = conn.execute("""
                    SELECT
                        SUBSTR(COALESCE(created_date, date_taken), 1, 4) as year,
                        COUNT(*) as cnt
                    FROM photo_metadata
                    WHERE project_id = ?
                      AND COALESCE(created_date, date_taken) IS NOT NULL
                      AND LENGTH(COALESCE(created_date, date_taken)) >= 4
                    GROUP BY year
                    HAVING cnt >= 5
                    ORDER BY cnt DESC
                    LIMIT 4
                """, (project_id,)).fetchall()

                for row in year_rows:
                    year = row['year']
                    cnt = row['cnt']
                    if year and year.isdigit() and 1990 <= int(year) <= 2099:
                        suggestions.append({
                            "label": f"{year} ({cnt:,})",
                            "query": f"date:{year}",
                            "icon": "\U0001f4c5",
                        })

                # 2. Favorites count
                fav_row = conn.execute("""
                    SELECT COUNT(*) as cnt FROM photo_metadata
                    WHERE project_id = ? AND rating >= 4
                """, (project_id,)).fetchone()
                if fav_row and fav_row['cnt'] > 0:
                    suggestions.append({
                        "label": f"Favorites ({fav_row['cnt']:,})",
                        "query": "is:fav",
                        "icon": "\u2b50",
                    })

                # 3. Photos with GPS
                gps_row = conn.execute("""
                    SELECT COUNT(*) as cnt FROM photo_metadata
                    WHERE project_id = ?
                      AND gps_latitude IS NOT NULL
                      AND gps_longitude IS NOT NULL
                      AND gps_latitude != 0
                """, (project_id,)).fetchone()
                if gps_row and gps_row['cnt'] > 0:
                    suggestions.append({
                        "label": f"With Location ({gps_row['cnt']:,})",
                        "query": "has:location",
                        "icon": "\U0001f4cd",
                    })

                # 4. Videos
                vid_row = conn.execute("""
                    SELECT COUNT(*) as cnt FROM photo_metadata
                    WHERE project_id = ?
                      AND LOWER(SUBSTR(path, -4)) IN ('.mp4', '.mov', '.avi', '.mkv', '.m4v')
                """, (project_id,)).fetchone()
                if vid_row and vid_row['cnt'] > 0:
                    suggestions.append({
                        "label": f"Videos ({vid_row['cnt']:,})",
                        "query": "type:video",
                        "icon": "\U0001f3ac",
                    })

                # 5. Photos with faces
                try:
                    face_row = conn.execute("""
                        SELECT COUNT(DISTINCT pm.id) as cnt
                        FROM photo_metadata pm
                        JOIN faces f ON pm.id = f.photo_id
                        WHERE pm.project_id = ?
                    """, (project_id,)).fetchone()
                    if face_row and face_row['cnt'] > 0:
                        suggestions.append({
                            "label": f"With Faces ({face_row['cnt']:,})",
                            "query": "has:faces",
                            "icon": "\U0001f464",
                        })
                except Exception:
                    pass  # faces table may not exist

                # 6. Rated photos (3+)
                rated_row = conn.execute("""
                    SELECT COUNT(*) as cnt FROM photo_metadata
                    WHERE project_id = ? AND rating >= 3 AND rating < 4
                """, (project_id,)).fetchone()
                if rated_row and rated_row['cnt'] > 0:
                    suggestions.append({
                        "label": f"3+ Stars ({rated_row['cnt']:,})",
                        "query": "rating:3",
                        "icon": "\u2b50",
                    })

        except Exception as e:
            logger.warning(f"[LibraryAnalyzer] suggest failed: {e}")

        return suggestions[:max_suggestions]


# ══════════════════════════════════════════════════════════════════════
# Module-level singleton cache
# ══════════════════════════════════════════════════════════════════════

_orchestrators: Dict[int, SearchOrchestrator] = {}
_lock = threading.Lock()


def get_search_orchestrator(project_id: int) -> SearchOrchestrator:
    """Get or create SearchOrchestrator for a project (singleton per project)."""
    with _lock:
        if project_id not in _orchestrators:
            _orchestrators[project_id] = SearchOrchestrator(project_id)
        return _orchestrators[project_id]
