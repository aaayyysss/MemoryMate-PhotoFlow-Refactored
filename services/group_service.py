# services/group_service.py
# Person Groups Service - Groups of People for "Together (AND)" matching
# Version: 1.0.0

"""
GroupService - Person Groups Management

Provides group-centric photo management where:
- Groups are user-defined sets of existing People (face clusters)
- "Together (AND)" matching shows photos where all group members appear
- "Event Window" matching shows photos within same event window

Based on:
- Apple Photos: People → Groups sub-area
- Google Photos: Face groups with combination searching
- Lightroom: People view with catalog indexing
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional, Callable

from PySide6.QtCore import Signal, QObject

from logging_config import get_logger

logger = get_logger(__name__)


# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================

class GroupScope(Enum):
    """Match scope for group queries."""
    SAME_PHOTO = "same_photo"      # All members in same photo
    EVENT_WINDOW = "event_window"  # Members within same event window


class GroupIndexStatus(Enum):
    """Status of group index job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PersonGroupData:
    """Data class for person group information."""
    id: int
    project_id: int
    name: str
    member_count: int
    photo_count: int
    created_at: int
    updated_at: int
    last_used_at: Optional[int]
    pinned: bool
    cover_photo_id: Optional[int]
    member_branch_keys: List[str]
    member_names: List[str]
    member_thumbnails: List[bytes]  # rep_thumb_png blobs


@dataclass
class GroupMatchResult:
    """Data class for group match query results."""
    group_id: int
    scope: GroupScope
    photo_ids: List[int]
    photo_paths: List[str]
    total_count: int
    computed_at: int


# ============================================================================
# SIGNAL CLASSES (Qt Event Contract)
# ============================================================================

class GroupServiceSignals(QObject):
    """
    Signals for GroupService events.

    Signal Contract:
    - group_created(group_id: int, project_id: int)
        Emitted when a new group is created

    - group_updated(group_id: int, project_id: int)
        Emitted when a group is modified (renamed, members changed)

    - group_deleted(group_id: int, project_id: int)
        Emitted when a group is deleted

    - group_index_started(group_id: int, project_id: int, scope: str)
        Emitted when group indexing begins

    - group_index_progress(group_id: int, progress: float, message: str)
        Emitted during indexing (progress: 0.0-1.0)

    - group_index_completed(group_id: int, project_id: int, photo_count: int)
        Emitted when indexing finishes successfully

    - group_index_failed(group_id: int, project_id: int, error: str)
        Emitted when indexing fails

    - groups_loaded(project_id: int, groups: list)
        Emitted when groups list is loaded

    - group_photos_loaded(group_id: int, scope: str, photo_ids: list)
        Emitted when group photos are loaded
    """

    # Group CRUD events
    group_created = Signal(int, int)            # (group_id, project_id)
    group_updated = Signal(int, int)            # (group_id, project_id)
    group_deleted = Signal(int, int)            # (group_id, project_id)

    # Group indexing events
    group_index_started = Signal(int, int, str)     # (group_id, project_id, scope)
    group_index_progress = Signal(int, float, str)  # (group_id, progress, message)
    group_index_completed = Signal(int, int, int)   # (group_id, project_id, photo_count)
    group_index_failed = Signal(int, int, str)      # (group_id, project_id, error)

    # Data loading events
    groups_loaded = Signal(int, list)           # (project_id, groups)
    group_photos_loaded = Signal(int, str, list)  # (group_id, scope, photo_ids)


class GroupIndexSignals(QObject):
    """
    Signals for GroupIndexWorker (background indexing).

    Used by workers running in QThreadPool for progress reporting.
    """
    started = Signal(int, int, str)             # (group_id, project_id, scope)
    progress = Signal(int, float, str)          # (group_id, progress, message)
    completed = Signal(int, int, int)           # (group_id, project_id, photo_count)
    error = Signal(int, int, str)               # (group_id, project_id, error_message)


# ============================================================================
# GROUP SERVICE
# ============================================================================

class GroupService(QObject):
    """
    Service for managing person groups and their photo matches.

    Thread-safe singleton pattern (same as FacePipelineService).

    Usage:
        service = GroupService.instance()
        service.signals.group_created.connect(on_group_created)
        group_id = service.create_group(project_id, "Family", ["person_1", "person_2"])
    """

    _instance: Optional["GroupService"] = None
    _lock = threading.Lock()

    def __init__(self):
        super().__init__()
        self.signals = GroupServiceSignals()
        self._db = None  # Lazy initialization
        self._active_jobs: Dict[int, str] = {}  # group_id -> job status

    @classmethod
    def instance(cls) -> "GroupService":
        """Get or create the singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _get_db(self):
        """Lazy database connection."""
        if self._db is None:
            from reference_db import ReferenceDB
            self._db = ReferenceDB()
        return self._db

    # =========================================================================
    # GROUP CRUD OPERATIONS
    # =========================================================================

    def create_group(
        self,
        project_id: int,
        name: str,
        person_ids: List[str],
        pinned: bool = False,
        cover_photo_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Create a new person group.

        Args:
            project_id: Project ID
            name: Group name (can be auto-generated like "Ammar + Alya")
            person_ids: List of branch_keys from face_branch_reps (min 2)
            pinned: Show at top of list
            cover_photo_id: Optional custom cover photo

        Returns:
            group_id if successful, None if failed

        Emits:
            group_created(group_id, project_id)
        """
        if len(person_ids) < 2:
            logger.error("[GroupService] Group must have at least 2 members")
            return None

        try:
            db = self._get_db()
            now = int(time.time())

            with db._connect() as conn:
                # Insert group
                cur = conn.execute("""
                    INSERT INTO person_groups (
                        project_id, name, created_at, updated_at,
                        pinned, cover_photo_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (project_id, name, now, now, 1 if pinned else 0, cover_photo_id))

                group_id = cur.lastrowid

                # Insert members
                for person_id in person_ids:
                    conn.execute("""
                        INSERT INTO person_group_members (group_id, person_id, added_at)
                        VALUES (?, ?, ?)
                    """, (group_id, person_id, now))

                conn.commit()

            logger.info(f"[GroupService] Created group {group_id}: '{name}' with {len(person_ids)} members")
            self.signals.group_created.emit(group_id, project_id)

            # Trigger background indexing
            self._enqueue_index_job(group_id, project_id, GroupScope.SAME_PHOTO)

            return group_id

        except Exception as e:
            logger.error(f"[GroupService] Failed to create group: {e}", exc_info=True)
            return None

    def update_group(
        self,
        group_id: int,
        name: Optional[str] = None,
        person_ids: Optional[List[str]] = None,
        pinned: Optional[bool] = None,
        cover_photo_id: Optional[int] = None
    ) -> bool:
        """
        Update an existing group.

        Args:
            group_id: Group to update
            name: New name (optional)
            person_ids: New member list (optional, min 2)
            pinned: New pinned state (optional)
            cover_photo_id: New cover photo (optional)

        Returns:
            True if successful

        Emits:
            group_updated(group_id, project_id)
        """
        if person_ids is not None and len(person_ids) < 2:
            logger.error("[GroupService] Group must have at least 2 members")
            return False

        try:
            db = self._get_db()
            now = int(time.time())

            with db._connect() as conn:
                # Get project_id
                cur = conn.execute(
                    "SELECT project_id FROM person_groups WHERE id = ?",
                    (group_id,)
                )
                row = cur.fetchone()
                if not row:
                    logger.error(f"[GroupService] Group {group_id} not found")
                    return False
                project_id = row[0]

                # Build update query
                updates = ["updated_at = ?"]
                params = [now]

                if name is not None:
                    updates.append("name = ?")
                    params.append(name)
                if pinned is not None:
                    updates.append("pinned = ?")
                    params.append(1 if pinned else 0)
                if cover_photo_id is not None:
                    updates.append("cover_photo_id = ?")
                    params.append(cover_photo_id)

                params.append(group_id)
                conn.execute(
                    f"UPDATE person_groups SET {', '.join(updates)} WHERE id = ?",
                    params
                )

                # Update members if provided
                if person_ids is not None:
                    conn.execute(
                        "DELETE FROM person_group_members WHERE group_id = ?",
                        (group_id,)
                    )
                    for person_id in person_ids:
                        conn.execute("""
                            INSERT INTO person_group_members (group_id, person_id, added_at)
                            VALUES (?, ?, ?)
                        """, (group_id, person_id, now))

                    # Clear cached matches (need recomputation)
                    conn.execute(
                        "DELETE FROM group_asset_matches WHERE group_id = ?",
                        (group_id,)
                    )

                conn.commit()

            logger.info(f"[GroupService] Updated group {group_id}")
            self.signals.group_updated.emit(group_id, project_id)

            # Trigger reindexing if members changed
            if person_ids is not None:
                self._enqueue_index_job(group_id, project_id, GroupScope.SAME_PHOTO)

            return True

        except Exception as e:
            logger.error(f"[GroupService] Failed to update group: {e}", exc_info=True)
            return False

    def delete_group(self, group_id: int) -> bool:
        """
        Delete a group (soft delete).

        Returns:
            True if successful

        Emits:
            group_deleted(group_id, project_id)
        """
        try:
            db = self._get_db()

            with db._connect() as conn:
                cur = conn.execute(
                    "SELECT project_id FROM person_groups WHERE id = ?",
                    (group_id,)
                )
                row = cur.fetchone()
                if not row:
                    logger.error(f"[GroupService] Group {group_id} not found")
                    return False
                project_id = row[0]

                # Soft delete
                conn.execute(
                    "UPDATE person_groups SET is_deleted = 1, updated_at = ? WHERE id = ?",
                    (int(time.time()), group_id)
                )
                conn.commit()

            logger.info(f"[GroupService] Deleted group {group_id}")
            self.signals.group_deleted.emit(group_id, project_id)
            return True

        except Exception as e:
            logger.error(f"[GroupService] Failed to delete group: {e}", exc_info=True)
            return False

    # =========================================================================
    # GROUP QUERIES
    # =========================================================================

    def get_groups(self, project_id: int) -> List[Dict[str, Any]]:
        """
        Get all groups for a project.

        Returns:
            List of group dicts with member info

        Emits:
            groups_loaded(project_id, groups)
        """
        try:
            db = self._get_db()

            with db._connect() as conn:
                # Get groups with photo counts
                cur = conn.execute("""
                    SELECT
                        g.id,
                        g.name,
                        g.created_at,
                        g.updated_at,
                        g.last_used_at,
                        g.pinned,
                        g.cover_photo_id,
                        (SELECT COUNT(*) FROM person_group_members WHERE group_id = g.id) AS member_count,
                        (SELECT COUNT(*) FROM group_asset_matches WHERE group_id = g.id AND scope = 'same_photo') AS photo_count
                    FROM person_groups g
                    WHERE g.project_id = ? AND g.is_deleted = 0
                    ORDER BY g.pinned DESC, g.last_used_at DESC NULLS LAST, g.name ASC
                """, (project_id,))

                groups = []
                for row in cur.fetchall():
                    group_id = row[0]

                    # Get member info
                    members_cur = conn.execute("""
                        SELECT
                            pgm.person_id,
                            COALESCE(fbr.label, pgm.person_id) AS display_name,
                            fbr.rep_thumb_png
                        FROM person_group_members pgm
                        LEFT JOIN face_branch_reps fbr
                            ON fbr.project_id = ? AND fbr.branch_key = pgm.person_id
                        WHERE pgm.group_id = ?
                    """, (project_id, group_id))

                    members = []
                    for m_row in members_cur.fetchall():
                        members.append({
                            "branch_key": m_row[0],
                            "display_name": m_row[1],
                            "rep_thumb_png": m_row[2]
                        })

                    groups.append({
                        "id": row[0],
                        "name": row[1],
                        "created_at": row[2],
                        "updated_at": row[3],
                        "last_used_at": row[4],
                        "pinned": bool(row[5]),
                        "cover_photo_id": row[6],
                        "member_count": row[7],
                        "photo_count": row[8],
                        "members": members
                    })

            logger.info(f"[GroupService] Loaded {len(groups)} groups for project {project_id}")
            self.signals.groups_loaded.emit(project_id, groups)
            return groups

        except Exception as e:
            logger.error(f"[GroupService] Failed to get groups: {e}", exc_info=True)
            return []

    def get_group_photos(
        self,
        group_id: int,
        scope: GroupScope = GroupScope.SAME_PHOTO,
        page: int = 0,
        page_size: int = 100
    ) -> Dict[str, Any]:
        """
        Get photos matching a group (from cache).

        Args:
            group_id: Group to query
            scope: Match scope (same_photo or event_window)
            page: Page number (0-indexed)
            page_size: Results per page

        Returns:
            Dict with photo_ids, paths, total_count

        Emits:
            group_photos_loaded(group_id, scope, photo_ids)
        """
        try:
            db = self._get_db()

            with db._connect() as conn:
                # Get project_id for proper filtering
                cur = conn.execute(
                    "SELECT project_id FROM person_groups WHERE id = ?",
                    (group_id,)
                )
                row = cur.fetchone()
                if not row:
                    logger.warning(f"[GroupService] Group {group_id} not found")
                    return {"group_id": group_id, "photo_ids": [], "total_count": 0}
                project_id = row[0]

                # Update last_used_at
                conn.execute(
                    "UPDATE person_groups SET last_used_at = ? WHERE id = ?",
                    (int(time.time()), group_id)
                )

                # Get total count (with project_id filter for security)
                cur = conn.execute("""
                    SELECT COUNT(*) FROM group_asset_matches
                    WHERE project_id = ? AND group_id = ? AND scope = ?
                """, (project_id, group_id, scope.value))
                total_count = cur.fetchone()[0]

                # Get paginated results (with project_id filter for security)
                cur = conn.execute("""
                    SELECT gam.photo_id, pm.path
                    FROM group_asset_matches gam
                    JOIN photo_metadata pm ON pm.id = gam.photo_id
                    WHERE gam.project_id = ? AND gam.group_id = ? AND gam.scope = ?
                    ORDER BY pm.created_ts DESC
                    LIMIT ? OFFSET ?
                """, (project_id, group_id, scope.value, page_size, page * page_size))

                photo_ids = []
                photo_paths = []
                for row in cur.fetchall():
                    photo_ids.append(row[0])
                    photo_paths.append(row[1])

                conn.commit()

            result = {
                "group_id": group_id,
                "scope": scope.value,
                "photo_ids": photo_ids,
                "photo_paths": photo_paths,
                "total_count": total_count,
                "page": page,
                "page_size": page_size
            }

            self.signals.group_photos_loaded.emit(group_id, scope.value, photo_ids)
            return result

        except Exception as e:
            logger.error(f"[GroupService] Failed to get group photos: {e}", exc_info=True)
            return {"group_id": group_id, "photo_ids": [], "total_count": 0}

    # =========================================================================
    # GROUP INDEXING (LIVE QUERY - FOR IMMEDIATE RESULTS)
    # =========================================================================

    def compute_group_matches_live(
        self,
        project_id: int,
        group_id: int,
        scope: GroupScope = GroupScope.SAME_PHOTO
    ) -> List[int]:
        """
        Compute group matches using live query (not cached).

        This is the "Together (AND)" query that finds photos where
        all group members appear together.

        Args:
            project_id: Project ID
            group_id: Group to compute
            scope: Match scope

        Returns:
            List of matching photo_ids
        """
        try:
            db = self._get_db()

            with db._connect() as conn:
                # Get group members
                cur = conn.execute(
                    "SELECT person_id FROM person_group_members WHERE group_id = ?",
                    (group_id,)
                )
                member_ids = [row[0] for row in cur.fetchall()]

                if len(member_ids) < 2:
                    logger.warning(f"[GroupService] Group {group_id} has < 2 members")
                    return []

                member_count = len(member_ids)

                if scope == GroupScope.SAME_PHOTO:
                    # Together (AND) query: photos where ALL members appear
                    # Uses the face_crops table which links image_path to branch_key
                    cur = conn.execute(f"""
                        WITH members AS (
                            SELECT person_id FROM person_group_members WHERE group_id = ?
                        )
                        SELECT pm.id
                        FROM photo_metadata pm
                        JOIN face_crops fc ON fc.image_path = pm.path AND fc.project_id = pm.project_id
                        JOIN members m ON m.person_id = fc.branch_key
                        WHERE pm.project_id = ?
                        GROUP BY pm.id
                        HAVING COUNT(DISTINCT fc.branch_key) = ?
                        ORDER BY pm.created_ts DESC
                    """, (group_id, project_id, member_count))

                elif scope == GroupScope.EVENT_WINDOW:
                    # Event window query: events where ALL members appear (any photo)
                    cur = conn.execute(f"""
                        WITH members AS (
                            SELECT person_id FROM person_group_members WHERE group_id = ?
                        ),
                        events_with_all_members AS (
                            SELECT pe.event_id
                            FROM face_crops fc
                            JOIN photo_metadata pm ON pm.path = fc.image_path AND pm.project_id = fc.project_id
                            JOIN photo_events pe ON pe.project_id = pm.project_id AND pe.photo_id = pm.id
                            JOIN members m ON m.person_id = fc.branch_key
                            WHERE fc.project_id = ?
                            GROUP BY pe.event_id
                            HAVING COUNT(DISTINCT fc.branch_key) = ?
                        )
                        SELECT pm.id
                        FROM photo_events pe
                        JOIN events_with_all_members e ON e.event_id = pe.event_id
                        JOIN photo_metadata pm ON pm.id = pe.photo_id
                        WHERE pe.project_id = ?
                        ORDER BY pm.created_ts DESC
                    """, (group_id, project_id, member_count, project_id))

                else:
                    logger.error(f"[GroupService] Unknown scope: {scope}")
                    return []

                photo_ids = [row[0] for row in cur.fetchall()]
                logger.info(f"[GroupService] Live query found {len(photo_ids)} matches for group {group_id}")
                return photo_ids

        except Exception as e:
            logger.error(f"[GroupService] Live query failed: {e}", exc_info=True)
            return []

    # =========================================================================
    # BACKGROUND INDEXING
    # =========================================================================

    def _enqueue_index_job(
        self,
        group_id: int,
        project_id: int,
        scope: GroupScope
    ):
        """
        Enqueue a background index job for a group.

        Jobs are deduplicated (only one pending job per group+scope).
        """
        try:
            db = self._get_db()
            now = int(time.time())

            with db._connect() as conn:
                # Cancel existing pending jobs for this group+scope
                conn.execute("""
                    UPDATE group_index_jobs
                    SET status = 'cancelled'
                    WHERE group_id = ? AND scope = ? AND status = 'pending'
                """, (group_id, scope.value))

                # Insert new job
                conn.execute("""
                    INSERT INTO group_index_jobs (
                        project_id, group_id, scope, status, created_at
                    ) VALUES (?, ?, ?, 'pending', ?)
                """, (project_id, group_id, scope.value, now))

                conn.commit()

            logger.info(f"[GroupService] Enqueued index job for group {group_id}")

            # Emit started signal and trigger worker
            self.signals.group_index_started.emit(group_id, project_id, scope.value)
            self._run_index_job(group_id, project_id, scope)

        except Exception as e:
            logger.error(f"[GroupService] Failed to enqueue index job: {e}", exc_info=True)

    def _run_index_job(
        self,
        group_id: int,
        project_id: int,
        scope: GroupScope
    ):
        """
        Run indexing job (called from thread pool in production).

        For simplicity, this runs synchronously here. In production,
        use GroupIndexWorker with QThreadPool.
        """
        try:
            self.signals.group_index_progress.emit(group_id, 0.1, "Computing matches...")

            # Compute matches
            photo_ids = self.compute_group_matches_live(project_id, group_id, scope)

            self.signals.group_index_progress.emit(group_id, 0.5, "Caching results...")

            # Store in cache
            db = self._get_db()
            now = int(time.time())

            with db._connect() as conn:
                # Clear old cache
                conn.execute(
                    "DELETE FROM group_asset_matches WHERE group_id = ? AND scope = ?",
                    (group_id, scope.value)
                )

                # Insert new matches
                for photo_id in photo_ids:
                    conn.execute("""
                        INSERT INTO group_asset_matches (
                            project_id, group_id, scope, photo_id, computed_at
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (project_id, group_id, scope.value, photo_id, now))

                # Update job status
                conn.execute("""
                    UPDATE group_index_jobs
                    SET status = 'completed', completed_at = ?, progress = 1.0
                    WHERE group_id = ? AND scope = ? AND status IN ('pending', 'running')
                """, (now, group_id, scope.value))

                conn.commit()

            self.signals.group_index_progress.emit(group_id, 1.0, "Complete")
            self.signals.group_index_completed.emit(group_id, project_id, len(photo_ids))

            logger.info(f"[GroupService] Indexed {len(photo_ids)} photos for group {group_id}")

        except Exception as e:
            logger.error(f"[GroupService] Index job failed: {e}", exc_info=True)
            self.signals.group_index_failed.emit(group_id, project_id, str(e))

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def suggest_group_name(self, member_names: List[str]) -> str:
        """
        Generate a suggested group name from member names.

        Examples:
            ["Ammar", "Alya"] -> "Ammar + Alya"
            ["Mom", "Dad", "Kids"] -> "Mom + Dad + Kids"
        """
        if not member_names:
            return "New Group"
        if len(member_names) <= 3:
            return " + ".join(member_names)
        return f"{member_names[0]} + {member_names[1]} + {len(member_names) - 2} more"

    def get_people_for_group_creation(self, project_id: int) -> List[Dict[str, Any]]:
        """
        Get list of people available for group creation.

        Returns:
            List of people dicts with branch_key, name, thumbnail
        """
        try:
            db = self._get_db()

            with db._connect() as conn:
                cur = conn.execute("""
                    SELECT
                        branch_key,
                        COALESCE(label, branch_key) AS display_name,
                        count AS member_count,
                        rep_thumb_png
                    FROM face_branch_reps
                    WHERE project_id = ?
                    ORDER BY count DESC, display_name ASC
                """, (project_id,))

                people = []
                for row in cur.fetchall():
                    people.append({
                        "branch_key": row[0],
                        "display_name": row[1],
                        "member_count": row[2],
                        "rep_thumb_png": row[3]
                    })

                return people

        except Exception as e:
            logger.error(f"[GroupService] Failed to get people: {e}", exc_info=True)
            return []

    def clear_all_group_caches(self, project_id: int = None):
        """
        Clear all cached group match results.

        This deletes all entries from group_asset_matches table,
        forcing results to be recomputed on next access.

        Args:
            project_id: Optional project ID to clear caches for.
                       If None, clears all caches globally.
        """
        try:
            db = self._get_db()

            with db._connect() as conn:
                if project_id:
                    conn.execute(
                        "DELETE FROM group_asset_matches WHERE project_id = ?",
                        (project_id,)
                    )
                    logger.info(f"[GroupService] Cleared group caches for project {project_id}")
                else:
                    conn.execute("DELETE FROM group_asset_matches")
                    logger.info("[GroupService] Cleared all group caches globally")

                conn.commit()

        except Exception as e:
            logger.error(f"[GroupService] Failed to clear group caches: {e}", exc_info=True)
            raise

    def close(self):
        """Close database connection."""
        if self._db:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None
