# Progress Dialog Behavior - User Guide

**Date:** 2025-12-11

---

## 📋 **IMPORTANT: When Does Progress Dialog Show?**

The progress dialog **ONLY shows during SCANNING**, not when loading existing database.

---

## ✅ **Progress Dialog WILL Show When:**

### **1. Scanning New Photos/Videos from Disk**
- Click **"Scan Repository"** button
- Toolbar → **Scan** action
- First-time scan of a folder
- Incremental scan (adding new files)

**Requirements:**
- Total files (photos + videos) > 20 threshold
- Example: 21 photos + 14 videos = 35 total ✅ (shows dialog)

**What You'll See:**
```
┌─────────────────────────────────┐
│  Scanning Photos                │
├─────────────────────────────────┤
│  Discovered 21 photos + 14      │
│  videos = 35 total files        │
│                                 │
│  📷 IMG_1234.jpg (2.5 MB)      │
│  Indexed: 15/35 photos          │
│  Committed: 150 rows            │
│                                 │
│  ▓▓▓▓▓▓▓░░░░░░░░  43%         │
│                                 │
│  [ Cancel ]                     │
└─────────────────────────────────┘
```

---

## ❌ **Progress Dialog WILL NOT Show When:**

### **1. Loading Existing Database**
- Opening app with existing database
- Switching between layouts (Current ↔ Google Photos)
- Filtering by folder/date/person
- Clicking on sidebar items
- Refreshing views

**Why:**
- No file system scan happening
- Just querying existing database
- No progress to track

**What You See Instead:**
- Status bar messages at bottom: "Loading 14 photos..."
- Smooth/instant loading (data already indexed)

### **2. Small Scans (Below Threshold)**
- Total files ≤ 20
- Example: 15 photos + 3 videos = 18 total ❌ (no dialog)

**Why:**
- Small scans complete quickly
- Dialog would flash too fast
- Status bar sufficient for < 20 files

**What You See Instead:**
- Status bar: "Scanning repository: /path/to/folder"
- Status bar: "Scan complete: 15 photos, 3 videos"

---

## 🔧 **How Progress Dialog Works**

### **Threshold Calculation:**
```python
total_files = photos_found + videos_found
if total_files > 20:  # Show dialog
    show_progress_dialog()
else:  # Use status bar only
    show_status_bar_message()
```

### **Example Calculations:**

| Photos | Videos | Total | Dialog? |
|--------|--------|-------|---------|
| 15 | 3 | 18 | ❌ No (use status bar) |
| 21 | 14 | 35 | ✅ Yes |
| 50 | 0 | 50 | ✅ Yes |
| 0 | 25 | 25 | ✅ Yes |
| 108 | 3 | 111 | ✅ Yes |

---

## 🎬 **Progress Dialog Features**

When the dialog shows, it displays:

### **1. File Discovery**
```
Discovered 21 candidate image files and 14 video files
Total: 35 files to process
```

### **2. Current Progress**
```
📷 IMG_1234.jpg (2.5 MB)
Indexed: 15/35 photos
Committed: 150 database rows
```

### **3. Percentage Bar**
```
▓▓▓▓▓▓▓░░░░░░░░  43%
```

### **4. Cancel Button**
- Click to stop scan mid-process
- Partial results saved
- Can resume with incremental scan

---

## 🐛 **Troubleshooting**

### **"I scanned but saw no dialog!"**

**Check These:**

1. **Was it actually a scan?**
   - Opening existing database → No dialog (normal)
   - Toolbar → Scan Repository → Should show dialog

2. **File count below threshold?**
   - < 20 files → No dialog (by design)
   - Check status bar for "Scan complete: X photos, Y videos"

3. **Check the logs:**
   ```
   "Detected X photos + Y videos = Z total files"
   "File count (Z) exceeds threshold (20), showing progress dialog"
   ```
   - If no logs → no scan happened
   - If logs show count < 20 → threshold not met

### **"Dialog shows but no details!"**

**Possible Causes:**
- UI freeze (should not happen with current fixes)
- Thread blocked (contact support)
- Check for error messages in console

---

## 📊 **Status Bar vs. Dialog**

### **Status Bar (Bottom of Window)**
**Always shows:**
- Loading messages
- Scan progress for small scans (< 20 files)
- Completion messages
- Error messages

**Example Messages:**
```
📸 Scanning repository: C:/Photos (incremental=False)
✓ Scan complete: 21 photos, 14 videos indexed
```

### **Progress Dialog (Popup Window)**
**Shows only for:**
- Large scans (≥ 20 files)
- During scanning operation
- Provides detailed progress tracking

---

## ⚙️ **Changing The Threshold**

If you want to change when the dialog appears:

**File:** `controllers/scan_controller.py`
**Line:** 43

```python
# Current: Show for 20+ files
self.PROGRESS_DIALOG_THRESHOLD = 20

# Always show dialog:
self.PROGRESS_DIALOG_THRESHOLD = 0

# Show only for large scans (100+ files):
self.PROGRESS_DIALOG_THRESHOLD = 100
```

**Recommendation:** Keep at 20 for best user experience
- Small scans (< 20): Fast enough for status bar
- Medium/large scans (≥ 20): Need detailed progress

---

## 🎯 **Summary**

**Progress Dialog Shows:**
- ✅ During scanning (Toolbar → Scan Repository)
- ✅ When total files ≥ 20
- ✅ With detailed progress, percentage, cancel button

**Progress Dialog Does NOT Show:**
- ❌ When loading existing database
- ❌ When filtering/navigating existing photos
- ❌ When total files < 20 (uses status bar instead)

**Both Are Normal Behavior!**

The current implementation is working correctly:
- Large scans get detailed dialog
- Small scans get simple status bar
- Database loading stays fast and responsive

---

**Last Updated:** 2025-12-11
**Version:** 1.0
