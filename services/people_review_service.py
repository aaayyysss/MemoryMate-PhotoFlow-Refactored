"""
UX-11A: People Review Service — business logic layer for merge and cluster decisions.

Owns the decision lifecycle:
  - Record merge accept/reject/skip with model version
  - Record cluster governance (assign, promote, ignore, low_confidence, keep_separate)
  - Filter suggestions against prior decisions
  - Invalidate stale decisions when embeddings change
  - Provide review stats for UI trust cues

Does NOT touch the database directly — delegates to PeopleMergeReviewRepository.
Does NOT execute merges — that responsibility stays with the caller (people_section).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from repository.people_merge_review_repository import (
    ClusterDecision,
    PeopleMergeReviewRepository,
    ReviewDecision,
)
from services.people_merge_engine import PeopleMergeEngine

logger = logging.getLogger(__name__)

# Sentinel for "no model version recorded"
_UNKNOWN_VERSION = ""


@dataclass
class ReviewSession:
    """Tracks stats for a single review session (dialog open→close)."""
    merged: int = 0
    rejected: int = 0
    skipped: int = 0

    @property
    def total(self) -> int:
        return self.merged + self.rejected + self.skipped

    def summary(self) -> str:
        parts = []
        if self.merged:
            parts.append(f"merged {self.merged}")
        if self.rejected:
            parts.append(f"rejected {self.rejected}")
        if self.skipped:
            parts.append(f"skipped {self.skipped}")
        return ", ".join(parts) if parts else "no decisions"


class PeopleReviewService:
    """
    UX-11A business logic for merge and cluster review decisions.

    Usage:
        repo = PeopleMergeReviewRepository(conn)
        svc = PeopleReviewService(repo)

        # During merge review dialog
        session = svc.start_session()
        svc.accept_merge(left, right, session=session)
        svc.reject_merge(left, right, session=session)
        print(session.summary())

        # Get filtered suggestions
        suggestions = svc.get_filtered_suggestions(clusters)
    """

    def __init__(self, repo: PeopleMergeReviewRepository,
                 model_version: str = ""):
        self._repo = repo
        self._model_version = model_version
        self._engine = PeopleMergeEngine()

    @property
    def model_version(self) -> str:
        return self._model_version

    @model_version.setter
    def model_version(self, value: str):
        self._model_version = value

    # ── Session tracking ──────────────────────────────────────────────

    def start_session(self) -> ReviewSession:
        """Start a new review session for stats tracking."""
        return ReviewSession()

    # ── Merge decisions ───────────────────────────────────────────────

    def accept_merge(self, left_id: str, right_id: str,
                     session: Optional[ReviewSession] = None):
        """Record an accepted merge decision."""
        self._repo.accept(left_id, right_id, self._model_version)
        logger.info("[ReviewService] Accepted merge: %s + %s (v=%s)",
                    left_id, right_id, self._model_version)
        if session:
            session.merged += 1

    def reject_merge(self, left_id: str, right_id: str,
                     session: Optional[ReviewSession] = None):
        """Record a rejected merge decision."""
        self._repo.reject(left_id, right_id, self._model_version)
        logger.info("[ReviewService] Rejected merge: %s / %s (v=%s)",
                    left_id, right_id, self._model_version)
        if session:
            session.rejected += 1

    def skip_merge(self, left_id: str, right_id: str,
                   session: Optional[ReviewSession] = None):
        """Record a skipped merge decision."""
        self._repo.skip(left_id, right_id, self._model_version)
        logger.info("[ReviewService] Skipped merge: %s ~ %s", left_id, right_id)
        if session:
            session.skipped += 1

    def get_decision(self, left_id: str, right_id: str) -> Optional[ReviewDecision]:
        """Look up the active decision for a pair."""
        return self._repo.get_decision_for_pair(left_id, right_id)

    # ── Suggestion filtering ──────────────────────────────────────────

    def get_filtered_suggestions(
        self,
        clusters: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build merge suggestions excluding already-decided pairs."""
        accepted = self._repo.get_pairs_by_decision("accepted")
        rejected = self._repo.get_pairs_by_decision("rejected")
        skipped = self._repo.get_pairs_by_decision("skipped")
        excluded = accepted | rejected | skipped
        return self._engine.build_merge_suggestions(
            clusters=clusters,
            accepted_pairs=excluded,
            rejected_pairs=set(),  # already included in excluded
        )

    # ── Cluster governance ────────────────────────────────────────────

    def assign_cluster(self, cluster_id: str, target_id: str):
        """Record that a cluster was assigned to an existing identity."""
        self._repo.set_cluster_decision(
            cluster_id, "assigned",
            target_id=target_id,
            model_version=self._model_version,
        )
        logger.info("[ReviewService] Cluster %s assigned to %s", cluster_id, target_id)

    def promote_cluster(self, cluster_id: str, new_label: str):
        """Record that a cluster was promoted to a new named identity."""
        self._repo.set_cluster_decision(
            cluster_id, "promoted",
            new_label=new_label,
            model_version=self._model_version,
        )
        logger.info("[ReviewService] Cluster %s promoted as '%s'", cluster_id, new_label)

    def ignore_cluster(self, cluster_id: str):
        """Record that a cluster was marked as ignored (not a real person)."""
        self._repo.set_cluster_decision(
            cluster_id, "ignored",
            model_version=self._model_version,
        )
        logger.info("[ReviewService] Cluster %s ignored", cluster_id)

    def mark_low_confidence(self, cluster_id: str):
        """Record that a cluster has low confidence — don't show but don't ignore."""
        self._repo.set_cluster_decision(
            cluster_id, "low_confidence",
            model_version=self._model_version,
        )
        logger.info("[ReviewService] Cluster %s marked low_confidence", cluster_id)

    def keep_separate(self, cluster_id: str):
        """Record that a cluster should remain separate (intentional)."""
        self._repo.set_cluster_decision(
            cluster_id, "keep_separate",
            model_version=self._model_version,
        )
        logger.info("[ReviewService] Cluster %s kept separate", cluster_id)

    def get_cluster_decision(self, cluster_id: str) -> Optional[ClusterDecision]:
        return self._repo.get_cluster_decision(cluster_id)

    def get_decided_cluster_ids(self) -> Set[str]:
        return self._repo.get_decided_cluster_ids()

    # ── Invalidation ──────────────────────────────────────────────────

    def invalidate_stale_decisions(self, old_model_version: str) -> int:
        """Invalidate all decisions made with an outdated model.
        Returns count of invalidated decisions."""
        count = self._repo.invalidate_by_model_version(old_model_version)
        if count:
            logger.warning(
                "[ReviewService] Invalidated %d decisions from model v=%s",
                count, old_model_version,
            )
        return count

    def invalidate_pair(self, left_id: str, right_id: str):
        """Invalidate a single pair (e.g. after undo/split)."""
        self._repo.invalidate_pair(left_id, right_id)
        logger.info("[ReviewService] Invalidated pair: %s / %s", left_id, right_id)

    def get_stale_review_count(self) -> int:
        """Return count of invalidated decisions awaiting re-review."""
        return len(self._repo.get_invalidated_decisions())

    # ── Stats / trust cues ────────────────────────────────────────────

    def get_review_stats(self) -> dict:
        """Return summary for UI trust display."""
        return self._repo.get_review_stats()

    def get_review_history(self) -> List[ReviewDecision]:
        """Return all active decisions, most recent first."""
        return self._repo.get_all_active_decisions()
