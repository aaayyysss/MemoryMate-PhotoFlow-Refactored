# GPS Location & Progress Dialog Audit Report
**Date:** 2026-01-09
**Branch:** claude/audit-github-debug-logs-kycmr

## Executive Summary

This audit investigates two reported issues:
1. **GPS location data not persisting after manual editing** - Location is lost when photo is rescanned
2. **Progress dialog positioning** - Verify dialogs are centered on main application window

---

## 🔴 CRITICAL ISSUE: GPS Location Data Not Persisting

### Problem Statement

When a user manually edits GPS location for a photo using the Location Editor:
1. GPS data is saved successfully to the database
2. Photo appears in Locations section
3. **BUT**: If the database is cleared and photos are rescanned, the GPS location data is LOST

**Root Cause:** GPS location data is only saved to the database, NOT written back to the photo file's EXIF metadata.

---

### Technical Analysis

#### Current Implementation Flow

**1. Location Editor Dialog** (`ui/location_editor_dialog.py`)
- User enters GPS coordinates (latitude, longitude)
- User optionally enters location name
- Dialog emits `locationSaved` signal with data

**2. Integration Handler** (`ui/location_editor_integration.py:129`)
```python
def on_location_saved(lat, lon, name):
    success = save_photo_location(photo_path, lat, lon, name)  # Line 129
```

**3. Save Function** (`ui/location_editor_integration.py:87`)
```python
def save_photo_location(photo_path, latitude, longitude, location_name):
    db = ReferenceDB()
    db.update_photo_gps(photo_path, latitude, longitude, location_name)  # LINE 87
    # ❌ NO EXIF WRITING - Only database updated
```

**4. Database Update** (`reference_db.py:3424-3428`)
```python
cur.execute("""
    UPDATE photo_metadata
    SET gps_latitude = ?, gps_longitude = ?, location_name = ?
    WHERE path = ?
""", (latitude, longitude, location_name, normalized_path))
```

**Result:** Location data exists ONLY in database, NOT in photo file.

---

### Why This is a Problem

1. **Data Loss on Rescan:** When database is cleared/recreated, all manual GPS edits are lost
2. **No Portability:** GPS data doesn't travel with the photo file
3. **Inconsistent with User Expectations:** Users expect metadata edits to be permanent
4. **Not Reversible:** Lost data cannot be recovered after rescan

---

### EXIF Writing Capability Assessment

**Checked for EXIF writing functionality:**
- ✅ `services/metadata_service.py` - Can READ EXIF (uses PIL.ExifTags)
- ❌ **NO piexif import found** - Cannot WRITE EXIF
- ❌ **NO EXIF writing methods** - No functionality to update photo files

**Conclusion:** Application has NO capability to write GPS data back to photo files.

---

### Solution: Implement EXIF GPS Writing

**Required Implementation:**

1. **Install piexif library** (if not already installed)
   ```bash
   pip install piexif
   ```

2. **Create EXIF GPS writing service** (`services/exif_gps_writer.py`)
   - Convert decimal GPS coordinates to EXIF format (degrees/minutes/seconds)
   - Handle GPS reference tags (N/S for latitude, E/W for longitude)
   - Preserve existing EXIF data while updating GPS tags
   - Handle edge cases (files without EXIF, read-only files, etc.)

3. **Update `save_photo_location` function**
   ```python
   def save_photo_location(photo_path, latitude, longitude, location_name):
       # 1. Update database (existing code)
       db = ReferenceDB()
       db.update_photo_gps(photo_path, latitude, longitude, location_name)

       # 2. Write GPS data to photo file EXIF metadata (NEW)
       from services.exif_gps_writer import write_gps_to_exif
       write_gps_to_exif(photo_path, latitude, longitude)

       return True
   ```

4. **EXIF GPS Tag Structure**
   GPS data in EXIF uses these tags:
   - `GPSLatitude` - Degrees, Minutes, Seconds as rationals
   - `GPSLatitudeRef` - 'N' or 'S'
   - `GPSLongitude` - Degrees, Minutes, Seconds as rationals
   - `GPSLongitudeRef` - 'E' or 'W'

5. **Coordinate Conversion**
   Convert decimal (37.7749) to DMS format:
   ```
   37.7749° = 37° 46' 29.64" N
   -122.4194° = 122° 25' 9.84" W (negative = West)
   ```

---

### Implementation Priority

**Priority:** 🔴 **CRITICAL**

**Rationale:**
- Data loss issue - users lose manual edits
- Breaks expected behavior (metadata should persist)
- No workaround available
- Affects all location editing functionality

**Estimated Effort:**
- Create GPS EXIF writer: ~2-3 hours
- Update save_photo_location: ~30 minutes
- Testing: ~1 hour
- **Total:** ~4 hours

---

## 🟡 ISSUE: Progress Dialog Positioning

### Current Implementation

**Scan Progress Dialog** (`controllers/scan_controller.py:112-138`)
```python
self.main._scan_progress = QProgressDialog(
    tr("messages.scan_preparing"),
    tr("messages.scan_cancel_button"),
    0, 100, self.main  # ← Parent is self.main (MainWindow)
)
self.main._scan_progress.setWindowModality(Qt.WindowModal)
```

**Post-Scan Progress Dialog** (`controllers/scan_controller.py:417-434`)
```python
progress = QProgressDialog(tr("messages.progress_building_branches"), None, 0, 4, self.main)
progress.setWindowModality(Qt.WindowModal)
```

---

### Qt Dialog Positioning Behavior

**Qt.WindowModal behavior:**
- Dialog is modal to the parent window
- **Automatically centers on parent window** when shown
- Cannot be moved behind parent
- Parent window is disabled while dialog is open

**Expected:** Dialogs should automatically center on `self.main` window.

**However:** No explicit positioning code exists. Qt's automatic centering may fail if:
1. Main window is minimized when dialog appears
2. Main window is on different screen
3. Dialog is shown before main window geometry is fully initialized

---

### Verification Test

To verify current behavior:
1. Launch application
2. Start repository scan
3. Observe progress dialog position:
   - ✅ **Expected:** Dialog centered on main window
   - ❌ **Potential Issue:** Dialog appears at screen center or default position

---

### Solution: Explicit Dialog Centering

**Add explicit positioning after dialog creation:**

```python
# After dialog creation
self.main._scan_progress.show()

# CRITICAL FIX: Explicitly center dialog on parent window
try:
    parent_geometry = self.main.geometry()
    dialog_geometry = self.main._scan_progress.geometry()

    # Calculate center position
    center_x = parent_geometry.x() + (parent_geometry.width() - dialog_geometry.width()) // 2
    center_y = parent_geometry.y() + (parent_geometry.height() - dialog_geometry.height()) // 2

    self.main._scan_progress.move(center_x, center_y)
except Exception as e:
    self.logger.warning(f"Could not center progress dialog: {e}")
```

**Alternative (simpler):**
```python
# Use Qt's automatic centering with explicit geometry update
self.main._scan_progress.adjustSize()
self.main._scan_progress.move(
    self.main.geometry().center() - self.main._scan_progress.rect().center()
)
```

---

### Implementation Priority

**Priority:** 🟡 **MEDIUM**

**Rationale:**
- User experience issue (dialog may appear off-center)
- Not breaking functionality (dialog still works)
- Quick fix (add centering code)
- Low risk (failsafe with try/except)

**Estimated Effort:**
- Add centering code: ~15 minutes
- Test on multiple screens: ~15 minutes
- **Total:** ~30 minutes

---

## Summary of Issues

| Issue | Severity | Impact | Effort | Priority |
|-------|----------|--------|--------|----------|
| GPS data not written to EXIF | 🔴 CRITICAL | Data loss on rescan | 4 hours | HIGH |
| Progress dialog centering | 🟡 MEDIUM | UX inconsistency | 30 min | MEDIUM |

---

## Recommended Action Plan

### Phase 1: GPS EXIF Writing (HIGH PRIORITY)
1. ✅ Install piexif library
2. ✅ Create `services/exif_gps_writer.py`
3. ✅ Implement GPS coordinate conversion (decimal → DMS)
4. ✅ Implement EXIF GPS tag writing
5. ✅ Update `save_photo_location` to write to both DB and EXIF
6. ✅ Add error handling for read-only files
7. ✅ Test with various photo formats (JPEG, HEIC)

### Phase 2: Progress Dialog Centering (MEDIUM PRIORITY)
1. ✅ Add explicit centering code to scan_controller.py
2. ✅ Test on single and multi-monitor setups
3. ✅ Verify on Windows/Linux/Mac

---

## Files to Modify

### GPS EXIF Writing
- **NEW:** `services/exif_gps_writer.py` (create new file)
- **MODIFY:** `ui/location_editor_integration.py` (update save_photo_location)
- **MODIFY:** `requirements.txt` (add piexif dependency)

### Progress Dialog Centering
- **MODIFY:** `controllers/scan_controller.py` (add centering code)

---

## Testing Checklist

### GPS Data Persistence
- [ ] Edit GPS location for a photo
- [ ] Verify location appears in database
- [ ] Verify location appears in Locations section
- [ ] **CRITICAL:** Read photo file EXIF and verify GPS tags are present
- [ ] Clear database and rescan
- [ ] **CRITICAL:** Verify GPS location is still present after rescan
- [ ] Test with JPEG files
- [ ] Test with HEIC files (if supported)
- [ ] Test clearing GPS location (should remove EXIF tags)

### Progress Dialog Positioning
- [ ] Launch app on single monitor
- [ ] Start scan, verify dialog centered on main window
- [ ] Launch app on multi-monitor setup
- [ ] Move main window to secondary monitor
- [ ] Start scan, verify dialog centered on main window (not primary screen)
- [ ] Minimize main window, start scan, verify dialog appears correctly

---

## Risk Assessment

### GPS EXIF Writing
**Risks:**
- ⚠️ **File corruption** - EXIF writing could corrupt photos if not done correctly
- ⚠️ **Permission errors** - Cannot write to read-only files
- ⚠️ **Format compatibility** - Some formats don't support EXIF (PNG, BMP)

**Mitigation:**
- ✅ Use well-tested piexif library
- ✅ Create backup before writing (optional user setting)
- ✅ Add comprehensive error handling
- ✅ Skip unsupported formats gracefully
- ✅ Extensive testing before deployment

### Progress Dialog Centering
**Risks:**
- ⚠️ **Edge cases** - May fail on unusual window states

**Mitigation:**
- ✅ Wrap in try/except block
- ✅ Fall back to Qt's default positioning if centering fails

---

## Conclusion

**GPS Location Persistence:** This is a CRITICAL bug that causes data loss. Users reasonably expect that manually edited GPS coordinates will persist with the photo file, not just in the database. This should be fixed immediately.

**Progress Dialog Positioning:** This is a MEDIUM priority UX improvement. While not breaking functionality, explicit centering will provide a more polished user experience.

---

**Auditor:** Claude
**Date:** 2026-01-09
**Status:** Awaiting implementation approval
