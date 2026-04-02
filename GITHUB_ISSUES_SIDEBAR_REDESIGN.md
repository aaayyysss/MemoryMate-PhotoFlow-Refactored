# GitHub Issues - Sidebar Design Redesign
## Generated from Design Audit | 2026-04-02
## Instructions: Copy/paste each issue into GitHub

---

## PHASE 1: Visual Foundation (Week 1)

### Issue #1: Define Design System Constants
**Priority:** P0 - Critical  
**Category:** Design System  
**Effort:** 1-2 days  
**Phase:** 1  

**Description:**
Create centralized design system with colors, spacing, and typography constants. This is the foundation for all Phase 1 improvements.

**Acceptance Criteria:**
- [ ] Create `ui/styles.py` with:
  - `COLORS` dictionary (primary, surface, text, semantic colors)
  - `SPACING` dictionary (8px grid multiples)
  - `TYPOGRAPHY` dictionary (5 type scales)
  - `SHADOWS` and `RADIUS` constants
- [ ] All constants match Material Design 3 principles
- [ ] Documentation in docstrings explaining each constant
- [ ] No hardcoded values in implementation files

**Files Affected:**
- `ui/styles.py` (new file)

**Related:**
- Blocks issue #2, #3
- Fixes: color inconsistency, spacing misalignment

---

### Issue #2: Update Sidebar Colors to Use Design System
**Priority:** P0 - Critical  
**Category:** Visual Polish  
**Effort:** 1 day  
**Phase:** 1

**Description:**
Replace all hardcoded colors in accordion_sidebar.py with COLORS from design system. Fixes inconsistent color usage throughout sidebar.

**Current State:**
- Multiple blue shades: #1a73e8, #e8f0fe, #d2e3fc
- Opacity-based states: rgba(26, 115, 232, 0.08), 0.10, 0.20
- No semantic color organization

**Target State:**
- Single primary blue: #1a73e8
- Consistent light backgrounds: #e8f0fe
- Semantic colors: success, warning, error

**Acceptance Criteria:**
- [ ] All colors imported from `COLORS` in `ui/styles.py`
- [ ] No hardcoded hex color values remain
- [ ] Color contrast ≥ 4.5:1 (WCAG AA) verified
- [ ] Visual regression test passes (screenshot comparison)
- [ ] All sections render correctly (colors applied)

**Implementation Notes:**
```python
from ui.styles import COLORS

# OLD:
self.setStyleSheet("background-color: #e8f0fe;")

# NEW:
self.setStyleSheet(f"background-color: {COLORS['primary_light']};")
```

**Files Affected:**
- `accordion_sidebar.py` (SectionHeader, AccordionSidebar)
- `google_components/widgets.py` (PersonCard, etc.)
- `layouts/google_layout.py` (if needed)

**Depends On:** Issue #1

---

### Issue #3: Implement 8px Spacing Grid Throughout Sidebar
**Priority:** P0 - Critical  
**Category:** Visual Polish  
**Effort:** 1 day  
**Phase:** 1

**Description:**
Standardize all margins and padding to 8px grid multiples. Fixes visual misalignment and makes layout feel professional.

**Current Problems:**
- Margins: 6px, 8px, 10px mixed inconsistently
- Padding: 4px-12px with no pattern
- Section headers: 10px 6px (inconsistent)
- People cards: 4px padding vs 8px elsewhere

**Target:**
- All values multiples of 8px: 4, 8, 12, 16, 24
- Consistent margins throughout: 8px
- Consistent section padding: 12px (1.5x grid)

**Acceptance Criteria:**
- [ ] All margins/padding multiples of 8px
- [ ] No pixel off-grid values remain
- [ ] Layout still looks good (no weird spacing)
- [ ] Elements properly aligned visually
- [ ] Screenshots show improved visual polish

**Implementation Location:**
```python
# In accordion_sidebar.py and google_components/widgets.py:
# Define spacing as constants:
from ui.styles import SPACING

layout.setContentsMargins(SPACING['md'], SPACING['md'], SPACING['md'], SPACING['md'])
layout.setSpacing(SPACING['sm'])
```

**Files Affected:**
- `accordion_sidebar.py` (all layouts)
- `google_components/widgets.py` (PersonCard, etc.)
- `layouts/google_layout.py` (if needed)

**Depends On:** Issue #1

---

### Issue #4: Implement Typography Scale System
**Priority:** P0 - Critical  
**Category:** Visual Polish  
**Effort:** 1 day  
**Phase:** 1

**Description:**
Apply typography scale from design system to establish clear visual hierarchy. Fixes readability and hierarchy issues.

**Current Problems:**
- Header sizes: 12pt-14pt unclear
- Body text: 9pt-13pt mixed
- Tab labels: 10pt (too small)
- No line-height specification

**Target Scale:**
- H2 (Header): 14px, weight 600, line-height 20px
- Body: 13px, weight 400, line-height 20px
- Small: 11px, weight 400, line-height 16px
- Caption: 10px, weight 400, line-height 14px

**Acceptance Criteria:**
- [ ] All text uses TYPOGRAPHY roles
- [ ] Line-heights ≥ 1.5x font size
- [ ] Font weights consistent (400, 500, 600 only)
- [ ] Section headers: H2 (14px, 600 weight)
- [ ] Tab labels: Body (13px, 500 weight)
- [ ] Hints/captions: Caption (10px, 400 weight)
- [ ] Text clearly scannable with good hierarchy

**Implementation:**
```python
from ui.styles import TYPOGRAPHY

typo = TYPOGRAPHY['h2']
font = label.font()
font.setPointSize(typo['size'])
font.setWeight(typo['weight'])
label.setFont(font)
```

**Files Affected:**
- `accordion_sidebar.py` (all labels)
- `google_components/widgets.py` (all text)
- `layouts/google_layout.py` (if needed)

**Depends On:** Issue #1

---

### Issue #5: Add Left Border Accent to Section Headers
**Priority:** P1 - High  
**Category:** Visual Improvement  
**Effort:** 2 hours  
**Phase:** 1

**Description:**
Add 3px colored left border to active sections for better visual distinction. Improves scannability and state clarity.

**Current:**
- Active sections: light blue background only (#e8f0fe)
- Inactive sections: off-white + 1px border (#f8f9fa)
- Visual distinction not clear enough

**Target:**
- Active: #e8f0fe background + 3px #1a73e8 left border
- Inactive: #f8f9fa background + 1px #dadce0 border (no left accent)

**Acceptance Criteria:**
- [ ] Active sections have 3px blue left border
- [ ] Inactive sections have subtle border
- [ ] Left border provides clear visual accent
- [ ] Colors from COLORS constant
- [ ] Visual test passes (screenshot comparison)

**Implementation:**
```python
if active:
    stylesheet = """
        SectionHeader {
            background-color: #e8f0fe;
            border: none;
            border-left: 3px solid #1a73e8;
            padding-left: 8px;
        }
    """
else:
    stylesheet = """
        SectionHeader {
            background-color: #f8f9fa;
            border: 1px solid #dadce0;
            border-left: none;
        }
    """
```

**Files Affected:**
- `accordion_sidebar.py` (SectionHeader.set_active)

**Related:** Issue #2 (colors)

---

## PHASE 2: UX Improvements (Week 2)

### Issue #6: Redesign Navigation Bar with Labels & Badges
**Priority:** P1 - High  
**Category:** Navigation  
**Effort:** 2-3 days  
**Phase:** 2

**Description:**
Improve left navigation bar from icon-only (52px) to icon+label (64px) with badge support. Improves discoverability and allows alerts.

**Current Problems:**
- 52px too narrow for clear icons
- Icon-only requires tooltip to understand
- No way to show alerts (e.g., unread duplicates)
- Poor affordance (unclear this is navigation)

**Target:**
- 64px width (icon + optional label)
- Show labels on hover (tooltip nearby)
- Badge support (red dot for alerts)
- Left border on active section
- Better visual feedback

**Acceptance Criteria:**
- [ ] Nav bar width: 64px
- [ ] Icons clear and identifiable
- [ ] Hover shows label tooltip nearby
- [ ] Active section has blue left border
- [ ] Badge support (red dot) implemented
- [ ] Section labels translated (i18n compatible)
- [ ] Touch target ≥ 44x44px
- [ ] Keyboard navigation works

**Implementation Files:**
- `accordion_sidebar.py` (nav bar section, ~100 lines)

**Acceptance Test:**
```
1. Hover over nav icon → Label appears
2. Click section → Border highlights, section expands
3. If badge count > 0 → Red dot appears
4. Tab key → Can navigate nav buttons
```

**Depends On:** Issue #2 (colors)

---

### Issue #7: Implement Responsive People Grid (3 Columns)
**Priority:** P1 - High  
**Category:** Content Layout  
**Effort:** 2 days  
**Phase:** 2

**Description:**
Redesign people grid from fixed 2-column to responsive 3-column layout. Shows more faces, better space utilization.

**Current Problems:**
- 80x100px cards only 2 per row
- 340px minimum height too constraining
- Only 6 faces visible without scrolling
- Person names truncated at 10 chars

**Target:**
- 100x120px cards per row
- 3 columns (better use of 260px sidebar)
- Responsive: 3 cols (desktop) → 2 cols (tablet) → 1 col (mobile)
- Show 9 faces before scrolling
- "Load more" button for additional faces
- Full names visible (no truncation)

**Acceptance Criteria:**
- [ ] 3-column layout by default
- [ ] 100x120px card size
- [ ] Min height = 2 rows (280px)
- [ ] Max height = 3 rows before scroll
- [ ] 9 faces visible initially
- [ ] "Load more" button if > 9 people
- [ ] Responsive for tablet (2 cols)
- [ ] Full person names shown (no truncation)
- [ ] Drag-merge still works
- [ ] Context menus still work

**Implementation:**
```python
class PeopleGridView(QWidget):
    CARD_WIDTH = 100
    CARD_HEIGHT = 120
    CARDS_PER_ROW = 3
    MIN_ROWS = 2
    MAX_ROWS = 3
```

**Files Affected:**
- `accordion_sidebar.py` (PeopleGridView class)
- `google_components/widgets.py` (PersonCard, if needed)

**Depends On:** Issue #2, #3 (colors/spacing)

---

### Issue #8: Add Loading State Indicators to Sections
**Priority:** P1 - High  
**Category:** UX/Feedback  
**Effort:** 1-2 days  
**Phase:** 2

**Description:**
Show loading spinners when sections fetch data. Prevents user confusion that app is broken.

**Current Problems:**
- Sections load quietly
- No indication of loading state
- Users think app is broken during load
- No error state handling

**Target:**
- Loading spinner in section center
- "Loading..." text
- Optional progress (for slow operations)
- Error state with retry button
- Smooth fade-in when content loads

**Acceptance Criteria:**
- [ ] Loading spinner visible (⟳ animation)
- [ ] "Loading..." message shown
- [ ] Spinner rotates smoothly (50ms per frame)
- [ ] Error state shows "Failed to load" + Retry button
- [ ] Content fades in smoothly (300ms)
- [ ] State transitions are obvious
- [ ] Works for all async sections (people, dates, etc.)
- [ ] No race conditions (latest data wins)

**Implementation:**
```python
def _show_loading(section):
    spinner = QLabel("⟳")
    anim = QPropertyAnimation(spinner, b"rotation")
    anim.setDuration(1000)
    anim.setStartValue(0)
    anim.setEndValue(360)
    anim.setLoopCount(-1)
    anim.start()
    
    layout.addWidget(spinner)
```

**Files Affected:**
- `accordion_sidebar.py` (all _load_* methods)

**Related:** Issue #4 (typography for messages)

---

### Issue #9: Animate Section Expand/Collapse
**Priority:** P2 - Medium  
**Category:** Animation/Polish  
**Effort:** 1 day  
**Phase:** 2

**Description:**
Add smooth animations when expanding/collapsing sections. Improves perceived responsiveness.

**Current Problems:**
- Instant show/hide (jarring)
- No feedback on interaction
- Feels unresponsive

**Target:**
- Smooth 300ms expand animation
- Slide + fade content in
- Rotate chevron smoothly
- Fade background color

**Acceptance Criteria:**
- [ ] Expand animation: 300ms smooth
- [ ] Collapse animation: 300ms smooth
- [ ] Chevron rotates 180° during animation
- [ ] Content fades in (0 → 1 opacity)
- [ ] No jarring layout shifts
- [ ] 60fps minimum (no jank)
- [ ] Can be interrupted/re-triggered

**Implementation:**
```python
anim = QPropertyAnimation(self.scroll_area, b"geometry")
anim.setDuration(300)
anim.setEasingCurve(QEasingCurve.InOutQuad)
anim.start()
```

**Files Affected:**
- `accordion_sidebar.py` (AccordionSection.set_expanded)

**Depends On:** Issue #2 (colors for smooth transitions)

---

## PHASE 3: Polish & Accessibility (Week 3)

### Issue #10: Keyboard Navigation & Accessibility Audit
**Priority:** P1 - High  
**Category:** Accessibility  
**Effort:** 2 days  
**Phase:** 3

**Description:**
Make sidebar fully keyboard navigable and accessible. Ensure WCAG AA compliance.

**Navigation Map:**
- Tab/Shift+Tab: Navigate controls
- Enter/Space: Expand/collapse sections
- Arrow Up/Down: Navigate between sections
- Arrow Right: Expand (when collapsed)
- Arrow Left: Collapse (when expanded)

**Acceptance Criteria:**
- [ ] All controls reachable via Tab key
- [ ] Keyboard shortcuts work as documented
- [ ] Focus indicators visible (≥3px outline)
- [ ] ARIA labels on all interactive elements
- [ ] Screen reader reads content in order
- [ ] No keyboard traps
- [ ] Focus management correct when expanding (focus first item)
- [ ] Skip links (if applicable)

**Testing Checklist:**
- [ ] Test with Tab key only (no mouse)
- [ ] Test with NVDA screen reader
- [ ] Test with browser keyboard shortcuts
- [ ] Focus ring visible and clear

**Files Affected:**
- `accordion_sidebar.py` (keyPressEvent overrides)
- `google_components/widgets.py` (all widgets)

**Depends On:** All previous issues

---

### Issue #11: Fix Accessibility Contrast & Colors
**Priority:** P1 - High  
**Category:** Accessibility  
**Effort:** 1 day  
**Phase:** 3

**Description:**
Ensure all text meets WCAG AA contrast (4.5:1). Fix existing contrast failures.

**Current Issue:**
- Secondary text (#5f6368) = 54% contrast (FAILS)
- Some states fail AA compliance

**Target:**
- All text: ≥ 4.5:1 contrast (WCAG AA)
- Verified against WCAG Color Contrast Checker

**Acceptance Criteria:**
- [ ] Primary text: ≥ 4.5:1 (✓ already ok)
- [ ] Secondary text: updated to pass (✓ verify)
- [ ] All button states: ≥ 4.5:1
- [ ] All section headers: ≥ 4.5:1
- [ ] All badges/labels: ≥ 4.5:1
- [ ] Verified with WCAG checker
- [ ] No accessibility regressions

**Testing:**
```
Use WebAIM Contrast Checker:
https://webaim.org/resources/contrastchecker/
```

**Files Affected:**
- `ui/styles.py` (COLORS - update secondary text color)
- All color usages

**Depends On:** Issue #1, #2 (colors)

---

### Issue #12: Add Responsive Design for Tablet/Mobile
**Priority:** P2 - Medium  
**Category:** Responsive Design  
**Effort:** 1-2 days  
**Phase:** 3

**Description:**
Adapt sidebar for tablet (768-1024px) and mobile (<768px) screen sizes.

**Responsive Breakpoints:**
- Desktop (>1200px): 260px sidebar, 3-col people grid
- Laptop (1024-1200px): 240px sidebar, 2-col people grid
- Tablet (768-1024px): 200px sidebar or drawer
- Mobile (<768px): Full-width, sidebar = drawer overlay

**Acceptance Criteria:**
- [ ] Desktop (1920x1080): 3-col grid works
- [ ] Laptop (1366x768): 2-col grid works
- [ ] Tablet (768x1024): sidebar docks or drawer
- [ ] Mobile (375x667): full-width grid, drawer sidebar
- [ ] No horizontal scrolling
- [ ] Touch targets ≥ 44x44px
- [ ] Fonts readable on small screens
- [ ] Drawer slides smoothly

**Implementation:**
```python
def adapt_to_window_size(self, width):
    if width > 1200:
        self.people_grid.cards_per_row = 3
        self.setMinimumWidth(260)
    elif width > 1024:
        self.people_grid.cards_per_row = 2
        self.setMinimumWidth(240)
    elif width > 768:
        self.show_as_drawer()
        self.setMinimumWidth(200)
    else:
        self.show_as_drawer()
```

**Files Affected:**
- `accordion_sidebar.py`
- `layouts/google_layout.py`

**Depends On:** All Phase 1-2 issues

---

### Issue #13: Create Comprehensive Design Documentation
**Priority:** P2 - Medium  
**Category:** Documentation  
**Effort:** 1 day  
**Phase:** 3

**Description:**
Create design specification document for developers. Ensures consistency in future changes.

**Content:**
- Component library (SectionHeader, PersonCard, etc.)
- States and variations for each component
- Color usage guide
- Typography usage guide
- Spacing guide
- Icon usage
- Animation guidelines
- Accessibility checklist

**Deliverable:**
- File: `SIDEBAR_DESIGN_SPECIFICATION.md`
- Linked in README
- Includes screenshots/diagrams

**Acceptance Criteria:**
- [ ] All components documented
- [ ] States clearly shown (active/inactive/hover/disabled)
- [ ] Color palette explained
- [ ] Typography scale documented
- [ ] Spacing grid documented
- [ ] Accessibility requirements listed
- [ ] Code examples for each component
- [ ] Screenshot for each variant

**Files Affected:**
- `SIDEBAR_DESIGN_SPECIFICATION.md` (new)

---

## Testing & QA

### Issue #14: Visual Regression Testing (QA)
**Priority:** P2 - Medium  
**Category:** Testing  
**Effort:** 1 day  
**Phase:** 3

**Description:**
Set up visual regression tests to prevent design breakages.

**Scope:**
- Screenshot comparisons (before/after each phase)
- All section states (expanded, collapsed, loading, error)
- All screen sizes (desktop, tablet, mobile)
- All themes (light mode, potentially dark mode)

**Acceptance Criteria:**
- [ ] Baseline screenshots created
- [ ] Regression test script (Python + Pillow, or similar)
- [ ] Automated comparison working
- [ ] CI/CD integration (if applicable)

**Files:**
- `test_sidebar_visual_regression.py` (new)

---

## Summary Table

| Issue | Title | Priority | Phase | Days | Depends |
|-------|-------|----------|-------|------|---------|
| #1 | Design System Constants | P0 | 1 | 1-2 | None |
| #2 | Update Sidebar Colors | P0 | 1 | 1 | #1 |
| #3 | 8px Spacing Grid | P0 | 1 | 1 | #1 |
| #4 | Typography Scale | P0 | 1 | 1 | #1 |
| #5 | Left Border Accent | P1 | 1 | 0.5 | #2 |
| #6 | Nav Bar Redesign | P1 | 2 | 2-3 | #2 |
| #7 | People Grid 3-Col | P1 | 2 | 2 | #2,#3 |
| #8 | Loading Indicators | P1 | 2 | 1-2 | #2,#4 |
| #9 | Expand Animations | P2 | 2 | 1 | #2 |
| #10 | Keyboard Navigation | P1 | 3 | 2 | All |
| #11 | Contrast Fixes | P1 | 3 | 1 | #1,#2 |
| #12 | Responsive Design | P2 | 3 | 1-2 | All |
| #13 | Design Documentation | P2 | 3 | 1 | All |
| #14 | Regression Testing | P2 | 3 | 1 | All |

**Total Effort:** 3 weeks, 14 issues, ~8-10 dev days

---

## How to Use This File

1. **Copy each issue** (from "### Issue #N" to end of issue)
2. **Paste into GitHub** as a new issue
3. **Add to project board** (Sidebar Redesign phase)
4. **Assign to developer** (matches phase)
5. **Label accordingly** (phase, priority, category)
6. **Create as issues in order** (respect dependencies)

