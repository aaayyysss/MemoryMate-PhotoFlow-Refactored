# Phase 3 Implementation Plan: Architecture Refactoring

**Date:** 2025-12-12
**Branch:** `claude/audit-face-detection-fixes-017b511yX8FznoEy9cGus3eF`
**Status:** 📋 **READY TO START**
**Estimated Time:** 30 hours
**Prerequisites:** ✅ Phase 1 Complete, ✅ Phase 2 Complete

---

## 📋 Executive Summary

**Phase 3** focuses on **architecture refactoring** to improve code maintainability, testability, and long-term scalability. This phase addresses technical debt identified in the Deep Audit Report.

### 🎯 Goals

- **Formal interfaces** - Define clear contracts between components
- **Modular architecture** - Break down 94KB monolithic files
- **Testability** - Add unit tests for critical paths
- **Type safety** - Enable static analysis with mypy

### 📊 Current State

| Issue | Impact | Priority |
|-------|--------|----------|
| **No layout interface** | Controllers don't know which methods are safe to call | 🟢 MEDIUM |
| **94KB accordion_sidebar.py** | Hard to navigate, maintain, and test | 🟢 MEDIUM |
| **No unit tests** | Regression risk, hard to validate fixes | 🟢 MEDIUM |

---

## 🚀 Task Breakdown

### Task 3.1: Define Formal Layout Interface ✅

**Priority:** 🟢 MEDIUM
**Estimated Time:** 8 hours
**Goal:** Create clear contract between MainWindow and layout implementations

#### Problem Statement

**Current Issues:**
- No formal contract between MainWindow and layouts
- GooglePhotosLayout and CurrentLayout have different APIs
- Controllers don't know which methods are safe to call
- Duck typing leads to runtime errors

**Example of Current Problem:**
```python
# controllers/project_controller.py
def switch_project(self, project_id):
    # Which methods exist? Which are safe to call?
    self.main.layout.set_project(project_id)  # ← May or may not exist!
    self.main.layout.refresh()  # ← Different signature in each layout!
```

#### Solution: BaseLayout Interface

**Step 1: Create Base Interface (2 hours)**

**File:** `layouts/base_layout.py`

```python
"""
Base layout interface for all layout implementations.
Defines the contract between MainWindow and layout widgets.
"""
from abc import ABC, abstractmethod
from typing import Optional
from PySide6.QtWidgets import QWidget


class BaseLayout(ABC, QWidget):
    """
    Abstract base class for all layout implementations.

    All layouts (Google Photos, Current, Timeline, etc.) must implement
    this interface to ensure consistent behavior and enable type checking.
    """

    # --- Project Management ---

    @abstractmethod
    def set_project(self, project_id: int) -> None:
        """
        Switch to a different project.

        Args:
            project_id: ID of project to display (from projects table)

        Implementation Requirements:
            - Clear existing UI state
            - Update internal project_id
            - Reload data for new project
            - Emit signals if needed
        """
        pass

    @abstractmethod
    def get_current_project(self) -> Optional[int]:
        """
        Get currently displayed project ID.

        Returns:
            int: Current project ID, or None if no project loaded
        """
        pass

    # --- Data Refresh ---

    @abstractmethod
    def refresh_after_scan(self) -> None:
        """
        Reload data after scan completes.

        Called by ScanController when:
            - Photo scan finishes
            - Video metadata extraction completes
            - Face detection finishes

        Implementation Requirements:
            - Reload photo/video list from database
            - Update sidebar sections (dates, folders, people)
            - Refresh thumbnail cache
            - Keep current filters active if possible
        """
        pass

    @abstractmethod
    def refresh_thumbnails(self) -> None:
        """
        Reload thumbnails without requerying database.

        Called when:
            - Thumbnail cache is cleared
            - Window is resized
            - User changes thumbnail size setting
        """
        pass

    # --- Filtering ---

    @abstractmethod
    def filter_by_date(self, year: Optional[int] = None,
                      month: Optional[int] = None,
                      day: Optional[int] = None) -> None:
        """
        Filter displayed items by date.

        Args:
            year: Year filter (e.g., 2024), or None for all years
            month: Month filter (1-12), requires year
            day: Day filter (1-31), requires year and month

        Implementation Requirements:
            - Update timeline/grid to show only matching items
            - Keep sidebar showing all available dates
            - Update "Clear Filter" button visibility
        """
        pass

    @abstractmethod
    def filter_by_folder(self, folder_id: int) -> None:
        """
        Filter displayed items by folder.

        Args:
            folder_id: Folder ID from folder_hierarchy table

        Implementation Requirements:
            - Show only items in specified folder (and subfolders)
            - Keep sidebar showing all folders
            - Highlight active folder in sidebar
        """
        pass

    @abstractmethod
    def filter_by_person(self, person_branch_key: str) -> None:
        """
        Filter displayed items by person (face cluster).

        Args:
            person_branch_key: Person identifier from face_crops table

        Implementation Requirements:
            - Show only photos containing this person
            - Exclude videos (no face detection on videos)
            - Keep sidebar showing all people
        """
        pass

    @abstractmethod
    def clear_filters(self) -> None:
        """
        Remove all active filters and show all items.

        Implementation Requirements:
            - Reset date/folder/person filters to None
            - Reload full photo/video list
            - Hide "Clear Filter" button
            - Update UI to reflect unfiltered state
        """
        pass

    # --- Selection ---

    @abstractmethod
    def get_selected_paths(self) -> list[str]:
        """
        Get list of currently selected file paths.

        Returns:
            list[str]: Absolute paths to selected photos/videos

        Used by:
            - Delete operation
            - Export operation
            - Bulk tagging
        """
        pass

    @abstractmethod
    def clear_selection(self) -> None:
        """
        Deselect all items.

        Implementation Requirements:
            - Clear internal selection state
            - Update UI to show no selection
            - Emit selection_changed signal
        """
        pass

    # --- Cleanup ---

    @abstractmethod
    def cleanup(self) -> None:
        """
        Clean up resources before layout is destroyed.

        Called when:
            - Switching to different layout
            - Closing application

        Implementation Requirements:
            - Cancel pending background tasks
            - Close database connections
            - Clear caches
            - Stop worker threads
        """
        pass
```

**Step 2: Create Type Protocols (1 hour)**

**File:** `layouts/layout_protocol.py`

```python
"""
Type protocols for layout components.
Enables static type checking without inheritance.
"""
from typing import Protocol, Optional
from PySide6.QtCore import Signal


class LayoutProtocol(Protocol):
    """Protocol for layout implementations (for type hints)."""

    def set_project(self, project_id: int) -> None: ...
    def get_current_project(self) -> Optional[int]: ...
    def refresh_after_scan(self) -> None: ...
    def filter_by_date(self, year: Optional[int] = None,
                      month: Optional[int] = None,
                      day: Optional[int] = None) -> None: ...
    def clear_filters(self) -> None: ...
    def get_selected_paths(self) -> list[str]: ...


class SidebarProtocol(Protocol):
    """Protocol for sidebar implementations."""

    # Signals
    folder_selected: Signal
    date_selected: Signal
    person_selected: Signal

    def set_project(self, project_id: int) -> None: ...
    def reload(self) -> None: ...
```

**Step 3: Implement in GooglePhotosLayout (3 hours)**

**File:** `layouts/google_layout.py`

```python
from layouts.base_layout import BaseLayout

class GooglePhotosLayout(BaseLayout):
    """
    Google Photos-style timeline layout.
    Implements BaseLayout interface.
    """

    def __init__(self, main_window):
        super().__init__(main_window)
        self.project_id = None
        # ... existing initialization ...

    # --- Implement BaseLayout methods ---

    def set_project(self, project_id: int) -> None:
        """Switch to different project."""
        self.project_id = project_id
        self._load_photos()  # Reload for new project
        if hasattr(self, 'accordion_sidebar'):
            self.accordion_sidebar.set_project(project_id)

    def get_current_project(self) -> Optional[int]:
        """Get current project ID."""
        return self.project_id

    def refresh_after_scan(self) -> None:
        """Reload data after scan completes."""
        self._load_photos(
            thumb_size=self.current_thumb_size,
            filter_year=self.current_filter_year,
            filter_month=self.current_filter_month,
            filter_day=self.current_filter_day,
            filter_folder=self.current_filter_folder,
            filter_person=self.current_filter_person
        )
        if hasattr(self, 'accordion_sidebar'):
            self.accordion_sidebar.reload_all_sections()

    def refresh_thumbnails(self) -> None:
        """Reload thumbnails without requerying database."""
        # Clear thumbnail cache
        self.thumbnail_buttons.clear()
        # Reload with current filters
        self.refresh_after_scan()

    def filter_by_date(self, year: Optional[int] = None,
                      month: Optional[int] = None,
                      day: Optional[int] = None) -> None:
        """Filter by date."""
        self._load_photos(
            thumb_size=self.current_thumb_size,
            filter_year=year,
            filter_month=month,
            filter_day=day,
            filter_folder=None,
            filter_person=None
        )

    def filter_by_folder(self, folder_id: int) -> None:
        """Filter by folder."""
        # Get folder path from database
        from reference_db import ReferenceDB
        db = ReferenceDB()
        folder_path = db.get_folder_path(folder_id)

        self._load_photos(
            thumb_size=self.current_thumb_size,
            filter_year=None,
            filter_month=None,
            filter_day=None,
            filter_folder=folder_path,
            filter_person=None
        )

    def filter_by_person(self, person_branch_key: str) -> None:
        """Filter by person."""
        self._load_photos(
            thumb_size=self.current_thumb_size,
            filter_year=None,
            filter_month=None,
            filter_day=None,
            filter_folder=None,
            filter_person=person_branch_key
        )

    def clear_filters(self) -> None:
        """Clear all filters."""
        self._load_photos(thumb_size=self.current_thumb_size)

    def get_selected_paths(self) -> list[str]:
        """Get selected file paths."""
        return list(self.selected_items)

    def clear_selection(self) -> None:
        """Clear selection."""
        self.selected_items.clear()
        # Update UI to show no selection
        # ... existing deselection code ...

    def cleanup(self) -> None:
        """Clean up resources."""
        # Cancel pending async operations
        self._photo_load_generation += 1  # Invalidate pending workers

        # Clear caches
        self.thumbnail_buttons.clear()
        self.date_groups_metadata.clear()

        # Stop worker threads
        if hasattr(self, 'accordion_sidebar'):
            self.accordion_sidebar.cleanup()
```

**Step 4: Update Controllers (1 hour)**

**File:** `controllers/project_controller.py`

```python
from layouts.base_layout import BaseLayout

class ProjectController:
    def __init__(self, main_window):
        self.main = main_window

    def switch_project(self, project_id: int):
        """
        Switch to different project.
        Type-safe now - layout guaranteed to have set_project method!
        """
        # Type hint ensures layout implements BaseLayout
        layout: BaseLayout = self.main.current_layout

        # IDE autocomplete works, type checker verifies method exists
        layout.set_project(project_id)

        # Refresh scan controller
        if hasattr(self.main, 'scan_controller'):
            self.main.scan_controller.project_id = project_id
```

**Step 5: Enable Type Checking (1 hour)**

**File:** `mypy.ini` (create if doesn't exist)

```ini
[mypy]
python_version = 3.10
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = False
disallow_incomplete_defs = False

[mypy-PySide6.*]
ignore_missing_imports = True

[mypy-PIL.*]
ignore_missing_imports = True
```

**Run Type Checker:**
```bash
mypy layouts/google_layout.py
mypy controllers/project_controller.py
```

#### Validation Checklist

- [ ] BaseLayout interface created with all abstract methods
- [ ] GooglePhotosLayout implements BaseLayout
- [ ] All abstract methods implemented
- [ ] Type hints added to controller methods
- [ ] mypy type checking passes
- [ ] All existing functionality still works
- [ ] No runtime errors during project switching

#### Files to Create
- `layouts/base_layout.py` (150 lines)
- `layouts/layout_protocol.py` (50 lines)

#### Files to Modify
- `layouts/google_layout.py` (+100 lines)
- `controllers/project_controller.py` (+20 lines)

---

### Task 3.2: Modularize AccordionSidebar 📦

**Priority:** 🟢 MEDIUM
**Estimated Time:** 12 hours
**Goal:** Split 94KB monolithic file into maintainable modules

#### Problem Statement

**Current State:**
- `accordion_sidebar.py` is **94KB / 2000+ lines**
- Mixes 5 different sections (folders, dates, videos, tags, people)
- Hard to navigate (Ctrl+F needed to find methods)
- Difficult to test individual sections
- High cognitive load for maintenance

#### Solution: Module-Based Architecture

**Step 1: Design Module Structure (1 hour)**

```
ui/accordion_sidebar/
├── __init__.py              # Main AccordionSidebar class (500 lines)
├── base_section.py          # BaseSection abstract class (100 lines)
├── folders_section.py       # FoldersSection implementation (300 lines)
├── dates_section.py         # DatesSection implementation (250 lines)
├── videos_section.py        # VideosSection implementation (200 lines)
├── tags_section.py          # TagsSection implementation (200 lines)
├── people_section.py        # PeopleSection implementation (300 lines)
└── navigation_widget.py     # Back/Forward/Home buttons (150 lines)
```

**Step 2: Create BaseSection Interface (2 hours)**

**File:** `ui/accordion_sidebar/base_section.py`

```python
"""
Base class for all accordion sections.
Provides common functionality and defines interface.
"""
from abc import ABC, abstractmethod
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget
from PySide6.QtCore import Signal


class BaseSection(QWidget, ABC):
    """
    Abstract base class for accordion sections.

    All sections (Folders, Dates, Videos, etc.) must implement this interface.
    """

    # Signals
    item_selected = Signal(object)  # Emitted when user clicks item
    loading_started = Signal()      # Emitted when async load starts
    loading_finished = Signal(int)  # Emitted with item count

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_id = None
        self.db_path = "reference_data.db"
        self._loading = False
        self._init_ui()

    def _init_ui(self):
        """Initialize common UI elements."""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Tree widget (common to most sections)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.layout.addWidget(self.tree)

    # --- Abstract Methods (must be implemented) ---

    @abstractmethod
    def set_project(self, project_id: int) -> None:
        """
        Update section for new project.

        Args:
            project_id: ID of project to display

        Implementation Requirements:
            - Store project_id
            - Clear existing tree items
            - Trigger reload if section is expanded
        """
        pass

    @abstractmethod
    def reload(self) -> None:
        """
        Reload section data from database.

        Implementation Requirements:
            - Clear existing items
            - Query database for current project
            - Populate tree widget
            - Emit loading_finished signal
        """
        pass

    @abstractmethod
    def _on_item_clicked(self, item, column: int) -> None:
        """
        Handle tree item click.

        Args:
            item: QTreeWidgetItem that was clicked
            column: Column index

        Implementation Requirements:
            - Extract data from item
            - Emit item_selected signal with appropriate data
        """
        pass

    # --- Common Methods (optional to override) ---

    def clear(self) -> None:
        """Clear all items from section."""
        self.tree.clear()

    def is_loading(self) -> bool:
        """Check if section is currently loading."""
        return self._loading

    def cleanup(self) -> None:
        """Clean up resources (override if needed)."""
        self.clear()
```

**Step 3: Implement FoldersSection (2 hours)**

**File:** `ui/accordion_sidebar/folders_section.py`

```python
"""
Folders section for accordion sidebar.
Displays folder hierarchy with file counts.
"""
from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtCore import QThread, Signal
from .base_section import BaseSection


class FoldersSection(BaseSection):
    """Folders section implementation."""

    def set_project(self, project_id: int) -> None:
        """Update section for new project."""
        self.project_id = project_id
        self.clear()
        # Reload is called by accordion when section is expanded

    def reload(self) -> None:
        """Reload folders from database."""
        if not self.project_id:
            return

        self._loading = True
        self.loading_started.emit()
        self.clear()

        # Start background worker
        self.worker = FoldersWorker(self.project_id, self.db_path)
        self.worker.loaded.connect(self._on_folders_loaded)
        self.worker.start()

    def _on_folders_loaded(self, folders: list):
        """Handle folders loaded from database."""
        self._loading = False

        # Build tree from folder hierarchy
        for folder in folders:
            item = QTreeWidgetItem(self.tree)
            item.setText(0, f"{folder['name']} ({folder['count']})")
            item.setData(0, Qt.UserRole, folder)

        self.loading_finished.emit(len(folders))

    def _on_item_clicked(self, item, column: int) -> None:
        """Handle folder click."""
        folder_data = item.data(0, Qt.UserRole)
        if folder_data:
            self.item_selected.emit(folder_data)


class FoldersWorker(QThread):
    """Background worker for loading folders."""

    loaded = Signal(list)  # Emits folder list

    def __init__(self, project_id: int, db_path: str):
        super().__init__()
        self.project_id = project_id
        self.db_path = db_path

    def run(self):
        """Query database in background thread."""
        from reference_db import ReferenceDB

        db = ReferenceDB()
        folders = db.get_folder_hierarchy(self.project_id)
        self.loaded.emit(folders)
```

**Step 4: Refactor Main AccordionSidebar (3 hours)**

**File:** `ui/accordion_sidebar/__init__.py`

```python
"""
Accordion sidebar with collapsible sections.
Orchestrates multiple section modules.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea
from PySide6.QtCore import Signal

from .folders_section import FoldersSection
from .dates_section import DatesSection
from .videos_section import VideosSection
from .tags_section import TagsSection
from .people_section import PeopleSection
from .navigation_widget import NavigationWidget


class AccordionSidebar(QWidget):
    """
    Main accordion sidebar widget.
    Manages multiple collapsible sections.
    """

    # Signals
    folder_selected = Signal(object)
    date_selected = Signal(object)
    person_selected = Signal(object)
    video_selected = Signal(object)
    tag_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_id = None
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """Initialize UI with sections."""
        layout = QVBoxLayout(self)

        # Navigation widget (back/forward/home)
        self.nav_widget = NavigationWidget()
        layout.addWidget(self.nav_widget)

        # Scroll area for sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        # Container for sections
        container = QWidget()
        sections_layout = QVBoxLayout(container)

        # Create sections
        self.folders_section = FoldersSection()
        self.dates_section = DatesSection()
        self.videos_section = VideosSection()
        self.tags_section = TagsSection()
        self.people_section = PeopleSection()

        sections_layout.addWidget(self.folders_section)
        sections_layout.addWidget(self.dates_section)
        sections_layout.addWidget(self.videos_section)
        sections_layout.addWidget(self.tags_section)
        sections_layout.addWidget(self.people_section)

        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _connect_signals(self):
        """Connect section signals to accordion signals."""
        self.folders_section.item_selected.connect(self.folder_selected)
        self.dates_section.item_selected.connect(self.date_selected)
        self.videos_section.item_selected.connect(self.video_selected)
        self.tags_section.item_selected.connect(self.tag_selected)
        self.people_section.item_selected.connect(self.person_selected)

    # --- Public API ---

    def set_project(self, project_id: int) -> None:
        """Update all sections for new project."""
        self.project_id = project_id
        self.folders_section.set_project(project_id)
        self.dates_section.set_project(project_id)
        self.videos_section.set_project(project_id)
        self.tags_section.set_project(project_id)
        self.people_section.set_project(project_id)

    def reload_all_sections(self) -> None:
        """Reload all sections from database."""
        self.folders_section.reload()
        self.dates_section.reload()
        self.videos_section.reload()
        self.tags_section.reload()
        self.people_section.reload()

    def cleanup(self) -> None:
        """Clean up all sections."""
        self.folders_section.cleanup()
        self.dates_section.cleanup()
        self.videos_section.cleanup()
        self.tags_section.cleanup()
        self.people_section.cleanup()
```

**Step 5: Implement Remaining Sections (2 hours each)**

Similar pattern for:
- `dates_section.py`
- `videos_section.py`
- `tags_section.py`
- `people_section.py`

**Step 6: Update Imports (1 hour)**

Update all files that import AccordionSidebar:

```python
# OLD:
from accordion_sidebar import AccordionSidebar

# NEW:
from ui.accordion_sidebar import AccordionSidebar  # Unchanged!
```

#### Validation Checklist

- [ ] All 8 module files created
- [ ] BaseSection interface implemented by all sections
- [ ] Main AccordionSidebar orchestrates sections correctly
- [ ] All signals still work
- [ ] File size reduced: 94KB → ~500 lines main file
- [ ] Each section is independently testable
- [ ] No functionality regressions

#### Files to Create
- `ui/accordion_sidebar/__init__.py` (500 lines)
- `ui/accordion_sidebar/base_section.py` (100 lines)
- `ui/accordion_sidebar/folders_section.py` (300 lines)
- `ui/accordion_sidebar/dates_section.py` (250 lines)
- `ui/accordion_sidebar/videos_section.py` (200 lines)
- `ui/accordion_sidebar/tags_section.py` (200 lines)
- `ui/accordion_sidebar/people_section.py` (300 lines)
- `ui/accordion_sidebar/navigation_widget.py` (150 lines)

#### Files to Modify
- `accordion_sidebar.py` → moved to `ui/accordion_sidebar/__init__.py`
- `layouts/google_layout.py` (update import only)

---

### Task 3.3: Add Unit Tests 🧪

**Priority:** 🟢 MEDIUM
**Estimated Time:** 10 hours
**Goal:** Create test suite for critical paths

#### Test Structure

```
tests/
├── __init__.py
├── conftest.py                    # Pytest fixtures
├── test_project_switching.py     # Project switching tests
├── test_date_filtering.py        # Date filter tests
├── test_thread_safety.py         # Threading tests
├── test_accordion_sections.py    # Sidebar section tests
└── test_timeline_queries.py      # SQL query tests
```

#### Step 1: Setup Test Infrastructure (2 hours)

**File:** `tests/conftest.py`

```python
"""
Pytest fixtures and configuration.
"""
import pytest
import os
import tempfile
from reference_db import ReferenceDB


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    db = ReferenceDB(path)

    yield db, path

    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def sample_project(temp_db):
    """Create sample project with test data."""
    db, path = temp_db

    # Create project
    project_id = db.add_project("Test Project", "/test/path")

    # Add sample photos
    db.add_photo_metadata(project_id, "/test/photo1.jpg", ...)
    db.add_photo_metadata(project_id, "/test/photo2.jpg", ...)

    yield db, project_id
```

**File:** `tests/__init__.py` (empty)

#### Step 2: Project Switching Tests (2 hours)

**File:** `tests/test_project_switching.py`

```python
"""
Test project switching updates all layouts correctly.
"""
import pytest
from layouts.google_layout import GooglePhotosLayout


def test_project_switch_updates_layout(sample_project, qtbot):
    """Test that switching projects updates GooglePhotosLayout."""
    db, project_id = sample_project

    # Create layout
    layout = GooglePhotosLayout(None)
    qtbot.addWidget(layout)

    # Switch project
    layout.set_project(project_id)

    # Verify project ID updated
    assert layout.get_current_project() == project_id


def test_project_switch_clears_filters(sample_project, qtbot):
    """Test that switching projects clears active filters."""
    db, project_id = sample_project

    layout = GooglePhotosLayout(None)
    qtbot.addWidget(layout)

    # Set filter
    layout.filter_by_date(year=2024)

    # Switch project
    layout.set_project(project_id)

    # Verify filters cleared
    assert layout.current_filter_year is None
```

#### Step 3: Thread Safety Tests (2 hours)

**File:** `tests/test_thread_safety.py`

```python
"""
Test thread safety of database access.
"""
import pytest
import threading
from reference_db import ReferenceDB


def test_concurrent_database_access(temp_db):
    """Test that multiple threads can access database safely."""
    db, path = temp_db

    errors = []

    def worker():
        try:
            # Each thread creates its own ReferenceDB instance
            thread_db = ReferenceDB(path)
            projects = thread_db.list_projects()
        except Exception as e:
            errors.append(e)

    # Start 10 concurrent threads
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # No errors should occur
    assert len(errors) == 0
```

#### Step 4: Timeline Query Tests (2 hours)

**File:** `tests/test_timeline_queries.py`

```python
"""
Test SQL queries for timeline loading.
"""
import pytest


def test_load_photos_with_year_filter(sample_project):
    """Test that year filter returns correct photos."""
    db, project_id = sample_project

    # Query with year filter
    query = """
        SELECT path FROM photo_metadata pm
        JOIN project_images pi ON pm.path = pi.image_path
        WHERE pi.project_id = ?
        AND strftime('%Y', pm.created_date) = ?
    """

    with db._connect() as conn:
        cur = conn.cursor()
        cur.execute(query, (project_id, "2024"))
        results = cur.fetchall()

    # Verify results
    assert len(results) > 0
```

#### Step 5: Accordion Section Tests (2 hours)

**File:** `tests/test_accordion_sections.py`

```python
"""
Test accordion sidebar sections.
"""
import pytest
from ui.accordion_sidebar.folders_section import FoldersSection


def test_folders_section_load(sample_project, qtbot):
    """Test that folders section loads correctly."""
    db, project_id = sample_project

    section = FoldersSection()
    qtbot.addWidget(section)

    # Set project
    section.set_project(project_id)

    # Reload
    with qtbot.waitSignal(section.loading_finished, timeout=5000):
        section.reload()

    # Verify items loaded
    assert section.tree.topLevelItemCount() > 0
```

#### Validation Checklist

- [ ] Test infrastructure setup (conftest.py)
- [ ] All 5 test files created
- [ ] Tests pass with pytest
- [ ] Code coverage > 60% for critical paths
- [ ] CI/CD integration (if applicable)

#### Files to Create
- `tests/conftest.py` (100 lines)
- `tests/test_project_switching.py` (150 lines)
- `tests/test_date_filtering.py` (150 lines)
- `tests/test_thread_safety.py` (100 lines)
- `tests/test_accordion_sections.py` (150 lines)
- `tests/test_timeline_queries.py` (150 lines)

---

## 📊 Success Metrics

### Code Quality

| Metric | Before | Target | How to Measure |
|--------|--------|--------|----------------|
| **Interface Coverage** | 0% | 100% | All layouts implement BaseLayout |
| **File Size (accordion)** | 94KB | <30KB | Lines of code in main file |
| **Module Count** | 1 | 8 | Number of files in accordion_sidebar/ |
| **Test Coverage** | 0% | 60%+ | pytest-cov coverage report |
| **Type Safety** | None | Basic | mypy passes on layouts/ |

### Maintainability

- **Navigation Time** - Time to find specific method in accordion sidebar
  - Before: 30+ seconds (Ctrl+F required)
  - After: <5 seconds (know which module to check)

- **Test Addition** - Time to add new section test
  - Before: N/A (no test infrastructure)
  - After: 15 minutes (copy existing pattern)

- **Bug Fix Time** - Time to fix section-specific bug
  - Before: 1+ hours (search 2000 lines)
  - After: 15 minutes (check specific module)

---

## 🚀 Implementation Schedule

### Week 1: Interface Definition
- **Day 1-2:** Task 3.1 - BaseLayout interface (8 hours)
- **Day 3:** Validation and testing

### Week 2: Modularization
- **Day 1-2:** Task 3.2 - AccordionSidebar refactoring (12 hours)
- **Day 3:** Integration testing

### Week 3: Testing
- **Day 1-2:** Task 3.3 - Unit test creation (10 hours)
- **Day 3:** Documentation and review

---

## 🧪 Testing Strategy

### Manual Testing
1. **Smoke Test** - Basic functionality after each task
2. **Regression Test** - Existing features still work
3. **Integration Test** - Components work together

### Automated Testing
1. **Unit Tests** - Individual component tests
2. **Type Checking** - mypy validation
3. **Coverage** - pytest-cov reports

---

## 📝 Dependencies

### Prerequisites
- ✅ Phase 1 complete (safety fixes)
- ✅ Phase 2 complete (performance improvements)
- Python 3.10+
- PySide6
- pytest (for testing)
- pytest-qt (for Qt testing)
- mypy (for type checking)

### Install Test Dependencies
```bash
pip install pytest pytest-qt pytest-cov mypy
```

---

## 🔄 Rollback Plan

If any task causes issues:

1. **Keep git commits atomic** - One task per commit
2. **Tag stable points** - After each completed task
3. **Easy rollback** - `git revert <commit>` or `git reset --hard <tag>`

---

## 📚 Documentation Updates

After Phase 3 completion:

- [ ] Update ARCHITECTURE.md with new module structure
- [ ] Add docstrings to all new interfaces
- [ ] Create TESTING.md guide
- [ ] Update CONTRIBUTING.md with testing requirements

---

**Phase 3 Status:** 📋 **READY TO START**
**Estimated Completion:** 3 weeks (30 hours)
**Risk Level:** 🟢 **LOW** - No critical path changes, mostly refactoring

**Ready to begin when you are!** 🚀

**Last Updated:** 2025-12-12
**Author:** Claude (Deep Audit Implementation)
