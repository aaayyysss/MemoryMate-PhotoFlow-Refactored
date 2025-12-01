# PyInstaller Face Detection Crash - Diagnostic Report
**Date**: 2025-11-30  
**Issue**: Face detection crashes on PC without Python (PyInstaller .exe)  
**Error**: `'NoneType' object has no attribute 'shape'`  
**Status**: 🔍 **DIAGNOSTIC MODE** - Added enhanced logging  

---

## 🚨 **Critical Finding from Debug Log**

### **ALL 69 Photos Failing with Same Error**

```
2025-11-30 23:39:41,829 [ERROR] Error detecting faces in screenshot/01.jpg: 'NoneType' object has no attribute 'shape'
2025-11-30 23:39:44,274 [ERROR] Error detecting faces in screenshot/017.jpg: 'NoneType' object has no attribute 'shape'
2025-11-30 23:39:44,464 [ERROR] Error detecting faces in screenshot/018.jpg: 'NoneType' object has no attribute 'shape'
... (69 total failures)
```

### **InsightFace Loaded Successfully**

```
✅ InsightFace (buffalo_l) loaded successfully with CPU acceleration (det_size=640x640)
[INFO] [FaceDetectionWorker] Processing 69 photos
```

### **What This Tells Us**

1. ✅ **InsightFace models ARE loaded** correctly
2. ✅ **Worker initialization** succeeds
3. ❌ **EVERY photo** fails with identical error
4. ❌ **NO** PIL fallback warnings → PIL loading succeeds
5. ❌ **NO** NumPy conversion warnings → np.array() succeeds
6. ❌ **NO** cv2 fallback warnings → cv2.cvtColor() succeeds

**Conclusion**: The crash happens **AFTER** image loading, likely during:
- Image dimension checks (`img.shape`)
- Image resizing operations
- InsightFace face detection
- Quality calculation

---

## 🎯 **Diagnostic Enhancements Added**

### **1. Enhanced Exception Logging** (Line 712-719)

Added full stack trace logging to identify exact crash location:

```python
except Exception as e:
    # Enhanced error logging with stack trace for PyInstaller debugging
    import traceback
    error_traceback = traceback.format_exc()
    logger.error(f"Error detecting faces in {image_path}: {e}")
    logger.error(f"Full traceback:\n{error_traceback}")
    return []
```

**Expected Output**: Will show **exact line number** where crash occurs

---

### **2. InsightFace Error Handling** (Line 658-666)

Wrapped `self.app.get(img)` with try/except to catch InsightFace failures:

```python
try:
    detected_faces = self.app.get(img)
    logger.debug(f"InsightFace returned {len(detected_faces) if detected_faces else 0} faces for {os.path.basename(image_path)}")
except Exception as insightface_error:
    logger.error(f"InsightFace.get() failed for {os.path.basename(image_path)}: {insightface_error}")
    import traceback
    logger.error(f"InsightFace traceback:\n{traceback.format_exc()}")
    return []
```

**Expected Output**: Will show if InsightFace itself is crashing

---

### **3. Critical Image Validation** (Line 631-650)

Added exhaustive validation **before** accessing `img.shape`:

```python
# CRITICAL VALIDATION: Ensure img is valid before ANY operations
if img is None:
    logger.error(f"CRITICAL: img became None after PIL/cv2 loading for {os.path.basename(image_path)}")
    return []

if not isinstance(img, np.ndarray):
    logger.error(f"CRITICAL: img is not a numpy array (type: {type(img)}) for {os.path.basename(image_path)}")
    return []

if not hasattr(img, 'shape'):
    logger.error(f"CRITICAL: img has no 'shape' attribute for {os.path.basename(image_path)}")
    return []

if img.size == 0:
    logger.error(f"CRITICAL: img.size is 0 for {os.path.basename(image_path)}")
    return []

try:
    max_dim = max(img.shape[0], img.shape[1])
    logger.debug(f"Image dimensions: {img.shape}, max_dim={max_dim} for {os.path.basename(image_path)}")
    # ... resize logic
except Exception as resize_error:
    logger.error(f"Failed to resize {image_path}: {resize_error}")
    import traceback
    logger.error(f"Resize error traceback:\n{traceback.format_exc()}")
    img = original_img
```

**Expected Output**: Will pinpoint if `img` is None, wrong type, or missing shape attribute

---

## 🔬 **Hypothesis: Why ALL Photos Fail**

Given that **100% of photos** fail with the **identical error**, the issue is likely:

### **Hypothesis 1: NumPy/cv2 Import Failure** ❌

**Unlikely** - InsightFace loaded successfully (requires NumPy/cv2)

### **Hypothesis 2: Image Loading Always Returns None** ❌

**Unlikely** - No "PIL failed" or "cv2 fallback" warnings

### **Hypothesis 3: np.array() Returns Non-Array Object** ⚠️

**POSSIBLE** - In PyInstaller, `np.array()` might return a different type

### **Hypothesis 4: img.shape Access Fails** ⭐ **MOST LIKELY**

**Likely** - The crash happens at:
```python
max_dim = max(img.shape[0], img.shape[1])  # Line 636
```

If `img` is a valid array but `img.shape` is somehow None or inaccessible in PyInstaller.

### **Hypothesis 5: InsightFace.get() Crashes** ⚠️

**POSSIBLE** - InsightFace might crash when processing the image array

---

## 📋 **Next Steps - REBUILD AND TEST**

### **Step 1: Rebuild .exe with Enhanced Logging**

```powershell
# Clean build
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# Rebuild with diagnostic logging
pyinstaller memorymate_pyinstaller.spec --clean --noconfirm
```

### **Step 2: Test on Other PC**

```powershell
# Copy new .exe to other PC
Copy-Item dist\MemoryMate-PhotoFlow-v3.0.2.exe -Destination \\OtherPC\SharedFolder\

# Run face detection on 1-2 photos
# Check logs at: %APPDATA%\MemoryMate-PhotoFlow\logs\memorymate.log
```

### **Step 3: Analyze New Log Output**

Look for these new messages:

```
# CRITICAL validation errors (will pinpoint img type issue)
[ERROR] CRITICAL: img became None after PIL/cv2 loading
[ERROR] CRITICAL: img is not a numpy array (type: <class 'XXX'>)
[ERROR] CRITICAL: img has no 'shape' attribute
[ERROR] CRITICAL: img.size is 0

# Image dimension logging (will show if shape access works)
[DEBUG] Image dimensions: (1920, 1080, 3), max_dim=1920

# InsightFace failure (will show if detection crashes)
[ERROR] InsightFace.get() failed: XXXX
[ERROR] InsightFace traceback: YYYY

# Full stack trace (will show exact crash line)
[ERROR] Full traceback:
  File "services/face_detection_service.py", line XXX, in detect_faces
    ...
```

---

## 🎯 **Expected Diagnostic Results**

### **Scenario A: NumPy Array Conversion Fails**

```
[ERROR] CRITICAL: img is not a numpy array (type: <class 'NoneType'>)
```

**Fix**: Add fallback to cv2.imdecode() earlier in the pipeline

### **Scenario B: img.shape is None**

```
[ERROR] CRITICAL: img has no 'shape' attribute
```

**Fix**: NumPy version mismatch - verify NumPy bundled correctly

### **Scenario C: InsightFace Crashes**

```
[ERROR] InsightFace.get() failed: XXXX
[ERROR] InsightFace traceback: ...
```

**Fix**: InsightFace model files not loaded - check runtime hook

### **Scenario D: Resize Operation Crashes**

```
[ERROR] Failed to resize screenshot/01.jpg: XXXX
[ERROR] Resize error traceback: ...
```

**Fix**: cv2.resize() incompatible in PyInstaller - use alternative

---

## 🔧 **Potential Root Causes**

### **1. NumPy Version Mismatch**

**Issue**: PyInstaller bundles different NumPy version than development

**Symptoms**:
- `np.array()` returns None
- `img.shape` raises AttributeError
- Array operations fail silently

**Fix**:
```python
# Add explicit NumPy version pinning in requirements.txt
numpy==1.24.3  # Match exact version used in development
```

### **2. Missing NumPy Binary Extensions**

**Issue**: `.pyd` files for NumPy not bundled

**Symptoms**:
- NumPy imports succeed but operations fail
- Array creation returns None

**Fix**:
```python
# In spec file, add:
a = Analysis(
    ...
    binaries=[
        ('venv/Lib/site-packages/numpy/.libs/*.dll', 'numpy/.libs'),
    ],
)
```

### **3. OpenCV DLL Missing**

**Issue**: `opencv_world455.dll` or similar not bundled

**Symptoms**:
- cv2 imports succeed
- cv2.cvtColor() returns None
- cv2.resize() crashes

**Fix**:
```bash
# Collect all cv2 files
pyinstaller ... --collect-all cv2
```

### **4. InsightFace Model Loading Failure**

**Issue**: ONNX models not accessible at runtime

**Symptoms**:
- InsightFace.app.get() crashes
- Model files in wrong temp location

**Fix**: Verify `pyi_rth_insightface.py` runtime hook

---

## 📊 **Comparison: Working vs Failing**

| Aspect | Python Environment (✅ Works) | PyInstaller .exe (❌ Fails) |
|--------|-------------------------------|----------------------------|
| **InsightFace Load** | ✅ Success | ✅ Success |
| **PIL Image Load** | ✅ Success | ⚠️ Unknown (no warnings) |
| **np.array()** | ✅ Returns valid array | ⚠️ Unknown (suspected None) |
| **cv2.cvtColor()** | ✅ Returns valid array | ⚠️ Unknown (suspected None) |
| **img.shape** | ✅ Returns (H, W, 3) | ❌ **'NoneType' has no attribute 'shape'** |
| **Face Detection** | ✅ Finds faces | ❌ ALL photos fail |

---

## 📝 **Files Modified for Diagnostics**

1. **`services/face_detection_service.py`**
   - Line 631-650: Critical image validation
   - Line 658-666: InsightFace error handling
   - Line 712-719: Enhanced exception logging with traceback

2. **`memorymate_pyinstaller.spec`**
   - Line 90-94: Added NumPy submodules (`numpy.core`, `numpy.core._methods`, etc.)

---

## 🚀 **Action Required**

1. ✅ **Code changes complete** - Enhanced diagnostic logging added
2. ⏳ **Rebuild required** - Must rebuild .exe with new code
3. ⏳ **Test required** - Run on other PC and collect new logs
4. ⏳ **Analysis required** - Review new logs to identify root cause

---

## 📞 **Next Communication**

**Please provide**:
1. New log output from other PC after rebuilding .exe
2. Specifically look for lines containing:
   - `CRITICAL:`
   - `InsightFace.get() failed`
   - `Full traceback:`
   - `Image dimensions:`
   - `Resize error traceback:`

**With this information**, we can pinpoint the exact failure point and implement a targeted fix.

---

**Status**: 🔍 **DIAGNOSTIC MODE ACTIVE**  
**Priority**: 🔥 **CRITICAL**  
**Action**: Rebuild .exe and test with enhanced logging
