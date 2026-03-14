# services/candidate_builders/screenshot_candidate_builder.py
# Dedicated screenshot candidate builder for the "screenshots" preset.
#
# Extracted from DocumentCandidateBuilder._build_screenshots() to give
# screenshots their own builder with richer evidence (screenshot_score)
# that feeds into the w_screenshot scoring channel.
#
# Detection signals:
#   1. is_screenshot metadata flag (from camera/EXIF analysis)
#   2. Filename markers (screenshot, screen_shot, bildschirmfoto, etc.)
#   3. UI-text OCR patterns (battery, wifi, settings, etc.)
#   4. Page-like aspect ratio + high OCR text density
#
# Each signal contributes to a composite screenshot_score [0..1].

"""
ScreenshotCandidateBuilder - Dedicated screenshot retrieval.

Usage:
    from services.candidate_builders.screenshot_candidate_builder import (
        ScreenshotCandidateBuilder,
    )

    builder = ScreenshotCandidateBuilder(project_id=1)
    candidate_set = builder.build(intent, project_meta)
"""

from __future__ import annotations
import os
from typing import Dict, List, Set

from services.candidate_builders.base_candidate_builder import (
    BaseCandidateBuilder,
    CandidateSet,
)
from services.query_intent_planner import QueryIntent
from logging_config import get_logger

logger = get_logger(__name__)

# Screenshot filename markers
_SCREENSHOT_MARKERS = frozenset({
    "screenshot", "screen shot", "screen_shot", "screen-shot",
    "bildschirmfoto", "captura", "schermopname",
})

# UI terms for OCR-based screenshot detection
_UI_TERMS = frozenset({
    "battery", "wifi", "lte", "5g", "notification",
    "settings", "search", "cancel", "back", "menu",
    "home", "share", "download", "whatsapp", "instagram",
    "telegram", "messenger", "chrome", "safari",
})

# Page-like aspect ratio range for screenshot detection
_SCREEN_RATIO_MIN = 1.5
_SCREEN_RATIO_MAX = 2.3
_MIN_OCR_FOR_SCREEN = 30  # chars of OCR text to count as text-dense


class ScreenshotCandidateBuilder(BaseCandidateBuilder):
    """
    Retrieve screenshot candidates using multi-signal detection.

    Each candidate gets a screenshot_score [0..1] that flows into
    the w_screenshot scoring channel for ranking.
    """

    def build(
        self,
        intent: QueryIntent,
        project_meta: Dict[str, dict],
        limit: int = 500,
    ) -> CandidateSet:
        """Build screenshot candidate pool."""
        if not project_meta:
            return self._empty("type", "No project metadata available")

        text_terms = intent.text_terms or []
        candidates = []
        evidence_by_path = {}
        rejection_counts = {}

        for path, meta in project_meta.items():
            score, evidence = self._evaluate_screenshot(
                path, meta, text_terms
            )
            if score > 0.0:
                evidence["screenshot_score"] = score
                candidates.append(path)
                evidence_by_path[path] = evidence
            else:
                reason = evidence.get("rejection_reason", "not_screenshot")
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

            if len(candidates) >= limit:
                break

        # Sort by screenshot_score descending
        candidates.sort(
            key=lambda p: evidence_by_path[p].get("screenshot_score", 0),
            reverse=True,
        )

        confidence = min(1.0, 0.3 + 0.5 * (len(candidates) / max(1, len(project_meta))))

        logger.info(
            f"[ScreenshotCandidateBuilder] {len(candidates)}/{len(project_meta)} "
            f"candidates"
        )
        if rejection_counts:
            logger.info(
                f"[ScreenshotCandidateBuilder] rejections: {rejection_counts}"
            )

        return CandidateSet(
            family="type",
            candidate_paths=candidates,
            evidence_by_path=evidence_by_path,
            source_counts={"screenshot_candidates": len(candidates)},
            builder_confidence=confidence if candidates else 0.0,
            ready_state="ready" if candidates else "empty",
            notes=[f"Screenshot builder: {len(candidates)} candidates"],
            diagnostics={
                "rejections": rejection_counts,
                "pre_filter_candidates": len(project_meta),
            },
        )

    @staticmethod
    def _evaluate_screenshot(
        path: str,
        meta: dict,
        text_terms: List[str],
    ) -> tuple:
        """
        Evaluate whether a photo is a screenshot and compute score.

        Returns:
            (screenshot_score, evidence_dict)
            score=0.0 means not a screenshot candidate.
        """
        score = 0.0
        evidence = {"builder": "screenshot"}

        # Signal 1: is_screenshot metadata flag
        is_screenshot = bool(meta.get("is_screenshot"))
        if is_screenshot:
            score += 0.40
        evidence["is_screenshot_flag"] = is_screenshot

        # Signal 2: Filename markers
        basename_lower = os.path.basename(path).lower() if path else ""
        filename_marker = any(m in basename_lower for m in _SCREENSHOT_MARKERS)
        if filename_marker:
            score += 0.25
        evidence["filename_marker"] = filename_marker

        # Signal 3: UI-text OCR detection
        ocr_text = (meta.get("ocr_text") or "").lower()
        ui_term_count = sum(1 for t in _UI_TERMS if t in ocr_text) if ocr_text else 0
        ui_hit = ui_term_count >= 2  # require 2+ UI terms for stronger signal
        if ui_hit:
            score += 0.20
        elif ui_term_count == 1:
            score += 0.10
        evidence["ui_text_hit"] = ui_hit
        evidence["ui_term_count"] = ui_term_count

        # Signal 4: Screen-like aspect ratio + OCR density
        w = meta.get("width") or 0
        h = meta.get("height") or 0
        if w > 0 and h > 0:
            aspect = max(w, h) / max(1, min(w, h))
            screen_ratio = _SCREEN_RATIO_MIN <= aspect <= _SCREEN_RATIO_MAX
            ocr_dense = len(ocr_text) >= _MIN_OCR_FOR_SCREEN
            if screen_ratio and ocr_dense:
                score += 0.15
            evidence["screen_aspect_ratio"] = screen_ratio
            evidence["ocr_dense"] = ocr_dense
        else:
            evidence["screen_aspect_ratio"] = False
            evidence["ocr_dense"] = False

        # Signal 5: Text term match in OCR
        term_hit = False
        if text_terms and ocr_text:
            term_hit = any(t.lower() in ocr_text for t in text_terms)
            if term_hit:
                score += 0.05
        evidence["text_term_hit"] = term_hit
        evidence["ocr_text_len"] = len(ocr_text)

        # Cap at 1.0
        score = min(1.0, score)

        if score == 0.0:
            evidence["rejection_reason"] = "not_screenshot"

        return score, evidence
