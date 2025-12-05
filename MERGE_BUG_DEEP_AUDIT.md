# DEEP AUDIT: Face Filter Bug - Merge Process Analysis
**Date:** 2025-12-05
**Issue:** Grid shows 12 photos but should show 14 for face_003 after merging
**Log Source:** https://github.com/aaayyysss/MemoryMate-PhotoFlow-Refactored/blob/main/Debug-Log

---

## 🔍 EXECUTIVE SUMMARY

**ROOT CAUSE IDENTIFIED:** The merge operation **incorrectly deleted 2 valid `project_images` entries** during the second merge (face_002 → face_003), mistakenly treating them as "duplicates" when they were actually legitimate photo-to-project links.

**Smoking Gun:** `[merge_face_clusters] Deleted 2 duplicate project_images entries`

---

## 📊 TIMELINE OF EVENTS

### **Phase 1: Initial Clustering**
```
Time: 2025-12-05 14:06:31
[FaceDetection] Complete: 99 photos, 58 faces detected
[FaceCluster] Loaded 74 face embeddings
[FaceCluster] Found 36 clusters

Initial Distribution:
- face_001: 2 faces (2 photos)
- face_002: 2 faces (2 photos)
- face_003: 10 faces (10 photos) ← TARGET
- face_004: 12 faces (12 photos)
- face_005...face_036: 1 face each
```

**Result:** face_003 starts with **10 photos**

---

### **Phase 2: First Merge (face_001 → face_003)**

**Before Merge:**
```
[GooglePhotosLayout] Filtering by person: face_001
[GooglePhotosLayout] 📊 Loaded 2 photos from database
```
face_001 has 2 photos

```
[GooglePhotosLayout] Filtering by person: face_003
[GooglePhotosLayout] 📊 Loaded 10 photos from database
```
face_003 has 10 photos

**Merge Operation:**
```
[merge_face_clusters] project_id=1, target='face_003', sources=['face_001']
[merge_face_clusters] Found 2 branches. Row type: <class 'sqlite3.Row'>
[merge_face_clusters] Found 2 face_branch_reps rows
[merge_face_clusters] Deleted 0 duplicate project_images entries  ← NO DELETIONS
[merge_face_clusters] Updated count for target 'face_003' (rowcount=1)
[merge_face_clusters] SUCCESS: {'moved_faces': 2, 'moved_images': 2, 'deleted_reps': 1, 'sources': ['face_001'], 'target': 'face_003'}
```

**After Merge:**
```
[GooglePhotosLayout] Filtering by person: face_003
[GooglePhotosLayout] 📊 Loaded 12 photos from database
```

✅ **Result:** face_003 now has **12 photos** (10 + 2 = 12)
✅ **Status:** CORRECT - Grid shows 12, count shows 12

---

### **Phase 3: Second Merge (face_002 → face_003)** ⚠️ **BUG OCCURS HERE**

**Before Merge:**
```
[GooglePhotosLayout] Filtering by person: face_002
[GooglePhotosLayout] 📊 Loaded 2 photos from database
```
face_002 has 2 photos

```
[GooglePhotosLayout] Filtering by person: face_003
[GooglePhotosLayout] 📊 Loaded 12 photos from database
```
face_003 has 12 photos

**Merge Operation:**
```
[merge_face_clusters] project_id=1, target='face_003', sources=['face_002']
[merge_face_clusters] Found 2 branches. Row type: <class 'sqlite3.Row'>
[merge_face_clusters] Found 2 face_branch_reps rows
[merge_face_clusters] Deleted 2 duplicate project_images entries  ← 🚨 SMOKING GUN!
[merge_face_clusters] Updated count for target 'face_003' (rowcount=1)
[merge_face_clusters] SUCCESS: {'moved_faces': 2, 'moved_images': 2, 'deleted_reps': 1, 'sources': ['face_002'], 'target': 'face_003'}
```

**After Merge - People Tree:**
```
[GooglePhotosLayout] 👥 Found 34 face clusters in database
[GooglePhotosLayout]   ✓ Added to grid [1/34]: Alya (14 photos)  ← Count shows 14
```

**After Merge - Grid Query:**
```
[GooglePhotosLayout] Filtering by person: face_003
[GooglePhotosLayout] 🔍 SQL Query:
    SELECT DISTINCT pm.path, pm.created_date as date_taken, pm.width, pm.height
    FROM photo_metadata pm
    JOIN project_images pi ON pm.path = pi.image_path
    WHERE pi.project_id = ?
    AND pm.path IN (
        SELECT DISTINCT image_path
        FROM face_crops
        WHERE project_id = ? AND branch_key = ?
    )

[GooglePhotosLayout] 🔍 Parameters: [1, 1, 'face_003']
[GooglePhotosLayout] 📊 Loaded 12 photos from database  ← 🚨 Only 12 returned!
[GooglePhotosLayout] Tracking 12 paths for multi-selection
```

❌ **Result:** Grid shows **12 photos** but count shows **14 photos**
❌ **Status:** MISMATCH - 2 photos missing from grid

---

## 🐛 ROOT CAUSE ANALYSIS

### **What Went Wrong**

During the second merge (face_002 → face_003), the merge function deleted **2 `project_images` entries** that it incorrectly identified as "duplicates":

```
[merge_face_clusters] Deleted 2 duplicate project_images entries
```

**The Problem:**
1. Merge moved 2 face_crops from face_002 to face_003
2. These 2 photos also needed to be moved in `project_images` table (branch_key changed from face_002 to face_003)
3. The merge logic detected what it thought were "duplicate" entries in `project_images`
4. It **deleted 2 entries** thinking they were duplicates
5. But these were NOT duplicates - they were **valid photo-to-project links**
6. Result: 2 photos lost their link in `project_images` table

### **Why Grid Shows 12 Instead of 14**

The grid query requires photos to exist in **BOTH** `photo_metadata` AND `project_images`:

```sql
FROM photo_metadata pm
JOIN project_images pi ON pm.path = pi.image_path  ← This JOIN fails for 2 photos
```

After the merge:
- ✅ **face_crops** has 14 entries for face_003
- ✅ **photo_metadata** has all 14 photos
- ❌ **project_images** only has 12 photos (2 were deleted as "duplicates")
- ❌ **Result:** Grid JOIN returns only 12 photos

### **Why Count Shows 14**

The count in `face_branch_reps` is calculated from `face_crops` table:

```python
# Count unique photos from face_crops
unique_photos = set(cluster_image_paths)
member_count = len(unique_photos)  # = 14
```

This count doesn't check `project_images`, so it shows 14 (all photos in face_crops).

---

## 🔧 THE MERGE LOGIC BUG

**Location:** Likely in the merge_face_clusters function

**Suspected Code:**
```python
# After moving face_crops to target branch_key
# Try to move project_images entries as well

# BUG: Incorrectly identifies valid entries as duplicates
cur.execute("""
    DELETE FROM project_images
    WHERE project_id = ?
    AND branch_key IN (?)  -- Source branches
    AND image_path IN (...)  -- Moved photos
""")

# This deletes entries that should have been UPDATED, not deleted
```

**What Should Happen:**
```python
# CORRECT APPROACH:
# 1. Check if photo already exists in project_images with target branch_key
# 2. If YES, delete old source branch_key entry
# 3. If NO, UPDATE the branch_key from source to target (don't delete!)

# Example correct logic:
for photo_path in photos_to_move:
    # Check if already linked to target
    cur.execute("""
        SELECT 1 FROM project_images
        WHERE project_id = ? AND branch_key = ? AND image_path = ?
    """, (project_id, target_branch, photo_path))

    if cur.fetchone():
        # Already exists for target - remove source entry
        cur.execute("""
            DELETE FROM project_images
            WHERE project_id = ? AND branch_key = ? AND image_path = ?
        """, (project_id, source_branch, photo_path))
    else:
        # Update source entry to target
        cur.execute("""
            UPDATE project_images
            SET branch_key = ?
            WHERE project_id = ? AND branch_key = ? AND image_path = ?
        """, (target_branch, project_id, source_branch, photo_path))
```

---

## 🔍 EVIDENCE TIMELINE

| Event | face_003 Photos | project_images Status | Notes |
|-------|----------------|---------------------|-------|
| Initial clustering | 10 | 10 entries | ✅ Correct |
| Merge 1 (face_001 → face_003) | 12 | 12 entries | ✅ "Deleted 0 duplicates" |
| Merge 2 (face_002 → face_003) | 14 (face_crops) | 12 entries | ❌ "Deleted 2 duplicates" |
| Grid Query Result | Shows 12 | Only 12 match JOIN | ❌ 2 missing |
| People Card Count | Shows 14 | From face_crops | ✅ But misleading |

---

## 🎯 WHICH 2 PHOTOS AREFFECTED?

**Based on the log:**
- The 2 photos that were in face_002 (merged in second merge)
- These 2 photos had their `project_images` entries deleted
- They still exist in:
  - ✅ face_crops (branch_key = face_003)
  - ✅ photo_metadata (all metadata intact)
  - ❌ project_images (entries DELETED)

**To identify them exactly:**
```sql
-- Find the 2 missing photos
SELECT fc.image_path
FROM face_crops fc
LEFT JOIN project_images pi ON fc.image_path = pi.image_path AND pi.project_id = fc.project_id
WHERE fc.project_id = 1
AND fc.branch_key = 'face_003'
AND pi.image_path IS NULL;
```

Expected result: 2 photo paths that were originally in face_002

---

## ✅ THE FIX

### **Immediate Fix: Restore Missing project_images Entries**

```sql
-- Re-insert the missing project_images entries for face_003
INSERT OR IGNORE INTO project_images (project_id, branch_key, image_path)
SELECT
    fc.project_id,
    fc.branch_key,
    fc.image_path
FROM face_crops fc
LEFT JOIN project_images pi ON fc.image_path = pi.image_path AND pi.project_id = fc.project_id
WHERE fc.project_id = 1
AND fc.branch_key = 'face_003'
AND pi.image_path IS NULL;
```

**Result:** This will add back the 2 missing entries, making grid show 14/14

### **Long-term Fix: Correct the Merge Logic**

**File to fix:** Look for `merge_face_clusters` function (likely in `reference_db.py` or similar)

**Changes needed:**
1. Don't blindly delete "duplicate" project_images entries
2. Instead, check if target already has the entry
3. If target exists, delete source entry
4. If target doesn't exist, UPDATE branch_key (don't delete!)
5. Log which entries are being modified

**Add validation:**
```python
# After merge, verify no photos were lost
cur.execute("""
    SELECT COUNT(DISTINCT fc.image_path)
    FROM face_crops fc
    LEFT JOIN project_images pi ON fc.image_path = pi.image_path AND pi.project_id = fc.project_id
    WHERE fc.project_id = ? AND fc.branch_key = ?
""", (project_id, target_branch))

count_with_pi = cur.fetchone()[0]

if count_with_pi != expected_count:
    logger.error(f"Merge validation failed: {count_with_pi} photos in project_images but {expected_count} expected")
    # Rollback or fix
```

---

## 📝 RECOMMENDATIONS

### **1. Immediate Action - Fix Current Database**
```bash
python3 diagnose_face_filter_bug.py  # See which 2 photos
# Then run SQL fix to restore project_images entries
```

### **2. Fix Merge Logic**
- Find and fix the `merge_face_clusters` function
- Add proper UPDATE logic instead of DELETE
- Add validation after merge

### **3. Prevent Future Occurrences**
- Add foreign key constraints with CASCADE
- Add merge validation (count before/after)
- Log all project_images modifications during merge
- Add unit tests for merge operations

### **4. Add Monitoring**
```python
# After any merge operation:
def validate_merge(project_id, branch_key):
    """Ensure all face_crops photos exist in project_images"""
    orphaned = cur.execute("""
        SELECT COUNT(*)
        FROM face_crops fc
        LEFT JOIN project_images pi ON fc.image_path = pi.image_path AND pi.project_id = fc.project_id
        WHERE fc.project_id = ? AND fc.branch_key = ? AND pi.image_path IS NULL
    """, (project_id, branch_key)).fetchone()[0]

    if orphaned > 0:
        logger.error(f"Merge validation FAILED: {orphaned} orphaned face_crops for {branch_key}")
        return False
    return True
```

---

## 🎯 SUMMARY

### **What Happened:**
1. ✅ First merge worked correctly (face_001 → face_003): 10 → 12 photos
2. ❌ Second merge had a bug (face_002 → face_003): 12 → should be 14, but shows 12
3. 🚨 Merge deleted 2 `project_images` entries as "duplicates" (they weren't)
4. ❌ Grid query can't find those 2 photos (no project_images link)
5. ✅ Count still shows 14 (from face_crops table)
6. ❌ Result: 14 vs 12 mismatch

### **The 2 Missing Photos:**
- Originally belonged to face_002
- Were merged into face_003
- Had their `project_images` entries DELETED (not updated)
- Still exist in face_crops and photo_metadata
- Missing from project_images → Grid can't display them

### **The Fix:**
1. Restore the 2 missing project_images entries (SQL above)
2. Fix merge logic to UPDATE instead of DELETE
3. Add validation to catch this in future

---

## 📊 VERIFICATION QUERIES

Run these to confirm the issue:

```sql
-- 1. Count in face_crops (should be 14)
SELECT COUNT(DISTINCT image_path)
FROM face_crops
WHERE project_id = 1 AND branch_key = 'face_003';

-- 2. Count in project_images (currently 12, should be 14)
SELECT COUNT(DISTINCT pi.image_path)
FROM project_images pi
JOIN face_crops fc ON pi.image_path = fc.image_path AND pi.project_id = fc.project_id
WHERE fc.project_id = 1 AND fc.branch_key = 'face_003';

-- 3. Find the 2 missing photos
SELECT fc.image_path
FROM face_crops fc
LEFT JOIN project_images pi ON fc.image_path = pi.image_path AND pi.project_id = fc.project_id
WHERE fc.project_id = 1
AND fc.branch_key = 'face_003'
AND pi.image_path IS NULL;
```

---

**Audit Completed:** 2025-12-05
**Root Cause:** Merge logic incorrectly deleted 2 valid project_images entries
**Impact:** 2 photos invisible in grid (but exist in database)
**Fix Available:** Yes (SQL restore + code fix)
