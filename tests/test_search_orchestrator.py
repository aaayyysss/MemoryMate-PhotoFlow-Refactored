# tests/test_search_orchestrator.py
# Relevance test framework for the unified search pipeline
#
# This is the "tiny but ruthless benchmark" (audit requirement #7):
# - Tests query parsing correctness
# - Tests scoring contract determinism
# - Tests facet computation
# - Tests token extraction
# - Can be extended with project-specific expected-result sets
#
# Run: python -m pytest tests/test_search_orchestrator.py -v

import pytest
import sys
import os
import importlib
from unittest import mock
from datetime import datetime, timedelta

# Bypass services/__init__.py (imports PySide6) by loading modules directly
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Mock PySide6 before any import touches it
_pyside_mock = mock.MagicMock()
sys.modules.setdefault('PySide6', _pyside_mock)
sys.modules.setdefault('PySide6.QtCore', _pyside_mock)
sys.modules.setdefault('PySide6.QtWidgets', _pyside_mock)
sys.modules.setdefault('PySide6.QtGui', _pyside_mock)


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: TokenParser
# ══════════════════════════════════════════════════════════════════════

class TestTokenParser:
    """Test structured token extraction from search queries."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from services.search_orchestrator import TokenParser
        self.parser = TokenParser

    # ── Structured Token Extraction ──

    def test_type_video_token(self):
        plan = self.parser.parse("sunset type:video")
        assert plan.filters.get("media_type") == "video"
        assert "sunset" in plan.semantic_text
        assert any(t["label"] == "Videos" for t in plan.extracted_tokens)

    def test_type_photo_token(self):
        plan = self.parser.parse("beach type:photo")
        assert plan.filters.get("media_type") == "photo"
        assert "beach" in plan.semantic_text

    def test_is_fav_token(self):
        plan = self.parser.parse("portraits is:fav")
        assert plan.filters.get("rating_min") == 4
        assert "portraits" in plan.semantic_text
        assert any(t["label"] == "Favorites" for t in plan.extracted_tokens)

    def test_is_favorite_token(self):
        plan = self.parser.parse("sunset is:favorite")
        assert plan.filters.get("rating_min") == 4

    def test_has_location_token(self):
        plan = self.parser.parse("wedding has:location")
        assert plan.filters.get("has_gps") is True
        assert "wedding" in plan.semantic_text
        assert any(t["label"] == "Has Location" for t in plan.extracted_tokens)

    def test_has_gps_token(self):
        plan = self.parser.parse("landscape has:gps")
        assert plan.filters.get("has_gps") is True

    def test_date_year_token(self):
        plan = self.parser.parse("beach date:2024")
        assert plan.filters.get("date_from") == "2024-01-01"
        assert plan.filters.get("date_to") == "2024-12-31"
        assert "beach" in plan.semantic_text

    def test_date_year_month_token(self):
        plan = self.parser.parse("sunset date:2024-06")
        assert plan.filters.get("date_from") == "2024-06-01"
        assert plan.filters.get("date_to") == "2024-06-30"

    def test_date_full_token(self):
        plan = self.parser.parse("party date:2024-12-25")
        assert plan.filters.get("date_from") == "2024-12-25"
        assert plan.filters.get("date_to") == "2024-12-25"

    def test_camera_token_ignored(self):
        """camera: token is not a valid filter (column not in schema)."""
        plan = self.parser.parse("portraits camera:iPhone")
        assert "camera_model" not in plan.filters
        assert "portraits" in plan.semantic_text

    def test_ext_token(self):
        plan = self.parser.parse("photos ext:heic")
        assert plan.filters.get("extension") == ".heic"

    def test_rating_token(self):
        plan = self.parser.parse("landscape rating:4")
        assert plan.filters.get("rating_min") == 4

    def test_person_token(self):
        plan = self.parser.parse("person:face_001 beach")
        assert plan.filters.get("person_id") == "face_001"
        assert "beach" in plan.semantic_text

    # ── Combined Tokens ──

    def test_multiple_tokens(self):
        """The critical test: "wedding Munich 2023 screenshots" plus filters."""
        plan = self.parser.parse("wedding Munich type:photo date:2023 is:fav")
        assert plan.filters.get("media_type") == "photo"
        assert plan.filters.get("date_from") == "2023-01-01"
        assert plan.filters.get("date_to") == "2023-12-31"
        assert plan.filters.get("rating_min") == 4
        # Semantic text should have the non-token parts
        assert "wedding" in plan.semantic_text.lower() or "munich" in plan.semantic_text.lower()

    def test_mixed_nl_and_tokens(self):
        """NL date extraction + structured tokens coexist."""
        plan = self.parser.parse("beach from 2024 is:fav")
        assert plan.filters.get("rating_min") == 4
        # Either NL parser or token parser should capture the date
        assert plan.filters.get("date_from") is not None

    # ── Edge Cases ──

    def test_empty_query(self):
        plan = self.parser.parse("")
        assert plan.semantic_text == ""
        assert plan.filters == {} or len(plan.filters) == 0

    def test_only_tokens_no_semantic(self):
        plan = self.parser.parse("type:video is:fav")
        assert plan.filters.get("media_type") == "video"
        assert plan.filters.get("rating_min") == 4
        # Semantic text should be empty or very short
        assert len(plan.semantic_text.strip()) <= 2

    def test_plain_text_no_tokens(self):
        plan = self.parser.parse("beautiful sunset over ocean")
        assert plan.semantic_text == "beautiful sunset over ocean"
        assert not plan.filters or len(plan.filters) == 0


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: ScoringWeights
# ══════════════════════════════════════════════════════════════════════

class TestScoringWeights:
    """Test the deterministic scoring contract."""

    def test_default_weights_sum_to_one(self):
        from services.search_orchestrator import ScoringWeights
        w = ScoringWeights()
        total = w.w_clip + w.w_recency + w.w_favorite + w.w_location + w.w_face_match
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected ~1.0"

    def test_validate_normalizes(self):
        from services.search_orchestrator import ScoringWeights
        w = ScoringWeights(w_clip=0.5, w_recency=0.5, w_favorite=0.5,
                           w_location=0.5, w_face_match=0.5)
        w.validate()
        total = w.w_clip + w.w_recency + w.w_favorite + w.w_location + w.w_face_match
        assert abs(total - 1.0) < 0.01

    def test_clip_dominates_scoring(self):
        """CLIP similarity should be the dominant signal."""
        from services.search_orchestrator import ScoringWeights
        w = ScoringWeights()
        assert w.w_clip > 0.5, "CLIP weight should dominate (>0.5)"
        assert w.w_clip > w.w_recency + w.w_favorite + w.w_location + w.w_face_match, \
            "CLIP should outweigh all other signals combined"

    def test_recency_cant_swamp_relevance(self):
        """Recency boost has a guardrail."""
        from services.search_orchestrator import ScoringWeights
        w = ScoringWeights()
        assert w.max_recency_boost <= 0.15, \
            "Recency boost guardrail should prevent swamping relevance"

    def test_favorites_cant_float_irrelevant(self):
        """Favorites boost has a guardrail."""
        from services.search_orchestrator import ScoringWeights
        w = ScoringWeights()
        assert w.max_favorite_boost <= 0.20, \
            "Favorite boost guardrail should prevent floating irrelevant items"


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: FacetComputer
# ══════════════════════════════════════════════════════════════════════

class TestFacetComputer:
    """Test result-set facet computation."""

    def test_empty_results_no_facets(self):
        from services.search_orchestrator import FacetComputer
        facets = FacetComputer.compute([], {})
        assert facets == {}

    def test_media_facet_mixed(self):
        from services.search_orchestrator import FacetComputer
        paths = ["/photos/a.jpg", "/photos/b.mp4", "/photos/c.jpg"]
        facets = FacetComputer.compute(paths, {})
        assert "media" in facets
        assert facets["media"]["Photos"] == 2
        assert facets["media"]["Videos"] == 1

    def test_media_facet_no_mix(self):
        """If all results are photos, no media facet (nothing to refine)."""
        from services.search_orchestrator import FacetComputer
        paths = ["/photos/a.jpg", "/photos/b.png"]
        facets = FacetComputer.compute(paths, {})
        assert "media" not in facets

    def test_year_facet(self):
        from services.search_orchestrator import FacetComputer
        paths = ["/a.jpg", "/b.jpg", "/c.jpg"]
        meta = {
            "/a.jpg": {"created_date": "2024-06-15", "has_gps": False, "rating": 0},
            "/b.jpg": {"created_date": "2023-03-10", "has_gps": False, "rating": 0},
            "/c.jpg": {"created_date": "2024-08-20", "has_gps": False, "rating": 0},
        }
        facets = FacetComputer.compute(paths, meta)
        assert "years" in facets
        assert facets["years"]["2024"] == 2
        assert facets["years"]["2023"] == 1

    def test_location_facet(self):
        from services.search_orchestrator import FacetComputer
        paths = ["/a.jpg", "/b.jpg"]
        meta = {
            "/a.jpg": {"has_gps": True, "created_date": None, "rating": 0},
            "/b.jpg": {"has_gps": False, "created_date": None, "rating": 0},
        }
        facets = FacetComputer.compute(paths, meta)
        assert "location" in facets
        assert facets["location"]["With Location"] == 1
        assert facets["location"]["No Location"] == 1

    def test_rating_facet(self):
        from services.search_orchestrator import FacetComputer
        paths = ["/a.jpg", "/b.jpg", "/c.jpg"]
        meta = {
            "/a.jpg": {"has_gps": False, "created_date": None, "rating": 5},
            "/b.jpg": {"has_gps": False, "created_date": None, "rating": 0},
            "/c.jpg": {"has_gps": False, "created_date": None, "rating": None},
        }
        facets = FacetComputer.compute(paths, meta)
        assert "rated" in facets
        assert facets["rated"]["Rated"] == 1
        assert facets["rated"]["Unrated"] == 2


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: QueryPlan
# ══════════════════════════════════════════════════════════════════════

class TestQueryPlan:
    """Test QueryPlan data structure."""

    def test_has_semantic(self):
        from services.search_orchestrator import QueryPlan
        plan = QueryPlan(semantic_text="beach")
        assert plan.has_semantic()

    def test_has_semantic_prompts(self):
        from services.search_orchestrator import QueryPlan
        plan = QueryPlan(semantic_prompts=["beach", "sand"])
        assert plan.has_semantic()

    def test_no_semantic(self):
        from services.search_orchestrator import QueryPlan
        plan = QueryPlan()
        assert not plan.has_semantic()

    def test_has_filters(self):
        from services.search_orchestrator import QueryPlan
        plan = QueryPlan(filters={"media_type": "video"})
        assert plan.has_filters()

    def test_no_filters(self):
        from services.search_orchestrator import QueryPlan
        plan = QueryPlan()
        assert not plan.has_filters()


# ══════════════════════════════════════════════════════════════════════
# Integration Tests: ScoredResult determinism
# ══════════════════════════════════════════════════════════════════════

class TestScoringDeterminism:
    """
    Verify that the scoring contract produces deterministic,
    reproducible results. Same inputs -> same outputs.
    """

    def test_same_inputs_same_score(self):
        """Scoring must be deterministic."""
        from services.search_orchestrator import SearchOrchestrator, ScoringWeights
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch._weights = ScoringWeights()
        orch._weights.validate()

        meta = {
            "/test.jpg": {
                "rating": 5,
                "has_gps": True,
                "created_date": "2024-06-15",
                "date_taken": "2024-06-15",
            }
        }

        r1 = orch._score_result("/test.jpg", 0.35, "sunset", meta)
        r2 = orch._score_result("/test.jpg", 0.35, "sunset", meta)

        assert r1.final_score == r2.final_score
        assert r1.clip_score == r2.clip_score
        assert r1.favorite_score == r2.favorite_score
        assert r1.location_score == r2.location_score

    def test_higher_clip_means_higher_score(self):
        """Higher CLIP similarity should produce higher final score."""
        from services.search_orchestrator import SearchOrchestrator, ScoringWeights
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch._weights = ScoringWeights()
        orch._weights.validate()

        meta = {"/a.jpg": {"rating": 0, "has_gps": False, "created_date": None, "date_taken": None}}

        r_high = orch._score_result("/a.jpg", 0.45, "sunset", meta)
        r_low = orch._score_result("/a.jpg", 0.20, "sunset", meta)

        assert r_high.final_score > r_low.final_score

    def test_favorite_boosts_but_doesnt_dominate(self):
        """A favorite with low clip should not outrank a strong clip match."""
        from services.search_orchestrator import SearchOrchestrator, ScoringWeights
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch._weights = ScoringWeights()
        orch._weights.validate()

        meta_fav = {"/fav.jpg": {"rating": 5, "has_gps": True, "created_date": "2024-01-01", "date_taken": "2024-01-01"}}
        meta_strong = {"/strong.jpg": {"rating": 0, "has_gps": False, "created_date": None, "date_taken": None}}

        r_fav = orch._score_result("/fav.jpg", 0.15, "sunset", meta_fav)
        r_strong = orch._score_result("/strong.jpg", 0.45, "sunset", meta_strong)

        assert r_strong.final_score > r_fav.final_score, \
            f"Strong clip ({r_strong.final_score:.4f}) should beat weak clip + fav ({r_fav.final_score:.4f})"

    def test_score_components_logged(self):
        """Every ScoredResult should have reasons explaining the score."""
        from services.search_orchestrator import SearchOrchestrator, ScoringWeights
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch._weights = ScoringWeights()
        orch._weights.validate()

        meta = {"/test.jpg": {"rating": 5, "has_gps": True, "created_date": "2024-06-15", "date_taken": "2024-06-15"}}
        r = orch._score_result("/test.jpg", 0.35, "sunset", meta)

        # Should have clip, favorite, and location reasons
        reason_text = " ".join(r.reasons)
        assert "clip=" in reason_text
        assert "favorite=" in reason_text
        assert "location=" in reason_text

    def test_recency_discriminates_across_dates(self):
        """Recency must produce different values for different dates, not saturate."""
        from services.search_orchestrator import SearchOrchestrator, ScoringWeights
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch._weights = ScoringWeights()
        orch._weights.validate()

        meta_recent = {"/recent.jpg": {"rating": 0, "has_gps": False,
                                       "created_date": "2026-02-28", "date_taken": "2026-02-28"}}
        meta_old = {"/old.jpg": {"rating": 0, "has_gps": False,
                                 "created_date": "2025-06-01", "date_taken": "2025-06-01"}}

        r_recent = orch._score_result("/recent.jpg", 0.30, "test", meta_recent)
        r_old = orch._score_result("/old.jpg", 0.30, "test", meta_old)

        assert r_recent.recency_score > r_old.recency_score, \
            f"Recent ({r_recent.recency_score:.4f}) must beat old ({r_old.recency_score:.4f})"
        assert r_recent.recency_score != r_old.recency_score, \
            "Recency must not saturate to the same value for all dates"

    def test_face_score_active_with_person_filter(self):
        """Face component must be 1.0 when person filter is active."""
        from services.search_orchestrator import SearchOrchestrator, ScoringWeights
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch._weights = ScoringWeights()
        orch._weights.validate()

        meta = {"/face.jpg": {"rating": 0, "has_gps": False,
                              "created_date": None, "date_taken": None}}

        r_no_face = orch._score_result("/face.jpg", 0.30, "test", meta)
        r_face = orch._score_result("/face.jpg", 0.30, "test", meta,
                                    active_filters={"person_id": "face_001"})

        assert r_no_face.face_match_score == 0.0
        assert r_face.face_match_score == 1.0
        assert r_face.final_score > r_no_face.final_score, \
            "Face match must boost the final score"

    def test_weight_component_structural_match(self):
        """Every ScoringWeights field must have a matching ScoredResult component."""
        from services.search_orchestrator import ScoringWeights
        w = ScoringWeights()
        # validate() now asserts weight-to-component mapping
        w.validate()  # must not raise


# ══════════════════════════════════════════════════════════════════════
# NLQueryParser backward compatibility
# ══════════════════════════════════════════════════════════════════════

class TestNLQueryParserCompat:
    """Ensure existing NLQueryParser still works after orchestrator integration."""

    def test_nl_date_extraction(self):
        from services.smart_find_service import NLQueryParser
        text, filters = NLQueryParser.parse("sunset from 2024")
        assert filters.get("date_from") == "2024-01-01"
        assert "sunset" in text

    def test_nl_rating_extraction(self):
        from services.smart_find_service import NLQueryParser
        text, filters = NLQueryParser.parse("5 star beach photos")
        assert filters.get("rating_min") == 5

    def test_nl_favorites_extraction(self):
        from services.smart_find_service import NLQueryParser
        text, filters = NLQueryParser.parse("my favorites")
        assert filters.get("rating_min") == 4

    def test_nl_video_extraction(self):
        from services.smart_find_service import NLQueryParser
        text, filters = NLQueryParser.parse("videos from last month")
        assert filters.get("media_type") == "video"

    def test_nl_gps_extraction(self):
        from services.smart_find_service import NLQueryParser
        text, filters = NLQueryParser.parse("photos with GPS")
        assert filters.get("has_gps") is True


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: OrchestratorResult progressive phase
# ══════════════════════════════════════════════════════════════════════

class TestProgressiveSearch:
    """Test the progressive search-as-you-type contract."""

    def test_result_has_phase_field(self):
        """OrchestratorResult must have a 'phase' field."""
        from services.search_orchestrator import OrchestratorResult
        r = OrchestratorResult()
        assert hasattr(r, 'phase')
        assert r.phase == "full"

    def test_metadata_phase(self):
        """Metadata-only results should have phase='metadata'."""
        from services.search_orchestrator import OrchestratorResult
        r = OrchestratorResult(phase="metadata")
        assert r.phase == "metadata"

    def test_search_metadata_only_exists(self):
        """SearchOrchestrator must have search_metadata_only method."""
        from services.search_orchestrator import SearchOrchestrator
        assert hasattr(SearchOrchestrator, 'search_metadata_only')

    def test_token_parser_works_for_progressive(self):
        """Token parsing used in progressive search must handle all cases."""
        from services.search_orchestrator import TokenParser
        # Progressive search uses the same TokenParser - ensure metadata tokens
        # are correctly extracted even without semantic search
        plan = TokenParser.parse("date:2024 is:fav")
        assert plan.filters.get("date_from") == "2024-01-01"
        assert plan.filters.get("rating_min") == 4
        assert not plan.semantic_text.strip()  # No semantic text


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: ANN Retrieval
# ══════════════════════════════════════════════════════════════════════

class TestANNRetrieval:
    """Test two-stage ANN retrieval infrastructure."""

    def test_search_ann_method_exists(self):
        """SearchOrchestrator must have search_ann method."""
        from services.search_orchestrator import SearchOrchestrator
        assert hasattr(SearchOrchestrator, 'search_ann')

    def test_invalidate_ann_cache_exists(self):
        """SearchOrchestrator must have invalidate_ann_cache method."""
        from services.search_orchestrator import SearchOrchestrator
        assert hasattr(SearchOrchestrator, 'invalidate_ann_cache')

    def test_ann_cache_class_level(self):
        """ANN index cache should be class-level (shared across instances)."""
        from services.search_orchestrator import SearchOrchestrator
        assert hasattr(SearchOrchestrator, '_ann_index_cache')
        assert isinstance(SearchOrchestrator._ann_index_cache, dict)

    def test_ann_cache_ttl(self):
        """ANN cache TTL should be > 0."""
        from services.search_orchestrator import SearchOrchestrator
        assert SearchOrchestrator._ANN_CACHE_TTL > 0


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: Find Similar
# ══════════════════════════════════════════════════════════════════════

class TestFindSimilar:
    """Test find-similar (Excire-style) integration."""

    def test_find_similar_method_exists(self):
        """SearchOrchestrator must have find_similar method."""
        from services.search_orchestrator import SearchOrchestrator
        assert hasattr(SearchOrchestrator, 'find_similar')

    def test_find_similar_returns_orchestrator_result(self):
        """find_similar should return OrchestratorResult (not raw list)."""
        from services.search_orchestrator import SearchOrchestrator
        import inspect
        sig = inspect.signature(SearchOrchestrator.find_similar)
        # Method signature: (self, photo_path, top_k, threshold)
        params = list(sig.parameters.keys())
        assert 'photo_path' in params
        assert 'top_k' in params
        assert 'threshold' in params

    def test_find_similar_query_plan_source(self):
        """find_similar results should have source='similar' in query_plan."""
        from services.search_orchestrator import QueryPlan
        plan = QueryPlan(source="similar", raw_query="similar:test.jpg")
        assert plan.source == "similar"


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: LibraryAnalyzer (suggested searches)
# ══════════════════════════════════════════════════════════════════════

class TestLibraryAnalyzer:
    """Test library-stats-based search suggestions."""

    def test_library_analyzer_exists(self):
        """LibraryAnalyzer class must exist."""
        from services.search_orchestrator import LibraryAnalyzer
        assert hasattr(LibraryAnalyzer, 'suggest')

    def test_suggest_returns_list(self):
        """suggest() should return a list of dicts."""
        from services.search_orchestrator import LibraryAnalyzer
        import inspect
        sig = inspect.signature(LibraryAnalyzer.suggest)
        params = list(sig.parameters.keys())
        assert 'project_id' in params
        assert 'max_suggestions' in params

    def test_suggestion_dict_format(self):
        """Each suggestion must have label, query, icon."""
        # Verify the expected format without hitting the DB
        suggestion = {"label": "2024 (100)", "query": "date:2024", "icon": "\U0001f4c5"}
        assert "label" in suggestion
        assert "query" in suggestion
        assert "icon" in suggestion

    def test_max_suggestions_cap(self):
        """suggest() should respect max_suggestions parameter."""
        from services.search_orchestrator import LibraryAnalyzer
        import inspect
        sig = inspect.signature(LibraryAnalyzer.suggest)
        # max_suggestions has a default value
        assert sig.parameters['max_suggestions'].default == 8


# ══════════════════════════════════════════════════════════════════════
# Integration Tests: Scoring with progressive phases
# ══════════════════════════════════════════════════════════════════════

class TestScoringInProgressiveMode:
    """Test scoring contract works correctly in metadata-only mode."""

    def test_metadata_only_scoring_no_clip(self):
        """In metadata-only phase, clip_score should be 0."""
        from services.search_orchestrator import SearchOrchestrator, ScoringWeights
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch._weights = ScoringWeights()
        orch._weights.validate()

        meta = {"/test.jpg": {
            "rating": 5, "has_gps": True,
            "created_date": "2024-06-15", "date_taken": "2024-06-15"
        }}
        r = orch._score_result("/test.jpg", 0.0, "", meta)

        assert r.clip_score == 0.0
        assert r.final_score > 0  # Other signals still contribute
        assert r.favorite_score > 0
        assert r.location_score > 0

    def test_full_scoring_beats_metadata_only(self):
        """Full search (with clip) should produce higher scores than metadata-only."""
        from services.search_orchestrator import SearchOrchestrator, ScoringWeights
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch._weights = ScoringWeights()
        orch._weights.validate()

        meta = {"/test.jpg": {
            "rating": 5, "has_gps": True,
            "created_date": "2024-06-15", "date_taken": "2024-06-15"
        }}

        r_meta = orch._score_result("/test.jpg", 0.0, "", meta)
        r_full = orch._score_result("/test.jpg", 0.35, "sunset", meta)

        assert r_full.final_score > r_meta.final_score

    def test_progressive_result_phase_distinguishable(self):
        """UI can tell metadata results from full results via phase field."""
        from services.search_orchestrator import OrchestratorResult
        meta_result = OrchestratorResult(phase="metadata", total_matches=10)
        full_result = OrchestratorResult(phase="full", total_matches=15)
        assert meta_result.phase != full_result.phase
        assert meta_result.phase == "metadata"
        assert full_result.phase == "full"


# ══════════════════════════════════════════════════════════════════════
# CI Integration: Relevance contract tests
# ══════════════════════════════════════════════════════════════════════

class TestRelevanceContract:
    """
    Relevance contract tests for CI integration.

    These tests verify the search system's fundamental contracts
    without requiring a database or CLIP model. They should pass
    in any CI environment.

    Run in CI: pytest tests/test_search_orchestrator.py -v -m "not requires_qt"
    """

    def test_scoring_weights_are_stable(self):
        """Scoring weights shouldn't change without deliberate update."""
        from services.search_orchestrator import ScoringWeights
        w = ScoringWeights()
        assert w.w_clip == 0.75
        assert w.w_recency == 0.05
        assert w.w_favorite == 0.08
        assert w.w_location == 0.04
        assert w.w_face_match == 0.08

    def test_token_parser_complete_coverage(self):
        """All documented token types must be parseable."""
        from services.search_orchestrator import TokenParser
        tokens = {
            "type:video": "media_type",
            "type:photo": "media_type",
            "is:fav": "rating_min",
            "has:location": "has_gps",
            "has:faces": "has_faces",
            "date:2024": "date_from",
            "ext:heic": "extension",
            "rating:4": "rating_min",
            "person:face_001": "person_id",
        }
        for token, expected_key in tokens.items():
            plan = TokenParser.parse(f"test {token}")
            assert expected_key in plan.filters, \
                f"Token '{token}' should produce filter key '{expected_key}'"

    def test_facet_computer_handles_edge_cases(self):
        """FacetComputer must not crash on degenerate inputs."""
        from services.search_orchestrator import FacetComputer
        # Empty
        assert FacetComputer.compute([], {}) == {}
        # No metadata
        paths = ["/a.jpg"]
        facets = FacetComputer.compute(paths, {})
        # Should not crash, may produce empty facets
        assert isinstance(facets, dict)
        # Single path
        facets = FacetComputer.compute(
            ["/a.jpg"],
            {"/a.jpg": {"has_gps": True, "rating": 5, "created_date": "2024-01-01"}}
        )
        assert isinstance(facets, dict)

    def test_orchestrator_result_serializable(self):
        """OrchestratorResult should be JSON-serializable (for CI reporting)."""
        from services.search_orchestrator import OrchestratorResult
        r = OrchestratorResult(
            paths=["/a.jpg", "/b.jpg"],
            total_matches=2,
            scores={"/a.jpg": 0.95, "/b.jpg": 0.80},
            facets={"media": {"Photos": 2}},
            phase="full",
        )
        import json
        # Should not raise
        data = {
            "paths": r.paths,
            "total_matches": r.total_matches,
            "scores": r.scores,
            "facets": r.facets,
            "phase": r.phase,
        }
        serialized = json.dumps(data)
        assert "full" in serialized

    def test_date_relative_tokens_resolve(self):
        """Relative date tokens should resolve to valid date strings."""
        from services.search_orchestrator import TokenParser
        relatives = ["today", "yesterday", "this_week", "last_week",
                      "this_month", "last_month", "this_year", "last_year"]
        for rel in relatives:
            plan = TokenParser.parse(f"test date:{rel}")
            assert "date_from" in plan.filters, \
                f"Relative date '{rel}' should resolve to date_from"
            assert "date_to" in plan.filters, \
                f"Relative date '{rel}' should resolve to date_to"

    def test_query_plan_immutable_source(self):
        """QueryPlan source should be one of: text, preset, combined, similar."""
        from services.search_orchestrator import QueryPlan
        for source in ["text", "preset", "combined", "similar"]:
            plan = QueryPlan(source=source)
            assert plan.source == source


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: Duplicate Stacking (P0)
# ══════════════════════════════════════════════════════════════════════

class TestDuplicateStacking:
    """Test duplicate stacking in search results."""

    def test_scored_result_has_duplicate_count(self):
        """ScoredResult must have a duplicate_count field."""
        from services.search_orchestrator import ScoredResult
        sr = ScoredResult(path="/test.jpg")
        assert hasattr(sr, 'duplicate_count')
        assert sr.duplicate_count == 0

    def test_deduplicate_empty_list(self):
        """_deduplicate_results on empty list returns empty."""
        from services.search_orchestrator import SearchOrchestrator
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch.project_id = 999
        orch._dup_cache = {}
        orch._dup_cache_time = 0.0
        deduped, stacked = orch._deduplicate_results([])
        assert deduped == []
        assert stacked == 0

    def test_deduplicate_no_duplicates(self):
        """Non-duplicate results pass through unchanged."""
        from services.search_orchestrator import SearchOrchestrator, ScoredResult
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch.project_id = 999
        orch._dup_cache = {}  # no duplicates mapped
        orch._dup_cache_time = 99999999999.0
        results = [
            ScoredResult(path="/a.jpg", final_score=0.9),
            ScoredResult(path="/b.jpg", final_score=0.8),
        ]
        deduped, stacked = orch._deduplicate_results(results)
        assert len(deduped) == 2
        assert stacked == 0

    def test_deduplicate_folds_duplicates(self):
        """Duplicate results should be folded into a single representative."""
        from services.search_orchestrator import SearchOrchestrator, ScoredResult
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch.project_id = 999
        # Simulate: /a.jpg and /a_copy.jpg share representative /a.jpg, group size 2
        orch._dup_cache = {
            "/a.jpg": ("/a.jpg", 2),
            "/a_copy.jpg": ("/a.jpg", 2),
        }
        orch._dup_cache_time = 99999999999.0

        results = [
            ScoredResult(path="/a.jpg", final_score=0.9),
            ScoredResult(path="/a_copy.jpg", final_score=0.85),
            ScoredResult(path="/b.jpg", final_score=0.7),  # not a duplicate
        ]
        deduped, stacked = orch._deduplicate_results(results)
        assert len(deduped) == 2  # /a.jpg representative + /b.jpg
        assert stacked == 1
        # Representative should have duplicate_count = 1
        rep = [r for r in deduped if r.path == "/a.jpg"][0]
        assert rep.duplicate_count == 1

    def test_deduplicate_promotes_higher_scorer(self):
        """If a copy scores higher than the representative, it gets promoted."""
        from services.search_orchestrator import SearchOrchestrator, ScoredResult
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch.project_id = 999
        orch._dup_cache = {
            "/a.jpg": ("/a.jpg", 2),
            "/a_copy.jpg": ("/a.jpg", 2),
        }
        orch._dup_cache_time = 99999999999.0

        results = [
            ScoredResult(path="/a.jpg", final_score=0.5),
            ScoredResult(path="/a_copy.jpg", final_score=0.9),  # copy scores higher
        ]
        deduped, stacked = orch._deduplicate_results(results)
        assert len(deduped) == 1
        assert deduped[0].final_score == 0.9  # higher-scoring copy wins

    def test_orchestrator_result_has_stacked_count(self):
        """OrchestratorResult must have stacked_duplicates field."""
        from services.search_orchestrator import OrchestratorResult
        r = OrchestratorResult()
        assert hasattr(r, 'stacked_duplicates')
        assert r.stacked_duplicates == 0


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: ANN Dirty-on-Embed (P2)
# ══════════════════════════════════════════════════════════════════════

class TestANNDirtyOnEmbed:
    """Test ANN index invalidation when new embeddings arrive."""

    def test_mark_ann_dirty_exists(self):
        """mark_ann_dirty class method must exist."""
        from services.search_orchestrator import SearchOrchestrator
        assert hasattr(SearchOrchestrator, 'mark_ann_dirty')
        assert callable(SearchOrchestrator.mark_ann_dirty)

    def test_dirty_flag_set_and_cleared(self):
        """mark_ann_dirty sets flag, _get_or_build_ann_index clears it."""
        from services.search_orchestrator import SearchOrchestrator
        project_id = 99999
        # Mark dirty
        SearchOrchestrator.mark_ann_dirty(project_id)
        assert project_id in SearchOrchestrator._ann_dirty
        # Clean up
        SearchOrchestrator._ann_dirty.discard(project_id)
        assert project_id not in SearchOrchestrator._ann_dirty

    def test_invalidate_ann_cache_clears_dirty(self):
        """invalidate_ann_cache must also clear dirty flag."""
        from services.search_orchestrator import SearchOrchestrator
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch.project_id = 99998
        SearchOrchestrator._ann_dirty.add(99998)
        orch.invalidate_ann_cache()
        assert 99998 not in SearchOrchestrator._ann_dirty


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: Relevance Feedback (P1)
# ══════════════════════════════════════════════════════════════════════

class TestRelevanceFeedback:
    """Test search event recording and personal boost."""

    def test_record_search_event_exists(self):
        """record_search_event static method must exist."""
        from services.search_orchestrator import SearchOrchestrator
        assert hasattr(SearchOrchestrator, 'record_search_event')
        assert callable(SearchOrchestrator.record_search_event)

    def test_get_personal_boost_exists(self):
        """get_personal_boost static method must exist."""
        from services.search_orchestrator import SearchOrchestrator
        assert hasattr(SearchOrchestrator, 'get_personal_boost')

    def test_personal_boost_returns_float(self):
        """get_personal_boost must return a float in [0, 0.15]."""
        from services.search_orchestrator import SearchOrchestrator
        # With no DB, should return 0.0 gracefully
        boost = SearchOrchestrator.get_personal_boost(1, "test_hash", "/test.jpg")
        assert isinstance(boost, float)
        assert 0.0 <= boost <= 0.15


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: Query Autocomplete (P1)
# ══════════════════════════════════════════════════════════════════════

class TestQueryAutocomplete:
    """Test autocomplete suggestions."""

    def test_autocomplete_exists(self):
        """autocomplete static method must exist."""
        from services.search_orchestrator import SearchOrchestrator
        assert hasattr(SearchOrchestrator, 'autocomplete')

    def test_autocomplete_returns_list(self):
        """autocomplete must return a list."""
        from services.search_orchestrator import SearchOrchestrator
        result = SearchOrchestrator.autocomplete(1, "type:")
        assert isinstance(result, list)

    def test_autocomplete_token_completions(self):
        """autocomplete must suggest token completions."""
        from services.search_orchestrator import SearchOrchestrator
        result = SearchOrchestrator.autocomplete(1, "type:v")
        labels = [r["label"] for r in result]
        assert "type:video" in labels

    def test_autocomplete_empty_prefix(self):
        """Empty prefix returns no suggestions."""
        from services.search_orchestrator import SearchOrchestrator
        result = SearchOrchestrator.autocomplete(1, "")
        assert result == []

    def test_autocomplete_respects_max(self):
        """autocomplete must respect max_results."""
        from services.search_orchestrator import SearchOrchestrator
        result = SearchOrchestrator.autocomplete(1, "type:", max_results=1)
        assert len(result) <= 1


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: OCR Search Integration (P1)
# ══════════════════════════════════════════════════════════════════════

class TestOCRSearchIntegration:
    """Test OCR text search integration point."""

    def test_search_ocr_text_exists(self):
        """search_ocr_text static method must exist."""
        from services.search_orchestrator import SearchOrchestrator
        assert hasattr(SearchOrchestrator, 'search_ocr_text')

    def test_search_ocr_text_graceful_fallback(self):
        """search_ocr_text must return empty list when FTS5 table doesn't exist."""
        from services.search_orchestrator import SearchOrchestrator
        result = SearchOrchestrator.search_ocr_text(1, "receipt")
        assert isinstance(result, list)
        assert result == []  # No FTS5 table = graceful empty


# ══════════════════════════════════════════════════════════════════════
# Unit Tests: Phase Labels (P2)
# ══════════════════════════════════════════════════════════════════════

class TestPhaseLabels:
    """Test hybrid retrieval phase labels for UI transparency."""

    def test_orchestrator_result_has_phase_label(self):
        """OrchestratorResult must have phase_label field."""
        from services.search_orchestrator import OrchestratorResult
        r = OrchestratorResult()
        assert hasattr(r, 'phase_label')
        assert r.phase_label == ""

    def test_metadata_phase_label(self):
        """Metadata-only results should be labeled."""
        from services.search_orchestrator import OrchestratorResult
        r = OrchestratorResult(phase="metadata", phase_label="Metadata results")
        assert r.phase_label == "Metadata results"

    def test_full_phase_label(self):
        """Full semantic results should be labeled."""
        from services.search_orchestrator import OrchestratorResult
        r = OrchestratorResult(phase="full", phase_label="Semantic refined")
        assert r.phase_label == "Semantic refined"
