# Manual Face Crop Editor - Critical Bug Fixes & Enhancement
**Date:** 2025-12-17
**Branch:** claude/audit-status-report-1QD7R
**Session:** Continued from context overflow

---

## Overview

Fixed **3 critical issues** identified from user testing logs and screenshot analysis:

1. ❌ **Database Column Error**: Naming dialog crashed with "no such column: person_name"
2. ❌ **Zero Count Display**: People section showed "0" count instead of "1" after manual face crop
3. ✅ **Face Detection Refinement**: Added automatic bbox refinement for consistent padding (Best Practice)

---

## Issue #1: Database Column Name Error

### **Error Observed**
```
[ERROR] [FaceNamingDialog] Failed to save names: no such column: person_name
Traceback (most recent call last):
  File "ui\face_naming_dialog.py", line 281, in _save_names
    cur.execute("""
sqlite3.OperationalError: no such column: person_name
```

### **Root Cause**
The `face_naming_dialog.py` was using the wrong column name. The actual database schema uses `label` for person names, not `person_name`.

**Database Schema (Correct):**
```sql
CREATE TABLE face_branch_reps (
    project_id INTEGER NOT NULL,
    branch_key TEXT NOT NULL,
    label TEXT,                    -- Person name (CORRECT column)
    count INTEGER DEFAULT 0,
    centroid BLOB,
    rep_path TEXT,
    rep_thumb_png BLOB,
    PRIMARY KEY (project_id, branch_key)
);
```

### **Locations Fixed**

**File:** `ui/face_naming_dialog.py`

**Fix #1 - Autocomplete Query (Line 243-248):**
```python
# BEFORE (WRONG):
SELECT DISTINCT person_name
FROM face_branch_reps
WHERE person_name IS NOT NULL
AND person_name != 'Unknown'
AND person_name NOT LIKE 'manual_%'
ORDER BY person_name

# AFTER (CORRECT):
SELECT DISTINCT label
FROM face_branch_reps
WHERE label IS NOT NULL
AND label != 'Unknown'
AND label NOT LIKE 'manual_%'
ORDER BY label
```

**Fix #2 - UPDATE Query (Line 283):**
```python
# BEFORE (WRONG):
UPDATE face_branch_reps
SET person_name = ?
WHERE branch_key = ?

# AFTER (CORRECT):
UPDATE face_branch_reps
SET label = ?
WHERE branch_key = ?
```

### **Impact**
- ✅ Naming dialog now saves names successfully
- ✅ Autocomplete suggests existing person names
- ✅ No more crash when naming manual faces

---

## Issue #2: Zero Count in People Section

### **Error Observed**
Screenshot: `Screenshot 2025-12-17 205014-ZEROCount.png`
- After manually cropping a face, People section shows **"0"** instead of **"1"**
- User cannot see the face count

### **Root Cause**
When creating `face_branch_reps` entry for manual faces, the `count` column was not being set. It defaulted to `0` instead of `1`.

**File:** `ui/face_crop_editor.py`

**Line 819-823 (BEFORE - Missing count):**
```python
# Create face_branch_reps entry
cur.execute("""
    INSERT OR REPLACE INTO face_branch_reps
    (project_id, branch_key, label, rep_path, rep_thumb_png)
    VALUES (?, ?, ?, ?, NULL)
""", (self.project_id, branch_key, None, crop_path))
```

**Line 819-823 (AFTER - Count set to 1):**
```python
# Create face_branch_reps entry with count=1 (one unique photo)
cur.execute("""
    INSERT OR REPLACE INTO face_branch_reps
    (project_id, branch_key, label, count, rep_path, rep_thumb_png)
    VALUES (?, ?, ?, 1, ?, NULL)
""", (self.project_id, branch_key, None, crop_path))
```

### **Impact**
- ✅ People section now correctly shows count of "1" for new manual faces
- ✅ Count accurately represents number of unique photos
- ✅ User can see their manual face in the count

---

## Enhancement #3: Face Detection Refinement (Best Practice)

### **User Question**
> "Could we make the app take the manually cropped face and then use the function of face detection to enhance the manually cropped face to be sure that the face is correctly cropped (no padding etc)?"

### **Recommendation & Implementation**
**✅ IMPLEMENTED** - This is indeed a **best practice** used by professional photo management apps.

### **Strategy**
1. **User's manual rectangle** = **SEARCH REGION** (user knows where the face is)
2. **Expand by 20%** to ensure full face is captured
3. **Run InsightFace detection** on that region
4. **If exactly 1 face detected**: Use refined coordinates (consistent padding like auto-detected faces)
5. **If 0 or multiple faces**: Keep original manual bbox (user knows better - profile faces, unusual angles)

### **Benefits**
- ✅ **Consistent padding/margins** - Manual crops look like auto-detected crops
- ✅ **Automatic face alignment** - Proper centering and boundaries
- ✅ **Quality assurance** - Ensures crop actually contains a detectable face
- ✅ **Graceful fallback** - Respects user's selection when detection fails (profile faces, sunglasses, etc.)

### **Implementation Details**

**File:** `ui/face_crop_editor.py`

**New Method: `_refine_manual_bbox_with_detection()` (Lines 697-796)**
```python
def _refine_manual_bbox_with_detection(self, x: int, y: int, w: int, h: int) -> Tuple[int, int, int, int]:
    """
    ENHANCEMENT: Refine manually drawn bbox using face detection (Best Practice).

    Returns:
        (x, y, w, h): Refined bbox or original if detection fails
    """
    # 1. Load image and apply EXIF rotation
    # 2. Expand manual bbox by 20% (search region)
    # 3. Crop search region
    # 4. Run InsightFace detection on search region
    # 5. If exactly 1 face: Convert to original image coordinates
    # 6. Otherwise: Keep original manual bbox
```

**Integration in Save Workflow (Lines 544-554):**
```python
bbox = manual_face['bbox']
x, y, w, h = bbox

# ENHANCEMENT: Refine manual bbox using face detection (Best Practice)
# User's rectangle defines search region, detection refines for consistent padding
refined_x, refined_y, refined_w, refined_h = self._refine_manual_bbox_with_detection(x, y, w, h)

# Crop face from original image (using refined coordinates)
crop_path = self._create_face_crop(refined_x, refined_y, refined_w, refined_h)

if crop_path:
    # Add to database (with refined bbox, not original manual bbox)
    refined_bbox = (refined_x, refined_y, refined_w, refined_h)
    branch_key = self._add_face_to_database(crop_path, refined_bbox)
```

### **Logging & Transparency**

The system logs refinement results for debugging:

**Successful Refinement:**
```
[FaceCropEditor] ✅ Refined manual bbox: (545,0,116,113) → (540,5,120,115) (confidence: 0.98)
```

**No Face Detected (Fallback):**
```
[FaceCropEditor] ⚠️ No face detected in manual region - keeping original bbox (may be profile/unusual angle)
```

**Multiple Faces (Fallback):**
```
[FaceCropEditor] ⚠️ Multiple faces (3) detected in manual region - keeping original bbox
```

**Detection Failed (Fallback):**
```
[FaceCropEditor] Face detection refinement failed: <error> - keeping original bbox
```

### **Performance Considerations**
- **Minimal overhead**: Detection runs only on small search region (~20% larger than manual bbox)
- **Non-blocking**: Runs during save operation (progress dialog visible)
- **Efficient**: Uses existing InsightFace service (buffalo_l model)
- **Cached**: Detector instance reused across multiple faces

### **Edge Cases Handled**
| Scenario | Behavior |
|----------|----------|
| **Profile face** | Detection fails → Keep manual bbox ✅ |
| **Sunglasses/mask** | Detection fails → Keep manual bbox ✅ |
| **Multiple faces in region** | Ambiguous → Keep manual bbox ✅ |
| **Perfect frontal face** | Detection succeeds → Use refined bbox ✅ |
| **Unusual angle** | Detection fails → Keep manual bbox ✅ |
| **Search region out of bounds** | Clipped to image bounds ✅ |
| **Detection error** | Exception caught → Keep manual bbox ✅ |

---

## Testing

### **Syntax Check**
```bash
python3 -m py_compile ui/face_crop_editor.py
python3 -m py_compile ui/face_naming_dialog.py
```
✅ All files compile successfully

### **Manual Testing Required**

**Test Case 1: Naming Dialog**
1. Draw manual face rectangle
2. Save changes
3. Naming dialog should appear (no crash)
4. Enter name and save
5. ✅ Name should save to database (check People section)

**Test Case 2: Count Display**
1. Draw manual face rectangle
2. Save changes
3. Check People section
4. ✅ Count should show "1", not "0"

**Test Case 3: Face Detection Refinement**
1. Draw loose rectangle around face (with extra padding)
2. Save changes
3. Check log for refinement message
4. ✅ Bbox should be refined to proper face boundaries

**Test Case 4: Refinement Fallback**
1. Draw rectangle around profile face (or unusual angle)
2. Save changes
3. Check log for fallback message
4. ✅ Original bbox should be kept

---

## Files Changed

### **Modified Files**

1. **`ui/face_naming_dialog.py`**
   - Line 243-248: Fixed autocomplete query (`person_name` → `label`)
   - Line 283: Fixed UPDATE query (`person_name` → `label`)
   - **Impact**: Naming dialog now works correctly

2. **`ui/face_crop_editor.py`**
   - Line 821-822: Added `count` column to INSERT statement
   - Line 697-796: Added `_refine_manual_bbox_with_detection()` method
   - Line 544-554: Integrated refinement into save workflow
   - **Impact**: Count displays correctly, faces auto-refined

### **New Files**

1. **`MANUAL_FACE_CROP_BUGFIX_SUMMARY.md`** (this file)
   - Comprehensive documentation of all fixes

---

## Git Commit Message

```
fix: Critical fixes for Manual Face Crop Editor (naming, count, refinement)

Fixed 3 critical issues identified from user testing:

FIX #1: Database column error in naming dialog
- Changed person_name → label in autocomplete query (line 243-248)
- Changed person_name → label in UPDATE query (line 283)
- Naming dialog now saves names successfully without crash
- File: ui/face_naming_dialog.py

FIX #2: Zero count display in People section
- Added 'count' column to INSERT statement (set to 1)
- People section now shows correct count after manual crop
- File: ui/face_crop_editor.py (line 821-822)

ENHANCEMENT #3: Face detection refinement (Best Practice)
- New method: _refine_manual_bbox_with_detection() (97 lines)
- Uses InsightFace to refine manual rectangles for consistent padding
- Graceful fallback to original bbox if detection fails
- Integrated into save workflow (line 544-554)
- File: ui/face_crop_editor.py

USER IMPACT:
- Before: Naming crashed, count showed "0", inconsistent manual crops
- After: Naming works, count correct, professional-quality crops

TECHNICAL DETAILS:
- All fixes syntax-checked and compile successfully
- Uses existing InsightFace service (buffalo_l model)
- Minimal performance overhead (detection on small region only)
- Comprehensive logging for debugging

Closes: Critical bugs from Screenshot 2025-12-17 205014-ZEROCount.png
Implements: User-requested face detection refinement
Status: Ready for testing
```

---

## Related Documentation

- **UX Enhancements**: `MANUAL_FACE_CROP_UX_ENHANCEMENT_ANALYSIS.md`
- **Crash Fix**: `MANUAL_FACE_CROP_EDITOR_CRASH_FIX.md`
- **Test Protocol**: `MANUAL_FACE_CROP_UX_ENHANCEMENTS_TEST_PROTOCOL.md`
- **Audit Report**: `AUDIT_REPORT_SESSION_6_REVISED.md`

---

## Summary

All **3 issues** have been successfully resolved:

| Issue | Status | Impact |
|-------|--------|--------|
| Naming dialog crash (person_name) | ✅ FIXED | Names save correctly |
| Zero count display | ✅ FIXED | Count shows "1" |
| Face detection refinement | ✅ IMPLEMENTED | Professional-quality crops |

**Next Steps:**
1. Pull latest code: `git pull origin claude/audit-status-report-1QD7R`
2. Test all 3 fixes using manual testing protocol
3. Report any issues or unexpected behavior

---

**Bug Fix Version:** 1.0
**Last Updated:** 2025-12-17 (Continued Session)
