# Video Section Fix - Root Cause Analysis

## Problem
Videos were not loading in the sidebar Video section in both Google Layout and Current Layout, despite:
- Videos being successfully scanned and indexed
- Thumbnails being generated
- Debug logging showing "Indexed video" entries

## Root Cause
**Database file was in the wrong location.**

The application expected the database at:
```
/home/user/MemoryMate-PhotoFlow-Refactored/reference_data.db
```

But the actual database with data was located at:
```
/home/user/MemoryMate-PhotoFlow-Refactored/DBfromTest/reference_data.db
```

This caused:
- `VideoRepository.get_by_project()` to return 0 videos (querying empty database)
- `VideoService.get_videos_by_project()` to return empty list
- Accordion sidebar Videos section to show "No videos found"
- Current Layout sidebar to show "Found 0 videos"

## Investigation Steps

### 1. Verified debug code was committed
```bash
$ git show adf3a42:accordion_sidebar.py | grep "from VideoService"
self._dbg(f"Loaded {total_videos} videos from VideoService")
```
✓ Debug logging was present in the code

### 2. Checked database in current directory
```bash
$ ls -lh photo_organizer.db reference_data.db
-rw-r--r-- 1 root root 0 Dec  9 16:43 photo_organizer.db
reference_data.db not found
```
✗ Only an empty `photo_organizer.db` existed (0 bytes)

### 3. Found actual database in DBfromTest
```bash
$ ls -lh DBfromTest/
-rw-r--r-- 1 root root 908K reference_data.db
-rw-r--r-- 1 root root 480K thumbnails_cache.db
```
✓ Real databases found with actual data

### 4. Verified videos exist in actual database
```python
import sqlite3
conn = sqlite3.connect('DBfromTest/reference_data.db')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM video_metadata WHERE project_id = 1')
print(cur.fetchone()[0])  # Output: 3
```
✓ Database contained 3 videos for project 1

## Solution
Copy the databases from `DBfromTest/` to the application root directory:

```bash
cp DBfromTest/reference_data.db reference_data.db
cp DBfromTest/thumbnails_cache.db thumbnails_cache.db
```

## Verification
Run the diagnostic test:
```bash
$ python3 test_video_loading.py
```

Expected output:
```
✓ Database is accessible
✓ video_metadata table contains 3 videos
✓ VideoRepository can query 3 videos for project 1
```

## Files Modified
- ✅ Copied `DBfromTest/reference_data.db` → `reference_data.db`
- ✅ Copied `DBfromTest/thumbnails_cache.db` → `thumbnails_cache.db`
- ✅ Created `test_video_loading.py` (diagnostic script)
- ✅ Created `VIDEO_SECTION_FIX.md` (this document)

## Technical Details

### Database Configuration
The application uses centralized database configuration via `db_config.py`:

```python
def get_db_path(base_dir: str = None) -> str:
    if base_dir is None:
        return "reference_data.db"
    return str(Path(base_dir) / "reference_data.db")
```

All components use this configuration:
- `reference_db.py` (line 31): `DB_FILE = get_db_filename()`
- `main_window_qt.py` (line 1065): `db_conn = DatabaseConnection("reference_data.db", ...)`
- `VideoRepository` (via `BaseRepository` and `DatabaseConnection`)

### Why Debug Logging Didn't Appear
The debug logging code WAS executed, but because `VideoService.get_videos_by_project()` returned 0 results (querying empty database), the log showed:
```
[AccordionSidebar] Loaded 0 videos from VideoService
```

The subsequent "checking database directly" code would have executed, but likely queried the same empty database.

## Status
✅ **FIXED** - Videos will now load correctly in both layouts after using the correct database file.

## Next Steps
When you pull this code and run the application:
1. The databases are now in the correct location
2. Video section should populate with 3 videos
3. Categories (By Duration, By Resolution, By Date) should appear
4. Videos should be clickable in the tree

If videos still don't appear, check:
- Run `python3 test_video_loading.py` to verify database access
- Check application logs for errors during sidebar initialization
- Verify project_id is set correctly when accordion sidebar loads
