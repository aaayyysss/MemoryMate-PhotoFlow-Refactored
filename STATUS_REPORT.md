# MemoryMate-PhotoFlow: Architecture Stabilization Status Report

**Branch:** `claude/fix-metadata-editor-placement-8NC6v`
**Date:** 2026-02-07
**Commits:** 10 (2d88a03..54bf0d1) | 22 files changed, +829 / -469 lines

---

## Executive Summary

Over multiple sessions we identified and fixed **25+ bugs** spanning the full
application stack: threading violations, stale-widget access, permanent UI locks,
DB context-manager misuse, service lifecycle issues, and silent data exclusion in
the similarity pipeline. The codebase is now architecturally sound. What remains
is a focused startup-timing pass to ensure cold starts on large projects don't
stutter.

---

## Completed Fixes (by commit)

### Commit 1 — `2d88a03` Metadata Editor Placement
- Moved metadata editing from main layout toolbar into MediaLightbox info panel
- Added "Edit Metadata" right-click context menu to both Google + Current layouts
- Fixed `_get_selected_photo_paths()` → `get_selected_paths()` API mismatch

### Commit 2 — `f7ae625` Metadata Editor Silent Failures
- Added case-insensitive DB path matching fallback for Windows path mismatches
- Initialized `_lb_loading` / `_lb_current_photo_id` in MediaLightbox `__init__`
- Added full metadata editing to Current Layout's LightboxDialog

### Commit 3 — `f25a37d` 6 Critical Performance Issues
- **ReferenceDB.get_connection() shim** — 102+ callers used `get_connection()` but only `_connect()` existed
- **UI-thread blocking** — `db_writer.shutdown(wait=True)` → `wait=False`
- **DeviceScanner gating** — wrong default `True→False`, prevented COM enumeration
- **Sidebar lazy-init** — SidebarTabs/AccordionSidebar created on first use, not eagerly
- **Background grouping** — `_group_photos_by_date` moved to QRunnable + chunked widget creation
- **Deferred cache purge** — thumbnail `purge_stale()` moved from splash to daemon thread

### Commit 4 — `69f610e` MainWindow.logger Crash + Stale Embeddings
- `MainWindow._on_metadata_changed` used `self.logger` (doesn't exist) → `print()`
- `get_stale_embeddings_for_project` now has 5-min TTL cache (was re-querying every 30s)

### Commit 5 — `033b5f3` Crash Guards + DB Misuse + Debounce
- **refresh_thumbnail crash** — `hasattr()` guard on `ThumbnailGridQt`
- **JobManager wiring** — `get_job_manager()` singleton instead of never-assigned `self.job_manager`
- **DB context-manager misuse** — Fixed 3 locations: `db_writer.py` (critical), `reference_db.py` (2x silent failures), `accordion_sidebar/__init__.py`
- **Debounce saves** — MetadataEditorDock text fields debounced 500ms via QTimer

### Commit 6 — `82e5935` 6 Architectural Issues
- **Project switching** — `_on_project_changed_by_id` delegates to active layout via `layout_manager`
- **SearchService singleton** — `get_search_service()` factory replaces 4 separate instantiations
- **Refresh storms** — `AccordionSidebar.refresh_all()` only reloads expanded section; others bump generation
- **CLIP tokenizer** — `use_fast=False` pinned for reproducible embeddings
- **Face crops dedup** — `UNIQUE INDEX` on `(project_id, image_path, bbox_x, bbox_y, bbox_w, bbox_h)`
- **Cross-date similarity** — Global embedding-similarity pass via vectorized numpy `emb_matrix @ emb_matrix.T`

### Commit 7 — `00c9c9d` scan_controller Crash on Google Layout
- **Root cause:** `scan_controller` directly poked `self.main.sidebar` / `self.main.grid` (CurrentLayout widgets) even when Google Layout was active
- **3 crashes fixed:**
  - `AttributeError: tabs_controller is None` (hasattr passed, value was None)
  - `"Cannot set accordion_sidebar project_id"` (wrong grid's project_id)
  - Grid reload aborted (hidden CurrentLayout grid had project_id=None)
- **Added `_get_active_project_id()`** helper — resolves via layout_manager → grid → DB default
- Refactored `_cleanup_impl` and `_finalize_scan_refresh` to delegate to active layout

### Commit 8 — `d140c7a` Accordion Sidebar Permanent Loading Lock
- **Bug 1: `_loading=True` never reset** — `set_project()` called twice in 4ms; second bumps generation while first thread runs; thread completes → generation mismatch → `_on_data_loaded` returns without `_loading=False` → section permanently stuck
  - Fix: Reset `_loading=False` BEFORE generation check in all 6 section files + base
  - Fix: Always emit loaded signal from `on_complete()` (removed thread-side generation guard)
- **Bug 2: `sidebar_was_updated` flag blocked accordion** — Flag set when hidden SidebarQt updated, incorrectly prevented AccordionSidebar refresh
  - Fix: Always refresh AccordionSidebar after scan; flag only gates CurrentLayout's SidebarQt

### Commit 9 — `eb7b440` Similarity Detection Data Exclusion
- **`created_ts IS NOT NULL` filter** excluded all dateless photos from similarity detection entirely (not just time-window pass, but also global cross-date pass)
  - Fix: Removed filter; time-window pass naturally skips dateless photos; global pass now considers all photos with embeddings
- **`cross_date_threshold` 0.90 → 0.85** — 0.90 too strict for real CLIP embeddings
- **Hardcoded `max(threshold, 0.90)`** in `generate_stacks_for_photos()` → uses `params.cross_date_threshold`
- **SimilarityConfig** now exposes `cross_date_similarity` and `cross_date_threshold` with settings persistence

### Commit 10 — `54bf0d1` Lightbox Thread Safety
- **Stale signal delivery** — Rapid Prev/Next spawns multiple `ProgressiveImageWorker`s; slow worker for photo N finishes after fast worker for photo N+2, overwriting display
  - Fix: `_lb_media_generation` counter bumped per navigation, carried through workers, checked in signal handlers
- **QPixmap in worker threads** — Qt documents QPixmap as GUI-only; both `PreloadImageWorker` and `ProgressiveImageWorker` created QPixmap in `run()` (background thread)
  - Fix: Workers emit `QImage` (thread-safe); `QPixmap.fromImage()` conversion happens in signal handlers on main thread

---

## Files Modified (22 total)

| File | Changes | Category |
|------|---------|----------|
| `controllers/scan_controller.py` | +188 -113 | Layout-aware project propagation |
| `services/stack_generation_service.py` | +185 -13 | Cross-date similarity, dateless photos |
| `main_window_qt.py` | +183 -151 | Project switching delegation, logger fix |
| `google_components/media_lightbox.py` | +158 -110 | Generation token, QImage thread safety |
| `layouts/google_layout.py` | +109 -35 | Background grouping, context menus |
| `sidebar_qt.py` | +108 -47 | Lazy initialization |
| `db_writer.py` | +65 -48 | Context-manager fix |
| `ui/metadata_editor_dock.py` | +45 -1 | Debounce, editing features |
| `services/semantic_embedding_service.py` | +44 -12 | Stale cache, use_fast=False |
| `config/similarity_config.py` | +41 -1 | Cross-date config params |
| `reference_db.py` | +29 -13 | get_connection shim, bare commit fix |
| `accordion_sidebar.py` | +24 -1 | Lazy refresh_all |
| `ui/accordion_sidebar/folders_section.py` | +22 -12 | Loading lock fix |
| `ui/accordion_sidebar/videos_section.py` | +15 -5 | Loading lock fix |
| `ui/accordion_sidebar/base_section.py` | +14 -2 | Loading lock fix |
| `ui/accordion_sidebar/dates_section.py` | +14 -2 | Loading lock fix |
| `ui/accordion_sidebar/locations_section.py` | +14 -2 | Loading lock fix |
| `ui/accordion_sidebar/people_section.py` | +12 -2 | Loading lock fix |
| `app_services.py` | +12 -0 | SearchService singleton |
| `splash_qt.py` | +10 -1 | Deferred cache purge |
| `search_widget_qt.py` | +3 -1 | Singleton usage |
| `ui/accordion_sidebar/__init__.py` | +3 -1 | DB context fix |

---

## Patterns Established

### Generation Token Pattern
Used in AccordionSidebar sections and now MediaLightbox. Counter bumped on
each state change; async results carry the generation and are discarded if stale.

```
self._generation += 1
current_gen = self._generation
# ... spawn worker with current_gen ...
# In handler:
if generation != self._generation:
    return  # discard stale result
```

### Layout Manager Delegation
All cross-cutting code (scan_controller, main_window) now routes through
`layout_manager.get_current_layout()` instead of directly touching
`self.main.sidebar` / `self.main.grid`.

### Thread-Safe Image Loading
Workers emit `QImage` (thread-safe). Main-thread handlers convert to
`QPixmap` via `QPixmap.fromImage()`. No GUI objects cross thread boundaries.

### _loading Flag Discipline
`_loading=False` is ALWAYS reset when a background thread completes,
regardless of whether the result is stale. The generation check happens
AFTER the flag reset.

---

## Current Architecture Health

| Subsystem | Status | Notes |
|-----------|--------|-------|
| Metadata editing | **Stable** | In lightbox + context menus, debounced saves |
| DB access layer | **Stable** | Context managers fixed, get_connection shim |
| Scan pipeline | **Stable** | Layout-aware, proper project propagation |
| Accordion sidebar | **Stable** | Loading locks fixed, lazy refresh |
| Similarity detection | **Stable** | Includes dateless photos, cross-date pass |
| Lightbox navigation | **Stable** | Generation token, QImage thread safety |
| Service lifecycle | **Stable** | Singletons (SearchService, JobManager) |
| Startup performance | **Needs work** | See "Tomorrow's Work" below |

---

## Tomorrow's Work: Startup Critical Path

The remaining work is a focused timing pass, not structural changes.

### 1. Reconstruct the Startup Critical Path
Map frame-by-frame what happens between `QApplication.exec()` and first paint:
- What MUST complete before first render (layout creation, initial project load)
- What currently runs synchronously but should be deferred (grouping, sidebar population, maintenance)
- Where background jobs and initial layout compete for the event loop

### 2. Verify Paging and Grouping Handoff
Specifically the moment where GoogleLayout dispatches:
- `_group_photos_by_date` (now in QRunnable, but timing vs first paint?)
- Thumbnail loading (progressive, but when does it start relative to layout stabilization?)
- JobManager maintenance job (should not compete with initial paint)

### 3. Add Two Guardrails
- **First-render fence:** Ensure the initial layout always completes and paints before any background work begins (even on large datasets)
- **Startup scheduling gate:** Prevent background jobs (maintenance, embedding updates, cache purge) from running until after layout stabilization

### 4. Confirm MediaLightbox is Isolated
From recent logs, lightbox behavior is correct and not involved in startup.
Explicitly verify it has no startup-time side effects (preloading, signal connections, etc.)

### Key Files to Examine
- `main_window_qt.py` — startup sequence, `show()` timing, deferred init
- `layouts/google_layout.py` — `set_project()`, `_group_photos_by_date`, initial load
- `splash_qt.py` — what runs before main window, handoff timing
- `controllers/scan_controller.py` — post-scan refresh timing (already fixed, verify)

---

## Known Non-Blockers (Future Consideration)

These were identified in the external audit but are not blockers:

- **Perceptual hashing (pHash/dHash)** — Pre-filter for near-duplicate detection before CLIP comparison; would reduce the O(n^2) embedding matrix
- **Duplicate focus-on-photo UI** — Navigate to a photo in the grid from the duplicates dialog
- **Path normalization** — Consistent path handling across Windows/Mac/Linux
- **SQLite → PostgreSQL** — Not needed; SQLite is correct for a desktop app

---

*Report generated from branch `claude/fix-metadata-editor-placement-8NC6v` at commit `54bf0d1`*
