# services/ranker.py
# Family-aware ranking profiles for search results.
#
# Different preset families use different scoring weights:
# - scenic: semantic-dominant (CLIP is primary signal)
# - type: structural/metadata-dominant (OCR, extension, dimensions)
# - people_event: face-presence is strong signal
# - utility: metadata-only (no semantic scoring)
#
# Extracted from SearchOrchestrator._score_result() to enable
# per-family weight profiles without duplicating the scoring logic.

"""
Ranker - Family-aware scoring profiles.

Usage:
    from services.ranker import Ranker

    ranker = Ranker()
    scored = ranker.score(path, clip_score, matched_prompt, meta,
                          active_filters, family="scenic")
"""

import re
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

from logging_config import get_logger
from config.ranking_config import RankingConfig

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Scoring Weights per family
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ScoringWeights:
    """
    Deterministic scoring contract.

    S = w_clip * clip + w_recency * recency + w_fav * favorite
      + w_location * location + w_face * face_match
      + w_structural * structural

    All weights are explicit, testable, and logged.
    The structural weight reserves budget for document/screenshot/scenic
    structural signals so that validate() does not normalize it away.
    """
    w_clip: float = 0.75
    w_recency: float = 0.05
    w_favorite: float = 0.08
    w_location: float = 0.04
    w_face_match: float = 0.08
    w_structural: float = 0.00  # reserved structural budget

    # Guardrails
    max_recency_boost: float = 0.10
    max_favorite_boost: float = 0.15
    recency_halflife_days: int = 90

    # Canonical mapping for validation
    _WEIGHT_TO_COMPONENT = {
        "w_clip": "clip_score",
        "w_recency": "recency_score",
        "w_favorite": "favorite_score",
        "w_location": "location_score",
        "w_face_match": "face_match_score",
        "w_structural": "structural_score",
    }

    def validate(self):
        """Ensure weights sum to ~1.0 and normalize if needed.

        Includes w_structural in the total so that profiles with a
        structural budget are not silently renormalized.
        """
        total = (self.w_clip + self.w_recency + self.w_favorite
                 + self.w_location + self.w_face_match + self.w_structural)
        if abs(total - 1.0) > 0.01:
            logger.warning(
                f"[ScoringWeights] Weights sum to {total:.3f}, not 1.0. Normalizing."
            )
            if total > 0:
                self.w_clip /= total
                self.w_recency /= total
                self.w_favorite /= total
                self.w_location /= total
                self.w_face_match /= total
                self.w_structural /= total


# ── Family-specific weight profiles ──
# Each profile must sum to 1.0 including w_structural.
# w_structural reserves budget for document/screenshot/scenic structural
# signals that are computed separately and folded into the final score.

FAMILY_WEIGHTS = {
    # Scenic: semantic is king, mild structural anti-type penalty
    "scenic": ScoringWeights(
        w_clip=0.82,
        w_recency=0.04,
        w_favorite=0.05,
        w_location=0.06,
        w_face_match=0.03,
        w_structural=0.00,  # scenic uses penalty, not positive structural
    ),
    # Type (Documents, Screenshots): structural is the dominant signal
    "type": ScoringWeights(
        w_clip=0.35,
        w_recency=0.02,
        w_favorite=0.03,
        w_location=0.00,
        w_face_match=0.00,
        w_structural=0.60,
    ),
    # People events: face presence is critical
    "people_event": ScoringWeights(
        w_clip=0.55,
        w_recency=0.03,
        w_favorite=0.04,
        w_location=0.02,
        w_face_match=0.36,
        w_structural=0.00,
    ),
    # Utility (Videos, Favorites, With Location): metadata-only
    "utility": ScoringWeights(
        w_clip=0.00,
        w_recency=0.30,
        w_favorite=0.40,
        w_location=0.20,
        w_face_match=0.10,
        w_structural=0.00,
    ),
}

# Normalize all profiles on import
for _fw in FAMILY_WEIGHTS.values():
    _fw.validate()


# ══════════════════════════════════════════════════════════════════════
# ScoredResult (shared dataclass, re-exported for convenience)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ScoredResult:
    """A single search result with full score decomposition."""
    path: str
    final_score: float = 0.0
    clip_score: float = 0.0
    recency_score: float = 0.0
    favorite_score: float = 0.0
    location_score: float = 0.0
    face_match_score: float = 0.0
    structural_score: float = 0.0
    matched_prompt: str = ""
    reasons: List[str] = field(default_factory=list)
    duplicate_count: int = 0


# ══════════════════════════════════════════════════════════════════════
# Preset Family Classification
# ══════════════════════════════════════════════════════════════════════

PRESET_FAMILIES = {
    # Type-like presets (precision-first, hard structural gates)
    "documents": "type",
    "screenshots": "type",
    "videos": "type",
    "panoramas": "type",
    "favorites": "type",
    "gps_photos": "type",
    # People-event presets (face-required)
    "wedding": "people_event",
    "party": "people_event",
    "baby": "people_event",
    "portraits": "people_event",
    # Scenic / semantic presets (recall-first, soft gates only)
    "beach": "scenic",
    "mountains": "scenic",
    "city": "scenic",
    "forest": "scenic",
    "lake": "scenic",
    "travel": "scenic",
    "sunset": "scenic",
    "sport": "scenic",
    "food": "scenic",
    "pets": "scenic",
    "flowers": "scenic",
    "snow": "scenic",
    "night": "scenic",
    "architecture": "scenic",
    "car": "scenic",
}


# ── Scenic anti-type penalty thresholds ──
# Scenic families use soft negative structural scores to demote
# assets that look type-like (document, screenshot).
SCENIC_ANTI_TYPE_PENALTIES = {
    "doc_extension": -0.30,     # .png/.pdf/.tif/.tiff/.bmp
    "high_ocr_text": -0.25,     # OCR text length > threshold
    "scan_aspect": -0.15,       # aspect ratio consistent with scan/page
}
SCENIC_OCR_TEXT_PENALTY_THRESHOLD = 50  # characters


def get_preset_family(preset_id: Optional[str]) -> str:
    """Get the preset family for gate/ranking profile selection."""
    if not preset_id:
        return "scenic"
    return PRESET_FAMILIES.get(preset_id, "scenic")


def get_weights_for_family(family: str) -> ScoringWeights:
    """Get the scoring weights for a preset family.

    The default/scenic profile reads from user preferences so weights
    are tunable in Preferences > Search & Discovery.  Other families
    use fixed profiles that are already optimized per best practices.
    """
    if family == "scenic" or family not in FAMILY_WEIGHTS:
        # Build from dynamic config (user-tunable defaults)
        return ScoringWeights(
            w_clip=RankingConfig.get_w_clip(),
            w_recency=RankingConfig.get_w_recency(),
            w_favorite=RankingConfig.get_w_favorite(),
            w_location=RankingConfig.get_w_location(),
            w_face_match=RankingConfig.get_w_face_match(),
            w_structural=RankingConfig.get_w_structural(),
            max_recency_boost=RankingConfig.get_max_recency_boost(),
            max_favorite_boost=RankingConfig.get_max_favorite_boost(),
            recency_halflife_days=RankingConfig.get_recency_halflife_days(),
        )
    return FAMILY_WEIGHTS[family]


# ══════════════════════════════════════════════════════════════════════
# People-implied detection
# ══════════════════════════════════════════════════════════════════════

_PEOPLE_IMPLIED_PRESETS = frozenset({
    "portraits", "baby", "wedding", "party",
})

_PEOPLE_IMPLIED_KEYWORDS = frozenset({
    "portrait", "portraits", "baby", "babies", "toddler", "infant",
    "wedding", "party", "celebration", "group photo", "family",
    "selfie", "people", "person", "child", "children", "kids",
})


def is_people_implied(plan: Any) -> bool:
    """Detect if a query implies people/faces."""
    preset_id = getattr(plan, 'preset_id', None)
    if preset_id and preset_id in _PEOPLE_IMPLIED_PRESETS:
        return True
    semantic_text = getattr(plan, 'semantic_text', '')
    if semantic_text:
        text_lower = semantic_text.lower()
        if any(kw in text_lower for kw in _PEOPLE_IMPLIED_KEYWORDS):
            return True
    return False


# ══════════════════════════════════════════════════════════════════════
# Ranker
# ══════════════════════════════════════════════════════════════════════

class Ranker:
    """
    Family-aware result ranker.

    Different families use different weight profiles, so a Documents
    search doesn't over-weight CLIP similarity while a Beach search does.
    """

    def __init__(self, default_family: str = "scenic"):
        self._default_family = default_family

    def score(
        self,
        path: str,
        clip_score: float,
        matched_prompt: str,
        meta: Dict[str, Any],
        active_filters: Optional[Dict] = None,
        people_implied: bool = False,
        family: Optional[str] = None,
        structural_score: float = 0.0,
    ) -> ScoredResult:
        """
        Apply the deterministic scoring contract to a single result.

        S = w_clip * clip + w_recency * recency + w_fav * favorite
          + w_location * location + w_face * face_match
          + w_structural * structural

        structural_score is computed externally (by the orchestrator) and
        passed in so it participates as a first-class weight term.
        """
        w = get_weights_for_family(family or self._default_family)
        reasons = []

        # Clip score
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
                recency = w.max_recency_boost * (
                    2.0 ** (-days_ago / max(1, w.recency_halflife_days))
                )
                if recency > 0.001:
                    reasons.append(f"recency={recency:.4f} ({days_ago}d ago)")
            except (ValueError, TypeError):
                pass

        # Favorite score
        favorite = 0.0
        flag = meta.get("flag", "none") or "none"
        rating = meta.get("rating", 0) or 0
        if flag == "pick":
            favorite = min(w.max_favorite_boost, 1.0)
            reasons.append(f"favorite={favorite:.2f} (flagged pick)")
        elif rating >= 4:
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

        # Face match score
        face_match = 0.0
        if active_filters and active_filters.get("person_id"):
            face_match = 1.0
            reasons.append(f"face=1.0 (person:{active_filters['person_id']})")
        elif people_implied:
            face_count = meta.get("face_count", 0) or 0
            if face_count > 0:
                face_match = 1.0
                reasons.append(f"face=1.0 (face_presence, {face_count} faces)")

        # Structural score (logged when non-zero)
        if structural_score != 0.0:
            reasons.append(f"structural={structural_score:.3f}")

        # Final score
        final = (
            w.w_clip * clip_score
            + w.w_recency * recency
            + w.w_favorite * favorite
            + w.w_location * location
            + w.w_face_match * face_match
            + w.w_structural * structural_score
        )

        return ScoredResult(
            path=path,
            final_score=final,
            clip_score=clip_score,
            recency_score=recency,
            favorite_score=favorite,
            location_score=location,
            face_match_score=face_match,
            structural_score=structural_score,
            matched_prompt=matched_prompt,
            reasons=reasons,
        )

    def score_many(
        self,
        candidates: list,
        project_meta: Dict[str, Dict],
        plan: Any,
        family: Optional[str] = None,
        structural_scores: Optional[Dict[str, float]] = None,
    ) -> List[ScoredResult]:
        """Score a batch of candidates using the same plan/family."""
        fam = family or get_preset_family(getattr(plan, 'preset_id', None))
        people = is_people_implied(plan)
        active_filters = getattr(plan, 'filters', None)
        struct_lookup = structural_scores or {}

        results = []
        for c in candidates:
            # c can be a tuple (path, clip_score, matched_prompt) or a ScoredResult
            if hasattr(c, 'path'):
                path = c.path
                clip_score = getattr(c, 'clip_score', 0.0)
                prompt = getattr(c, 'matched_prompt', '')
            else:
                path, clip_score, prompt = c[0], c[1], c[2]

            meta = project_meta.get(path, {})
            struct = struct_lookup.get(path, 0.0)
            sr = self.score(path, clip_score, prompt, meta,
                            active_filters, people, fam,
                            structural_score=struct)
            results.append(sr)

        results.sort(key=lambda r: r.final_score, reverse=True)
        return results
