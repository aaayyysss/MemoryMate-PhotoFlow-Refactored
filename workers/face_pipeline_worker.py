# workers/face_pipeline_worker.py
# Version 03.00.00.00 dated 20260218
#
# Background pipeline worker that chains face detection + clustering
# as a single non-blocking job.  No modal dialogs, no UI coupling.
#
# Steps:
#   1. Face detection (InsightFace on all unprocessed photos)
#      - After each batch commit, if enough new faces accumulated,
#        trigger a lightweight interim clustering pass so the UI can
#        show partial People results immediately (progressive UX).
#   2. Final face clustering (DBSCAN on all embeddings)
#
# Progressive clustering pattern (Google Photos / Apple Photos style):
#   - First interim cluster at 50+ detected faces
#   - Subsequent interim clusters every 200 additional faces
#   - Full recluster at pipeline completion for final accuracy
#   - UI shows "Indexing faces..." banner during progressive phase

import time
import threading

from PySide6.QtCore import QRunnable, QObject, Signal

from logging_config import get_logger

logger = get_logger(__name__)

# ── Progressive clustering thresholds ─────────────────────────────
# Google/Apple/Lightroom pattern: show faces early, refine as more arrive.
# First interim at 20 faces so users see results quickly, then every 100
# faces with a 10-second minimum gap to avoid excessive recluster churn.
_FIRST_INTERIM_THRESHOLD = 20    # faces before first interim cluster
_SUBSEQUENT_INTERVAL = 100       # faces between subsequent interim clusters
_MIN_INTERIM_GAP_S = 10.0        # minimum seconds between interim clusters


class FacePipelineSignals(QObject):
    """Signals emitted by the face pipeline worker."""
    # (step_name, message)
    progress = Signal(str, str)
    # Forwarded from FaceDetectionWorker after each DB batch commit
    # (processed, total, faces_so_far, project_id)
    batch_committed = Signal(int, int, int, int)
    # Emitted after each interim clustering pass completes
    # (cluster_count, total_faces, is_final)
    interim_clusters_ready = Signal(int, int, bool)
    # Emitted when pipeline finishes: {faces_detected, clusters_created, errors}
    finished = Signal(dict)
    # Fatal error
    error = Signal(str)


class FacePipelineWorker(QRunnable):
    """
    Background worker that runs face detection then clustering
    entirely off the UI thread.

    Supports progressive clustering: interim cluster passes run during
    detection so the user sees partial People results without waiting
    for the full dataset to finish.

    Usage:
        worker = FacePipelineWorker(project_id=1)
        worker.signals.progress.connect(on_progress)
        worker.signals.finished.connect(on_finished)
        QThreadPool.globalInstance().start(worker)
    """

    def __init__(self, project_id: int, model: str = "buffalo_l"):
        super().__init__()
        self.setAutoDelete(True)
        self.signals = FacePipelineSignals()
        self.project_id = project_id
        self.model = model
        self._cancelled = False
        # Optional: scoped photo paths (set by FacePipelineService)
        self._scoped_photo_paths = None

        # Progressive clustering state
        self._faces_at_last_interim = 0
        self._last_interim_time = 0.0
        self._interim_cluster_count = 0

    def cancel(self):
        self._cancelled = True

    def _clear_stale_face_data(self):
        """
        Clear stale face detection data from previous pipeline runs.

        This prevents the "20 detected / 30 loaded" mismatch where old faces
        from previous runs accumulate and pollute clustering results.

        Clears:
        - face_crops: All face crops for this project (embeddings + bboxes)
        - face_branch_reps: Derived cluster representatives
        - branches with face-related branch_keys (auto-generated clusters)

        Does NOT clear:
        - User-curated labels or manual assignments (if any)
        """
        from reference_db import ReferenceDB

        db = ReferenceDB()
        try:
            with db._connect() as conn:
                cur = conn.cursor()

                # Count existing face data for logging
                cur.execute(
                    "SELECT COUNT(*) FROM face_crops WHERE project_id = ?",
                    (self.project_id,)
                )
                old_crop_count = cur.fetchone()[0]

                cur.execute(
                    "SELECT COUNT(*) FROM face_branch_reps WHERE project_id = ?",
                    (self.project_id,)
                )
                old_rep_count = cur.fetchone()[0]

                # Clear face_crops (detection results with embeddings)
                cur.execute(
                    "DELETE FROM face_crops WHERE project_id = ?",
                    (self.project_id,)
                )

                # Clear face_branch_reps (cluster centroids and representatives)
                cur.execute(
                    "DELETE FROM face_branch_reps WHERE project_id = ?",
                    (self.project_id,)
                )

                # Clear auto-generated branches (face_cluster_* pattern)
                cur.execute(
                    "DELETE FROM branches WHERE project_id = ? AND branch_key LIKE 'face_cluster_%'",
                    (self.project_id,)
                )

                conn.commit()

                logger.info(
                    "[FacePipelineWorker] Cleared stale face data: "
                    "%d crops, %d reps (project %d)",
                    old_crop_count, old_rep_count, self.project_id
                )
        finally:
            db.close()

    # ── Group member remapping (Google/Apple stable-identity pattern) ──

    def _snapshot_group_members(self) -> dict:
        """Snapshot group member identities BEFORE clearing old clusters.

        For each group member's branch_key, saves:
        1. rep_path from face_branch_reps (crop file path — Strategy 1 anchor)
        2. image_paths from face_crops (photos containing this person — Strategy 2 anchor)

        Returns:
            dict: {group_id: [(old_branch_key, rep_path, [image_paths]), ...]}
        """
        from reference_db import ReferenceDB

        db = ReferenceDB()
        try:
            with db._connect() as conn:
                # Get all active groups with their members and rep_paths
                rows = conn.execute("""
                    SELECT g.id, m.branch_key, r.rep_path
                    FROM person_groups g
                    JOIN person_group_members m ON m.group_id = g.id
                    LEFT JOIN face_branch_reps r
                        ON r.branch_key = m.branch_key AND r.project_id = g.project_id
                    WHERE g.project_id = ? AND g.is_deleted = 0
                    ORDER BY g.id, m.added_at
                """, (self.project_id,)).fetchall()

                # Also grab the image_paths per branch_key for overlap matching
                all_bks = set(r[1] for r in rows)
                bk_image_paths = {}
                if all_bks:
                    placeholders = ','.join(['?'] * len(all_bks))
                    img_rows = conn.execute(f"""
                        SELECT DISTINCT branch_key, image_path
                        FROM face_crops
                        WHERE project_id = ? AND branch_key IN ({placeholders})
                    """, (self.project_id, *all_bks)).fetchall()
                    for bk, img in img_rows:
                        bk_image_paths.setdefault(bk, []).append(img)

                snapshot = {}
                for group_id, branch_key, rep_path in rows:
                    if group_id not in snapshot:
                        snapshot[group_id] = []
                    image_paths = bk_image_paths.get(branch_key, [])
                    snapshot[group_id].append((branch_key, rep_path, image_paths))

                if snapshot:
                    logger.info(
                        "[FacePipelineWorker] Snapshot: %d groups with %d total members",
                        len(snapshot), sum(len(v) for v in snapshot.values()),
                    )
                return snapshot
        except Exception as e:
            logger.warning("[FacePipelineWorker] Snapshot failed (groups will need manual recompute): %s", e)
            return {}
        finally:
            db.close()

    def _remap_group_members(self, snapshot: dict) -> None:
        """Remap group member branch_keys to new clusters AFTER re-clustering.

        Strategy (most-specific to least-specific):
        1. Exact crop_path match: old rep_path found in new face_crops → direct mapping
        2. Image overlap match: find the new branch_key whose faces share the
           most images with the old branch_key's snapshot of image_paths

        This implements the Google/Apple pattern where person groups survive
        re-clustering with stable identity tracking.
        """
        if not snapshot:
            return

        from reference_db import ReferenceDB

        db = ReferenceDB()
        try:
            with db._connect() as conn:
                cur = conn.cursor()

                # Strategy 1: crop_path → new_branch_key
                cur.execute("""
                    SELECT crop_path, branch_key
                    FROM face_crops
                    WHERE project_id = ? AND branch_key IS NOT NULL
                """, (self.project_id,))
                crop_to_branch = {r[0]: r[1] for r in cur.fetchall()}

                # Strategy 2 prep: build new branch_key → {image_paths} for
                # overlap matching when crop_path doesn't match exactly
                cur.execute("""
                    SELECT branch_key, image_path
                    FROM face_crops
                    WHERE project_id = ? AND branch_key IS NOT NULL
                """, (self.project_id,))
                new_bk_images = {}
                for bk, img in cur.fetchall():
                    new_bk_images.setdefault(bk, set()).add(img)

                total_remapped = 0
                total_unchanged = 0
                total_lost = 0

                for group_id, members in snapshot.items():
                    for old_bk, rep_path, old_image_paths in members:
                        # Strategy 1: exact crop_path match
                        new_bk = crop_to_branch.get(rep_path) if rep_path else None

                        # Strategy 2: image overlap
                        if not new_bk and old_image_paths:
                            old_imgs = set(old_image_paths)
                            best_bk = None
                            best_overlap = 0
                            for nbk, nimg_set in new_bk_images.items():
                                overlap = len(old_imgs & nimg_set)
                                if overlap > best_overlap:
                                    best_overlap = overlap
                                    best_bk = nbk
                            if best_bk and best_overlap > 0:
                                new_bk = best_bk

                        if not new_bk:
                            total_lost += 1
                            logger.debug(
                                "[FacePipelineWorker] Group %d: lost member %s (no match)",
                                group_id, old_bk,
                            )
                            continue

                        if new_bk == old_bk:
                            total_unchanged += 1
                            continue

                        # Update the group member to point to new branch_key
                        cur.execute("""
                            UPDATE person_group_members
                            SET branch_key = ?
                            WHERE group_id = ? AND branch_key = ?
                        """, (new_bk, group_id, old_bk))
                        total_remapped += 1
                        logger.debug(
                            "[FacePipelineWorker] Group %d: %s → %s",
                            group_id, old_bk, new_bk,
                        )

                conn.commit()

                logger.info(
                    "[FacePipelineWorker] Group remap: %d remapped, "
                    "%d unchanged, %d lost",
                    total_remapped, total_unchanged, total_lost,
                )
        except Exception as e:
            logger.warning("[FacePipelineWorker] Group remap failed: %s", e)
        finally:
            db.close()

    def _recompute_all_groups(self) -> None:
        """Recompute match results for all active groups after re-clustering.

        Google/Apple pattern: group match results are automatically refreshed
        when the underlying face data changes.
        """
        from reference_db import ReferenceDB

        db = ReferenceDB()
        try:
            with db._connect() as conn:
                rows = conn.execute("""
                    SELECT id FROM person_groups
                    WHERE project_id = ? AND is_deleted = 0
                """, (self.project_id,)).fetchall()
                group_ids = [r[0] for r in rows]
        except Exception as e:
            logger.warning("[FacePipelineWorker] Failed to list groups: %s", e)
            return
        finally:
            db.close()

        if not group_ids:
            return

        logger.info("[FacePipelineWorker] Recomputing %d groups after re-clustering", len(group_ids))

        try:
            from services.people_group_service import PeopleGroupService

            db = ReferenceDB()
            service = PeopleGroupService(db)
            for gid in group_ids:
                try:
                    result = service.compute_together_matches(self.project_id, gid)
                    count = result.get("match_count", 0) if result else 0
                    logger.info("[FacePipelineWorker] Group %d: %d matches", gid, count)
                except Exception as ge:
                    logger.warning("[FacePipelineWorker] Group %d recompute failed: %s", gid, ge)
            db.close()
        except Exception as e:
            logger.warning("[FacePipelineWorker] Group recompute failed: %s", e)

    # ── Progressive clustering ────────────────────────────────────

    def _should_run_interim_cluster(self, faces_so_far: int) -> bool:
        """Decide whether to trigger an interim clustering pass.

        Thresholds mirror the approach used by Google Photos and Apple Photos:
        show something useful early, then refine as more data arrives.
        """
        if faces_so_far < _FIRST_INTERIM_THRESHOLD:
            return False

        faces_since_last = faces_so_far - self._faces_at_last_interim
        now = time.perf_counter()
        elapsed = now - self._last_interim_time

        # First interim pass
        if self._faces_at_last_interim == 0:
            return True

        # Subsequent passes: enough new faces AND enough time elapsed
        if faces_since_last >= _SUBSEQUENT_INTERVAL and elapsed >= _MIN_INTERIM_GAP_S:
            return True

        return False

    def _run_interim_clustering(self, faces_so_far: int):
        """Run a lightweight clustering pass on faces detected so far.

        This is NOT the final cluster — it gives the user approximate People
        results while detection continues.  The final recluster at pipeline
        end produces the authoritative grouping.
        """
        try:
            from config.face_detection_config import get_face_config
            from workers.face_cluster_worker import FaceClusterWorker

            face_config = get_face_config()
            cluster_params = face_config.get_clustering_params()

            cluster_worker = FaceClusterWorker(
                project_id=self.project_id,
                eps=cluster_params["eps"],
                min_samples=cluster_params["min_samples"],
                auto_tune=True,
            )

            interim_result = {}

            def _on_interim_finished(cluster_count, total_faces):
                interim_result["cluster_count"] = cluster_count
                interim_result["total_faces"] = total_faces

            cluster_worker.signals.finished.connect(_on_interim_finished)

            logger.info(
                "[FacePipelineWorker] Running interim clustering "
                "(%d faces so far, pass #%d)",
                faces_so_far, self._interim_cluster_count + 1,
            )

            cluster_worker.run()

            self._interim_cluster_count += 1
            self._faces_at_last_interim = faces_so_far
            self._last_interim_time = time.perf_counter()

            cc = interim_result.get("cluster_count", 0)
            logger.info(
                "[FacePipelineWorker] Interim clustering #%d complete: "
                "%d clusters from %d faces",
                self._interim_cluster_count, cc, faces_so_far,
            )

            # Signal UI to refresh People section (is_final=False)
            self.signals.interim_clusters_ready.emit(
                cc, faces_so_far, False,
            )

        except Exception as e:
            logger.warning(
                "[FacePipelineWorker] Interim clustering failed (non-fatal): %s", e
            )

    # ── Main pipeline ─────────────────────────────────────────────

    def run(self):
        """Execute face detection + clustering sequentially in background thread."""
        _thread = threading.current_thread()
        _is_main = _thread is threading.main_thread()
        logger.info(
            "[FacePipelineWorker] Starting face pipeline for project %d "
            "(thread=%s, is_main=%s)",
            self.project_id, _thread.name, _is_main,
        )

        results = {
            "faces_detected": 0,
            "images_processed": 0,
            "clusters_created": 0,
            "interim_passes": 0,
            "errors": [],
        }

        # ── Step 0a: Snapshot group member identities before clearing ──
        # Google/Apple pattern: groups survive re-clustering via identity anchors
        group_snapshot = {}
        try:
            group_snapshot = self._snapshot_group_members()
        except Exception as e:
            logger.warning("[FacePipelineWorker] Group snapshot warning: %s", e)

        # ── Step 0b: Clear stale face data from previous runs ──────
        if self._cancelled:
            self.signals.finished.emit(results)
            return

        self.signals.progress.emit("cleanup", "Clearing previous face detection data...")
        try:
            self._clear_stale_face_data()
            logger.info("[FacePipelineWorker] Cleared stale face data for project %d", self.project_id)
        except Exception as e:
            logger.warning("[FacePipelineWorker] Cleanup warning (continuing): %s", e)

        # ── Step 1: Face Detection ────────────────────────────────
        if self._cancelled:
            self.signals.finished.emit(results)
            return

        self.signals.progress.emit("face_detection", "Detecting faces in photos...")

        try:
            from workers.face_detection_worker import FaceDetectionWorker

            worker_kwargs = {
                "project_id": self.project_id,
                "model": self.model,
                "skip_processed": True,
            }
            if self._scoped_photo_paths:
                worker_kwargs["photo_paths"] = self._scoped_photo_paths

            face_worker = FaceDetectionWorker(**worker_kwargs)

            detection_results = {}

            def _on_detect_progress(current, total, message):
                self.signals.progress.emit(
                    "face_detection",
                    f"Detecting faces: {current}/{total} — {message}",
                )

            def _on_detect_batch(processed, total, faces_so_far, pid):
                # Forward to pipeline-level signal for incremental UI refresh
                self.signals.batch_committed.emit(processed, total, faces_so_far, pid)

                # ── Progressive clustering check ──
                if not self._cancelled and self._should_run_interim_cluster(faces_so_far):
                    self.signals.progress.emit(
                        "interim_clustering",
                        f"Quick-clustering {faces_so_far} faces (partial results)...",
                    )
                    self._run_interim_clustering(faces_so_far)
                    # Resume detection progress message
                    self.signals.progress.emit(
                        "face_detection",
                        f"Detecting faces: {processed}/{total} — resuming...",
                    )

            def _on_detect_finished(success, failed, total_faces):
                detection_results["success"] = success
                detection_results["failed"] = failed
                detection_results["total_faces"] = total_faces

            def _on_detect_error(path, msg):
                logger.warning("[FacePipelineWorker] Detection error on %s: %s", path, msg)

            face_worker.signals.progress.connect(_on_detect_progress)
            face_worker.signals.batch_committed.connect(_on_detect_batch)
            face_worker.signals.finished.connect(_on_detect_finished)
            face_worker.signals.error.connect(_on_detect_error)

            # Execute directly in this thread (already off UI)
            face_worker.run()

            # Collect results (signals fire synchronously in same thread)
            results["faces_detected"] = detection_results.get("total_faces", 0)
            results["images_processed"] = detection_results.get("success", 0)
            results["interim_passes"] = self._interim_cluster_count

            logger.info(
                "[FacePipelineWorker] Detection complete: %d faces in %d images "
                "(%d interim cluster passes)",
                results["faces_detected"], results["images_processed"],
                self._interim_cluster_count,
            )

            # ── Invariant check: faces_written_to_db == faces_detected ──
            try:
                from reference_db import ReferenceDB as _DB
                _db = _DB()
                with _db._connect() as _conn:
                    _cur = _conn.cursor()
                    _cur.execute(
                        "SELECT COUNT(*) FROM face_crops "
                        "WHERE project_id = ? AND embedding IS NOT NULL",
                        (self.project_id,),
                    )
                    faces_in_db = _cur.fetchone()[0]
                if faces_in_db != results["faces_detected"]:
                    logger.warning(
                        "[FacePipelineWorker] INVARIANT: faces_detected=%d but "
                        "faces_in_db=%d — possible insert/skip mismatch",
                        results["faces_detected"], faces_in_db,
                    )
                else:
                    logger.info(
                        "[FacePipelineWorker] INVARIANT OK: faces_detected == "
                        "faces_in_db == %d", faces_in_db,
                    )
            except Exception as inv_err:
                logger.debug("[FacePipelineWorker] Invariant check error: %s", inv_err)

        except Exception as e:
            logger.error("[FacePipelineWorker] Face detection failed: %s", e, exc_info=True)
            results["errors"].append(f"Detection: {e}")

        # ── Step 2: Final Face Clustering ─────────────────────────
        if self._cancelled or results["faces_detected"] == 0:
            if results["faces_detected"] == 0:
                logger.info("[FacePipelineWorker] No faces detected, skipping clustering")
            self.signals.finished.emit(results)
            return

        self.signals.progress.emit("face_clustering", "Final clustering of all detected faces...")

        try:
            from config.face_detection_config import get_face_config
            face_config = get_face_config()
            cluster_params = face_config.get_clustering_params()

            from workers.face_cluster_worker import FaceClusterWorker

            cluster_worker = FaceClusterWorker(
                project_id=self.project_id,
                eps=cluster_params["eps"],
                min_samples=cluster_params["min_samples"],
                auto_tune=True,
            )

            cluster_results = {}

            def _on_cluster_progress(current, total, message):
                self.signals.progress.emit(
                    "face_clustering",
                    f"Clustering faces: {message}",
                )

            def _on_cluster_finished(cluster_count, total_faces):
                cluster_results["cluster_count"] = cluster_count
                cluster_results["total_faces"] = total_faces

            def _on_cluster_error(msg):
                results["errors"].append(f"Clustering: {msg}")

            cluster_worker.signals.progress.connect(_on_cluster_progress)
            cluster_worker.signals.finished.connect(_on_cluster_finished)
            cluster_worker.signals.error.connect(_on_cluster_error)

            # Execute directly in this thread
            cluster_worker.run()

            results["clusters_created"] = cluster_results.get("cluster_count", 0)

            logger.info(
                "[FacePipelineWorker] Final clustering complete: %d clusters from %d faces",
                results["clusters_created"],
                cluster_results.get("total_faces", 0),
            )

            # Signal UI that final clusters are ready
            self.signals.interim_clusters_ready.emit(
                results["clusters_created"],
                results["faces_detected"],
                True,  # is_final=True
            )

        except Exception as e:
            logger.error("[FacePipelineWorker] Clustering failed: %s", e, exc_info=True)
            results["errors"].append(f"Clustering: {e}")

        # ── Step 3: Remap group members + recompute matches ────────
        # Google/Apple pattern: groups survive re-clustering automatically
        if group_snapshot and not self._cancelled:
            self.signals.progress.emit("group_remap", "Updating groups after re-clustering...")
            try:
                self._remap_group_members(group_snapshot)
                self._recompute_all_groups()
            except Exception as e:
                logger.warning("[FacePipelineWorker] Group remap/recompute failed: %s", e)

        self.signals.finished.emit(results)
