# Duplicate Photo Management - User Guide

**Version:** 1.0.0
**Last Updated:** 2026-01-15

## Overview

MemoryMate PhotoFlow's Duplicate Management feature helps you identify, review, and manage exact duplicate photos in your library. This powerful tool uses SHA256 content hashing to find identical photos, even if they have different filenames or are in different folders.

## Key Features

- **Automatic Hash Computation**: One-time hash calculation for all photos
- **Smart Duplicate Detection**: Find exact duplicates based on file content (not names)
- **Visual Comparison**: Side-by-side view of all duplicate copies
- **Representative Selection**: Automatically chooses the best copy to keep
- **Safe Deletion**: Protected deletion workflow with confirmations
- **Stack Badges**: Visual indicators on thumbnails showing duplicate count
- **Metadata Preservation**: Important photo data is preserved during cleanup

---

## Getting Started

### Step 1: Prepare Photos for Duplicate Detection

Before you can find duplicates, you need to compute file hashes for your photos. This is a one-time operation.

1. Open **Preferences** (Settings menu)
2. Go to the **Advanced** tab
3. Look for the **"Duplicate Management"** section
4. Click **"🔍 Prepare Duplicate Detection"**

![Preferences Dialog](./images/duplicate_preferences.png)

**What happens during preparation:**
- MemoryMate computes SHA256 hashes for all photos
- Photos are linked to assets (content-based identity)
- Progress is shown in real-time with statistics
- This process is resumable if interrupted
- Typical speed: 500-1000 photos per minute

**Status Indicators:**
- 🟢 **Green** - All photos are ready for duplicate detection
- 🟠 **Orange** - Photos need processing (shows count)

### Step 2: Review Duplicates

Once preparation is complete, you can review duplicates:

1. Go to **Google Layout** (main photo view)
2. Click the **"🔍 Duplicates"** button in the toolbar
3. The Duplicates Dialog opens showing all duplicate groups

![Duplicates Button](./images/duplicates_toolbar.png)

---

## Using the Duplicates Dialog

### Understanding the Interface

The Duplicates Dialog has two main panels:

**Left Panel - Duplicate Groups:**
- Lists all duplicate asset groups
- Shows representative thumbnail
- Displays instance count (e.g., "3 copies")
- Shows content hash preview

**Right Panel - Instance Details:**
- Shows all copies of the selected duplicate
- Displays thumbnails and metadata
- Highlights the representative (⭐) copy
- Provides checkboxes for selection

![Duplicates Dialog](./images/duplicates_dialog.png)

### Understanding Representatives

The **representative** is the "best" copy of a duplicate group, automatically chosen based on:

1. **Resolution** - Higher resolution preferred
2. **File Size** - Larger files preferred (less compression)
3. **Date Taken** - Earlier dates preferred
4. **Source** - Camera photos preferred over screenshots
5. **Import Time** - Earlier imports preferred

The representative is **protected from deletion** and marked with a ⭐ star.

### Reviewing and Deleting Duplicates

1. **Select a duplicate group** from the left panel
2. **Review all instances** in the right panel
3. **Check the copies you want to delete**
   - The representative cannot be selected (protected)
   - You can select one or more duplicates
4. **Click "🗑️ Delete Selected"**
5. **Confirm the deletion**

**What happens during deletion:**
- ✅ Selected photo files are deleted from disk
- ✅ Database entries are removed
- ✅ If you deleted the representative, a new one is automatically chosen
- ✅ If all copies are deleted, the duplicate group is removed

**Safety Features:**
- Representative is always protected
- Confirmation dialog with details
- Shows exactly what will be deleted
- Reports errors if files can't be deleted
- Cannot be undone - be careful!

---

## Stack Badges (Thumbnail Indicators)

Photos that belong to duplicate groups show a **stack badge** on their thumbnail:

![Stack Badge](./images/stack_badge.png)

**Badge Features:**
- Circular black badge in bottom-right corner
- White count number (e.g., "5" for 5 duplicates)
- Clickable to open Stack View Dialog

### Using Stack Badges

**To view a stack:**
1. Click the stack badge on any thumbnail
2. Stack View Dialog opens showing all members

**Stack View Dialog:**
- Shows all photos in the stack
- Displays similarity scores (if available)
- Shows metadata comparison table
- Provides same deletion capabilities
- Allows unstacking (remove grouping without deleting)

![Stack View Dialog](./images/stack_view_dialog.png)

---

## Advanced Operations

### Unstacking Photos

"Unstacking" removes the duplicate grouping without deleting any photos.

**Use this when:**
- Photos are similar but you want to keep them separate
- You want to remove the duplicate badge
- Photos were incorrectly grouped

**To unstack:**
1. Open Stack View Dialog (click badge)
2. Click **"🔓 Unstack All"**
3. Confirm the action
4. Photos remain but badge is removed

### Handling Deletion Errors

If deletion fails for some files:

**Common reasons:**
- File is open in another program
- File permissions issue
- File was moved or renamed
- Disk is write-protected

**What to do:**
1. Note the error messages shown
2. Close programs that might have files open
3. Check file permissions
4. Try deletion again
5. Check the log file for details

### Managing Representatives

You cannot manually set representatives yet, but they are updated automatically when:

- You delete the current representative
- You delete some duplicate copies
- A new, better quality photo is imported

The system always ensures the best copy is the representative.

---

## Best Practices

### Before Running Duplicate Detection

1. **Import all photos first** - Complete all imports before running detection
2. **Backup your photos** - Always have a backup before mass deletions
3. **Review carefully** - Take time to understand what you're deleting
4. **Start small** - Test with a small group first

### During Duplicate Review

1. **Check metadata** - Compare dates, sizes, resolutions
2. **Open full images** - Click thumbnails to view full size if unsure
3. **Keep the best quality** - The representative is usually the best, but verify
4. **Document decisions** - Note why you kept certain copies if important

### After Deletion

1. **Empty Recycle Bin** - Free up disk space (files are permanently deleted)
2. **Refresh the view** - The display updates automatically
3. **Re-run if needed** - Import new photos will trigger new duplicate detection

---

## Troubleshooting

### "No duplicates found" but I know there are duplicates

**Possible causes:**
- Hash backfill hasn't run yet (check Preferences)
- Photos are similar but not identical (different edits)
- Photos are from different imports

**Solution:**
- Run "Prepare Duplicate Detection" from Preferences
- Wait for completion (check status)
- Try again

### Deletion is slow or hangs

**Possible causes:**
- Large files take time to delete
- Antivirus scanning
- Network drives
- Disk fragmentation

**Solution:**
- Be patient (check log for progress)
- Temporarily disable antivirus
- Delete in smaller batches

### Representative was deleted anyway

This shouldn't happen (it's protected), but if it does:

**What happens:**
- System automatically chooses a new representative
- Duplicate group continues to exist
- No data loss

**If you see this:**
- Report it as a bug
- Check logs for details

### Stack badges not showing

**Possible causes:**
- Photos aren't actually in stacks yet
- Only showing in duplicate groups
- View needs refresh

**Solution:**
- Run duplicate detection first
- Refresh the view (F5)
- Check if duplicates exist in Duplicates Dialog

---

## Technical Details

### Hash Algorithm

- **Algorithm**: SHA256 (cryptographic hash)
- **What it does**: Creates unique fingerprint of file content
- **Collision probability**: Effectively zero for photo libraries
- **Performance**: ~1000 photos per minute on modern hardware

### Database Tables

Duplicate management uses these database tables:

- `media_asset` - Unique content (one per unique photo)
- `media_instance` - File instances (multiple copies of same photo)
- `media_stack` - Groupings (duplicate, similar, burst)
- `media_stack_member` - Photos in each stack

### File Deletion

When you delete a duplicate:

1. Photo file deleted from disk (os.remove)
2. `photo_metadata` entry removed (CASCADE removes `media_instance`)
3. Thumbnail cache invalidated
4. Folder photo count updated
5. Representative updated if needed
6. Orphaned assets cleaned up

---

## FAQ

**Q: Will this delete my only copy of a photo?**
A: No. The representative (best copy) is always protected from deletion. You can only delete additional copies.

**Q: Can I undo a deletion?**
A: No. Files are permanently deleted. Use your backup if you need to recover.

**Q: How much disk space will I save?**
A: Depends on your duplicates. The dialog shows total size before deletion.

**Q: Does this work with videos?**
A: Currently optimized for photos. Video support is planned for future versions.

**Q: What about similar (but not identical) photos?**
A: Future feature. Current version only finds exact duplicates.

**Q: Can I choose which copy to keep?**
A: Not manually yet. The system chooses based on quality criteria. You can unstack and manually manage if needed.

**Q: Will this work with RAW files?**
A: Yes! The hash is computed on file content, so RAW, JPEG, PNG, etc. all work.

**Q: What if I have multiple projects?**
A: Duplicate detection is per-project. Duplicates across projects aren't detected.

---

## Keyboard Shortcuts

Currently no keyboard shortcuts are implemented for duplicate management. All operations are mouse-driven through the UI.

---

## Privacy & Security

- **All processing is local** - No data sent to external servers
- **Hashes are cryptographic** - SHA256 is secure and private
- **Original files untouched** - Only explicit deletions remove files
- **No telemetry** - Your photo review is completely private

---

## Support & Feedback

If you encounter issues or have suggestions:

1. Check the log file: `logs/memorymate.log`
2. Report issues on GitHub: [MemoryMate-PhotoFlow Issues](https://github.com/...)
3. Include log excerpts with bug reports
4. Describe steps to reproduce

---

## Version History

### Version 1.0.0 (2026-01-15)
- Initial release
- Exact duplicate detection
- Hash backfill workflow
- Duplicates dialog
- Stack view dialog
- Stack badges
- Deletion workflow
- Representative selection

---

## Future Enhancements

Planned features for future releases:

- **Near-duplicate detection** - Find similar photos with perceptual hashing
- **Burst detection** - Identify photo bursts
- **Manual representative selection** - Choose your preferred copy
- **Bulk operations** - Delete all duplicates at once
- **Smart suggestions** - AI-powered duplicate recommendations
- **Cross-project duplicates** - Find duplicates across all projects
- **Merge metadata** - Combine tags/ratings from all copies

---

## Conclusion

MemoryMate PhotoFlow's Duplicate Management feature provides a safe, powerful way to clean up your photo library. By using content-based hashing and smart representative selection, you can confidently remove duplicate photos while keeping the best copies.

Always remember:
- ✅ Backup before mass deletions
- ✅ Review carefully before deleting
- ✅ Representatives are protected
- ✅ Deletion is permanent

Happy organizing! 📸
