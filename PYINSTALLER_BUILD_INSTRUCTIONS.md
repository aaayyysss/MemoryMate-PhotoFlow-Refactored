# PyInstaller Build Instructions for MemoryMate-PhotoFlow

**Date:** 2025-12-18
**Version:** 3.0.2
**Build Type:** One-file executable (.exe)
**Status:** ✅ READY TO BUILD

---

## Prerequisites

### 1. Install PyInstaller
```bash
pip install pyinstaller==6.3.0
```

### 2. Install UPX (Optional but Recommended)
Download from: https://github.com/upx/upx/releases
- Reduces executable size by ~50%
- Obfuscates binary structure for security
- Add to PATH or place `upx.exe` in project directory

### 3. Verify FFmpeg is Installed
```bash
ffmpeg -version
ffprobe -version
```
If not installed:
- Download from: https://ffmpeg.org/download.html
- Add to system PATH
- Required for video thumbnails and metadata

### 4. Verify InsightFace Models Exist
Check if models are present:
```bash
dir %USERPROFILE%\.insightface\models\buffalo_l
```
Should contain:
- det_10g.onnx (or scrfd_10g_bnkps.onnx)
- genderage.onnx
- w600k_r50.onnx

If missing, run face detection once in the app to download models automatically.

---

## Build Process

### Step 1: Navigate to Project Directory
```bash
cd C:\path\to\MemoryMate-PhotoFlow-Refactored
```

### Step 2: Run PyInstaller
```bash
pyinstaller memorymate_pyinstaller.spec
```

### Expected Output
```
Building EXE from EXE-00.toc
Building EXE from EXE-00.toc completed successfully.
```

### Build Location
```
dist/MemoryMate-PhotoFlow-v3.0.2.exe
```

---

## What's Included in the Build

### Core Application
- ✅ All Python code (compiled to bytecode)
- ✅ PySide6 (Qt6 GUI framework)
- ✅ All layouts (Google, Apple, Lightroom, Current)
- ✅ Accordion sidebar with all sections
- ✅ Face detection and recognition UI

### Dependencies
- ✅ InsightFace + buffalo_l models (face detection)
- ✅ ONNXRuntime (ML inference)
- ✅ OpenCV (cv2)
- ✅ NumPy, scikit-learn
- ✅ PIL/Pillow + pillow-heif (image processing)
- ✅ rawpy (RAW image support)
- ✅ FFmpeg + FFprobe (video support)
- ✅ pywin32 (Windows device detection)
- ✅ Matplotlib (visualization)

### Data Files
- ✅ Language files (lang/, locales/)
- ✅ Configuration files (config/)
- ✅ Layout templates (layouts/)
- ✅ SQL migrations (migrations/)
- ✅ App icon (app_icon.ico)

### NOT Included (Users Create Fresh)
- ❌ Database files (reference_data.db, thumbnails_cache.db)
- ❌ User settings
- ❌ Cached thumbnails
- ❌ User projects

---

## Updated Modules (2025-12-18)

### New Additions to Spec File
```python
# UI modules (face detection features)
'ui.face_crop_editor',          # Manual face cropping
'ui.face_quality_dashboard',    # Face quality scoring
'ui.face_quality_scorer',       # Quality scoring utility
'ui.cluster_face_selector',     # Face clustering selector
'ui.face_naming_dialog',        # Face naming dialog
'ui.visual_photo_browser',      # Visual photo browser

# Accordion sidebar package (Phase 2 refactor)
'accordion_sidebar',            # Root controller
'ui.accordion_sidebar',         # Package
'ui.accordion_sidebar.base_section',
'ui.accordion_sidebar.dates_section',
'ui.accordion_sidebar.devices_section',
'ui.accordion_sidebar.folders_section',
'ui.accordion_sidebar.people_section',
'ui.accordion_sidebar.quick_section',
'ui.accordion_sidebar.section_widgets',
'ui.accordion_sidebar.videos_section',

# Layout modules
'layouts.layout_manager',       # Layout manager
'layouts.layout_protocol',      # Layout protocol interface
'layouts.video_editor_mixin',   # Video editing mixin

# Core modules
'db_writer',                    # Database write operations
```

---

## Build Configuration

### Security Features
- **One-file mode**: All files packed in single .exe
- **UPX compression**: Obfuscates binary structure
- **Bytecode-only**: No .py source files included
- **Icon**: Custom app_icon.ico embedded

### Performance Settings
```python
debug=False          # No debug output
console=True         # Console window for logging
upx=True            # Enable UPX compression
strip=False         # Keep debug symbols for better error reports
```

### Runtime Hooks
- `pyi_rth_insightface.py` - Sets INSIGHTFACE_HOME to bundled models

---

## Testing the Build

### Step 1: Copy to Test Machine (No Python)
Copy `dist/MemoryMate-PhotoFlow-v3.0.2.exe` to a Windows PC without Python installed.

### Step 2: First Run
1. Double-click the .exe
2. Wait for temporary extraction (~30 seconds first time)
3. App should start and show splash screen
4. Create a new project
5. Scan photos

### Step 3: Test Core Features
- ✅ Photo scanning and import
- ✅ Thumbnail generation
- ✅ Video playback
- ✅ Face detection (if models bundled)
- ✅ Sidebar navigation (accordion)
- ✅ Search and filtering
- ✅ Photo viewing (MediaLightbox)
- ✅ Tag management

### Step 4: Check for Errors
Monitor console output for:
- ❌ Missing DLL errors
- ❌ Import errors
- ❌ File not found errors
- ❌ InsightFace model loading errors

---

## Common Build Issues

### Issue 1: "Module not found" Errors
**Symptom:** ImportError when running the .exe
**Solution:** Add missing module to `hiddenimports` in spec file

### Issue 2: FFmpeg Not Found
**Symptom:** Video thumbnails don't generate
**Solution:**
- Verify FFmpeg is on PATH when building
- Or manually copy ffmpeg.exe/ffprobe.exe to dist/ folder

### Issue 3: InsightFace Models Missing
**Symptom:** Face detection doesn't work
**Solution:**
- Run face detection once before building
- Verify models exist in `~/.insightface/models/buffalo_l`
- Check spec file includes model_datas

### Issue 4: UPX Failed
**Symptom:** "UPX is not available" warning
**Solution:**
- Install UPX and add to PATH, or
- Disable UPX: Set `upx=False` in spec file

### Issue 5: Executable Too Large
**Current Size:** ~800MB (with all dependencies)
**Optimizations:**
- Enable UPX compression (-50% size)
- Exclude unused modules (matplotlib if not needed)
- Use --exclude-module for test frameworks

---

## Build Size Breakdown

| Component | Size (MB) | Purpose |
|-----------|-----------|---------|
| Python + PySide6 | ~150 | GUI framework |
| InsightFace + ONNX | ~200 | Face detection/recognition |
| OpenCV | ~100 | Image processing |
| NumPy + sklearn | ~50 | ML libraries |
| PIL/Pillow | ~20 | Image codecs |
| FFmpeg | ~80 | Video processing |
| App code | ~10 | Your application |
| Other dependencies | ~190 | Misc libraries |
| **Total (uncompressed)** | **~800MB** | |
| **Total (UPX compressed)** | **~400MB** | Recommended |

---

## Distribution Checklist

Before distributing the .exe to users:

- [ ] Test on clean Windows machine (no Python)
- [ ] Verify all core features work
- [ ] Check face detection works (if models included)
- [ ] Test video playback and thumbnails
- [ ] Verify FFmpeg bundled correctly
- [ ] Test photo import from various sources
- [ ] Check sidebar accordion works
- [ ] Test MediaLightbox (photo viewer)
- [ ] Verify no console errors
- [ ] Create user documentation
- [ ] Package with README.txt

---

## Deployment Package Contents

Recommended distribution structure:
```
MemoryMate-PhotoFlow-v3.0.2/
  ├── MemoryMate-PhotoFlow-v3.0.2.exe  (main executable)
  ├── README.txt                        (user guide)
  ├── LICENSE.txt                       (if applicable)
  └── CHANGELOG.txt                     (version history)
```

---

## Troubleshooting Runtime Errors

### Enable Debug Logging
Edit spec file:
```python
console=True,  # Already enabled - shows console
debug=True,    # Change to True for verbose output
```

Rebuild with:
```bash
pyinstaller memorymate_pyinstaller.spec
```

### Check Temp Directory
When running, app extracts to:
```
%TEMP%\_MEIxxxxxx\
```
Browse this folder to verify all files extracted correctly.

### Common Missing Files
If app crashes on startup, check for:
- `insightface/models/buffalo_l/*.onnx` - Face detection models
- `ffmpeg.exe`, `ffprobe.exe` - Video support
- `lang/*.json` - Translation files
- `config/*.json` - Configuration files

---

## Performance Notes

### First Launch
- Slower (~30-60 seconds) due to extraction
- Subsequent launches faster (~10-20 seconds)

### Memory Usage
- Base: ~200MB
- With face detection: ~500MB
- With large projects: ~1GB+

### Disk Space
- Executable: ~400MB (compressed)
- Temp extraction: ~800MB
- User data: Varies by project size

---

## Version History

### v3.0.2 (2025-12-18)
- ✅ Added accordion sidebar support
- ✅ Added face crop editor and quality dashboard
- ✅ Fixed missing UI modules
- ✅ Updated layout modules
- ✅ Added db_writer module
- ✅ Enhanced video editor support

---

## Support

### Build Issues
- Check PyInstaller documentation: https://pyinstaller.org
- Review build log for specific errors
- Verify all prerequisites installed

### Runtime Issues
- Enable console window to see error messages
- Check Windows Event Viewer for crash details
- Test individual features to isolate problems

---

## Advanced: Build Optimization

### Reduce Size Further
1. **Exclude test modules:**
   ```python
   excludes=['pytest', 'tests', 'IPython', 'jupyter']
   ```

2. **Remove unused backends:**
   ```python
   excludes=['matplotlib.backends.backend_qt*']
   ```

3. **One-folder mode** (faster startup, larger distribution):
   ```python
   # Comment out exe = EXE(... a.binaries, a.zipfiles, a.datas)
   # Uncomment COLLECT section at end of spec file
   ```

### Multi-threading Builds
PyInstaller doesn't support parallel builds, but you can:
- Build on SSD for faster I/O
- Close other applications to free RAM
- Use `--clean` flag to clear cache

---

## Notes

1. **Antivirus False Positives**: Some AV software flags PyInstaller .exes as suspicious. This is normal. You may need to:
   - Sign the executable with a code signing certificate
   - Submit to AV vendors for whitelisting
   - Provide users with instructions to allow

2. **Windows Defender**: May quarantine on first run. Whitelist the .exe or sign it.

3. **Updates**: To update the app, rebuild with new code and redistribute the new .exe.

4. **User Data**: User databases and settings are stored in:
   ```
   %USERPROFILE%\.memorymate\
   ```
   These persist across app updates.

---

## Build Command Summary

```bash
# Standard build
pyinstaller memorymate_pyinstaller.spec

# Clean build (recommended for major changes)
pyinstaller --clean memorymate_pyinstaller.spec

# Verbose output (for debugging)
pyinstaller --log-level DEBUG memorymate_pyinstaller.spec
```

---

**Status:** ✅ Spec file updated and ready for building

**Last Updated:** 2025-12-18

**Build Ready:** YES - All modules included, dependencies verified
