# Remaining Bugs - Comprehensive Fix Plan

**Date:** 2025-12-11
**Status:** Videos now populating ✅ - Fixing remaining UI issues

---

## ✅ **WHAT'S WORKING NOW**

After fixing the `total_videos` variable collision bug:
- ✅ Videos discovered correctly (14 videos)
- ✅ Videos indexed to database with folder_id and created_date
- ✅ Videos appear in Videos section of accordion sidebar
- ✅ Video metadata extraction works
- ✅ Database has complete video data

---

## ❌ **REMAINING BUGS**

### **Bug #1: Progress Dialog Not Showing**

**Current Behavior:**
- Threshold: 50 photos
- Scan: 21 photos + 14 videos = 35 total files
- Result: 21 < 50 → NO progress dialog!
- User sees NO visual feedback during scan

**Root Cause:**
```python
# controllers/scan_controller.py - Line 207
self._total_files_found = int(parts[i + 1])  # Only extracts PHOTO count!
```

The code parses "Discovered 21 candidate image files and 14 video files" but only extracts the FIRST number (21 photos), ignoring videos!

**Symptoms:**
- No progress dialog during scan
- No percentage completion
- No file name/path display
- No cancel button available
- Silent background operation

**Fix Strategy:**

**Option A:** Lower threshold to 10 (matches working version)
```python
self.PROGRESS_DIALOG_THRESHOLD = 10  # Was 50
```

**Option B:** Parse TOTAL files (photos + videos)
```python
# Parse: "Discovered 21 candidate image files and 14 video files"
# Extract BOTH numbers: 21 + 14 = 35 total
if "Discovered" in msg and "candidate" in msg:
    numbers = re.findall(r'\d+', msg)
    if len(numbers) >= 2:
        total_photos = int(numbers[0])
        total_videos = int(numbers[1])
        self._total_files_found = total_photos + total_videos
```

**Option C:** Always show progress dialog (remove threshold)
```python
# Always show dialog for any scan
self.main._scan_progress = QProgressDialog(...)
self.main._scan_progress.show()
```

**Recommendation:** Use **Option B** (count total files) with threshold of 20
- Shows progress for medium/large scans
- Counts both photos AND videos
- Most user-friendly approach

---

### **Bug #2: Folders Section Shows Only Photos**

**Current Behavior:**
- Folder "أغاني كرتون قديم": Shows "21 photos" but has 7 videos (missing!)
- Folder "Gardinia Band": Shows count but missing 7 videos
- Header: "Folder | Photos" (should be "Folder | Photos | Videos" or "Media")

**Root Cause:**
```python
# accordion_sidebar.py - Line 1892-1893
photo_count = int(self.db.get_image_count_recursive(fid) or 0)
# Only counts PHOTOS, not videos!

# Line 1902
item = QTreeWidgetItem([f"📁 {name}", f"{photo_count:>5}"])
# Shows only photo count
```

**Fix Strategy:**

**Option A:** Show combined count
```python
photo_count = int(self.db.get_image_count_recursive(fid) or 0)
video_count = int(self.db.get_video_count_recursive(fid) or 0)
total_count = photo_count + video_count
item = QTreeWidgetItem([f"📁 {name}", f"{total_count:>5}"])
tree.setHeaderLabels(["Folder", "Media"])
```

**Option B:** Show separate counts
```python
photo_count = int(self.db.get_image_count_recursive(fid) or 0)
video_count = int(self.db.get_video_count_recursive(fid) or 0)
count_text = f"{photo_count}📷 {video_count}🎬"
item = QTreeWidgetItem([f"📁 {name}", count_text])
tree.setHeaderLabels(["Folder", "Photos | Videos"])
```

**Option C:** Show smart count (photos, or videos, or both)
```python
photo_count = int(self.db.get_image_count_recursive(fid) or 0)
video_count = int(self.db.get_video_count_recursive(fid) or 0)

if photo_count > 0 and video_count > 0:
    count_text = f"{photo_count}📷 {video_count}🎬"
elif video_count > 0:
    count_text = f"{video_count}🎬"
else:
    count_text = f"{photo_count:>5}"

item = QTreeWidgetItem([f"📁 {name}", count_text])
```

**Recommendation:** Use **Option B** (separate counts with emojis)
- Clear visual distinction
- Shows exactly what's in each folder
- Matches Google Photos style

---

### **Bug #3: Dates Section Shows Only Photos**

**Current Behavior:**
- Date "2021-03-10": Shows "X photos" but has 12 videos
- Date "2019-12-01": Missing 1 video count
- Header: "Year/Month/Day | Photos" (should include videos)

**Root Cause:**
```python
# accordion_sidebar.py - Line 1701
tree.setHeaderLabels([tr('sidebar.header_year_month_day'), tr('sidebar.header_photos')])
# Header says "Photos" only

# Date count queries only count photos from photo_metadata table
# Doesn't query video_metadata table
```

**Fix Strategy:**

Similar to folders fix, but needs to:
1. Query video_date_branches table
2. Combine photo and video counts per date
3. Update header to show "Photos | Videos" or "Media"
4. Display counts with emojis for clarity

**Implementation:**
```python
# Update date hierarchy to include videos
def get_date_hierarchy_with_videos(self, project_id):
    """Get date hierarchy including both photos and videos."""
    # Get photo hierarchy
    photo_hier = self.get_date_hierarchy(project_id)

    # Get video hierarchy
    video_hier = self.get_video_date_hierarchy(project_id)

    # Merge hierarchies with counts
    # Return: {year: {month: {day: {"photos": 5, "videos": 2}}}}
```

**Recommendation:** Match folders implementation for consistency

---

## 🎯 **IMPLEMENTATION PRIORITY**

### **Priority 1: Progress Dialog (CRITICAL)**
Users NEED visual feedback during scanning!
- **Impact:** HIGH - User experience
- **Complexity:** LOW - Simple threshold/parsing fix
- **Files:** `controllers/scan_controller.py` (1 file, ~10 lines)

### **Priority 2: Folders Section Video Counts (HIGH)**
Folders are primary navigation - must show complete counts!
- **Impact:** HIGH - Data accuracy
- **Complexity:** MEDIUM - Need video count query + UI update
- **Files:** `accordion_sidebar.py`, `reference_db.py` (2 files, ~50 lines)

### **Priority 3: Dates Section Video Counts (MEDIUM)**
Important for chronological browsing
- **Impact:** MEDIUM - Data accuracy
- **Complexity:** MEDIUM - Similar to folders
- **Files:** `accordion_sidebar.py`, `reference_db.py` (2 files, ~50 lines)

---

## 📝 **DETAILED IMPLEMENTATION STEPS**

### **Step 1: Fix Progress Dialog (15 minutes)**

**File:** `controllers/scan_controller.py`

**Changes:**
1. Line 43: Lower threshold to 20
2. Line 201-211: Parse BOTH photo and video counts
3. Add total count logic

**Code:**
```python
# Line 43
self.PROGRESS_DIALOG_THRESHOLD = 20  # Lower from 50 to 20

# Line 199-215 (replace existing parsing)
if msg and "Discovered" in msg and "candidate" in msg:
    try:
        # Parse: "Discovered X candidate image files and Y video files"
        # Extract BOTH numbers
        import re
        numbers = re.findall(r'\d+', msg)
        if len(numbers) >= 2:
            total_photos = int(numbers[0])
            total_videos = int(numbers[1])
            self._total_files_found = total_photos + total_videos
            self.logger.info(f"Detected {total_photos} photos + {total_videos} videos = {self._total_files_found} total files")
        elif len(numbers) == 1:
            self._total_files_found = int(numbers[0])
    except Exception as e:
        self.logger.warning(f"Could not parse file count: {e}")
```

---

### **Step 2: Add Video Count Queries to ReferenceDB (20 minutes)**

**File:** `reference_db.py`

**Add new methods:**
```python
def get_video_count_recursive(self, folder_id: int) -> int:
    """Get total video count for folder and all subfolders."""
    try:
        with self.connection() as conn:
            cur = conn.cursor()
            # Get all descendant folder IDs
            descendant_ids = self._get_descendant_folder_ids(folder_id)
            descendant_ids.append(folder_id)

            placeholders = ','.join('?' * len(descendant_ids))
            cur.execute(f"""
                SELECT COUNT(*)
                FROM video_metadata
                WHERE folder_id IN ({placeholders})
            """, descendant_ids)

            return cur.fetchone()[0] or 0
    except Exception as e:
        logger.error(f"Error getting video count for folder {folder_id}: {e}")
        return 0

def get_video_date_hierarchy(self, project_id: int) -> dict:
    """Get video date hierarchy: {year: {month: [days]}} with counts."""
    try:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT created_year, created_date, COUNT(*) as cnt
                FROM video_metadata
                WHERE project_id = ? AND created_date IS NOT NULL
                GROUP BY created_year, created_date
                ORDER BY created_date DESC
            """, (project_id,))

            hier = {}
            for row in cur.fetchall():
                year = row['created_year']
                date = row['created_date']
                count = row['cnt']

                # Parse date string: "2021-03-10"
                parts = date.split('-')
                if len(parts) == 3:
                    month = int(parts[1])
                    day = int(parts[2])

                    if year not in hier:
                        hier[year] = {}
                    if month not in hier[year]:
                        hier[year][month] = []

                    hier[year][month].append({"day": day, "count": count})

            return hier
    except Exception as e:
        logger.error(f"Error getting video date hierarchy: {e}")
        return {}
```

---

### **Step 3: Update Accordion Sidebar Folders Section (25 minutes)**

**File:** `accordion_sidebar.py`

**Changes:**
1. Line 1824: Update header to "Photos | Videos"
2. Line 1892-1902: Add video count query and display

**Code:**
```python
# Line 1824 - Update header
tree.setHeaderLabels([tr('sidebar.header_folder'), "Photos | Videos"])

# Line 1891-1910 - Replace existing code
# Get photo count
if hasattr(self.db, "get_image_count_recursive"):
    photo_count = int(self.db.get_image_count_recursive(fid) or 0)
else:
    photo_count = 0

# Get video count
if hasattr(self.db, "get_video_count_recursive"):
    video_count = int(self.db.get_video_count_recursive(fid) or 0)
else:
    video_count = 0

# Format count display
if photo_count > 0 and video_count > 0:
    count_text = f"{photo_count}📷 {video_count}🎬"
elif video_count > 0:
    count_text = f"{video_count}🎬"
else:
    count_text = f"{photo_count:>5}"

# Create tree item
item = QTreeWidgetItem([f"📁 {name}", count_text])
```

---

### **Step 4: Update Accordion Sidebar Dates Section (30 minutes)**

**File:** `accordion_sidebar.py`

**Changes:**
1. Line 1701: Update header
2. Date hierarchy merging logic
3. Display counts for both photos and videos

**Code:** Similar pattern to folders section

---

## 🧪 **TESTING PROTOCOL**

After implementing all fixes, test with your dataset (21 photos + 14 videos):

### **Test 1: Progress Dialog**
- [ ] Start scan
- [ ] Progress dialog appears (21 + 14 = 35 > 20 threshold)
- [ ] Dialog shows: "Discovered 21 photos and 14 videos"
- [ ] Dialog updates with current file name
- [ ] Dialog shows percentage (0-100%)
- [ ] Cancel button works

### **Test 2: Folders Section**
- [ ] Open Folders section in accordion sidebar
- [ ] Folder "أغاني كرتون قديم" shows: "X📷 7🎬"
- [ ] Folder "Gardinia Band" shows: "X📷 7🎬"
- [ ] Counts are accurate
- [ ] Double-click folder shows both photos and videos

### **Test 3: Dates Section**
- [ ] Open Dates section in accordion sidebar
- [ ] Date "2021-03-10" shows: "X📷 12🎬"
- [ ] Date "2019-12-01" shows: "X📷 1🎬"
- [ ] Counts are accurate
- [ ] Double-click date shows both photos and videos

---

## 📊 **SUCCESS CRITERIA**

✅ **All fixes successful when:**

1. **Progress Dialog**
   - Shows for scans with 20+ total files (photos + videos)
   - Displays file name, path, percentage
   - Cancel button responsive
   - Counts both media types

2. **Folders Section**
   - Shows photo count AND video count for each folder
   - Header clearly indicates "Photos | Videos"
   - Emoji icons for visual clarity (📷 🎬)
   - Counts include subfolders recursively

3. **Dates Section**
   - Shows photo count AND video count for each date
   - Video dates appear correctly (2019, 2021)
   - Combined hierarchy shows all media chronologically
   - Accurate counts at year/month/day levels

---

**Implementation Time Estimate:** 90-120 minutes total
**Risk Level:** LOW (isolated changes, well-tested patterns)
**User Impact:** HIGH (significantly improves UX and data visibility)
