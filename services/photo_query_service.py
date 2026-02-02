# services/photo_query_service.py
# Paged photo query service for both layouts.
#
# Provides count_photos() and fetch_page() with stable ordering so that
# both GoogleLayout and CurrentLayout can load large result sets in
# incremental pages without duplicates or missing rows.
#
# Thresholds are centralised here and can be tuned from preferences.

import logging
from typing import Optional, Dict, Any, List

from reference_db import ReferenceDB

logger = logging.getLogger(__name__)

# ── Tunable thresholds ───────────────────────────────────────────────
SMALL_THRESHOLD = 3_000      # below this: load everything in one shot
PAGE_SIZE = 250              # rows per page (base grid)
PREFETCH_PAGES = 2           # keep N pages ahead of the viewport
MAX_IN_MEMORY_ROWS = 10_000  # upper cap to avoid OOM


class PhotoQueryService:
    """
    Centralised photo-query backend used by both layouts.

    Usage:
        svc = PhotoQueryService()
        total = svc.count_photos(project_id, filters)
        rows  = svc.fetch_page(project_id, filters, offset=0, limit=250)
    """

    def __init__(self):
        self.db = ReferenceDB()

    # ── Public API ───────────────────────────────────────────────────

    def count_photos(
        self,
        project_id: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Return total matching photo+video count for *project_id* + *filters*."""
        filters = filters or {}
        sql, params = self._build_count_sql(project_id, filters)
        with self.db._connect() as conn:
            row = conn.execute(sql, params).fetchone()
            total = row[0] if row else 0
        logger.debug(
            "[PhotoQueryService] count_photos pid=%d filters=%s -> %d",
            project_id, filters, total,
        )
        return total

    def fetch_page(
        self,
        project_id: int,
        filters: Optional[Dict[str, Any]] = None,
        offset: int = 0,
        limit: int = PAGE_SIZE,
    ) -> List[Dict[str, Any]]:
        """
        Fetch a page of rows sorted by created_date DESC, rowid DESC.

        Returns list of dicts: {path, date_taken, width, height, media_type}.
        """
        filters = filters or {}
        sql, params = self._build_page_sql(project_id, filters, offset, limit)
        with self.db._connect() as conn:
            cur = conn.execute(sql, params)
            columns = [d[0] for d in cur.description]
            rows = [dict(zip(columns, r)) for r in cur.fetchall()]
        logger.debug(
            "[PhotoQueryService] fetch_page pid=%d offset=%d limit=%d -> %d rows",
            project_id, offset, limit, len(rows),
        )
        return rows

    def should_page(self, total: int) -> bool:
        """Return True if the result set is large enough to warrant paging."""
        return total > SMALL_THRESHOLD

    # ── SQL builders ─────────────────────────────────────────────────

    def _build_where(
        self, project_id: int, filters: Dict[str, Any]
    ) -> tuple[str, list]:
        """Build shared WHERE clause fragments + params."""
        clauses = ["pi.project_id = ?"]
        params: list = [project_id]

        if filters.get("year"):
            clauses.append("strftime('%Y', m.created_date) = ?")
            params.append(str(filters["year"]))
        if filters.get("month"):
            clauses.append("strftime('%m', m.created_date) = ?")
            params.append(str(filters["month"]).zfill(2))
        if filters.get("day"):
            clauses.append("strftime('%d', m.created_date) = ?")
            params.append(str(filters["day"]).zfill(2))
        if filters.get("folder"):
            clauses.append("m.path LIKE ?")
            params.append(filters["folder"].rstrip("/\\") + "%")
        if filters.get("person_branch_key"):
            clauses.append(
                "m.path IN ("
                "  SELECT DISTINCT fc.image_path FROM face_crops fc"
                "  WHERE fc.project_id = ? AND fc.branch_key = ?"
                ")"
            )
            params.extend([project_id, filters["person_branch_key"]])

        return " AND ".join(clauses), params

    def _build_count_sql(
        self, project_id: int, filters: Dict[str, Any]
    ) -> tuple[str, list]:
        where, params = self._build_where(project_id, filters)

        # Photos
        photo_sql = (
            "SELECT COUNT(DISTINCT m.path) FROM photo_metadata m "
            "JOIN project_images pi ON m.path = pi.image_path "
            f"WHERE {where}"
        )

        # Videos (skip person filter — face_crops is photo-only)
        if not filters.get("person_branch_key"):
            video_where = where.replace("m.path", "v.path").replace(
                "m.created_date", "v.created_date"
            )
            video_sql = (
                "SELECT COUNT(DISTINCT v.path) FROM video_metadata v "
                "JOIN project_videos pv ON v.path = pv.video_path "
                f"WHERE {video_where.replace('pi.project_id', 'pv.project_id')}"
            )
            sql = f"SELECT (({photo_sql}) + ({video_sql}))"
            params = params + params  # second set for video sub-query
        else:
            sql = photo_sql

        return sql, params

    def _build_page_sql(
        self,
        project_id: int,
        filters: Dict[str, Any],
        offset: int,
        limit: int,
    ) -> tuple[str, list]:
        where_photo, params_photo = self._build_where(project_id, filters)

        # Photos sub-query
        photo_sql = (
            "SELECT DISTINCT m.path, m.created_date AS date_taken, "
            "m.width, m.height, 'photo' AS media_type "
            "FROM photo_metadata m "
            "JOIN project_images pi ON m.path = pi.image_path "
            f"WHERE {where_photo}"
        )

        if not filters.get("person_branch_key"):
            # Videos sub-query (mirror WHERE for video tables)
            where_video = where_photo.replace("m.path", "v.path").replace(
                "m.created_date", "v.created_date"
            ).replace("m.width", "v.width").replace("m.height", "v.height")
            where_video = where_video.replace("pi.project_id", "pv.project_id")

            video_sql = (
                "SELECT DISTINCT v.path, v.created_date AS date_taken, "
                "v.width, v.height, 'video' AS media_type "
                "FROM video_metadata v "
                "JOIN project_videos pv ON v.path = pv.video_path "
                f"WHERE {where_video}"
            )

            union_sql = (
                f"SELECT * FROM ({photo_sql} UNION ALL {video_sql}) "
                "ORDER BY date_taken DESC, path DESC "
                "LIMIT ? OFFSET ?"
            )
            all_params = params_photo + params_photo + [limit, offset]
        else:
            union_sql = (
                f"{photo_sql} "
                "ORDER BY date_taken DESC, path DESC "
                "LIMIT ? OFFSET ?"
            )
            all_params = params_photo + [limit, offset]

        return union_sql, all_params
