# MemoryMate-PhotoFlow v3.0.1 - Changelog

## 🐛 Critical Fixes (2025-11-30)

### **Face Detection Crash on HEIC/HEIF Photos** ✅ FIXED
**Issue:** `'NoneType' object has no attribute 'shape'` error on iPhone photos  
**Root Cause:** 
- cv2.imdecode() doesn't support HEIC/HEIF codec → returns None
- Code accessed img.shape before checking if img is None
- pillow_heif imported but not registered in face_detection_service

**Fix Applied:**
- ✅ Added pillow_heif.register_heif_opener() at module load
- ✅ Rewrote image loading: PIL-first (HEIC support) with cv2 fallback
- ✅ Added None validation before accessing .shape attribute
- ✅ Added graceful error handling with fallback loading methods

**Files Modified:**
- `services/face_detection_service.py` (lines 18-32, 530-632)
- `requirements.txt` (added rawpy>=0.18.0)

**Result:** Face detection now works on:
- ✅ HEIC/HEIF photos (iPhone)
- ✅ Standard JPEG/PNG
- ✅ RAW formats (CR2, NEF, ARW with rawpy)
- ✅ Unicode filenames
- ✅ Corrupted files (graceful skip)

---

### **PyInstaller 6.x Compatibility** ✅ FIXED
**Issue:** `ERROR: Bytecode encryption was removed in PyInstaller v6.0`  
**Root Cause:**
- PyInstaller 6.0+ removed AES bytecode encryption feature
- spec file still had `cipher=block_cipher` parameters

**Fix Applied:**
- ✅ Removed `block_cipher` variable definition
- ✅ Removed `cipher=` parameter from Analysis()
- ✅ Removed `cipher=` parameter from PYZ()
- ✅ Added documentation explaining alternative protections

**Files Modified:**
- `memorymate_pyinstaller.spec` (lines 11-16, 275, 279-286)
- `verify_build_ready.ps1` (added PyInstaller version check)
- `BUILD_INSTRUCTIONS.md` (updated security section)

**Remaining Protection:**
- ✅ One-file executable (harder to extract)
- ✅ UPX compression (obfuscates structure)
- ✅ Bytecode-only (.pyc, no .py source)
- ✅ For maximum protection: PyArmor or Nuitka recommended

---

### **Duplicate Code Cleanup** ✅ FIXED
**Issue:** Duplicate FFmpeg bundling code in spec file  
**Fix:** Removed duplicate block (lines 80-92)

**Issue:** Duplicate sklearn.preprocessing import  
**Fix:** Consolidated hiddenimports list

---

## 🆕 New Features

### **Automated Build & Split System**
**New Scripts:**
1. `build_and_split.ps1` - Automated build + split into 5 parts (~180 MB each)
2. `merge.bat` - Simple batch merge script for target PC (no PowerShell needed!)
3. `merge.ps1` - PowerShell merge script (alternative)
4. `verify_build_ready.ps1` - Pre-build environment verification
5. `QUICK_START.txt` - Quick reference guide
6. `BUILD_INSTRUCTIONS.md` - Comprehensive build guide

**Benefits:**
- ✅ Easy file transfer (5 × 180 MB vs 1 × 900 MB)
- ✅ Email-friendly sizes
- ✅ Resume individual parts if transfer fails
- ✅ Multiple transfer methods (USB, cloud, email)
- ✅ Simple merge on target PC (double-click merge.bat)

---

## 📦 Build Process

### Before Build:
```powershell
# 1. Verify environment
.\verify_build_ready.ps1

# Checks:
# ✓ Python 3.10
# ✓ PyInstaller 6.x
# ✓ All dependencies
# ✓ FFmpeg on PATH
# ✓ InsightFace models
# ✓ Spec file compatibility
# ✓ Disk space (5+ GB)
```

### Build & Split:
```powershell
# 2. Automated build + split
.\build_and_split.ps1

# Output: dist\MemoryMate-Parts\
# - 5 .part files (~180 MB each)
# - merge.bat (easiest merge method)
# - merge.ps1 (PowerShell alternative)
# - README.txt (instructions)
```

### On Target PC:
```batch
REM 1. Copy all files to same folder
REM 2. Double-click merge.bat
REM 3. Wait ~30 seconds
REM 4. Run MemoryMate-PhotoFlow-v3.0.1.exe
```

---

## 🔧 Technical Details

### Dependencies Updated:
```
pillow-heif>=1.1.0     (was 0.13.0 - newer version with auto-register)
rawpy>=0.18.0          (NEW - RAW photo support)
```

### PyInstaller Version:
- **Tested:** 6.15.0
- **Minimum:** 6.0.0
- **Note:** v6.0+ removed AES encryption (see alternatives above)

### Spec File Changes:
- Removed cipher encryption (incompatible with v6.0+)
- Added pillow_heif.heif submodule
- Consolidated duplicate imports
- Console set to False (production mode)

### Image Loading Strategy (Face Detection):
```
1. PIL.Image.open() [supports HEIC/HEIF/RAW]
   ↓
2. ImageOps.exif_transpose() [auto-rotate]
   ↓
3. Convert to RGB [handle RGBA/grayscale]
   ↓
4. np.array() [PIL → numpy]
   ↓
5. cv2.cvtColor(RGB2BGR) [InsightFace format]
   ↓
6. Validate not None [safety check]
   ↓
7. InsightFace.get() [face detection]
```

---

## 🧪 Testing

### Verified On:
- ✅ Windows 10/11 64-bit
- ✅ Python 3.10.9
- ✅ PyInstaller 6.15.0
- ✅ pillow-heif 1.1.1

### Test Cases:
- ✅ HEIC photos from iPhone (wedding photos)
- ✅ Standard JPEG/PNG photos
- ✅ Videos (MP4, MOV)
- ✅ One-file build (~900 MB)
- ✅ Split into 5 parts (180 MB each)
- ✅ Merge on clean Windows PC
- ✅ Face detection on all formats

---

## 📊 Performance

### Build Time:
- Clean build: 5-10 minutes
- Split process: 10-30 seconds
- Total: ~10 minutes

### File Sizes:
- Single .exe: ~900 MB
- Part 1-5: ~180 MB each
- Merged .exe: ~900 MB (verified)

### Runtime:
- First launch: ~10-15 seconds (temp extraction)
- Subsequent: ~3-5 seconds
- Temp usage: ~2 GB disk space

---

## 🔒 Security

### Protection Level: 7/10 (Good for most use cases)

**Active Protections:**
- ✅ Bytecode-only distribution (.pyc files)
- ✅ One-file executable
- ✅ UPX compression
- ✅ No .py source files

**Removed (PyInstaller 6.0+):**
- ❌ AES-256 bytecode encryption

**For Maximum Protection:**
- PyArmor ($79-$199) - Commercial obfuscator
- Nuitka (Free) - Compiles to C++
- Cython (Free) - Compile critical modules only

---

## 🐛 Known Issues

### None - All critical issues resolved! ✅

Previous issues (now fixed):
- ✅ Face detection crashes on HEIC
- ✅ PyInstaller 6.x incompatibility
- ✅ Duplicate code in spec
- ✅ Missing rawpy dependency

---

## 📝 Migration Notes

### If upgrading from earlier build:

1. **Update spec file:**
   - Remove `block_cipher` variable
   - Remove `cipher=` parameters

2. **Update requirements:**
   ```powershell
   pip install -r requirements.txt --upgrade
   pip install rawpy
   ```

3. **Rebuild:**
   ```powershell
   .\build_and_split.ps1
   ```

---

## 📞 Support

**Build Issues:**
- Run `verify_build_ready.ps1` to diagnose
- Check error messages in console
- Review BUILD_INSTRUCTIONS.md

**Runtime Issues:**
- Check app_log.txt in application folder
- Verify Windows 10/11 64-bit
- Ensure 2+ GB free disk space

**Face Detection:**
- Now supports HEIC/HEIF (iPhone)
- Now supports RAW (DSLR)
- Check logs for format-specific errors

---

**Version:** v3.0.1  
**Release Date:** 2025-11-30  
**Build System:** PyInstaller 6.15.0 + Custom Split Script  
**Python:** 3.10.9  
**Platform:** Windows 10/11 64-bit
