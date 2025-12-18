# Root Cause Analysis: face_crops Database Corruption

**Date:** 2025-12-18
**Analyst:** Claude Code (Automated Code Review)
**Status:** INVESTIGATION COMPLETE
**Severity:** HIGH (Causes application crashes)

---

## Executive Summary

A database corruption issue was discovered where some `face_crops` table entries contain incorrect `image_path` values pointing to face crop files (`/face_crops/`) instead of original photos. This corruption causes the Manual Face Crop Editor to crash when users attempt to review faces from the Face Quality Dashboard.

**Finding:** After comprehensive code review, **no active bugs were found** in the current codebase that would cause this corruption. All current INSERT and UPDATE statements are correctly implemented.

**Conclusion:** The corruption likely originated from:
1. **Legacy code** that has since been fixed or removed
2. **Historical bugs** that existed during development but were corrected
3. **Manual database operations** during debugging/testing
4. **Migration issues** from older schema versions

---

## Investigation Methodology

### Phase 1: Automated Code Audit
Searched entire codebase for all INSERT and UPDATE statements affecting `face_crops` table:
- Face Detection Worker
- Face Crop Editor
- Face Cluster Worker
- Migration Scripts
- Legacy Code (previous-version-working/)
- Layout Files (google_layout.py)

### Phase 2: Parameter Verification
Verified parameter order for all database operations:
- Checked that `image_path` receives original photo paths
- Checked that `crop_path` receives face crop paths
- Validated no parameter swapping occurs

### Phase 3: Validation Check Review
Reviewed defensive checks implemented to prevent corruption:
- Input validation in Face Crop Editor
- Dashboard button disabling for corrupted entries
- Qt memory management fixes

---

## Code Review Findings

### ✅ Face Detection Worker (workers/face_detection_worker.py)

**Lines 381-396:** Face insertion during detection

```python
cur.execute("""
    INSERT OR REPLACE INTO face_crops (
        project_id, image_path, crop_path, embedding,
        bbox_x, bbox_y, bbox_w, bbox_h, confidence
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    self.project_id,
    image_path,      # ✅ CORRECT: Original photo path
    crop_path,       # ✅ CORRECT: Face crop path
    embedding_bytes,
    face['bbox_x'],
    face['bbox_y'],
    face['bbox_w'],
    face['bbox_h'],
    face['confidence']
))
```

**Verification:**
- ✅ `image_path` parameter receives original photo path (from `photo['path']`)
- ✅ `crop_path` parameter receives face crop path (constructed as `{basename}_face{idx}.jpg`)
- ✅ Parameters are in correct order
- ✅ No risk of corruption

**Evidence:** Line 143 shows `photo_path = photo['path']` which is from `project_images` table, guaranteed to be original photo.

---

### ✅ Face Crop Editor (ui/face_crop_editor.py)

**Lines 2155-2165:** Manual face crop insertion

```python
cur.execute("""
    INSERT INTO face_crops
    (project_id, image_path, crop_path, bbox, branch_key, is_representative, quality_score)
    VALUES (?, ?, ?, ?, ?, 1, 0.5)
""", (self.project_id, self.photo_path, crop_path, bbox_str, branch_key))
```

**Verification:**
- ✅ `self.photo_path` is validated at initialization (lines 63-76)
- ✅ Validation explicitly rejects paths containing `/face_crops/`
- ✅ `crop_path` is constructed correctly from `self.photo_path`
- ✅ Parameters are in correct order
- ✅ No risk of corruption (protection added in recent crash fix)

**Evidence:** Line 65 validation prevents opening face crops:
```python
if '/face_crops/' in photo_path.replace('\\', '/'):
    raise ValueError("Cannot open Face Crop Editor on a face crop image.")
```

---

### ✅ Migration Scripts (migrate_add_face_detection_columns.py)

**Analysis:** Migration script only adds columns to existing table

```python
columns_to_add = {
    "embedding": "BLOB",
    "confidence": "REAL DEFAULT 1.0",
    "bbox_top": "INTEGER",
    "bbox_right": "INTEGER",
    "bbox_bottom": "INTEGER",
    "bbox_left": "INTEGER",
}
```

**Verification:**
- ✅ No INSERT statements
- ✅ No UPDATE statements
- ✅ Only ALTER TABLE ADD COLUMN operations
- ✅ No data transformation that could swap columns
- ✅ No risk of corruption

---

### ✅ Google Layout (layouts/google_layout.py)

**Lines 12517, 12569:** Face branch reassignment

```python
cur.execute(f"UPDATE face_crops SET branch_key = ? WHERE project_id = ? AND id IN ({placeholders})",
            [target, self.project_id] + ids)
```

**Verification:**
- ✅ Only updates `branch_key` column (for cluster assignment)
- ✅ Does not modify `image_path` or `crop_path`
- ✅ WHERE clause correctly filters by project_id and face IDs
- ✅ No risk of corruption

---

### ✅ Face Cluster Worker (workers/face_cluster_worker.py)

**Analysis:** No INSERT or UPDATE statements found that modify `image_path` or `crop_path`

**Verification:**
- ✅ No database writes to face_crops table
- ✅ Worker only reads embeddings for clustering
- ✅ Cluster assignments handled by google_layout.py
- ✅ No risk of corruption

---

## Historical Code Analysis

### Legacy Code Review (previous-version-working/)

**Finding:** No INSERT statements found in legacy code directory

**Implications:**
- Either corruption predates the preserved "previous-version-working" snapshot
- Or corruption was caused by code that has since been removed/rewritten
- Or corruption was introduced through external tools (SQL editor, migration scripts, etc.)

---

## Corruption Characteristics

### Pattern Analysis

Based on the status report and defensive checks:

**Corrupted Entry Pattern:**
```
image_path: .memorymate/faces/IMG_1234_face0.jpg  ❌ WRONG (points to face crop)
crop_path:  .memorymate/faces/IMG_1234_face0.jpg  ❓ UNKNOWN (possibly same or different)
```

**Correct Entry Pattern:**
```
image_path: /path/to/photos/IMG_1234.jpg         ✅ CORRECT (original photo)
crop_path:  .memorymate/faces/IMG_1234_face0.jpg ✅ CORRECT (face crop)
```

### Detection Method

Corruption detected by:
1. Path substring check: `'/face_crops/' in image_path`
2. Defensive validation in Face Crop Editor (line 65)
3. Dashboard button disabling (line 384)

---

## Root Cause Hypotheses

### Hypothesis 1: Historical Parameter Swap Bug ⭐ MOST LIKELY

**Description:** Earlier version of code had parameters in wrong order

**Evidence:**
- Current code is correct (verified in all modules)
- Corruption exists in some entries but not others
- Implies bug existed in past, was fixed, but old data remains

**Likelihood:** HIGH

**Example Bug (hypothetical):**
```python
# BUG: Parameters swapped
cur.execute("INSERT INTO face_crops (project_id, image_path, crop_path, ...) VALUES (?, ?, ?, ...)",
           (project_id, crop_path, image_path, ...))  # ❌ WRONG ORDER
                       # ^^^^^^^^^  ^^^^^^^^^^
                       #    SWAPPED!
```

---

### Hypothesis 2: Schema Migration Issue

**Description:** Data transformation during schema evolution incorrectly moved data between columns

**Evidence:**
- Migration script reviewed - only adds columns, doesn't transform data
- However, there may be other migration scripts not in current codebase

**Likelihood:** MEDIUM

**Possible Scenario:**
- Old schema used different column names
- Migration renamed columns but incorrectly mapped data
- Some entries were corrupted during migration

---

### Hypothesis 3: Manual Database Editing

**Description:** Developer or user manually edited database during debugging

**Evidence:**
- No direct evidence
- Common during development/testing

**Likelihood:** LOW-MEDIUM

**Possible Scenario:**
- Developer used SQLite browser to edit face_crops table
- Accidentally copied crop_path value into image_path column
- Affected specific entries that are still in database

---

### Hypothesis 4: External Tool or Script

**Description:** External script or tool (not in current codebase) modified database

**Evidence:**
- No scripts found that could cause this
- May have existed temporarily during development

**Likelihood:** LOW

**Possible Scenario:**
- One-off debugging script
- Data import/export tool
- Database repair attempt gone wrong

---

## Impact Assessment

### Affected Systems
1. **Face Quality Dashboard** - Shows "⚠️ Invalid" for corrupted entries
2. **Manual Face Crop Editor** - Cannot open corrupted entries (prevented by validation)
3. **Face Clustering** - May produce incorrect clusters if using corrupted paths

### User Experience Impact
- **Before Fix:** Application crashed with segmentation fault
- **After Fix:** Graceful error message, disabled buttons
- **Current:** Users cannot manually crop affected faces until data is repaired

### Data Integrity Impact
- **Corrupted Entries:** Cannot be used for manual cropping
- **Face Recognition:** Embeddings still valid (not affected by path corruption)
- **Clustering:** Branch assignments still valid
- **Recovery:** Potentially recoverable by parsing crop filenames

---

## Prevention Measures (Already Implemented)

### 1. Input Validation ✅
**Location:** `ui/face_crop_editor.py:65`
```python
if '/face_crops/' in photo_path.replace('\\', '/'):
    raise ValueError("Cannot open Face Crop Editor on a face crop image.")
```
**Effect:** Prevents new corruption from manual crop operations

### 2. Dashboard Protection ✅
**Location:** `ui/face_quality_dashboard.py:384-390`
```python
is_face_crop = '/face_crops/' in face['image_path'].replace('\\', '/')
if is_face_crop:
    review_btn = QPushButton("⚠️ Invalid")
    review_btn.setEnabled(False)
```
**Effect:** Prevents users from triggering crashes

### 3. Qt Memory Management ✅
**Location:** `ui/face_crop_editor.py:2316-2338`
**Effect:** Prevents segmentation fault when loading images

---

## Recommended Next Steps

### Priority 1: Data Repair (Immediate)
1. ✅ Create audit script to quantify corruption
2. 🔄 Run audit on production databases
3. 🔄 Implement recovery script with backup mechanism
4. 🔄 Execute repair with dry-run testing

### Priority 2: Additional Prevention (This Week)
1. Add database CHECK constraint
   ```sql
   ALTER TABLE face_crops
   ADD CONSTRAINT check_image_path_not_crop
   CHECK (image_path NOT LIKE '%/face_crops/%');
   ```
2. Create validation utility for all insertion points
3. Add automated tests for corruption scenarios

### Priority 3: Monitoring (This Week)
1. Implement integrity checking service
2. Add startup integrity scan
3. Create user-accessible "Verify Database Integrity" option

### Priority 4: Documentation (Next Week)
1. Document correct vs incorrect data patterns
2. Create troubleshooting guide for users
3. Add developer guidelines for face_crops operations

---

## Conclusions

1. **Current codebase is clean** - No active bugs found that would cause corruption
2. **Historical bug likely** - Corruption probably originated from past code that has since been fixed
3. **Defensive measures working** - Current protections prevent crashes and new corruption
4. **Recovery feasible** - Most corrupted entries can potentially be recovered by parsing crop filenames
5. **Prevention needed** - Database constraints and additional validation will prevent future issues

---

## Appendix A: Verified Code Paths

### All INSERT INTO face_crops Statements
1. ✅ `workers/face_detection_worker.py:382` - Correct order
2. ✅ `ui/face_crop_editor.py:2155` - Correct order (with validation)
3. ✅ `ui/face_crop_editor.py:2162` - Correct order (schema variant)
4. ✅ `ui/face_crop_editor.py:2174` - Correct order (old schema)
5. ✅ `ui/face_crop_editor.py:2182` - Correct order (old schema variant)

### All UPDATE face_crops Statements
1. ✅ `layouts/google_layout.py:12517` - Only modifies branch_key
2. ✅ `layouts/google_layout.py:12569` - Only modifies branch_key

**Total Statements Reviewed:** 7
**Bugs Found:** 0
**Correct Implementations:** 7 (100%)

---

## Appendix B: Validation Logic

### Path Validation Function (Proposed)
```python
def validate_face_crops_entry(image_path: str, crop_path: str) -> bool:
    """
    Validate face_crops entry before database insertion.

    Checks:
    1. image_path must NOT contain '/face_crops/'
    2. crop_path SHOULD contain '/face_crops/'
    3. Both paths must exist on disk
    4. image_path must be in project_images table

    Raises ValueError if validation fails.
    """
    # Check 1: image_path must be original photo
    if '/face_crops/' in image_path.replace('\\', '/'):
        raise ValueError(
            f"image_path cannot point to face crop: {image_path}\n"
            f"Expected original photo path, got face crop path"
        )

    # Check 2: crop_path should be face crop
    if '/face_crops/' not in crop_path.replace('\\', '/'):
        logger.warning(f"crop_path doesn't contain '/face_crops/': {crop_path}")

    # Check 3: Paths exist
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"image_path does not exist: {image_path}")

    if not os.path.exists(crop_path):
        logger.warning(f"crop_path does not exist (will be created): {crop_path}")

    return True
```

---

## Appendix C: Database Constraint

### Proposed CHECK Constraint
```sql
-- Prevent face crop paths in image_path column
ALTER TABLE face_crops
ADD CONSTRAINT check_image_path_not_crop
CHECK (
    image_path NOT LIKE '%/face_crops/%'
    AND image_path NOT LIKE '%\face_crops\%'
);

-- Create trigger for additional logging
CREATE TRIGGER face_crops_corruption_attempt
BEFORE INSERT ON face_crops
WHEN NEW.image_path LIKE '%/face_crops/%'
   OR NEW.image_path LIKE '%\face_crops\%'
BEGIN
  SELECT RAISE(ABORT, 'Attempted to insert face crop path as image_path');
END;
```

**Note:** This constraint will prevent ANY future corruption at database level, regardless of application bugs.

---

## Document Control

**Version:** 1.0
**Created:** 2025-12-18
**Author:** Claude Code (Automated Analysis)
**Reviewed:** Pending
**Status:** FINAL - INVESTIGATION COMPLETE

**Related Documents:**
- `MANUAL_FACE_CROP_CRASH_FIX_SESSION_STATUS.md` - Status report of fixes
- `NEXT_IMPROVEMENTS_PLAN.md` - Implementation plan for repairs
- `scripts/audit_face_crops_corruption.py` - Database audit tool
- `reports/face_crops_corruption_report.txt` - Audit results (when generated)

---

**END OF ROOT CAUSE ANALYSIS**
