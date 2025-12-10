# Face Filter Bug Analysis
**Date:** 2025-12-05
**Issue:** People card shows 14 photos but grid only displays 12 (2 missing)
**Face Cluster:** face_003

---

## Bug Summary

When filtering by a person (face_003):
- **People Card Count:** 14 photos
- **Grid Display:** 12 photos
- **Missing:** 2 photos

---

## Root Cause Analysis

### The Count Query (People Card)
**Location:** `layouts/google_layout.py:9551-9554`

```sql
SELECT branch_key, label, count, rep_path, rep_thumb_png
FROM face_branch_reps
WHERE project_id = ?
ORDER BY count DESC
```

**What it does:**
- Reads `count` column directly from `face_branch_reps` table
- This count is **pre-calculated** during face detection/clustering
- **Assumption:** Count represents ALL entries in `face_crops` table for this branch_key

### The Fetch Query (Grid Display)
**Location:** `layouts/google_layout.py:9150-9188`

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

**What it does:**
- Requires photos to exist in **THREE** tables:
  1. `face_crops` (WHERE branch_key = face_003)
  2. `photo_metadata` (JOIN pm.path = face_crops.image_path)
  3. `project_images` (JOIN pm.path = pi.image_path)
- Only returns photos that pass ALL these conditions

---

## The Discrepancy

### What's Happening:
1. **face_branch_reps.count = 14** (counts ALL rows in face_crops)
2. **Actual query returns 12** (only photos in all 3 tables)
3. **Missing 2 photos** exist in face_crops but NOT in photo_metadata or project_images

### Why This Happens:
- Face detection adds entries to `face_crops` table
- But these photos may not have been scanned into `photo_metadata` yet
- Or they may have been removed from `project_images` but still in `face_crops`
- The `count` in `face_branch_reps` is stale/out of sync

---

## Verification Queries

To confirm the bug, run these queries on the database:

### Query 1: Count from face_crops (should be 14)
```sql
SELECT COUNT(DISTINCT image_path)
FROM face_crops
WHERE project_id = 1 AND branch_key = 'face_003';
```

### Query 2: Count with photo_metadata join (should be 12)
```sql
SELECT COUNT(DISTINCT pm.path)
FROM photo_metadata pm
WHERE pm.path IN (
    SELECT DISTINCT image_path
    FROM face_crops
    WHERE project_id = 1 AND branch_key = 'face_003'
);
```

### Query 3: Count with full join (should be 12 - matches grid)
```sql
SELECT COUNT(DISTINCT pm.path)
FROM photo_metadata pm
JOIN project_images pi ON pm.path = pi.image_path
WHERE pi.project_id = 1
AND pm.path IN (
    SELECT DISTINCT image_path
    FROM face_crops
    WHERE project_id = 1 AND branch_key = 'face_003'
);
```

### Query 4: Find the 2 missing photos
```sql
SELECT fc.image_path,
       CASE WHEN pm.path IS NULL THEN 'NOT in photo_metadata' ELSE 'in photo_metadata' END as pm_status,
       CASE WHEN pi.image_path IS NULL THEN 'NOT in project_images' ELSE 'in project_images' END as pi_status
FROM face_crops fc
LEFT JOIN photo_metadata pm ON fc.image_path = pm.path
LEFT JOIN project_images pi ON fc.image_path = pi.image_path AND pi.project_id = fc.project_id
WHERE fc.project_id = 1 AND fc.branch_key = 'face_003'
ORDER BY fc.image_path;
```

---

## Solution Options

### Option 1: Fix the Count Calculation ⭐ RECOMMENDED
**Change:** Update `face_branch_reps.count` to match the actual query logic

**Implementation:**
- When populating/updating `face_branch_reps`, use a count that joins with photo_metadata and project_images
- This ensures the count always matches what will actually be displayed

**Query to use:**
```sql
SELECT COUNT(DISTINCT pm.path)
FROM photo_metadata pm
JOIN project_images pi ON pm.path = pi.image_path
WHERE pi.project_id = ?
AND pm.path IN (
    SELECT DISTINCT image_path
    FROM face_crops
    WHERE project_id = ? AND branch_key = ?
)
```

**Pros:**
- ✅ Count always accurate
- ✅ No data shown that doesn't exist
- ✅ Consistent with grid display logic

**Cons:**
- ⚠️ Need to find where face_branch_reps is populated/updated
- ⚠️ May need to recalculate all counts

### Option 2: Fix the Grid Query
**Change:** Remove requirement for photo_metadata/project_images join

**Pros:**
- ✅ Shows all photos from face_crops
- ✅ Count matches display

**Cons:**
- ❌ May show photos that don't exist in project
- ❌ May show photos with no metadata
- ❌ Violates data integrity constraints
- ❌ NOT RECOMMENDED

### Option 3: Fix the Data
**Change:** Ensure all photos in face_crops exist in photo_metadata and project_images

**Implementation:**
- Remove orphaned face_crops entries (photos not in photo_metadata)
- Or add missing photos to photo_metadata/project_images

**Pros:**
- ✅ Fixes data integrity
- ✅ Both queries will match

**Cons:**
- ⚠️ Requires data migration
- ⚠️ May delete valid face detections if photos were intentionally removed

---

## Recommended Fix: Option 1

Update the count calculation when building face_branch_reps to use the same logic as the grid query.

**Location to fix:** Find where `face_branch_reps` table is populated/updated
**Change:** Replace simple `COUNT(*)` from `face_crops` with joined count

---

## Testing Plan

After implementing fix:
1. ✅ Verify count in people card matches grid
2. ✅ Test with multiple face clusters
3. ✅ Test after adding new photos
4. ✅ Test after removing photos
5. ✅ Test after running face detection

---

## Next Steps

1. Find where `face_branch_reps` is populated
2. Update count calculation to match grid query
3. Recalculate all existing counts
4. Test with face_003 (should show 12/12)
5. Verify no regressions with other faces
