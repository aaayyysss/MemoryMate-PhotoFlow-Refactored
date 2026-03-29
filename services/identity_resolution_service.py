"""
UX-11A: Identity Resolution Service — single authoritative source for identity membership.

Responsibilities:
  - Resolve a cluster/branch key to its canonical identity
  - Track identity links (which clusters belong to which identity)
  - Provide the ground truth for "who is this person" queries
  - Detect protected identities (user-confirmed merges that must not be re-split)
  - Support undo by recording the merge chain

This service reads from both the live database (face_branch_reps, branches)
and the review repository (merge decisions, cluster decisions).
It does NOT own the merge execution — that stays with ReferenceDB.merge_face_clusters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from repository.people_merge_review_repository import PeopleMergeReviewRepository

logger = logging.getLogger(__name__)


@dataclass
class IdentityRecord:
    """A resolved identity with its constituent clusters."""
    identity_id: str          # canonical branch_key (the merge target)
    label: str                # display name
    member_cluster_ids: List[str] = field(default_factory=list)
    photo_count: int = 0
    is_named: bool = False
    is_protected: bool = False  # user-confirmed merges — do not auto-split


class IdentityResolutionService:
    """
    UX-11A: Single authoritative source for identity membership.

    Combines live DB state with review decisions to produce a consistent
    view of "who is who" for search, sidebar, and merge dialogs.
    """

    def __init__(self, db, repo: PeopleMergeReviewRepository,
                 project_id: Optional[int] = None):
        self._db = db
        self._repo = repo
        self._project_id = project_id

    @property
    def project_id(self) -> Optional[int]:
        return self._project_id

    @project_id.setter
    def project_id(self, value: int):
        self._project_id = value

    # ── Core resolution ───────────────────────────────────────────────

    def resolve_identity(self, cluster_id: str) -> Optional[IdentityRecord]:
        """Resolve a single cluster/branch key to its identity record."""
        if not self._db or not self._project_id:
            return None
        try:
            with self._db._connect() as conn:
                row = conn.execute("""
                    SELECT branch_key, label, count
                    FROM face_branch_reps
                    WHERE project_id = ? AND branch_key = ?
                """, (self._project_id, cluster_id)).fetchone()
                if not row:
                    return None

                label = str(row[1] or row[0])
                is_named = not (
                    label.lower().startswith("face_")
                    or "unnamed" in label.lower()
                    or label == "__ignored__"
                )

                # Check if this identity has accepted merges (protected)
                is_protected = self._is_protected(cluster_id)

                return IdentityRecord(
                    identity_id=str(row[0]),
                    label=label,
                    photo_count=int(row[2] or 0),
                    is_named=is_named,
                    is_protected=is_protected,
                )
        except Exception:
            logger.debug("[IdentityService] resolve_identity failed for %s",
                         cluster_id, exc_info=True)
            return None

    def get_all_identities(self) -> List[IdentityRecord]:
        """Return all current identities for the project."""
        if not self._db or not self._project_id:
            return []
        try:
            with self._db._connect() as conn:
                rows = conn.execute("""
                    SELECT branch_key, label, count
                    FROM face_branch_reps
                    WHERE project_id = ?
                    ORDER BY count DESC
                """, (self._project_id,)).fetchall()

            protected_ids = self._get_protected_ids()
            results = []
            for row in rows:
                bk = str(row[0])
                label = str(row[1] or bk)
                if label == "__ignored__":
                    continue
                is_named = not (
                    label.lower().startswith("face_")
                    or "unnamed" in label.lower()
                )
                results.append(IdentityRecord(
                    identity_id=bk,
                    label=label,
                    photo_count=int(row[2] or 0),
                    is_named=is_named,
                    is_protected=bk in protected_ids,
                ))
            return results
        except Exception:
            logger.debug("[IdentityService] get_all_identities failed", exc_info=True)
            return []

    def get_named_identities(self) -> List[IdentityRecord]:
        """Return only named (user-labeled) identities."""
        return [i for i in self.get_all_identities() if i.is_named]

    def get_unnamed_identities(self) -> List[IdentityRecord]:
        """Return only unnamed/auto-generated identities."""
        return [i for i in self.get_all_identities() if not i.is_named]

    # ── Protection ────────────────────────────────────────────────────

    def _is_protected(self, cluster_id: str) -> bool:
        """A cluster is protected if it was the target of an accepted merge."""
        try:
            decisions = self._repo.get_all_active_decisions()
            for d in decisions:
                if d.decision == "accepted" and (
                    d.left_id == cluster_id or d.right_id == cluster_id
                ):
                    return True
            return False
        except Exception:
            return False

    def _get_protected_ids(self) -> Set[str]:
        """Return all cluster IDs that are involved in accepted merges."""
        try:
            decisions = self._repo.get_all_active_decisions()
            protected = set()
            for d in decisions:
                if d.decision == "accepted":
                    protected.add(d.left_id)
                    protected.add(d.right_id)
            return protected
        except Exception:
            return set()

    def get_protected_identities(self) -> List[IdentityRecord]:
        """Return identities that have user-confirmed merges."""
        return [i for i in self.get_all_identities() if i.is_protected]

    # ── Merge chain ───────────────────────────────────────────────────

    def get_merge_history_for(self, cluster_id: str) -> List[Dict[str, Any]]:
        """Return the merge decision history involving a cluster."""
        try:
            decisions = self._repo.get_all_active_decisions()
            return [
                {
                    "left_id": d.left_id,
                    "right_id": d.right_id,
                    "decision": d.decision,
                    "model_version": d.model_version,
                    "created_at": d.created_at,
                }
                for d in decisions
                if d.left_id == cluster_id or d.right_id == cluster_id
            ]
        except Exception:
            return []

    # ── Consistency checks ────────────────────────────────────────────

    def find_orphaned_decisions(self) -> List[Dict[str, str]]:
        """Find merge decisions that reference clusters no longer in the DB.
        Useful for cleanup after external DB changes."""
        if not self._db or not self._project_id:
            return []
        try:
            with self._db._connect() as conn:
                rows = conn.execute("""
                    SELECT branch_key FROM face_branch_reps
                    WHERE project_id = ?
                """, (self._project_id,)).fetchall()
                live_ids = {str(r[0]) for r in rows}

            decisions = self._repo.get_all_active_decisions()
            orphans = []
            for d in decisions:
                missing = []
                if d.left_id not in live_ids:
                    missing.append(d.left_id)
                if d.right_id not in live_ids:
                    missing.append(d.right_id)
                if missing:
                    orphans.append({
                        "left_id": d.left_id,
                        "right_id": d.right_id,
                        "decision": d.decision,
                        "missing_ids": missing,
                    })
            return orphans
        except Exception:
            return []
