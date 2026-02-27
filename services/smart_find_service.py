# services/smart_find_service.py
# Smart Find Service - Combines CLIP semantic search + metadata filtering
# Inspired by iPhone/Google Photos/Lightroom/Excire discovery patterns

"""
SmartFindService - Intelligent photo discovery engine.

Combines two existing services:
- SemanticSearchService (CLIP text-to-image similarity)
- SearchService (metadata SQL filters: dates, GPS, tags, camera, etc.)

Pipeline:
1. If preset has prompts -> run CLIP search across all prompts, merge results
2. If preset has metadata filters -> apply SQL filters to narrow results
3. Score fusion: combine CLIP similarity + metadata match into final ranking
4. Return ordered list of file paths for grid display

Phase 2 additions:
- Custom preset CRUD (save/edit/delete user-created presets)
- Save current search as preset
- Natural language parsing (extract dates, ratings, etc. before CLIP fallback)
- Combinable filters (stack multiple presets + metadata)

Usage:
    from services.smart_find_service import SmartFindService

    service = SmartFindService(project_id=1)
    results = service.find_by_preset("beach")
    # Returns: SmartFindResult(paths=[...], scores={...}, ...)
"""

import json
import re
import time
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from logging_config import get_logger

logger = get_logger(__name__)


# ── Builtin Presets (iPhone/Google Photos inspired categories) ──

BUILTIN_PRESETS = [
    # Places / Scenes
    {
        "id": "beach", "name": "Beach", "icon": "\U0001f3d6\ufe0f",
        "prompts": ["beach", "sand", "seaside", "coast", "ocean shore"],
        "category": "places",
    },
    {
        "id": "mountains", "name": "Mountains", "icon": "\u26f0\ufe0f",
        "prompts": ["mountain", "mountain view", "peaks", "hiking trail", "mountain landscape"],
        "category": "places",
    },
    {
        "id": "city", "name": "City", "icon": "\U0001f3d9\ufe0f",
        "prompts": ["city skyline", "urban", "buildings", "downtown", "street view"],
        "category": "places",
    },
    {
        "id": "forest", "name": "Forest", "icon": "\U0001f332",
        "prompts": ["forest", "trees", "woods", "nature trail", "woodland"],
        "category": "places",
    },
    {
        "id": "lake", "name": "Lake & River", "icon": "\U0001f3de\ufe0f",
        "prompts": ["lake", "river", "waterfall", "pond", "stream"],
        "category": "places",
    },

    # Events / Activities
    {
        "id": "wedding", "name": "Wedding", "icon": "\U0001f492",
        "prompts": ["wedding", "bride", "wedding ceremony", "wedding dress", "wedding reception"],
        "category": "events",
    },
    {
        "id": "party", "name": "Party", "icon": "\U0001f389",
        "prompts": ["party", "celebration", "birthday party", "gathering", "birthday cake"],
        "category": "events",
    },
    {
        "id": "travel", "name": "Travel", "icon": "\u2708\ufe0f",
        "prompts": ["travel", "vacation", "sightseeing", "tourist attraction", "landmark"],
        "category": "events",
    },
    {
        "id": "sport", "name": "Sports", "icon": "\u26bd",
        "prompts": ["sport", "playing sports", "athletic activity", "game", "exercise"],
        "category": "events",
    },

    # Subjects
    {
        "id": "sunset", "name": "Sunset & Sunrise", "icon": "\U0001f305",
        "prompts": ["sunset", "sunrise", "golden hour", "dusk sky"],
        "category": "subjects",
    },
    {
        "id": "food", "name": "Food & Drinks", "icon": "\U0001f355",
        "prompts": ["food", "meal", "dish", "restaurant table", "cooking"],
        "category": "subjects",
    },
    {
        "id": "pets", "name": "Pets & Animals", "icon": "\U0001f43e",
        "prompts": ["dog", "cat", "pet", "puppy", "kitten", "animal"],
        "category": "subjects",
    },
    {
        "id": "baby", "name": "Baby & Kids", "icon": "\U0001f476",
        "prompts": ["baby", "infant", "toddler", "small child", "kids playing"],
        "category": "subjects",
    },
    {
        "id": "portraits", "name": "Portraits", "icon": "\U0001f5bc\ufe0f",
        "prompts": ["portrait", "headshot", "face close-up", "person posing"],
        "category": "subjects",
    },
    {
        "id": "flowers", "name": "Flowers & Garden", "icon": "\U0001f338",
        "prompts": ["flowers", "garden", "blooming", "bouquet", "floral"],
        "category": "subjects",
    },
    {
        "id": "snow", "name": "Snow & Winter", "icon": "\u2744\ufe0f",
        "prompts": ["snow", "winter", "skiing", "snowfall", "ice"],
        "category": "subjects",
    },
    {
        "id": "night", "name": "Night & Stars", "icon": "\U0001f319",
        "prompts": ["night sky", "stars", "night photography", "moon", "city lights at night"],
        "category": "subjects",
    },
    {
        "id": "architecture", "name": "Architecture", "icon": "\U0001f3db\ufe0f",
        "prompts": ["architecture", "building facade", "interior design", "monument", "church"],
        "category": "subjects",
    },
    {
        "id": "car", "name": "Cars & Vehicles", "icon": "\U0001f697",
        "prompts": ["car", "vehicle", "automobile", "motorcycle", "truck"],
        "category": "subjects",
    },

    # Media types (metadata-only, no CLIP needed)
    {
        "id": "screenshots", "name": "Screenshots", "icon": "\U0001f4f1",
        "prompts": ["screenshot", "screen capture", "phone screen"],
        "category": "media",
    },
    {
        "id": "documents", "name": "Documents", "icon": "\U0001f4c4",
        "prompts": ["document", "text", "paper", "receipt", "handwriting"],
        "category": "media",
    },
    {
        "id": "videos", "name": "Videos", "icon": "\U0001f3ac",
        "prompts": [],
        "filters": {"media_type": "video"},
        "category": "media",
    },
    {
        "id": "panoramas", "name": "Panoramas", "icon": "\U0001f304",
        "prompts": ["panoramic view", "wide landscape"],
        "filters": {"orientation": "landscape", "width_min": 4000},
        "category": "media",
    },

    # Quality flags (metadata-only)
    {
        "id": "favorites", "name": "Favorites", "icon": "\u2b50",
        "prompts": [],
        "filters": {"rating_min": 4},
        "category": "quality",
    },
    {
        "id": "gps_photos", "name": "With Location", "icon": "\U0001f4cd",
        "prompts": [],
        "filters": {"has_gps": True},
        "category": "quality",
    },
]

# Build lookup for fast preset access
_BUILTIN_LOOKUP = {p["id"]: p for p in BUILTIN_PRESETS}


@dataclass
class SmartFindResult:
    """Result from a Smart Find query."""
    paths: List[str]
    query_label: str  # Human-readable label (e.g., "Beach", "Mountains")
    total_matches: int
    execution_time_ms: float
    scores: Optional[Dict[str, float]] = None  # path -> score for ranking info
    excluded_paths: Optional[List[str]] = None  # paths user chose to exclude


# ── Natural Language Parser ──

class NLQueryParser:
    """
    Parse natural language queries to extract structured metadata filters.

    Inspired by Lightroom/Excire: attempt structured extraction before CLIP fallback.
    Examples:
        "sunset photos from 2024" -> {prompts: ["sunset"], filters: {date_from: "2024-01-01"}}
        "5 star beach" -> {prompts: ["beach"], filters: {rating_min: 5}}
        "videos from last month" -> {prompts: [], filters: {media_type: "video", date: "last_month"}}
    """

    # Date patterns
    _YEAR_PATTERN = re.compile(
        r'\b(?:from|in|during|taken\s+in|shot\s+in)\s+(\d{4})\b', re.IGNORECASE)
    _MONTH_YEAR_PATTERN = re.compile(
        r'\b(?:from|in|during)\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|'
        r'may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|'
        r'nov(?:ember)?|dec(?:ember)?)\s+(\d{4})\b', re.IGNORECASE)
    _RELATIVE_DATE_PATTERN = re.compile(
        r'\b(today|yesterday|this\s+week|last\s+week|this\s+month|last\s+month|'
        r'this\s+year|last\s+year)\b', re.IGNORECASE)

    # Rating patterns
    _RATING_PATTERN = re.compile(
        r'\b(\d)\s*(?:star|stars|\u2605|\u2b50)s?\b', re.IGNORECASE)
    _RATING_WORD_PATTERN = re.compile(
        r'\b(?:rated|rating)\s*(?:>=?\s*)?(\d)\b', re.IGNORECASE)
    _FAVORITES_PATTERN = re.compile(
        r'\bfavorit(?:e|es)\b', re.IGNORECASE)

    # Media type patterns
    _VIDEO_PATTERN = re.compile(r'\bvideos?\b', re.IGNORECASE)
    _PHOTO_PATTERN = re.compile(r'\b(?:photos?\s+only|only\s+photos?)\b', re.IGNORECASE)

    # Location patterns
    _GPS_PATTERN = re.compile(
        r'\b(?:with\s+(?:gps|location|coordinates)|geo-?tagged)\b', re.IGNORECASE)

    # Month name to number mapping
    _MONTH_MAP = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
        'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6,
        'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
        'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
    }

    @classmethod
    def parse(cls, query: str) -> Tuple[str, Dict]:
        """
        Parse a natural language query into CLIP text + metadata filters.

        Returns:
            (clip_query, filters_dict) - clip_query is the remaining text for CLIP,
            filters_dict has extracted metadata filters.
        """
        filters = {}
        remaining = query

        # Extract month+year (must check before year-only)
        m = cls._MONTH_YEAR_PATTERN.search(remaining)
        if m:
            month_name = m.group(1).lower()
            year = int(m.group(2))
            month_num = cls._MONTH_MAP.get(month_name, 1)
            import calendar
            last_day = calendar.monthrange(year, month_num)[1]
            filters["date_from"] = f"{year}-{month_num:02d}-01"
            filters["date_to"] = f"{year}-{month_num:02d}-{last_day:02d}"
            remaining = remaining[:m.start()] + remaining[m.end():]

        # Extract year
        if "date_from" not in filters:
            m = cls._YEAR_PATTERN.search(remaining)
            if m:
                year = int(m.group(1))
                if 1990 <= year <= 2099:
                    filters["date_from"] = f"{year}-01-01"
                    filters["date_to"] = f"{year}-12-31"
                    remaining = remaining[:m.start()] + remaining[m.end():]

        # Extract relative dates
        if "date_from" not in filters:
            m = cls._RELATIVE_DATE_PATTERN.search(remaining)
            if m:
                filters["_relative_date"] = m.group(1).lower().strip()
                remaining = remaining[:m.start()] + remaining[m.end():]

        # Extract rating
        m = cls._RATING_PATTERN.search(remaining)
        if m:
            filters["rating_min"] = int(m.group(1))
            remaining = remaining[:m.start()] + remaining[m.end():]
        else:
            m = cls._RATING_WORD_PATTERN.search(remaining)
            if m:
                filters["rating_min"] = int(m.group(1))
                remaining = remaining[:m.start()] + remaining[m.end():]
            elif cls._FAVORITES_PATTERN.search(remaining):
                filters["rating_min"] = 4
                remaining = cls._FAVORITES_PATTERN.sub('', remaining)

        # Extract media type
        if cls._VIDEO_PATTERN.search(remaining):
            filters["media_type"] = "video"
            remaining = cls._VIDEO_PATTERN.sub('', remaining)
        elif cls._PHOTO_PATTERN.search(remaining):
            filters["media_type"] = "photo"
            remaining = cls._PHOTO_PATTERN.sub('', remaining)

        # Extract GPS
        if cls._GPS_PATTERN.search(remaining):
            filters["has_gps"] = True
            remaining = cls._GPS_PATTERN.sub('', remaining)

        # Clean remaining text for CLIP
        remaining = re.sub(r'\s+', ' ', remaining).strip()
        # Remove dangling prepositions
        remaining = re.sub(r'\b(?:from|in|during|with|taken|shot)\s*$', '', remaining).strip()

        return remaining, filters


class SmartFindService:
    """
    Intelligent photo discovery combining CLIP + metadata.

    Reuses existing SemanticSearchService and SearchService.
    Does NOT create parallel pipelines - leverages what's already built.
    """

    def __init__(self, project_id: int):
        self.project_id = project_id
        self._semantic_service = None  # Lazy init
        self._search_service = None  # Lazy init
        self._result_cache: Dict[str, SmartFindResult] = {}
        self._cache_ttl = 300  # 5 minute cache TTL
        self._custom_presets: Optional[List[Dict]] = None  # Lazy-loaded
        self._excluded_paths: set = set()  # "Not this" exclusions for current session

    @property
    def semantic_service(self):
        """Lazy-initialize semantic search service."""
        if self._semantic_service is None:
            try:
                from services.semantic_search_service import get_semantic_search_service_for_project
                self._semantic_service = get_semantic_search_service_for_project(self.project_id)
            except Exception as e:
                logger.warning(f"[SmartFind] Semantic search not available: {e}")
        return self._semantic_service

    @property
    def search_service(self):
        """Lazy-initialize metadata search service."""
        if self._search_service is None:
            from services.search_service import SearchService
            self._search_service = SearchService()
        return self._search_service

    @property
    def clip_available(self) -> bool:
        """Check if CLIP semantic search is available."""
        svc = self.semantic_service
        return svc is not None and svc.available

    # ── Preset Access (builtin + custom merged) ──

    def get_presets(self) -> List[Dict]:
        """Get all available presets (builtin + custom)."""
        all_presets = list(BUILTIN_PRESETS)
        custom = self._load_custom_presets()
        all_presets.extend(custom)
        return all_presets

    def get_presets_by_category(self) -> Dict[str, List[Dict]]:
        """Get presets organized by category."""
        categories = {}
        for preset in self.get_presets():
            cat = preset.get("category", "other")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(preset)
        return categories

    def _lookup_preset(self, preset_id: str) -> Optional[Dict]:
        """Find a preset by ID (builtin or custom)."""
        if preset_id in _BUILTIN_LOOKUP:
            return _BUILTIN_LOOKUP[preset_id]
        # Check custom presets
        for p in self._load_custom_presets():
            if p["id"] == preset_id:
                return p
        return None

    # ── Custom Preset CRUD ──

    def _load_custom_presets(self) -> List[Dict]:
        """Load custom presets from database."""
        if self._custom_presets is not None:
            return self._custom_presets

        self._custom_presets = []
        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            with db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, name, icon, category, config_json, sort_order "
                    "FROM smart_find_presets WHERE project_id = ? ORDER BY sort_order, name",
                    (self.project_id,)
                )
                for row in cursor.fetchall():
                    config = json.loads(row['config_json'])
                    self._custom_presets.append({
                        "id": f"custom_{row['id']}",
                        "db_id": row['id'],
                        "name": row['name'],
                        "icon": row['icon'] or "\U0001f516",
                        "category": row['category'] or "custom",
                        "prompts": config.get("prompts", []),
                        "filters": config.get("filters", {}),
                        "threshold": config.get("threshold", 0.22),
                        "is_custom": True,
                    })
        except Exception as e:
            logger.warning(f"[SmartFind] Failed to load custom presets: {e}")

        return self._custom_presets

    def save_custom_preset(self, name: str, icon: str, prompts: List[str],
                           filters: Optional[Dict] = None,
                           threshold: float = 0.22,
                           category: str = "custom") -> Optional[int]:
        """
        Save a new custom preset to the database.

        Returns:
            The new preset's database ID, or None on failure.
        """
        config = {
            "prompts": prompts,
            "filters": filters or {},
            "threshold": threshold,
        }
        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            with db.get_connection() as conn:
                cursor = conn.execute(
                    "INSERT INTO smart_find_presets "
                    "(project_id, name, icon, category, config_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (self.project_id, name, icon, category, json.dumps(config))
                )
                conn.commit()
                new_id = cursor.lastrowid
                self._custom_presets = None  # Invalidate cache
                self.invalidate_cache()
                logger.info(f"[SmartFind] Saved custom preset '{name}' (id={new_id})")
                return new_id
        except Exception as e:
            logger.error(f"[SmartFind] Failed to save preset: {e}")
            return None

    def update_custom_preset(self, db_id: int, name: str, icon: str,
                             prompts: List[str], filters: Optional[Dict] = None,
                             threshold: float = 0.22,
                             category: str = "custom") -> bool:
        """Update an existing custom preset."""
        config = {
            "prompts": prompts,
            "filters": filters or {},
            "threshold": threshold,
        }
        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            with db.get_connection() as conn:
                conn.execute(
                    "UPDATE smart_find_presets SET name=?, icon=?, category=?, "
                    "config_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND project_id=?",
                    (name, icon, category, json.dumps(config), db_id, self.project_id)
                )
                conn.commit()
                self._custom_presets = None
                self.invalidate_cache()
                logger.info(f"[SmartFind] Updated preset '{name}' (id={db_id})")
                return True
        except Exception as e:
            logger.error(f"[SmartFind] Failed to update preset: {e}")
            return False

    def delete_custom_preset(self, db_id: int) -> bool:
        """Delete a custom preset."""
        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            with db.get_connection() as conn:
                conn.execute(
                    "DELETE FROM smart_find_presets WHERE id=? AND project_id=?",
                    (db_id, self.project_id)
                )
                conn.commit()
                self._custom_presets = None
                self.invalidate_cache()
                logger.info(f"[SmartFind] Deleted preset id={db_id}")
                return True
        except Exception as e:
            logger.error(f"[SmartFind] Failed to delete preset: {e}")
            return False

    def save_current_search(self, name: str, icon: str,
                            preset_id: Optional[str] = None,
                            text_query: Optional[str] = None,
                            extra_filters: Optional[Dict] = None) -> Optional[int]:
        """
        Save the current active search as a custom preset.

        Captures the full search configuration (preset prompts + refine filters).
        """
        prompts = []
        filters = extra_filters.copy() if extra_filters else {}

        if preset_id:
            source = self._lookup_preset(preset_id)
            if source:
                prompts = list(source.get("prompts", []))
                base_filters = source.get("filters", {})
                # Merge: source filters as base, extra_filters override
                merged = dict(base_filters)
                merged.update(filters)
                filters = merged
        elif text_query:
            prompts = [text_query]

        return self.save_custom_preset(name, icon, prompts, filters)

    # ── Search Execution ──

    def find_by_preset(self, preset_id: str,
                       top_k: int = 200,
                       threshold: float = 0.22,
                       extra_filters: Optional[Dict] = None) -> SmartFindResult:
        """Execute a Smart Find using a preset (builtin or custom)."""
        # Check cache
        cache_key = f"{preset_id}:{top_k}:{threshold}:{extra_filters}"
        if cache_key in self._result_cache:
            cached = self._result_cache[cache_key]
            if (time.time() - cached.execution_time_ms) < self._cache_ttl * 1000:
                return cached

        start = time.time()

        # Find preset (builtin or custom)
        preset = self._lookup_preset(preset_id)

        if not preset:
            logger.warning(f"[SmartFind] Unknown preset: {preset_id}")
            return SmartFindResult(
                paths=[], query_label=preset_id,
                total_matches=0, execution_time_ms=0
            )

        prompts = preset.get("prompts", [])
        filters = dict(preset.get("filters", {}))
        preset_threshold = preset.get("threshold", threshold)
        if extra_filters:
            filters.update(extra_filters)

        result_paths = []
        score_map = {}

        # Step 1: CLIP semantic search (if prompts exist and CLIP available)
        if prompts and self.clip_available:
            clip_results = self._run_clip_search(prompts, top_k * 2, preset_threshold)
            for path, score in clip_results:
                if path not in score_map or score > score_map[path]:
                    score_map[path] = score

        # Step 2: Apply metadata filters (SQL-based, fast)
        if filters:
            metadata_paths = self._run_metadata_filter(filters)
            if score_map:
                # Intersection: CLIP results AND metadata match
                clip_paths = set(score_map.keys())
                metadata_set = set(metadata_paths)
                final_paths = clip_paths & metadata_set
                result_paths = sorted(final_paths, key=lambda p: score_map.get(p, 0), reverse=True)
            else:
                # Metadata-only preset (e.g., "Videos", "Favorites")
                result_paths = metadata_paths
        elif score_map:
            # CLIP-only preset (e.g., "Beach", "Mountains")
            result_paths = sorted(score_map.keys(), key=lambda p: score_map[p], reverse=True)

        # Apply "Not this" exclusions
        if self._excluded_paths:
            result_paths = [p for p in result_paths if p not in self._excluded_paths]

        # Limit results
        result_paths = result_paths[:top_k]

        elapsed_ms = (time.time() - start) * 1000

        result = SmartFindResult(
            paths=result_paths,
            query_label=f"{preset.get('icon', '')} {preset['name']}",
            total_matches=len(result_paths),
            execution_time_ms=elapsed_ms,
            scores=score_map if score_map else None,
        )

        # Cache result
        self._result_cache[cache_key] = result

        logger.info(
            f"[SmartFind] Preset '{preset['name']}': {len(result_paths)} results "
            f"in {elapsed_ms:.0f}ms (CLIP={bool(prompts and self.clip_available)}, "
            f"filters={bool(filters)})"
        )

        return result

    def find_by_text(self, query: str,
                     top_k: int = 200,
                     threshold: float = 0.22,
                     extra_filters: Optional[Dict] = None) -> SmartFindResult:
        """
        Free-text Smart Find with NLP parsing.

        Parses structured metadata from the query before falling back to CLIP.
        Example: "sunset photos from 2024" -> CLIP("sunset") + date filter 2024.
        """
        start = time.time()

        # NLP: extract structured filters before CLIP
        clip_query, parsed_filters = NLQueryParser.parse(query)

        # Merge parsed filters with extra UI filters
        all_filters = dict(parsed_filters)
        if extra_filters:
            all_filters.update(extra_filters)

        # Resolve relative dates
        if "_relative_date" in all_filters:
            date_filters = self._resolve_relative_date(all_filters.pop("_relative_date"))
            all_filters.update(date_filters)

        score_map = {}

        # CLIP search on cleaned query
        if clip_query and self.clip_available:
            clip_results = self._run_clip_search([clip_query], top_k, threshold)
            for path, score in clip_results:
                score_map[path] = score

        # Apply metadata filters
        result_paths = []
        if all_filters:
            metadata_paths = self._run_metadata_filter(all_filters)
            if score_map:
                # Intersection: CLIP + metadata
                result_paths = [p for p in metadata_paths if p in score_map]
                result_paths.sort(key=lambda p: score_map.get(p, 0), reverse=True)
            else:
                result_paths = metadata_paths
        elif score_map:
            result_paths = sorted(score_map.keys(), key=lambda p: score_map[p], reverse=True)

        # Apply "Not this" exclusions
        if self._excluded_paths:
            result_paths = [p for p in result_paths if p not in self._excluded_paths]

        result_paths = result_paths[:top_k]

        elapsed_ms = (time.time() - start) * 1000

        # Build label showing what was parsed
        label_parts = [f"\U0001f50d {query}"]
        if parsed_filters:
            extracted = []
            if "date_from" in parsed_filters:
                extracted.append(f"date: {parsed_filters['date_from']}")
            if "rating_min" in parsed_filters:
                extracted.append(f"rating >= {parsed_filters['rating_min']}")
            if "media_type" in parsed_filters:
                extracted.append(parsed_filters["media_type"])
            if extracted:
                label_parts.append(f"[{', '.join(extracted)}]")

        return SmartFindResult(
            paths=result_paths,
            query_label=' '.join(label_parts),
            total_matches=len(result_paths),
            execution_time_ms=elapsed_ms,
            scores=score_map if score_map else None,
        )

    def find_combined(self, preset_ids: List[str],
                      text_query: Optional[str] = None,
                      extra_filters: Optional[Dict] = None,
                      top_k: int = 200,
                      threshold: float = 0.22) -> SmartFindResult:
        """
        Combinable filters: stack multiple presets + text + metadata.

        Intersects CLIP results from all sources, unions metadata filters.
        Example: "Beach" + "With Location" + rating >= 3
        """
        start = time.time()
        all_prompts = []
        all_metadata_filters = {}
        labels = []

        for pid in preset_ids:
            preset = self._lookup_preset(pid)
            if preset:
                all_prompts.extend(preset.get("prompts", []))
                for k, v in preset.get("filters", {}).items():
                    all_metadata_filters[k] = v
                labels.append(f"{preset.get('icon', '')} {preset['name']}")

        if text_query:
            clip_text, parsed = NLQueryParser.parse(text_query)
            if clip_text:
                all_prompts.append(clip_text)
            all_metadata_filters.update(parsed)
            if "_relative_date" in all_metadata_filters:
                date_f = self._resolve_relative_date(all_metadata_filters.pop("_relative_date"))
                all_metadata_filters.update(date_f)

        if extra_filters:
            all_metadata_filters.update(extra_filters)

        score_map = {}
        if all_prompts and self.clip_available:
            clip_results = self._run_clip_search(all_prompts, top_k * 2, threshold)
            for path, score in clip_results:
                if path not in score_map or score > score_map[path]:
                    score_map[path] = score

        result_paths = []
        if all_metadata_filters:
            metadata_paths = self._run_metadata_filter(all_metadata_filters)
            if score_map:
                result_paths = [p for p in metadata_paths if p in score_map]
                result_paths.sort(key=lambda p: score_map.get(p, 0), reverse=True)
            else:
                result_paths = metadata_paths
        elif score_map:
            result_paths = sorted(score_map.keys(), key=lambda p: score_map[p], reverse=True)

        if self._excluded_paths:
            result_paths = [p for p in result_paths if p not in self._excluded_paths]
        result_paths = result_paths[:top_k]

        elapsed_ms = (time.time() - start) * 1000
        combined_label = " + ".join(labels) if labels else "\U0001f50d Combined Search"

        return SmartFindResult(
            paths=result_paths,
            query_label=combined_label,
            total_matches=len(result_paths),
            execution_time_ms=elapsed_ms,
            scores=score_map if score_map else None,
        )

    # ── "Not This" Exclusion ──

    def exclude_path(self, path: str):
        """Exclude a photo from current results ('Not this' feature)."""
        self._excluded_paths.add(path)
        self.invalidate_cache()
        logger.info(f"[SmartFind] Excluded: {path}")

    def clear_exclusions(self):
        """Clear all 'Not this' exclusions."""
        self._excluded_paths.clear()
        self.invalidate_cache()

    # ── Search Suggestions ──

    def get_suggestions(self) -> List[Dict]:
        """
        Get search suggestions based on library content distribution.

        Returns presets with estimated match counts based on quick sampling.
        """
        suggestions = []
        for preset in BUILTIN_PRESETS:
            prompts = preset.get("prompts", [])
            filters = preset.get("filters", {})
            has_content = bool(prompts) or bool(filters)
            if has_content:
                suggestions.append({
                    "id": preset["id"],
                    "name": preset["name"],
                    "icon": preset.get("icon", ""),
                    "category": preset.get("category", "other"),
                })
        return suggestions

    # ── Internal Helpers ──

    def _resolve_relative_date(self, relative: str) -> Dict:
        """Convert relative date string to date_from/date_to filters."""
        from datetime import datetime, timedelta
        today = datetime.now().date()
        filters = {}

        rel = relative.replace(' ', '_').lower()
        if rel == "today":
            filters["date_from"] = today.strftime("%Y-%m-%d")
            filters["date_to"] = today.strftime("%Y-%m-%d")
        elif rel == "yesterday":
            yesterday = today - timedelta(days=1)
            filters["date_from"] = yesterday.strftime("%Y-%m-%d")
            filters["date_to"] = yesterday.strftime("%Y-%m-%d")
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
            first_of_month = today.replace(day=1)
            last_month_end = first_of_month - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            filters["date_from"] = last_month_start.strftime("%Y-%m-%d")
            filters["date_to"] = last_month_end.strftime("%Y-%m-%d")
        elif rel == "this_year":
            filters["date_from"] = f"{today.year}-01-01"
            filters["date_to"] = today.strftime("%Y-%m-%d")
        elif rel == "last_year":
            filters["date_from"] = f"{today.year - 1}-01-01"
            filters["date_to"] = f"{today.year - 1}-12-31"

        return filters

    def _run_clip_search(self, prompts: List[str],
                         top_k: int,
                         threshold: float) -> List[tuple]:
        """
        Run CLIP search across multiple prompts and merge results.

        Uses max-score fusion: for each photo, keep the highest score
        across all prompts. This handles synonyms naturally.

        Returns:
            List of (file_path, best_score) tuples
        """
        svc = self.semantic_service
        if not svc:
            return []

        # Collect results across all prompts
        all_scores: Dict[int, float] = {}  # photo_id -> best score
        for prompt in prompts:
            try:
                results = svc.search(
                    query=prompt,
                    top_k=top_k,
                    threshold=threshold,
                    include_metadata=False
                )
                for r in results:
                    if r.photo_id not in all_scores or r.relevance_score > all_scores[r.photo_id]:
                        all_scores[r.photo_id] = r.relevance_score
            except Exception as e:
                logger.warning(f"[SmartFind] CLIP search failed for '{prompt}': {e}")

        if not all_scores:
            return []

        # Get file paths for matched photo IDs
        path_scores = []
        try:
            from repository.base_repository import DatabaseConnection
            db = DatabaseConnection()
            photo_ids = list(all_scores.keys())
            placeholders = ','.join(['?'] * len(photo_ids))

            with db.get_connection() as conn:
                cursor = conn.execute(
                    f"SELECT id, path FROM photo_metadata WHERE id IN ({placeholders})",
                    photo_ids
                )
                for row in cursor.fetchall():
                    photo_id = row['id']
                    file_path = row['path']
                    if file_path:
                        path_scores.append((file_path, all_scores[photo_id]))
        except Exception as e:
            logger.error(f"[SmartFind] Failed to resolve photo paths: {e}")

        return path_scores

    def _run_metadata_filter(self, filters: Dict) -> List[str]:
        """
        Apply metadata filters using existing SearchService.

        Supported filter keys:
            media_type, has_gps, orientation, date_from, date_to,
            rating_min, width_min, camera_model
        """
        from services.search_service import SearchCriteria

        criteria = SearchCriteria()

        if "has_gps" in filters:
            criteria.has_gps = filters["has_gps"]

        if "orientation" in filters:
            criteria.orientation = filters["orientation"]

        if "date_from" in filters:
            criteria.date_from = filters["date_from"]

        if "date_to" in filters:
            criteria.date_to = filters["date_to"]

        if "camera_model" in filters:
            criteria.camera_model = filters["camera_model"]

        if "width_min" in filters:
            criteria.width_min = filters["width_min"]

        if "media_type" in filters:
            media_type = filters["media_type"]
            if media_type == "video":
                # Filter to video file extensions
                criteria.path_contains = None  # Will use custom logic below

        if "rating_min" in filters:
            # Rating filtering requires custom query (not in SearchCriteria)
            pass  # Handled separately below

        result = self.search_service.search(criteria)
        paths = result.paths

        # Custom: media type filtering
        if "media_type" in filters:
            media_type = filters["media_type"]
            if media_type == "video":
                video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.webm', '.m4v', '.flv'}
                paths = [p for p in paths if any(p.lower().endswith(ext) for ext in video_exts)]
            elif media_type == "photo":
                video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.webm', '.m4v', '.flv'}
                paths = [p for p in paths if not any(p.lower().endswith(ext) for ext in video_exts)]

        # Custom: rating filtering
        if "rating_min" in filters:
            rating_min = filters["rating_min"]
            try:
                from repository.base_repository import DatabaseConnection
                db = DatabaseConnection()
                with db.get_connection() as conn:
                    cursor = conn.execute(
                        "SELECT path FROM photo_metadata WHERE rating >= ? AND project_id = ?",
                        (rating_min, self.project_id)
                    )
                    rated_paths = {row['path'] for row in cursor.fetchall()}
                if paths:
                    paths = [p for p in paths if p in rated_paths]
                else:
                    paths = list(rated_paths)
            except Exception as e:
                logger.warning(f"[SmartFind] Rating filter failed: {e}")

        return paths

    def invalidate_cache(self):
        """Clear result cache (call after new photos ingested)."""
        self._result_cache.clear()
        logger.info("[SmartFind] Cache invalidated")


# Per-project service cache
_smart_find_services: Dict[int, SmartFindService] = {}


def get_smart_find_service(project_id: int) -> SmartFindService:
    """Get or create SmartFindService for a project."""
    if project_id not in _smart_find_services:
        _smart_find_services[project_id] = SmartFindService(project_id)
    return _smart_find_services[project_id]
