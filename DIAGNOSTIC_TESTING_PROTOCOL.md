# Diagnostic Testing Protocol

**Date:** 2025-12-11
**Purpose:** Diagnose two issues:
1. Progress dialog not appearing during scan
2. Video folders not showing videos in grid

---

## 🔬 **TEST 1: Progress Dialog During Scan**

### **Setup:**
```bash
git pull  # Get latest debugging code
```

### **Steps:**

1. **Prepare fresh log:**
   - Close the app completely
   - Navigate to: `/home/user/MemoryMate-PhotoFlow-Refactored/`
   - Delete or rename `Debug-Log` file

2. **Start app and scan:**
   - Launch the app
   - Click **"Scan Repository"** button in toolbar
   - Select your test folder: `C:/Users/ASUS/OneDrive/Documents/Python/Test-Photos/photos/refs`
   - (Should have 21 photos + 14 videos = 35 total files)

3. **Watch carefully:**
   - Does a popup dialog window appear? ✅ / ❌
   - Or only status bar messages at bottom? ✅ / ❌
   - Take screenshot if dialog appears (or doesn't)

4. **After scan completes:**
   - Find the `Debug-Log` file
   - Upload to GitHub at: `Debug-Log-SCAN-TEST`

### **What We're Looking For:**

The log should contain:
```
📸 Scanning repository: .../refs (incremental=False)
Discovered 21 candidate image files and 14 video files
Detected 21 photos + 14 videos = 35 total files
File count (35) exceeds threshold (20), showing progress dialog
```

**If missing "Detected" line:**
- File count parsing failed
- Need to fix regex

**If missing "exceeds threshold" line:**
- Threshold check failed
- Total wasn't calculated correctly

**If has all lines but no dialog visible:**
- Dialog created but not shown
- Qt issue or window placement problem

---

## 🔬 **TEST 2: Video Folder Display**

### **Setup:**
```bash
git pull  # Get latest debugging code
```

### **Steps:**

1. **Prepare fresh log:**
   - Close the app
   - Delete or rename `Debug-Log` file

2. **Test video folder click:**
   - Launch the app
   - Open **Google Photos layout**
   - Open accordion sidebar → **Folders section**
   - Find folder: **"أغاني كرتون قديم"** (should show `X📷 7🎬`)
   - **Double-click** the folder

3. **Observe grid:**
   - Does grid show videos? ✅ / ❌
   - If yes: How many videos shown? _____
   - If no: What does grid show? (empty? photos only? error message?)
   - Take screenshot

4. **Check the log:**
   - Find lines between:
     ```
     ========================================
     Accordion folder clicked: folder_id=XX
     ...
     ========================================
     ```
   - Upload log to GitHub at: `Debug-Log-VIDEO-FOLDER-TEST`

### **What We're Looking For:**

The log should show:
```
========================================
[GooglePhotosLayout] Accordion folder clicked: folder_id=44
[GooglePhotosLayout] Found folder path: c:/users/.../أغاني كرتون قديم
[GooglePhotosLayout] Calling _load_photos with filter_folder=...
🔍 SQL Query:
  SELECT DISTINCT pm.path, pm.created_date, pm.width, pm.height
  FROM photo_metadata pm
  ...
  UNION ALL
  SELECT DISTINCT vm.path, vm.created_date, vm.width, vm.height
  FROM video_metadata vm
  WHERE vm.project_id = ?
  AND vm.path LIKE ?
  ...
🔍 Parameters: [1, 'c:/users/.../أغاني كرتون قديم%']
✅ Found XX photos in database
```

**Key Questions:**

1. **Does query include `UNION ALL` with video_metadata?**
   - If NO → query not combining photos + videos
   - If YES → query is correct

2. **What are the parameters?**
   - Check folder path format: `c:/users/...` (forward slashes, lowercase)
   - Check LIKE pattern: ends with `%`

3. **How many results found?**
   - If 0 → path matching problem or data problem
   - If 7 → videos found! But not displaying (UI problem)
   - If 21 → only photos found (video query failing)

4. **Is there an error after the query?**
   - Check for exceptions or error messages

---

## 🔬 **TEST 3: Videos Section (Control Test)**

### **Steps:**

1. **Test Videos section click:**
   - Open accordion sidebar → **Videos section**
   - Click **"Videos"** (not a specific folder!)

2. **Observe:**
   - Does grid show all 14 videos? ✅ / ❌
   - Take screenshot

3. **Compare:**
   - Videos section works? → General video display OK
   - Video folder doesn't work? → Folder filtering problem

---

## 📋 **SUMMARY CHECKLIST**

Please provide:

### **For Progress Dialog Issue:**
- [ ] Screenshot during scan (dialog visible or not)
- [ ] `Debug-Log-SCAN-TEST` file uploaded to GitHub
- [ ] Confirmation: Did you click "Scan Repository" button?
- [ ] Confirmation: Folder has 35 files (21 photos + 14 videos)?

### **For Video Folder Issue:**
- [ ] Screenshot of grid after clicking video folder
- [ ] Screenshot of folder section showing `X📷 7🎬` count
- [ ] `Debug-Log-VIDEO-FOLDER-TEST` file uploaded to GitHub
- [ ] Does Videos section show all 14 videos? (control test)

---

## 🎯 **EXPECTED BEHAVIOR**

### **Progress Dialog:**
```
During scan of 35 files:
- ✅ Popup dialog appears
- ✅ Shows: "Detected 21 photos + 14 videos = 35 total files"
- ✅ Progress bar updates
- ✅ Shows current file name
- ✅ Cancel button works
```

### **Video Folder:**
```
Click folder "أغاني كرتون قديم" (7🎬):
- ✅ Grid shows 7 video thumbnails
- ✅ Videos are playable
- ✅ Same videos as clicking "Videos" section
```

---

## 🐛 **POSSIBLE ISSUES & FIXES**

### **If Progress Dialog Doesn't Show:**

**Issue A: No scan performed**
- Log has no "Scanning repository" message
- Solution: Make sure to click "Scan Repository" button, not just open app

**Issue B: File count below threshold**
- Log shows: "Detected 18 total files" (< 20)
- Solution: Verify folder actually has 35 files

**Issue C: Parsing failed**
- Log has no "Detected X photos + Y videos" message
- Solution: Fix regex parsing in scan_controller.py

**Issue D: Threshold check failed**
- Log has "Detected 35 total" but no "exceeds threshold"
- Solution: Debug threshold comparison logic

### **If Video Folder Shows 0 Results:**

**Issue A: Path mismatch**
- Folder path: `C:\Users\...` (backslash, uppercase)
- Database path: `c:/users/...` (forward slash, lowercase)
- Solution: Verify path normalization

**Issue B: Video query missing**
- SQL query has no `UNION ALL` section
- Solution: Check if video query is being built

**Issue C: JOIN still failing**
- Query uses `JOIN project_videos` (non-existent table)
- Solution: Verify latest code pulled

**Issue D: Videos not in database**
- Query runs but returns 0 results
- Solution: Check if videos were actually indexed during scan

---

**Please run both tests and provide the logs + screenshots!** 🔬
