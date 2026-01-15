# Face Filter Bug Fix
**Date:** 2025-12-05
**Issue:** Grid shows 12 photos but should show 14 for face_003
**Root Cause:** Data integrity - 2 photos in face_crops don't exist in photo_metadata or project_images

---

## Corrected Analysis

### What's Correct:
- ✅ People card count: **14 photos** (from face_branch_reps.count)
- ✅ face_crops table has 14 entries for face_003

### What's Wrong:
- ❌ Grid displays: **12 photos** (missing 2)
- ❌ Grid query returns only 12 rows

---

## Root Cause

The grid query (google_layout.py:9150-9188) requires photos to exist in **ALL THREE** tables:

```sql
SELECT DISTINCT pm.path, pm.created_date as date_taken, pm.width, pm.height
FROM photo_metadata pm
JOIN project_images pi ON pm.path = pi.image_path
WHERE pi.project_id = ?
AND pm.path IN (
    SELECT DISTINCT image_path
    FROM face_crops
    WHERE project_id = ? AND branch_key = ?
)
ORDER BY pm.date_taken DESC
```

**The problem:** 2 photos exist in `face_crops` but NOT in:
- `photo_metadata` (missing EXIF/metadata)
- OR `project_images` (not linked to project properly)

---

## Diagnostic Queries

Run these on the provided database to confirm:

### Query 1: Find ALL 14 photos in face_crops
```sql
SELECT DISTINCT fc.image_path
FROM face_crops fc
WHERE fc.project_id = 1 AND fc.branch_key = 'face_003'
ORDER BY fc.image_path;
```
**Expected:** 14 rows

### Query 2: Check which photos are in photo_metadata
```sql
SELECT fc.image_path,
       CASE WHEN pm.path IS NOT NULL THEN 'YES' ELSE 'NO - MISSING' END as in_photo_metadata
FROM face_crops fc
LEFT JOIN photo_metadata pm ON fc.image_path = pm.path
WHERE fc.project_id = 1 AND fc.branch_key = 'face_003'
ORDER BY fc.image_path;
```
**Expected:** Shows which 2 are missing from photo_metadata

### Query 3: Check which photos are in project_images
```sql
SELECT fc.image_path,
       CASE WHEN pi.image_path IS NOT NULL THEN 'YES' ELSE 'NO - MISSING' END as in_project_images
FROM face_crops fc
LEFT JOIN project_images pi ON fc.image_path = pi.image_path AND pi.project_id = fc.project_id
WHERE fc.project_id = 1 AND fc.branch_key = 'face_003'
ORDER BY fc.image_path;
```
**Expected:** Shows which 2 are missing from project_images

### Query 4: Find the 2 missing photos (comprehensive)
```sql
SELECT
    fc.image_path,
    CASE WHEN pm.path IS NULL THEN '❌ NOT in photo_metadata' ELSE '✅ in photo_metadata' END as metadata_status,
    CASE WHEN pi.image_path IS NULL THEN '❌ NOT in project_images' ELSE '✅ in project_images' END as project_status,
    CASE WHEN pm.path IS NOT NULL AND pi.image_path IS NOT NULL THEN '✅ SHOWN IN GRID'
         ELSE '❌ MISSING FROM GRID' END as grid_status
FROM face_crops fc
LEFT JOIN photo_metadata pm ON fc.image_path = pm.path
LEFT JOIN project_images pi ON fc.image_path = pi.image_path AND pi.project_id = fc.project_id
WHERE fc.project_id = 1 AND fc.branch_key = 'face_003'
ORDER BY grid_status, fc.image_path;
```
**Expected:** Shows exactly which 2 photos are missing and why

---

## Possible Root Causes

### Scenario A: Photos Not Scanned into Metadata
- Face detection ran BEFORE photo scan
- Photos added to face_crops but never scanned into photo_metadata
- **Fix:** Re-scan repository to populate photo_metadata

### Scenario B: Photos Not Linked to Project
- Photos scanned but not added to project_images table
- Orphaned entries in face_crops
- **Fix:** Link photos to project or clean up face_crops

### Scenario C: Photos Deleted After Face Detection
- Photos were scanned and detected
- Later deleted from photo_metadata/project_images
- face_crops entries remain (orphaned)
- **Fix:** Clean up orphaned face_crops entries

---

## Solution Options

### Option 1: Fix Data Integrity ⭐ RECOMMENDED
**Ensure all photos in face_crops exist in photo_metadata and project_images**

**Implementation:**
```sql
-- Find orphaned face_crops entries
SELECT fc.image_path
FROM face_crops fc
LEFT JOIN photo_metadata pm ON fc.image_path = pm.path
LEFT JOIN project_images pi ON fc.image_path = pi.image_path AND pi.project_id = fc.project_id
WHERE fc.project_id = 1
AND (pm.path IS NULL OR pi.image_path IS NULL);

-- Clean up orphaned entries (after confirming they should be removed)
DELETE FROM face_crops
WHERE id IN (
    SELECT fc.id
    FROM face_crops fc
    LEFT JOIN photo_metadata pm ON fc.image_path = pm.path
    LEFT JOIN project_images pi ON fc.image_path = pi.image_path AND pi.project_id = fc.project_id
    WHERE fc.project_id = ?
    AND (pm.path IS NULL OR pi.image_path IS NULL)
);

-- Then re-cluster to update counts
```

**Pros:**
- ✅ Maintains data integrity
- ✅ Grid and count will match
- ✅ No orphaned data

**Cons:**
- ⚠️ May lose face detection data for missing photos
- ⚠️ Requires re-clustering

### Option 2: Add Missing Photos to Metadata/Project
**Scan missing photos into photo_metadata and link to project**

**Implementation:**
- Identify the 2 missing photo paths
- Run photo scan service to add them to photo_metadata
- Link them to project via project_images
- Verify grid now shows all 14

**Pros:**
- ✅ No data loss
- ✅ All 14 photos will appear in grid

**Cons:**
- ⚠️ Requires photos to still exist on disk
- ⚠️ If photos were intentionally deleted, this recreates them

### Option 3: Make Grid Query Less Restrictive ❌ NOT RECOMMENDED
**Remove requirement for photo_metadata/project_images**

```sql
-- OPTION 3 (NOT RECOMMENDED):
SELECT DISTINCT fc.image_path as path
FROM face_crops fc
WHERE fc.project_id = ? AND fc.branch_key = ?
ORDER BY fc.image_path DESC
```

**Pros:**
- ✅ Shows all 14 photos

**Cons:**
- ❌ May show photos that don't exist
- ❌ No metadata (created_date, width, height)
- ❌ Breaks grid rendering (needs width/height)
- ❌ NOT RECOMMENDED

---

## Recommended Fix: Option 1 + Validation

**Step 1:** Run diagnostic Query 4 to identify the 2 missing photos

**Step 2:** Check if photos exist on disk:
```bash
# Check if the 2 missing photos still exist
ls -la "/path/to/missing/photo1.jpg"
ls -la "/path/to/missing/photo2.jpg"
```

**Step 3:** Choose based on file existence:
- **If files exist:** Option 2 (add to metadata/project)
- **If files don't exist:** Option 1 (clean up orphaned face_crops)

**Step 4:** Add preventive check to face detection worker:
- Before adding to face_crops, verify photo exists in photo_metadata
- Or add photo to photo_metadata if it doesn't exist
- Ensures future consistency

---

## Preventive Fix in Face Detection

**Location:** `workers/face_detect_worker.py` or wherever faces are added to face_crops

**Add validation:**
```python
# Before inserting into face_crops:
# Ensure photo exists in photo_metadata
cur.execute("SELECT path FROM photo_metadata WHERE path = ?", (image_path,))
if not cur.fetchone():
    # Photo not in metadata - either skip or add it
    logger.warning(f"Photo {image_path} not in photo_metadata, skipping face detection")
    continue  # Or add to photo_metadata first

# Ensure photo is linked to project
cur.execute("SELECT 1 FROM project_images WHERE project_id = ? AND image_path = ?",
            (project_id, image_path))
if not cur.fetchone():
    # Add to project_images
    cur.execute("INSERT OR IGNORE INTO project_images (project_id, branch_key, image_path) VALUES (?, 'all', ?)",
                (project_id, image_path))

# Now safe to add to face_crops
cur.execute("INSERT INTO face_crops (...) VALUES (...)")
```

---

## Testing Plan

After implementing fix:
1. ✅ Run diagnostic queries - should show 14/14 in all tables
2. ✅ Filter by face_003 - grid should show 14 photos
3. ✅ Count in people card should match grid (14/14)
4. ✅ Test with other face clusters
5. ✅ Run face detection on new photos - verify no orphans created

---

## Next Steps

1. Run diagnostic Query 4 on provided database
2. Identify the 2 missing photos and their paths
3. Check if files exist on disk
4. Implement appropriate fix (Option 1 or 2)
5. Add preventive validation to face detection
6. Re-cluster faces to update counts
7. Verify 14/14 match in grid
