# Duplicate Methods Cleanup Plan

**Date:** 2026-01-04
**File:** layouts/google_layout.py
**Total Duplicates:** 18 real duplicates in same class
**Status:** 🚨 CRITICAL - Must fix before further refactoring

---

## Summary

Found **18 real duplicate method definitions** across 2 classes:
- **GooglePhotosLayout:** 13 duplicates
- **MediaLightbox:** 5 duplicates

---

## Cleanup Strategy

**Rule:** Keep the FIRST complete implementation, remove all subsequent duplicates.

**Exceptions:** If a later implementation is clearly more complete/correct, note it and keep that one instead.

---

## GooglePhotosLayout Duplicates (13 methods)

### 1. `_build_tags_tree()`
- **Occurrences:** 2 (lines 9330, 9552)
- **Analysis:** Both implementations are IDENTICAL
- **Action:** ✅ **KEEP line 9330**, ❌ **REMOVE line 9552**

### 2. `_on_accordion_device_selected()`
- **Occurrences:** 5 (lines 9991, 10137, 10243, 10330, 10417)
- **Analysis:**
  - Line 9991: Most complete - handles Windows namespace paths with `_open_windows_device()`
  - Line 10137: Similar but less complete Windows handling
  - Lines 10243, 10330, 10417: Simplified versions using `fromLocalFile()`
- **Action:** ✅ **KEEP line 9991** (most complete), ❌ **REMOVE lines 10137, 10243, 10330, 10417**

### 3. `_on_accordion_person_deleted()`
- **Occurrences:** 6 (lines 10066, 10172, 10259, 10346, 10433, 10504)
- **Action:** ✅ **KEEP line 10066**, ❌ **REMOVE lines 10172, 10259, 10346, 10433, 10504**

### 4. `_on_accordion_person_merged()`
- **Occurrences:** 6 (lines 9764, 10084, 10190, 10277, 10364, 10451)
- **Action:** ✅ **KEEP line 9764**, ❌ **REMOVE lines 10084, 10190, 10277, 10364, 10451**

### 5. `_on_drag_merge()`
- **Occurrences:** 2 (lines 11852, 12926)
- **Analysis:** Both are IDENTICAL
- **Action:** ✅ **KEEP line 11852**, ❌ **REMOVE line 12926**

### 6. `_on_people_merge_history_requested()`
- **Occurrences:** 6 (lines 9795, 10115, 10221, 10308, 10395, 10482)
- **Action:** ✅ **KEEP line 9795**, ❌ **REMOVE lines 10115, 10221, 10308, 10395, 10482**

### 7. `_on_people_redo_requested()`
- **Occurrences:** 6 (lines 9809, 10129, 10235, 10322, 10409, 10496)
- **Action:** ✅ **KEEP line 9809**, ❌ **REMOVE lines 10129, 10235, 10322, 10409, 10496**

### 8. `_on_people_undo_requested()`
- **Occurrences:** 6 (lines 9802, 10122, 10228, 10315, 10402, 10489)
- **Action:** ✅ **KEEP line 9802**, ❌ **REMOVE lines 10122, 10228, 10315, 10402, 10489**

### 9. `_on_tags_item_clicked()`
- **Occurrences:** 2 (lines 9378, 9600)
- **Action:** ✅ **KEEP line 9378**, ❌ **REMOVE line 9600**

### 10. `_redo_last_undo()`
- **Occurrences:** 2 (lines 11930, 13004)
- **Action:** ✅ **KEEP line 11930**, ❌ **REMOVE line 13004**

### 11. `_refresh_people_sidebar()`
- **Occurrences:** 6 (lines 9788, 10108, 10214, 10301, 10388, 10475)
- **Action:** ✅ **KEEP line 9788**, ❌ **REMOVE lines 10108, 10214, 10301, 10388, 10475**

### 12. `_undo_last_merge()`
- **Occurrences:** 2 (lines 11873, 12947)
- **Action:** ✅ **KEEP line 11873**, ❌ **REMOVE line 12947**

### 13. `_update_undo_redo_state()`
- **Occurrences:** 2 (lines 12007, 13087)
- **Action:** ✅ **KEEP line 12007**, ❌ **REMOVE line 13087**

---

## MediaLightbox Duplicates (5 methods)

### 1. `_toggle_info_panel()`
- **Occurrences:** 2 (lines 1907, 4885)
- **Action:** ✅ **KEEP line 1907**, ❌ **REMOVE line 4885**

### 2. `eventFilter()`
- **Occurrences:** 2 in MediaLightbox (lines 1841, 7623)
- **Note:** There are other eventFilter() methods in other classes (legitimate)
- **Action:** ✅ **KEEP line 1841**, ❌ **REMOVE line 7623**

### 3. `keyPressEvent()`
- **Occurrences:** 2 in MediaLightbox (lines 4076, 6197)
- **Action:** ✅ **KEEP line 4076**, ❌ **REMOVE line 6197**

### 4. `resizeEvent()`
- **Occurrences:** 2 (lines 1506, 5919)
- **Action:** ✅ **KEEP line 1506**, ❌ **REMOVE line 5919**

### 5. `showEvent()`
- **Occurrences:** 2 (lines 1391, 6175)
- **Action:** ✅ **KEEP line 1391**, ❌ **REMOVE line 6175**

---

## Lines to Remove (Total: 39 methods to delete)

**GooglePhotosLayout (28 deletions):**
- Line 9552: `_build_tags_tree()`
- Lines 10137, 10243, 10330, 10417: `_on_accordion_device_selected()` (4 deletions)
- Lines 10172, 10259, 10346, 10433, 10504: `_on_accordion_person_deleted()` (5 deletions)
- Lines 10084, 10190, 10277, 10364, 10451: `_on_accordion_person_merged()` (5 deletions)
- Line 12926: `_on_drag_merge()`
- Lines 10115, 10221, 10308, 10395, 10482: `_on_people_merge_history_requested()` (5 deletions)
- Lines 10129, 10235, 10322, 10409, 10496: `_on_people_redo_requested()` (5 deletions)
- Lines 10122, 10228, 10315, 10402, 10489: `_on_people_undo_requested()` (5 deletions)
- Line 9600: `_on_tags_item_clicked()`
- Line 13004: `_redo_last_undo()`
- Lines 10108, 10214, 10301, 10388, 10475: `_refresh_people_sidebar()` (5 deletions)
- Line 12947: `_undo_last_merge()`
- Line 13087: `_update_undo_redo_state()`

**MediaLightbox (5 deletions):**
- Line 4885: `_toggle_info_panel()`
- Line 7623: `eventFilter()`
- Line 6197: `keyPressEvent()`
- Line 5919: `resizeEvent()`
- Line 6175: `showEvent()`

---

## Method Detection Strategy

Each duplicate method needs to be removed completely, including:
1. Method definition line (def ...)
2. Docstring (if present)
3. All method body lines
4. Until the next method definition or class-level code

**Detection Pattern:**
```python
# Find method start
def method_name(...):

# Find method end (next dedented line at same level as 'def')
# This could be:
# - Another method definition (def ...)
# - End of class
# - Class-level code
```

---

## Implementation Plan

### Phase 1: Backup (CRITICAL)
```bash
cp layouts/google_layout.py layouts/google_layout.py.backup
```

### Phase 2: Automated Removal
Use Python AST to:
1. Parse the file
2. Identify duplicate methods by line number
3. Remove complete method bodies
4. Preserve formatting

### Phase 3: Manual Verification
- Check diff to ensure only duplicates removed
- Verify no code broken by removal

### Phase 4: Testing
```bash
python -m pytest tests/test_google_layout.py -v
python main_qt.py --test-mode
```

### Phase 5: Commit
```bash
git add layouts/google_layout.py
git commit -m "fix: Remove 39 duplicate method definitions from google_layout.py"
```

---

## Expected Impact

**Before Cleanup:**
- 18,279 lines
- 18 duplicate methods (39 total definitions)
- Runtime uses LAST definition (unpredictable behavior)

**After Cleanup:**
- ~17,500 lines (estimate: 700-800 lines removed)
- 0 duplicate methods
- Predictable, maintainable code

**Risks:**
- LOW: Keeping first implementations should preserve intended behavior
- Mitigation: Backup file, careful testing

---

## Next Steps After Cleanup

1. **Create centralized configuration** (face_detection_config.py)
2. **Begin modularization** (extract timeline_view, face_controller)
3. **Add tests** for extracted components
4. **Performance monitoring** instrumentation

---

**Status:** Ready to execute cleanup
**Estimated Time:** 30-60 minutes (automated + verification)
**Priority:** 🚨 CRITICAL - Must complete before other refactoring
