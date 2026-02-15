# services/people_group_service.py
# Version 1.0.0 dated 20260215
# Service for managing People Groups feature
#
# People Groups allow users to define groups of 2+ people and find photos
# where those people appear together (AND mode) or within a time window.

"""
PeopleGroupService - Groups of people for finding photos together

Based on best practices from Google Photos, Apple Photos, and Adobe Lightroom.
Provides:
- Group CRUD operations (create, read, update, delete)
- Member management (add/remove people from groups)
- Match computation (Together AND, Event Window modes)
- Staleness detection and recomputation triggers

Key Design Decisions:
1. Per-project scoped groups (not global)
2. Precomputed/cached results (no live joins on scroll)
3. Background computation with progress signals
4. Staleness tracking for automatic refresh
"""

from __future__ import annotations
import json
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from logging_config import get_logger

logger = get_logger(__name__)


class PeopleGroupService:
    """
    Service for managing people groups and computing group matches.

    Features:
    - Create/update/delete groups
    - Add/remove members from groups
    - Compute matches (Together AND mode)
    - Compute matches (Event Window mode)
    - Track staleness and trigger recomputation
    """

    def __init__(self, db):
        """
        Initialize PeopleGroupService.

        Args:
            db: ReferenceDB instance
        """
        self.db = db

    # =========================================================================
    # GROUP CRUD OPERATIONS
    # =========================================================================

    def create_group(
        self,
        project_id: int,
        display_name: str,
        member_branch_keys: List[str],
        description: Optional[str] = None,
        icon: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new people group.

        Args:
            project_id: Project ID
            display_name: User-visible name for the group
            member_branch_keys: List of branch_keys (face clusters) to include
            description: Optional description
            icon: Optional emoji/icon

        Returns:
            Dict with group info including 'id' and 'group_key'

        Raises:
            ValueError: If fewer than 2 members provided
        """
        if len(member_branch_keys) < 2:
            raise ValueError("A group must have at least 2 members")

        # Generate unique group key
        group_key = f"group_{uuid.uuid4().hex[:8]}"

        try:
            with self.db._connect() as conn:
                cur = conn.cursor()

                # Insert group
                cur.execute("""
                    INSERT INTO person_groups (project_id, group_key, display_name, description, icon)
                    VALUES (?, ?, ?, ?, ?)
                """, (project_id, group_key, display_name, description, icon))

                group_id = cur.lastrowid

                # Insert members
                for branch_key in member_branch_keys:
                    cur.execute("""
                        INSERT INTO person_group_members (group_id, project_id, branch_key)
                        VALUES (?, ?, ?)
                    """, (group_id, project_id, branch_key))

                # Initialize state as stale (needs computation)
                cur.execute("""
                    INSERT INTO person_group_state (group_id, project_id, is_stale, member_count)
                    VALUES (?, ?, 1, ?)
                """, (group_id, project_id, len(member_branch_keys)))

                conn.commit()

                logger.info(f"[PeopleGroupService] Created group '{display_name}' "
                           f"(id={group_id}, key={group_key}) with {len(member_branch_keys)} members")

                return {
                    'id': group_id,
                    'group_key': group_key,
                    'display_name': display_name,
                    'description': description,
                    'icon': icon,
                    'member_count': len(member_branch_keys),
                    'is_stale': True,
                    'result_count': 0
                }

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to create group: {e}", exc_info=True)
            raise

    def get_group(self, project_id: int, group_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a single group by ID.

        Args:
            project_id: Project ID
            group_id: Group ID

        Returns:
            Group dict or None if not found
        """
        try:
            with self.db._connect() as conn:
                cur = conn.execute("""
                    SELECT
                        g.id, g.group_key, g.display_name, g.description, g.icon,
                        g.created_at, g.updated_at,
                        COALESCE(s.is_stale, 1) as is_stale,
                        COALESCE(s.member_count, 0) as member_count,
                        COALESCE(s.result_count, 0) as result_count,
                        s.last_computed_at,
                        s.match_mode,
                        s.params_json,
                        s.error_message
                    FROM person_groups g
                    LEFT JOIN person_group_state s ON g.id = s.group_id
                    WHERE g.project_id = ? AND g.id = ? AND g.is_deleted = 0
                """, (project_id, group_id))

                row = cur.fetchone()
                if not row:
                    return None

                return {
                    'id': row[0],
                    'group_key': row[1],
                    'display_name': row[2],
                    'description': row[3],
                    'icon': row[4],
                    'created_at': row[5],
                    'updated_at': row[6],
                    'is_stale': bool(row[7]),
                    'member_count': row[8],
                    'result_count': row[9],
                    'last_computed_at': row[10],
                    'match_mode': row[11] or 'together',
                    'params_json': row[12],
                    'error_message': row[13]
                }

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to get group {group_id}: {e}", exc_info=True)
            return None

    def get_all_groups(self, project_id: int, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        Get all groups for a project.

        Args:
            project_id: Project ID
            include_deleted: Include soft-deleted groups

        Returns:
            List of group dicts
        """
        try:
            with self.db._connect() as conn:
                deleted_clause = "" if include_deleted else "AND g.is_deleted = 0"

                cur = conn.execute(f"""
                    SELECT
                        g.id, g.group_key, g.display_name, g.description, g.icon,
                        g.created_at, g.updated_at,
                        COALESCE(s.is_stale, 1) as is_stale,
                        COALESCE(s.member_count, 0) as member_count,
                        COALESCE(s.result_count, 0) as result_count,
                        s.last_computed_at,
                        s.match_mode
                    FROM person_groups g
                    LEFT JOIN person_group_state s ON g.id = s.group_id
                    WHERE g.project_id = ? {deleted_clause}
                    ORDER BY g.display_name ASC
                """, (project_id,))

                groups = []
                for row in cur.fetchall():
                    groups.append({
                        'id': row[0],
                        'group_key': row[1],
                        'display_name': row[2],
                        'description': row[3],
                        'icon': row[4],
                        'created_at': row[5],
                        'updated_at': row[6],
                        'is_stale': bool(row[7]),
                        'member_count': row[8],
                        'result_count': row[9],
                        'last_computed_at': row[10],
                        'match_mode': row[11] or 'together'
                    })

                return groups

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to get groups: {e}", exc_info=True)
            return []

    def update_group(
        self,
        project_id: int,
        group_id: int,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        icon: Optional[str] = None
    ) -> bool:
        """
        Update group metadata.

        Args:
            project_id: Project ID
            group_id: Group ID
            display_name: New name (or None to keep)
            description: New description (or None to keep)
            icon: New icon (or None to keep)

        Returns:
            True if updated successfully
        """
        try:
            updates = []
            params = []

            if display_name is not None:
                updates.append("display_name = ?")
                params.append(display_name)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if icon is not None:
                updates.append("icon = ?")
                params.append(icon)

            if not updates:
                return True  # Nothing to update

            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.extend([project_id, group_id])

            with self.db._connect() as conn:
                conn.execute(f"""
                    UPDATE person_groups
                    SET {', '.join(updates)}
                    WHERE project_id = ? AND id = ?
                """, params)
                conn.commit()

            logger.info(f"[PeopleGroupService] Updated group {group_id}")
            return True

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to update group: {e}", exc_info=True)
            return False

    def delete_group(self, project_id: int, group_id: int, soft_delete: bool = True) -> bool:
        """
        Delete a group.

        Args:
            project_id: Project ID
            group_id: Group ID
            soft_delete: If True, mark as deleted; if False, hard delete

        Returns:
            True if deleted successfully
        """
        try:
            with self.db._connect() as conn:
                if soft_delete:
                    conn.execute("""
                        UPDATE person_groups
                        SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP
                        WHERE project_id = ? AND id = ?
                    """, (project_id, group_id))
                else:
                    # Hard delete cascades to members, matches, and state
                    conn.execute("""
                        DELETE FROM person_groups
                        WHERE project_id = ? AND id = ?
                    """, (project_id, group_id))

                conn.commit()

            logger.info(f"[PeopleGroupService] {'Soft' if soft_delete else 'Hard'} deleted group {group_id}")
            return True

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to delete group: {e}", exc_info=True)
            return False

    # =========================================================================
    # MEMBER MANAGEMENT
    # =========================================================================

    def get_group_members(self, project_id: int, group_id: int) -> List[Dict[str, Any]]:
        """
        Get all members of a group with their face cluster info.

        Args:
            project_id: Project ID
            group_id: Group ID

        Returns:
            List of member dicts with face cluster info
        """
        try:
            with self.db._connect() as conn:
                cur = conn.execute("""
                    SELECT
                        m.branch_key,
                        m.added_at,
                        COALESCE(f.label, m.branch_key) as display_name,
                        f.count as photo_count,
                        f.rep_path,
                        f.rep_thumb_png
                    FROM person_group_members m
                    LEFT JOIN face_branch_reps f
                        ON f.project_id = m.project_id AND f.branch_key = m.branch_key
                    WHERE m.group_id = ? AND m.project_id = ?
                    ORDER BY display_name ASC
                """, (group_id, project_id))

                members = []
                for row in cur.fetchall():
                    members.append({
                        'branch_key': row[0],
                        'added_at': row[1],
                        'display_name': row[2],
                        'photo_count': row[3] or 0,
                        'rep_path': row[4],
                        'rep_thumb_png': row[5]
                    })

                return members

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to get members: {e}", exc_info=True)
            return []

    def add_member(self, project_id: int, group_id: int, branch_key: str) -> bool:
        """
        Add a person to a group.

        Args:
            project_id: Project ID
            group_id: Group ID
            branch_key: Face cluster branch_key to add

        Returns:
            True if added successfully
        """
        try:
            with self.db._connect() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO person_group_members (group_id, project_id, branch_key)
                    VALUES (?, ?, ?)
                """, (group_id, project_id, branch_key))

                # Mark group as stale (needs recomputation)
                self._mark_group_stale(conn, group_id)

                # Update member count
                conn.execute("""
                    UPDATE person_group_state
                    SET member_count = (
                        SELECT COUNT(*) FROM person_group_members WHERE group_id = ?
                    )
                    WHERE group_id = ?
                """, (group_id, group_id))

                conn.commit()

            logger.info(f"[PeopleGroupService] Added member {branch_key} to group {group_id}")
            return True

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to add member: {e}", exc_info=True)
            return False

    def remove_member(self, project_id: int, group_id: int, branch_key: str) -> bool:
        """
        Remove a person from a group.

        Args:
            project_id: Project ID
            group_id: Group ID
            branch_key: Face cluster branch_key to remove

        Returns:
            True if removed successfully
        """
        try:
            with self.db._connect() as conn:
                conn.execute("""
                    DELETE FROM person_group_members
                    WHERE group_id = ? AND project_id = ? AND branch_key = ?
                """, (group_id, project_id, branch_key))

                # Mark group as stale
                self._mark_group_stale(conn, group_id)

                # Update member count
                conn.execute("""
                    UPDATE person_group_state
                    SET member_count = (
                        SELECT COUNT(*) FROM person_group_members WHERE group_id = ?
                    )
                    WHERE group_id = ?
                """, (group_id, group_id))

                conn.commit()

            logger.info(f"[PeopleGroupService] Removed member {branch_key} from group {group_id}")
            return True

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to remove member: {e}", exc_info=True)
            return False

    # =========================================================================
    # MATCH COMPUTATION
    # =========================================================================

    def compute_together_matches(
        self,
        project_id: int,
        group_id: int,
        min_confidence: float = 0.5,
        include_videos: bool = False,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Compute 'together' matches: photos where ALL group members appear.

        This is the default AND mode - find photos containing all people in the group.

        Args:
            project_id: Project ID
            group_id: Group ID
            min_confidence: Minimum face detection confidence
            include_videos: Include video frames (future)
            progress_callback: Optional callback(current, total, message)

        Returns:
            Dict with computation results
        """
        start_time = time.time()

        try:
            with self.db._connect() as conn:
                cur = conn.cursor()

                # Get group members
                cur.execute("""
                    SELECT branch_key FROM person_group_members
                    WHERE group_id = ? AND project_id = ?
                """, (group_id, project_id))
                members = [row[0] for row in cur.fetchall()]

                if len(members) < 2:
                    return {
                        'success': False,
                        'error': 'Group must have at least 2 members',
                        'match_count': 0
                    }

                member_count = len(members)

                if progress_callback:
                    progress_callback(0, 100, f"Finding photos with {member_count} people together...")

                # Find photos where ALL members appear
                # This is the key AND query - count distinct persons per photo
                # and only keep photos where count equals total members
                placeholders = ','.join(['?'] * len(members))

                cur.execute(f"""
                    SELECT
                        fc.image_path,
                        pm.id as photo_id,
                        COUNT(DISTINCT fc.branch_key) as person_count
                    FROM face_crops fc
                    JOIN photo_metadata pm ON pm.path = fc.image_path AND pm.project_id = fc.project_id
                    WHERE fc.project_id = ?
                      AND fc.branch_key IN ({placeholders})
                      AND fc.confidence >= ?
                    GROUP BY fc.image_path
                    HAVING COUNT(DISTINCT fc.branch_key) = ?
                """, (project_id, *members, min_confidence, member_count))

                matching_photos = cur.fetchall()

                if progress_callback:
                    progress_callback(50, 100, f"Found {len(matching_photos)} matching photos")

                # Clear previous matches for this group/mode
                cur.execute("""
                    DELETE FROM person_group_matches
                    WHERE group_id = ? AND match_mode = 'together'
                """, (group_id,))

                # Insert new matches
                match_count = 0
                for image_path, photo_id, person_count in matching_photos:
                    cur.execute("""
                        INSERT INTO person_group_matches
                            (group_id, project_id, asset_type, asset_id, asset_path, match_mode)
                        VALUES (?, ?, 'photo', ?, ?, 'together')
                    """, (group_id, project_id, photo_id, image_path))
                    match_count += 1

                if progress_callback:
                    progress_callback(90, 100, f"Saved {match_count} matches")

                # Update state
                params_json = json.dumps({
                    'min_confidence': min_confidence,
                    'include_videos': include_videos
                })

                cur.execute("""
                    UPDATE person_group_state
                    SET
                        is_stale = 0,
                        last_computed_at = CURRENT_TIMESTAMP,
                        match_mode = 'together',
                        result_count = ?,
                        params_json = ?,
                        error_message = NULL
                    WHERE group_id = ?
                """, (match_count, params_json, group_id))

                conn.commit()

                duration = time.time() - start_time

                if progress_callback:
                    progress_callback(100, 100, f"Complete: {match_count} photos")

                logger.info(f"[PeopleGroupService] Together matches for group {group_id}: "
                           f"{match_count} photos with {member_count} people in {duration:.2f}s")

                return {
                    'success': True,
                    'match_count': match_count,
                    'member_count': member_count,
                    'duration_s': duration
                }

        except Exception as e:
            logger.error(f"[PeopleGroupService] Together match computation failed: {e}", exc_info=True)

            # Record error in state
            try:
                with self.db._connect() as conn:
                    conn.execute("""
                        UPDATE person_group_state
                        SET error_message = ?
                        WHERE group_id = ?
                    """, (str(e), group_id))
                    conn.commit()
            except:
                pass

            return {
                'success': False,
                'error': str(e),
                'match_count': 0
            }

    def compute_event_window_matches(
        self,
        project_id: int,
        group_id: int,
        window_seconds: int = 30,
        min_confidence: float = 0.5,
        include_videos: bool = False,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Compute 'event_window' matches: photos taken within a time window
        where all group members appear somewhere in that window.

        This mode finds photos from events where the group was together,
        even if not all in the same photo.

        Args:
            project_id: Project ID
            group_id: Group ID
            window_seconds: Time window in seconds (default 30s)
            min_confidence: Minimum face detection confidence
            include_videos: Include video frames (future)
            progress_callback: Optional callback(current, total, message)

        Returns:
            Dict with computation results
        """
        start_time = time.time()

        try:
            with self.db._connect() as conn:
                cur = conn.cursor()

                # Get group members
                cur.execute("""
                    SELECT branch_key FROM person_group_members
                    WHERE group_id = ? AND project_id = ?
                """, (group_id, project_id))
                members = [row[0] for row in cur.fetchall()]

                if len(members) < 2:
                    return {
                        'success': False,
                        'error': 'Group must have at least 2 members',
                        'match_count': 0
                    }

                member_count = len(members)

                if progress_callback:
                    progress_callback(0, 100, f"Finding event windows with {member_count} people...")

                # Step 1: Get all photo timestamps for each member
                # Build a timeline of when each person appears
                placeholders = ','.join(['?'] * len(members))

                cur.execute(f"""
                    SELECT
                        fc.branch_key,
                        pm.created_ts,
                        pm.id as photo_id,
                        pm.path
                    FROM face_crops fc
                    JOIN photo_metadata pm ON pm.path = fc.image_path AND pm.project_id = fc.project_id
                    WHERE fc.project_id = ?
                      AND fc.branch_key IN ({placeholders})
                      AND fc.confidence >= ?
                      AND pm.created_ts IS NOT NULL
                    ORDER BY pm.created_ts ASC
                """, (project_id, *members, min_confidence))

                events = cur.fetchall()

                if not events:
                    return {
                        'success': True,
                        'match_count': 0,
                        'member_count': member_count,
                        'message': 'No photos with timestamps found'
                    }

                if progress_callback:
                    progress_callback(20, 100, f"Analyzing {len(events)} photo events...")

                # Step 2: Find event windows where all members appear
                # Sliding window algorithm
                matching_photos = set()

                # Build person -> timestamp mapping
                person_times: Dict[str, List[Tuple[int, int, str]]] = {m: [] for m in members}
                for branch_key, ts, photo_id, path in events:
                    if ts is not None:
                        person_times[branch_key].append((ts, photo_id, path))

                # Sort each person's timeline
                for m in members:
                    person_times[m].sort(key=lambda x: x[0])

                # Use the first member's timeline as anchor and check windows
                if not person_times[members[0]]:
                    return {
                        'success': True,
                        'match_count': 0,
                        'member_count': member_count,
                        'message': 'No photos found for anchor person'
                    }

                # For each photo of the anchor person, check if all others
                # appear within the window
                anchor_member = members[0]
                other_members = members[1:]

                for anchor_ts, anchor_photo_id, anchor_path in person_times[anchor_member]:
                    window_start = anchor_ts - window_seconds
                    window_end = anchor_ts + window_seconds

                    # Check if all other members appear in this window
                    all_present = True
                    window_photos = [(anchor_photo_id, anchor_path)]

                    for other_member in other_members:
                        found_in_window = False
                        for other_ts, other_photo_id, other_path in person_times[other_member]:
                            if window_start <= other_ts <= window_end:
                                found_in_window = True
                                window_photos.append((other_photo_id, other_path))
                                break

                        if not found_in_window:
                            all_present = False
                            break

                    if all_present:
                        # Add all photos in this window
                        for photo_id, path in window_photos:
                            matching_photos.add((photo_id, path))

                if progress_callback:
                    progress_callback(70, 100, f"Found {len(matching_photos)} matching photos")

                # Clear previous matches for this group/mode
                cur.execute("""
                    DELETE FROM person_group_matches
                    WHERE group_id = ? AND match_mode = 'event_window'
                """, (group_id,))

                # Insert new matches
                match_count = 0
                for photo_id, path in matching_photos:
                    cur.execute("""
                        INSERT OR IGNORE INTO person_group_matches
                            (group_id, project_id, asset_type, asset_id, asset_path, match_mode)
                        VALUES (?, ?, 'photo', ?, ?, 'event_window')
                    """, (group_id, project_id, photo_id, path))
                    match_count += 1

                if progress_callback:
                    progress_callback(90, 100, f"Saved {match_count} matches")

                # Update state
                params_json = json.dumps({
                    'window_seconds': window_seconds,
                    'min_confidence': min_confidence,
                    'include_videos': include_videos
                })

                cur.execute("""
                    UPDATE person_group_state
                    SET
                        is_stale = 0,
                        last_computed_at = CURRENT_TIMESTAMP,
                        match_mode = 'event_window',
                        result_count = ?,
                        params_json = ?,
                        error_message = NULL
                    WHERE group_id = ?
                """, (match_count, params_json, group_id))

                conn.commit()

                duration = time.time() - start_time

                if progress_callback:
                    progress_callback(100, 100, f"Complete: {match_count} photos")

                logger.info(f"[PeopleGroupService] Event window matches for group {group_id}: "
                           f"{match_count} photos within {window_seconds}s window in {duration:.2f}s")

                return {
                    'success': True,
                    'match_count': match_count,
                    'member_count': member_count,
                    'duration_s': duration,
                    'window_seconds': window_seconds
                }

        except Exception as e:
            logger.error(f"[PeopleGroupService] Event window computation failed: {e}", exc_info=True)

            # Record error in state
            try:
                with self.db._connect() as conn:
                    conn.execute("""
                        UPDATE person_group_state
                        SET error_message = ?
                        WHERE group_id = ?
                    """, (str(e), group_id))
                    conn.commit()
            except:
                pass

            return {
                'success': False,
                'error': str(e),
                'match_count': 0
            }

    def get_group_matches(
        self,
        project_id: int,
        group_id: int,
        match_mode: str = 'together',
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get cached matches for a group.

        Args:
            project_id: Project ID
            group_id: Group ID
            match_mode: 'together' or 'event_window'
            limit: Max results (None for all)
            offset: Results offset for pagination

        Returns:
            List of match dicts with photo info
        """
        try:
            with self.db._connect() as conn:
                limit_clause = f"LIMIT {limit}" if limit else ""
                offset_clause = f"OFFSET {offset}" if offset else ""

                cur = conn.execute(f"""
                    SELECT
                        m.asset_id,
                        m.asset_path,
                        m.asset_type,
                        m.score,
                        m.matched_at,
                        pm.created_ts,
                        pm.created_date
                    FROM person_group_matches m
                    LEFT JOIN photo_metadata pm ON pm.id = m.asset_id AND m.asset_type = 'photo'
                    WHERE m.group_id = ? AND m.project_id = ? AND m.match_mode = ?
                    ORDER BY pm.created_ts DESC
                    {limit_clause}
                    {offset_clause}
                """, (group_id, project_id, match_mode))

                matches = []
                for row in cur.fetchall():
                    matches.append({
                        'asset_id': row[0],
                        'asset_path': row[1],
                        'asset_type': row[2],
                        'score': row[3],
                        'matched_at': row[4],
                        'created_ts': row[5],
                        'created_date': row[6]
                    })

                return matches

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to get matches: {e}", exc_info=True)
            return []

    # =========================================================================
    # STALENESS MANAGEMENT
    # =========================================================================

    def _mark_group_stale(self, conn, group_id: int) -> None:
        """Mark a group as needing recomputation."""
        conn.execute("""
            UPDATE person_group_state
            SET is_stale = 1
            WHERE group_id = ?
        """, (group_id,))

    def mark_groups_stale_for_person(self, project_id: int, branch_key: str) -> int:
        """
        Mark all groups containing a person as stale.

        Called when:
        - Face clustering runs
        - Person merge happens
        - Photos are added/deleted

        Args:
            project_id: Project ID
            branch_key: Person's branch_key

        Returns:
            Number of groups marked stale
        """
        try:
            with self.db._connect() as conn:
                cur = conn.execute("""
                    UPDATE person_group_state
                    SET is_stale = 1
                    WHERE group_id IN (
                        SELECT group_id FROM person_group_members
                        WHERE project_id = ? AND branch_key = ?
                    )
                """, (project_id, branch_key))

                affected = cur.rowcount
                conn.commit()

                if affected > 0:
                    logger.info(f"[PeopleGroupService] Marked {affected} groups stale "
                               f"for person {branch_key}")

                return affected

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to mark stale: {e}", exc_info=True)
            return 0

    def mark_all_groups_stale(self, project_id: int) -> int:
        """
        Mark all groups in a project as stale.

        Called when:
        - Photo scan completes
        - Face detection/clustering completes

        Args:
            project_id: Project ID

        Returns:
            Number of groups marked stale
        """
        try:
            with self.db._connect() as conn:
                cur = conn.execute("""
                    UPDATE person_group_state
                    SET is_stale = 1
                    WHERE project_id = ?
                """, (project_id,))

                affected = cur.rowcount
                conn.commit()

                if affected > 0:
                    logger.info(f"[PeopleGroupService] Marked {affected} groups stale "
                               f"in project {project_id}")

                return affected

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to mark all stale: {e}", exc_info=True)
            return 0

    def get_stale_groups(self, project_id: int) -> List[int]:
        """
        Get list of group IDs that need recomputation.

        Args:
            project_id: Project ID

        Returns:
            List of group IDs
        """
        try:
            with self.db._connect() as conn:
                cur = conn.execute("""
                    SELECT group_id FROM person_group_state
                    WHERE project_id = ? AND is_stale = 1
                """, (project_id,))

                return [row[0] for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"[PeopleGroupService] Failed to get stale groups: {e}", exc_info=True)
            return []
