# repository/asset_repository.py
# Version 01.00.00.00 dated 20260115
# Repository for media_asset and media_instance
#
# Part of the asset-centric duplicate management system.
# Manages:
# - media_asset: unique content identity (content_hash)
# - media_instance: physical file occurrences linked to photo_metadata

from typing import Optional, List, Dict, Any, Tuple
from .base_repository import BaseRepository, DatabaseConnection
from logging_config import get_logger

logger = get_logger(__name__)


class AssetRepository(BaseRepository):
    """
    AssetRepository manages asset-centric identity.

    Tables:
    - media_asset: (project_id, content_hash) unique identity
    - media_instance: links existing photo_metadata rows to assets

    Responsibilities:
    - Create and link assets to photo instances
    - Find duplicate assets (multiple instances of same content_hash)
    - Manage representative photo selection
    - Provide traceability (source_device, source_path, import_session)
    """

    def __init__(self, db: DatabaseConnection):
        """
        Initialize AssetRepository.

        Args:
            db: DatabaseConnection instance
        """
        super().__init__(db)

    def _table_name(self) -> str:
        """Primary table name managed by this repository."""
        return "media_asset"

    # =========================================================================
    # ASSET OPERATIONS
    # =========================================================================

    def get_asset_by_hash(self, project_id: int, content_hash: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve media_asset by (project_id, content_hash).

        Args:
            project_id: Project ID
            content_hash: SHA256 or equivalent content hash

        Returns:
            Asset dictionary or None if not found
        """
        sql = """
            SELECT asset_id, project_id, content_hash, perceptual_hash, representative_photo_id,
                   created_at, updated_at
            FROM media_asset
            WHERE project_id = ? AND content_hash = ?
        """
        with self._db_connection.get_connection(read_only=True) as conn:
            cur = conn.execute(sql, (project_id, content_hash))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_asset_by_id(self, project_id: int, asset_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve media_asset by asset_id.

        Args:
            project_id: Project ID
            asset_id: Asset ID

        Returns:
            Asset dictionary or None if not found
        """
        sql = """
            SELECT asset_id, project_id, content_hash, perceptual_hash, representative_photo_id,
                   created_at, updated_at
            FROM media_asset
            WHERE project_id = ? AND asset_id = ?
        """
        with self._db_connection.get_connection(read_only=True) as conn:
            cur = conn.execute(sql, (project_id, asset_id))
            row = cur.fetchone()
            return dict(row) if row else None

    def create_asset_if_missing(
        self,
        project_id: int,
        content_hash: str,
        representative_photo_id: Optional[int] = None,
        perceptual_hash: Optional[str] = None
    ) -> int:
        """
        Insert asset if missing, return asset_id.

        Contract:
        - Must be idempotent (safe to call multiple times with same hash)
        - Must not throw on duplicate, returns existing asset_id
        - Uses INSERT OR IGNORE for idempotency

        Args:
            project_id: Project ID
            content_hash: SHA256 or equivalent content hash
            representative_photo_id: Optional representative photo ID
            perceptual_hash: Optional perceptual hash (pHash/dHash)

        Returns:
            asset_id (existing or newly created)
        """
        with self._db_connection.get_connection(read_only=False) as conn:
            # Try to insert, ignore if already exists
            conn.execute(
                """
                INSERT OR IGNORE INTO media_asset (project_id, content_hash, representative_photo_id, perceptual_hash)
                VALUES (?, ?, ?, ?)
                """,
                (project_id, content_hash, representative_photo_id, perceptual_hash)
            )

            # Fetch the asset_id (either just inserted or already existing)
            cur = conn.execute(
                """
                SELECT asset_id FROM media_asset
                WHERE project_id = ? AND content_hash = ?
                """,
                (project_id, content_hash)
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"Failed to create or fetch media_asset for hash {content_hash[:16]}...")

            conn.commit()
            return int(row["asset_id"])

    def set_representative_photo(self, project_id: int, asset_id: int, photo_id: int) -> None:
        """
        Set representative_photo_id for an asset.

        Args:
            project_id: Project ID
            asset_id: Asset ID
            photo_id: Photo ID to set as representative
        """
        with self._db_connection.get_connection(read_only=False) as conn:
            conn.execute(
                """
                UPDATE media_asset
                SET representative_photo_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ? AND asset_id = ?
                """,
                (photo_id, project_id, asset_id)
            )
            conn.commit()

        self.logger.debug(f"Set representative photo {photo_id} for asset {asset_id}")

    def set_perceptual_hash(self, project_id: int, asset_id: int, perceptual_hash: str) -> None:
        """
        Set perceptual_hash for an asset (used during backfill).

        Args:
            project_id: Project ID
            asset_id: Asset ID
            perceptual_hash: Perceptual hash string (pHash/dHash)
        """
        with self._db_connection.get_connection(read_only=False) as conn:
            conn.execute(
                """
                UPDATE media_asset
                SET perceptual_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ? AND asset_id = ?
                """,
                (perceptual_hash, project_id, asset_id)
            )
            conn.commit()

    def list_duplicate_assets(self, project_id: int, min_instances: int = 2) -> List[Dict[str, Any]]:
        """
        List assets that have at least min_instances instances (duplicates).

        Used to populate "Duplicates" utility view in UI.

        Args:
            project_id: Project ID
            min_instances: Minimum number of instances to be considered duplicate (default: 2)

        Returns:
            List of asset dictionaries with instance_count
        """
        sql = """
            SELECT a.asset_id, a.content_hash, a.representative_photo_id, a.perceptual_hash,
                   COUNT(i.instance_id) AS instance_count
            FROM media_asset a
            JOIN media_instance i ON i.asset_id = a.asset_id AND i.project_id = a.project_id
            WHERE a.project_id = ?
            GROUP BY a.asset_id
            HAVING COUNT(i.instance_id) >= ?
            ORDER BY instance_count DESC
        """
        with self._db_connection.get_connection(read_only=True) as conn:
            cur = conn.execute(sql, (project_id, min_instances))
            return [dict(r) for r in cur.fetchall()]

    # =========================================================================
    # INSTANCE OPERATIONS
    # =========================================================================

    def link_instance(
        self,
        project_id: int,
        asset_id: int,
        photo_id: int,
        source_device_id: Optional[str] = None,
        source_path: Optional[str] = None,
        import_session_id: Optional[str] = None,
        file_size: Optional[int] = None
    ) -> None:
        """
        Create media_instance linking photo_metadata.id to an asset.

        Contract:
        - One photo_id must map to exactly one instance per project
        - Uses INSERT OR REPLACE to allow re-linking in repair/backfill flows
        - Idempotent (safe to call multiple times)

        Args:
            project_id: Project ID
            asset_id: Asset ID
            photo_id: Photo metadata ID
            source_device_id: Optional device ID (for traceability)
            source_path: Optional source path on device
            import_session_id: Optional import session ID
            file_size: Optional file size in bytes
        """
        with self._db_connection.get_connection(read_only=False) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO media_instance
                (project_id, asset_id, photo_id, source_device_id, source_path, import_session_id, file_size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, asset_id, photo_id, source_device_id, source_path, import_session_id, file_size)
            )
            conn.commit()

        self.logger.debug(f"Linked photo {photo_id} to asset {asset_id} as instance")

    def get_instance_by_photo(self, project_id: int, photo_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve media_instance by photo_id.

        Args:
            project_id: Project ID
            photo_id: Photo metadata ID

        Returns:
            Instance dictionary or None if not found
        """
        sql = """
            SELECT instance_id, project_id, asset_id, photo_id, source_device_id, source_path,
                   import_session_id, file_size, created_at
            FROM media_instance
            WHERE project_id = ? AND photo_id = ?
        """
        with self._db_connection.get_connection(read_only=True) as conn:
            cur = conn.execute(sql, (project_id, photo_id))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_asset_instances(self, project_id: int, asset_id: int) -> List[Dict[str, Any]]:
        """
        Return all instances for an asset, including traceability fields.

        Args:
            project_id: Project ID
            asset_id: Asset ID

        Returns:
            List of instance dictionaries ordered by created_at (import order)
        """
        sql = """
            SELECT i.instance_id, i.photo_id, i.source_device_id, i.source_path,
                   i.import_session_id, i.file_size, i.created_at
            FROM media_instance i
            WHERE i.project_id = ? AND i.asset_id = ?
            ORDER BY i.created_at ASC
        """
        with self._db_connection.get_connection(read_only=True) as conn:
            cur = conn.execute(sql, (project_id, asset_id))
            return [dict(r) for r in cur.fetchall()]

    def count_instances_for_asset(self, project_id: int, asset_id: int) -> int:
        """
        Count number of instances for an asset.

        Args:
            project_id: Project ID
            asset_id: Asset ID

        Returns:
            Number of instances
        """
        sql = """
            SELECT COUNT(*) AS count
            FROM media_instance
            WHERE project_id = ? AND asset_id = ?
        """
        with self._db_connection.get_connection(read_only=True) as conn:
            cur = conn.execute(sql, (project_id, asset_id))
            row = cur.fetchone()
            return int(row["count"]) if row else 0

    # =========================================================================
    # BACKFILL SUPPORT
    # =========================================================================

    def get_photos_without_instance(self, project_id: int, limit: int = 500) -> List[Dict[str, Any]]:
        """
        Find photos that don't have a media_instance yet (for backfill).

        Args:
            project_id: Project ID
            limit: Maximum number of photos to return

        Returns:
            List of photo_metadata dictionaries without instances
        """
        sql = """
            SELECT pm.id, pm.path, pm.file_hash, pm.size_kb, pm.project_id
            FROM photo_metadata pm
            LEFT JOIN media_instance mi ON mi.photo_id = pm.id AND mi.project_id = pm.project_id
            WHERE pm.project_id = ? AND mi.instance_id IS NULL
            LIMIT ?
        """
        with self._db_connection.get_connection(read_only=True) as conn:
            cur = conn.execute(sql, (project_id, limit))
            return [dict(r) for r in cur.fetchall()]

    def count_photos_without_instance(self, project_id: int) -> int:
        """
        Count photos without media_instance (for backfill progress tracking).

        Args:
            project_id: Project ID

        Returns:
            Number of photos without instances
        """
        sql = """
            SELECT COUNT(*) AS count
            FROM photo_metadata pm
            LEFT JOIN media_instance mi ON mi.photo_id = pm.id AND mi.project_id = pm.project_id
            WHERE pm.project_id = ? AND mi.instance_id IS NULL
        """
        with self._db_connection.get_connection(read_only=True) as conn:
            cur = conn.execute(sql, (project_id,))
            row = cur.fetchone()
            return int(row["count"]) if row else 0
