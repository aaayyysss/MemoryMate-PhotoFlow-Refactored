# services/group_service.py
# Version 01.01.02.00 dated 20260215
# People Groups service - CRUD + co-occurrence retrieval
#
# Manages user-defined groups of people (face clusters) and computes
# which photos contain all group members together (AND matching).
#
# Design:
#   - Groups are per-project, identified by person_groups.id
#   - Members are linked via branch_key (same as face_branch_reps)
#   - Match results are materialized in group_asset_matches for speed
#   - Live queries are available for small groups / interactive use
#
# Fix 2026-02-15: Added instance() singleton method for callers expecting
#                 instance-based access pattern.

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from reference_db import ReferenceDB

logger = logging.getLogger(__name__)

# Module-level singleton instance
_group_service_instance: Optional["GroupServiceInstance"] = None


class GroupServiceInstance:
    """
    Instance-based wrapper around GroupService static methods.

    Provides an instance() pattern for callers that expect singleton access.
    Automatically acquires ReferenceDB from the application context.
    """

    def __init__(self):
        """Initialize with lazy db acquisition."""
        self._db = None

    @property
    def db(self):
        """Lazily acquire ReferenceDB instance."""
        if self._db is None:
            from reference_db import ReferenceDB
            self._db = ReferenceDB.instance()
        return self._db

    def get_groups(self, project_id: int, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """Get all groups for a project."""
        return GroupService.get_groups(self.db, project_id, include_deleted)

    def get_group(self, group_id: int, project_id: int) -> Optional[Dict[str, Any]]:
        """Get a single group by ID."""
        return GroupService.get_group(self.db, group_id, project_id)

    def create_group(
        self,
        project_id: int,
        name: str,
        branch_keys: List[str],
        is_pinned: bool = False,
    ) -> int:
        """Create a new people group."""
        return GroupService.create_group(self.db, project_id, name, branch_keys, is_pinned)

    def update_group(
        self,
        group_id: int,
        name: Optional[str] = None,
        branch_keys: Optional[List[str]] = None,
        is_pinned: Optional[bool] = None,
    ) -> None:
        """Update a group."""
        return GroupService.update_group(self.db, group_id, name, branch_keys, is_pinned)

    def delete_group(self, group_id: int) -> None:
        """Soft-delete a group."""
        return GroupService.delete_group(self.db, group_id)

    def hard_delete_group(self, group_id: int) -> None:
        """Permanently delete a group."""
        return GroupService.hard_delete_group(self.db, group_id)

    def touch_group(self, group_id: int) -> None:
        """Update last_used_at timestamp."""
        return GroupService.touch_group(self.db, group_id)

    def query_same_photo_matches(self, project_id: int, group_id: int) -> List[int]:
        """Live AND-match query returning photo IDs."""
        return GroupService.query_same_photo_matches(self.db, project_id, group_id)

    def query_same_photo_paths(self, project_id: int, group_id: int) -> List[str]:
        """Live AND-match query returning file paths."""
        return GroupService.query_same_photo_paths(self.db, project_id, group_id)

    def compute_and_store_matches(
        self,
        project_id: int,
        group_id: int,
        scope: str = "same_photo",
    ) -> int:
        """Compute and cache group matches."""
        return GroupService.compute_and_store_matches(self.db, project_id, group_id, scope)

    def get_cached_match_paths(
        self,
        project_id: int,
        group_id: int,
        scope: str = "same_photo",
    ) -> List[str]:
        """Get cached match paths."""
        return GroupService.get_cached_match_paths(self.db, project_id, group_id, scope)

    def get_cached_match_count(self, group_id: int, scope: str = "same_photo") -> int:
        """Get count of cached matches."""
        return GroupService.get_cached_match_count(self.db, group_id, scope)

    def get_group_photos(
        self,
        project_id: int,
        group_id: int,
        scope: str = "same_photo",
    ) -> List[str]:
        """
        Get photo paths for a group.

        This is the primary method for retrieving photos that match a group's
        criteria (all members appearing together). Returns cached results if
        available, otherwise performs a live query.

        Args:
            project_id: Project ID
            group_id: Group ID
            scope: Match scope (default "same_photo" for AND-matching)

        Returns:
            List of file paths for matching photos
        """
        return GroupService.get_cached_match_paths(self.db, project_id, group_id, scope)

    def reindex_all_groups(self, project_id: int) -> Dict[int, int]:
        """Recompute matches for all groups."""
        return GroupService.reindex_all_groups(self.db, project_id)

    def get_people_for_group_creation(self, project_id: int) -> List[Dict[str, Any]]:
        """Get all people (face clusters) for group creation dialog."""
        return GroupService.get_people_for_group_creation(self.db, project_id)


class GroupService:
    """
    Service for People Groups CRUD and co-occurrence retrieval.

    Thread safety:
        Each caller must pass its own ReferenceDB or sqlite3 connection.
        The service itself holds no mutable state.

    Usage:
        # Static method pattern (explicit db):
        GroupService.get_groups(db, project_id)

        # Singleton pattern (auto db acquisition):
        service = GroupService.instance()
        service.get_groups(project_id)
    """

    @classmethod
    def instance(cls) -> GroupServiceInstance:
        """
        Get singleton GroupServiceInstance.

        Returns an instance wrapper that automatically acquires
        ReferenceDB and provides instance methods for all static methods.

        Example:
            service = GroupService.instance()
            groups = service.get_groups(project_id)
        """
        global _group_service_instance
        if _group_service_instance is None:
            _group_service_instance = GroupServiceInstance()
        return _group_service_instance

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @staticmethod
    def create_group(
        db,
        project_id: int,
        name: str,
        branch_keys: List[str],
        is_pinned: bool = False,
    ) -> int:
        """
        Create a new people group.
 
        Args:
            db: ReferenceDB instance
            project_id: Project this group belongs to
            name: Display name (e.g. "Family", "Ammar + Alya")
            branch_keys: List of face branch_keys (min 2)
            is_pinned: Pin group to top of list
 
        Returns:
            int: The new group ID
 
        Raises:
            ValueError: If fewer than 2 branch_keys are provided
        """
        if len(branch_keys) < 2:
            raise ValueError("A group requires at least 2 members")
 
        now = int(time.time())
 
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO person_groups
                    (project_id, name, created_at, updated_at, last_used_at, is_pinned)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, name, now, now, now, int(is_pinned)),
            )
            group_id = cur.lastrowid
 
            member_rows = [
                (group_id, bk, now) for bk in branch_keys
            ]
            cur.executemany(
                "INSERT INTO person_group_members (group_id, branch_key, added_at) VALUES (?, ?, ?)",
                member_rows,
            )
            conn.commit()
 
        logger.info(
            "[GroupService] Created group %d '%s' with %d members (project %d)",
            group_id, name, len(branch_keys), project_id,
        )
        return group_id
 
    @staticmethod
    def update_group(
        db,
        group_id: int,
        name: Optional[str] = None,
        branch_keys: Optional[List[str]] = None,
        is_pinned: Optional[bool] = None,
    ) -> None:
        """
        Update an existing group's name, members, or pinned state.
 
        If branch_keys is provided, replaces all members (and clears cached matches).
        """
        now = int(time.time())
 
        with db.get_connection() as conn:
            cur = conn.cursor()
 
            updates = ["updated_at = ?"]
            params: list = [now]
 
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if is_pinned is not None:
                updates.append("is_pinned = ?")
                params.append(int(is_pinned))
 
            params.append(group_id)
            cur.execute(
                f"UPDATE person_groups SET {', '.join(updates)} WHERE id = ?",
                params,
            )
 
            if branch_keys is not None:
                if len(branch_keys) < 2:
                    raise ValueError("A group requires at least 2 members")
 
                # Replace members
                cur.execute("DELETE FROM person_group_members WHERE group_id = ?", (group_id,))
                member_rows = [(group_id, bk, now) for bk in branch_keys]
                cur.executemany(
                    "INSERT INTO person_group_members (group_id, branch_key, added_at) VALUES (?, ?, ?)",
                    member_rows,
                )
                # Clear stale match cache
                cur.execute("DELETE FROM group_asset_matches WHERE group_id = ?", (group_id,))
 
            conn.commit()
 
        logger.info("[GroupService] Updated group %d", group_id)
 
    @staticmethod
    def delete_group(db, group_id: int) -> None:
        """Soft-delete a group (sets is_deleted=1)."""
        now = int(time.time())
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE person_groups SET is_deleted = 1, updated_at = ? WHERE id = ?",
                (now, group_id),
            )
            conn.commit()
        logger.info("[GroupService] Soft-deleted group %d", group_id)
 
    @staticmethod
    def hard_delete_group(db, group_id: int) -> None:
        """Permanently delete a group and all its members + cached matches."""
        with db.get_connection() as conn:
            conn.execute("DELETE FROM group_asset_matches WHERE group_id = ?", (group_id,))
            conn.execute("DELETE FROM person_group_members WHERE group_id = ?", (group_id,))
            conn.execute("DELETE FROM person_groups WHERE id = ?", (group_id,))
            conn.commit()
        logger.info("[GroupService] Hard-deleted group %d", group_id)
 
    @staticmethod
    def get_groups(db, project_id: int, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        Get all groups for a project.
 
        Returns list of dicts with keys:
            id, name, created_at, updated_at, last_used_at, is_pinned,
            member_count, members (list of {branch_key, label})
        """
        with db.get_connection() as conn:
            cur = conn.cursor()
 
            deleted_filter = "" if include_deleted else "AND g.is_deleted = 0"
            cur.execute(
                f"""
                SELECT g.id, g.name, g.created_at, g.updated_at,
                       g.last_used_at, g.is_pinned,
                       COUNT(m.branch_key) AS member_count
                FROM person_groups g
                LEFT JOIN person_group_members m ON m.group_id = g.id
                WHERE g.project_id = ? {deleted_filter}
                GROUP BY g.id
                ORDER BY g.is_pinned DESC, g.last_used_at DESC NULLS LAST, g.name ASC
                """,
                (project_id,),
            )
            groups = []
            for row in cur.fetchall():
                groups.append({
                    "id": row[0],
                    "name": row[1],
                    "created_at": row[2],
                    "updated_at": row[3],
                    "last_used_at": row[4],
                    "is_pinned": bool(row[5]),
                    "member_count": row[6],
                })
 
            # Load members for each group
            for g in groups:
                cur.execute(
                    """
                    SELECT m.branch_key,
                           COALESCE(r.label, m.branch_key) AS display_name,
                           r.rep_thumb_png
                    FROM person_group_members m
                    LEFT JOIN face_branch_reps r
                        ON r.branch_key = m.branch_key AND r.project_id = ?
                    WHERE m.group_id = ?
                    ORDER BY m.added_at ASC
                    """,
                    (project_id, g["id"]),
                )
                g["members"] = [
                    {"branch_key": r[0], "display_name": r[1], "rep_thumb_png": r[2]}
                    for r in cur.fetchall()
                ]
 
        return groups
 
    @staticmethod
    def get_group(db, group_id: int, project_id: int) -> Optional[Dict[str, Any]]:
        """Get a single group by ID with members."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, name, created_at, updated_at, last_used_at, is_pinned
                FROM person_groups
                WHERE id = ? AND project_id = ? AND is_deleted = 0
                """,
                (group_id, project_id),
            )
            row = cur.fetchone()
            if not row:
                return None
 
            group = {
                "id": row[0],
                "name": row[1],
                "created_at": row[2],
                "updated_at": row[3],
                "last_used_at": row[4],
                "is_pinned": bool(row[5]),
            }
 
            cur.execute(
                """
                SELECT m.branch_key,
                       COALESCE(r.label, m.branch_key) AS display_name,
                       r.rep_thumb_png
                FROM person_group_members m
                LEFT JOIN face_branch_reps r
                    ON r.branch_key = m.branch_key AND r.project_id = ?
                WHERE m.group_id = ?
                ORDER BY m.added_at ASC
                """,
                (project_id, group_id),
            )
            group["members"] = [
                {"branch_key": r[0], "display_name": r[1], "rep_thumb_png": r[2]}
                for r in cur.fetchall()
            ]
            return group
 
    @staticmethod
    def touch_group(db, group_id: int) -> None:
        """Update last_used_at timestamp (called when user opens a group)."""
        now = int(time.time())
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE person_groups SET last_used_at = ? WHERE id = ?",
                (now, group_id),
            )
            conn.commit()
 
    # ------------------------------------------------------------------
    # Co-occurrence queries (live, no materialization)
    # ------------------------------------------------------------------
 
    @staticmethod
    def query_same_photo_matches(
        db,
        project_id: int,
        group_id: int,
    ) -> List[int]:
        """
        Live AND-match: photos where ALL group members appear together.
 
        Uses face_crops (not project_images) for accurate face-level matching.
        Returns list of photo_metadata.id values.
        """
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                WITH members AS (
                    SELECT branch_key
                    FROM person_group_members
                    WHERE group_id = ?
                ),
                member_count AS (
                    SELECT COUNT(*) AS n FROM members
                )
                SELECT pm.id
                FROM face_crops fc
                JOIN members m ON m.branch_key = fc.branch_key
                JOIN photo_metadata pm ON pm.path = fc.image_path AND pm.project_id = fc.project_id
                WHERE fc.project_id = ?
                GROUP BY pm.id
                HAVING COUNT(DISTINCT fc.branch_key) = (SELECT n FROM member_count)
                ORDER BY pm.created_ts DESC, pm.id DESC
                """,
                (group_id, project_id),
            )
            return [row[0] for row in cur.fetchall()]
 
    @staticmethod
    def query_same_photo_paths(
        db,
        project_id: int,
        group_id: int,
    ) -> List[str]:
        """
        Live AND-match returning file paths instead of IDs.
        Useful for grid display that works with paths.
        """
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                WITH members AS (
                    SELECT branch_key
                    FROM person_group_members
                    WHERE group_id = ?
                ),
                member_count AS (
                    SELECT COUNT(*) AS n FROM members
                )
                SELECT fc.image_path
                FROM face_crops fc
                JOIN members m ON m.branch_key = fc.branch_key
                WHERE fc.project_id = ?
                GROUP BY fc.image_path
                HAVING COUNT(DISTINCT fc.branch_key) = (SELECT n FROM member_count)
                ORDER BY fc.image_path
                """,
                (group_id, project_id),
            )
            return [row[0] for row in cur.fetchall()]
 
    # ------------------------------------------------------------------
    # Materialized match management
    # ------------------------------------------------------------------
 
    @staticmethod
    def compute_and_store_matches(
        db,
        project_id: int,
        group_id: int,
        scope: str = "same_photo",
    ) -> int:
        """
        Compute group matches and store in group_asset_matches.
 
        Returns number of matched photos.
        """
        now = int(time.time())
        photo_ids = GroupService.query_same_photo_matches(db, project_id, group_id)
 
        with db.get_connection() as conn:
            cur = conn.cursor()
            # Clear old matches for this group+scope
            cur.execute(
                "DELETE FROM group_asset_matches WHERE group_id = ? AND scope = ?",
                (group_id, scope),
            )
            if photo_ids:
                rows = [(group_id, scope, pid, now) for pid in photo_ids]
                cur.executemany(
                    "INSERT INTO group_asset_matches (group_id, scope, photo_id, computed_at) VALUES (?, ?, ?, ?)",
                    rows,
                )
            conn.commit()
 
        logger.info(
            "[GroupService] Computed %d matches for group %d scope=%s",
            len(photo_ids), group_id, scope,
        )
        return len(photo_ids)
 
    @staticmethod
    def get_cached_match_paths(
        db,
        project_id: int,
        group_id: int,
        scope: str = "same_photo",
    ) -> List[str]:
        """
        Get cached match paths from group_asset_matches.
 
        Falls back to live query if no cached results.
        """
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT pm.path
                FROM group_asset_matches gam
                JOIN photo_metadata pm ON pm.id = gam.photo_id AND pm.project_id = ?
                WHERE gam.group_id = ? AND gam.scope = ?
                ORDER BY pm.created_ts DESC, pm.id DESC
                """,
                (project_id, group_id, scope),
            )
            paths = [row[0] for row in cur.fetchall()]
 
        if not paths:
            # Fallback to live query
            paths = GroupService.query_same_photo_paths(db, project_id, group_id)
 
        return paths
 
    @staticmethod
    def get_cached_match_count(
        db,
        group_id: int,
        scope: str = "same_photo",
    ) -> int:
        """Get count of cached matches for a group."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM group_asset_matches WHERE group_id = ? AND scope = ?",
                (group_id, scope),
            )
            return cur.fetchone()[0]
 
    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------
 
    @staticmethod
    def reindex_all_groups(db, project_id: int) -> Dict[int, int]:
        """
        Recompute matches for all active groups in a project.
 
        Returns dict of {group_id: match_count}.
        """
        groups = GroupService.get_groups(db, project_id)
        results = {}
        for g in groups:
            count = GroupService.compute_and_store_matches(
                db, project_id, g["id"], scope="same_photo"
            )
            results[g["id"]] = count
        logger.info(
            "[GroupService] Reindexed %d groups for project %d",
            len(results), project_id,
        )
        return results
 
    # ------------------------------------------------------------------
    # Smart name suggestion
    # ------------------------------------------------------------------
 
    @staticmethod
    def suggest_group_name(member_names: List[str]) -> str:
        """
        Generate a default group name from member display names.

        Examples:
            ["Ammar", "Alya"] -> "Ammar + Alya"
            ["Mom", "Dad", "Sis"] -> "Mom + Dad + Sis"
            More than 3: "Mom + Dad + 2 others"
        """
        if not member_names:
            return "New Group"
        if len(member_names) <= 3:
            return " + ".join(member_names)
        return f"{member_names[0]} + {member_names[1]} + {len(member_names) - 2} others"

    # ------------------------------------------------------------------
    # People list for group creation dialog
    # ------------------------------------------------------------------

    @staticmethod
    def get_people_for_group_creation(db, project_id: int) -> List[Dict[str, Any]]:
        """
        Get all people (face clusters) available for group creation.

        Returns a list of dicts with branch_key, display_name, and rep_thumb_png
        for rendering in the CreateGroupDialog person selection grid.

        Args:
            db: ReferenceDB instance
            project_id: Project ID to fetch people for

        Returns:
            List of dicts: [{"branch_key": str, "display_name": str, "rep_thumb_png": bytes|None}, ...]
        """
        try:
            rows = db.get_face_branch_reps(project_id)
            result = []
            for row in rows:
                branch_key = row.get("id", "")
                label = row.get("name", branch_key)
                thumb_png = row.get("rep_thumb_png")
                result.append({
                    "branch_key": branch_key,
                    "display_name": label,
                    "rep_thumb_png": thumb_png,
                })
            logger.info(f"[GroupService] get_people_for_group_creation: {len(result)} people for project {project_id}")
            return result
        except Exception as e:
            logger.error(f"[GroupService] get_people_for_group_creation failed: {e}", exc_info=True)
            return []
		
