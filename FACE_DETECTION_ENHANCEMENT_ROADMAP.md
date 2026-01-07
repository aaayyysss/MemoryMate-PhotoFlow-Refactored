# Face Detection Enhancement Roadmap
**Date:** January 7, 2026
**Based on:** Pre-Deployment Audit Report
**Priority Order:** Critical → High → Medium → Low

---

## 🔴 Critical Enhancements (Before Deployment)

### 1. Transactional Face Saving
**File:** `workers/face_detection_worker.py:356-423`
**Issue:** Face crops saved before embedding validation
**Impact:** Orphaned files if embedding generation fails
**Effort:** 2-4 hours

**Implementation:**
```python
def _save_face_transactional(self, db, image_path, face, face_idx, face_crops_dir):
    """
    Atomically save face crop and embedding.
    Rollback on failure to prevent orphaned files.
    """
    crop_path = None
    try:
        # Validate embedding exists first
        if face.get('embedding') is None:
            logger.warning(f"No embedding for {image_path}, skipping")
            return False

        # Generate crop path
        image_basename = os.path.splitext(os.path.basename(image_path))[0]
        crop_filename = f"{image_basename}_face{face_idx}.jpg"
        crop_path = os.path.join(face_crops_dir, crop_filename)

        # Save crop to disk
        face_service = get_face_detection_service()
        if get_face_config().get('save_face_crops', True):
            if not face_service.save_face_crop(image_path, face, crop_path):
                return False

        # Save to database (with transaction)
        embedding_bytes = face['embedding'].astype(np.float32).tobytes()
        with db._connect() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO face_crops
                    (project_id, image_path, crop_path, embedding,
                     bbox_x, bbox_y, bbox_w, bbox_h, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (self.project_id, image_path, crop_path, embedding_bytes,
                      face['bbox_x'], face['bbox_y'], face['bbox_w'],
                      face['bbox_h'], face['confidence']))
                conn.commit()
                return True
            except Exception as db_error:
                conn.rollback()
                # Cleanup orphaned crop file
                if crop_path and os.path.exists(crop_path):
                    os.remove(crop_path)
                    logger.warning(f"Rolled back face crop: {crop_path}")
                raise db_error

    except Exception as e:
        logger.error(f"Failed to save face transactionally: {e}")
        # Final cleanup check
        if crop_path and os.path.exists(crop_path):
            try:
                os.remove(crop_path)
            except:
                pass
        return False
```

**Testing:**
- Simulate embedding generation failure
- Verify no orphaned crop files
- Verify database consistency

---

### 2. Comprehensive Logging Enhancement
**Files:** All face detection modules
**Issue:** Insufficient logging for production troubleshooting
**Impact:** Hard to diagnose user issues
**Effort:** 4-6 hours

**Implementation:**
```python
# Add structured logging throughout
import logging
import json
from datetime import datetime

class FaceDetectionLogger:
    """Structured logging for face detection operations."""

    def __init__(self, project_id):
        self.project_id = project_id
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = f".memorymate/logs/face_detection_{project_id}_{self.session_id}.json"

    def log_detection_start(self, params):
        """Log detection session start with parameters."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "detection_start",
            "project_id": self.project_id,
            "session_id": self.session_id,
            "parameters": params,
            "hardware": self._get_hardware_info()
        }
        self._write_log(log_entry)

    def log_photo_processed(self, photo_path, faces_found, duration_ms):
        """Log individual photo processing result."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "photo_processed",
            "photo_path": photo_path,
            "faces_found": faces_found,
            "duration_ms": duration_ms
        }
        self._write_log(log_entry)

    def log_error(self, photo_path, error_type, error_message, traceback):
        """Log errors with full context."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "error",
            "photo_path": photo_path,
            "error_type": error_type,
            "error_message": error_message,
            "traceback": traceback
        }
        self._write_log(log_entry)

    def _write_log(self, entry):
        """Append log entry to JSON log file."""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(entry) + "\n")
```

**Integration Points:**
- `face_detection_worker.py:run()` - Session start/end
- `face_detection_service.py:detect_faces()` - Per-photo logging
- All exception handlers - Error logging

---

### 3. Video File Exclusion Notification
**File:** `workers/face_detection_worker.py:274-312`
**Issue:** Videos silently skipped, users confused
**Impact:** Poor user experience
**Effort:** 1-2 hours

**Implementation:**
```python
def _get_photos_to_process(self, db: ReferenceDB) -> list:
    """Get photos with video exclusion notification."""
    # ... existing code ...

    # Enhanced notification
    if videos_excluded > 0:
        self._stats['videos_excluded'] = videos_excluded

        # Emit user-visible notification
        notification_msg = (
            f"Note: {videos_excluded} video files excluded from face detection. "
            f"Face detection currently supports photos only. "
            f"Processing {total_count} photos..."
        )
        self.signals.progress.emit(0, total_count, notification_msg)

        logger.info(f"[FaceDetectionWorker] {notification_msg}")

        # Optional: Show info dialog (if UI available)
        if self.show_notifications:
            self._show_video_exclusion_info(videos_excluded, total_count)

    # ... rest of code ...
```

---

## 🟡 High Priority (Do Soon After Deployment)

### 4. GPU Batch Processing
**File:** `services/face_detection_service.py`
**Expected Gain:** 2-5x speedup on GPU systems
**Effort:** 8-12 hours

**Implementation:**
```python
def batch_detect_faces_gpu(self, image_paths: List[str],
                           batch_size: int = 4) -> Dict[str, List[dict]]:
    """
    GPU-optimized batch face detection.

    Processes multiple images in single GPU inference call for better throughput.
    Expected performance: 2-5x faster than sequential processing.

    Args:
        image_paths: List of image paths to process
        batch_size: Number of images to process in parallel (2-8 for most GPUs)

    Returns:
        Dict mapping image_path -> list of detected faces
    """
    results = {}

    # Process in batches
    for i in range(0, len(image_paths), batch_size):
        batch_paths = image_paths[i:i+batch_size]

        # Load and preprocess batch
        batch_images = []
        valid_paths = []
        for path in batch_paths:
            try:
                img = self._load_and_preprocess(path)
                if img is not None:
                    batch_images.append(img)
                    valid_paths.append(path)
            except Exception as e:
                logger.warning(f"Failed to load {path}: {e}")
                results[path] = []

        if not batch_images:
            continue

        # Batch inference (single GPU call)
        try:
            # InsightFace batch processing
            batch_faces = self.app.get_batch(batch_images)

            # Map results back to paths
            for path, faces in zip(valid_paths, batch_faces):
                results[path] = self._format_faces(faces)

        except Exception as e:
            logger.error(f"Batch inference failed: {e}")
            # Fallback to sequential processing
            for path in valid_paths:
                results[path] = self.detect_faces(path)

    return results
```

**Integration:**
```python
# In face_detection_worker.py
if self._has_gpu() and total_photos > 10:
    # Use batch processing for GPU
    results = face_service.batch_detect_faces_gpu(
        photo_paths, batch_size=4
    )
else:
    # Sequential processing for CPU
    for photo_path in photo_paths:
        faces = face_service.detect_faces(photo_path)
```

**Testing:**
- Benchmark 100 photos: GPU batch vs sequential
- Measure memory usage
- Test with different batch sizes (2, 4, 8)

---

### 5. Quality Threshold Filtering
**File:** `services/face_detection_service.py:616-963`
**Expected Gain:** 20-30% reduction in low-quality faces
**Effort:** 4-6 hours

**Implementation:**
```python
def detect_faces(self, image_path: str, project_id: Optional[int] = None) -> List[dict]:
    """Enhanced with quality filtering."""

    # ... existing detection code ...

    # Get quality threshold from config
    cfg = get_face_config()
    params = cfg.get_detection_params(project_id)
    min_quality = float(params.get('min_quality_score', 0.0))  # 0 = disabled

    # Filter by quality if enabled
    if min_quality > 0:
        original_count = len(faces)
        faces = [f for f in faces if f.get('quality', 0) >= min_quality]
        filtered_count = original_count - len(faces)

        if filtered_count > 0:
            logger.info(
                f"[FaceDetection] Filtered {filtered_count} low-quality faces "
                f"(threshold: {min_quality:.1f}/100) from {os.path.basename(image_path)}"
            )

    # ... rest of code ...
```

**Configuration:**
```python
# In config/face_detection_config.py
DEFAULT_CONFIG = {
    # ...
    "min_quality_score": 0.0,  # 0 = disabled, 40 = Fair, 60 = Good, 80 = Excellent
    "quality_metrics": {
        "blur_weight": 0.30,
        "lighting_weight": 0.25,
        "size_weight": 0.20,
        "aspect_weight": 0.10,
        "confidence_weight": 0.15
    }
}
```

**UI Integration:**
```python
# Add to face detection settings dialog
quality_slider = QSlider(Qt.Horizontal)
quality_slider.setRange(0, 100)
quality_slider.setValue(cfg.get('min_quality_score', 0))
quality_slider.setToolTip(
    "Minimum quality score for faces:\n"
    "0 = All faces (default)\n"
    "40 = Fair quality and above\n"
    "60 = Good quality and above\n"
    "80 = Excellent quality only"
)
```

---

### 6. Smart Representative Selection
**File:** `workers/face_cluster_worker.py:350-450`
**Expected Gain:** Better UI, more accurate person identification
**Effort:** 4-6 hours

**Implementation:**
```python
def _select_best_representative(self, cluster_faces: List[dict],
                                cluster_embeddings: np.ndarray) -> dict:
    """
    Select highest quality face as cluster representative.

    Scoring criteria (weighted):
    1. Quality score (40%) - Overall quality metric
    2. Centrality (30%) - Distance to cluster centroid
    3. Face size (20%) - Larger faces preferred
    4. Confidence (10%) - Detection confidence

    Args:
        cluster_faces: List of face dicts with metadata
        cluster_embeddings: Embeddings for faces in cluster

    Returns:
        Best representative face dict
    """
    if len(cluster_faces) == 1:
        return cluster_faces[0]

    # Calculate cluster centroid
    centroid = np.mean(cluster_embeddings, axis=0)

    # Score each face
    scores = []
    for i, (face, embedding) in enumerate(zip(cluster_faces, cluster_embeddings)):
        # Quality score (0-100)
        quality = face.get('quality', 50.0)
        quality_score = quality / 100.0

        # Centrality score (0-1, higher = closer to centroid)
        distance = np.linalg.norm(embedding - centroid)
        centrality_score = 1.0 / (1.0 + distance)

        # Size score (0-1)
        face_area = face.get('bbox_w', 0) * face.get('bbox_h', 0)
        size_score = min(1.0, face_area / 25000.0)  # Normalize to 160x160

        # Confidence score (0-1)
        confidence_score = face.get('confidence', 0.5)

        # Weighted combination
        total_score = (
            quality_score * 0.40 +
            centrality_score * 0.30 +
            size_score * 0.20 +
            confidence_score * 0.10
        )

        scores.append((total_score, i, face))

    # Select highest scoring face
    best_score, best_idx, best_face = max(scores, key=lambda x: x[0])

    logger.info(
        f"[FaceCluster] Selected representative with score {best_score:.3f} "
        f"(quality: {best_face.get('quality', 0):.1f}/100)"
    )

    return best_face
```

**Integration:**
```python
# In clustering loop
for cid in unique_labels:
    mask = labels == cid
    cluster_vecs = X[mask]
    cluster_indices = np.where(mask)[0]
    cluster_faces_data = [
        {
            'id': ids[i],
            'path': paths[i],
            'quality': qualities[i],
            'bbox_w': bboxes[i]['bbox'][2],
            'bbox_h': bboxes[i]['bbox'][3],
            'confidence': bboxes[i]['confidence']
        }
        for i in cluster_indices
    ]

    # Select best representative
    representative = self._select_best_representative(
        cluster_faces_data, cluster_vecs
    )

    rep_path = representative['path']
    # ... save cluster ...
```

---

## 🟢 Medium Priority (Enhancements)

### 7. Duplicate Face Detection
**Effort:** 6-8 hours
**Expected Gain:** Cleaner clusters, reduced redundancy

**Implementation:**
```python
def remove_duplicate_faces(self, faces: List[dict], iou_threshold: float = 0.7) -> List[dict]:
    """
    Remove duplicate face detections using IoU (Intersection over Union).

    Sometimes the same face is detected multiple times with overlapping bboxes.
    This removes duplicates, keeping the highest confidence detection.
    """
    if len(faces) <= 1:
        return faces

    # Sort by confidence (descending)
    faces_sorted = sorted(faces, key=lambda f: f['confidence'], reverse=True)

    keep = []
    for face in faces_sorted:
        # Check if this face overlaps significantly with any kept face
        is_duplicate = False
        for kept_face in keep:
            iou = self._calculate_iou(face, kept_face)
            if iou > iou_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            keep.append(face)

    removed_count = len(faces) - len(keep)
    if removed_count > 0:
        logger.info(f"Removed {removed_count} duplicate face detections")

    return keep

def _calculate_iou(self, face1: dict, face2: dict) -> float:
    """Calculate Intersection over Union for two face bboxes."""
    # Get bounding boxes
    x1_1, y1_1 = face1['bbox_x'], face1['bbox_y']
    x2_1, y2_1 = x1_1 + face1['bbox_w'], y1_1 + face1['bbox_h']

    x1_2, y1_2 = face2['bbox_x'], face2['bbox_y']
    x2_2, y2_2 = x1_2 + face2['bbox_w'], y1_2 + face2['bbox_h']

    # Calculate intersection
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)

    if x2_i < x1_i or y2_i < y1_i:
        return 0.0  # No intersection

    intersection = (x2_i - x1_i) * (y2_i - y1_i)

    # Calculate union
    area1 = face1['bbox_w'] * face1['bbox_h']
    area2 = face2['bbox_w'] * face2['bbox_h']
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0
```

---

### 8. Pause/Resume Functionality
**Effort:** 8-10 hours
**Expected Gain:** Better UX for large libraries

**Implementation:**
```python
# Checkpoint system
class DetectionCheckpoint:
    """Manages face detection checkpoints for pause/resume."""

    def __init__(self, project_id):
        self.project_id = project_id
        self.checkpoint_file = f".memorymate/checkpoints/detection_{project_id}.json"

    def save(self, state: dict):
        """Save current detection state."""
        os.makedirs(os.path.dirname(self.checkpoint_file), exist_ok=True)
        with open(self.checkpoint_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'project_id': self.project_id,
                'photos_processed': state['photos_processed'],
                'photos_total': state['photos_total'],
                'faces_detected': state['faces_detected'],
                'last_photo_path': state.get('last_photo_path'),
                'config_snapshot': state.get('config')
            }, f, indent=2)

    def load(self) -> Optional[dict]:
        """Load checkpoint if exists."""
        if not os.path.exists(self.checkpoint_file):
            return None

        with open(self.checkpoint_file, 'r') as f:
            return json.load(f)

    def delete(self):
        """Delete checkpoint."""
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)

# Integration in worker
class FaceDetectionWorker(QRunnable):
    def run(self):
        checkpoint = DetectionCheckpoint(self.project_id)

        # Check for existing checkpoint
        state = checkpoint.load()
        if state:
            logger.info(f"Resuming from checkpoint: {state['photos_processed']}/{state['photos_total']}")
            start_from = state['photos_processed']
        else:
            start_from = 0

        # Process photos
        for idx, photo in enumerate(photos[start_from:], start_from):
            # ... process photo ...

            # Save checkpoint every 50 photos
            if idx % 50 == 0:
                checkpoint.save({
                    'photos_processed': idx,
                    'photos_total': total_photos,
                    'faces_detected': self._stats['faces_detected'],
                    'last_photo_path': photo['path'],
                    'config': get_face_config().to_dict()
                })

        # Delete checkpoint on completion
        checkpoint.delete()
```

---

## 🔵 Low Priority (Future Improvements)

### 9. Advanced Quality Metrics
- Pose estimation (frontal vs profile)
- Blur gradient analysis
- Occlusion detection
- Eye openness detection

### 10. Privacy Features
- Optional encryption for embeddings
- Data retention policies
- GDPR compliance tools
- Face data export/deletion

### 11. Performance Dashboards
- Real-time detection speed graphs
- Quality distribution histograms
- Clustering accuracy trends
- Hardware utilization monitoring

---

## Implementation Timeline

### Week 1: Critical Items
- [ ] Day 1-2: Transactional face saving (#1)
- [ ] Day 3-4: Comprehensive logging (#2)
- [ ] Day 5: Video exclusion notification (#3)
- [ ] Testing and validation

### Week 2: High Priority
- [ ] Day 1-3: GPU batch processing (#4)
- [ ] Day 4-5: Quality threshold filtering (#5)
- [ ] Testing and benchmarking

### Week 3: High Priority (continued)
- [ ] Day 1-3: Smart representative selection (#6)
- [ ] Day 4-5: Integration testing
- [ ] Performance validation

### Week 4: Medium Priority
- [ ] Day 1-2: Duplicate face detection (#7)
- [ ] Day 3-5: Pause/resume functionality (#8)
- [ ] Final testing

### Week 5: Beta Deployment
- [ ] Deploy to beta users
- [ ] Monitor performance metrics
- [ ] Collect user feedback
- [ ] Bug fixes

### Week 6+: Full Deployment
- [ ] Full production deployment
- [ ] Low priority enhancements
- [ ] Ongoing monitoring

---

## Success Metrics

### Performance Targets
- [ ] GPU detection: 100+ photos/second (2x improvement)
- [ ] CPU detection: 40+ photos/second (2x improvement)
- [ ] Memory usage: <2GB for 1000 photos
- [ ] Clustering time: <5 seconds for 1000 faces

### Quality Targets
- [ ] Clustering accuracy: >95% (up from 85-90%)
- [ ] False positive rate: <5%
- [ ] User satisfaction: >4.5/5 stars

### Reliability Targets
- [ ] Zero orphaned face crops
- [ ] 100% error logging coverage
- [ ] <1% crash rate during detection
- [ ] Full recovery from interruptions

---

**Document Version:** 1.0
**Last Updated:** January 7, 2026
**Next Review:** After Week 3 (before beta deployment)
