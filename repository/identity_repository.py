"""
UX-11: Identity Repository — durable identity layer, cluster links, action log.

Owns CRUD for:
  - person_identity table (durable user-facing person entities)
  - identity_cluster_link table (maps machine clusters to identities)
  - identity_action_log table (audit trail for all identity actions)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models.people_review_models import (
    IdentityClusterLinkModel,
    PersonIdentityModel,
    IdentityActionModel,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}_{short}" if prefix else short


class IdentityRepository:
    """UX-11 repository for durable identities, cluster links, and action log."""

    def __init__(self, db):
        self.db = db

    # ── Identity CRUD ─────────────────────────────────────────────────

    def create_identity(
        self,
        display_name: Optional[str] = None,
        canonical_cluster_id: Optional[str] = None,
        source: str = "system",
    ) -> str:
        identity_id = _new_id("pid")
        now = _now_iso()
        self.db.execute("""
            INSERT INTO person_identity (
                identity_id, display_name, canonical_cluster_id,
                created_at, updated_at, is_protected, is_hidden, source
            ) VALUES (?, ?, ?, ?, ?, 0, 0, ?)
        """, (identity_id, display_name, canonical_cluster_id, now, now, source))
        return identity_id

    def get_identity(self, identity_id: str) -> Optional[PersonIdentityModel]:
        row = self.db.execute("""
            SELECT identity_id, display_name, canonical_cluster_id,
                   created_at, updated_at, is_protected, is_hidden, source
            FROM person_identity WHERE identity_id = ?
        """, (identity_id,)).fetchone()
        return self._row_to_identity(row) if row else None

    def get_identity_by_cluster_id(self, cluster_id: str) -> Optional[PersonIdentityModel]:
        row = self.db.execute("""
            SELECT pi.identity_id, pi.display_name, pi.canonical_cluster_id,
                   pi.created_at, pi.updated_at, pi.is_protected, pi.is_hidden, pi.source
            FROM person_identity pi
            JOIN identity_cluster_link icl ON pi.identity_id = icl.identity_id
            WHERE icl.cluster_id = ? AND icl.is_active = 1
            ORDER BY icl.created_at DESC LIMIT 1
        """, (str(cluster_id),)).fetchone()
        return self._row_to_identity(row) if row else None

    def list_identities(
        self, include_hidden: bool = False,
    ) -> List[PersonIdentityModel]:
        sql = """
            SELECT identity_id, display_name, canonical_cluster_id,
                   created_at, updated_at, is_protected, is_hidden, source
            FROM person_identity
        """
        if not include_hidden:
            sql += " WHERE is_hidden = 0"
        sql += " ORDER BY updated_at DESC"
        rows = self.db.execute(sql).fetchall()
        return [self._row_to_identity(r) for r in rows]

    def update_identity_display_name(
        self, identity_id: str, display_name: str,
    ) -> None:
        self.db.execute("""
            UPDATE person_identity
            SET display_name = ?, updated_at = ?
            WHERE identity_id = ?
        """, (display_name, _now_iso(), identity_id))

    def set_identity_protected(
        self, identity_id: str, is_protected: bool,
    ) -> None:
        self.db.execute("""
            UPDATE person_identity
            SET is_protected = ?, updated_at = ?
            WHERE identity_id = ?
        """, (1 if is_protected else 0, _now_iso(), identity_id))

    def set_identity_hidden(
        self, identity_id: str, is_hidden: bool,
    ) -> None:
        self.db.execute("""
            UPDATE person_identity
            SET is_hidden = ?, updated_at = ?
            WHERE identity_id = ?
        """, (1 if is_hidden else 0, _now_iso(), identity_id))

    # ── Cluster links ─────────────────────────────────────────────────

    def attach_cluster_to_identity(
        self,
        identity_id: str,
        cluster_id: str,
        link_type: str,
        source: str,
    ) -> str:
        link_id = _new_id("lnk")
        self.db.execute("""
            INSERT INTO identity_cluster_link (
                link_id, identity_id, cluster_id,
                link_type, created_at, is_active, source
            ) VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (link_id, identity_id, str(cluster_id), link_type, _now_iso(), source))
        return link_id

    def list_active_cluster_links(
        self, identity_id: str,
    ) -> List[IdentityClusterLinkModel]:
        rows = self.db.execute("""
            SELECT link_id, identity_id, cluster_id, link_type,
                   created_at, removed_at, is_active, source
            FROM identity_cluster_link
            WHERE identity_id = ? AND is_active = 1
            ORDER BY created_at ASC
        """, (identity_id,)).fetchall()
        return [self._row_to_link(r) for r in rows]

    def get_active_link_for_cluster(
        self, cluster_id: str,
    ) -> Optional[IdentityClusterLinkModel]:
        row = self.db.execute("""
            SELECT link_id, identity_id, cluster_id, link_type,
                   created_at, removed_at, is_active, source
            FROM identity_cluster_link
            WHERE cluster_id = ? AND is_active = 1
            ORDER BY created_at DESC LIMIT 1
        """, (str(cluster_id),)).fetchone()
        return self._row_to_link(row) if row else None

    def deactivate_cluster_link(
        self, identity_id: str, cluster_id: str,
    ) -> int:
        cursor = self.db.execute("""
            UPDATE identity_cluster_link
            SET is_active = 0, removed_at = ?
            WHERE identity_id = ? AND cluster_id = ? AND is_active = 1
        """, (_now_iso(), identity_id, str(cluster_id)))
        return cursor.rowcount if hasattr(cursor, "rowcount") else 0

    def get_cluster_ids_for_identity(self, identity_id: str) -> List[str]:
        rows = self.db.execute("""
            SELECT cluster_id FROM identity_cluster_link
            WHERE identity_id = ? AND is_active = 1
        """, (identity_id,)).fetchall()
        return [r[0] for r in rows]

    # ── Action log ────────────────────────────────────────────────────

    def log_identity_action(
        self,
        action_type: str,
        identity_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        related_identity_id: Optional[str] = None,
        related_cluster_id: Optional[str] = None,
        candidate_id: Optional[str] = None,
        payload_json: Optional[str] = None,
        created_by: Optional[str] = None,
        is_undoable: bool = True,
    ) -> str:
        action_id = _new_id("act")
        self.db.execute("""
            INSERT INTO identity_action_log (
                action_id, action_type, identity_id, cluster_id,
                related_identity_id, related_cluster_id,
                candidate_id, payload_json,
                created_at, created_by, is_undoable
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            action_id, action_type, identity_id, cluster_id,
            related_identity_id, related_cluster_id,
            candidate_id, payload_json,
            _now_iso(), created_by, 1 if is_undoable else 0,
        ))
        return action_id

    def get_last_undoable_action_for_identity(
        self, identity_id: str,
    ) -> Optional[IdentityActionModel]:
        row = self.db.execute("""
            SELECT action_id, action_type, identity_id, cluster_id,
                   related_identity_id, related_cluster_id,
                   candidate_id, payload_json,
                   created_at, created_by, is_undoable, undone_by_action_id
            FROM identity_action_log
            WHERE identity_id = ? AND is_undoable = 1 AND undone_by_action_id IS NULL
            ORDER BY created_at DESC LIMIT 1
        """, (identity_id,)).fetchone()
        return self._row_to_action(row) if row else None

    def mark_action_undone(
        self, action_id: str, undone_by_action_id: str,
    ) -> None:
        self.db.execute("""
            UPDATE identity_action_log
            SET undone_by_action_id = ?
            WHERE action_id = ?
        """, (undone_by_action_id, action_id))

    def get_actions_for_identity(
        self, identity_id: str, limit: int = 50,
    ) -> List[IdentityActionModel]:
        rows = self.db.execute("""
            SELECT action_id, action_type, identity_id, cluster_id,
                   related_identity_id, related_cluster_id,
                   candidate_id, payload_json,
                   created_at, created_by, is_undoable, undone_by_action_id
            FROM identity_action_log
            WHERE identity_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (identity_id, limit)).fetchall()
        return [self._row_to_action(r) for r in rows]

    def get_actions_for_candidate(
        self, candidate_id: str,
    ) -> List[IdentityActionModel]:
        rows = self.db.execute("""
            SELECT action_id, action_type, identity_id, cluster_id,
                   related_identity_id, related_cluster_id,
                   candidate_id, payload_json,
                   created_at, created_by, is_undoable, undone_by_action_id
            FROM identity_action_log
            WHERE candidate_id = ?
            ORDER BY created_at DESC
        """, (candidate_id,)).fetchall()
        return [self._row_to_action(r) for r in rows]

    # ── Row mappers ───────────────────────────────────────────────────

    def _row_to_identity(self, row) -> PersonIdentityModel:
        return PersonIdentityModel(
            identity_id=row[0],
            display_name=row[1],
            canonical_cluster_id=row[2],
            created_at=row[3] or "",
            updated_at=row[4] or "",
            is_protected=bool(row[5]),
            is_hidden=bool(row[6]),
            source=row[7] or "system",
        )

    def _row_to_link(self, row) -> IdentityClusterLinkModel:
        return IdentityClusterLinkModel(
            link_id=row[0],
            identity_id=row[1],
            cluster_id=row[2],
            link_type=row[3],
            created_at=row[4] or "",
            removed_at=row[5],
            is_active=bool(row[6]),
            source=row[7] or "system",
        )

    def _row_to_action(self, row) -> IdentityActionModel:
        return IdentityActionModel(
            action_id=row[0],
            action_type=row[1],
            identity_id=row[2],
            cluster_id=row[3],
            related_identity_id=row[4],
            related_cluster_id=row[5],
            candidate_id=row[6],
            payload_json=row[7],
            created_at=row[8] or "",
            created_by=row[9],
            is_undoable=bool(row[10]),
            undone_by_action_id=row[11],
        )
