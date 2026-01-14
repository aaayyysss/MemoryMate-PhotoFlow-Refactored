# GoogleLayout Accordion Sidebar - Implementation Plan
**Date:** 2025-12-16
**Branch:** claude/audit-accordion-sidebar-BXWgy
**Based on:** ACCORDION_SIDEBAR_AUDIT_REPORT.md

---

## Overview

This implementation plan addresses the critical bugs and missing components identified in the accordion sidebar audit. Work is organized into 3 phases with clear priorities and dependencies.

---

## Phase 1: Critical Bug Fixes (Immediate)
**Priority:** P0 - Must fix before any new development
**Estimated Time:** 30 minutes
**Risk:** Low - Simple deletions, no logic changes

### Task 1.1: Fix Duplicate Device Signal Connections
**File:** `ui/accordion_sidebar/__init__.py`
**Lines:** 257-277
**Severity:** HIGH

**Current Code:**
```python
# Lines 254-277
# Devices section
devices = self.section_logic.get("devices")
if devices and hasattr(devices, 'deviceSelected'):
    devices.deviceSelected.connect(self.selectDevice.emit)

# Devices section  [DUPLICATE 1]
devices = self.section_logic.get("devices")
if devices and hasattr(devices, 'deviceSelected'):
    devices.deviceSelected.connect(self.selectDevice.emit)

# Devices section  [DUPLICATE 2]
devices = self.section_logic.get("devices")
if devices and hasattr(devices, 'deviceSelected'):
    devices.deviceSelected.connect(self.selectDevice.emit)

# Devices section  [DUPLICATE 3]
devices = self.section_logic.get("devices")
if devices and hasattr(devices, 'deviceSelected'):
    devices.deviceSelected.connect(self.selectDevice.emit)

# Devices section  [DUPLICATE 4]
devices = self.section_logic.get("devices")
if devices and hasattr(devices, 'deviceSelected'):
    devices.deviceSelected.connect(self.selectDevice.emit)
```

**Fix:**
Delete lines 259-277 (4 duplicate blocks)
Keep only lines 254-257 (first occurrence)

**Expected Result:**
```python
# Devices section
devices = self.section_logic.get("devices")
if devices and hasattr(devices, 'deviceSelected'):
    devices.deviceSelected.connect(self.selectDevice.emit)

# Quick section  [continues with next section]
quick = self.section_logic.get("quick")
...
```

**Testing:**
1. Run init.sh to verify no syntax errors
2. Load accordion sidebar in application
3. Click device section
4. Verify deviceSelected signal fires exactly once
5. Check logs for duplicate signal emissions

**Success Criteria:**
- ✅ File reduced by ~20 lines
- ✅ No syntax errors
- ✅ Device selection works correctly
- ✅ Signal fires exactly once per device selection

---

### Task 1.2: Fix Duplicate _on_person_selected Method Definitions
**File:** `ui/accordion_sidebar/__init__.py`
**Lines:** 289-487
**Severity:** CRITICAL

**Current Code:**
10 identical definitions of `_on_person_selected` (20 lines each = 200 lines total)

**Fix:**
Delete lines 289-466 (9 duplicate definitions)
Keep only lines 469-487 (last occurrence)

**Implementation Steps:**
1. Verify lines 469-487 contain the complete, correct implementation
2. Delete lines 289-466 (inclusive)
3. Verify method is now defined exactly once
4. Check no other code references the deleted lines

**Expected Result:**
```python
# --- People selection helpers ---
def _on_person_selected(self, branch_key: str):
    """Track active person selection, support toggling, and emit filter signal."""
    people_logic = self.section_logic.get("people")

    # Toggle selection when clicking the same person again
    if self._active_person_branch and branch_key == self._active_person_branch:
        self._active_person_branch = None
        if hasattr(people_logic, "set_active_branch"):
            people_logic.set_active_branch(None)
        self.selectPerson.emit("")
        return

    self._active_person_branch = branch_key

    if hasattr(people_logic, "set_active_branch"):
        people_logic.set_active_branch(branch_key)

    self.selectPerson.emit(branch_key)

def _expand_section(self, section_id: str):  # Next method continues here
    ...
```

**Testing:**
1. Run init.sh to verify no syntax errors
2. Search file for `def _on_person_selected` - should find exactly 1 match
3. Load accordion sidebar in application
4. Click person card - verify selection works
5. Click same person again - verify toggle works
6. Click different person - verify selection changes

**Success Criteria:**
- ✅ File reduced by ~180 lines
- ✅ No syntax errors
- ✅ Method defined exactly once
- ✅ Person selection works correctly
- ✅ Toggle behavior works correctly

---

### Task 1.3: Verify No Other Duplicates
**File:** `ui/accordion_sidebar/__init__.py`
**Severity:** MEDIUM

**Investigation Steps:**
1. Search for duplicate method definitions:
   ```bash
   grep -n "^    def " ui/accordion_sidebar/__init__.py | sort | uniq -d
   ```

2. Search for duplicate signal connections:
   ```bash
   grep -n "\.connect(" ui/accordion_sidebar/__init__.py | sort | uniq -c | grep -v "^ *1 "
   ```

3. Manual review of `_connect_signals()` method

**Expected Result:**
- No other duplicate method definitions
- No other duplicate signal connections

**If Duplicates Found:**
- Document in bug report
- Fix following same pattern as Tasks 1.1 and 1.2

---

### Task 1.4: Post-Fix Cleanup
**Severity:** LOW

**Actions:**
1. Run code formatter (if project uses one):
   ```bash
   black ui/accordion_sidebar/__init__.py
   ```

2. Verify file structure:
   ```bash
   # Should be ~720 lines (901 - 181 duplicates)
   wc -l ui/accordion_sidebar/__init__.py
   ```

3. Run linter:
   ```bash
   pylint ui/accordion_sidebar/__init__.py
   ```

4. Update ClaudeProgress.txt with fix summary

---

## Phase 2: Address Incomplete Features (Short-Term)
**Priority:** P1 - Required before release
**Estimated Time:** 2-3 hours
**Risk:** Medium - New implementation required

### Task 2.1: Quick Section - Decision Point

**Options:**

**Option A: Implement Quick Dates Section**
- Estimated Time: 2-3 hours
- Complexity: Medium
- User Impact: High (valuable feature)

**Features to Implement:**
- Today
- Yesterday
- Last 7 days
- Last 30 days
- This month
- Last month
- This year
- Last year

**Implementation:**
1. Update `quick_section.py`:
   - Remove TODO comments
   - Implement `load_section()` method
   - Implement `create_content_widget()` with date buttons
   - Add click handlers that emit `quickDateSelected` signal

2. Update `__init__.py`:
   - Connect `quickDateSelected` signal to date filtering logic

3. Add to `FeatureList.json`:
   ```json
   {
     "id": "accordion-sidebar-quick-dates",
     "name": "Quick Dates Section",
     "description": "Quick access to common date filters (Today, Yesterday, etc.)",
     "status": "passing",
     "priority": "medium",
     "dependencies": ["date-filtering"],
     "tests": [
       "Quick dates section displays all quick date options",
       "Clicking quick date filters photo grid",
       "Quick date calculations are accurate"
     ]
   }
   ```

**Option B: Remove Quick Section**
- Estimated Time: 30 minutes
- Complexity: Low
- User Impact: Low (feature never worked)

**Implementation:**
1. Remove from `__init__.py`:
   - Remove QuickSection import
   - Remove from `_create_sections()`
   - Remove from `_connect_signals()`

2. Delete `quick_section.py`

3. Update navigation bar to remove quick dates icon

**Recommendation:** **Option A** - Implement the feature
- Provides real user value
- Completes the sidebar feature set
- Aligns with Google Photos UX (which has similar quick filters)

---

### Task 2.2: Implement Quick Dates Section (If Option A Chosen)

**File:** `ui/accordion_sidebar/quick_section.py`

**New Implementation:**
```python
# ui/accordion_sidebar/quick_section.py
import logging
from datetime import datetime, timedelta
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PySide6.QtCore import Signal, Qt
from .base_section import BaseSection

logger = logging.getLogger(__name__)


class QuickSection(BaseSection):
    """
    Quick dates section implementation.

    Provides quick access to common date filters:
    - Today
    - Yesterday
    - Last 7 days
    - Last 30 days
    - This month
    - Last month
    - This year
    - Last year
    """

    quickDateSelected = Signal(str)  # date range identifier

    def __init__(self, parent=None):
        super().__init__(parent)
        self._quick_dates = [
            ("today", "Today"),
            ("yesterday", "Yesterday"),
            ("last_7_days", "Last 7 days"),
            ("last_30_days", "Last 30 days"),
            ("this_month", "This month"),
            ("last_month", "Last month"),
            ("this_year", "This year"),
            ("last_year", "Last year"),
        ]

    def get_section_id(self) -> str:
        return "quick"

    def get_title(self) -> str:
        return "Quick Dates"

    def get_icon(self) -> str:
        return "⚡"

    def load_section(self) -> None:
        """Load quick dates section data."""
        logger.info("[QuickSection] Loading quick dates")
        self._loading = False
        # Return quick dates config
        return self._quick_dates

    def create_content_widget(self, data):
        """Create quick dates section widget."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        quick_dates = data if data else self._quick_dates

        for date_id, label in quick_dates:
            btn = QPushButton(label)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #f8f9fa;
                    border: 1px solid #e8eaed;
                    border-radius: 4px;
                    padding: 8px 12px;
                    text-align: left;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #e8f0fe;
                    border-color: #1a73e8;
                }
                QPushButton:pressed {
                    background-color: #d2e3fc;
                }
            """)
            btn.clicked.connect(lambda checked, d=date_id: self._on_quick_date_clicked(d))
            layout.addWidget(btn)

        layout.addStretch()
        return container

    def _on_quick_date_clicked(self, date_id: str):
        """Handle quick date button click."""
        logger.info(f"[QuickSection] Quick date selected: {date_id}")

        # Calculate actual date range based on date_id
        date_range = self._calculate_date_range(date_id)

        # Emit signal with date range string
        self.quickDateSelected.emit(date_range)

    def _calculate_date_range(self, date_id: str) -> str:
        """
        Calculate date range string for quick date filter.

        Returns date string in format compatible with date filtering:
        - "2025-12-16" for single day
        - "2025-12-10:2025-12-16" for date range
        - "2025-12" for month
        - "2025" for year
        """
        today = datetime.now().date()

        if date_id == "today":
            return today.strftime("%Y-%m-%d")

        elif date_id == "yesterday":
            yesterday = today - timedelta(days=1)
            return yesterday.strftime("%Y-%m-%d")

        elif date_id == "last_7_days":
            start = today - timedelta(days=6)
            return f"{start.strftime('%Y-%m-%d')}:{today.strftime('%Y-%m-%d')}"

        elif date_id == "last_30_days":
            start = today - timedelta(days=29)
            return f"{start.strftime('%Y-%m-%d')}:{today.strftime('%Y-%m-%d')}"

        elif date_id == "this_month":
            return today.strftime("%Y-%m")

        elif date_id == "last_month":
            first_of_month = today.replace(day=1)
            last_month = first_of_month - timedelta(days=1)
            return last_month.strftime("%Y-%m")

        elif date_id == "this_year":
            return today.strftime("%Y")

        elif date_id == "last_year":
            last_year = today.year - 1
            return str(last_year)

        else:
            logger.warning(f"[QuickSection] Unknown date_id: {date_id}")
            return today.strftime("%Y-%m-%d")
```

**Testing Plan:**
1. Unit tests for `_calculate_date_range()` method
2. UI test for button rendering
3. Integration test for signal emission
4. E2E test for photo grid filtering

---

## Phase 3: Comprehensive Test Coverage (Medium-Term)
**Priority:** P1 - Required before release
**Estimated Time:** 8-10 hours
**Risk:** Low - Tests don't affect production code

### Task 3.1: Set Up Qt Testing Infrastructure

**File:** `tests/conftest_qt.py`

**Implementation:**
```python
# tests/conftest_qt.py
"""Qt-specific test fixtures for accordion sidebar tests."""

import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt


@pytest.fixture(scope="session")
def qapp():
    """
    QApplication fixture for Qt tests.

    Creates a single QApplication instance for the entire test session.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Don't quit here - let pytest handle cleanup


@pytest.fixture
def qtbot(qapp, qtbot):
    """
    Combine QApplication with pytest-qt's qtbot fixture.

    Requires: pip install pytest-qt
    """
    return qtbot


@pytest.fixture
def test_project_id():
    """Test project ID for accordion sidebar tests."""
    return 1


@pytest.fixture
def accordion_sidebar(qapp, test_db_path, test_project_id):
    """
    AccordionSidebar fixture with test database.

    Creates a fresh AccordionSidebar instance for each test.
    """
    # Import here to avoid circular dependencies
    from ui.accordion_sidebar import AccordionSidebar

    # Override database path for testing
    import db_config
    original_db_path = db_config.DB_PATH
    db_config.DB_PATH = str(test_db_path)

    sidebar = AccordionSidebar(project_id=test_project_id)

    yield sidebar

    # Cleanup
    sidebar.cleanup()
    db_config.DB_PATH = original_db_path


@pytest.fixture
def mock_face_clusters(test_db_path, test_project_id):
    """Create mock face clusters in test database."""
    import sqlite3
    conn = sqlite3.connect(str(test_db_path))
    cur = conn.cursor()

    # Insert mock face clusters
    mock_data = [
        (test_project_id, "face_john", "John Doe", None, 15),
        (test_project_id, "face_jane", "Jane Smith", None, 12),
        (test_project_id, "face_bob", "Bob Johnson", None, 8),
    ]

    cur.executemany(
        """
        INSERT INTO face_branch_reps (project_id, branch_key, branch_name, rep_thumb_blob, face_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        mock_data
    )
    conn.commit()
    conn.close()

    return mock_data


@pytest.fixture
def mock_folders(test_db_path, test_project_id):
    """Create mock folder hierarchy in test database."""
    import sqlite3
    conn = sqlite3.connect(str(test_db_path))
    cur = conn.cursor()

    # Insert mock folders
    mock_data = [
        (1, "/photos/2024", test_project_id, 50),
        (2, "/photos/2023", test_project_id, 30),
        (3, "/photos/2024/vacation", test_project_id, 20),
    ]

    cur.executemany(
        """
        INSERT INTO folders (folder_id, path, project_id, photo_count)
        VALUES (?, ?, ?, ?)
        """,
        mock_data
    )
    conn.commit()
    conn.close()

    return mock_data
```

**Dependencies:**
```bash
pip install pytest-qt
```

---

### Task 3.2: Write Unit Tests for AccordionSidebar

**File:** `tests/test_accordion_sidebar_unit.py`

**Test Coverage:**
- Initialization
- Section expansion/collapse
- Signal connections
- Generation token system
- Cleanup

**Sample Tests:**
```python
# tests/test_accordion_sidebar_unit.py
"""Unit tests for AccordionSidebar class."""

import pytest
from ui.accordion_sidebar import AccordionSidebar


class TestAccordionSidebarInit:
    """Test AccordionSidebar initialization."""

    def test_creates_with_project_id(self, accordion_sidebar):
        """Test AccordionSidebar initializes with project_id."""
        assert accordion_sidebar.project_id == 1
        assert accordion_sidebar.expanded_section_id is None
        assert accordion_sidebar._active_person_branch is None

    def test_creates_all_sections(self, accordion_sidebar):
        """Test all expected sections are created."""
        expected_sections = ["folders", "dates", "videos", "people", "devices", "quick"]
        assert set(accordion_sidebar.section_widgets.keys()) == set(expected_sections)

    def test_creates_navigation_buttons(self, accordion_sidebar):
        """Test navigation buttons are created for all sections."""
        expected_sections = ["folders", "dates", "videos", "people", "devices", "quick"]
        assert set(accordion_sidebar.nav_buttons.keys()) == set(expected_sections)


class TestSectionExpansion:
    """Test section expansion/collapse behavior."""

    def test_expand_section_sets_expanded_state(self, accordion_sidebar):
        """Test expanding a section sets expanded_section_id."""
        accordion_sidebar._expand_section("people")
        assert accordion_sidebar.expanded_section_id == "people"

    def test_expand_section_collapses_others(self, accordion_sidebar):
        """Test expanding one section collapses all others."""
        # Expand folders first
        accordion_sidebar._expand_section("folders")
        assert accordion_sidebar.section_widgets["folders"].is_expanded()

        # Expand people - folders should collapse
        accordion_sidebar._expand_section("people")
        assert accordion_sidebar.section_widgets["people"].is_expanded()
        assert not accordion_sidebar.section_widgets["folders"].is_expanded()

    def test_expand_section_emits_signal(self, accordion_sidebar, qtbot):
        """Test expanding section emits sectionExpanding signal."""
        with qtbot.waitSignal(accordion_sidebar.sectionExpanding, timeout=1000) as blocker:
            accordion_sidebar._expand_section("dates")
        assert blocker.args == ["dates"]


class TestSignalConnections:
    """Test signal connections and propagation."""

    def test_person_selected_emits_signal(self, accordion_sidebar, qtbot, mock_face_clusters):
        """Test selecting person emits selectPerson signal."""
        with qtbot.waitSignal(accordion_sidebar.selectPerson, timeout=1000) as blocker:
            accordion_sidebar._on_person_selected("face_john")
        assert blocker.args == ["face_john"]

    def test_person_toggle_emits_empty_string(self, accordion_sidebar, qtbot, mock_face_clusters):
        """Test toggling person selection emits empty string."""
        # Select first
        accordion_sidebar._on_person_selected("face_john")

        # Toggle (select same person again)
        with qtbot.waitSignal(accordion_sidebar.selectPerson, timeout=1000) as blocker:
            accordion_sidebar._on_person_selected("face_john")
        assert blocker.args == [""]


class TestGenerationTokens:
    """Test generation token staleness prevention."""

    def test_generation_increments_on_load(self, accordion_sidebar):
        """Test section generation increments on load."""
        people_section = accordion_sidebar.section_logic.get("people")
        initial_gen = people_section._generation

        people_section.load_section()

        assert people_section._generation == initial_gen + 1

    def test_stale_data_discarded(self, accordion_sidebar):
        """Test stale data is discarded based on generation token."""
        people_section = accordion_sidebar.section_logic.get("people")

        # Load section (increments generation)
        people_section.load_section()
        current_gen = people_section._generation

        # Simulate stale data arriving with old generation
        old_gen = current_gen - 1
        accordion_sidebar._on_section_loaded("people", old_gen, [])

        # Section content should NOT be updated
        # (Verify by checking widget content is still placeholder/empty)


class TestCleanup:
    """Test resource cleanup."""

    def test_cleanup_closes_database(self, accordion_sidebar):
        """Test cleanup closes database connection."""
        accordion_sidebar.cleanup()
        # Verify db is closed (accessing it should raise an error or return None)

    def test_cleanup_cleans_all_sections(self, accordion_sidebar):
        """Test cleanup calls cleanup on all sections."""
        accordion_sidebar.cleanup()
        # Each section's cleanup should be called
        # (Can verify by mocking section cleanup methods)
```

**Estimated Tests:** 15-20 unit tests

---

### Task 3.3: Write Integration Tests

**File:** `tests/test_accordion_sidebar_integration.py`

**Test Coverage:**
- AccordionSidebar + Database integration
- AccordionSidebar + Section modules integration
- Signal flow from section → accordion → layout

**Sample Tests:**
```python
# tests/test_accordion_sidebar_integration.py
"""Integration tests for AccordionSidebar with database and sections."""

import pytest
from ui.accordion_sidebar import AccordionSidebar


class TestPeopleSectionIntegration:
    """Test People section integration with database."""

    def test_people_section_loads_from_database(self, accordion_sidebar, mock_face_clusters):
        """Test people section loads face clusters from database."""
        accordion_sidebar._expand_section("people")

        # Wait for async load
        # Verify people section shows 3 person cards (from mock_face_clusters)

    def test_person_merge_updates_database(self, accordion_sidebar, mock_face_clusters):
        """Test merging people updates database correctly."""
        # Trigger merge: john + jane → john
        # Verify database shows merged cluster
        # Verify UI reloads and shows updated person card


class TestFoldersSectionIntegration:
    """Test Folders section integration with database."""

    def test_folders_section_loads_from_database(self, accordion_sidebar, mock_folders):
        """Test folders section loads folder tree from database."""
        accordion_sidebar._expand_section("folders")

        # Wait for async load
        # Verify folder tree shows mock folders


class TestSignalPropagation:
    """Test signals propagate correctly between components."""

    def test_person_selection_signal_propagates(self, accordion_sidebar, mock_face_clusters):
        """Test person selection signal propagates from section to accordion."""
        # Expand people section
        accordion_sidebar._expand_section("people")

        # Simulate clicking person card in section
        people_section = accordion_sidebar.section_logic.get("people")

        # Verify signal propagates to accordion
        # Verify accordion emits selectPerson signal
```

**Estimated Tests:** 10-12 integration tests

---

### Task 3.4: Write End-to-End Tests

**File:** `tests/test_accordion_sidebar_e2e.py`

**Test Coverage:**
- Full user workflows
- UI interactions (clicks, drags, right-clicks)
- Multi-step scenarios

**Sample Tests:**
```python
# tests/test_accordion_sidebar_e2e.py
"""End-to-end tests for AccordionSidebar user workflows."""

import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest


class TestUserWorkflows:
    """Test complete user workflows."""

    def test_user_filters_by_person(self, accordion_sidebar, qtbot, mock_face_clusters):
        """
        Test complete workflow:
        1. User clicks People section
        2. Section expands and loads
        3. User clicks person card
        4. Photo grid filters to that person
        """
        # Click people nav button
        people_btn = accordion_sidebar.nav_buttons["people"]
        QTest.mouseClick(people_btn, Qt.LeftButton)

        # Wait for section to expand
        qtbot.wait(100)

        # Verify section is expanded
        assert accordion_sidebar.expanded_section_id == "people"

        # Wait for data to load
        qtbot.wait(500)

        # Get people section widget
        people_section = accordion_sidebar.section_logic.get("people")

        # Simulate clicking first person card
        # (This requires accessing the PersonCard widget)

        # Verify selectPerson signal emitted

    def test_user_merges_people_via_drag_drop(self, accordion_sidebar, qtbot, mock_face_clusters):
        """
        Test drag-and-drop face merge:
        1. User drags person card A
        2. User drops on person card B
        3. Merge confirmation dialog appears
        4. User confirms
        5. Faces merge in database
        6. People section reloads
        """
        # Expand people section
        accordion_sidebar._expand_section("people")
        qtbot.wait(500)

        # Get person cards
        # Simulate drag from card A to card B
        # Verify merge confirmation dialog
        # Confirm merge
        # Verify database updated
        # Verify UI reloaded

    def test_user_renames_person_via_context_menu(self, accordion_sidebar, qtbot, mock_face_clusters):
        """
        Test context menu rename:
        1. User right-clicks person card
        2. Context menu appears
        3. User clicks "Rename"
        4. Rename dialog appears
        5. User enters new name
        6. Database updates
        7. UI reloads with new name
        """
        # Expand people section
        accordion_sidebar._expand_section("people")
        qtbot.wait(500)

        # Right-click person card
        # Verify context menu appears
        # Click "Rename" action
        # Verify rename dialog
        # Enter new name
        # Confirm
        # Verify database updated
        # Verify UI shows new name


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_rapid_section_switching(self, accordion_sidebar, qtbot):
        """Test rapidly switching between sections doesn't cause errors."""
        sections = ["folders", "dates", "videos", "people", "devices"]

        for section in sections * 3:  # Cycle through 3 times
            accordion_sidebar._expand_section(section)
            qtbot.wait(10)  # Very short delay

        # Verify no crashes, no errors
        # Verify only last section is expanded

    def test_empty_database(self, accordion_sidebar, qtbot):
        """Test accordion works correctly with empty database."""
        # Expand all sections
        for section_id in accordion_sidebar.section_widgets.keys():
            accordion_sidebar._expand_section(section_id)
            qtbot.wait(200)

        # Verify no crashes
        # Verify empty states display correctly
```

**Estimated Tests:** 8-10 E2E tests

---

### Task 3.5: Test Execution and Coverage

**Dependencies:**
```bash
pip install pytest pytest-qt pytest-cov
```

**Run Tests:**
```bash
# Run all accordion tests
pytest tests/test_accordion_sidebar_*.py -v

# Run with coverage
pytest tests/test_accordion_sidebar_*.py --cov=ui.accordion_sidebar --cov-report=html

# Run specific test class
pytest tests/test_accordion_sidebar_unit.py::TestAccordionSidebarInit -v

# Run in parallel (faster)
pip install pytest-xdist
pytest tests/test_accordion_sidebar_*.py -n auto
```

**Coverage Target:**
- Minimum: 70%
- Target: 80%+
- Stretch: 90%+

---

## Phase 4: Documentation and Polish (Long-Term)
**Priority:** P2 - Nice to have
**Estimated Time:** 2-3 hours
**Risk:** Low

### Task 4.1: Update FeatureList.json

Add quick dates feature (if implemented):
```json
{
  "id": "accordion-sidebar-quick-dates",
  "name": "Quick Dates Section",
  "description": "Quick access to common date filters (Today, Yesterday, This Week, etc.)",
  "status": "passing",
  "priority": "medium",
  "dependencies": ["date-filtering"],
  "tests": [
    "Quick dates section displays all quick date options",
    "Clicking Today filters to today's photos",
    "Clicking Last 7 days filters to past week",
    "Date calculations are accurate"
  ]
}
```

Add test coverage feature:
```json
{
  "id": "accordion-sidebar-test-coverage",
  "name": "Accordion Sidebar Test Suite",
  "description": "Comprehensive unit, integration, and E2E tests for accordion sidebar",
  "status": "passing",
  "priority": "critical",
  "dependencies": ["accordion-sidebar-modular-architecture"],
  "tests": [
    "Unit tests cover AccordionSidebar class (80%+ coverage)",
    "Integration tests verify database integration",
    "E2E tests cover user workflows",
    "All tests pass in CI/CD pipeline"
  ]
}
```

---

### Task 4.2: Update ClaudeProgress.txt

Add new session entry:
```markdown
---

## Session 2025-12-16 (2)
**Branch:** claude/audit-accordion-sidebar-BXWgy
**Goal:** Audit accordion sidebar and fix critical bugs

### Work Completed:
1. ✅ Comprehensive audit of accordion sidebar against disciplined workflow
2. ✅ Identified 3 critical bugs:
   - Duplicate device signal connections (5x)
   - Duplicate _on_person_selected method definitions (10x)
   - Quick section not implemented
3. ✅ Fixed duplicate signal connections (reduced 5 to 1)
4. ✅ Fixed duplicate method definitions (removed 180 lines of dead code)
5. ✅ [If applicable] Implemented quick dates section
6. ✅ [If applicable] Created comprehensive test suite (25+ tests)

### Files Modified:
- ui/accordion_sidebar/__init__.py: Fixed duplicates, reduced from 901 to ~720 lines
- ui/accordion_sidebar/quick_section.py: [If implemented] Full implementation
- tests/conftest_qt.py: Qt testing fixtures
- tests/test_accordion_sidebar_unit.py: Unit tests
- tests/test_accordion_sidebar_integration.py: Integration tests
- tests/test_accordion_sidebar_e2e.py: E2E tests
- FeatureList.json: Added test coverage feature
- ACCORDION_SIDEBAR_AUDIT_REPORT.md: Complete audit documentation
- ACCORDION_SIDEBAR_FIX_IMPLEMENTATION_PLAN.md: This implementation plan

### Status:
- Accordion sidebar code quality significantly improved
- Critical bugs fixed
- [If applicable] Test coverage at 80%+
- [If applicable] Quick dates section complete
- Ready for production deployment

### Metrics:
- Lines of code reduced: ~180 lines (dead code removed)
- Bugs fixed: 3 critical
- Tests added: [X] unit + [X] integration + [X] E2E = [X] total
- Test coverage: [X]%
```

---

### Task 4.3: Add Code Documentation

**Files to Document:**
- `ui/accordion_sidebar/__init__.py` - Add comprehensive module docstring
- `ui/accordion_sidebar/quick_section.py` - [If implemented] Add usage examples
- Test files - Add docstrings explaining test strategy

**Example Module Docstring:**
```python
"""
Accordion Sidebar - Main Orchestrator

This module provides the main AccordionSidebar widget for the GooglePhotosLayout.
The accordion sidebar is a modular, collapsible navigation panel that allows users
to filter photos by:

- Folders (hierarchical folder tree)
- Dates (year > month > day hierarchy)
- Videos (video type filters)
- People (face clusters with merge support)
- Devices (import sources)
- Quick dates (Today, Yesterday, Last 7 days, etc.)

Architecture:
-----------
The AccordionSidebar follows a modular architecture with separate section modules:

    AccordionSidebar (__init__.py)
    ├── FoldersSection (folders_section.py)
    ├── DatesSection (dates_section.py)
    ├── VideosSection (videos_section.py)
    ├── PeopleSection (people_section.py)
    ├── DevicesSection (devices_section.py)
    └── QuickSection (quick_section.py)

Each section implements the BaseSection interface and handles:
- Data loading (thread-safe, async)
- UI rendering (create_content_widget)
- User interactions (clicks, drags, context menus)
- Signal emissions (for filtering)

Signals:
--------
The AccordionSidebar emits these signals to parent layouts:

- selectFolder(int) - Folder selected, filter by folder_id
- selectDate(str) - Date selected, filter by date string
- selectPerson(str) - Person selected, filter by branch_key
- selectVideo(str) - Video filter selected
- selectDevice(str) - Device selected, filter by root path
- personMerged(str, str) - People merged (source, target)
- personDeleted(str) - Person deleted (branch_key)

Thread Safety:
-------------
All section loading is performed on background threads using:
- Per-thread ReferenceDB instances (no shared connections)
- Generation tokens to prevent stale data
- Qt signals for thread-safe UI updates

Example Usage:
-------------
    from ui.accordion_sidebar import AccordionSidebar

    sidebar = AccordionSidebar(project_id=1)

    # Connect signals to photo grid filtering
    sidebar.selectPerson.connect(photo_grid.filter_by_person)
    sidebar.selectDate.connect(photo_grid.filter_by_date)

    # Clean up when done
    sidebar.cleanup()

Testing:
--------
See tests/ directory for comprehensive test suite:
- test_accordion_sidebar_unit.py - Unit tests
- test_accordion_sidebar_integration.py - Integration tests
- test_accordion_sidebar_e2e.py - End-to-end tests

For more information, see:
- SIDEBAR_ACCORDION_DESIGN.md - Design specification
- ACCORDION_SIDEBAR_AUDIT_REPORT.md - Audit report
- FeatureList.json - Feature tracking
"""
```

---

## Testing Checklist

### Pre-Fix Testing
- [ ] Run init.sh successfully
- [ ] Load accordion sidebar in application
- [ ] Verify all sections load
- [ ] Note any errors or warnings in logs

### Post-Fix Testing (Phase 1)
- [ ] Run init.sh successfully
- [ ] File size reduced correctly (~720 lines)
- [ ] No syntax errors
- [ ] All sections load correctly
- [ ] Device section signal fires exactly once
- [ ] Person selection works correctly
- [ ] Person toggle works correctly
- [ ] No duplicate signal emissions in logs
- [ ] No new errors or warnings

### Post-Implementation Testing (Phase 2)
- [ ] Quick dates section displays correctly
- [ ] All quick date buttons work
- [ ] Date calculations are accurate
- [ ] Photo grid filters correctly when quick date selected
- [ ] No errors when switching between quick dates

### Test Suite Testing (Phase 3)
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] All E2E tests pass
- [ ] Test coverage >= 80%
- [ ] No flaky tests
- [ ] Tests run in reasonable time (<2 minutes total)

---

## Success Metrics

### Code Quality
- ✅ File size reduced by ~180 lines (20%)
- ✅ Zero duplicate method definitions
- ✅ Zero duplicate signal connections
- ✅ All linter warnings resolved
- ✅ Code formatted consistently

### Test Coverage
- ✅ Unit test coverage >= 80%
- ✅ Integration test coverage >= 70%
- ✅ E2E tests cover critical workflows
- ✅ All tests pass
- ✅ No flaky tests

### Feature Completeness
- ✅ All sections implemented (including Quick)
- ✅ All sections load correctly
- ✅ All signals emit correctly
- ✅ All user interactions work

### Documentation
- ✅ FeatureList.json updated
- ✅ ClaudeProgress.txt updated
- ✅ Code docstrings added
- ✅ Audit report complete
- ✅ Implementation plan complete

---

## Rollback Plan

If fixes introduce regressions:

1. **Revert commits:**
   ```bash
   git log --oneline  # Find commit hash before fixes
   git revert <commit-hash>
   ```

2. **Keep audit artifacts:**
   - Keep ACCORDION_SIDEBAR_AUDIT_REPORT.md
   - Keep ACCORDION_SIDEBAR_FIX_IMPLEMENTATION_PLAN.md
   - Update ClaudeProgress.txt with rollback reason

3. **Investigate root cause:**
   - Review test failures
   - Check application logs
   - Identify specific regression

4. **Fix forward:**
   - Address root cause
   - Re-apply fixes carefully
   - Add tests to prevent regression

---

## Timeline Estimates

### Phase 1: Critical Bugs (P0)
- Task 1.1: 10 minutes
- Task 1.2: 15 minutes
- Task 1.3: 5 minutes
- Task 1.4: 10 minutes
- **Total: 40 minutes**

### Phase 2: Quick Section (P1)
- Decision: 10 minutes
- Implementation: 2-3 hours
- Testing: 30 minutes
- **Total: 2.5-3.5 hours**

### Phase 3: Test Suite (P1)
- Task 3.1: 1 hour
- Task 3.2: 3 hours
- Task 3.3: 2 hours
- Task 3.4: 2 hours
- Task 3.5: 30 minutes
- **Total: 8.5 hours**

### Phase 4: Documentation (P2)
- Task 4.1: 30 minutes
- Task 4.2: 30 minutes
- Task 4.3: 1 hour
- **Total: 2 hours**

### Grand Total: ~13-14 hours

**Recommended Sprint:**
- Day 1: Phase 1 (bugs) + Start Phase 2 (quick section)
- Day 2: Complete Phase 2 + Start Phase 3 (test infrastructure)
- Day 3: Complete Phase 3 (write tests)
- Day 4: Phase 4 (documentation) + Final review

---

## Conclusion

This implementation plan provides a clear, actionable roadmap to address all issues identified in the audit. By following this plan systematically, we will:

1. ✅ Fix critical bugs immediately (40 minutes)
2. ✅ Complete missing features (2-3 hours)
3. ✅ Achieve comprehensive test coverage (8-10 hours)
4. ✅ Improve documentation (2 hours)

The result will be a production-ready accordion sidebar with high code quality, complete feature set, and comprehensive test coverage that prevents future regressions.

**Next Step:** Begin Phase 1, Task 1.1 - Fix duplicate device signal connections.

---

**End of Implementation Plan**
