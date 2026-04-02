# Google Layout Integration & Design Alignment Strategy
## Sidebar + Main Layout Coordination | 2026-04-02

---

## Overview

The sidebar doesn't exist in isolation—it's part of the larger Google Photos-style layout. This document outlines how to align sidebar improvements with the overall layout architecture and ensure consistent UX across all components.

---

## Current Architecture Problems

### Problem 1: Sidebar vs Content Area Mismatch

**Visual Disconnect:**
```
┌─────────────────────────────────────────────────────┐
│ Toolbar (modern, material design)                   │
├─────────────────────────────────────────────────────┤
│ ┌─────────────────┬─────────────────────────────┐  │
│ │ Sidebar         │ Timeline Grid               │  │
│ │ (cramped,       │ (spacious, modern)          │  │
│ │  cluttered)     │                             │  │
│ │                 │                             │  │
│ │ Inconsistent    │ Clean, airy layout          │  │
│ │ colors/spacing  │                             │  │
│ │                 │                             │  │
│ └─────────────────┴─────────────────────────────┘  │
└─────────────────────────────────────────────────────┘

Issue: Sidebar looks 1.0, content looks 3.0
User experience is jarring and inconsistent
```

### Problem 2: Sidebar Width Inefficiency

**Current State:**
- Sidebar: 260-300px (40% of available space on 1024px screen)
- Content: 724-764px (60% of space)
- **Result:** Timeline grid cramped, sidebar feels bloated

**Proposed State:**
- Sidebar: 240px (25-30% on desktop)
- Content: 760px+ (70-75% of space)
- **Result:** Grid gets more room, sidebar feels focused

**Code Location:** `google_layout.py` line ~450

```python
# CURRENT:
self.left_shell_container.setMinimumWidth(260)
self.left_shell_container.setMaximumWidth(300)
self.splitter.setSizes([280, 1000])  # 28% sidebar

# PROPOSED:
self.left_shell_container.setMinimumWidth(220)
self.left_shell_container.setMaximumWidth(260)
self.splitter.setSizes([240, 1200])  # 20% sidebar
```

### Problem 3: SearchSidebar vs AccordionSidebar Duplication

**Current Structure:**
```python
# google_layout.py:_build_left_shell()
self.left_shell_layout.addWidget(self.search_sidebar, 1)      # Production
self.left_shell_layout.addWidget(self.legacy_container, 0)    # Legacy

# Result: TWO sidebars stacked
# - SearchSidebar: Search hub, discover, people quick
# - AccordionSidebar: 9 accordion sections
# - Users confused by redundant sections
```

**Issue:** "People" appears in both sidebars (redundant, confusing)

**Solution:** Merge into single unified sidebar
- SearchSidebar for search + quick filters
- AccordionSidebar for browse + content exploration
- No overlap

---

## Design Alignment Issues

### Color Consistency

**Current Problem:**
```
Material Design 3 Palette:
├─ Toolbar buttons:     #1a73e8 blue ✓
├─ Sidebar header:      #e8f0fe light blue ✓
├─ Main grid:           #ffffff white ✓
└─ Sidebar header:      ...wait, which shade? 

Different shades of blue used:
- Primary: #1a73e8
- Light: #e8f0fe vs #1a73e8 - Different tone/saturation
- Hover: rgba(26, 115, 232, 0.08) vs rgba(26, 115, 232, 0.10)
- Inactive: #f8f9fa vs #f1f3f4 (both used)
```

**Fix:** Establish single color system used everywhere

```python
# Define in themes.py

MATERIAL_DESIGN_3 = {
    # Primary colors
    'primary': {
        'base': '#1a73e8',      # Google blue
        'container': '#e8f0fe',  # Light blue background
        'on': '#ffffff',         # Text on blue
    },
    
    # Surface colors
    'surface': {
        'primary': '#ffffff',     # Main white
        'secondary': '#f8f9fa',   # Off-white
        'tertiary': '#f1f3f4',    # Light gray
    },
    
    # Outlined colors
    'outline': {
        'primary': '#dadce0',     # Main borders
        'secondary': '#bdc1c6',   # Secondary borders
    },
    
    # Semantic colors
    'success': '#34a853',
    'warning': '#fbbc04',
    'error': '#ea4335',
    
    # Text colors
    'text': {
        'primary': '#202124',
        'secondary': '#5f6368',
        'tertiary': '#9aa0a6',
    }
}
```

---

## Alignment Strategy: 5-Phase Approach

### Phase 1: Sidebar Polish (Week 1)

**Goal:** Make sidebar visually consistent with toolbar/grid

**Changes:**
1. Update color palette to MATERIAL_DESIGN_3
2. Fix typography scale (match toolbar +/- 1pt)
3. Improve spacing (use 8px grid like grid)
4. Add section header left border accent
5. Improve section animations

**Files to Update:**
- `accordion_sidebar.py` (colors, spacing, animation)
- `google_components/widgets.py` (PersonCard styling)
- `layouts/google_layout.py` (toolbar integration)

**Expected Time:** 3-4 days

---

### Phase 2: Navigation Improvements (Week 1-2)

**Goal:** Make sidebar navigation clearer and more discoverable

**Changes:**
1. Redesign nav bar (64px, show labels on hover)
2. Add badges for alerts (red dot on Activity)
3. Improve hover/active state contrast
4. Add keyboard navigation support
5. Align nav bar styling with toolbar

**Files to Update:**
- `accordion_sidebar.py` (AccordionSidebar.__init__)
- `ui/accordion_sidebar/__init__.py` (NavBar component)

**Expected Time:** 2-3 days

---

### Phase 3: Content Reorganization (Week 2)

**Goal:** Better information architecture matching user workflows

**Changes:**
1. Reorder sections (People → Browse → Specialized)
2. Combine duplicate People sections (Search + Accordion)
3. Improve People grid layout (3 columns, responsive)
4. Add filtering/search within sections
5. Lazy load collapsed sections

**Files to Update:**
- `accordion_sidebar.py` (_build_sections, _build_people_grid)
- `ui/people_list_view.py` (if used)

**Expected Time:** 3-4 days

---

### Phase 4: Loading & Error States (Week 2-3)

**Goal:** Better feedback during async operations

**Changes:**
1. Add loading spinners to all sections
2. Clear error messages with retry buttons
3. Progress indicators for long operations
4. Skeleton screens for content placeholders
5. Smooth transitions on content load

**Files to Update:**
- `accordion_sidebar.py` (all _load_* methods)
- `google_components/widgets.py` (loader components)

**Expected Time:** 2-3 days

---

### Phase 5: Accessibility & Polish (Week 3)

**Goal:** Ensure AA accessibility + professional finish

**Changes:**
1. Keyboard navigation audit
2. ARIA labels for screen readers
3. Contrast ratio fixes (WCAG AA)
4. Touch target sizing (44x44px minimum)
5. Cross-browser testing

**Files to Update:**
- All files (audit + fixes)

**Expected Time:** 2-3 days

---

## Specific Integration Points

### 1. Search Sidebar ↔ Accordion Sidebar

**Current:** Two separate components, possible redundancy

**Goal:** Unified navigation experience

**Implementation:**

```python
# In google_layout.py:_build_left_shell()

# CURRENT approach (duplicate sections):
self.search_sidebar = SearchSidebar(...)  # Has People quick
self.accordion_sidebar = AccordionSidebar(...)  # Has People full

# PROPOSED approach (complementary):
# - SearchSidebar: Search focus, quick access
# - AccordionSidebar: Browse focus, detailed access
# - NO OVERLAP

# Example: SearchSidebar shows top 5 recent searches + quick people
# AccordionSidebar shows full people list when expanded

# Connection:
self.search_sidebar.selectPerson.connect(self.accordion_sidebar.select_person)
self.accordion_sidebar.selectPerson.connect(self._on_person_selected)
```

---

### 2. Toolbar ↔ Sidebar Styling

**Goal:** Consistent look between toolbar buttons and sidebar controls

**Current Disconnect:**
```
Toolbar button:
┌──────────────┐
│ Scan Now ✓   │  Background: #ffffff
│              │  Border: 1px #dadce0
└──────────────┘  Font: 10pt, weight 500
                  Hover: #f1f3f4 background


Sidebar header:
┌──────────────┐
│ People (23)  │  Background: #e8f0fe (different!)
│              │  Border: none (different!)
└──────────────┘  Font: 14pt weight 600 (different!)
                  Hover: #d2e3fc (different shade!)

Problem: Doesn't feel like same app!
```

**Solution:**

```python
# Define button styles as constants (use in both places)

# In ui/styles.py:
BUTTON_STYLES = {
    'default': {
        'background': '#ffffff',
        'border': '1px solid #dadce0',
        'color': '#202124',
        'font_size': '10pt',
        'font_weight': '500',
        'padding': '6px 10px',
        'border_radius': '4px',
    },
    'primary': {
        'background': '#1a73e8',
        'border': 'none',
        'color': '#ffffff',
        'font_size': '10pt',
        'font_weight': '600',
        'padding': '6px 10px',
        'border_radius': '4px',
    },
    'section_header': {
        'background': '#f8f9fa',
        'border': '1px solid #dadce0',
        'border_left': '3px solid transparent',
        'color': '#202124',
        'font_size': '14pt',
        'font_weight': '600',
        'padding': '12px 8px',
        'border_radius': '6px',
    },
    'section_header_active': {
        'background': '#e8f0fe',
        'border': 'none',
        'border_left': '3px solid #1a73e8',
        'color': '#1a73e8',
        'font_size': '14pt',
        'font_weight': '600',
        'padding': '12px 8px',
        'border_radius': '6px',
    }
}

# Use across codebase:
from ui.styles import BUTTON_STYLES

# In toolbar:
scan_btn = QPushButton("Scan")
scan_btn.setStyleSheet(self._get_stylesheet(BUTTON_STYLES['primary']))

# In sidebar:
section_header = SectionHeader("People")
section_header.setStyleSheet(self._get_stylesheet(BUTTON_STYLES['section_header']))
```

---

### 3. Grid ↔ Sidebar Content Updates

**Problem:** Sidebar doesn't reflect grid state changes

**Examples:**
- User filters grid to specific date → sidebar date section should show visual indicator
- User selects photos → selection count should update in sidebar
- User runs duplicate detection → duplicates count should update

**Solution:**

```python
# In google_layout.py, connect state changes:

def _on_search_state_changed(self, state):
    """Respond to global SearchState changes."""
    
    # Update sidebar to reflect current filters
    if state.active_people:
        # Highlight selected people in sidebar
        for person_key in state.active_people:
            self.accordion_sidebar.highlight_person(person_key)
    
    if state.active_filters.get('folder_id'):
        # Expand folders section, highlight selected folder
        self.accordion_sidebar.expand_section('folders')
        self.accordion_sidebar.highlight_folder(state.active_filters['folder_id'])
    
    # Update count badges
    if hasattr(state, 'result_count'):
        self.accordion_sidebar.update_count_badge('results', state.result_count)
```

---

### 4. Timeline ↔ Sidebar Scroll Synchronization

**Feature:** When user scrolls timeline to July, sidebar shows "July 2024" highlighted

```python
# In google_layout.py:

def _on_timeline_scroll(self, scroll_position):
    """Sync sidebar date view with timeline scroll."""
    
    # Determine visible date range
    visible_date = self._calculate_visible_date_from_scroll(scroll_position)
    
    # Highlight in sidebar
    self.accordion_sidebar.highlight_date(visible_date)
    
    # Show date indicator (already implemented as date_scroll_indicator)
```

---

### 5. Duplicates Section Integration

**Current Issue:** Duplicates section is in accordion sidebar but detection runs in main layout

**Solution:** Improve connection

```python
# In accordion_sidebar.py:
class AccordionSidebar:
    # Add signal when user clicks "Run Duplicates"
    runDuplicateDetection = Signal()
    duplicateCountUpdated = Signal(int)  # Emit count when available

# In google_layout.py:
self.accordion_sidebar.duplicateCountUpdated.connect(self._on_duplicate_count_updated)

def _on_duplicate_count_updated(self, count):
    """Update duplicates UI when count changes."""
    if count > 0:
        self.btn_duplicates.setStyleSheet("""
            QPushButton {
                background: #fbbc04;
                color: #202124;
            }
        """)
        self.btn_duplicates.setText(f"🔍 Duplicates ({count})")
```

---

## Responsive Design Considerations

### Desktop (> 1200px)
```
┌─────────────────────────────────────────────────────────────┐
│ Toolbar (40px)                                              │
├──────────────────┬────────────────────────────────────────┤
│ Sidebar 260px    │ Timeline Grid (remaining space) (80%)  │
│ (20%)            │                                         │
│ - 3 cols people  │ - 3 cols thumbnails                    │
│ - Full sections  │ - Date headers  
└──────────────────┴────────────────────────────────────────┘
```

### Laptop (1024-1200px)
```
┌───────────────────────────────────────────────────────┐
│ Toolbar (40px)                                        │
├──────────────────┬──────────────────────────────────┤
│ Sidebar 240px    │ Timeline Grid (60%)              │
│ (20%)            │                                  │
│ - 2 cols people  │ - 2-3 cols thumbnails           │
│ - Collapsed      │                                  │
└──────────────────┴──────────────────────────────────┘
```

### Tablet (768-1024px)
```
┌──────────────────────────────────────────────┐
│ Toolbar (40px)                               │
├──────────────────────────────────────────────┤
│ Timeline Grid (90%)                          │
├──────────────────────────────────────────────┤
│ Sidebar Drawer (can be swiped out) (10%)    │
└──────────────────────────────────────────────┘
OR
├────────────┬────────────────────────────────┤
│Sidebar 200 │ Timeline (80%)                │
│px (20%)    │                              │
└────────────┴────────────────────────────────┘
```

### Mobile (< 768px)
```
┌───────────────────────────────────┐
│ Toolbar (36px) + Tab bar          │
├───────────────────────────────────┤
│ Timeline Grid (Full width)        │
│ (Sidebar = drawer/tab)            │
│                                   │
│                                   │
│ [Sidebar Drawer ◄] (overlay)      │
└───────────────────────────────────┘
```

**Implementation:**

```python
# In accordion_sidebar.py:
class AccordionSidebar:
    def adapt_to_window_size(self, width):
        """Adapt layout to window width."""
        if width > 1200:  # Desktop
            self.people_grid.cards_per_row = 3
            self.setMinimumWidth(260)
        elif width > 1024:  # Laptop
            self.people_grid.cards_per_row = 2
            self.setMinimumWidth(240)
        elif width > 768:  # Tablet
            self.people_grid.cards_per_row = 2
            self.setMinimumWidth(200)
        else:  # Mobile
            self.people_grid.cards_per_row = 1
            self.setMinimumWidth(160)
```

---

## Performance Considerations

### Issue: Sidebar sections load all content immediately

**Problem:**
```
User opens app:
1. SearchSidebar loads: ✓ fast
2. AccordionSidebar expands: ✓ fast
3. People section loads: ✓ fast (~50ms)
4. Dates section loads: ✓ fast (~100ms)
5. Folders section loads: ✓ fast (~50ms)
6. Other sections load: ✓ fast (~50-100ms)

Total: ~400ms before UI is responsive
Timeline grid also loading in parallel...
Result: Possible janky first paint
```

**Solution: Lazy Load Collapsed Sections**

```python
# In accordion_sidebar.py:
class AccordionSidebar:
    def __init__(self, project_id: int | None, parent=None):
        # Track which sections have been loaded
        self._section_content_loaded = {
            'people': False,
            'dates': False,
            'folders': False,
            # ... etc
        }
        
        # Only load expanded section on init
        self.expand_section("people")  # Expanded by default
        # Others remain empty until clicked

    def expand_section(self, section_id: str):
        """Expand section, loading content if needed."""
        # Collapse others
        for sid in self.sections:
            if sid != section_id:
                self.sections[sid].set_expanded(False)
        
        # Expand this one
        self.sections[section_id].set_expanded(True)
        
        # Load content if not already loaded
        if not self._section_content_loaded.get(section_id, False):
            self._load_section_content(section_id)
            self._section_content_loaded[section_id] = True

# Result:
# - First paint: 50ms (1 section)
# - Dates section lazy-load: 100ms when clicked
# - Folders lazy-load: 50ms when clicked
# Much better!
```

---

## Accessibility Improvements

### Keyboard Navigation Map

```
Tab:                Navigate forward through controls
Shift+Tab:          Navigate backward through controls
Enter/Space:        Expand/collapse section
Arrow Up/Down:      Navigate between sections
Arrow Right:        Expand section (if collapsed)
Arrow Left:         Collapse section (if expanded)
Home:               Jump to first section
End:                Jump to last section

Section-specific (when inside):
- Arrow Up/Down:    Move between items in list
- Enter:            Select item / apply filter
- Escape:           Close section or return to nav
```

**Implementation:**

```python
# In accordion_sidebar.py:

class SectionHeader(QFrame):
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        key = event.key()
        
        if key == Qt.Key_Space or key == Qt.Key_Return:
            self.clicked.emit()
            event.accept()
        elif key == Qt.Key_Right and not self.is_active:
            self.clicked.emit()
            event.accept()
        elif key == Qt.Key_Left and self.is_active:
            self.clicked.emit()
            event.accept()
        else:
            super().keyPressEvent(event)
```

---

## Testing Checklist

### Visual Testing
- [ ] Colors consistent across sidebar/toolbar/grid
- [ ] Typography sizes and weights correct
- [ ] Spacing aligns to 8px grid
- [ ] Animations smooth (no jank at 60fps)
- [ ] Section transitions fluid (300ms max)
- [ ] Buttons have clear hover/active states
- [ ] Icons render clearly at all sizes

### Layout Testing
- [ ] Desktop (1920x1080): 3-col people grid
- [ ] Laptop (1366x768): 2-col people grid
- [ ] Tablet (768x1024): 1-col people grid, docked sidebar
- [ ] Mobile (375x667): Full-width grid, sidebar drawer
- [ ] Splitter works smoothly (drag resize)
- [ ] No horizontal scrollbars on any size

### Functionality Testing
- [ ] Sections expand/collapse correctly
- [ ] Clicking nav button switches sections
- [ ] People grid loads and displays correctly
- [ ] Lazy loading works (sections only load when expanded)
- [ ] Counts update when data changes
- [ ] Drag-merge still works
- [ ] Context menus work
- [ ] Keyboard shortcuts work

### Accessibility Testing
- [ ] Tab order correct (logical flow)
- [ ] All buttons keyboard accessible
- [ ] ARIA labels present
- [ ] Color contrast ≥ 4.5:1
- [ ] Focus indicators visible (≥ 3px outline)
- [ ] Screen reader reads all content
- [ ] Touch targets ≥ 44x44px

### Performance Testing
- [ ] First paint < 100ms
- [ ] Lazy loading reduces initial load
- [ ] Section expand animation ≤ 300ms
- [ ] Scrolling smooth (60fps minimum)
- [ ] Memory doesn't leak (check DevTools)
- [ ] No layout thrashing during animations

---

## Migration Strategy

### Risk: Breaking Existing Integrations

**Current code depends on:**
```python
# accordion_sidebar.py exports:
- AccordionSidebar class
- Section loading behavior
- Signal names (selectBranch, selectFolder, etc.)

# google_layout.py uses:
self.accordion_sidebar.selectBranch.connect(...)
self.accordion_sidebar.selectFolder.connect(...)
etc.
```

**Mitigation:**
1. Keep signal names exactly the same
2. Add new signals, don't remove old ones
3. Implement backward compatibility layer
4. Test all existing connections

**Implementation:**
```python
# In accordion_sidebar.py:

class AccordionSidebar(QWidget):
    # NEW signals (can be different names)
    selectBranch = Signal(str)     # Keep existing
    selectFolder = Signal(int)     # Keep existing
    
    # Backward compatibility:
    # If existing code uses selectBranch, it still works
    # New code can use new naming
    
    def _on_person_clicked(self, branch_key):
        """Maintain compatibility."""
        self.selectBranch.emit(branch_key)  # Still emit old signal
        self.selectPerson.emit(branch_key)  # Also emit new signal
```

---

## Success Metrics

### Design Metrics
- ✓ Sidebar color palette matches toolbar (show side-by-side comparison)
- ✓ Typography hierarchy consistent (measure size ratios)
- ✓ Spacing aligns to 8px grid (0 pixels off-grid)
- ✓ Section transitions smooth (≤ 300ms, 60fps)

### UX Metrics
- ✓ Users can identify 3+ sections within 30 seconds (first-time)
- ✓ Section expand time ≤ 500ms (perceived performance)
- ✓ People grid shows ≥ 4 faces without scrolling
- ✓ Keyboard navigation works for all controls

### Technical Metrics
- ✓ First paint < 100ms
- ✓ WCAG AA compliance (4.5:1 contrast minimum)
- ✓ No console errors on startup
- ✓ Memory usage stable (no leaks)
- ✓ No layout thrashing (> 60fps scroll)

---

## Conclusion

By aligning the sidebar design with the overall Google layout strategy, we can create a cohesive, professional user experience. The improvements outlined in this document coordinate sidebar changes with the larger layout ecosystem, ensuring:

1. **Visual Consistency:** Same color palette, typography, spacing
2. **Navigation Clarity:** Clear section hierarchy and affordances
3. **Performance:** Lazy loading and efficient rendering
4. **Accessibility:** Full keyboard support, WCAG AA compliance
5. **Responsiveness:** Adaptive layouts for all screen sizes

**Estimated Effort:** 2-3 weeks (coordinated with layout changes)

**Expected ROI:** Significantly improved user perception of design quality and polish

