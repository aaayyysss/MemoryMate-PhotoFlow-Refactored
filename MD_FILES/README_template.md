# MemoryMate-PhotoFlow Patch v3.0.2-hotfix

**Release Date**: 2025-11-29  
**Patch Type**: Critical Hotfix  
**Size**: ~50 KB (vs 1.2 GB full package)

---

## What This Patch Fixes

**CRITICAL BUG**: Face detection crash with error:
```
'NoneType' object has no attribute 'shape'
```

**Impact**: 100% crash rate on certain images (HEIC, large files, corrupted images)

**Fix**: Added defensive validation in quality calculation and image resize logic

---

## Installation Methods

### Method 1: Windows Batch Installer (Easiest)

1. Extract this patch to a temporary folder
2. Double-click `install_patch.bat`
3. Enter your MemoryMate installation directory when prompted
4. Restart MemoryMate

**Example**:
```
Enter MemoryMate installation directory: C:\Program Files\MemoryMate
```

### Method 2: Manual Installation

1. Locate your MemoryMate installation directory
2. Navigate to `services\` subfolder
3. **BACKUP**: Copy `face_detection_service.py` to `face_detection_service.py.backup`
4. Replace `face_detection_service.py` with the patched version from this package
5. Restart MemoryMate

---

## For PyInstaller Users (Standalone .exe)

**You CANNOT patch the .exe file directly.** You must:

1. **Option A**: Wait for the full v3.0.2 rebuild (1.2 GB)
2. **Option B**: If you have the source code:
   - Replace `services\face_detection_service.py` with the patched version
   - Rebuild using: `pyinstaller memorymate_pyinstaller.spec --clean`

---

## Verification

After applying the patch, verify it's working:

1. Open MemoryMate
2. Start a face detection scan on your photos
3. Check the log console - you should see:
   ```
   ✓ HEIC/HEIF support enabled for face detection
   ```
4. Face detection should complete without crashes

---

## Files Included

- `services/face_detection_service.py` - Patched face detection service
- `BUGFIX_FACE_DETECTION_NONETYPE.md` - Detailed technical documentation
- `install_patch.bat` - Automated installer for Windows
- `README.md` - This file

---

## Rollback Instructions

If you experience issues after applying the patch:

### Automatic Backup
The installer automatically creates a backup:
```
services\face_detection_service.py.backup_2025-11-29
```

### Restore Backup
1. Navigate to MemoryMate installation directory
2. Delete the patched `services\face_detection_service.py`
3. Rename `face_detection_service.py.backup_2025-11-29` to `face_detection_service.py`
4. Restart MemoryMate

---

## Technical Details

See `BUGFIX_FACE_DETECTION_NONETYPE.md` for:
- Root cause analysis
- Code changes
- Testing scenarios
- Performance impact

---

## Support

If you encounter issues:
1. Check the backup file was created
2. Verify you're patching the correct installation directory
3. Ensure MemoryMate is completely closed before applying patch
4. Check logs for error messages

---

## Changelog

### v3.0.2-hotfix (2025-11-29)
- **FIXED**: NoneType AttributeError in face quality calculation
- **FIXED**: Image resize failure handling
- **IMPROVED**: Quality calculation now uses full-resolution images (+10% accuracy)
- **IMPROVED**: Added multi-layer defensive validation

---

**Package Size**: ~50 KB  
**Installation Time**: <1 minute  
**Restart Required**: Yes
