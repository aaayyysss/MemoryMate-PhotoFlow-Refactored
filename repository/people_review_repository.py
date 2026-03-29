"""
UX-11: People Review Repository — merge candidates and cluster review decisions.

Owns CRUD for:
  - merge_candidate table (pairwise merge suggestions with lifecycle)
  - cluster_review_decision table (unnamed cluster governance)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Set

from models.people_review_models import (
    ClusterReviewDecisionModel,
    MergeCandidateModel,
    MergeRationale,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}_{short}" if prefix else short


def _confidence_band(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.70:
        return "medium"
    return "low"


def _parse_rationale(json_str: str) -> List[MergeRationale]:
    try:
        items = json.loads(json_str) if json_str else []
        return [MergeRationale(
            code=r.get("code", ""),
            label=r.get("label", ""),
            weight=float(r.get("weight", 0)),
        ) for r in items]
    except Exception:
        return []


def _serialize_rationale(rationale: List[MergeRationale]) -> str:
    return json.dumps([
        {"code": r.code, "label": r.label, "weight": r.weight}
        for r in rationale
    ])


class PeopleReviewRepository:
    """UX-11 repository for merge candidates and cluster review decisions."""

    def __init__(self, db):
        self.db = db

    # ── Merge candidate CRUD ──────────────────────────────────────────

    def upsert_merge_candidate(self, candidate: MergeCandidateModel) -> None:
        self.db.execute("""
            INSERT INTO merge_candidate (
                candidate_id, cluster_a_id, cluster_b_id,
                confidence_score, confidence_band, rationale_json,
                status, created_at, reviewed_at, reviewed_by,
                model_version, feature_version,
                invalidated_reason, superseded_by_candidate_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id) DO UPDATE SET
                confidence_score=excluded.confidence_score,
                confidence_band=excluded.confidence_band,
                rationale_json=excluded.rationale_json,
                status=excluded.status,
                reviewed_at=excluded.reviewed_at,
                reviewed_by=excluded.reviewed_by,
                model_version=excluded.model_version,
                feature_version=excluded.feature_version,
                invalidated_reason=excluded.invalidated_reason,
                superseded_by_candidate_id=excluded.superseded_by_candidate_id
        """, (
            candidate.candidate_id, candidate.cluster_a_id, candidate.cluster_b_id,
            candidate.confidence_score, candidate.confidence_band,
            _serialize_rationale(candidate.rationale),
            candidate.status, candidate.created_at,
            candidate.reviewed_at, candidate.reviewed_by,
            candidate.model_version, candidate.feature_version,
            candidate.invalidated_reason, candidate.superseded_by_candidate_id,
        ))

    def get_merge_candidate(self, candidate_id: str) -> Optional[MergeCandidateModel]:
        row = self.db.execute("""
            SELECT candidate_id, cluster_a_id, cluster_b_id,
                   confidence_score, confidence_band, rationale_json,
                   status, created_at, reviewed_at, reviewed_by,
                   model_version, feature_version,
                   invalidated_reason, superseded_by_candidate_id
            FROM merge_candidate WHERE candidate_id = ?
        """, (candidate_id,)).fetchone()
        return self._row_to_candidate(row) if row else None

    def list_merge_candidates(
        self,
        status: Optional[str] = None,
        include_invalidated: bool = False,
        limit: Optional[int] = None,
    ) -> List[MergeCandidateModel]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if not include_invalidated:
            clauses.append("status != 'invalidated'")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT candidate_id, cluster_a_id, cluster_b_id,
                   confidence_score, confidence_band, rationale_json,
                   status, created_at, reviewed_at, reviewed_by,
                   model_version, feature_version,
                   invalidated_reason, superseded_by_candidate_id
            FROM merge_candidate {where}
            ORDER BY
                CASE status
                    WHEN 'unreviewed' THEN 0
                    WHEN 'skipped' THEN 1
                    ELSE 2
                END,
                confidence_score DESC
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.db.execute(sql, params).fetchall()
        return [self._row_to_candidate(r) for r in rows]

    def find_existing_pair(
        self,
        cluster_a_id: str,
        cluster_b_id: str,
        include_invalidated: bool = False,
    ) -> Optional[MergeCandidateModel]:
        a, b = sorted([str(cluster_a_id), str(cluster_b_id)])
        sql = """
            SELECT candidate_id, cluster_a_id, cluster_b_id,
                   confidence_score, confidence_band, rationale_json,
                   status, created_at, reviewed_at, reviewed_by,
                   model_version, feature_version,
                   invalidated_reason, superseded_by_candidate_id
            FROM merge_candidate
            WHERE ((cluster_a_id = ? AND cluster_b_id = ?)
                OR (cluster_a_id = ? AND cluster_b_id = ?))
        """
        params = [a, b, b, a]
        if not include_invalidated:
            sql += " AND status != 'invalidated'"
        sql += " ORDER BY created_at DESC LIMIT 1"
        row = self.db.execute(sql, params).fetchone()
        return self._row_to_candidate(row) if row else None

    def update_merge_candidate_status(
        self,
        candidate_id: str,
        status: str,
        reviewed_at: Optional[str] = None,
        reviewed_by: Optional[str] = None,
        invalidated_reason: Optional[str] = None,
        superseded_by_candidate_id: Optional[str] = None,
    ) -> None:
        self.db.execute("""
            UPDATE merge_candidate SET
                status = ?,
                reviewed_at = COALESCE(?, reviewed_at),
                reviewed_by = COALESCE(?, reviewed_by),
                invalidated_reason = COALESCE(?, invalidated_reason),
                superseded_by_candidate_id = COALESCE(?, superseded_by_candidate_id)
            WHERE candidate_id = ?
        """, (status, reviewed_at, reviewed_by, invalidated_reason,
              superseded_by_candidate_id, candidate_id))

    def invalidate_candidates_for_cluster_ids(
        self, cluster_ids: List[str], reason: str,
    ) -> int:
        if not cluster_ids:
            return 0
        placeholders = ",".join("?" * len(cluster_ids))
        cursor = self.db.execute(f"""
            UPDATE merge_candidate SET
                status = 'invalidated',
                invalidated_reason = ?
            WHERE status IN ('unreviewed', 'skipped')
              AND (cluster_a_id IN ({placeholders}) OR cluster_b_id IN ({placeholders}))
        """, [reason] + list(cluster_ids) + list(cluster_ids))
        return cursor.rowcount if hasattr(cursor, "rowcount") else 0

    def invalidate_candidates_for_model_version_change(
        self, old_model_version: str, new_model_version: str, reason: str,
    ) -> int:
        cursor = self.db.execute("""
            UPDATE merge_candidate SET
                status = 'invalidated',
                invalidated_reason = ?
            WHERE model_version = ?
              AND status IN ('unreviewed', 'skipped')
        """, (reason, old_model_version))
        return cursor.rowcount if hasattr(cursor, "rowcount") else 0

    def get_reviewed_pair_keys(self) -> Set[tuple]:
        """Return set of (a, b) tuples for all non-invalidated reviewed candidates."""
        rows = self.db.execute("""
            SELECT cluster_a_id, cluster_b_id
            FROM merge_candidate
            WHERE status IN ('accepted', 'rejected', 'skipped')
        """).fetchall()
        return {tuple(sorted([r[0], r[1]])) for r in rows}

    # ── Cluster review decisions ──────────────────────────────────────

    def save_cluster_review_decision(self, decision: ClusterReviewDecisionModel) -> None:
        self.db.execute("""
            INSERT INTO cluster_review_decision (
                decision_id, cluster_id, decision_type,
                target_identity_id, notes, created_at,
                created_by, is_active, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(decision_id) DO UPDATE SET
                decision_type=excluded.decision_type,
                target_identity_id=excluded.target_identity_id,
                notes=excluded.notes,
                is_active=excluded.is_active
        """, (
            decision.decision_id, decision.cluster_id, decision.decision_type,
            decision.target_identity_id, decision.notes, decision.created_at,
            decision.created_by, 1 if decision.is_active else 0, decision.source,
        ))

    def get_active_cluster_review_decision(
        self, cluster_id: str,
    ) -> Optional[ClusterReviewDecisionModel]:
        row = self.db.execute("""
            SELECT decision_id, cluster_id, decision_type,
                   target_identity_id, notes, created_at,
                   created_by, is_active, source
            FROM cluster_review_decision
            WHERE cluster_id = ? AND is_active = 1
            ORDER BY created_at DESC LIMIT 1
        """, (str(cluster_id),)).fetchone()
        return self._row_to_cluster_decision(row) if row else None

    def deactivate_cluster_review_decisions(self, cluster_id: str) -> int:
        cursor = self.db.execute("""
            UPDATE cluster_review_decision
            SET is_active = 0
            WHERE cluster_id = ? AND is_active = 1
        """, (str(cluster_id),))
        return cursor.rowcount if hasattr(cursor, "rowcount") else 0

    def list_cluster_decisions_by_type(
        self, decision_type: str, active_only: bool = True,
    ) -> List[ClusterReviewDecisionModel]:
        sql = """
            SELECT decision_id, cluster_id, decision_type,
                   target_identity_id, notes, created_at,
                   created_by, is_active, source
            FROM cluster_review_decision
            WHERE decision_type = ?
        """
        params = [decision_type]
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY created_at DESC"
        rows = self.db.execute(sql, params).fetchall()
        return [self._row_to_cluster_decision(r) for r in rows]

    def get_decided_cluster_ids(self) -> Set[str]:
        rows = self.db.execute("""
            SELECT DISTINCT cluster_id FROM cluster_review_decision WHERE is_active = 1
        """).fetchall()
        return {r[0] for r in rows}

    # ── Helpers ───────────────────────────────────────────────────────

    def _row_to_candidate(self, row) -> MergeCandidateModel:
        return MergeCandidateModel(
            candidate_id=row[0],
            cluster_a_id=row[1],
            cluster_b_id=row[2],
            confidence_score=float(row[3]),
            confidence_band=row[4],
            rationale=_parse_rationale(row[5]),
            status=row[6],
            created_at=row[7] or "",
            reviewed_at=row[8],
            reviewed_by=row[9],
            model_version=row[10],
            feature_version=row[11],
            invalidated_reason=row[12],
            superseded_by_candidate_id=row[13],
        )

    def _row_to_cluster_decision(self, row) -> ClusterReviewDecisionModel:
        return ClusterReviewDecisionModel(
            decision_id=row[0],
            cluster_id=row[1],
            decision_type=row[2],
            target_identity_id=row[3],
            notes=row[4],
            created_at=row[5] or "",
            created_by=row[6],
            is_active=bool(row[7]),
            source=row[8] or "user",
        )
