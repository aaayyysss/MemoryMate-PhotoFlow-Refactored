# Merge Conflict Resolution Guide

**PR #83:** CRITICAL FIX: Variable name collision destroying video count

---

## ⚠️ Conflict Detected

**File:** `services/photo_scan_service.py`
**Location:** Line 491-496 (around line 476 in original code)

---

## 🔍 What Caused the Conflict?

Both branches independently fixed the **same bug** (IMAGE_EXTENSIONS) but with different comments:

### **Main Branch (HEAD):**
```python
# FIX: Only discover IMAGE files, not videos
if ext in self.IMAGE_EXTENSIONS:
```

### **Feature Branch (claude/audit-face-detection-fixes):**
```python
if ext in self.IMAGE_EXTENSIONS:  # CRITICAL FIX: Use IMAGE_EXTENSIONS, not SUPPORTED_EXTENSIONS
```

---

## ✅ Resolution Strategy

**Keep BOTH comments for maximum clarity:**

```python
# CRITICAL FIX: Use IMAGE_EXTENSIONS, not SUPPORTED_EXTENSIONS
# Only discover IMAGE files, not videos (prevents double-counting)
if ext in self.IMAGE_EXTENSIONS:
```

---

## 📋 Step-by-Step Merge Instructions

### **Option 1: Merge via GitHub UI**

1. Go to PR #83 on GitHub
2. Click "Resolve conflicts" button
3. In the conflict editor, replace the conflicted section with:
   ```python
   # CRITICAL FIX: Use IMAGE_EXTENSIONS, not SUPPORTED_EXTENSIONS
   # Only discover IMAGE files, not videos (prevents double-counting)
   if ext in self.IMAGE_EXTENSIONS:
   ```
4. Click "Mark as resolved"
5. Click "Commit merge"
6. Merge the PR

### **Option 2: Merge via Command Line**

```bash
# Switch to main branch
git checkout main
git pull origin main

# Merge feature branch
git merge claude/audit-face-detection-fixes-017b511yX8FznoEy9cGus3eF

# Resolve conflict manually
# Edit services/photo_scan_service.py around line 491
# Replace conflict markers with resolved code above

# Complete merge
git add services/photo_scan_service.py
git commit -m "Merge PR #83: CRITICAL FIX for video scanning bug"
git push origin main
```

---

## 🎯 Why This Conflict is Safe to Resolve

1. **Both fixes are identical** - only comments differ
2. **No functional code changes conflict** - just documentation improvements
3. **Combined comments provide better context** for future developers
4. **The bug fix itself is preserved** in both versions

---

## ✅ After Merge Checklist

Once merged, verify:

- [ ] `services/photo_scan_service.py` has no conflict markers
- [ ] Line 349 uses `indexed_videos` (not `total_videos`)
- [ ] Line 476 uses `IMAGE_EXTENSIONS` (not `SUPPORTED_EXTENSIONS`)
- [ ] Comments clearly explain both fixes
- [ ] Tests pass (run video scan with 14 videos)

---

## 🚀 What Gets Fixed After Merge

### **Fix #1: Variable Overwrite Bug (Line 349)**
```python
# BEFORE (❌):
total_videos = self._stats['videos_indexed']  # Overwrites discovery count!

# AFTER (✅):
indexed_videos = self._stats['videos_indexed']  # Different variable name
```

### **Fix #2: Extension Filter Bug (Line 476)**
```python
# BEFORE (❌):
if ext in self.SUPPORTED_EXTENSIONS:  # Includes videos!

# AFTER (✅):
if ext in self.IMAGE_EXTENSIONS:  # Only images
```

---

## 📊 Expected Results After Merge

**Before Fix:**
- ❌ "Discovered 14 videos" → `total_videos=0` → No videos processed
- ❌ Video section shows "0 videos"

**After Fix:**
- ✅ "Discovered 14 videos" → `total_videos=14` → Videos processed
- ✅ Video section shows "14 videos"
- ✅ Videos appear with thumbnails

---

**Resolution Status:** ✅ Conflict identified and resolution documented
**Merge Safety:** ✅ Safe to merge - non-conflicting functional changes
**Testing Required:** ✅ Yes - test video scanning after merge
