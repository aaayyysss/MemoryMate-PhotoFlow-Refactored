"""
UX-11B: Identity Resolution Service — single authoritative source for identity membership.

This is the most important service in the UX-11 package.

Responsibilities:
  - Resolve a cluster/branch key to its canonical identity
  - Accept/reject/skip merge candidates with non-destructive semantics
  - Reverse merges (undo) by deactivating links, not deleting data
  - Detach clusters from identities
  - Protect/unprotect identities
  - Emit domain events for cross-system coherence

Merge acceptance does NOT destructively replace clusters.
Instead it attaches the secondary cluster to the target identity via link.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.people_review_models import (
    IdentitySnapshot,
    MergeCandidateModel,
    PersonIdentityModel,
)
from repository.identity_repository import IdentityRepository
from repository.people_review_repository import PeopleReviewRepository
from services.domain_events import (
    MERGE_CANDIDATE_ACCEPTED,
    MERGE_CANDIDATE_REJECTED,
    MERGE_CANDIDATE_SKIPPED,
    MERGE_REVERSED,
    IDENTITY_CLUSTER_DETACHED,
    IDENTITY_PROTECTED,
    IDENTITY_UNPROTECTED,
    PEOPLE_INDEX_REFRESH_REQUESTED,
    PEOPLE_SIDEBAR_REFRESH_REQUESTED,
    PEOPLE_REVIEW_QUEUE_REFRESH_REQUESTED,
    SEARCH_PERSON_FACETS_REFRESH_REQUESTED,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IdentityResolutionService:
    """
    UX-11B: Single authoritative source for identity membership.

    Combines the durable identity layer (person_identity + identity_cluster_link)
    with the merge candidate lifecycle to provide a consistent view for
    search, sidebar, and merge dialogs.
    """

    def __init__(
        self,
        identity_repo: IdentityRepository,
        people_review_repo: PeopleReviewRepository,
        event_bus=None,
    ):
        self.identity_repo = identity_repo
        self.people_review_repo = people_review_repo
        self.event_bus = event_bus  # Qt signal hub or None

    # ── Identity resolution ───────────────────────────────────────────

    def ensure_identity_for_cluster(
        self, cluster_id: str, source: str = "system",
    ) -> str:
        """Ensure a cluster has a durable identity. Create one if missing."""
        existing = self.identity_repo.get_identity_by_cluster_id(cluster_id)
        if existing:
            return existing.identity_id

        identity_id = self.identity_repo.create_identity(
            canonical_cluster_id=cluster_id,
            source=source,
        )
        self.identity_repo.attach_cluster_to_identity(
            identity_id=identity_id,
            cluster_id=cluster_id,
            link_type="canonical",
            source=source,
        )
        return identity_id

    def get_identity_for_cluster(
        self, cluster_id: str,
    ) -> Optional[PersonIdentityModel]:
        return self.identity_repo.get_identity_by_cluster_id(cluster_id)

    def get_identity_snapshot(
        self, identity_id: str,
    ) -> Optional[IdentitySnapshot]:
        identity = self.identity_repo.get_identity(identity_id)
        if not identity:
            return None
        cluster_ids = self.identity_repo.get_cluster_ids_for_identity(identity_id)
        badges = self._compute_badges(identity)
        return IdentitySnapshot(
            identity=identity,
            cluster_ids=cluster_ids,
            badges=badges,
        )

    # ── Merge candidate actions ───────────────────────────────────────

    def accept_merge_candidate(
        self,
        candidate_id: str,
        reviewed_by: Optional[str] = None,
    ) -> dict:
        """Accept a merge candidate — non-destructive identity attachment."""
        candidate = self.people_review_repo.get_merge_candidate(candidate_id)
        if not candidate:
            raise ValueError(f"Unknown merge candidate: {candidate_id}")
        if candidate.status not in ("unreviewed", "skipped"):
            raise ValueError(
                f"Candidate {candidate_id} not mergeable from status={candidate.status}"
            )

        identity_a = self.identity_repo.get_identity_by_cluster_id(candidate.cluster_a_id)
        identity_b = self.identity_repo.get_identity_by_cluster_id(candidate.cluster_b_id)

        # Already same identity
        if (identity_a and identity_b
                and identity_a.identity_id == identity_b.identity_id):
            self.people_review_repo.update_merge_candidate_status(
                candidate_id,
                status="invalidated",
                reviewed_at=_now_iso(),
                reviewed_by=reviewed_by,
                invalidated_reason="already_same_identity",
            )
            return {"status": "already_same_identity"}

        # Determine target identity and secondary cluster
        if identity_a and not identity_b:
            target_identity_id = identity_a.identity_id
            secondary_cluster_id = candidate.cluster_b_id
        elif identity_b and not identity_a:
            target_identity_id = identity_b.identity_id
            secondary_cluster_id = candidate.cluster_a_id
        elif identity_a and identity_b:
            target_identity_id = self._select_primary_identity(
                identity_a, identity_b
            )
            secondary_cluster_id = (
                candidate.cluster_b_id
                if target_identity_id == identity_a.identity_id
                else candidate.cluster_a_id
            )
        else:
            # Neither cluster has an identity — create one
            target_identity_id = self.identity_repo.create_identity(
                canonical_cluster_id=candidate.cluster_a_id,
                source="merge_accept",
            )
            self.identity_repo.attach_cluster_to_identity(
                identity_id=target_identity_id,
                cluster_id=candidate.cluster_a_id,
                link_type="canonical",
                source="merge_accept",
            )
            secondary_cluster_id = candidate.cluster_b_id

        # Attach secondary cluster to target identity
        self.identity_repo.attach_cluster_to_identity(
            identity_id=target_identity_id,
            cluster_id=secondary_cluster_id,
            link_type="merged_into_identity",
            source="merge_accept",
        )

        # Log the action
        payload = json.dumps({
            "candidate_id": candidate_id,
            "cluster_a_id": candidate.cluster_a_id,
            "cluster_b_id": candidate.cluster_b_id,
            "secondary_cluster_id": secondary_cluster_id,
            "confidence_score": candidate.confidence_score,
        })
        action_id = self.identity_repo.log_identity_action(
            action_type="merge_accepted",
            identity_id=target_identity_id,
            related_cluster_id=secondary_cluster_id,
            candidate_id=candidate_id,
            payload_json=payload,
            created_by=reviewed_by,
            is_undoable=True,
        )

        # Update candidate status
        self.people_review_repo.update_merge_candidate_status(
            candidate_id,
            status="accepted",
            reviewed_at=_now_iso(),
            reviewed_by=reviewed_by,
        )

        # Emit events
        event_payload = {
            "candidate_id": candidate_id,
            "identity_id": target_identity_id,
            "cluster_a_id": candidate.cluster_a_id,
            "cluster_b_id": candidate.cluster_b_id,
            "action_id": action_id,
        }
        self._emit_event(MERGE_CANDIDATE_ACCEPTED, event_payload)
        self._emit_refresh_events(
            identity_ids=[target_identity_id],
            cluster_ids=[candidate.cluster_a_id, candidate.cluster_b_id],
            reason="merge_candidate_accepted",
        )

        logger.info(
            "[IdentityService] Accepted merge %s: %s + %s -> identity %s",
            candidate_id, candidate.cluster_a_id, candidate.cluster_b_id,
            target_identity_id,
        )
        return {
            "status": "accepted",
            "identity_id": target_identity_id,
            "action_id": action_id,
        }

    def reject_merge_candidate(
        self,
        candidate_id: str,
        reviewed_by: Optional[str] = None,
    ) -> dict:
        """Reject a merge candidate — persist rejection, no identity change."""
        candidate = self.people_review_repo.get_merge_candidate(candidate_id)
        if not candidate:
            raise ValueError(f"Unknown merge candidate: {candidate_id}")

        self.people_review_repo.update_merge_candidate_status(
            candidate_id,
            status="rejected",
            reviewed_at=_now_iso(),
            reviewed_by=reviewed_by,
        )

        action_id = self.identity_repo.log_identity_action(
            action_type="merge_rejected",
            candidate_id=candidate_id,
            cluster_id=candidate.cluster_a_id,
            related_cluster_id=candidate.cluster_b_id,
            created_by=reviewed_by,
            is_undoable=False,
        )

        self._emit_event(MERGE_CANDIDATE_REJECTED, {
            "candidate_id": candidate_id,
            "cluster_a_id": candidate.cluster_a_id,
            "cluster_b_id": candidate.cluster_b_id,
            "action_id": action_id,
        })
        self._emit_event(PEOPLE_REVIEW_QUEUE_REFRESH_REQUESTED, {})

        logger.info("[IdentityService] Rejected merge %s", candidate_id)
        return {"status": "rejected", "action_id": action_id}

    def skip_merge_candidate(
        self,
        candidate_id: str,
        reviewed_by: Optional[str] = None,
    ) -> dict:
        """Skip a merge candidate — mark as skipped, no identity change."""
        candidate = self.people_review_repo.get_merge_candidate(candidate_id)
        if not candidate:
            raise ValueError(f"Unknown merge candidate: {candidate_id}")

        self.people_review_repo.update_merge_candidate_status(
            candidate_id,
            status="skipped",
            reviewed_at=_now_iso(),
            reviewed_by=reviewed_by,
        )

        self._emit_event(MERGE_CANDIDATE_SKIPPED, {
            "candidate_id": candidate_id,
            "cluster_a_id": candidate.cluster_a_id,
            "cluster_b_id": candidate.cluster_b_id,
        })
        self._emit_event(PEOPLE_REVIEW_QUEUE_REFRESH_REQUESTED, {})

        logger.info("[IdentityService] Skipped merge %s", candidate_id)
        return {"status": "skipped"}

    # ── Undo / detach ─────────────────────────────────────────────────

    def reverse_last_merge_for_identity(
        self,
        identity_id: str,
        performed_by: Optional[str] = None,
    ) -> dict:
        """Reverse the most recent undoable merge action for an identity."""
        last_action = self.identity_repo.get_last_undoable_action_for_identity(
            identity_id
        )
        if not last_action or last_action.action_type != "merge_accepted":
            return {"status": "nothing_to_undo"}

        # Parse payload to find attached cluster
        try:
            payload = json.loads(last_action.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        secondary_cluster_id = payload.get("secondary_cluster_id")
        if not secondary_cluster_id:
            return {"status": "no_cluster_in_payload"}

        # Deactivate the link
        self.identity_repo.deactivate_cluster_link(identity_id, secondary_cluster_id)

        # Log the reversal
        reversal_id = self.identity_repo.log_identity_action(
            action_type="merge_reversed",
            identity_id=identity_id,
            cluster_id=secondary_cluster_id,
            candidate_id=last_action.candidate_id,
            payload_json=json.dumps({
                "reversed_action_id": last_action.action_id,
                "secondary_cluster_id": secondary_cluster_id,
            }),
            created_by=performed_by,
            is_undoable=False,
        )

        # Mark original action as undone
        self.identity_repo.mark_action_undone(last_action.action_id, reversal_id)

        # Emit events
        self._emit_event(MERGE_REVERSED, {
            "identity_id": identity_id,
            "cluster_id": secondary_cluster_id,
            "reversed_action_id": last_action.action_id,
            "reversal_action_id": reversal_id,
        })
        self._emit_refresh_events(
            identity_ids=[identity_id],
            cluster_ids=[secondary_cluster_id],
            reason="merge_reversed",
        )

        logger.info(
            "[IdentityService] Reversed merge: detached %s from identity %s",
            secondary_cluster_id, identity_id,
        )
        return {
            "status": "reversed",
            "identity_id": identity_id,
            "detached_cluster_id": secondary_cluster_id,
            "reversal_action_id": reversal_id,
        }

    def detach_cluster_from_identity(
        self,
        identity_id: str,
        cluster_id: str,
        performed_by: Optional[str] = None,
    ) -> dict:
        """Detach a specific cluster from an identity."""
        count = self.identity_repo.deactivate_cluster_link(identity_id, cluster_id)
        if count == 0:
            return {"status": "no_active_link"}

        action_id = self.identity_repo.log_identity_action(
            action_type="cluster_detached",
            identity_id=identity_id,
            cluster_id=cluster_id,
            created_by=performed_by,
            is_undoable=False,
        )

        self._emit_event(IDENTITY_CLUSTER_DETACHED, {
            "identity_id": identity_id,
            "cluster_id": cluster_id,
            "action_id": action_id,
        })
        self._emit_refresh_events(
            identity_ids=[identity_id],
            cluster_ids=[cluster_id],
            reason="cluster_detached",
        )

        logger.info(
            "[IdentityService] Detached cluster %s from identity %s",
            cluster_id, identity_id,
        )
        return {"status": "detached", "action_id": action_id}

    # ── Protection ────────────────────────────────────────────────────

    def set_identity_protected(
        self,
        identity_id: str,
        is_protected: bool,
        performed_by: Optional[str] = None,
    ) -> None:
        self.identity_repo.set_identity_protected(identity_id, is_protected)

        action_type = "identity_protected" if is_protected else "identity_unprotected"
        self.identity_repo.log_identity_action(
            action_type=action_type,
            identity_id=identity_id,
            created_by=performed_by,
            is_undoable=False,
        )

        event_name = IDENTITY_PROTECTED if is_protected else IDENTITY_UNPROTECTED
        self._emit_event(event_name, {
            "identity_id": identity_id,
            "is_protected": is_protected,
        })

        logger.info(
            "[IdentityService] Identity %s: protected=%s",
            identity_id, is_protected,
        )

    # ── Internal helpers ──────────────────────────────────────────────

    def _select_primary_identity(
        self,
        identity_a: PersonIdentityModel,
        identity_b: PersonIdentityModel,
    ) -> str:
        """Select which identity should be the merge target.
        Prefer: protected > named > older."""
        if identity_a.is_protected and not identity_b.is_protected:
            return identity_a.identity_id
        if identity_b.is_protected and not identity_a.is_protected:
            return identity_b.identity_id
        # Prefer the one with a display name
        if identity_a.display_name and not identity_b.display_name:
            return identity_a.identity_id
        if identity_b.display_name and not identity_a.display_name:
            return identity_b.identity_id
        # Fall back to older identity
        if identity_a.created_at <= identity_b.created_at:
            return identity_a.identity_id
        return identity_b.identity_id

    def _compute_badges(self, identity: PersonIdentityModel) -> List[str]:
        badges = []
        if identity.is_protected:
            badges.append("protected")
        if identity.is_hidden:
            badges.append("hidden")
        if identity.display_name:
            badges.append("named")
        else:
            badges.append("unnamed")
        return badges

    def _emit_event(self, event_name: str, payload: dict) -> None:
        if self.event_bus and hasattr(self.event_bus, "emit"):
            try:
                self.event_bus.emit(event_name, payload)
            except Exception:
                logger.debug("[IdentityService] Event emission failed: %s",
                             event_name, exc_info=True)

    def _emit_refresh_events(
        self,
        identity_ids: List[str],
        cluster_ids: List[str],
        reason: str,
    ) -> None:
        refresh_payload = {
            "identity_ids": identity_ids,
            "cluster_ids": cluster_ids,
            "reason": reason,
        }
        self._emit_event(PEOPLE_INDEX_REFRESH_REQUESTED, refresh_payload)
        self._emit_event(PEOPLE_SIDEBAR_REFRESH_REQUESTED, refresh_payload)
        self._emit_event(PEOPLE_REVIEW_QUEUE_REFRESH_REQUESTED, refresh_payload)
        self._emit_event(SEARCH_PERSON_FACETS_REFRESH_REQUESTED, refresh_payload)
