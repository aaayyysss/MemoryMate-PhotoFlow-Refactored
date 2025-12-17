# Coordinate Bug and Database Schema Analysis
## Date: 2025-12-17

---

## Problem 1: Manual Face Rectangle Drawn in Wrong Position

### User Report
> "The manually drawn frame coordinates need auditing as it draws the rectangle in a wrong position as originally manually drawn"

### Root Cause Analysis

**The Bug:**
When the user draws a rectangle on the screen, the coordinates are captured in **widget coordinates** (which include centering offsets), but when converting to **image coordinates**, the code doesn't account for these offsets.

**Visual Explanation:**

```
┌─────────────────────────────────────────────────┐
│ Widget (QWidget)                                 │
│                                                  │
│    x_offset →  ┌───────────────┐  ← y_offset    │
│                │               │                 │
│                │  Photo (scaled│                 │
│                │  and centered)│                 │
│                │               │                 │
│                └───────────────┘                 │
│                                                  │
└─────────────────────────────────────────────────┘

User draws here (widget coords: includes offsets)
        ↓
   [150, 200, 100, 100]

Code converts: rect.x() * scale
        ↓
   [150 * 2.5, 200 * 2.5, 100 * 2.5, 100 * 2.5]
        ↓
   [375, 500, 250, 250]  ← WRONG! Didn't subtract offsets first

Should be: (rect.x() - x_offset) * scale
        ↓
   [(150 - 50) * 2.5, (200 - 30) * 2.5, ...]
        ↓
   [250, 425, 250, 250]  ← CORRECT!
```

**Code Location:**
`ui/face_crop_editor.py`, lines 720-743, `mouseReleaseEvent()` method

**Current Code (INCORRECT):**
```python
# Line 724-729
widget_rect = self.rect()
pixmap_rect = self.pixmap.rect()

scale_x = pixmap_rect.width() / widget_rect.width()
scale_y = pixmap_rect.height() / widget_rect.height()
scale = max(scale_x, scale_y)

# Line 732-735 - BUG: Doesn't account for x_offset/y_offset
x = int(rect.x() * scale)
y = int(rect.y() * scale)
w = int(rect.width() * scale)
h = int(rect.height() * scale)
```

**Why It's Wrong:**
1. Photo is **scaled to fit** the widget: `scaled_pixmap = self.pixmap.scaled(self.size(), Qt.KeepAspectRatio)`
2. Photo is **centered** in the widget:
   ```python
   x_offset = (self.width() - scaled_pixmap.width()) // 2
   y_offset = (self.height() - scaled_pixmap.height()) // 2
   ```
3. When painting rectangles, the code correctly adds these offsets:
   ```python
   rect = QRect(
       int(x * scale) + x_offset,  # ← Offset added here
       int(y * scale) + y_offset,  # ← Offset added here
       int(w * scale),
       int(h * scale)
   )
   ```
4. But when capturing mouse coordinates, the code **forgets to subtract the offsets before scaling**!

**The Fix:**
```python
# Calculate scaled pixmap and offsets (same as paintEvent)
scaled_pixmap = self.pixmap.scaled(
    self.size(),
    Qt.KeepAspectRatio,
    Qt.SmoothTransformation
)

x_offset = (self.width() - scaled_pixmap.width()) // 2
y_offset = (self.height() - scaled_pixmap.height()) // 2

# Calculate scale factor (image pixels per display pixel)
scale = self.pixmap.width() / scaled_pixmap.width()

# Convert widget coords to image coords
# CRITICAL: Subtract offsets BEFORE scaling!
x = int((rect.x() - x_offset) * scale)
y = int((rect.y() - y_offset) * scale)
w = int(rect.width() * scale)
h = int(rect.height() * scale)

# Clamp to image bounds
x = max(0, min(x, self.pixmap.width() - w))
y = max(0, min(y, self.pixmap.height() - h))
```

**Testing:**
1. Open Face Crop Editor on a portrait photo (will have x_offset)
2. Draw a rectangle around a face
3. **Before fix:** Rectangle appears shifted to the right/down
4. **After fix:** Rectangle appears exactly where you drew it

---

## Problem 2: Database Schema Confusion (Old vs New)

### User Question
> "Why there is two databases schemas Old and New?? Audit and conduct an analysation for this topic and what is the recommendation?"

### Investigation Results

**Conclusion: There is NO "new schema" - only ONE correct schema exists!**

I made a false assumption during bug fixing that led to unnecessary complexity.

### Schema History

**1. Official Schema (repository/schema.py, v5.0.0):**
```sql
CREATE TABLE IF NOT EXISTS face_crops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    branch_key TEXT,
    image_path TEXT NOT NULL,
    crop_path TEXT NOT NULL,
    embedding BLOB,
    bbox_x INTEGER,      -- ← Separate columns (CORRECT)
    bbox_y INTEGER,      -- ← Separate columns (CORRECT)
    bbox_w INTEGER,      -- ← Separate columns (CORRECT)
    bbox_h INTEGER,      -- ← Separate columns (CORRECT)
    confidence REAL,
    is_representative INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, image_path, bbox_x, bbox_y, bbox_w, bbox_h)
);
```

**2. My Code's Assumption (WRONG!):**
I incorrectly assumed there was a "new schema" with a single `bbox TEXT` column containing comma-separated values like `"x,y,w,h"`.

**Truth:**
- ✅ **Official schema:** Uses `bbox_x`, `bbox_y`, `bbox_w`, `bbox_h` INTEGER columns
- ❌ **"New schema" with bbox TEXT:** **DOES NOT EXIST** in official schema!
- ❌ quality_score column: **ALSO DOES NOT EXIST** in official schema!

### Why This Confusion Happened

**Timeline:**
1. **User reported error:** `no such column: fc.bbox`
2. **I assumed:** User has "old schema" without bbox column
3. **I added code:** To check for both "bbox TEXT" (new) and "bbox_x/y/w/h" (old)
4. **Reality:** User has the CORRECT official schema with bbox_x/y/w/h
5. **My code was wrong:** It was trying to use bbox TEXT which doesn't exist!

**Git History:**
```bash
$ git log --oneline -S "bbox TEXT"
06fa472 Fix: Add database schema compatibility for saving manual face crops
9c22629 Critical Fix: Support both old and new bbox schema in Face Crop Editor
```

These commits (by me) added the wrong assumption about "bbox TEXT".

### Database Schema Audit

**Columns in Official Schema:**
```
face_crops table:
✅ id               INTEGER PRIMARY KEY
✅ project_id       INTEGER NOT NULL
✅ branch_key       TEXT
✅ image_path       TEXT NOT NULL
✅ crop_path        TEXT NOT NULL
✅ embedding        BLOB
✅ bbox_x           INTEGER  ← Official schema
✅ bbox_y           INTEGER  ← Official schema
✅ bbox_w           INTEGER  ← Official schema
✅ bbox_h           INTEGER  ← Official schema
✅ confidence       REAL
✅ is_representative INTEGER DEFAULT 0
✅ created_at       TEXT DEFAULT CURRENT_TIMESTAMP
```

**Columns NOT in Official Schema:**
```
❌ bbox             TEXT      ← Never existed, my wrong assumption
❌ quality_score    REAL      ← Not in official schema (yet?)
```

### Why User's Database is "Old"

The user's database likely predates some migrations but has the CORRECT core schema. The "old" label is misleading - it's actually the official production schema.

**What's Actually Old:**
- Missing `quality_score` column (was this planned but never added to schema?)
- This is OK - my code already handles it correctly by defaulting to 0.0

### Recommendation: Simplify the Code

**Current Code Complexity:**
My fixes check for 4 schema variations:
1. bbox TEXT + quality_score
2. bbox TEXT without quality_score
3. bbox_x/y/w/h + quality_score
4. bbox_x/y/w/h without quality_score

**Recommended Simplification:**
Since bbox TEXT doesn't exist in the official schema, simplify to 2 variations:
1. bbox_x/y/w/h + quality_score (if quality_score gets added officially)
2. bbox_x/y/w/h without quality_score (current official schema)

**Action Items:**

**Option A: Keep Current Code (Safe but Verbose)**
- ✅ Works with all possible database states
- ✅ Handles potential future schema with bbox TEXT
- ✅ No risk of breaking existing code
- ❌ Unnecessary complexity for non-existent schema
- ❌ Confusing for future developers

**Option B: Simplify to Official Schema Only (Recommended)**
- ✅ Matches official schema (repository/schema.py)
- ✅ Simpler, easier to understand
- ✅ Removes wrong assumptions
- ⚠️ Need to verify no databases actually use bbox TEXT
- ⚠️ Requires testing

**Option C: Add quality_score to Official Schema (Future)**
- Add quality_score column to repository/schema.py
- Create migration script: migrate_add_quality_score.py
- Update all code to expect quality_score
- Eliminates the need for conditional logic

### Migration Path Recommendation

**If you want to standardize the schema:**

1. **Audit all databases:**
   ```bash
   python3 diagnose_schema.py reference_data.db
   ```

2. **Check for bbox column:**
   ```sql
   PRAGMA table_info(face_crops);
   ```

3. **If bbox TEXT exists anywhere (unlikely):**
   Create migration to convert:
   ```sql
   ALTER TABLE face_crops ADD COLUMN bbox_x INTEGER;
   ALTER TABLE face_crops ADD COLUMN bbox_y INTEGER;
   ALTER TABLE face_crops ADD COLUMN bbox_w INTEGER;
   ALTER TABLE face_crops ADD COLUMN bbox_h INTEGER;

   UPDATE face_crops SET
       bbox_x = CAST(substr(bbox, 1, instr(bbox, ',') - 1) AS INTEGER),
       bbox_y = CAST(substr(bbox, instr(bbox, ',') + 1, ...) AS INTEGER),
       ...

   ALTER TABLE face_crops DROP COLUMN bbox;  -- SQLite needs table recreation
   ```

4. **Add quality_score officially:**
   ```sql
   ALTER TABLE face_crops ADD COLUMN quality_score REAL DEFAULT 0.5;
   ```

5. **Update schema version:**
   ```sql
   INSERT INTO schema_version (version, description)
   VALUES ('5.1.0', 'Standardized face_crops with quality_score column');
   ```

---

## Problem 3: Replace Wrong Face Crops After Confirmation

### User Request
> "The drawn faces after confirming it is a face must replace the wrong face crop after confirmation"

### Current Behavior
- Manual faces are added as NEW faces with new branch_keys
- They appear as separate people in the People section
- No mechanism to replace or merge with existing wrong detections

### Recommended Solution

**Option A: Manual Merge Workflow (Recommended)**
1. User draws manual face → Saved as new face with branch_key `manual_abc123`
2. New face appears in People section as separate person
3. User can **drag-and-drop merge** the manual face onto the correct person
4. This merges all photos and face crops, keeping the better one

**Advantages:**
- ✅ User has full control
- ✅ Can review before merging
- ✅ Drag-and-drop already implemented
- ✅ Undo/redo already supported
- ✅ No risk of wrong automatic merging

**Option B: Automatic Replacement (Complex)**
1. When drawing manual face, ask user which existing face to replace
2. Delete old face crop from database
3. Insert new manual face with SAME branch_key
4. Requires UI selection: "Replace which face?" dropdown

**Disadvantages:**
- ❌ More complex UI
- ❌ User might replace wrong face
- ❌ Hard to undo if mistake
- ❌ Requires identifying which face is "wrong"

**Option C: Hybrid Approach (Best User Experience)**
1. After drawing manual face, show confirmation dialog:
   ```
   ┌────────────────────────────────────────────────┐
   │  New Face Detected                             │
   ├────────────────────────────────────────────────┤
   │                                                │
   │  [Thumbnail of manual face crop]               │
   │                                                │
   │  What would you like to do?                    │
   │                                                │
   │  ○ Add as new person                           │
   │  ○ Replace existing face: [Dropdown ▼]         │
   │     • John Doe (confidence: 75%)               │
   │     • Unknown Person 1 (confidence: 45%)       │
   │     • Unknown Person 2 (confidence: 32%)       │
   │                                                │
   │           [Cancel]  [Save]                     │
   └────────────────────────────────────────────────┘
   ```

2. If "Replace existing face":
   - Delete old face crop (old branch_key)
   - Insert manual face with SAME branch_key as replaced face
   - Update face count in face_branch_reps
   - Refresh People section

3. If "Add as new person":
   - Same as current behavior
   - User can merge later via drag-and-drop

**Implementation for Option C:**
```python
def _on_manual_face_added(self, bbox: Tuple[int, int, int, int]):
    """Handle manual face rectangle drawn."""
    # Create crop
    crop_path = self._create_face_crop(*bbox)

    # Show confirmation dialog
    dialog = ManualFaceConfirmDialog(
        crop_path=crop_path,
        existing_faces=self.detected_faces,
        parent=self
    )

    result = dialog.exec()

    if result == QDialog.Accepted:
        action = dialog.get_action()  # "new" or "replace"

        if action == "replace":
            # Replace existing face
            target_branch = dialog.get_target_branch()
            self._replace_face_in_database(
                crop_path=crop_path,
                bbox=bbox,
                target_branch=target_branch
            )
        else:
            # Add as new person
            self._add_face_to_database(crop_path, bbox)
```

---

## Summary

### Issues Found

1. **Coordinate Bug:** Manual face rectangles appear in wrong position
   - **Cause:** Not subtracting x_offset/y_offset before scaling
   - **Impact:** HIGH - Makes manual face drawing unusable
   - **Fix:** 5 lines of code change

2. **Schema Confusion:** Assumed "new schema" that doesn't exist
   - **Cause:** Wrong assumption during bug fixing
   - **Impact:** MEDIUM - Unnecessary code complexity
   - **Fix:** Simplify schema detection logic

3. **Missing Feature:** Can't replace wrong face crops
   - **Cause:** Not implemented yet
   - **Impact:** LOW - User can work around with drag-and-drop merge
   - **Fix:** Add "replace existing face" option (optional enhancement)

### Action Plan

**Priority 1: Fix Coordinate Bug (CRITICAL)**
- Update mouseReleaseEvent in FacePhotoViewer
- Test with portrait and landscape photos
- Verify rectangles appear exactly where drawn

**Priority 2: Simplify Schema Code (RECOMMENDED)**
- Remove bbox TEXT checks (doesn't exist in official schema)
- Keep only bbox_x/y/w/h logic
- Add comment explaining official schema

**Priority 3: Face Replacement Feature (OPTIONAL)**
- Discuss with user which option they prefer (A, B, or C)
- Implement chosen approach
- Add to feature backlog if not immediate priority

---

**Status:** Analysis complete, ready for fixes
**Date:** 2025-12-17
**Branch:** claude/resume-improvement-work-k59mB
