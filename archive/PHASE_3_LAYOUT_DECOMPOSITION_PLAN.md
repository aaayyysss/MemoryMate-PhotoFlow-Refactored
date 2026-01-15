# Phase 3: Layout Decomposition - Implementation Plan

**Date:** 2026-01-04
**Status:** 🔄 **IN PROGRESS**
**Branch:** claude/audit-embedding-extraction-QRRVm

---

## Executive Summary

Phase 3 focuses on decomposing the massive 17,300-line `google_layout.py` file into smaller, focused, maintainable components. This plan outlines a safe, incremental approach to extract functionality while maintaining backward compatibility and stability.

**Current State:**
- **File Size:** 17,300 lines (after Phase 1 duplicate cleanup)
- **Main Class:** GooglePhotosLayout (~9,440 lines)
- **Helper Classes:** MediaLightbox, FlowLayout, CollapsibleSection, PersonCard, PeopleGridView, etc.

**Goal:**
- Extract components into `google_components/` directory
- Reduce google_layout.py to <3,000 lines (coordinator only)
- Improve testability, maintainability, and code organization

---

## Decomposition Strategy

### Principle: Incremental, Safe Extraction

1. **Extract self-contained widgets first** (lowest risk)
2. **Create component interfaces** (define clean APIs)
3. **Move business logic to components** (gradual migration)
4. **Keep google_layout.py as coordinator** (thin orchestration layer)
5. **Test after each extraction** (ensure no breakage)

---

## Component Architecture

```
google_layout.py (coordinator ~2,500 lines)
├── google_components/
│   ├── __init__.py
│   ├── widgets.py                    # UI widget classes
│   │   ├── FlowLayout
│   │   ├── CollapsibleSection
│   │   ├── PersonCard
│   │   └── PeopleGridView
│   ├── timeline_view.py              # Timeline display component
│   │   ├── TimelineView
│   │   ├── DateGroupManager
│   │   └── PhotoGridRenderer
│   ├── people_manager.py             # People/face management
│   │   ├── PeopleManager
│   │   ├── FaceMergeController
│   │   └── UndoRedoStack
│   ├── sidebar_manager.py            # Sidebar components
│   │   ├── SidebarManager
│   │   ├── DateNavigator
│   │   ├── FolderNavigator
│   │   └── TagNavigator
│   ├── media_lightbox.py             # Photo viewer (extracted from google_layout.py)
│   │   └── MediaLightbox
│   └── thumbnail_loader.py           # Async thumbnail loading
│       ├── ThumbnailLoader
│       └── ThumbnailCache
```

---

## Phase 3A: Extract Self-Contained Widgets ✅ (Current Step)

### Classes to Extract

1. **FlowLayout** (lines 16620-16711, ~91 lines)
   - Custom Qt layout for flow grid
   - Zero dependencies on GooglePhotosLayout
   - **Risk:** Low

2. **CollapsibleSection** (lines 16712-16855, ~143 lines)
   - Collapsible UI widget with animation
   - Zero dependencies on GooglePhotosLayout
   - **Risk:** Low

3. **PersonCard** (lines 16856-17168, ~312 lines)
   - Individual person card widget
   - Signals for click, context menu, drag-drop
   - **Risk:** Low

4. **PeopleGridView** (lines 17169-17300, ~131 lines)
   - Grid container for PersonCard widgets
   - Uses FlowLayout
   - **Risk:** Low

**Total:** ~677 lines extracted to `google_components/widgets.py`

### Benefits
- Easier to test widgets in isolation
- Reusable widgets for other layouts
- Cleaner imports
- Reduced google_layout.py size

---

## Phase 3B: Extract Helper Classes (Next Step)

### Classes to Extract

1. **ThumbnailLoader & Signals** (lines 166-247)
   - Async thumbnail loading with QRunnable
   - Move to `google_components/thumbnail_loader.py`
   - **Risk:** Low-Medium (used throughout)

2. **PhotoButton** (lines 34-164)
   - Custom QPushButton with checkbox overlay
   - Move to `google_components/widgets.py`
   - **Risk:** Low

3. **GooglePhotosEventFilter** (lines 545-616)
   - Event filter for scrolling and keyboard
   - Move to `google_components/event_filters.py`
   - **Risk:** Medium (deeply integrated)

4. **AutocompleteEventFilter** (lines 7828-7859)
   - Event filter for autocomplete dropdown
   - Move to `google_components/event_filters.py`
   - **Risk:** Low

**Total:** ~350 lines to extract

---

## Phase 3C: Extract MediaLightbox (Major Component)

### MediaLightbox Class (lines 617-7757, ~7,140 lines!)

**Complexity:** This is a massive component that deserves its own file.

**Extract to:** `google_components/media_lightbox.py`

**Dependencies:**
- VideoEditorMixin (mixin from line 617)
- ProgressiveImageWorker, PreloadImageWorker
- Edit tools (brightness, contrast, saturation, filters)

**Challenges:**
- 7,140 lines is still too large for one file
- Should further decompose into:
  - `media_lightbox.py` (~1,500 lines) - Main lightbox
  - `lightbox_edit_tools.py` (~2,000 lines) - Edit functionality
  - `lightbox_video_player.py` (~1,500 lines) - Video playback
  - `image_preloader.py` (~500 lines) - Preloading logic

**Risk:** High (complex component with many features)

**Approach:**
1. Extract as single file first
2. Verify it works
3. Further decompose if needed

---

## Phase 3D: Extract Timeline Component

### Timeline Methods (~2,500 lines in GooglePhotosLayout)

**Methods to Extract:**
```python
# Data loading
_load_photos()
_group_photos_by_date()
_on_photos_loaded()

# Timeline rendering
_build_timeline_tree()
_display_photos_in_timeline()
_create_date_group()
_create_date_header()
_create_photo_grid()
_create_thumbnail()

# Scrolling and lazy loading
_on_timeline_scrolled()
_render_visible_date_groups()
_toggle_date_group()

# Thumbnail loading
_on_thumbnail_loaded()
_create_thumbnail()
```

**Extract to:** `google_components/timeline_view.py`

**New Component:**
```python
class TimelineView(QWidget):
    """Timeline display component for photo grid with date grouping."""

    photo_clicked = Signal(str)  # path
    selection_changed = Signal(str, int)  # path, state

    def __init__(self, project_id, db, config):
        self.project_id = project_id
        self.db = db
        self.config = config
        # ... init UI

    def load_photos(self, filter_params=None):
        """Load and display photos."""

    def refresh(self):
        """Refresh timeline display."""
```

**Risk:** High (core functionality, many dependencies)

---

## Phase 3E: Extract People Manager

### People/Face Methods (~3,500 lines in GooglePhotosLayout)

**Methods to Extract:**
```python
# People sidebar
_build_people_tree()
_refresh_people_sidebar()
_filter_people_grid()

# Person actions
_on_accordion_person_clicked()
_rename_person()
_delete_person()
_on_person_context_menu()

# Merging
_merge_person()
_perform_merge()
_on_drag_merge()
_suggest_cluster_merges()
_show_merge_suggestions_dialog()
_prompt_merge_suggestions()

# Undo/Redo
_undo_last_merge()
_redo_last_undo()
_update_undo_redo_state()
_show_merge_history()

# Face tools
_open_face_quality_dashboard()
_open_manual_face_crop_selector()
_prompt_bulk_face_review()
```

**Extract to:** `google_components/people_manager.py`

**New Component:**
```python
class PeopleManager(QObject):
    """Manages people/face detection, merging, and organization."""

    person_clicked = Signal(str)  # branch_key
    people_updated = Signal()
    merge_completed = Signal(str, str)  # source, target

    def __init__(self, project_id, db, config):
        self.project_id = project_id
        self.db = db
        self.config = config
        self.undo_stack = []
        self.redo_stack = []
        self.max_history = config.people.max_history

    def load_people(self):
        """Load people from database."""

    def merge_people(self, source_key, target_key):
        """Merge two people."""

    def undo(self):
        """Undo last merge."""

    def suggest_merges(self, target_key):
        """Suggest similar people to merge."""
```

**Risk:** High (complex logic, database operations, undo/redo)

---

## Phase 3F: Extract Sidebar Manager

### Sidebar Methods (~1,500 lines in GooglePhotosLayout)

**Methods to Extract:**
```python
# Sidebar creation
_create_sidebar()

# Navigation trees
_build_timeline_tree()
_build_folders_tree()
_build_tags_tree()
_build_videos_tree()

# Click handlers
_on_accordion_date_clicked()
_on_accordion_folder_clicked()
_on_accordion_tag_clicked()
_on_accordion_device_selected()
_on_accordion_video_clicked()

# Section management
_on_accordion_section_expanding()
```

**Extract to:** `google_components/sidebar_manager.py`

**New Component:**
```python
class SidebarManager(QWidget):
    """Manages sidebar navigation (dates, folders, tags, people, devices)."""

    filter_changed = Signal(dict)  # filter_params

    def __init__(self, project_id, db):
        self.project_id = project_id
        self.db = db
        # Create collapsible sections
        self.date_section = CollapsibleSection("📅 Timeline", ...)
        self.folder_section = CollapsibleSection("📁 Folders", ...)
        self.tag_section = CollapsibleSection("🏷️ Tags", ...)
        self.people_section = CollapsibleSection("👥 People", ...)

    def refresh_all(self):
        """Refresh all sidebar sections."""

    def set_filter(self, filter_type, value):
        """Apply filter and emit signal."""
```

**Risk:** Medium (UI integration, multiple sections)

---

## File Size Projections

### Before Decomposition
```
google_layout.py: 17,300 lines
```

### After Phase 3A (Widgets)
```
google_layout.py: 16,623 lines (-677)
google_components/widgets.py: 677 lines
```

### After Phase 3B (Helpers)
```
google_layout.py: 16,273 lines (-350)
google_components/thumbnail_loader.py: 200 lines
google_components/event_filters.py: 150 lines
```

### After Phase 3C (MediaLightbox)
```
google_layout.py: 9,133 lines (-7,140)
google_components/media_lightbox.py: 7,140 lines
```

### After Phase 3D (Timeline)
```
google_layout.py: 6,633 lines (-2,500)
google_components/timeline_view.py: 2,500 lines
```

### After Phase 3E (People)
```
google_layout.py: 3,133 lines (-3,500)
google_components/people_manager.py: 3,500 lines
```

### After Phase 3F (Sidebar)
```
google_layout.py: 1,633 lines (-1,500)
google_components/sidebar_manager.py: 1,500 lines
```

### Final State
```
google_layout.py: ~1,600 lines (coordinator only)
google_components/
  ├── widgets.py: 677 lines
  ├── thumbnail_loader.py: 200 lines
  ├── event_filters.py: 150 lines
  ├── media_lightbox.py: 7,140 lines (can further decompose)
  ├── timeline_view.py: 2,500 lines
  ├── people_manager.py: 3,500 lines
  └── sidebar_manager.py: 1,500 lines

Total component lines: ~15,667 lines
Coordinator lines: ~1,600 lines
Total: ~17,267 lines (slightly less due to removed boilerplate)
```

---

## Testing Strategy

### After Each Extraction

1. **Syntax Check**
   ```bash
   python -m py_compile google_layout.py
   python -m py_compile google_components/*.py
   ```

2. **Import Test**
   ```python
   from google_components.widgets import FlowLayout, CollapsibleSection, PersonCard, PeopleGridView
   ```

3. **Component Instantiation Test**
   ```python
   from google_components.widgets import PersonCard
   from PySide6.QtWidgets import QApplication

   app = QApplication([])
   card = PersonCard("cluster_0", "Test Person", None, 10)
   assert card.branch_key == "cluster_0"
   ```

4. **Integration Test**
   - Launch application
   - Navigate to Google Photos Layout
   - Verify all features work:
     - Timeline displays
     - Photos load
     - People sidebar works
     - Lightbox opens
     - Editing tools work
     - No errors in console

---

## Risks and Mitigation

### Risk 1: Breaking Imports
**Probability:** High
**Impact:** High
**Mitigation:**
- Update imports in google_layout.py immediately after extraction
- Test imports before committing
- Use backward-compatible imports if needed

### Risk 2: Circular Dependencies
**Probability:** Medium
**Impact:** High
**Mitigation:**
- Define clear component interfaces
- Use signals for cross-component communication
- Avoid direct class references between components

### Risk 3: Missing Dependencies
**Probability:** Medium
**Impact:** Medium
**Mitigation:**
- Carefully track all imports when extracting classes
- Include all necessary Qt imports in component files
- Test component files independently

### Risk 4: Runtime Errors
**Probability:** Medium
**Impact:** High
**Mitigation:**
- Extensive testing after each extraction
- Keep backup of working state
- Git commit after each successful extraction

---

## Success Criteria

### Phase 3A Success (Current)
- ✅ google_components/ directory created
- ✅ widgets.py file created with all 4 widget classes
- ✅ google_layout.py updated to import from widgets
- ✅ All syntax checks pass
- ✅ Application launches without errors
- ✅ People sidebar displays correctly

### Phase 3 Overall Success
- ✅ google_layout.py reduced to <2,000 lines
- ✅ All components extracted and working
- ✅ No regressions in functionality
- ✅ Code is more maintainable
- ✅ Components can be tested independently
- ✅ Clear architectural boundaries

---

## Implementation Timeline

### Phase 3A: Extract Widgets (CURRENT)
**Estimated Time:** 1-2 hours
**Status:** In Progress
**Deliverables:**
- google_components/widgets.py
- google_components/__init__.py
- Updated google_layout.py imports

### Phase 3B: Extract Helpers
**Estimated Time:** 2-3 hours
**Dependencies:** Phase 3A complete
**Deliverables:**
- google_components/thumbnail_loader.py
- google_components/event_filters.py

### Phase 3C: Extract MediaLightbox
**Estimated Time:** 4-6 hours
**Dependencies:** Phase 3B complete
**Deliverables:**
- google_components/media_lightbox.py
- Further decomposed if needed

### Phase 3D: Extract Timeline
**Estimated Time:** 6-8 hours
**Dependencies:** Phase 3C complete
**Deliverables:**
- google_components/timeline_view.py

### Phase 3E: Extract People Manager
**Estimated Time:** 6-8 hours
**Dependencies:** Phase 3D complete
**Deliverables:**
- google_components/people_manager.py

### Phase 3F: Extract Sidebar
**Estimated Time:** 3-4 hours
**Dependencies:** Phase 3E complete
**Deliverables:**
- google_components/sidebar_manager.py

---

## Current Status

**Phase 3A Progress:**
- ✅ Created google_components/ directory
- ⏸️ Need to extract widget classes to widgets.py
- ⏸️ Need to update google_layout.py imports
- ⏸️ Need to test extraction

**Next Immediate Steps:**
1. Create google_components/widgets.py with FlowLayout, CollapsibleSection, PersonCard, PeopleGridView
2. Create google_components/__init__.py
3. Update google_layout.py to import from google_components.widgets
4. Test that application still works
5. Commit Phase 3A changes

---

## References

- **Phase 1 Report:** DUPLICATE_METHODS_CLEANUP_COMPLETED.md
- **Phase 2 Report:** PHASE_2_CONFIGURATION_CENTRALIZATION.md
- **Audit Report:** GOOGLE_LAYOUT_AUDIT_REPORT.md
- **Implementation Plan:** IMPLEMENTATION_PLAN_GOOGLE_LAYOUT_REFACTOR.md (if exists)

---

**Status:** 🔄 **IN PROGRESS - PHASE 3A**
**Next Milestone:** Complete widget extraction
**Branch:** claude/audit-embedding-extraction-QRRVm
