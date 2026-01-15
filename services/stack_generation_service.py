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

        # Step 1: Clear existing stacks
        cleared = self.stack_repo.clear_stacks_by_type(
            project_id=project_id,
            stack_type="similar",
            rule_version=params.rule_version
        )
        self.logger.info(f"Cleared {cleared} existing similar shot stacks")

        # Step 2: STUB - Full implementation needed
        # TODO: Implement candidate selection and clustering
        #
        # Algorithm outline:
        # 1. Get all photos with embeddings and timestamps
        # 2. For each photo, find candidates within time_window
        # 3. Compute cosine similarity for candidates
        # 4. Cluster photos with similarity > threshold
        # 5. For each cluster >= min_stack_size:
        #    - Create media_stack
        #    - Choose representative (deterministic selection)
        #    - Add members with similarity scores

        self.logger.warning(
            "Similar shot stack generation not fully implemented. "
            "Requires PhotoSimilarityService integration and clustering algorithm."
        )

        return StackGenStats(
            photos_considered=0,
            stacks_created=0,
            memberships_created=0,
            errors=0
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
        time_window_seconds: int
    ) -> List[Dict[str, Any]]:
        """
        Find photos within time window of reference timestamp.

        Args:
            project_id: Project ID
            reference_timestamp: Reference Unix timestamp
            time_window_seconds: Time window in seconds (+/- around reference)

        Returns:
            List of photo dictionaries within time window
        """
        # TODO: Implement using photo_repo query with created_ts
        # SELECT * FROM photo_metadata
        # WHERE project_id = ? AND created_ts BETWEEN ? AND ?
        raise NotImplementedError("Time-based candidate selection not implemented")

    def _cluster_by_similarity(
        self,
        photos: List[Dict[str, Any]],
        similarity_threshold: float,
        min_cluster_size: int
    ) -> List[List[int]]:
        """
        Cluster photos by visual similarity.

        Args:
            photos: List of photo dictionaries with embeddings
            similarity_threshold: Minimum similarity for same cluster
            min_cluster_size: Minimum photos per cluster

        Returns:
            List of clusters (each cluster is a list of photo_ids)
        """
        # TODO: Implement clustering algorithm
        # Options:
        # 1. DBSCAN (density-based)
        # 2. Hierarchical clustering (agglomerative)
        # 3. Greedy grouping (simpler, faster)
        raise NotImplementedError("Similarity clustering not implemented")

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
        # TODO: Implement representative selection
        # Could reuse AssetService logic or implement here
        raise NotImplementedError("Representative selection not implemented")

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
