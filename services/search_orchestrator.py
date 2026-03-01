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
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from logging_config import get_logger

logger = get_logger(__name__)


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
    recency_halflife_days: int = 365  # How fast recency decays

    def validate(self):
        """Ensure weights sum to ~1.0 and are reasonable."""
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

        elif key == "camera":
            filters["camera_model"] = value
            return {"type": "camera", "label": f"Camera: {value}", "key": "camera_model", "value": value}

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

                sr = self._score_result(path, sem_score, matched_prompt, project_meta)
                scored.append(sr)

        elif metadata_candidate_paths is not None:
            for path in metadata_candidate_paths:
                sr = self._score_result(path, 0.0, "", project_meta)
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
                        sr = self._score_result(path, sem_score, prompt, project_meta)
                        sr.reasons.append("(backoff)")
                        scored.append(sr)

                    scored.sort(key=lambda r: r.final_score, reverse=True)
                    backoff_applied = True
                    break

        # Step 8: Limit to top_k
        scored = scored[:top_k]

        # Step 9: Compute facets from result set
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
        )

    def _score_result(self, path: str, clip_score: float,
                      matched_prompt: str,
                      project_meta: Dict[str, Dict]) -> ScoredResult:
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
                days_ago = (datetime.now() - dt).days
                # Exponential decay: score = 2^(-days/halflife)
                recency = min(w.max_recency_boost,
                              2.0 ** (-days_ago / max(1, w.recency_halflife_days)))
                if recency > 0.01:
                    reasons.append(f"recency={recency:.3f} ({days_ago}d ago)")
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

        # Face match score (future: when person filter is active)
        face_match = 0.0

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
            f"fav={weights.w_favorite:.2f} loc={weights.w_location:.2f}]"
            f"{'| backoff' if result.backoff_applied else ''}"
            f"{' | filters=' + str(plan.filters) if plan.filters else ''}"
        )

        # Top-N breakdown
        for i, sr in enumerate(result.scored_results[:top_n]):
            import os
            basename = os.path.basename(sr.path)
            components = (
                f"clip={sr.clip_score:.3f} rec={sr.recency_score:.3f} "
                f"fav={sr.favorite_score:.2f} loc={sr.location_score:.1f}"
            )
            logger.info(
                f"  #{i+1} {sr.final_score:.4f} | {components} | {basename}"
            )

        # Facets summary
        if result.facets:
            facet_summary = {k: dict(v) for k, v in result.facets.items()}
            logger.info(f"  facets: {facet_summary}")

    def invalidate_meta_cache(self):
        """Invalidate the metadata cache (call after scans, rating changes, etc.)."""
        self._project_meta_cache = None
        self._meta_cache_time = 0.0


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
