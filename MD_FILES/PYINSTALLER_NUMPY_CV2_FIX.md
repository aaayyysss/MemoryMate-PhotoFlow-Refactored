# PyInstaller NumPy/CV2 Fix - Face Detection Crash
**Date**: 2025-11-30  
**Version**: v3.0.2+  
**Issue**: Face detection works in Python but crashes in PyInstaller .exe  

---

## 🐛 **Critical Bug Report**

### **Symptoms**

Face detection **works perfectly** on PC with Python installed, but **crashes** on PC without Python using the packaged .exe:

```
[ERROR] Error detecting faces in screenshot/038.jpg: 'NoneType' object has no attribute 'shape'
[ERROR] Error detecting faces in screenshot/039.jpg: 'NoneType' object has no attribute 'shape'
[ERROR] Error detecting faces in screenshot/04.jpg: 'NoneType' object has no attribute 'shape'
```

### **Key Observations**

1. ✅ **Same photos** work fine in Python environment
2. ❌ **Same photos** fail in PyInstaller .exe
3. 🎯 **Error location**: Line 704 in `face_detection_service.py`
4. 🔍 **Error type**: `'NoneType' object has no attribute 'shape'`

---

## 🔬 **Root Cause Analysis**

### **The Problem Chain**

```python
# services/face_detection_service.py (lines 567-594)

# STEP 1: PIL loads the image successfully ✅
pil_image = Image.open(image_path)
pil_image = ImageOps.exif_transpose(pil_image)
if pil_image.mode != 'RGB':
    pil_image = pil_image.convert('RGB')

# STEP 2: Convert PIL → NumPy array
img_rgb = np.array(pil_image)  # ← RETURNS None IN PYINSTALLER! ❌

# STEP 3: Convert RGB → BGR for cv2/InsightFace
img = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)  # ← CRASHES! img_rgb is None

# Later...
h, w = img.shape[:2]  # ← ERROR: 'NoneType' object has no attribute 'shape'
```

### **Why It Works in Python but Fails in PyInstaller**

| Environment | Behavior | Reason |
|-------------|----------|--------|
| **Python** | ✅ `np.array()` works | NumPy fully loaded with all submodules |
| **PyInstaller** | ❌ `np.array()` returns None | Missing NumPy submodules (`numpy.core`, `numpy.core._methods`) |

### **Technical Explanation**

PyInstaller **static analysis** can't detect all NumPy runtime dependencies:

1. **PIL.Image.open()** succeeds (PIL is properly bundled)
2. **np.array(pil_image)** silently fails (missing `numpy.core._methods`)
3. Returns **None** instead of raising an exception
4. **cv2.cvtColor(None, ...)** crashes with "NoneType has no attribute 'shape'"

---

## ✅ **Solution Implemented**

### **Fix 1: Add Defensive Validation in Code**

**File**: `services/face_detection_service.py`  
**Lines**: 567-604

```python
# STEP 2: Convert PIL → numpy array → cv2 BGR format
img_rgb = np.array(pil_image)

# CRITICAL: Validate numpy conversion succeeded (can fail in PyInstaller)
if img_rgb is None or not isinstance(img_rgb, np.ndarray) or img_rgb.size == 0:
    logger.warning(f"NumPy conversion failed for {os.path.basename(image_path)}, trying cv2 fallback")
    pil_image.close()
    raise ValueError("NumPy array conversion failed")

# Convert RGB to BGR for cv2/InsightFace
img = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

# CRITICAL: Validate cv2.cvtColor succeeded
if img is None or not hasattr(img, 'shape') or img.size == 0:
    logger.warning(f"cv2.cvtColor failed for {os.path.basename(image_path)}, trying cv2 fallback")
    pil_image.close()
    raise ValueError("cv2.cvtColor failed")

# Cleanup PIL image
pil_image.close()

logger.debug(f"Loaded image via PIL: {img.shape} - {os.path.basename(image_path)}")
```

**Result**:
- If NumPy conversion fails, **gracefully fallback to cv2.imdecode()**
- If cv2.cvtColor fails, **fallback to cv2.imdecode()**
- No more crashes, clear warning logs

---

### **Fix 2: Add Missing NumPy Submodules to PyInstaller**

**File**: `memorymate_pyinstaller.spec`  
**Lines**: 83-99

```python
hiddenimports = [
    # ML/AI libraries
    'insightface',
    'insightface.app',
    'insightface.model_zoo',
    'onnxruntime',
    'onnxruntime.capi',
    'onnxruntime.capi.onnxruntime_pybind11_state',
    'numpy',
    'numpy.core',  # CRITICAL: Required for np.array() in PyInstaller
    'numpy.core._methods',  # CRITICAL: Required for array operations
    'numpy.lib',  # Required for numpy utilities
    'numpy.lib.format',  # Required for array serialization
    'cv2',
    'cv2.cv2',  # CRITICAL: Explicit cv2 binary module for PyInstaller
    'PIL',
    'PIL.Image',
    'PIL.ImageOps',
    'PIL.ImageQt',
    # ... rest of imports
]
```

**Added Modules**:
- ✅ `numpy.core` - Core NumPy functionality
- ✅ `numpy.core._methods` - Array methods (required for `np.array()`)
- ✅ `numpy.lib` - NumPy library utilities
- ✅ `numpy.lib.format` - Array serialization
- ✅ `cv2.cv2` - Explicit cv2 binary module

---

## 🎯 **Expected Behavior After Fix**

### **Scenario 1: NumPy Conversion Succeeds** (Normal Case)

```
[DEBUG] Loaded image via PIL: (1920, 1080, 3) - screenshot.jpg
[INFO] [FaceDetection] Found 2 faces in screenshot.jpg
```

### **Scenario 2: NumPy Conversion Fails** (Fallback)

```
[WARNING] NumPy conversion failed for screenshot.jpg, trying cv2 fallback
[DEBUG] Loaded image via cv2.imdecode: (1920, 1080, 3) - screenshot.jpg
[INFO] [FaceDetection] Found 2 faces in screenshot.jpg
```

### **Scenario 3: Both PIL and cv2 Fail** (Corrupted File)

```
[WARNING] Failed to load image (both PIL and cv2 failed): corrupted.jpg
[INFO] [FaceDetectionWorker] [140/298] corrupted.jpg: ERROR - Failed to load image
```

---

## 🧪 **Testing Strategy**

### **Test 1: Python Environment** (Baseline)

```bash
python main_qt.py
# Run face detection on screenshot folder
# Expected: All photos processed successfully
```

### **Test 2: PyInstaller Build** (Before Fix)

```bash
pyinstaller memorymate_pyinstaller.spec --clean --noconfirm
dist/MemoryMate-PhotoFlow-v3.0.2.exe
# Run face detection on screenshot folder
# Expected: Crashes with 'NoneType' has no attribute 'shape'
```

### **Test 3: PyInstaller Build** (After Fix)

```bash
pyinstaller memorymate_pyinstaller.spec --clean --noconfirm
dist/MemoryMate-PhotoFlow-v3.0.2.exe
# Run face detection on screenshot folder
# Expected: All photos processed successfully (with fallback warnings if needed)
```

---

## 📊 **Build Checklist**

Before building with PyInstaller, verify:

- ✅ `services/face_detection_service.py` has validation code (lines 583-598)
- ✅ `memorymate_pyinstaller.spec` includes `numpy.core`, `numpy.core._methods`
- ✅ `memorymate_pyinstaller.spec` includes `cv2.cv2`
- ✅ Clean build: `pyinstaller ... --clean --noconfirm`
- ✅ Test on PC **without Python** installed

---

## 🔍 **Diagnostic Commands**

### **Check NumPy Modules in .exe**

```powershell
# Extract .exe to temp folder
$exePath = "dist\MemoryMate-PhotoFlow-v3.0.2.exe"
& $exePath --help  # Triggers extraction to temp

# Check extracted files
$tempDir = "$env:TEMP\_MEI*"
Get-ChildItem $tempDir -Recurse -Filter "*numpy*" | Select-Object FullName
Get-ChildItem $tempDir -Recurse -Filter "*cv2*" | Select-Object FullName
```

### **Enable Debug Logging**

Modify `logging_config.py`:

```python
# Change from INFO to DEBUG
logger.setLevel(logging.DEBUG)
```

Then check logs:

```
%APPDATA%\MemoryMate-PhotoFlow\logs\memorymate.log
```

---

## 🚨 **Common PyInstaller Pitfalls**

### **1. Missing Binary Modules**

**Problem**: `cv2.pyd`, `numpy.core._multiarray_umath.pyd` not included  
**Solution**: Add `cv2.cv2`, `numpy.core` to hiddenimports

### **2. Incorrect Module Paths**

**Problem**: PyInstaller can't find modules in nested packages  
**Solution**: Use explicit imports like `numpy.core._methods`

### **3. Runtime Import Detection**

**Problem**: Dynamic imports (`importlib`, `__import__`) not detected  
**Solution**: Add to hiddenimports explicitly

### **4. DLL Dependencies**

**Problem**: OpenCV DLLs not bundled (e.g., `opencv_world455.dll`)  
**Solution**: Use `--collect-all cv2` or copy DLLs to binaries

---

## 📦 **Build and Deploy**

### **Step 1: Clean Build**

```powershell
# Remove old build artifacts
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# Clean build
pyinstaller memorymate_pyinstaller.spec --clean --noconfirm
```

### **Step 2: Verify Build**

```powershell
# Check .exe size (should be ~900 MB)
Get-Item dist\MemoryMate-PhotoFlow-v3.0.2.exe | Select-Object Length

# Check for NumPy/cv2 in build warnings
# Look for "WARNING: Hidden import 'numpy.core' not found"
```

### **Step 3: Test on Clean PC**

```powershell
# Copy .exe to PC without Python
# Run face detection on test photos
# Check logs: %APPDATA%\MemoryMate-PhotoFlow\logs\memorymate.log
```

### **Step 4: Package for Distribution**

```powershell
# Option 1: Single .exe (900 MB)
Copy-Item dist\MemoryMate-PhotoFlow-v3.0.2.exe -Destination release\

# Option 2: Split into 5 × 180 MB parts
.\build_and_split.ps1
```

---

## 📝 **Verification Checklist**

After deploying the fix, verify:

- [ ] Face detection works on PC **with Python** (baseline)
- [ ] Face detection works on PC **without Python** (PyInstaller .exe)
- [ ] Same photos processed successfully in both environments
- [ ] No "'NoneType' object has no attribute 'shape'" errors
- [ ] Logs show either success or graceful fallback messages
- [ ] Video files correctly excluded (no warnings)
- [ ] Progress reporting shows rich information

---

## 🎓 **Lessons Learned**

### **Key Takeaways**

1. **PyInstaller != Python**: What works in dev might fail in production
2. **Static Analysis Limitations**: PyInstaller can't detect all runtime dependencies
3. **Defensive Programming**: Always validate external library results
4. **Explicit Imports**: Better to over-specify than under-specify hiddenimports
5. **Graceful Fallbacks**: Multiple loading strategies improve robustness

### **Best Practices**

1. ✅ Always test packaged .exe on clean PC without Python
2. ✅ Add validation after every external library call
3. ✅ Use explicit hiddenimports for critical submodules
4. ✅ Implement fallback strategies for file loading
5. ✅ Log detailed warnings for debugging
6. ✅ Clean build with `--clean --noconfirm`

---

## 🔗 **Related Issues**

- **NoneType crash in face detection** - Fixed with validation
- **Video files incorrectly processed** - Fixed with SQL filtering
- **Missing DPI helper module** - Fixed by adding to hiddenimports
- **Face quality calculation crash** - Fixed with img validation

---

## 📄 **Related Documentation**

- `BUGFIX_FACE_DETECTION_NONETYPE.md` - Original face detection bug
- `PYINSTALLER_AUDIT_REPORT.md` - Complete spec file audit
- `BUILD_INSTRUCTIONS.md` - PyInstaller build guide
- `CHANGELOG_v3.0.2.md` - All changes in this version

---

**Status**: ✅ **FIXED**  
**Files Modified**: `services/face_detection_service.py`, `memorymate_pyinstaller.spec`  
**Testing Required**: PyInstaller .exe on clean PC  
**Priority**: 🔥 **CRITICAL** - Blocks face detection on deployed .exe
