# face_cluster_worker.py
# Version 02.00.00.00 (Phase 8 - Automatic Face Grouping)
# QRunnable worker with signals for automatic pipeline integration
# Reuses face_branch_reps + face_crops for clustering
# ------------------------------------------------------

import os
import sys
import time
import sqlite3
import numpy as np
import logging
from typing import Optional
from sklearn.cluster import DBSCAN
from PySide6.QtCore import QRunnable, QObject, Signal, Slot
from reference_db import ReferenceDB
from workers.progress_writer import write_status
from config.face_detection_config import get_face_config
from services.performance_monitor import PerformanceMonitor
from services.face_quality_analyzer import FaceQualityAnalyzer
from services.clustering_quality_analyzer import ClusteringQualityAnalyzer

logger = logging.getLogger(__name__)


class FaceClusterSignals(QObject):
    """
    Signals for face clustering worker progress reporting.
    """
    # progress(current, total, message)
    progress = Signal(int, int, str)

    # finished(cluster_count, total_faces)
    finished = Signal(int, int)

    # error(error_message)
    error = Signal(str)


class FaceClusterWorker(QRunnable):
    """
    Background worker for clustering detected faces into person groups.

    Uses DBSCAN clustering algorithm with cosine similarity metric
    to group similar face embeddings together.

    Usage:
        worker = FaceClusterWorker(project_id=1)
        worker.signals.progress.connect(on_progress)
        worker.signals.finished.connect(on_finished)
        QThreadPool.globalInstance().start(worker)

    Performance:
        - Clustering is fast: ~1-5 seconds for 1000 faces
        - Memory efficient: processes embeddings in batches
        - Configurable: eps and min_samples can be tuned

    Features:
        - Clears previous clusters before creating new ones
        - Creates representative face for each cluster
        - Updates face_branch_reps, branches, and face_crops tables
        - Emits progress signals for UI updates
    """

    def __init__(self, project_id: int, eps: Optional[float] = None,
                 min_samples: Optional[int] = None, auto_tune: bool = True):
        """
        Initialize face clustering worker with adaptive parameter selection.

        Args:
            project_id: Project ID to cluster faces for
            eps: Optional DBSCAN epsilon parameter (manual override)
                 If None and auto_tune=True, will be auto-selected based on dataset size
                 Range: 0.20-0.50 (validated)
                 Lower = stricter grouping (more clusters, fewer false positives)
                 Higher = looser grouping (fewer clusters, more false positives)
            min_samples: Optional minimum faces to form a cluster (manual override)
                        If None and auto_tune=True, will be auto-selected based on dataset size
                        Range: 1-10 (validated)
            auto_tune: If True, automatically select optimal parameters based on dataset size
                      If False, use provided eps/min_samples or config defaults
                      Recommended: True for best results

        Parameter Selection:
            When auto_tune=True (recommended):
              - Tiny dataset (< 50 faces): eps=0.42, min_samples=2 (prevent fragmentation)
              - Small dataset (50-200): eps=0.38, min_samples=2
              - Medium dataset (200-1000): eps=0.35, min_samples=2 (current default)
              - Large dataset (1000-5000): eps=0.32, min_samples=3 (prevent false merges)
              - XLarge dataset (> 5000): eps=0.30, min_samples=3 (very strict)
        """
        super().__init__()
        self.project_id = project_id
        self.auto_tune = auto_tune
        self.tuning_rationale = ""
        self.tuning_category = ""

        # Determine parameters with adaptive selection
        if eps is not None and min_samples is not None:
            # Manual parameters provided - use them
            self.eps = eps
            self.min_samples = min_samples
            self.tuning_rationale = "Manual parameters"
            self.tuning_category = "manual"
        elif auto_tune:
            # Auto-tune based on dataset size
            face_count = self._get_face_count()
            config = get_face_config()
            optimal = config.get_optimal_clustering_params(face_count, project_id)

            self.eps = optimal["eps"]
            self.min_samples = optimal["min_samples"]
            self.tuning_rationale = optimal["rationale"]
            self.tuning_category = optimal["category"]

            logger.info(f"[FaceClusterWorker] Auto-tuned for {face_count} faces")
            logger.info(f"[FaceClusterWorker] Parameters: eps={self.eps}, min_samples={self.min_samples}")
            logger.info(f"[FaceClusterWorker] Rationale: {self.tuning_rationale}")
        else:
            # Use config defaults
            config = get_face_config()
            params = config.get_clustering_params(project_id)
            self.eps = params["eps"]
            self.min_samples = params["min_samples"]
            self.tuning_rationale = "Config defaults"
            self.tuning_category = "default"

        self.signals = FaceClusterSignals()
        self.cancelled = False

    def _get_face_count(self) -> int:
        """
        Get total number of faces for this project.

        Returns:
            Number of faces in face_crops table for this project
        """
        db = ReferenceDB()
        with db._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM face_crops WHERE project_id = ?",
                (self.project_id,)
            )
            count = cur.fetchone()[0]
            return count

    def cancel(self):
        """Cancel the clustering process."""
        self.cancelled = True
        logger.info("[FaceClusterWorker] Cancellation requested")

    @Slot()
    def run(self):
        """Main worker execution."""
        import threading
        _thread = threading.current_thread()
        _is_main = _thread is threading.main_thread()
        logger.info(
            "[FaceClusterWorker] Starting face clustering for project %d "
            "(thread=%s, is_main=%s)",
            self.project_id, _thread.name, _is_main,
        )
        start_time = time.time()

        # Initialize performance monitoring
        monitor = PerformanceMonitor(f"face_clustering_project_{self.project_id}")

        try:
            db = ReferenceDB()
            with db._connect() as conn:
                cur = conn.cursor()

                # Step 1: Load embeddings from face_crops table
                metric_load = monitor.record_operation("load_embeddings", {
                    "project_id": self.project_id
                })
                # CRITICAL FIX (2025-12-05): Only load faces for photos that exist in
                # photo_metadata AND project_images. This ensures counts match grid displays.
                # Previous bug: Loaded all face_crops, including orphaned entries for deleted photos
                # This caused count mismatch: face_branch_reps showed 14 but grid only showed 12
                self.signals.progress.emit(0, 100, "Loading face embeddings...")

                # Use EXISTS instead of JOIN on project_images to prevent
                # cartesian product: project_images is a many-to-many membership
                # table (same photo in "all", date, folder branches), so a JOIN
                # duplicates face rows for every branch the photo belongs to.
                cur.execute("""
                    SELECT fc.id, fc.crop_path, fc.image_path, fc.embedding,
                           fc.confidence, fc.bbox_x, fc.bbox_y, fc.bbox_w, fc.bbox_h,
                           pm.width, pm.height
                    FROM face_crops fc
                    JOIN photo_metadata pm ON fc.image_path = pm.path
                    WHERE fc.project_id=? AND fc.embedding IS NOT NULL
                      AND EXISTS (
                          SELECT 1 FROM project_images pi
                          WHERE pi.image_path = fc.image_path
                            AND pi.project_id = fc.project_id
                      )
                """, (self.project_id,))
                rows = cur.fetchall()

                # ── Invariant check: embeddings_loaded == faces_in_db ──
                cur.execute("SELECT COUNT(*) FROM face_crops WHERE project_id=? AND embedding IS NOT NULL", (self.project_id,))
                total_faces_in_db = cur.fetchone()[0]

                if len(rows) != total_faces_in_db:
                    delta = total_faces_in_db - len(rows)
                    if delta > 0:
                        logger.warning(
                            f"[FaceClusterWorker] INVARIANT: {delta} orphaned face_crops "
                            f"(in DB but not in photo_metadata/project_images). "
                            f"Loaded {len(rows)}/{total_faces_in_db}. "
                            f"Run cleanup_face_crops.py to remove orphans."
                        )
                    else:
                        # More loaded than in DB should never happen with EXISTS
                        logger.error(
                            f"[FaceClusterWorker] INVARIANT VIOLATION: loaded {len(rows)} "
                            f"but only {total_faces_in_db} in face_crops — possible query bug"
                        )

                if not rows:
                    logger.warning(f"[FaceClusterWorker] No embeddings found for project {self.project_id}")
                    self.signals.finished.emit(0, 0)
                    return

                # Parse embeddings
                ids, paths, image_paths, vecs = [], [], [], []
                qualities = []  # Store (confidence, face_ratio, aspect_ratio) for quality filtering
                bboxes = []  # Store bbox info for comprehensive quality analysis
                for rid, path, img_path, blob, conf, bx, by, bw, bh, img_w, img_h in rows:
                    try:
                        vec = np.frombuffer(blob, dtype=np.float32)
                        if vec.size:
                            ids.append(rid)
                            paths.append(path)
                            image_paths.append(img_path)
                            vecs.append(vec)

                            # Compute basic quality metrics for backward compatibility
                            face_area = (bw or 0) * (bh or 0)
                            img_area = (img_w or 0) * (img_h or 0)
                            face_ratio = (face_area / img_area) if (face_area > 0 and img_area > 0) else 0.0
                            aspect_ratio = (bw / bh) if (bw and bh) else 0.0
                            qualities.append((conf or 0.0, face_ratio, aspect_ratio))

                            # Store bbox and image info for comprehensive quality analysis
                            bboxes.append({
                                'bbox': (bx or 0, by or 0, bw or 0, bh or 0),
                                'image_path': img_path,
                                'confidence': conf or 0.0
                            })
                    except Exception as e:
                        logger.warning(f"[FaceClusterWorker] Failed to parse embedding: {e}")

                if len(vecs) < 2:
                    logger.warning("[FaceClusterWorker] Not enough faces to cluster (need at least 2)")
                    self.signals.finished.emit(0, len(vecs))
                    return

                X = np.vstack(vecs)
                total_faces = len(X)
                logger.info(f"[FaceClusterWorker] Loaded {total_faces} face embeddings")
                metric_load.finish()

                # Step 2: Run DBSCAN clustering
                metric_cluster = monitor.record_operation("dbscan_clustering", {
                    "face_count": total_faces,
                    "eps": self.eps,
                    "min_samples": self.min_samples,
                    "tuning_category": self.tuning_category
                })
                self.signals.progress.emit(10, 100, f"Clustering {total_faces} faces...")

                try:
                    params = get_face_config().get_clustering_params(project_id=self.project_id)
                    eps = float(params.get('eps', self.eps))
                    min_samples = int(params.get('min_samples', self.min_samples))
                except Exception:
                    eps = self.eps
                    min_samples = self.min_samples
                dbscan = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
                labels = dbscan.fit_predict(X)

                unique_labels = sorted([l for l in set(labels) if l != -1])
                cluster_count = len(unique_labels)

                logger.info(f"[FaceClusterWorker] Found {cluster_count} clusters")

                # If no clusters found, retry once with looser parameters
                if cluster_count == 0:
                    try:
                        retry_eps = max(0.40, eps)  # loosen threshold slightly
                        retry_min_samples = max(1, min_samples - 1)  # allow singletons
                        logger.info(f"[FaceClusterWorker] ⚠️ No clusters found, retrying with eps={retry_eps}, min_samples={retry_min_samples}")
                        dbscan_retry = DBSCAN(eps=retry_eps, min_samples=retry_min_samples, metric='cosine')
                        labels = dbscan_retry.fit_predict(X)
                        unique_labels = sorted([l for l in set(labels) if l != -1])
                        cluster_count = len(unique_labels)
                        logger.info(f"[FaceClusterWorker] Retry found {cluster_count} clusters")
                    except Exception as retry_error:
                        logger.warning(f"[FaceClusterWorker] Retry clustering failed: {retry_error}")

                # Count unclustered faces (noise, label == -1)
                noise_count = np.sum(labels == -1)
                if noise_count > 0:
                    logger.info(f"[FaceClusterWorker] Found {noise_count} unclustered faces (will create 'Unidentified' branch)")

                metric_cluster.finish()

                # Phase 2A: Analyze clustering quality
                metric_quality = monitor.record_operation("analyze_clustering_quality", {
                    "cluster_count": cluster_count,
                    "noise_count": noise_count
                })
                try:
                    quality_analyzer = ClusteringQualityAnalyzer()
                    clustering_metrics = quality_analyzer.analyze_clustering(X, labels, metric='cosine')

                    logger.info(
                        f"[FaceClusterWorker] Clustering Quality Analysis:\n"
                        f"  - Overall Quality: {clustering_metrics.overall_quality:.1f}/100 ({clustering_metrics.quality_label})\n"
                        f"  - Silhouette Score: {clustering_metrics.silhouette_score:.3f} "
                        f"({'Excellent' if clustering_metrics.silhouette_score >= 0.7 else 'Good' if clustering_metrics.silhouette_score >= 0.5 else 'Fair' if clustering_metrics.silhouette_score >= 0.25 else 'Poor'})\n"
                        f"  - Davies-Bouldin Index: {clustering_metrics.davies_bouldin_index:.3f} "
                        f"({'Excellent' if clustering_metrics.davies_bouldin_index < 0.5 else 'Good' if clustering_metrics.davies_bouldin_index < 1.0 else 'Fair' if clustering_metrics.davies_bouldin_index < 1.5 else 'Poor'})\n"
                        f"  - Noise Ratio: {clustering_metrics.noise_ratio:.1%}\n"
                        f"  - Avg Cluster Compactness: {clustering_metrics.avg_cluster_compactness:.3f}\n"
                        f"  - Avg Cluster Separation: {clustering_metrics.avg_cluster_separation:.3f}"
                    )

                    # Get tuning suggestions
                    suggestions = quality_analyzer.get_tuning_suggestions(clustering_metrics)
                    if suggestions:
                        logger.info(f"[FaceClusterWorker] Parameter Tuning Suggestions:")
                        for i, suggestion in enumerate(suggestions, 1):
                            logger.info(f"  {i}. {suggestion}")

                except Exception as quality_error:
                    logger.warning(f"[FaceClusterWorker] Clustering quality analysis failed: {quality_error}")

                metric_quality.finish()
                self.signals.progress.emit(40, 100, f"Found {cluster_count} person groups...")

                # Step 3: Clear previous cluster data
                metric_clear = monitor.record_operation("clear_previous_clusters")
                cur.execute("DELETE FROM face_branch_reps WHERE project_id=? AND branch_key LIKE 'face_%'", (self.project_id,))
                cur.execute("DELETE FROM branches WHERE project_id=? AND branch_key LIKE 'face_%'", (self.project_id,))
                cur.execute("DELETE FROM project_images WHERE project_id=? AND branch_key LIKE 'face_%'", (self.project_id,))
                metric_clear.finish()

                # Step 4: Write new cluster results
                # Split into separate operations so timing attribution is accurate

                # PERFORMANCE OPTIMIZATION (2026-01-07): Create quality analyzer ONCE for all clusters
                face_quality_analyzer = FaceQualityAnalyzer()

                # Track granular timing within cluster loop
                total_quality_analysis_time = 0.0
                total_db_operations_time = 0.0

                for idx, cid in enumerate(unique_labels):
                    if self.cancelled:
                        logger.info("[FaceClusterWorker] Cancelled by user")
                        conn.rollback()
                        return

                    mask = labels == cid
                    cluster_vecs = X[mask]
                    cluster_paths = np.array(paths)[mask].tolist()
                    cluster_image_paths = np.array(image_paths)[mask].tolist()
                    cluster_ids = np.array(ids)[mask].tolist()
                    cluster_quals = np.array(qualities)[mask]
                    cluster_bboxes = [bboxes[i] for i, m in enumerate(mask) if m]

                    centroid_vec = np.mean(cluster_vecs, axis=0).astype(np.float32)

                    # Phase 2A: ENHANCED QUALITY-BASED REPRESENTATIVE SELECTION
                    # Uses comprehensive face quality analysis (blur, lighting, size, aspect ratio, confidence)
                    # Strategy:
                    # 1. Calculate comprehensive quality for each face in cluster
                    # 2. Filter faces by overall quality threshold (>= 60/100)
                    # 3. Among high-quality faces, select one with:
                    #    - Highest overall quality score (primary)
                    #    - Closest to centroid (secondary, for tie-breaking)
                    # 4. Fallback: If no high-quality faces, use centroid-based selection
                    quality_start = time.time()
                    try:
                        # Use shared face_quality_analyzer instance (created outside loop)
                        face_qualities = []

                        # Calculate comprehensive quality for each face
                        for i, bbox_info in enumerate(cluster_bboxes):
                            try:
                                quality_metrics = face_quality_analyzer.analyze_face_crop(
                                    image_path=bbox_info['image_path'],
                                    bbox=bbox_info['bbox'],
                                    confidence=bbox_info['confidence']
                                )
                                face_qualities.append(quality_metrics)
                            except Exception as e:
                                logger.debug(f"[FaceClusterWorker] Quality analysis failed for face {i}: {e}")
                                # Use default metrics as fallback
                                face_qualities.append(face_quality_analyzer._default_metrics(bbox_info['confidence']))

                        # Filter high-quality faces (overall_quality >= 60)
                        quality_threshold = 60.0
                        high_quality_indices = [
                            i for i, q in enumerate(face_qualities)
                            if q.overall_quality >= quality_threshold
                        ]

                        if high_quality_indices:
                            # Among high-quality faces, select best combination of quality + centroid proximity
                            # Calculate weighted score: 70% quality + 30% centroid proximity
                            best_idx = None
                            best_score = -1.0

                            # Normalize centroid distances to 0-100 scale
                            high_quality_vecs = cluster_vecs[high_quality_indices]
                            centroid_dists = np.linalg.norm(high_quality_vecs - centroid_vec, axis=1)
                            max_dist = np.max(centroid_dists) if len(centroid_dists) > 1 else 1.0
                            if max_dist == 0:
                                max_dist = 1.0

                            for local_idx, global_idx in enumerate(high_quality_indices):
                                quality_score = face_qualities[global_idx].overall_quality  # 0-100
                                # Invert distance: closer to centroid = higher score
                                proximity_score = 100.0 * (1.0 - centroid_dists[local_idx] / max_dist)  # 0-100

                                # Weighted combination: prioritize quality over proximity
                                combined_score = 0.70 * quality_score + 0.30 * proximity_score

                                if combined_score > best_score:
                                    best_score = combined_score
                                    best_idx = global_idx

                            rep_path = cluster_paths[best_idx]
                            best_quality = face_qualities[best_idx]
                            logger.debug(
                                f"[FaceClusterWorker] Cluster {cid}: Selected representative with "
                                f"quality={best_quality.overall_quality:.1f}/100 ({best_quality.quality_label}), "
                                f"blur={best_quality.blur_score:.1f}, lighting={best_quality.lighting_score:.1f}, "
                                f"from {len(high_quality_indices)}/{len(cluster_paths)} high-quality candidates"
                            )
                        else:
                            # Fallback: No high-quality faces, use centroid-based selection
                            logger.debug(
                                f"[FaceClusterWorker] Cluster {cid}: No faces meet quality threshold "
                                f"(>={quality_threshold}), using centroid fallback"
                            )
                            dists = np.linalg.norm(cluster_vecs - centroid_vec, axis=1)
                            rep_idx = int(np.argmin(dists))
                            rep_path = cluster_paths[rep_idx]

                    except Exception as quality_selection_error:
                        # Ultimate fallback: Use basic quality filter or first face
                        logger.warning(
                            f"[FaceClusterWorker] Cluster {cid}: Enhanced quality selection failed: "
                            f"{quality_selection_error}, using basic fallback"
                        )
                        # Basic quality filter (legacy)
                        conf = cluster_quals[:, 0]
                        face_ratio = cluster_quals[:, 1]
                        aspect_ratio = cluster_quals[:, 2]
                        good_mask = (
                            (conf >= 0.6) &
                            (face_ratio >= 0.02) &
                            (aspect_ratio >= 0.5) & (aspect_ratio <= 1.6)
                        )
                        if np.any(good_mask):
                            good_vecs = cluster_vecs[good_mask]
                            good_paths = np.array(cluster_paths)[good_mask].tolist()
                            dists_good = np.linalg.norm(good_vecs - centroid_vec, axis=1)
                            rep_idx_local = int(np.argmin(dists_good))
                            rep_path = good_paths[rep_idx_local]
                        else:
                            rep_path = cluster_paths[0]
                    centroid = centroid_vec.tobytes()
                    branch_key = f"face_{cid:03d}"
                    display_name = f"Person {cid+1}"

                    # Track quality analysis time
                    quality_elapsed = time.time() - quality_start
                    total_quality_analysis_time += quality_elapsed

                    # CRITICAL FIX: Count should be unique PHOTOS, not face crops
                    # A person can appear multiple times in one photo (e.g., mirror selfie)
                    unique_photos = set(cluster_image_paths)
                    member_count = len(unique_photos)

                    # Time database operations
                    db_start = time.time()

                    # Insert into face_branch_reps
                    cur.execute("""
                        INSERT INTO face_branch_reps (project_id, branch_key, centroid, rep_path, count)
                        VALUES (?, ?, ?, ?, ?)
                    """, (self.project_id, branch_key, centroid, rep_path, member_count))

                    # Insert into branches (for sidebar display)
                    cur.execute("""
                        INSERT INTO branches (project_id, branch_key, display_name)
                        VALUES (?, ?, ?)
                    """, (self.project_id, branch_key, display_name))

                    # Update face_crops entries to reflect cluster
                    placeholders = ','.join(['?'] * len(cluster_ids))
                    cur.execute(f"""
                        UPDATE face_crops SET branch_key=? WHERE project_id=? AND id IN ({placeholders})
                    """, (branch_key, self.project_id, *cluster_ids))

                    # CRITICAL FIX: Link photos to this face branch in project_images
                    # This allows get_images_by_branch() to return photos for face clusters
                    # (unique_photos already calculated above for count)
                    # PERFORMANCE OPTIMIZATION (2026-01-07): Batch INSERT for 50-70% speedup
                    if unique_photos:
                        photo_data = [(self.project_id, branch_key, photo_path)
                                      for photo_path in unique_photos]
                        cur.executemany("""
                            INSERT OR IGNORE INTO project_images (project_id, branch_key, image_path)
                            VALUES (?, ?, ?)
                        """, photo_data)
                        logger.debug(f"[FaceClusterWorker] Batch-linked {len(unique_photos)} unique photos to {branch_key}")
                    else:
                        logger.debug(f"[FaceClusterWorker] No photos to link for {branch_key}")

                    # Track database operations time
                    db_elapsed = time.time() - db_start
                    total_db_operations_time += db_elapsed

                    # Emit progress
                    progress_pct = int(40 + (idx / cluster_count) * 60)
                    self.signals.progress.emit(
                        progress_pct, 100,
                        f"Saving cluster {idx+1}/{cluster_count}: {display_name} ({member_count} faces)"
                    )

                    logger.info(f"[FaceClusterWorker] Cluster {cid} → {member_count} faces")

                # Record split metrics so PerformanceMonitor shows accurate attribution
                monitor.record_operation("quality_analysis", {
                    "cluster_count": cluster_count,
                    "elapsed_s": round(total_quality_analysis_time, 3),
                }).finish()
                monitor.record_operation("db_write_clusters", {
                    "cluster_count": cluster_count,
                    "elapsed_s": round(total_db_operations_time, 3),
                }).finish()

                # Report granular timing breakdown
                total_loop_time = total_quality_analysis_time + total_db_operations_time
                quality_pct = (total_quality_analysis_time / total_loop_time * 100) if total_loop_time > 0 else 0
                db_pct = (total_db_operations_time / total_loop_time * 100) if total_loop_time > 0 else 0

                logger.info(f"[FaceClusterWorker] 📊 Cluster Loop Performance Breakdown:")
                logger.info(f"  - Quality Analysis: {total_quality_analysis_time:.2f}s ({quality_pct:.1f}%)")
                logger.info(f"  - Database Operations: {total_db_operations_time:.2f}s ({db_pct:.1f}%)")
                logger.info(f"  - Total Measured: {total_loop_time:.2f}s")
                logger.info(f"[FaceClusterWorker] ✅ Optimizations: Reused FaceQualityAnalyzer instance + batch INSERT with executemany()")

                # Step 5: Handle unclustered faces (noise from DBSCAN, label == -1)
                if noise_count > 0:
                    metric_noise = monitor.record_operation("handle_unclustered_faces", {
                        "noise_count": int(noise_count)
                    })
                    self.signals.progress.emit(95, 100, f"Processing {noise_count} unidentified faces...")

                    # Get unclustered face data
                    noise_mask = labels == -1
                    noise_ids = np.array(ids)[noise_mask].tolist()
                    noise_paths = np.array(paths)[noise_mask].tolist()
                    noise_image_paths = np.array(image_paths)[noise_mask].tolist()
                    noise_vecs = X[noise_mask]

                    # Create centroid from unclustered faces
                    centroid = np.mean(noise_vecs, axis=0).astype(np.float32).tobytes()
                    rep_path = noise_paths[0] if noise_paths else None

                    # CRITICAL FIX: Count unique PHOTOS, not face crops
                    unique_noise_photos = set(noise_image_paths)
                    photo_count = len(unique_noise_photos)

                    # Special branch for unidentified faces
                    branch_key = "face_unidentified"
                    display_name = f"⚠️ Unidentified ({noise_count} faces)"

                    # Insert into face_branch_reps
                    cur.execute("""
                        INSERT INTO face_branch_reps (project_id, branch_key, centroid, rep_path, count)
                        VALUES (?, ?, ?, ?, ?)
                    """, (self.project_id, branch_key, centroid, rep_path, photo_count))

                    # Insert into branches (for sidebar display)
                    cur.execute("""
                        INSERT INTO branches (project_id, branch_key, display_name)
                        VALUES (?, ?, ?)
                    """, (self.project_id, branch_key, display_name))

                    # Update face_crops entries
                    placeholders = ','.join(['?'] * len(noise_ids))
                    cur.execute(f"""
                        UPDATE face_crops SET branch_key=? WHERE project_id=? AND id IN ({placeholders})
                    """, (branch_key, self.project_id, *noise_ids))

                    # Link photos to unidentified branch
                    # (unique_noise_photos already calculated above for count)
                    # PERFORMANCE OPTIMIZATION (2026-01-07): Batch INSERT for 50-70% speedup
                    if unique_noise_photos:
                        noise_photo_data = [(self.project_id, branch_key, photo_path)
                                            for photo_path in unique_noise_photos]
                        cur.executemany("""
                            INSERT OR IGNORE INTO project_images (project_id, branch_key, image_path)
                            VALUES (?, ?, ?)
                        """, noise_photo_data)
                        logger.info(f"[FaceClusterWorker] Created 'Unidentified' branch with {noise_count} faces from {len(unique_noise_photos)} photos (batch-linked)")
                    else:
                        logger.info(f"[FaceClusterWorker] Created 'Unidentified' branch with {noise_count} faces but no photos to link")
                    metric_noise.finish()

                # Commit all changes
                metric_commit = monitor.record_operation("database_commit")
                conn.commit()
                metric_commit.finish()

            # Finish monitoring and print summary
            monitor.finish_monitoring()
            duration = time.time() - start_time
            total_branches = cluster_count + (1 if noise_count > 0 else 0)
            logger.info(f"[FaceClusterWorker] Complete in {duration:.1f}s: {cluster_count} person clusters + {noise_count} unidentified faces")

            # Print performance summary
            print("\n")
            monitor.print_summary()

            self.signals.progress.emit(100, 100, f"Clustering complete: {total_branches} branches created")
            self.signals.finished.emit(cluster_count, total_faces)

        except Exception as e:
            logger.error(f"[FaceClusterWorker] Fatal error: {e}", exc_info=True)
            self.signals.error.emit(str(e))
            self.signals.finished.emit(0, 0)


# ============================================================================
# Legacy functions (kept for backward compatibility with standalone script)
# ============================================================================

def cluster_faces_1st(project_id: int, eps: float = 0.35, min_samples: int = 2):
    """
    Performs unsupervised face clustering using embeddings already in the DB.
    Writes cluster info back into face_branch_reps, branches, and face_crops.
    """
    db = ReferenceDB()
    with db._connect() as conn:
        cur = conn.cursor()

    # 1️: Get embeddings from existing face_crops table
    cur.execute("""
        SELECT id, crop_path, image_path, embedding FROM face_crops
        WHERE project_id=? AND embedding IS NOT NULL
    """, (project_id,))
    rows = cur.fetchall()
    if not rows:
        print(f"[FaceCluster] No embeddings found for project {project_id}")
        return

    ids, paths, image_paths, vecs = [], [], [], []
    for rid, path, img_path, blob in rows:
        try:
            vec = np.frombuffer(blob, dtype=np.float32)
            if vec.size:
                ids.append(rid)
                paths.append(path)
                image_paths.append(img_path)
                vecs.append(vec)
        except Exception:
            pass

    if len(vecs) < 2:
        print("[FaceCluster] Not enough faces to cluster.")
        return

    X = np.vstack(vecs)
    print(f"[FaceCluster] Clustering {len(X)} faces ...")

    # 2️: Run DBSCAN clustering
    dbscan = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
    labels = dbscan.fit_predict(X)
    unique_labels = sorted([l for l in set(labels) if l != -1])

    # 3️: Clear previous cluster data
    cur.execute("DELETE FROM face_branch_reps WHERE project_id=? AND branch_key LIKE 'face_%'", (project_id,))
    cur.execute("DELETE FROM branches WHERE project_id=? AND branch_key LIKE 'face_%'", (project_id,))
    cur.execute("DELETE FROM project_images WHERE project_id=? AND branch_key LIKE 'face_%'", (project_id,))

    # 4️: Write new cluster results
    for cid in unique_labels:
        mask = labels == cid
        cluster_vecs = X[mask]
        cluster_paths = np.array(paths)[mask].tolist()
        cluster_image_paths = np.array(image_paths)[mask].tolist()

        centroid = np.mean(cluster_vecs, axis=0).astype(np.float32).tobytes()
        rep_path = cluster_paths[0]
        branch_key = f"face_{cid:03d}"
        display_name = f"Person {cid+1}"

        # CRITICAL FIX: Count unique PHOTOS, not face crops
        unique_photos = set(cluster_image_paths)
        member_count = len(unique_photos)

        # Insert into face_branch_reps
        cur.execute("""
            INSERT INTO face_branch_reps (project_id, branch_key, centroid, rep_path, count)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, branch_key, centroid, rep_path, member_count))

        # Insert into branches (for sidebar display)
        cur.execute("""
            INSERT INTO branches (project_id, branch_key, display_name)
            VALUES (?, ?, ?)
        """, (project_id, branch_key, display_name))

        # Update face_crops entries to reflect cluster
        cur.execute("""
            UPDATE face_crops SET branch_key=? WHERE project_id=? AND id IN (%s)
        """ % ",".join(["?"] * np.sum(mask)),
        (branch_key, project_id, *np.array(ids)[mask].tolist()))

        # CRITICAL FIX: Link photos to this face branch in project_images
        # (unique_photos already calculated above for count)
        for photo_path in unique_photos:
            cur.execute("""
                INSERT OR IGNORE INTO project_images (project_id, branch_key, image_path)
                VALUES (?, ?, ?)
            """, (project_id, branch_key, photo_path))

        print(f"[FaceCluster] Cluster {cid} → {len(cluster_paths)} faces across {member_count} unique photos")

    conn.commit()
    conn.close()
    print(f"[FaceCluster] Done: {len(unique_labels)} clusters saved.")

def cluster_faces(project_id: int, eps: float = 0.35, min_samples: int = 2):
    """
    Performs unsupervised face clustering using embeddings already in the DB.
    Writes cluster info back into face_branch_reps, branches, and face_crops.
    """
    db = ReferenceDB()
    with db._connect() as conn:
        cur = conn.cursor()

    # 1️: Get embeddings from existing face_crops table
    cur.execute("""
        SELECT id, crop_path, image_path, embedding FROM face_crops
        WHERE project_id=? AND embedding IS NOT NULL
    """, (project_id,))
    rows = cur.fetchall()
    if not rows:
        print(f"[FaceCluster] No embeddings found for project {project_id}")
        return

    ids, paths, image_paths, vecs = [], [], [], []
    for rid, path, img_path, blob in rows:
        try:
            vec = np.frombuffer(blob, dtype=np.float32)
            if vec.size:
                ids.append(rid)
                paths.append(path)
                image_paths.append(img_path)
                vecs.append(vec)
        except Exception:
            pass

    if len(vecs) < 2:
        print("[FaceCluster] Not enough faces to cluster.")
        return

    X = np.vstack(vecs)
    total = len(X)
    status_path = os.path.join(os.getcwd(), "status", "cluster_status.json")
    log_path = status_path.replace(".json", ".log")

    def _log_progress(phase, current, total):
        pct = round((current / total) * 100, 1) if total else 0
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {phase} {pct:.1f}% ({current}/{total})\n")

    write_status(status_path, "embedding_load", 0, total)
    _log_progress("embedding_load", 0, total)
    print(f"[FaceCluster] Clustering {len(X)} faces ...")

    # 2️: Run DBSCAN clustering
    dbscan = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
    labels = dbscan.fit_predict(X)

    unique_labels = sorted([l for l in set(labels) if l != -1])

    # Count unclustered faces (noise, label == -1)
    noise_count = int(np.sum(labels == -1))
    if noise_count > 0:
        print(f"[FaceCluster] Found {noise_count} unclustered faces (will create 'Unidentified' branch)")

    # 3️: Clear previous cluster data
    cur.execute("DELETE FROM face_branch_reps WHERE project_id=? AND branch_key LIKE 'face_%'", (project_id,))
    cur.execute("DELETE FROM branches WHERE project_id=? AND branch_key LIKE 'face_%'", (project_id,))
    cur.execute("DELETE FROM project_images WHERE project_id=? AND branch_key LIKE 'face_%'", (project_id,))

    # 4️: Write new cluster results
    processed_clusters = 0
    total_clusters = len(unique_labels)
    write_status(status_path, "clustering", 0, total_clusters)

    for cid in unique_labels:
        mask = labels == cid
        cluster_vecs = X[mask]
        cluster_paths = np.array(paths)[mask].tolist()
        cluster_image_paths = np.array(image_paths)[mask].tolist()

        centroid = np.mean(cluster_vecs, axis=0).astype(np.float32).tobytes()
        rep_path = cluster_paths[0]
        branch_key = f"face_{cid:03d}"
        display_name = f"Person {cid+1}"

        # CRITICAL FIX: Count unique PHOTOS, not face crops
        unique_photos = set(cluster_image_paths)
        member_count = len(unique_photos)

        # Insert into face_branch_reps
        cur.execute("""
            INSERT INTO face_branch_reps (project_id, branch_key, centroid, rep_path, count)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, branch_key, centroid, rep_path, member_count))

        # Insert into branches (for sidebar display)
        cur.execute("""
            INSERT INTO branches (project_id, branch_key, display_name)
            VALUES (?, ?, ?)
        """, (project_id, branch_key, display_name))

        # Update face_crops entries to reflect cluster
        cur.execute(f"""
            UPDATE face_crops SET branch_key=? WHERE project_id=? AND id IN ({','.join(['?'] * np.sum(mask))})
        """, (branch_key, project_id, *np.array(ids)[mask].tolist()))

        # CRITICAL FIX: Link photos to this face branch in project_images
        # (unique_photos already calculated above for count)
        for photo_path in unique_photos:
            cur.execute("""
                INSERT OR IGNORE INTO project_images (project_id, branch_key, image_path)
                VALUES (?, ?, ?)
            """, (project_id, branch_key, photo_path))

        processed_clusters += 1
        write_status(status_path, "clustering", processed_clusters, total_clusters)
        _log_progress("clustering", processed_clusters, total_clusters)

        print(f"[FaceCluster] Cluster {cid} → {len(cluster_paths)} faces across {member_count} unique photos")

    # Step 5: Handle unclustered faces (noise from DBSCAN, label == -1)
    if noise_count > 0:
        noise_mask = labels == -1
        noise_ids = np.array(ids)[noise_mask].tolist()
        noise_paths = np.array(paths)[noise_mask].tolist()
        noise_image_paths = np.array(image_paths)[noise_mask].tolist()
        noise_vecs = X[noise_mask]

        centroid = np.mean(noise_vecs, axis=0).astype(np.float32).tobytes()
        rep_path = noise_paths[0] if noise_paths else None
        branch_key = "face_unidentified"
        display_name = f"⚠️ Unidentified ({noise_count} faces)"

        # CRITICAL FIX: Count unique PHOTOS, not face crops
        unique_noise_photos = set(noise_image_paths)
        photo_count = len(unique_noise_photos)

        cur.execute("""
            INSERT INTO face_branch_reps (project_id, branch_key, centroid, rep_path, count)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, branch_key, centroid, rep_path, photo_count))

        cur.execute("""
            INSERT INTO branches (project_id, branch_key, display_name)
            VALUES (?, ?, ?)
        """, (project_id, branch_key, display_name))

        cur.execute(f"""
            UPDATE face_crops SET branch_key=? WHERE project_id=? AND id IN ({','.join(['?'] * len(noise_ids))})
        """, (branch_key, project_id, *noise_ids))

        # (unique_noise_photos already calculated above for count)
        for photo_path in unique_noise_photos:
            cur.execute("""
                INSERT OR IGNORE INTO project_images (project_id, branch_key, image_path)
                VALUES (?, ?, ?)
            """, (project_id, branch_key, photo_path))

        print(f"[FaceCluster] Created 'Unidentified' branch with {noise_count} faces from {len(unique_noise_photos)} photos")

    conn.commit()
    total_branches = len(unique_labels) + (1 if noise_count > 0 else 0)
    write_status(status_path, "done", total_clusters, total_clusters)
    _log_progress("done", total_clusters, total_clusters)
    conn.close()
    print(f"[FaceCluster] Done: {len(unique_labels)} person clusters + {noise_count} unidentified faces = {total_branches} branches")


if __name__ == "__main__":
    """
    Standalone script entry point.

    Usage:
        python face_cluster_worker.py <project_id>

    This mode is used when called as a detached subprocess (legacy mode).
    For normal operation, use FaceClusterWorker class with QThreadPool.
    """
    if len(sys.argv) < 2:
        print("Usage: python face_cluster_worker.py <project_id>")
        sys.exit(1)

    pid = int(sys.argv[1])

    # Use Qt event loop for signal handling (if available)
    try:
        from PySide6.QtCore import QCoreApplication, QThreadPool

        app = QCoreApplication(sys.argv)

        def on_progress(current, total, message):
            print(f"[{current}/{total}] {message}")

        def on_finished(cluster_count, total_faces):
            print(f"\nFinished: {cluster_count} clusters created from {total_faces} faces")
            app.quit()

        def on_error(error_msg):
            print(f"Error: {error_msg}")
            app.quit()

        worker = FaceClusterWorker(project_id=pid)
        worker.signals.progress.connect(on_progress)
        worker.signals.finished.connect(on_finished)
        worker.signals.error.connect(on_error)

        QThreadPool.globalInstance().start(worker)

        sys.exit(app.exec())

    except ImportError:
        # Fallback to legacy function if Qt not available
        print("[FaceClusterWorker] Qt not available, using legacy mode")
        cluster_faces(pid)
