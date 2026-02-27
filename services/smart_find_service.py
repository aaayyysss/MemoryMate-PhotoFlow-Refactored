# services/smart_find_service.py
# Smart Find Service - Combines CLIP semantic search + metadata filtering
# Inspired by iPhone/Google Photos/Lightroom/Excire discovery patterns

"""
SmartFindService - Intelligent photo discovery engine.

Combines two existing services:
- SemanticSearchService (CLIP text-to-image similarity)
- SearchService (metadata SQL filters: dates, GPS, tags, camera, etc.)

Pipeline:
1. If preset has prompts → run CLIP search across all prompts, merge results
2. If preset has metadata filters → apply SQL filters to narrow results
3. Score fusion: combine CLIP similarity + metadata match into final ranking
4. Return ordered list of file paths for grid display

Usage:
    from services.smart_find_service import SmartFindService

    service = SmartFindService(project_id=1)
    results = service.find_by_preset("beach")
    # Returns: ["/photos/img001.jpg", "/photos/img042.jpg", ...]
"""

import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from logging_config import get_logger

logger = get_logger(__name__)


# ── Builtin Presets (iPhone/Google Photos inspired categories) ──

BUILTIN_PRESETS = [
    # Places / Scenes
    {
        "id": "beach", "name": "Beach", "icon": "🏖️",
        "prompts": ["beach", "sand", "seaside", "coast", "ocean shore"],
        "category": "places",
    },
    {
        "id": "mountains", "name": "Mountains", "icon": "⛰️",
        "prompts": ["mountain", "mountain view", "peaks", "hiking trail", "mountain landscape"],
        "category": "places",
    },
    {
        "id": "city", "name": "City", "icon": "🏙️",
        "prompts": ["city skyline", "urban", "buildings", "downtown", "street view"],
        "category": "places",
    },
    {
        "id": "forest", "name": "Forest", "icon": "🌲",
        "prompts": ["forest", "trees", "woods", "nature trail", "woodland"],
        "category": "places",
    },
    {
        "id": "lake", "name": "Lake & River", "icon": "🏞️",
        "prompts": ["lake", "river", "waterfall", "pond", "stream"],
        "category": "places",
    },

    # Events / Activities
    {
        "id": "wedding", "name": "Wedding", "icon": "💒",
        "prompts": ["wedding", "bride", "wedding ceremony", "wedding dress", "wedding reception"],
        "category": "events",
    },
    {
        "id": "party", "name": "Party", "icon": "🎉",
        "prompts": ["party", "celebration", "birthday party", "gathering", "birthday cake"],
        "category": "events",
    },
    {
        "id": "travel", "name": "Travel", "icon": "✈️",
        "prompts": ["travel", "vacation", "sightseeing", "tourist attraction", "landmark"],
        "category": "events",
    },
    {
        "id": "sport", "name": "Sports", "icon": "⚽",
        "prompts": ["sport", "playing sports", "athletic activity", "game", "exercise"],
        "category": "events",
    },

    # Subjects
    {
        "id": "sunset", "name": "Sunset & Sunrise", "icon": "🌅",
        "prompts": ["sunset", "sunrise", "golden hour", "dusk sky"],
        "category": "subjects",
    },
    {
        "id": "food", "name": "Food & Drinks", "icon": "🍕",
        "prompts": ["food", "meal", "dish", "restaurant table", "cooking"],
        "category": "subjects",
    },
    {
        "id": "pets", "name": "Pets & Animals", "icon": "🐾",
        "prompts": ["dog", "cat", "pet", "puppy", "kitten", "animal"],
        "category": "subjects",
    },
    {
        "id": "baby", "name": "Baby & Kids", "icon": "👶",
        "prompts": ["baby", "infant", "toddler", "small child", "kids playing"],
        "category": "subjects",
    },
    {
        "id": "portraits", "name": "Portraits", "icon": "🖼️",
        "prompts": ["portrait", "headshot", "face close-up", "person posing"],
        "category": "subjects",
    },
    {
        "id": "flowers", "name": "Flowers & Garden", "icon": "🌸",
        "prompts": ["flowers", "garden", "blooming", "bouquet", "floral"],
        "category": "subjects",
    },
    {
        "id": "snow", "name": "Snow & Winter", "icon": "❄️",
        "prompts": ["snow", "winter", "skiing", "snowfall", "ice"],
        "category": "subjects",
    },
    {
        "id": "night", "name": "Night & Stars", "icon": "🌙",
        "prompts": ["night sky", "stars", "night photography", "moon", "city lights at night"],
        "category": "subjects",
    },
    {
        "id": "architecture", "name": "Architecture", "icon": "🏛️",
        "prompts": ["architecture", "building facade", "interior design", "monument", "church"],
        "category": "subjects",
    },
    {
        "id": "car", "name": "Cars & Vehicles", "icon": "🚗",
        "prompts": ["car", "vehicle", "automobile", "motorcycle", "truck"],
        "category": "subjects",
    },

    # Media types (metadata-only, no CLIP needed)
    {
        "id": "screenshots", "name": "Screenshots", "icon": "📱",
        "prompts": ["screenshot", "screen capture", "phone screen"],
        "category": "media",
    },
    {
        "id": "documents", "name": "Documents", "icon": "📄",
        "prompts": ["document", "text", "paper", "receipt", "handwriting"],
        "category": "media",
    },
    {
        "id": "videos", "name": "Videos", "icon": "🎬",
        "prompts": [],
        "filters": {"media_type": "video"},
        "category": "media",
    },
    {
        "id": "panoramas", "name": "Panoramas", "icon": "🌄",
        "prompts": ["panoramic view", "wide landscape"],
        "filters": {"orientation": "landscape", "width_min": 4000},
        "category": "media",
    },

    # Quality flags (metadata-only)
    {
        "id": "favorites", "name": "Favorites", "icon": "⭐",
        "prompts": [],
        "filters": {"rating_min": 4},
        "category": "quality",
    },
    {
        "id": "gps_photos", "name": "With Location", "icon": "📍",
        "prompts": [],
        "filters": {"has_gps": True},
        "category": "quality",
    },
]


@dataclass
class SmartFindResult:
    """Result from a Smart Find query."""
    paths: List[str]
    query_label: str  # Human-readable label (e.g., "Beach", "Mountains")
    total_matches: int
    execution_time_ms: float
    scores: Optional[Dict[str, float]] = None  # path -> score for ranking info


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

    def get_presets(self) -> List[Dict]:
        """Get all available presets (builtin + future custom)."""
        return list(BUILTIN_PRESETS)

    def get_presets_by_category(self) -> Dict[str, List[Dict]]:
        """Get presets organized by category."""
        categories = {}
        for preset in BUILTIN_PRESETS:
            cat = preset.get("category", "other")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(preset)
        return categories

    def find_by_preset(self, preset_id: str,
                       top_k: int = 200,
                       threshold: float = 0.22,
                       extra_filters: Optional[Dict] = None) -> SmartFindResult:
        """
        Execute a Smart Find using a preset.

        Args:
            preset_id: Preset identifier (e.g., "beach", "mountains")
            top_k: Max results to return
            threshold: CLIP similarity threshold (0.0-1.0)
            extra_filters: Additional metadata filters (date_from, date_to, has_gps, etc.)

        Returns:
            SmartFindResult with matching photo paths
        """
        # Check cache
        cache_key = f"{preset_id}:{top_k}:{threshold}:{extra_filters}"
        if cache_key in self._result_cache:
            cached = self._result_cache[cache_key]
            if (time.time() - cached.execution_time_ms) < self._cache_ttl * 1000:
                return cached

        start = time.time()

        # Find preset
        preset = None
        for p in BUILTIN_PRESETS:
            if p["id"] == preset_id:
                preset = p
                break

        if not preset:
            logger.warning(f"[SmartFind] Unknown preset: {preset_id}")
            return SmartFindResult(
                paths=[], query_label=preset_id,
                total_matches=0, execution_time_ms=0
            )

        prompts = preset.get("prompts", [])
        filters = preset.get("filters", {})
        if extra_filters:
            filters.update(extra_filters)

        result_paths = []
        score_map = {}

        # Step 1: CLIP semantic search (if prompts exist and CLIP available)
        if prompts and self.clip_available:
            clip_results = self._run_clip_search(prompts, top_k * 2, threshold)
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
                     threshold: float = 0.22) -> SmartFindResult:
        """
        Free-text Smart Find (user types their own query).

        Args:
            query: Natural language query (e.g., "dog on the beach")
            top_k: Max results
            threshold: CLIP similarity threshold

        Returns:
            SmartFindResult with matching photo paths
        """
        start = time.time()
        score_map = {}

        if self.clip_available:
            clip_results = self._run_clip_search([query], top_k, threshold)
            for path, score in clip_results:
                score_map[path] = score

        result_paths = sorted(score_map.keys(), key=lambda p: score_map[p], reverse=True)
        result_paths = result_paths[:top_k]

        elapsed_ms = (time.time() - start) * 1000

        return SmartFindResult(
            paths=result_paths,
            query_label=f"🔍 {query}",
            total_matches=len(result_paths),
            execution_time_ms=elapsed_ms,
            scores=score_map if score_map else None,
        )

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
                    include_metadata=True
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
                    f"SELECT id, file_path FROM photo_metadata WHERE id IN ({placeholders})",
                    photo_ids
                )
                for row in cursor.fetchall():
                    photo_id = row['id']
                    file_path = row['file_path']
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

        # Custom: rating filtering
        if "rating_min" in filters:
            rating_min = filters["rating_min"]
            try:
                from repository.base_repository import DatabaseConnection
                db = DatabaseConnection()
                with db.get_connection() as conn:
                    cursor = conn.execute(
                        "SELECT file_path FROM photo_metadata WHERE rating >= ? AND project_id = ?",
                        (rating_min, self.project_id)
                    )
                    rated_paths = {row['file_path'] for row in cursor.fetchall()}
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
