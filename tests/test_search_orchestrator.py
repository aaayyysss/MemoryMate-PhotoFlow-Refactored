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

    def test_camera_token(self):
        plan = self.parser.parse("portraits camera:iPhone")
        assert plan.filters.get("camera_model") == "iPhone"
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
