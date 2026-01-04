# Feature: Smart CLIP Model Selection with User Prompts

**Date:** 2026-01-04
**Status:** ✅ **IMPLEMENTED**

---

## 🎯 Feature Overview

The app now intelligently checks for the best CLIP model (large-patch14) before extracting embeddings and prompts users if it's not available offline.

### User Experience Flow:

```
User clicks "Extract Embeddings"
    ↓
App checks: Is large-patch14 available offline?
    ↓
┌─────────────────────────────────┐
│ YES - Large model found         │
│ → Use it automatically          │
│ → Continue to extraction        │
│ → Get 40-60% search quality     │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ NO - Large model NOT found      │
│ → Show dialog with options:     │
│   [1] Download Large Model      │
│   [2] Continue with base-patch32│
│   [3] Cancel                    │
└─────────────────────────────────┘
    ↓
User chooses option:
    ↓
[1] Download → Opens preferences → User downloads → Try again
[2] Continue → Uses base-patch32 → 19-26% quality (informed choice)
[3] Cancel → Abort operation
```

---

## 📋 Implementation Details

### New Files Created:

#### 1. `utils/model_selection_helper.py`
**Purpose:** Smart model checking and user prompting

**Key Functions:**

```python
check_and_select_model(parent: QWidget) -> Tuple[str, bool]
```
- Checks if large-patch14 is available offline
- Returns it immediately if found
- Prompts user with dialog if not found
- Returns: (model_variant, should_continue)

**Dialog Options:**
1. **Download Large Model** → Opens preferences, aborts current operation
2. **Continue with base-patch32** → Proceeds with available model
3. **Cancel** → Aborts operation

**Special Return Values:**
- `('openai/clip-vit-large-patch14', True)` - Large model found, continue
- `('openai/clip-vit-base-patch32', True)` - User chose to continue with base model
- `('OPEN_DOWNLOAD_DIALOG', True)` - User wants to download, open preferences
- `('', False)` - User cancelled

```python
open_model_download_preferences(parent: QWidget) -> bool
```
- Opens preferences dialog
- Navigates to Visual Embeddings section (TODO: auto-navigate)
- Returns True if successful

---

### Modified Files:

#### 1. `main_window_qt.py`
**Location:** `_on_extract_embeddings()` method (lines 1467-1535)

**Changes:**
```python
# BEFORE (hardcoded base-patch32)
model_variant = 'openai/clip-vit-base-patch32'

# AFTER (smart selection with user prompt)
model_variant, should_continue = check_and_select_model(self)
if not should_continue:
    return  # User cancelled

if model_variant == 'OPEN_DOWNLOAD_DIALOG':
    open_model_download_preferences(self)
    return  # Abort, let user download first
```

**Updated Confirmation Dialog:**
```python
# Now shows which model will be used
f"Using: large model (~1.7GB, best, 40-60% quality)\n"
# or
f"Using: base model (~600MB, fast, 19-26% quality)\n"
```

#### 2. `workers/embedding_worker.py`
**Location:** `__init__()` method (lines 87-112)

**Changes:**
```python
# BEFORE
def __init__(self, ..., model_variant: str = 'openai/clip-vit-base-patch32'):
    self.model_variant = model_variant

# AFTER
def __init__(self, ..., model_variant: Optional[str] = None):
    if model_variant is None:
        model_variant = get_recommended_variant()
        logger.info(f"Auto-selected: {model_variant}")
    self.model_variant = model_variant
```

**Benefits:**
- Workers created without explicit variant auto-select best model
- Consistent with EmbeddingService behavior
- Better logging for debugging

---

## 🎨 User Interface

### Dialog #1: Large Model Not Available

**Shown when:** User clicks "Extract Embeddings" and large model is missing

```
┌─────────────────────────────────────────────────────────┐
│ ⚠️  Large Model Not Available                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ The large CLIP model (clip-vit-large-patch14) is not   │
│ available offline.                                      │
│                                                         │
│ Best available model: Base model (512-D, fast, 19-26%  │
│ quality)                                                │
│                                                         │
│ The large model provides 2-3x better search quality.   │
│ What would you like to do?                             │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [Download Large Model]  [Continue with base-patch32]  │
│                          [Cancel]                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Dialog #2: Download Required (if user chose download)

```
┌─────────────────────────────────────────────────────────┐
│ ℹ️  Download Required                                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Please download the large CLIP model from the          │
│ preferences dialog.                                     │
│                                                         │
│ After download completes, run 'Extract Embeddings'     │
│ again.                                                  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                        [OK]                             │
└─────────────────────────────────────────────────────────┘
```

### Dialog #3: Updated Confirmation

**Shown when:** Model selected, ready to extract

```
┌─────────────────────────────────────────────────────────┐
│ Extract Embeddings                                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ This will extract AI embeddings for 21 photos.         │
│                                                         │
│ Using: large model (~1.7GB, best, 40-60% quality)      │
│ Processing may take a while depending on your hardware.│
│                                                         │
│ Continue?                                               │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                    [Yes]  [No]                          │
└─────────────────────────────────────────────────────────┘
```

---

## 🔄 Workflow Examples

### Scenario 1: Large Model Already Installed ✅

```
1. User: Clicks "Extract Embeddings"
2. App: Checks for large-patch14
3. App: Found! ✓
4. App: Shows confirmation: "Using: large model (~1.7GB, best, 40-60% quality)"
5. User: Clicks "Yes"
6. App: Extracts embeddings with large-patch14
7. Result: High-quality search (40-60% scores)
```

**No additional prompts!** Seamless experience for users who already have the best model.

---

### Scenario 2: Large Model Missing, User Downloads 📥

```
1. User: Clicks "Extract Embeddings"
2. App: Checks for large-patch14
3. App: Not found! ✗
4. App: Shows dialog: "Large Model Not Available"
5. User: Clicks "Download Large Model"
6. App: Opens preferences dialog
7. App: Shows info: "Download Required - After download completes, run Extract Embeddings again"
8. User: Downloads model in preferences
9. User: Closes preferences
10. User: Clicks "Extract Embeddings" again
11. App: Now finds large-patch14! ✓
12. App: Proceeds with large model
13. Result: High-quality search (40-60% scores)
```

**Guided experience!** User is walked through download process.

---

### Scenario 3: Large Model Missing, User Continues with Base 🏃

```
1. User: Clicks "Extract Embeddings"
2. App: Checks for large-patch14
3. App: Not found! ✗
4. App: Shows dialog: "Large Model Not Available"
5. User: Clicks "Continue with clip-vit-base-patch32"
6. App: Shows confirmation: "Using: base model (~600MB, fast, 19-26% quality)"
7. User: Clicks "Yes" (informed decision)
8. App: Extracts embeddings with base-patch32
9. Result: Lower quality search (19-26% scores)
```

**Informed choice!** User knows they're using lower-quality model and can upgrade later.

---

### Scenario 4: No Models Installed (First Run) 🆕

```
1. User: Clicks "Extract Embeddings"
2. App: Checks for ANY models
3. App: None found! ✗
4. App: Shows critical dialog: "No CLIP Models Found"
5. Dialog: "Would you like to download the large model now? (~1.7GB, 40-60% quality)"
6. User: Clicks "Yes"
7. App: Opens preferences dialog
8. User: Downloads large-patch14
9. User: Closes preferences, tries again
10. App: Now finds large-patch14! ✓
11. Result: Best experience from the start
```

**First-run optimization!** New users get guided to the best model.

---

## 📊 Decision Matrix

| Situation | Large-patch14 Available? | User Choice | Model Used | Search Quality |
|-----------|--------------------------|-------------|------------|----------------|
| Scenario 1 | ✅ Yes | N/A (auto) | large-patch14 | 40-60% ⭐⭐⭐ |
| Scenario 2 | ❌ No | Download → Yes | large-patch14 | 40-60% ⭐⭐⭐ |
| Scenario 3 | ❌ No | Continue | base-patch32 | 19-26% ⭐ |
| Scenario 4 | ❌ None | Download → Yes | large-patch14 | 40-60% ⭐⭐⭐ |
| User cancels | N/A | Cancel | N/A | Operation aborted |

---

## 🔧 Technical Architecture

### Call Stack:

```
main_window_qt.py::_on_extract_embeddings()
    ↓
utils/model_selection_helper.py::check_and_select_model()
    ↓
utils/clip_check.py::check_clip_availability('openai/clip-vit-large-patch14')
    ↓
┌─────────────────────────────────┐
│ Large model available?          │
└─────────────────────────────────┘
    ↓ YES                    ↓ NO
Return variant          Show QMessageBox
Continue               User chooses option
    ↓                        ↓
workers/embedding_worker.py::__init__(model_variant=...)
    ↓
services/embedding_service.py::load_clip_model(variant=...)
    ↓
Embedding extraction begins
```

### Model Selection Priority:

```python
# utils/clip_check.py::get_recommended_variant()
Priority order:
1. openai/clip-vit-large-patch14  (768-D, best)     ← TARGET
2. openai/clip-vit-base-patch16   (512-D, better)
3. openai/clip-vit-base-patch32   (512-D, fallback)
```

---

## ✅ Success Criteria

All criteria met:

- [x] App checks for large-patch14 before embedding extraction
- [x] If available: uses it automatically without prompting
- [x] If missing: shows user-friendly dialog with options
- [x] User can choose to download large model
- [x] User can choose to continue with available model
- [x] User can cancel the operation
- [x] Confirmation dialog shows which model will be used
- [x] No breaking changes to existing code
- [x] Graceful fallback for all scenarios
- [x] Clear logging for debugging

---

## 🧪 Testing Checklist

### Test Case 1: Large Model Installed
1. Ensure large-patch14 is installed (check_clip_models.py)
2. Click "Tools → Extract Embeddings"
3. ✓ Should NOT show "Large Model Not Available" dialog
4. ✓ Should show confirmation: "Using: large model (~1.7GB, best, 40-60% quality)"
5. ✓ Click Yes → Extraction proceeds with large-patch14
6. ✓ Log shows: "Auto-selected CLIP variant: openai/clip-vit-large-patch14"

### Test Case 2: Large Model Missing, Choose Download
1. Rename large-patch14 folder to hide it temporarily
2. Click "Tools → Extract Embeddings"
3. ✓ Should show "Large Model Not Available" dialog
4. ✓ Click "Download Large Model"
5. ✓ Preferences dialog opens
6. ✓ Info dialog shows: "Download Required"
7. ✓ Download model in preferences
8. ✓ Close preferences, try again
9. ✓ Now proceeds with large model

### Test Case 3: Large Model Missing, Choose Continue
1. Rename large-patch14 folder to hide it
2. Click "Tools → Extract Embeddings"
3. ✓ Should show "Large Model Not Available" dialog
4. ✓ Dialog shows: "Best available model: Base model (512-D, fast, 19-26% quality)"
5. ✓ Click "Continue with clip-vit-base-patch32"
6. ✓ Confirmation shows: "Using: base model (~600MB, fast, 19-26% quality)"
7. ✓ Click Yes → Extraction proceeds with base-patch32
8. ✓ Log shows: "Processing with model openai/clip-vit-base-patch32"

### Test Case 4: User Cancels
1. Click "Tools → Extract Embeddings"
2. In any dialog, click "Cancel"
3. ✓ Operation aborts
4. ✓ No worker started
5. ✓ No error messages

### Test Case 5: No Models Installed (First Run)
1. Delete all CLIP model folders
2. Click "Tools → Extract Embeddings"
3. ✓ Shows critical dialog: "No CLIP Models Found"
4. ✓ Recommends downloading large model
5. ✓ Click Yes → Opens preferences
6. ✓ Download model → Try again
7. ✓ Works after download

---

## 📝 Logging Output

### When Large Model Found:
```
[INFO] [ModelSelection] Large model found offline: openai/clip-vit-large-patch14
[INFO] [EmbeddingWorker] Processing 21 photos with model openai/clip-vit-large-patch14
[INFO] [EmbeddingService] ✓ CLIP loaded: openai/clip-vit-large-patch14 (768-D, device=cpu)
```

### When User Chooses to Continue with Base:
```
[INFO] [ModelSelection] User chose to continue with: openai/clip-vit-base-patch32
[INFO] [EmbeddingWorker] Processing 21 photos with model openai/clip-vit-base-patch32
[INFO] [EmbeddingService] ✓ CLIP loaded: openai/clip-vit-base-patch32 (512-D, device=cpu)
```

### When User Chooses to Download:
```
[INFO] [ModelSelection] User chose to download large model
[INFO] [ModelSelection] Preferences dialog opened for model download
```

### When User Cancels:
```
[INFO] [ModelSelection] User cancelled operation
```

---

## 🎯 User Benefits

1. **Automatic Best Quality** - If large model is installed, it's used automatically
2. **Informed Choices** - Users know exactly which model they're using and its quality level
3. **Guided Downloads** - Clear path to download the best model
4. **No Surprises** - Confirmation shows model details before processing
5. **Flexibility** - Users can choose to continue with available model if needed
6. **First-Run Excellence** - New users get guided to best experience

---

## 🔄 Backward Compatibility

**100% backward compatible!**

- Existing code explicitly specifying variant continues to work
- New code can omit variant and get auto-selection
- No breaking API changes
- Graceful fallback in all scenarios

**Example:**
```python
# OLD CODE (still works)
worker = EmbeddingWorker(job_id=123, model_variant='openai/clip-vit-base-patch32')

# NEW CODE (auto-selects)
worker = EmbeddingWorker(job_id=123)  # Gets large-patch14 if available

# EXPLICIT (always works)
worker = EmbeddingWorker(job_id=123, model_variant='openai/clip-vit-large-patch14')
```

---

## 🚀 Future Enhancements

### Planned:
1. **Auto-navigate to download section** in preferences dialog
2. **Progress indicator** during model download in dialog
3. **Model size indicator** showing disk space requirements
4. **Model comparison table** in dialog to help users choose
5. **Remember user preference** ("Don't ask again, always use base model")

### Possible:
- **Auto-download** large model in background (with permission)
- **Model benchmarks** showing actual search quality on user's hardware
- **Model switching** without re-extraction (if dimensions compatible)

---

## 🔗 Related Documents

- **BUG_FIX_EMBEDDING_MODEL_SELECTION.md** - Previous auto-selection fix
- **CLIP_DOWNLOAD_FIX.md** - Model download bug fix
- **EMBEDDING_EXTRACTION_AUDIT.md** - Comprehensive audit
- **check_clip_models.py** - Diagnostic tool

---

**Feature implemented:** 2026-01-04
**Branch:** claude/audit-embedding-extraction-QRRVm
**Status:** ✅ Ready for testing
