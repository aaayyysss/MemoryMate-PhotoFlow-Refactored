# Search Quality and UI Issues - Diagnosis and Fixes

**Date:** 2026-01-04
**Status:** ⚠️ PARTIAL FIX - Enhanced Diagnostics Added

---

## 🔍 Issues Reported

### Issue #1: Low Search Quality (15.5% top score)
**User Query:** "trees", "green trees"
**Result:** Only 1 photo matched at 15.5% similarity
**Expected:** Higher scores (40-60%) with large-patch14 model

### Issue #2: Search Toolbar Disappearing
**Behavior:** After each search in Google layout, search toolbar becomes hidden
**Workaround:** Toggle to current layout and back to Google layout to restore

### Issue #3: Search Results Show All Photos
**Behavior:** Search finds 1 result but then loads all 35 photos
**Log Evidence:**
```
[INFO] [GooglePhotosLayout] 🔍✨ Semantic search: 1 results for 'trees'
[GooglePhotosLayout] Photo query complete: generation=2, current=2, rows=35
```

---

## 🔬 Root Cause Analysis

### Issue #1: Low Search Quality

**Possible Causes:**

#### A. Photos Genuinely Don't Contain Trees
- The dataset might not have tree photos
- CLIP model can only find what exists in the images

#### B. Dimension Mismatch (Most Likely)
**Hypothesis:** Old embeddings from base-patch32 (512-D) still in database

**Evidence from Log:**
```
2026-01-04 03:34:10 [INFO] [EmbeddingWorker] Processing 21 photos with model openai/clip-vit-large-patch14
2026-01-04 03:51:59 [INFO] [SemanticSearch] Using cached CLIP model: openai/clip-vit-large-patch14
2026-01-04 03:51:59 [WARNING] [EmbeddingService] Search complete but NO results above similarity threshold!
```

**What Likely Happened:**
1. **Before fixes:** Embeddings extracted with base-patch32 (512-D = 2048 bytes)
2. **After fixes:** Search uses large-patch14 (768-D = 3072 bytes query)
3. **Result:** Dimension validation skips old 512-D embeddings silently
4. **Only new 768-D embeddings processed** → Very few or none available

#### C. Model Not Fully Loaded
Less likely, but model cache might be incomplete.

---

## ✅ Fixes Applied

### Enhanced Diagnostic Logging

**File:** `services/embedding_service.py`

**Added Comprehensive Logging:**

1. **Pre-Search Info:**
   ```python
   logger.info(f"Search starting: {len(rows)} embeddings to check, "
               f"query dimension: {query_dim}-D ({expected_bytes} bytes expected)")
   ```

2. **Dimension Mismatch Tracking:**
   ```python
   skipped_dim_mismatch = 0
   skipped_errors = 0

   if len(embedding_blob) != expected_size:
       actual_dim = len(embedding_blob) // 4
       if skipped_dim_mismatch == 0:  # Log first occurrence with details
           logger.warning(f"Dimension mismatch detected! ...")
       skipped_dim_mismatch += 1
       continue
   ```

3. **Post-Search Statistics:**
   ```python
   logger.info(f"Search complete: {len(rows)} total embeddings, {processed_count} processed "
               f"({skipped_dim_mismatch} dimension mismatches, {skipped_errors} errors), "
               f"{len(results)} above threshold, top score={top_results[0][1]:.3f}")
   ```

4. **Actionable Warnings:**
   ```python
   if skipped_dim_mismatch > 0:
       logger.warning(f"⚠️ {skipped_dim_mismatch} embeddings skipped due to dimension mismatch! "
                      f"Consider re-extracting embeddings with Tools → Extract Embeddings")
   ```

**Benefits:**
- ✅ Shows exactly how many embeddings were skipped and why
- ✅ Identifies dimension mismatches immediately
- ✅ Provides actionable fix suggestions
- ✅ Helps diagnose search quality issues

---

## 🔧 How to Fix Search Quality

### Solution: Re-Extract Embeddings with Large Model

The embeddings in your database are likely from the base-patch32 model. You need to re-extract with large-patch14:

**Steps:**

1. **Open the App**
   ```bash
   python main_qt.py
   ```

2. **Re-Extract Embeddings**
   - Go to **Tools → Extract Embeddings**
   - The app will detect large-patch14 and use it automatically
   - Click **"Yes"** to proceed
   - Wait for extraction to complete (21 photos)

3. **Verify in Logs**
   Look for these messages:
   ```
   [INFO] [ModelSelection] Large model found offline: openai/clip-vit-large-patch14
   [INFO] [EmbeddingWorker] Processing 21 photos with model openai/clip-vit-large-patch14
   [INFO] [EmbeddingService] ✓ CLIP loaded: openai/clip-vit-large-patch14 (768-D)
   ```

4. **Test Search Again**
   - Search for "trees" or other queries
   - Check new log output:
     ```
     [INFO] [EmbeddingService] Search starting: 21 embeddings to check, query dimension: 768-D
     [INFO] [EmbeddingService] Search complete: 21 total embeddings, 21 processed
     (0 dimension mismatches, 0 errors), ...
     ```

5. **Expected Results:**
   - ✅ No dimension mismatch warnings
   - ✅ All 21 embeddings processed
   - ✅ Higher similarity scores (if photos match query)
   - ✅ Better search quality overall

---

## 📊 New Log Output Examples

### Before This Fix (Minimal Info):
```
[WARNING] [EmbeddingService] Search complete but NO results above similarity threshold!
21 candidates found, but all scores below 0.16.
```

**Problem:** No insight into WHY search failed

### After This Fix (Detailed Diagnostics):

**Scenario 1: Dimension Mismatch**
```
[INFO] [EmbeddingService] Search starting: 21 embeddings to check, query dimension: 768-D (3072 bytes expected)
[WARNING] [EmbeddingService] Dimension mismatch detected! Photo 1: embedding is 512-D (2048 bytes),
          but query is 768-D (3072 bytes). This embedding was likely extracted with a different CLIP model. Skipping.
[WARNING] [EmbeddingService] Search found NO results! 21 total embeddings: 21 dimension mismatches,
          0 errors, 0 processed. ❌ All dimension-matched embeddings scored below 0.14.
          💡 FIX: Re-extract embeddings with current model (Tools → Extract Embeddings)
```

**Scenario 2: Low Scores (No Dimension Issues)**
```
[INFO] [EmbeddingService] Search starting: 21 embeddings to check, query dimension: 768-D (3072 bytes expected)
[INFO] [EmbeddingService] Search complete: 21 total embeddings, 21 processed (0 dimension mismatches, 0 errors),
       1 above threshold (≥0.14), 20 below threshold, returning top 1 results, top score=0.155
```

**Scenario 3: Good Results**
```
[INFO] [EmbeddingService] Search starting: 21 embeddings to check, query dimension: 768-D (3072 bytes expected)
[INFO] [EmbeddingService] Search complete: 21 total embeddings, 21 processed (0 dimension mismatches, 0 errors),
       8 above threshold (≥0.30), 13 below threshold, returning top 8 results, top score=0.547
```

---

## 🐛 Issues Not Yet Fixed

### Issue #2: Search Toolbar Disappearing

**Status:** 🔍 Under Investigation

**What I Found:**
- Toolbar is created in `_create_toolbar()` and added to main layout
- Semantic search widget is added to toolbar at line 8462
- No code found that explicitly hides the toolbar after search
- Possible causes:
  - Layout refresh might be removing/recreating widgets
  - Google Photos layout mode switching
  - Z-index or stacking issue

**Workaround:**
- Toggle layout: Current → Google → Current → Google
- Or restart the app

**Next Steps:**
- Need to trace layout refresh events
- Check if widget parents are being changed
- May need to add toolbar persistence logic

### Issue #3: Search Results Showing All Photos

**Status:** 🔍 Code Review Needed

**What I Found:**
- `_on_semantic_search()` correctly receives 1 photo_id
- Calls `_rebuild_timeline_with_results(rows, query)` with only matching photo
- BUT log shows all 35 photos loaded afterwards

**Possible Causes:**
- Event triggered after search that reloads all photos
- Sidebar click or state change
- Timeline rebuild triggering full reload

**Need to Check:**
- Signal connections that might trigger `_load_photos()`
- Event listeners on sidebar or tabs
- Whether `_rebuild_timeline_with_results` completes correctly

---

## 📝 Testing Checklist

After re-extracting embeddings and restarting:

### Test 1: Verify Embeddings
```bash
sqlite3 photo_library.db "SELECT COUNT(*),
        LENGTH(embedding) as bytes,
        LENGTH(embedding)/4 as dimensions
        FROM photo_embedding
        WHERE embedding_type='visual_semantic'
        GROUP BY LENGTH(embedding)"
```

**Expected:** All embeddings are 3072 bytes (768-D)

### Test 2: Search with Diagnostics
Search for "blue", "trees", or any query and check logs:
- ✅ Should see: "Search starting: query dimension: 768-D"
- ✅ Should see: "0 dimension mismatches"
- ✅ Should see: "21 processed" (all embeddings checked)

### Test 3: Search Quality
- ✅ Higher scores (20-60% depending on content)
- ✅ More results above threshold
- ✅ Better relevance

---

## 🎯 Summary

**What's Fixed:**
- ✅ Enhanced diagnostic logging for search
- ✅ Dimension mismatch detection and warnings
- ✅ Actionable error messages
- ✅ Statistics tracking (processed, skipped, errors)

**What Needs Fixing:**
- ⚠️ **Re-extract embeddings** (user action required)
- ⚠️ Search toolbar disappearing (needs investigation)
- ⚠️ Search results showing all photos (needs investigation)

**User Action Required:**
1. Pull latest changes
2. Restart app
3. **Re-extract embeddings** (Tools → Extract Embeddings)
4. Test search with new diagnostic logs
5. Report back with new log output

---

**Fix committed:** 2026-01-04
**Branch:** claude/audit-embedding-extraction-QRRVm
**Files Changed:** services/embedding_service.py
