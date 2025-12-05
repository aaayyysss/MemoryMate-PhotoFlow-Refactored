# Sequential Merge Duplicate Handling

## Problem Scenario

### Initial State
When face detection runs, it can detect multiple faces in the same photos:

```
Photo1.jpg: Has 2 faces detected
  - Face A (Person 1) → clustered as face_001
  - Face B (Person 2) → clustered as face_002

Photo2.jpg: Has 2 faces detected
  - Face A (Person 1) → clustered as face_001
  - Face B (Person 2) → clustered as face_002

Photo3.jpg, Photo4.jpg, ... → clustered as face_003 (another person)
```

**Cluster State:**
- `face_001`: Photo1, Photo2 (Person 1's faces)
- `face_002`: Photo1, Photo2 (Person 2's faces)
- `face_003`: Photo3, Photo4, ... (another person)

### Sequential Merge Operations

**First Merge: face_001 → face_003**
User realizes face_001 and face_003 are the same person.

```
ACTION: Merge face_001 into face_003
RESULT:
  - Moves Photo1, Photo2 from face_001 to face_003
  - face_003 now has: Photo1, Photo2, Photo3, Photo4, ...
  - face_001 cluster deleted (empty source)
  - Count updated correctly
```

**Second Merge: face_002 → face_003**
User mistakenly thinks face_002 is also the same person as face_003 (or correctly if all 3 are same person).

```
ACTION: Merge face_002 into face_003
ISSUE:
  - face_002 contains: Photo1, Photo2
  - face_003 ALREADY contains: Photo1, Photo2 (from first merge)
  - These are DUPLICATE PHOTOS - same images, already in target

QUESTION: What should happen?
```

## Best Practice: Google Photos Approach

### 1. Duplicate Detection During Merge

**Before merge, check for duplicates:**
```sql
-- Count photos in source that are ALREADY in target
SELECT COUNT(DISTINCT pi_source.image_path)
FROM project_images pi_source
WHERE pi_source.project_id = ?
  AND pi_source.branch_key = source_branch
  AND pi_source.image_path IN (
      SELECT image_path
      FROM project_images
      WHERE project_id = ? AND branch_key = target_branch
  )
```

### 2. Don't Inflate Count with Duplicates

**WRONG Approach:**
- Add all photos from source to target
- Result: Photo1, Photo2 appear TWICE in face_003
- Count shows 16 but should be 14
- Grid may show duplicates or cause SQL errors

**CORRECT Approach:**
- Delete duplicate source entries (photos already in target)
- Move only unique photos from source to target
- Count remains accurate
- No duplicates in grid

### 3. Inform User About Duplicates

**Google Photos Pattern:**
When merging with duplicates detected:

```
Merge Complete
✓ Merged "Person B" into "Person A"
• Found 2 duplicate photos (already in target)
• Moved 0 unique photos
• Total: 14 photos in "Person A"
```

**Benefits:**
- User understands what happened
- No surprise about count not increasing
- Transparency about duplicate handling
- Clear confirmation of merge result

### 4. Detailed Statistics

**Return comprehensive merge statistics:**
```python
{
    "moved_faces": 250,           # Face crops moved
    "duplicates_found": 2,        # Photos already in target
    "unique_moved": 0,            # Photos only in source (moved)
    "total_photos": 14,           # Final photo count in target
    "sources": ["face_002"],      # Source clusters merged
    "target": "face_003"          # Target cluster
}
```

## Implementation Requirements

### 1. Enhanced merge_face_clusters Return Value

```python
def merge_face_clusters(self, project_id, target_branch, source_branches, log_undo=True):
    """
    Returns:
        {
            "moved_faces": int,        # Face crops reassigned
            "duplicates_found": int,   # Photos already in target (deleted from source)
            "unique_moved": int,       # Photos only in source (moved to target)
            "total_photos": int,       # Final unique photo count in target
            "sources": list,           # Source branch keys
            "target": str              # Target branch key
        }
    """
```

### 2. UI Notification Enhancement

**sidebar_qt.py (line ~5434):**
```python
msg = f"Merged {len(source_keys)} people into "{target_name}".\n\n"
if stats.get("duplicates_found", 0) > 0:
    msg += f"• Found {stats['duplicates_found']} duplicate photos (already in target)\n"
if stats.get("unique_moved", 0) > 0:
    msg += f"• Moved {stats['unique_moved']} unique photos\n"
msg += f"• Total: {stats.get('total_photos', 0)} photos in "{target_name}""

QMessageBox.information(self, "Merge complete", msg)
```

**google_layout.py (line ~10603):**
```python
msg = f"'{source_name}' merged successfully\n\n"
if result.get('duplicates_found', 0) > 0:
    msg += f"⚠️ Found {result['duplicates_found']} duplicate photos\n"
    msg += f"   (already in target, not duplicated)\n\n"
msg += f"• Moved {result['unique_moved']} unique photos\n"
msg += f"• Reassigned {result['moved_faces']} face crops\n"
msg += f"• Total: {result.get('total_photos', 0)} photos"

QMessageBox.information(self.main_window, "Merged", msg)
```

## Key Principles

1. **Transparency**: Always inform user about duplicates found
2. **Accuracy**: Count should reflect unique photos, not inflated by duplicates
3. **No Data Loss**: Duplicates are detected and handled, not deleted from DB
4. **Clear Messaging**: User knows exactly what happened during merge
5. **Google Photos UX**: Follow familiar patterns users expect

## Edge Cases Handled

### Case 1: All Photos are Duplicates
```
Source: Photo1, Photo2
Target: Photo1, Photo2 (already has both)
Result:
  - 2 duplicates found
  - 0 unique photos moved
  - Count doesn't increase
  - User informed: "Found 2 duplicate photos"
```

### Case 2: Mix of Duplicates and Unique Photos
```
Source: Photo1, Photo2, Photo5
Target: Photo1, Photo2, Photo3, Photo4
Result:
  - 2 duplicates found (Photo1, Photo2)
  - 1 unique photo moved (Photo5)
  - Count increases by 1 (Photo5 added)
  - User informed: "Found 2 duplicates, moved 1 unique photo"
```

### Case 3: No Duplicates
```
Source: Photo5, Photo6
Target: Photo1, Photo2, Photo3, Photo4
Result:
  - 0 duplicates found
  - 2 unique photos moved
  - Count increases by 2
  - User informed: "Moved 2 unique photos"
```

## Testing Checklist

- [ ] Sequential merge with 100% duplicates (count doesn't increase)
- [ ] Sequential merge with mix of duplicates and unique photos
- [ ] Sequential merge with no duplicates (normal case)
- [ ] Three-way merge with overlapping photos
- [ ] UI notifications show correct duplicate counts
- [ ] Grid displays correct photos after merge (no duplicates)
- [ ] Count in people section matches grid photo count
- [ ] Undo/redo works correctly with duplicate handling

## References

- **Original Bug**: MERGE_BUG_DEEP_AUDIT.md
- **Google Photos UX**: Duplicate detection during merge operations
- **Database Schema**: project_images table with project_id + branch_key + image_path
