# services/stack_generation_service.py
# Version 01.00.00.00 dated 20260115
# Similar-shot and near-duplicate stack generation service
#
# Part of the asset-centric duplicate management system.
# Generates materialized stacks for:
# - Similar shots (burst, series, pose variations)
# - Near-duplicates (pHash-based detection - future)

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
import json
from logging_config import get_logger

from repository.stack_repository import StackRepository
from repository.photo_repository import PhotoRepository

logger = get_logger(__name__)


@dataclass(frozen=True)
class StackGenParams:
    """Parameters for stack generation algorithms."""
    rule_version: str = "1"
    time_window_seconds: int = 10
    min_stack_size: int = 3
    top_k: int = 30
    similarity_threshold: float = 0.92
    candidate_limit_per_photo: int = 300


@dataclass(frozen=True)
class StackGenStats:
    """Statistics from stack generation operation."""
    photos_considered: int
    stacks_created: int
    memberships_created: int
    errors: int


class StackGenerationService:
    """
    Generates materialized stacks for similar shots and near-duplicates.

    This service orchestrates the creation of media_stack and media_stack_member
    records based on similarity detection algorithms.

    No UI responsibilities - pure data processing.

    Algorithms:
    1. Similar shots: Time proximity + visual embedding similarity
    2. Near-duplicates: Perceptual hash distance + embedding confirmation (future)
    """

    def __init__(
        self,
        photo_repo: PhotoRepository,
        stack_repo: StackRepository,
        similarity_service: Optional[Any] = None  # PhotoSimilarityService - optional for now
    ):
        """
        Initialize StackGenerationService.

        Args:
            photo_repo: PhotoRepository instance
            stack_repo: StackRepository instance
            similarity_service: Optional PhotoSimilarityService for embeddings
        """
        self.photo_repo = photo_repo
        self.stack_repo = stack_repo
        self.similarity_service = similarity_service
        self.logger = get_logger(self.__class__.__name__)

    # =========================================================================
    # SIMILAR SHOT STACKS
    # =========================================================================

    def regenerate_similar_shot_stacks(
        self,
        project_id: int,
        params: StackGenParams
    ) -> StackGenStats:
        """
        Generate stacks for similar shots (burst, series, pose variations).

        Contract:
        - Clears existing stacks of type "similar" for the same rule_version
        - Builds new stacks by:
          1) Candidate selection (time window, optional folder, optional device)
          2) Cosine similarity scoring with semantic embeddings
          3) Cluster into stacks, choose representative, persist memberships

        Must be:
        - Deterministic for same params
        - Resumable (optional enhancement - not implemented yet)

        Args:
            project_id: Project ID
            params: Stack generation parameters

        Returns:
            StackGenStats with operation results

        Note: This is a stub implementation. Full implementation requires:
        - Photo embedding extraction (PhotoSimilarityService integration)
        - Time-based candidate filtering
        - Clustering algorithm (DBSCAN, hierarchical, or greedy grouping)
        """
        self.logger.info(f"Starting similar shot stack generation for project {project_id}")
        self.logger.info(f"Parameters: {params}")

        if not self.similarity_service:
            self.logger.error("Cannot generate similar shot stacks: similarity_service not provided")
            return StackGenStats(
                photos_considered=0,
                stacks_created=0,
                memberships_created=0,
                errors=1
            )

        # Step 1: Clear existing stacks
        cleared = self.stack_repo.clear_stacks_by_type(
            project_id=project_id,
            stack_type="similar",
            rule_version=params.rule_version
        )
        self.logger.info(f"Cleared {cleared} existing similar shot stacks")

        # Step 2: Get all photos with embeddings
        # Note: For large projects, might need pagination
        all_photos = self.photo_repo.find_all(
            where_clause="project_id = ? AND created_ts IS NOT NULL",
            params=(project_id,),
            order_by="created_ts ASC"
        )

        if not all_photos:
            self.logger.info("No photos with timestamps found")
            return StackGenStats(
                photos_considered=0,
                stacks_created=0,
                memberships_created=0,
                errors=0
            )

        self.logger.info(f"Found {len(all_photos)} photos with timestamps")

        # Step 3: Find clusters using time window + similarity
        photo_to_cluster: Dict[int, int] = {}  # photo_id -> cluster_id
        all_clusters: List[List[int]] = []
        photos_processed = 0
        errors = 0

        for photo in all_photos:
            photo_id = photo["id"]
            photos_processed += 1

            # Skip if already in a cluster
            if photo_id in photo_to_cluster:
                continue

            # Check if photo has embedding
            embedding = self.similarity_service.get_embedding(photo_id)
            if embedding is None:
                continue

            # Find candidates within time window
            created_ts = photo.get("created_ts")
            if not created_ts:
                continue

            candidates = self._find_time_candidates(
                project_id=project_id,
                reference_timestamp=created_ts,
                time_window_seconds=params.time_window_seconds,
                reference_photo_id=photo_id,
                folder_id=photo.get("folder_id")  # Same folder only
            )

            if not candidates:
                continue

            # Include reference photo in clustering
            all_candidates = [photo] + candidates

            # Cluster by similarity
            clusters = self._cluster_by_similarity(
                photos=all_candidates,
                similarity_threshold=params.similarity_threshold,
                min_cluster_size=params.min_stack_size
            )

            # Register clusters
            for cluster in clusters:
                cluster_id = len(all_clusters)
                all_clusters.append(cluster)

                for pid in cluster:
                    photo_to_cluster[pid] = cluster_id

        self.logger.info(f"Found {len(all_clusters)} similar shot clusters")

        # Step 4: Create stacks in database
        stacks_created = 0
        memberships_created = 0

        for cluster in all_clusters:
            try:
                # Choose representative
                rep_photo_id = self._choose_stack_representative(project_id, cluster)
                if not rep_photo_id:
                    self.logger.warning(f"Could not choose representative for cluster {cluster}")
                    errors += 1
                    continue

                # Create stack
                stack_id = self.stack_repo.create_stack(
                    project_id=project_id,
                    stack_type="similar",
                    representative_photo_id=rep_photo_id,
                    rule_version=params.rule_version,
                    created_by="system"
                )

                stacks_created += 1

                # Add members
                for photo_id in cluster:
                    # Compute similarity score to representative
                    if photo_id == rep_photo_id:
                        similarity_score = 1.0
                    else:
                        rep_emb = self.similarity_service.get_embedding(rep_photo_id)
                        photo_emb = self.similarity_service.get_embedding(photo_id)

                        if rep_emb is not None and photo_emb is not None:
                            import numpy as np
                            # Normalize
                            rep_emb = rep_emb / np.linalg.norm(rep_emb)
                            photo_emb = photo_emb / np.linalg.norm(photo_emb)
                            similarity_score = float(np.dot(rep_emb, photo_emb))
                        else:
                            similarity_score = params.similarity_threshold  # Default

                    self.stack_repo.add_stack_member(
                        project_id=project_id,
                        stack_id=stack_id,
                        photo_id=photo_id,
                        similarity_score=similarity_score
                    )
                    memberships_created += 1

                self.logger.debug(
                    f"Created stack {stack_id} with {len(cluster)} members "
                    f"(representative: {rep_photo_id})"
                )

            except Exception as e:
                self.logger.error(f"Failed to create stack for cluster {cluster}: {e}")
                errors += 1

        self.logger.info(
            f"Similar shot stack generation complete: "
            f"{stacks_created} stacks, {memberships_created} memberships, {errors} errors"
        )

        return StackGenStats(
            photos_considered=photos_processed,
            stacks_created=stacks_created,
            memberships_created=memberships_created,
            errors=errors
        )

    # =========================================================================
    # NEAR-DUPLICATE STACKS
    # =========================================================================

    def regenerate_near_duplicate_stacks(
        self,
        project_id: int,
        params: StackGenParams
    ) -> StackGenStats:
        """
        Generate stacks for near-duplicates (visual similarity despite encoding/resize).

        Recommended approach:
        - Add perceptual hashing (pHash, dHash) as pre-filter
        - Use Hamming distance < threshold for candidates
        - Confirm with embedding cosine similarity

        Reference for pHash:
        http://www.hackerfactor.com/blog/index.php?/archives/432-Looks-Like-It.html

        Args:
            project_id: Project ID
            params: Stack generation parameters

        Returns:
            StackGenStats with operation results

        Note: This is a stub implementation. Full implementation requires:
        - Perceptual hash computation (imagehash library)
        - Hamming distance comparison
        - Embedding confirmation for ambiguous cases
        """
        self.logger.info(f"Starting near-duplicate stack generation for project {project_id}")

        # Step 1: Clear existing stacks
        cleared = self.stack_repo.clear_stacks_by_type(
            project_id=project_id,
            stack_type="near_duplicate",
            rule_version=params.rule_version
        )
        self.logger.info(f"Cleared {cleared} existing near-duplicate stacks")

        # Step 2: STUB - Full implementation needed
        # TODO: Implement perceptual hash-based near-duplicate detection
        #
        # Algorithm outline:
        # 1. Ensure all photos have perceptual_hash (backfill if needed)
        # 2. Group photos by perceptual hash buckets (BK-tree or LSH)
        # 3. Within each bucket, compute Hamming distance
        # 4. If distance < threshold (e.g., 5-10 bits), consider near-duplicate
        # 5. Optionally confirm with embedding similarity
        # 6. Create stacks and add members

        self.logger.warning(
            "Near-duplicate stack generation not fully implemented. "
            "Requires perceptual hashing infrastructure (imagehash library)."
        )

        return StackGenStats(
            photos_considered=0,
            stacks_created=0,
            memberships_created=0,
            errors=0
        )

    # =========================================================================
    # HELPER METHODS (for future implementation)
    # =========================================================================

    def _find_time_candidates(
        self,
        project_id: int,
        reference_timestamp: int,
        time_window_seconds: int,
        reference_photo_id: Optional[int] = None,
        folder_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Find photos within time window of reference timestamp.

        Args:
            project_id: Project ID
            reference_timestamp: Reference Unix timestamp
            time_window_seconds: Time window in seconds (+/- around reference)
            reference_photo_id: Optional photo ID to exclude from results
            folder_id: Optional folder filter (same folder only)

        Returns:
            List of photo dictionaries within time window
        """
        exclude_ids = [reference_photo_id] if reference_photo_id else None

        return self.photo_repo.get_photos_in_time_window(
            project_id=project_id,
            reference_timestamp=reference_timestamp,
            time_window_seconds=time_window_seconds,
            folder_id=folder_id,
            exclude_photo_ids=exclude_ids
        )

    def _cluster_by_similarity(
        self,
        photos: List[Dict[str, Any]],
        similarity_threshold: float,
        min_cluster_size: int
    ) -> List[List[int]]:
        """
        Cluster photos by visual similarity using greedy grouping.

        Algorithm:
        1. Load embeddings for all photos
        2. For each photo, compute cosine similarity with all others
        3. Greedily assign photos to clusters based on threshold
        4. Return clusters meeting minimum size requirement

        Args:
            photos: List of photo dictionaries
            similarity_threshold: Minimum cosine similarity for same cluster (0.0-1.0)
            min_cluster_size: Minimum photos per cluster

        Returns:
            List of clusters (each cluster is a list of photo_ids)

        Note:
            Requires photos to have semantic embeddings. Photos without
            embeddings are skipped.
        """
        if not self.similarity_service:
            self.logger.warning("Cannot cluster: similarity_service not provided")
            return []

        import numpy as np

        # Load embeddings
        photo_embeddings: Dict[int, np.ndarray] = {}
        for photo in photos:
            photo_id = photo["id"]
            embedding = self.similarity_service.get_embedding(photo_id)
            if embedding is not None:
                # Normalize for cosine similarity
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    photo_embeddings[photo_id] = embedding / norm

        if len(photo_embeddings) < min_cluster_size:
            self.logger.debug(f"Not enough photos with embeddings: {len(photo_embeddings)}")
            return []

        # Greedy clustering
        photo_ids = list(photo_embeddings.keys())
        assigned = set()
        clusters = []

        for i, photo_id in enumerate(photo_ids):
            if photo_id in assigned:
                continue

            # Start new cluster with this photo
            cluster = [photo_id]
            assigned.add(photo_id)

            # Find similar photos not yet assigned
            embedding = photo_embeddings[photo_id]

            for other_id in photo_ids[i+1:]:
                if other_id in assigned:
                    continue

                other_embedding = photo_embeddings[other_id]

                # Cosine similarity (dot product of normalized vectors)
                similarity = float(np.dot(embedding, other_embedding))

                if similarity >= similarity_threshold:
                    cluster.append(other_id)
                    assigned.add(other_id)

            # Keep cluster if meets minimum size
            if len(cluster) >= min_cluster_size:
                clusters.append(cluster)
                self.logger.debug(
                    f"Created cluster of {len(cluster)} photos "
                    f"(similarity >= {similarity_threshold:.2f})"
                )

        return clusters

    def _choose_stack_representative(
        self,
        project_id: int,
        photo_ids: List[int]
    ) -> Optional[int]:
        """
        Choose representative photo for stack (deterministic).

        Uses same logic as AssetService.choose_representative_photo:
        1. Higher resolution
        2. Larger file size
        3. Earlier capture date
        4. Non-screenshot
        5. Earlier import

        Args:
            project_id: Project ID
            photo_ids: List of photo IDs in stack

        Returns:
            photo_id of representative, or None
        """
        if not photo_ids:
            return None

        # Fetch photo metadata for all candidates
        photos = []
        for photo_id in photo_ids:
            photo = self.photo_repo.get_by_id(photo_id)
            if photo:
                photos.append(photo)

        if not photos:
            return None

        # Selection key function (same as AssetService)
        def selection_key(photo: Dict[str, Any]) -> Tuple[float, float, float, int, int]:
            """
            Return tuple for sorting (lower = better, so negate values we want maximized).

            Priority order:
            1. Higher resolution (more pixels)
            2. Larger file size (less compression)
            3. Earlier capture date
            4. Non-screenshot paths
            5. Earlier import (lower photo ID)
            """
            # Resolution (prefer higher)
            width = photo.get("width") or 0
            height = photo.get("height") or 0
            resolution = width * height

            # File size (prefer larger)
            file_size = photo.get("size_kb") or 0.0

            # Capture timestamp (prefer earlier)
            if photo.get("created_ts"):
                timestamp = photo.get("created_ts") or float('inf')
            else:
                timestamp = float('inf')

            # Avoid screenshots
            path = photo.get("path") or ""
            is_screenshot = 1 if "screenshot" in path.lower() else 0

            # Earlier import (lower ID = earlier)
            photo_id = photo.get("id") or float('inf')

            return (
                -resolution,      # Higher resolution first (negated)
                -file_size,       # Larger file first (negated)
                timestamp,        # Earlier date first
                is_screenshot,    # Non-screenshots first
                photo_id          # Earlier import first
            )

        # Sort and select best
        sorted_photos = sorted(photos, key=selection_key)
        representative = sorted_photos[0]
        representative_id = representative["id"]

        self.logger.debug(
            f"Chose photo {representative_id} as stack representative "
            f"(resolution: {representative.get('width')}x{representative.get('height')}, "
            f"size: {representative.get('size_kb')} KB)"
        )

        return representative_id

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_stack_summary(self, project_id: int, stack_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get summary statistics for stacks.

        Args:
            project_id: Project ID
            stack_type: Optional filter by stack type

        Returns:
            Dictionary with stack statistics
        """
        total_stacks = self.stack_repo.count_stacks(project_id, stack_type)

        # Get member counts
        stacks = self.stack_repo.list_stacks(project_id, stack_type, limit=1000)
        member_counts = []
        for stack in stacks:
            count = self.stack_repo.count_stack_members(project_id, stack["stack_id"])
            member_counts.append(count)

        avg_members = sum(member_counts) / len(member_counts) if member_counts else 0

        return {
            "project_id": project_id,
            "stack_type": stack_type or "all",
            "total_stacks": total_stacks,
            "average_members_per_stack": round(avg_members, 2),
            "total_memberships": sum(member_counts)
        }
