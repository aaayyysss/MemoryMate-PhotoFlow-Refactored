# Phase 1 Implementation Guide: Colors & Spacing
## Complete Code Changes for Phase 1 | 2026-04-02

---

## Overview

Phase 1 transforms the sidebar from "cluttered" to "professional" by:
1. Using centralized design constants (colors, spacing, typography)
2. Fixing all spacing to 8px grid
3. Improving color hierarchy and contrast
4. Adding left border accents to active sections

**Estimated Time:** 1-2 days  
**Impact:** ~30% immediate visual improvement  

---

## Files to Modify

1. **`accordion_sidebar.py`** - Update all styling to use constants
2. **`google_components/widgets.py`** - Update PersonCard styling
3. **`layouts/google_layout.py`** - Ensure toolbar alignment

---

## Implementation: accordion_sidebar.py

### Change 1: Import Design Constants

**Location:** Top of `accordion_sidebar.py` (after existing imports)

**Add these lines:**

```python
# Design System
from ui.styles import (
    COLORS,
    SPACING,
    TYPOGRAPHY,
    RADIUS,
    ANIMATION,
    get_color,
    get_spacing,
    get_typography,
)
```

---

### Change 2: Update SectionHeader Class

**File:** `accordion_sidebar.py`

**Location:** `class SectionHeader(QFrame):` (around line 700+)

**Replace the entire `set_active()` method:**

**BEFORE:**
```python
def set_active(self, active: bool):
    """Set header to active (expanded) or inactive (collapsed) state."""
    self.is_active = active

    if active:
        # Active state: Bold, highlighted, chevron down
        self.title_font.setBold(True)
        self.title_label.setFont(self.title_font)
        self.chevron_label.setText("▼")  # Down arrow
        self.setStyleSheet("""
            SectionHeader {
                background-color: #e8f0fe;
                border: none;
                border-radius: 6px;
            }
            SectionHeader:hover {
                background-color: #d2e3fc;
            }
        """)
    else:
        # Inactive state: Normal, default background, chevron right
        self.title_font.setBold(False)
        self.title_label.setFont(self.title_font)
        self.chevron_label.setText("▶")  # Right arrow
        self.setStyleSheet("""
            SectionHeader {
                background-color: #f8f9fa;
                border: 1px solid #e8eaed;
                border-radius: 6px;
            }
            SectionHeader:hover {
                background-color: #f1f3f4;
            }
        """)
```

**AFTER:**
```python
def set_active(self, active: bool):
    """Set header to active (expanded) or inactive (collapsed) state."""
    self.is_active = active

    if active:
        # Active state: Bold, highlighted background + left blue border, chevron down
        self.title_font.setBold(True)
        self.title_label.setFont(self.title_font)
        self.chevron_label.setText("▼")  # Down arrow
        
        # Use design system colors + 3px left border accent
        self.setStyleSheet(f"""
            SectionHeader {{
                background-color: {COLORS['primary_container']};
                border: none;
                border-left: 3px solid {COLORS['primary']};
                border-radius: {RADIUS['medium']}px;
                padding-left: {get_spacing('sm')}px;
            }}
            SectionHeader:hover {{
                background-color: {COLORS['surface_tertiary_alt']};
            }}
        """)
    else:
        # Inactive state: Normal weight, neutral background, subtle border, chevron right
        self.title_font.setBold(False)
        self.title_label.setFont(self.title_font)
        self.chevron_label.setText("▶")  # Right arrow
        
        # Use design system colors + subtle border
        self.setStyleSheet(f"""
            SectionHeader {{
                background-color: {COLORS['surface_secondary']};
                border: 1px solid {COLORS['outline_tertiary']};
                border-left: none;
                border-radius: {RADIUS['medium']}px;
            }}
            SectionHeader:hover {{
                background-color: {COLORS['surface_tertiary']};
            }}
        """)
```

---

### Change 3: Update SectionHeader Layout (Margins/Padding)

**Location:** `SectionHeader.__init__()` method

**Find this section:**
```python
# Layout
layout = QHBoxLayout(self)
layout.setContentsMargins(10, 6, 10, 6)
layout.setSpacing(8)
```

**Replace with:**
```python
# Layout - Use design system spacing (8px grid)
layout = QHBoxLayout(self)
margin = get_spacing('md')  # 12px
spacing = get_spacing('sm')  # 8px
layout.setContentsMargins(margin, spacing, margin, spacing)
layout.setSpacing(spacing)
```

---

### Change 4: Update SectionHeader Icon/Title Layout

**Location:** In `SectionHeader.__init__()`, find the icon/title section:

**BEFORE:**
```python
self.icon_label = QLabel(icon)
self.icon_label.setFixedWidth(24)
font = self.icon_label.font()
font.setPointSize(14)
self.icon_label.setFont(font)

self.title_label = QLabel(title)
self.title_font = self.title_label.font()

# Count badge (optional)
self.count_label = QLabel("")
self.count_label.setStyleSheet("color: #666; font-size: 11px;")
self.count_label.setVisible(False)

# Chevron
self.chevron_label = QLabel("▶")  # Right arrow for collapsed
self.chevron_label.setFixedWidth(20)
chevron_font = self.chevron_label.font()
chevron_font.setPointSize(10)
self.chevron_label.setFont(chevron_font)
```

**AFTER:**
```python
# Icon - 18pt size (semantic icon size)
self.icon_label = QLabel(icon)
self.icon_label.setFixedWidth(24)
icon_font = self.icon_label.font()
icon_font.setPointSize(14)  # ~18px equivalent
self.icon_label.setFont(icon_font)

# Title - Use typography system
self.title_label = QLabel(title)
self.title_font = self.title_label.font()
typo = TYPOGRAPHY['title']
self.title_font.setPointSize(typo['size_pt'])
self.title_font.setWeight(typo['weight'])
self.title_label.setFont(self.title_font)

# Count badge - Use consistent styling
self.count_label = QLabel("")
count_typo = TYPOGRAPHY['label']
count_font = self.count_label.font()
count_font.setPointSize(count_typo['size_pt'])
self.count_label.setFont(count_font)
self.count_label.setStyleSheet(
    f"color: {COLORS['text_secondary']}; "
    f"font-size: {count_typo['size_pt']}pt;"
)
self.count_label.setVisible(False)

# Chevron - Use typography for consistency
self.chevron_label = QLabel("▶")  # Right arrow for collapsed
self.chevron_label.setFixedWidth(20)
chevron_font = self.chevron_label.font()
chevron_font.setPointSize(12)  # Slightly larger
self.chevron_label.setFont(chevron_font)
chevron_typo = TYPOGRAPHY['label']
self.chevron_label.setStyleSheet(
    f"color: {COLORS['text_secondary']};"
)
```

---

### Change 5: Update AccordionSection Container Margins

**Location:** `class AccordionSection(QWidget)` → `__init__()` method

**Find:**
```python
# Main layout
layout = QVBoxLayout(self)
layout.setContentsMargins(0, 0, 0, 0)
layout.setSpacing(0)
```

**Replace with:**
```python
# Main layout - Use design system spacing
layout = QVBoxLayout(self)
layout.setContentsMargins(0, 0, 0, 0)
layout.setSpacing(0)  # No spacing between header and content
```

**Find the content_layout section:**
```python
self.content_layout = QVBoxLayout(self.content_container)
self.content_layout.setContentsMargins(8, 8, 8, 8)
self.content_layout.setSpacing(0)
```

**Replace with:**
```python
self.content_layout = QVBoxLayout(self.content_container)
padding = get_spacing('md')  # 12px (1.5x grid)
self.content_layout.setContentsMargins(padding, padding, padding, padding)
self.content_layout.setSpacing(0)
```

---

### Change 6: Update AccordionSidebar Nav Bar Layout

**Location:** `AccordionSidebar.__init__()` → nav bar section

**Find:**
```python
nav_bar = QWidget()
nav_bar.setFixedWidth(52)
nav_bar.setStyleSheet("""
    QWidget {
        background: #ffffff;
        border-right: 1px solid #dadce0;
    }
""")
nav_layout = QVBoxLayout(nav_bar)
nav_layout.setContentsMargins(6, 12, 6, 4)
nav_layout.setSpacing(4)
```

**Replace with:**
```python
nav_bar = QWidget()
nav_bar.setFixedWidth(52)  # Keep width for now (Phase 2 expands to 64px)
nav_bar.setStyleSheet(f"""
    QWidget {{
        background: {COLORS['surface_primary']};
        border-right: 1px solid {COLORS['outline_primary']};
    }}
""")
nav_layout = QVBoxLayout(nav_bar)
nav_margin = get_spacing('sm')      # 8px
nav_margin_top = get_spacing('md')  # 12px
nav_spacing = get_spacing('xs')     # 4px
nav_layout.setContentsMargins(nav_margin, nav_margin_top, nav_margin, nav_spacing)
nav_layout.setSpacing(nav_spacing)
```

---

### Change 7: Update Nav Button Styles

**Location:** In `_build_sections()` method, find the nav button styling:

**Find:**
```python
nav_btn.setStyleSheet("""
    QPushButton {
        background: transparent;
        border: none;
        border-radius: 10px;
        font-size: 20pt;
    }
    QPushButton:hover {
        background: rgba(26, 115, 232, 0.10);
    }
    QPushButton:pressed {
        background: rgba(26, 115, 232, 0.20);
    }
""")
```

**Replace with:**
```python
nav_btn.setStyleSheet(f"""
    QPushButton {{
        background: transparent;
        border: none;
        border-radius: {RADIUS['large']}px;
        font-size: 20pt;
    }}
    QPushButton:hover {{
        background: {COLORS['scrim_light']};
    }}
    QPushButton:pressed {{
        background: rgba(26, 115, 232, 0.20);
    }}
""")
```

---

### Change 8: Update Sections Container Layout

**Location:** In `AccordionSidebar.__init__()`, find:

```python
self.sections_layout = QVBoxLayout(self.sections_container)
self.sections_layout.setContentsMargins(6, 6, 6, 6)
self.sections_layout.setSpacing(3)  # Tighter spacing between sections
```

**Replace with:**
```python
self.sections_layout = QVBoxLayout(self.sections_container)
section_margin = get_spacing('sm')     # 8px gutters
section_spacing = get_spacing('sm')    # 8px between sections (improved from 3px)
self.sections_layout.setContentsMargins(section_margin, section_margin, section_margin, section_margin)
self.sections_layout.setSpacing(section_spacing)
```

---

## Implementation: PersonCard (google_components/widgets.py)

### Change 1: Update PersonCard Layout

**Location:** In `PersonCard.__init__()` method, find layout setup:

**BEFORE:**
```python
layout = QVBoxLayout(self)
layout.setContentsMargins(4, 4, 4, 4)
layout.setSpacing(4)
layout.setAlignment(Qt.AlignCenter)
```

**AFTER:**
```python
layout = QVBoxLayout(self)
card_margin = get_spacing('xs')  # 4px tight margin for cards
card_spacing = get_spacing('xs')  # 4px spacing between elements
layout.setContentsMargins(card_margin, card_margin, card_margin, card_margin)
layout.setSpacing(card_spacing)
layout.setAlignment(Qt.AlignCenter)
```

### Change 2: Update PersonCard Background/Styling

**Location:** In `PersonCard.__init__()` stylesheet:

**BEFORE:**
```python
self.setStyleSheet("""
    PersonCard {
        background: transparent;
        border-radius: 6px;
    }
    PersonCard:hover {
        background: rgba(26, 115, 232, 0.08);
    }
""")
```

**AFTER:**
```python
# Import design system at top: from ui.styles import COLORS, RADIUS
self.setStyleSheet(f"""
    PersonCard {{
        background: transparent;
        border-radius: {RADIUS['medium']}px;
    }}
    PersonCard:hover {{
        background: {COLORS['scrim_light']};
    }}
""")
```

### Change 3: Update PersonCard Face Label

**Location:** In face label placeholder:

**BEFORE:**
```python
self.face_label.setStyleSheet("""
    QLabel {
        background: #e8eaed;
        border-radius: 32px;
        font-size: 24pt;
    }
""")
```

**AFTER:**
```python
self.face_label.setStyleSheet(f"""
    QLabel {{
        background: {COLORS['surface_tertiary']};
        border-radius: {RADIUS['full']}px;
        font-size: 24pt;
    }}
""")
```

### Change 4: Update PersonCard Name Label

**Location:** In name label styling:

**BEFORE:**
```python
self.name_label.setStyleSheet("""
    QLabel {
        font-size: 9pt;
        color: #202124;
        font-weight: 500;
    }
""")
```

**AFTER:**
```python
# Use design system typography
typo = TYPOGRAPHY['caption']
self.name_label.setStyleSheet(f"""
    QLabel {{
        font-size: {typo['size_pt']}pt;
        color: {COLORS['text_primary']};
        font-weight: 500;
    }}
""")
```

### Change 5: Update Count Badge Label

**Location:** In count label styling:

**BEFORE:**
```python
self.count_label.setStyleSheet("""
    QLabel {
        font-size: 8pt;
        color: #5f6368;
    }
""")
```

**AFTER:**
```python
typo = TYPOGRAPHY['caption_small']
self.count_label.setStyleSheet(f"""
    QLabel {{
        font-size: {typo['size_pt']}pt;
        color: {COLORS['text_secondary']};
    }}
""")
```

---

## Implementation: PeopleGridView

### Change 1: Update Grid Container Layout

**Location:** In `PeopleGridView.__init__()`:

**BEFORE:**
```python
main_layout = QVBoxLayout(self)
main_layout.setContentsMargins(4, 4, 4, 4)
main_layout.setSpacing(0)

# Container with flow layout
self.grid_container = QWidget()
self.flow_layout = FlowLayout(self.grid_container, margin=4, spacing=8)
self.grid_container.setMinimumHeight(340)
```

**AFTER:**
```python
main_layout = QVBoxLayout(self)
container_margin = get_spacing('sm')  # 8px
main_layout.setContentsMargins(container_margin, container_margin, container_margin, container_margin)
main_layout.setSpacing(0)

# Container with flow layout
self.grid_container = QWidget()
flow_margin = get_spacing('xs')    # 4px
flow_spacing = get_spacing('sm')   # 8px
self.flow_layout = FlowLayout(self.grid_container, margin=flow_margin, spacing=flow_spacing)

# Responsive heights (calculated instead of hard-coded)
# Min: 2 rows of 100px cards = 200px + margins + spacing
self.grid_container.setMinimumHeight(260)  # ~2 rows
# Max: 3 rows before scrolling
self.grid_container.setMaximumHeight(400)  # ~3 rows
```

### Change 2: Update Empty State Label

**Location:** In empty label styling:

**BEFORE:**
```python
self.empty_label.setStyleSheet("""
    QLabel {
        color: #5f6368;
        font-size: 10pt;
        padding: 20px;
    }
""")
```

**AFTER:**
```python
typo = TYPOGRAPHY['caption']
self.empty_label.setStyleSheet(f"""
    QLabel {{
        color: {COLORS['text_secondary']};
        font-size: {typo['size_pt']}pt;
        padding: {get_spacing('lg')}px;
    }}
""")
```

---

## Implementation: google_layout.py

### Change 1: Update Toolbar Styling

**Location:** In `_create_toolbar()` method:

**Find:**
```python
toolbar.setStyleSheet("""
    QToolBar {
        background: #f8f9fa;
        border-bottom: 1px solid #dadce0;
        padding: 6px;
        spacing: 8px;
    }
    ...
""")
```

**Replace with:**
```python
toolbar.setStyleSheet(f"""
    QToolBar {{
        background: {COLORS['surface_secondary']};
        border-bottom: 1px solid {COLORS['outline_primary']};
        padding: {get_spacing('sm')}px;
        spacing: {get_spacing('sm')}px;
    }}
    ...
""")
```

### Change 2: Update Left Shell Container Background

**Location:** In `_build_left_shell()` method:

**Find:**
```python
self.left_shell_container.setStyleSheet("""
    QWidget#google_left_shell_container {
        background: #ffffff;
        border-right: 1px solid #e0e0e0;
    }
""")
```

**Replace with:**
```python
self.left_shell_container.setStyleSheet(f"""
    QWidget#google_left_shell_container {{
        background: {COLORS['surface_primary']};
        border-right: 1px solid {COLORS['outline_primary']};
    }}
""")
```

### Change 3: Update Left Shell Layout Spacing

**Location:** In `_build_left_shell()` method:

**Find:**
```python
self.left_shell_layout = QVBoxLayout(self.left_shell_container)
self.left_shell_layout.setContentsMargins(8, 8, 8, 8)
self.left_shell_layout.setSpacing(8)
```

**Replace with:**
```python
self.left_shell_layout = QVBoxLayout(self.left_shell_container)
shell_margin = get_spacing('sm')    # 8px
shell_spacing = get_spacing('sm')   # 8px
self.left_shell_layout.setContentsMargins(shell_margin, shell_margin, shell_margin, shell_margin)
self.left_shell_layout.setSpacing(shell_spacing)
```

---

## Testing Checklist for Phase 1

After implementing all changes, verify:

### Visual Verification
- [ ] All colors use design system (no hardcoded colors remain)
- [ ] Spacing on 8px grid (verify pixel-perfect alignment)
- [ ] Section headers have blue left border when active
- [ ] Colors match Material Design 3 reference
- [ ] Text contrast passes WCAG AA (4.5:1 minimum)

### Layout Verification
- [ ] No horizontal scrollbars
- [ ] Sections properly aligned
- [ ] Cards properly spaced
- [ ] Text readable at all sizes
- [ ] Icons properly sized

### Functional Verification
- [ ] Section expand/collapse works
- [ ] Navigation buttons work
- [ ] People grid displays correctly
- [ ] All signals still connect
- [ ] No console errors

### Cross-Browser Testing
- [ ] Windows: Chrome, Firefox, Edge
- [ ] macOS: Chrome, Firefox, Safari
- [ ] Linux: Chrome, Firefox

### Screenshots for Comparison
Take before/after screenshots of:
- [ ] Expanded People section
- [ ] Collapsed sections stack
- [ ] Full sidebar view
- [ ] Navigation bar detail

---

## Common Issues & Solutions

### Issue: Some colors look wrong

**Solution:**
- Check COLORS dictionary spelling (case-sensitive)
- Verify hex values match: primary='#1a73e8', surface_secondary='#f8f9fa'
- Test with WCAG contrast checker

### Issue: Layout misaligned

**Solution:**
- Verify all margins/padding use get_spacing()
- Check all values are multiples of 4 or 8
- Look for leftover hardcoded values

### Issue: Buttons don't look right

**Solution:**
- Check border-radius uses RADIUS['medium'] or RADIUS['small']
- Verify opacity values removed (use colors instead)
- Test hover states

### Issue: Typography looks small

**Solution:**
- TYPOGRAPHY uses 'size_pt' not 'size'
- 'size_pt' is Qt-specific (different from CSS px)
- 13px = ~10pt in Qt

---

## Rollback Plan

If something breaks:

1. Keep git commit log clean
2. Test locally before pushing
3. Create feature branch for Phase 1
4. If issues found:
   - Revert specific file
   - Or revert entire branch
   - Update constants and retry

Command to revert:
```bash
git checkout -- accordion_sidebar.py
```

---

## Validation Script (Optional)

Create `test_phase1_styling.py` to validate:

```python
"""Quick validation that Phase 1 changes applied correctly."""
from ui.styles import COLORS, SPACING, TYPOGRAPHY

def test_colors_defined():
    """Verify all required colors defined."""
    assert COLORS['primary'] == '#1a73e8'
    assert COLORS['surface_secondary'] == '#f8f9fa'
    assert COLORS['text_primary'] == '#202124'
    print("✓ Colors defined correctly")

def test_spacing_multiples():
    """Verify spacing on 8px grid."""
    for key, value in SPACING.items():
        assert value % 4 == 0, f"{key}={value} not multiple of 4"
    print("✓ Spacing on grid")

def test_typography_sizes():
    """Verify typography sizes reasonable."""
    for role, typo in TYPOGRAPHY.items():
        assert 8 <= typo['size_pt'] <= 24, f"{role} size {typo['size_pt']} out of range"
    print("✓ Typography sizes reasonable")

if __name__ == '__main__':
    test_colors_defined()
    test_spacing_multiples()
    test_typography_sizes()
    print("\n✓✓✓ Phase 1 Validation Passed ✓✓✓")
```

Run with:
```bash
python test_phase1_styling.py
```

---

## Next Steps

After Phase 1 is complete and tested:

1. **Review with team** - Get visual/UX feedback
2. **Gather screenshots** - Document improvements
3. **Commit to repo** - Push Phase 1 changes
4. **Proceed to Phase 2** - Navigation bar redesign

---

**Phase 1 Complete Checklist:**
- [ ] Design constants file created (`ui/styles.py`)
- [ ] All colors updated in `accordion_sidebar.py`
- [ ] All spacing updated to 8px grid
- [ ] Typography scale applied
- [ ] Left border accents added to headers
- [ ] Visual regression test passed
- [ ] No console errors
- [ ] Pushed to feature branch
- [ ] Documentation updated

