# Count Mismatch After Merge - Root Cause Analysis

## Problem

After merging face clusters with duplicate photos, the count displayed in the People section is **higher** than the actual number of photos shown in the grid.

## Root Cause

### Current Count Update Logic (reference_db.py:4913-4916)

```python
UPDATE face_branch_reps
SET count = (
    SELECT COUNT(*)        # ← Counts ALL face_crops entries
    FROM face_crops
    WHERE project_id = ? AND branch_key = ?
)
```

**Problem:** This counts **ALL face_crops entries**, including multiple faces from the same photo.

### Grid Display Logic (layouts/google_layout.py:9151-9185)

```python
SELECT DISTINCT pm.path, ...    # ← Returns UNIQUE photos only
FROM photo_metadata pm
JOIN project_images pi ON pm.path = pi.image_path
WHERE pi.project_id = ?
AND pm.path IN (
    SELECT DISTINCT image_path  # ← DISTINCT photos with this face
    FROM face_crops
    WHERE project_id = ? AND branch_key = ?
)
```

**Behavior:** This displays **UNIQUE photos** (DISTINCT).

## The Mismatch Scenario

### Example with Multiple Faces Per Photo

**Initial State:**
```
Photo1.jpg has 2 detected faces:
  - Face A (Person 1) → face_001
  - Face B (Person 2) → face_002

Photo2.jpg has 2 detected faces:
  - Face A (Person 1) → face_001
  - Face B (Person 2) → face_002

face_003: Photo3, Photo4, Photo5 (10 more photos)
```

**Database State:**
```
face_crops table:
  face_001: [Photo1/FaceA, Photo2/FaceA] = 2 entries
  face_002: [Photo1/FaceB, Photo2/FaceB] = 2 entries
  face_003: [Photo3, Photo4, Photo5...] = 10 entries

project_images table:
  face_001: [Photo1, Photo2] = 2 unique photos
  face_002: [Photo1, Photo2] = 2 unique photos
  face_003: [Photo3-Photo12] = 10 unique photos
```

### First Merge: face_001 → face_003

**After merge:**
```
face_crops:
  face_003: 12 entries (10 original + 2 from face_001)

project_images:
  face_003: 12 unique photos (10 original + 2 from face_001)

COUNT UPDATE:
  count = COUNT(*) FROM face_crops = 12 ✓ Correct!

Grid displays: 12 photos ✓ Matches!
```

### Second Merge: face_002 → face_003

**After merge:**
```
face_crops:
  face_003: 14 entries (12 previous + 2 from face_002)
            ← But Photo1 and Photo2 face_crops now have 2 entries each!
               (FaceA and FaceB both in face_003)

project_images (after duplicate deletion):
  face_003: 12 unique photos (Photo1, Photo2 already existed as duplicates)
            ← Correctly kept only 12 unique photos

COUNT UPDATE:
  count = COUNT(*) FROM face_crops = 14 ✗ WRONG!
  ↑ Counts all face_crops, including 2 faces from same photos

Grid displays: 12 unique photos ✓ Correct!

MISMATCH: Count shows 14, grid shows 12
```

## Why This Happens

1. **Multiple faces per photo**: When a photo has multiple detected faces (Face A and Face B)
2. **Sequential merges**: Merging both Face A and Face B into the same target
3. **face_crops count**: Counts face instances (14 = 10 original + 2×FaceA + 2×FaceB)
4. **Grid display**: Counts unique photos (12 = 10 original + Photo1 + Photo2)

## The Fix

### Current (Wrong)
```python
# Counts face_crops entries (can have multiple per photo)
UPDATE face_branch_reps
SET count = (
    SELECT COUNT(*)
    FROM face_crops
    WHERE project_id = ? AND branch_key = ?
)
```

### Fixed (Correct)
```python
# Counts DISTINCT photos (matches grid display)
UPDATE face_branch_reps
SET count = (
    SELECT COUNT(DISTINCT fc.image_path)
    FROM face_crops fc
    JOIN project_images pi ON fc.image_path = pi.image_path
                          AND fc.project_id = pi.project_id
                          AND fc.branch_key = pi.branch_key
    WHERE fc.project_id = ? AND fc.branch_key = ?
)
```

**Why this works:**
- Uses `COUNT(DISTINCT fc.image_path)` to count unique photos
- Joins with `project_images` to match exactly what the grid displays
- Handles multiple faces per photo correctly
- After merge with duplicates: Shows 12, grid shows 12 ✓

## Best Practice: Post-Merge Count Refresh

After any merge operation, refresh counts for ALL affected face clusters based on the actual final database state:

```python
def refresh_face_counts(project_id):
    """
    Refresh counts for ALL face clusters to reflect actual unique photos.
    Should be called after merge operations to ensure accuracy.
    """
    cur.execute(
        """
        UPDATE face_branch_reps
        SET count = (
            SELECT COUNT(DISTINCT fc.image_path)
            FROM face_crops fc
            JOIN project_images pi ON fc.image_path = pi.image_path
                                  AND fc.project_id = pi.project_id
                                  AND fc.branch_key = pi.branch_key
            WHERE fc.project_id = face_branch_reps.project_id
              AND fc.branch_key = face_branch_reps.branch_key
        )
        WHERE project_id = ?
        """,
        [project_id]
    )
```

## Benefits

1. **Accuracy**: Count always matches grid display
2. **Duplicate handling**: Correctly handles multiple faces per photo
3. **Post-merge consistency**: Refreshing all counts ensures database-wide accuracy
4. **User trust**: No confusion about mismatched counts

## Testing

- [x] Single face per photo merge: Count matches
- [x] Multiple faces per photo: Count = unique photos, not face instances
- [x] Sequential merge with duplicates: Count stays accurate
- [x] After undo/redo: Counts refresh correctly
