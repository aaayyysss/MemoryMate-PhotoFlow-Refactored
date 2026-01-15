# Sidebar Synchronization Fix - Session 6C
## Date: 2025-12-17

---

## Issue

**User Report:**
> "The sidebar in the google-layout is not updated and synchronized after the scanning of Repository is concluded. I need always to toggle to the current layout and back to the google layout in order for the synchronization to be done and the sidebar is showing all results."

---

## Root Cause Analysis

### The Problem

After a Repository scan with face detection and clustering:
1. ✅ The photo grid updates correctly showing detected faces
2. ❌ The People section in the accordion sidebar does NOT update
3. ⚠️ Only when toggling layouts does the sidebar refresh

### Why This Happens

**Timeline of Events:**

1. **Scan completes** → `scan_controller.py:_finalize_scan_refresh()` runs
   - Line 692: Calls `accordion_sidebar.reload_all_sections()`
   - This reloads ALL sidebar sections including People
   - **BUT:** Face clustering is still running asynchronously in background

2. **Face clustering finishes** → Clustering completion handler runs
   - Line 548: Calls `_build_people_tree()` to refresh photo grid ✅
   - **Missing:** Does NOT refresh People section in sidebar ❌

3. **User toggles layouts** → Layout switch triggers full sidebar reload
   - This is why toggling "fixes" the issue temporarily

### The Bug

In `controllers/scan_controller.py` lines 538-551, the face clustering completion handler:

```python
# Refresh People grid with newly clustered faces
current_layout._build_people_tree()
self.logger.info("✓ People grid refreshed with detected faces")

# ❌ MISSING: No sidebar refresh here!
```

This only refreshes the **photo grid** (filtered by person), not the **People section** in the accordion sidebar.

---

## The Fix

### Code Changes

**File:** `controllers/scan_controller.py`
**Lines:** 551-556 (added 6 new lines)

```python
# Refresh People grid with newly clustered faces
current_layout._build_people_tree()
self.logger.info("✓ People grid refreshed with detected faces")

# CRITICAL FIX: Also refresh People section in accordion sidebar
# Without this, sidebar doesn't update until user toggles layouts
if hasattr(current_layout, 'accordion_sidebar'):
    self.logger.info("Refreshing People section in sidebar...")
    current_layout.accordion_sidebar.reload_people_section()
    self.logger.info("✓ People section in sidebar refreshed")
```

### What This Does

1. After face clustering completes, refresh the photo grid (existing)
2. **NEW:** Also refresh the People section in the accordion sidebar
3. Uses `accordion_sidebar.reload_people_section()` which:
   - Loads face clusters from database asynchronously
   - Updates the People section UI with new face cards
   - Shows correct person names and photo counts

---

## Testing

### Before Fix

1. Run Repository scan with face detection
2. Wait for scan + clustering to complete
3. **Observe:** Photo grid shows faces, but sidebar People section is empty/old
4. Toggle to Current layout and back to Google layout
5. **Observe:** Sidebar now shows detected faces (workaround)

### After Fix

1. Run Repository scan with face detection
2. Wait for scan + clustering to complete
3. **Observe:** Both photo grid AND sidebar People section update automatically ✅
4. No need to toggle layouts ✅

### Test Checklist

- [ ] Scan repository with face detection enabled
- [ ] Verify clustering completes (progress dialog shows 100%)
- [ ] Check photo grid shows people thumbnails
- [ ] **Check sidebar People section updates without toggling layouts**
- [ ] Verify person names and photo counts are correct
- [ ] Test with multiple people (5+) to ensure all appear

---

## Technical Details

### Async Timing

The fix handles the asynchronous nature of face clustering:

1. **Main scan refresh** (line 692): Reloads sidebar BEFORE clustering finishes
   - People section shows old/empty data at this point

2. **Clustering completion** (lines 551-556): Reloads ONLY People section after clustering finishes
   - People section now shows newly detected faces
   - This is a targeted refresh, not a full reload

### Why Not Use `reload_all_sections()`?

The main scan already calls `reload_all_sections()` at line 692. We only need to refresh the **People section** after clustering, not all sections (Folders, Dates, Videos, etc.).

Using `reload_people_section()` is:
- ✅ More efficient (only one section reloads)
- ✅ Faster (no unnecessary database queries for other sections)
- ✅ Less disruptive to UI (other sections don't flicker)

---

## Related Code

### AccordionSidebar API

**File:** `ui/accordion_sidebar/__init__.py`

```python
def reload_all_sections(self):
    """Reload all sections from database."""
    for section_id, section in self.section_logic.items():
        self._trigger_section_load(section_id)

def reload_people_section(self):
    """Public helper to refresh the people section content."""
    self._trigger_section_load("people")
```

### PeopleSection Loading

**File:** `ui/accordion_sidebar/people_section.py`

```python
def load_section(self) -> None:
    """Load people section data in a background thread."""
    # Increments generation counter (staleness check)
    # Queries database: db.get_face_clusters(project_id)
    # Emits signals.loaded when data ready
```

---

## Impact

### Before
- ❌ Sidebar People section does not update after scan
- ❌ User must toggle layouts to see results (workaround)
- ❌ Confusing UX - looks like faces weren't detected
- ❌ Requires manual intervention every time

### After
- ✅ Sidebar People section updates automatically
- ✅ No layout toggling required
- ✅ Clear UX - faces appear immediately when clustering completes
- ✅ Seamless workflow

---

## Additional Notes

### Logging

The fix adds comprehensive logging:

```
[INFO] Refreshing People grid after face clustering...
[INFO] ✓ People grid refreshed with detected faces
[INFO] Refreshing People section in sidebar...
[INFO] ✓ People section in sidebar refreshed
```

This helps debug any future synchronization issues.

### Error Handling

The fix is wrapped in the existing try/except block (line 541-558), so any errors during sidebar refresh won't crash the scan completion process.

### Backward Compatibility

The fix uses defensive checks:
```python
if hasattr(current_layout, 'accordion_sidebar'):
```

This ensures compatibility with:
- Current layout (doesn't have accordion_sidebar)
- Future layout implementations
- Edge cases where sidebar hasn't been initialized

---

## Conclusion

**Summary:**
Fixed sidebar synchronization issue by adding a People section refresh after face clustering completes.

**Root Cause:**
Clustering completion handler only refreshed photo grid, not sidebar.

**Solution:**
Call `accordion_sidebar.reload_people_section()` after `_build_people_tree()`.

**Result:**
Sidebar updates automatically without requiring layout toggle workaround.

---

**Session:** 6C - Sidebar Synchronization Fix
**Date:** 2025-12-17
**Files Modified:** 1 (`controllers/scan_controller.py`, +6 lines)
**Status:** ✅ Ready for testing
