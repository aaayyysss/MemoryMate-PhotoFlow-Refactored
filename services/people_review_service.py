"""
UX-11B/C: People Review Service — queues, filtering, cluster governance.

Owns:
  - Merge review queue (read model for UI)
  - Merge candidate compare payloads
  - Unnamed cluster queue and governance (assign, keep_separate, ignore, low_confidence)
  - UI-ready payloads for dialogs

Does NOT own:
  - Identity resolution (that's IdentityResolutionService)
  - Merge execution (that stays with caller / ReferenceDB)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from models.people_review_models import (
    ClusterReviewDecisionModel,
    MergeCandidateModel,
)
from repository.identity_repository import IdentityRepository
from repository.people_review_repository import PeopleReviewRepository
from services.domain_events import (
    UNNAMED_CLUSTER_ASSIGNED,
    UNNAMED_CLUSTER_KEPT_SEPARATE,
    UNNAMED_CLUSTER_IGNORED,
    UNNAMED_CLUSTER_LOW_CONFIDENCE,
    PEOPLE_INDEX_REFRESH_REQUESTED,
    PEOPLE_REVIEW_QUEUE_REFRESH_REQUESTED,
    SEARCH_PERSON_FACETS_REFRESH_REQUESTED,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}_{short}" if prefix else short


class PeopleReviewService:
    """
    UX-11B/C: Business logic for review queues and cluster governance.
    """

    def __init__(
        self,
        people_review_repo: PeopleReviewRepository,
        identity_repo: IdentityRepository,
        event_bus=None,
    ):
        self.people_review_repo = people_review_repo
        self.identity_repo = identity_repo
        self.event_bus = event_bus

    # ── Merge review queue ────────────────────────────────────────────

    def get_merge_review_queue(
        self,
        include_reviewed: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return UI-ready merge candidate list for the review dialog."""
        if include_reviewed:
            candidates = self.people_review_repo.list_merge_candidates(
                limit=limit,
            )
        else:
            # Show unreviewed + skipped
            unreviewed = self.people_review_repo.list_merge_candidates(
                status="unreviewed", limit=limit,
            )
            skipped = self.people_review_repo.list_merge_candidates(
                status="skipped", limit=limit,
            )
            candidates = unreviewed + skipped
            if limit:
                candidates = candidates[:limit]

        return [self._to_merge_queue_item(c) for c in candidates]

    def get_merge_candidate_compare_payload(
        self, candidate_id: str,
    ) -> Dict[str, Any]:
        """Return UI-ready compare payload for a specific candidate."""
        candidate = self.people_review_repo.get_merge_candidate(candidate_id)
        if not candidate:
            return {}

        return {
            "candidate_id": candidate.candidate_id,
            "confidence_score": candidate.confidence_score,
            "confidence_band": candidate.confidence_band,
            "status": candidate.status,
            "rationale": [
                {"code": r.code, "label": r.label, "weight": r.weight}
                for r in candidate.rationale
            ],
            "cluster_a_id": candidate.cluster_a_id,
            "cluster_b_id": candidate.cluster_b_id,
            "left_cluster": self._build_cluster_panel_payload(candidate.cluster_a_id),
            "right_cluster": self._build_cluster_panel_payload(candidate.cluster_b_id),
        }

    def get_merge_queue_counts(self) -> Dict[str, int]:
        """Return counts for badge display."""
        unreviewed = self.people_review_repo.list_merge_candidates(status="unreviewed")
        skipped = self.people_review_repo.list_merge_candidates(status="skipped")
        return {
            "unreviewed": len(unreviewed),
            "skipped": len(skipped),
            "total_pending": len(unreviewed) + len(skipped),
        }

    # ── Unnamed cluster queue ─────────────────────────────────────────

    def get_unnamed_review_queue(
        self,
        include_low_value: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return unnamed clusters that need governance decisions.
        Excludes clusters with active ignore/assign decisions."""
        decided_ids = self.people_review_repo.get_decided_cluster_ids()

        # The caller should provide the cluster list from face_branch_reps.
        # This method filters and enriches.
        # For now return the decided set info for the caller to filter.
        return [{
            "decided_cluster_ids": list(decided_ids),
            "include_low_value": include_low_value,
        }]

    # ── Cluster governance ────────────────────────────────────────────

    def assign_cluster_to_existing_identity(
        self,
        cluster_id: str,
        target_identity_id: str,
        performed_by: Optional[str] = None,
    ) -> dict:
        """Assign an unnamed cluster to an existing identity."""
        # Deactivate prior decision
        self.people_review_repo.deactivate_cluster_review_decisions(cluster_id)

        decision = ClusterReviewDecisionModel(
            decision_id=_new_id("dec"),
            cluster_id=cluster_id,
            decision_type="assign_existing",
            target_identity_id=target_identity_id,
            created_at=_now_iso(),
            created_by=performed_by,
            is_active=True,
            source="user",
        )
        self.people_review_repo.save_cluster_review_decision(decision)

        # Attach cluster to identity
        self.identity_repo.attach_cluster_to_identity(
            identity_id=target_identity_id,
            cluster_id=cluster_id,
            link_type="manual_assign",
            source="user_assign",
        )

        action_id = self.identity_repo.log_identity_action(
            action_type="cluster_assigned",
            identity_id=target_identity_id,
            cluster_id=cluster_id,
            payload_json=json.dumps({"decision_type": "assign_existing"}),
            created_by=performed_by,
            is_undoable=True,
        )

        event_payload = {
            "cluster_id": cluster_id,
            "identity_id": target_identity_id,
            "decision_id": decision.decision_id,
            "action_id": action_id,
        }
        self._emit_event(UNNAMED_CLUSTER_ASSIGNED, event_payload)
        self._emit_secondary_refresh_events(
            [cluster_id], [target_identity_id], "cluster_assigned",
        )

        logger.info(
            "[ReviewService] Cluster %s assigned to identity %s",
            cluster_id, target_identity_id,
        )
        return {
            "status": "assigned",
            "identity_id": target_identity_id,
            "action_id": action_id,
        }

    def keep_cluster_as_separate_person(
        self,
        cluster_id: str,
        performed_by: Optional[str] = None,
    ) -> dict:
        """Mark cluster as intentionally separate."""
        self.people_review_repo.deactivate_cluster_review_decisions(cluster_id)

        decision = ClusterReviewDecisionModel(
            decision_id=_new_id("dec"),
            cluster_id=cluster_id,
            decision_type="keep_separate",
            created_at=_now_iso(),
            created_by=performed_by,
            is_active=True,
            source="user",
        )
        self.people_review_repo.save_cluster_review_decision(decision)

        action_id = self.identity_repo.log_identity_action(
            action_type="cluster_kept_separate",
            cluster_id=cluster_id,
            created_by=performed_by,
            is_undoable=False,
        )

        self._emit_event(UNNAMED_CLUSTER_KEPT_SEPARATE, {
            "cluster_id": cluster_id,
            "decision_id": decision.decision_id,
            "action_id": action_id,
        })

        logger.info("[ReviewService] Cluster %s kept separate", cluster_id)
        return {"status": "keep_separate", "action_id": action_id}

    def ignore_cluster(
        self,
        cluster_id: str,
        performed_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Mark cluster as ignored (not a real person)."""
        self.people_review_repo.deactivate_cluster_review_decisions(cluster_id)

        decision = ClusterReviewDecisionModel(
            decision_id=_new_id("dec"),
            cluster_id=cluster_id,
            decision_type="ignore",
            notes=notes,
            created_at=_now_iso(),
            created_by=performed_by,
            is_active=True,
            source="user",
        )
        self.people_review_repo.save_cluster_review_decision(decision)

        action_id = self.identity_repo.log_identity_action(
            action_type="cluster_ignored",
            cluster_id=cluster_id,
            payload_json=json.dumps({"notes": notes}) if notes else None,
            created_by=performed_by,
            is_undoable=False,
        )

        self._emit_event(UNNAMED_CLUSTER_IGNORED, {
            "cluster_id": cluster_id,
            "decision_id": decision.decision_id,
            "action_id": action_id,
        })

        logger.info("[ReviewService] Cluster %s ignored", cluster_id)
        return {"status": "ignored", "action_id": action_id}

    def mark_cluster_low_confidence(
        self,
        cluster_id: str,
        performed_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Mark cluster as low confidence — keep visible but lower priority."""
        self.people_review_repo.deactivate_cluster_review_decisions(cluster_id)

        decision = ClusterReviewDecisionModel(
            decision_id=_new_id("dec"),
            cluster_id=cluster_id,
            decision_type="low_confidence",
            notes=notes,
            created_at=_now_iso(),
            created_by=performed_by,
            is_active=True,
            source="user",
        )
        self.people_review_repo.save_cluster_review_decision(decision)

        action_id = self.identity_repo.log_identity_action(
            action_type="cluster_low_confidence",
            cluster_id=cluster_id,
            created_by=performed_by,
            is_undoable=False,
        )

        self._emit_event(UNNAMED_CLUSTER_LOW_CONFIDENCE, {
            "cluster_id": cluster_id,
            "decision_id": decision.decision_id,
            "action_id": action_id,
        })

        logger.info("[ReviewService] Cluster %s marked low_confidence", cluster_id)
        return {"status": "low_confidence", "action_id": action_id}

    # ── Internal helpers ──────────────────────────────────────────────

    def _to_merge_queue_item(self, candidate: MergeCandidateModel) -> dict:
        """Convert a candidate model to a UI-ready queue item."""
        return {
            "candidate_id": candidate.candidate_id,
            "cluster_a_id": candidate.cluster_a_id,
            "cluster_b_id": candidate.cluster_b_id,
            "confidence_score": candidate.confidence_score,
            "confidence_band": candidate.confidence_band,
            "status": candidate.status,
            "created_at": candidate.created_at,
            "reviewed_at": candidate.reviewed_at,
        }

    def _build_cluster_panel_payload(self, cluster_id: str) -> dict:
        """Build a UI-ready payload for one side of the compare view."""
        identity = self.identity_repo.get_identity_by_cluster_id(cluster_id)
        return {
            "cluster_id": cluster_id,
            "identity_id": identity.identity_id if identity else None,
            "display_name": identity.display_name if identity else None,
            "is_protected": identity.is_protected if identity else False,
        }

    def _emit_event(self, event_name: str, payload: dict) -> None:
        if self.event_bus and hasattr(self.event_bus, "emit"):
            try:
                self.event_bus.emit(event_name, payload)
            except Exception:
                logger.debug("[ReviewService] Event emission failed: %s",
                             event_name, exc_info=True)

    def _emit_secondary_refresh_events(
        self,
        cluster_ids: List[str],
        identity_ids: List[str],
        reason: str,
    ) -> None:
        refresh = {
            "cluster_ids": cluster_ids,
            "identity_ids": identity_ids,
            "reason": reason,
        }
        self._emit_event(PEOPLE_INDEX_REFRESH_REQUESTED, refresh)
        self._emit_event(PEOPLE_REVIEW_QUEUE_REFRESH_REQUESTED, refresh)
        self._emit_event(SEARCH_PERSON_FACETS_REFRESH_REQUESTED, refresh)
