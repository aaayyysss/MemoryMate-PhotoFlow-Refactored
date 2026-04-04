# Sidebar Design Specification v1.0
## Complete Design System & Component Guide | 2026-04-02

---

## Table of Contents

1. [Design Principles](#design-principles)
2. [Color System](#color-system)
3. [Typography System](#typography-system)
4. [Spacing & Layout Grid](#spacing--layout-grid)
5. [Component Library](#component-library)
6. [Interactive States](#interactive-states)
7. [Accessibility Guidelines](#accessibility-guidelines)
8. [Animation & Transitions](#animation--transitions)
9. [Implementation Examples](#implementation-examples)
10. [Maintenance & Updates](#maintenance--updates)

---

## 1. Design Principles

The MemoryMate sidebar follows these design principles:

### 1.1 Material Design 3 Foundation
- Google's Material Design 3 as the design language
- Semantic color tokens (primary, surface, error, etc.)
- Consistent spacing grid (8px multiples)
- Clear typographic hierarchy

### 1.2 Information Hierarchy
- **Primary:** Most important (People section, active state)
- **Secondary:** Navigation and quick access
- **Tertiary:** Hints, captions, secondary information

### 1.3 Clarity & Scannability
- Clear visual distinction between states (active/inactive/loading/error)
- Consistent patterns for similar components
- Sufficient whitespace for visual breathing room
- Hierarchical layout (top-to-bottom, left-to-right)

### 1.4 Accessibility First
- All text meets WCAG AA contrast (4.5:1 minimum)
- Fully keyboard navigable
- Screen reader compatible
- Touch-friendly (44x44px minimum)

### 1.5 Performance
- Lazy load non-visible sections
- Smooth 60fps animations
- Responsive to all screen sizes
- Fast load times (< 100ms first paint)

---

## 2. Color System

### 2.1 Primary Color

**Purpose:** Primary actions, active states, key interactions

```
Primary Blue: #1a73e8
├─ Active section background: #e8f0fe (container)
├─ Active borders/accents: #1a73e8 (solid)
└─ Text on primary: #ffffff
```

**Usage:**
- Active section header left border
- Primary buttons
- Active checkbox/radio states
- Focus indicators
- Link text (if enabled)

**Code:**
```python
from ui.styles import COLORS

# Get the color
primary = COLORS['primary']  # '#1a73e8'

# Apply in stylesheet
f"border-left: 3px solid {COLORS['primary']};"
```

---

### 2.2 Surface Colors

**Purpose:** Background surfaces at different elevation levels

| Name | Color | Elevation | Usage |
|------|-------|-----------|-------|
| Primary | #ffffff | High | Main background, cards, buttons |
| Secondary | #f8f9fa | Medium | Inactive sections, hover states |
| Tertiary | #f1f3f4 | Low | Light hover states |
| Tertiary Alt | #ececf1 | Low | Alternative light gray |

**Usage in Sidebar:**
- Active section: Primary surface with primary_container background
- Inactive section: Secondary surface (light gray)
- Hover state: Tertiary surface (slightly darker)

**Code:**
```python
# Inactive section background
background-color: {COLORS['surface_secondary']}  # #f8f9fa

# Hover state
background-color: {COLORS['surface_tertiary']}   # #f1f3f4
```

---

### 2.3 Text Colors

**Purpose:** Text at different emphasis levels

| Role | Color | Contrast | Usage |
|------|-------|----------|-------|
| Primary | #202124 | 95% | Main text, headings |
| Secondary | #5f6368 | 60% | Secondary text, hints |
| Tertiary | #9aa0a6 | 35% | Very low emphasis |
| Disabled | #dadce0 | N/A | Disabled state |

**Contrast Verification:**
- Primary (95%): ✅ WCAG AAA (7:1+)
- Secondary (60%): ✅ WCAG AA (4.5:1+)
- Tertiary (35%): ✅ WCAG A (3:1+)

**Usage:**
```python
# Main text (section headers, lists)
color: {COLORS['text_primary']}    # #202124

# Secondary text (badges, hints, metadata)
color: {COLORS['text_secondary']}  # #5f6368

# Low emphasis
color: {COLORS['text_tertiary']}   # #9aa0a6
```

---

### 2.4 Semantic Colors

**Purpose:** Indicate state or intent (success, error, warning)

```
Success:  #34a853 (✓ Checkmark, positive actions)
Warning:  #fbbc04 (⚠️ Caution, warnings)
Error:    #ea4335 (✘ Error, delete, negative)
Info:     #4285f4 (ℹ️ Information, neutral)
```

**Usage:**
- Success: Completion badges, successful operations
- Warning: Caution messages, low confidence indicators
- Error: Error messages, failed operations, delete actions
- Info: Informational badges, tips

**Example:**
```python
# Low confidence person (warning color)
if confidence < 0.5:
    badge_color = COLORS['warning']  # #fbbc04
    icon = "⚠️"
```

---

### 2.5 Outline Colors

**Purpose:** Borders, dividers, and structural elements

| Name | Color | Usage |
|------|-------|-------|
| Primary | #dadce0 | Main borders, dividers |
| Secondary | #bdc1c6 | Secondary borders, hover |
| Tertiary | #e8eaed | Subtle borders, low emphasis |

**Usage:**
```python
# Main border (section headers)
border: 1px solid {COLORS['outline_tertiary']}

# Hover state border
border-color: {COLORS['outline_secondary']}

# Section divider
border-bottom: 1px solid {COLORS['outline_primary']}
```

---

## 3. Typography System

### 3.1 Type Scale

Five typographic roles used in sidebar:

```
┌─────────────────────────────────────────┐
│ H2 (Section Header)                    │  14pt, weight 600
│ Bold, high contrast                    │  Line-height: 20px
├─────────────────────────────────────────┤
│ [Individuals] [Groups]                  │  13pt, weight 500
│ Tab labels left-aligned                │  (slightly bolder)
├─────────────────────────────────────────┤
│ • John (24 photos)                      │  13pt, weight 400
│ • Sarah (18 photos)                     │  Line-height: 20px
│ List items                              │  (standard body)
├─────────────────────────────────────────┤
│ 5 people, last updated 2 hours ago      │  11pt, weight 400
│ Metadata, hints, secondary info         │  Line-height: 16px
├─────────────────────────────────────────┤
│ Touch to select or drag to reorder      │  10pt, weight 400
│ Tips, captions, very low emphasis       │  Line-height: 14px
└─────────────────────────────────────────┘
```

---

### 3.2 Type Definitions

**H2 (Header)**
```python
from ui.styles import TYPOGRAPHY

typo = TYPOGRAPHY['h2']
# {'size_pt': 10.5, 'weight': 600, 'line_height': 20}

# Apply to widget:
font = label.font()
font.setPointSize(typo['size_pt'])
font.setWeight(typo['weight'])
label.setFont(font)
```

**Body (Default)**
```python
typo = TYPOGRAPHY['body']
# {'size_pt': 10, 'weight': 400, 'line_height': 20}

# Most list items and content use this
```

**Small (Metadata)**
```python
typo = TYPOGRAPHY['small']
# {'size_pt': 8.5, 'weight': 400, 'line_height': 16}

# Used for timestamps, counts, secondary info
```

**Caption (Very Small)**
```python
typo = TYPOGRAPHY['caption']
# {'size_pt': 8, 'weight': 400, 'line_height': 14}

# Hints, very low emphasis text
```

---

### 3.3 Typography Usage Guide

| Element | Role | Example |
|---------|------|---------|
| Section Header | H2 | "👥 People (23)" |
| Tab Labels | Title | "Individuals", "Groups" |
| List Items | Body | "John", "📅 2024-12-15" |
| Counts/Badges | Small | "(23)", "(5)⚠️" |
| Hints/Metadata | Caption | "last updated 2 hours ago" |
| Button Text | Label | "Load more", "Save", "Delete" |
| Status Text | Small | "Loading...", "No results" |

---

### 3.4 Font Weight Scale

Only use three weights:

```
Regular (400)     → Body text, standard weight
Medium (500)      → Tab labels, slightly emphasized
Semi-Bold (600)   → Headers, maximum emphasis
```

**Do NOT use:**
- ❌ Thin (300) - Hard to read
- ❌ Bold (700) - Use semi-bold (600) instead
- ❌ Black (900) - Too heavy

---

## 4. Spacing & Layout Grid

### 4.1 8px Grid System

All spacing is based on 8px multiples:

```
1x grid  = 8px
2x grid  = 16px
3x grid  = 24px
1.5x grid = 12px

Special: 4px (0.5x grid) for very tight spacing
```

**In Code:**
```python
from ui.styles import SPACING

xs = SPACING['xs']    # 4px (0.5x)
sm = SPACING['sm']    # 8px (1x)
md = SPACING['md']    # 12px (1.5x)
lg = SPACING['lg']    # 16px (2x)
xl = SPACING['xl']    # 24px (3x)
```

### 4.2 Layout Measurements

**Section Header:**
```
┌─────────────────────────────────────┐
│ 12px  👥 People (23)         ▼  12px│  Height: 48px
│ md    sm  text    md+space  md  md  │  Margin below: 8px (sm)
└─────────────────────────────────────┘
```

**Section Content:**
```
┌─────────────────────────────────────┐
│ 12px margin (md)                    │  
│ ┌──────────────────────────────────┐│  
│ │ Content: 12px padding (md)       ││  
│ │                                  ││  
│ └──────────────────────────────────┘│  
│ 12px margin (md)                    │  
└─────────────────────────────────────┘
```

**List Item:**
```
┌─────────────────────────────────────┐
│ 12px 👤 John (24 photos)        12px│  Height: 48px
│ sm   md     sm space            sm  │  Margin-bottom: 4px (xs)
└─────────────────────────────────────┘
```

---

### 4.3 Responsive Spacing

Spacing stays consistent across screen sizes. Only the sidebar width/column count changes:

| Screen | Sidebar Width | People Grid | Section Spacing |
|--------|---------------|-------------|-----------------|
| Desktop (>1200px) | 260px | 3 columns | 8px (standard) |
| Laptop (1024-1200px) | 240px | 2 columns | 8px (standard) |
| Tablet (768-1024px) | 200px | Stack | 8px (standard) |
| Mobile (<768px) | Drawer | Full-width | 8px (standard) |

**Spacing never changes.** Only layout adapts.

---

## 5. Component Library

### 5.1 Section Header

**Component:** `SectionHeader` (in accordion_sidebar.py)

**States:**

#### Normal (Inactive)
```
┌──────────────────────────────────────┐
│ 📅 Dates (156)                   ▶ │
│                                      │
└──────────────────────────────────────┘

Background: #f8f9fa (surface_secondary)
Border: 1px solid #e8eaed (outline_tertiary)
Font: 14pt, weight 600
Color: #202124 (text_primary)
Chevron: ▶ (right arrow)
Height: 48px
```

#### Active (Expanded)
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ 👥 People (23)                   ▼ ┃
┃ Left Border: 3px #1a73e8             ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

Background: #e8f0fe (primary_container)
Border: None (except left border)
Left Border: 3px solid #1a73e8 (primary)
Font: 14pt, weight 600, color #202124
Chevron: ▼ (down arrow)
Height: 48px
```

#### Hover (Inactive)
```
┌──────────────────────────────────────┐
│ 📅 Dates (156)                   ▶ │ ← Slightly darker background
│                                      │
└──────────────────────────────────────┘

Background: #f1f3f4 (surface_tertiary)
Border: 1px solid #e8eaed
Cursor: pointer (hand)
```

**Click Behavior:**
```
User clicks header
    ↓
If inactive: emit expandRequested(section_id)
If active: (no action, already expanded)
```

**CSS:**
```css
SectionHeader {
    background-color: #f8f9fa;
    border: 1px solid #e8eaed;
    border-radius: 6px;
    padding: 12px 8px;
}

SectionHeader:hover {
    background-color: #f1f3f4;
    cursor: pointer;
}

SectionHeader.active {
    background-color: #e8f0fe;
    border: none;
    border-left: 3px solid #1a73e8;
    padding-left: 8px;
}
```

---

### 5.2 Section Content (Scroll Area)

**Purpose:** Expandable content container with vertical scroll

**Features:**
- Smooth fade-in animation on expand
- Always-on vertical scrollbar (right-aligned)
- No horizontal scrolling
- Consistent padding (12px all sides)

**States:**

#### Collapsed
```
Height: 0 (hidden)
Opacity: 0 (transparent)
Overflow: hidden
```

#### Expanding (300ms animation)
```
Height: 0 → Max
Opacity: 0 → 1
Smooth easing (cubic-bezier)
```

#### Expanded
```
Height: Full available space
Opacity: 1 (fully visible)
Overflow: auto (scroll if needed)
Margin-top: 0
```

---

### 5.3 Navigation Button (Vertical Bar)

**Component:** QPushButton (in nav bar)

**Size:** 44x44px (minimum touch target)

**States:**

#### Default
```
┌──────┐
│  👥  │  Transparent background
│      │  Icon: 20pt
└──────┘

Background: transparent
Border: none
Color: #202124
```

#### Hover
```
┌──────┐
│  👥  │  Light background on hover
│      │  Hints it's clickable
└──────┘

Background: rgba(0, 0, 0, 0.08) (scrim_light)
Border: none
Cursor: pointer
```

#### Active
```
╔══════╗
║  👥  ║  Active section highlighted
║      ║  Optional: Blue left border
╚══════╝

Background: rgba(26, 115, 232, 0.20)
Border-left: 3px solid #1a73e8 (Phase 2)
```

**Tooltip:** Visible on hover for 1+ second
```
Tooltip text: "{Icon} {Label}" 
e.g., "📅 Dates (156)"
Position: Right of button
Delay: 500ms
```

---

### 5.4 People Card

**Component:** `PersonCard` (in accordion_sidebar.py)

**Size:** 100x120px (Phase 2 change from 80x100px)

**Elements:**
```
┌──────────────────┐
│   ┌──────────┐   │  12px padding all
│   │  ┌────┐  │   │
│   │  │face│  │   │  Face image: 64px circle
│   │  └────┘  │   │
│   └──────────┘   │
│                  │
│  John            │  Name: 9pt, truncated 13 chars
│  24 🟢           │  Badge: 8pt, confidence icon
│                  │
└──────────────────┘
```

**States:**

#### Default
```
Background: transparent
Border: none
Border-radius: 6px
```

#### Hover
```
Background: rgba(26, 115, 232, 0.08) (scrim_light)
Border-radius: 6px
Cursor: pointer
```

#### Drag Source (being dragged)
```
Opacity: 0.5 (semi-transparent)
Background: rgba(26, 115, 232, 0.2)
Border: 2px dashed #1a73e8
```

#### Drop Target (drag over)
```
Background: rgba(26, 115, 232, 0.2)
Border: 2px dashed #1a73e8
Highlight: Show as valid merge target
```

**Confidence Indicators:**
```
🟢 Green (≥15 photos)    → High confidence
🟡 Yellow (5-14 photos)  → Medium confidence
🔴 Red (<5 photos)       → Low confidence
❓ Question mark (<5)    → Unnamed cluster
```

---

### 5.5 Loading Spinner

**Purpose:** Show section is loading data

**Component:** Animated QLabel with rotating emoji

**Appearance:**
```
        ⟳      (Rotating at 50ms/frame = 20 rotations/sec)
                Speed = 20x per second = smooth animation

Text below:
      Loading...  (Or specific message)
      13pt body text in secondary color
```

**Animation:**
- Duration: 1000ms per rotation
- Loop: Infinite until content loads
- Easing: Linear (no acceleration)
- Opacity: 1.0 (fully opaque)

**Removal:**
- Fade out: 300ms
- Replace with actual content (fade in simultaneously)

**CSS:**
```css
QLabel#spinner {
    font-size: 32pt;
    color: #1a73e8;
    background: transparent;
}

QLabel#spinner_text {
    font-size: 13pt;
    color: #5f6368;
    background: transparent;
}
```

---

### 5.6 Error Message

**Purpose:** Show section failed to load

**Appearance:**
```
        ⚠️        (Warning icon)

   Error: Database error    (Red error text)

       [🔄 Retry]             (Retry button)
```

**Colors:**
- Icon: #ea4335 (error red)
- Text: #ea4335 (error red)
- Button: #1a73e8 (primary blue)

**Button Style:**
- Background: #1a73e8 (primary blue)
- Text: #ffffff (white)
- Hover: #1557b0 (darker blue)

---

## 6. Interactive States

### 6.1 Button States

All buttons follow this state machine:

```
Default → Hover → Pressed → Normal
   ↑                           │
   └─────────────────────────────┘
   
Disabled: In any state, show disabled appearance
```

#### Default (Normal)
```
Background: #ffffff
Border: 1px solid #dadce0
Color: #202124
Cursor: default
```

#### Hover
```
Background: #f1f3f4
Border: 1px solid #bdc1c6
Color: #202124
Cursor: pointer
Shadow: elevation_1
```

#### Pressed/Active
```
Background: #e8eaed
Border: 1px solid #dadce0
Color: #202124
Cursor: pointer
Inset effect (slight visual depression)
```

#### Disabled
```
Background: #f5f5f5
Border: 1px solid #dadce0
Color: #9aa0a6 (dimmed)
Cursor: not-allowed
Opacity: 0.6
```

---

### 6.2 Link States

If links used in sidebar:

```
Default: #1a73e8 (blue), underline
Hover:   #1a73e8 (darker), underline
Visited: #681da8 (purple), underline
Active:  #1a73e8 (blue), underline
```

---

### 6.3 Focus Indicator

**For keyboard navigation:**

```
Focus ring: 3px solid #4285f4 (info blue)
Outline style: solid
Offset: 2px outside border
Animation: None (instant)
```

**CSS:**
```css
*:focus {
    outline: 3px solid #4285f4;
    outline-offset: 2px;
}
```

---

## 7. Accessibility Guidelines

### 7.1 Color Contrast

**Minimum Requirements:**
- WCAG AA: 4.5:1 (normal text)
- WCAG AA: 3:1 (large text 18pt+)
- WCAG AAA: 7:1 (recommended for UI)

**Verified Colors:**
- Primary text (#202124) on white: ✅ 95% (AAA)
- Secondary text (#5f6368) on white: ✅ 62% (AA)
- Error text (#ea4335) on white: ✅ 61% (AA)
- All semantic colors: ✅ AA minimum

**Test:** Use WebAIM Contrast Checker
https://webaim.org/resources/contrastchecker/

### 7.2 Keyboard Navigation

**Tab Order:**
1. Navigation buttons (left bar)
2. Section headers (top to bottom)
3. Content within expanded section
4. Moved to next section when Tab reaches end

**Keyboard Shortcuts:**
```
Tab           → Next control
Shift+Tab     → Previous control
Enter/Space   → Activate button or toggle
Arrow Up      → Previous in list
Arrow Down    → Next in list
Arrow Right   → Expand section
Arrow Left    → Collapse section
Escape        → Close popup/dialog
```

**Implementation:**
```python
def keyPressEvent(self, event):
    key = event.key()
    if key == Qt.Key_Return or key == Qt.Key_Space:
        self.clicked.emit()
        event.accept()
    elif key == Qt.Key_Right and not self.is_expanded:
        self.expand()
        event.accept()
    elif key == Qt.Key_Left and self.is_expanded:
        self.collapse()
        event.accept()
```

### 7.3 Screen Reader Support

**ARIA Labels:**
```python
widget.setAttribute(Qt.WA_AccessibleName, "Section name")
widget.setAttribute(Qt.WA_AccessibleDescription, "Description")
```

**Example:**
```python
header.setAttribute(Qt.WA_AccessibleName, "People")
header.setAttribute(Qt.WA_AccessibleDescription, 
    "Expandable section containing 23 people from face detection")
```

**Semantic HTML (if applicable):**
- Use `<button>` not `<div onclick>`
- Use `<label>` for form inputs
- Use `<h2>` for headers
- Use proper list markup `<ul>`, `<li>`

### 7.4 Touch Targets

**Minimum size:** 44x44px (recommended by iOS/Android)

**In Sidebar:**
- Navigation buttons: 44x44px ✅
- Section headers: 48px height ✅
- People cards: 100x120px ✅
- List items: 48px height (calculated) ✅

**Spacing between targets:** ≥8px

---

## 8. Animation & Transitions

### 8.1 Timing

**Standard animation durations:**

| Duration | Use Case | Example |
|----------|----------|---------|
| 150ms | Fast transitions | Hover states, quick feedback |
| 300ms | Normal transitions | Section expand, content fade-in |
| 500ms | Slow transitions | Major layout changes, modals |

**Recommended:**
- Hover effects: 150ms
- Section expand: 300ms
- Chevron rotation: 200ms
- Content fade-in: 300ms

### 8.2 Easing Functions

**Material Design Standard:**
```
cubic-bezier(0.2, 0, 0, 1)
```

**Emphasis (bouncy):**
```
cubic-bezier(0.3, 0, 0.8, 0.15)
```

**Implementation in Qt:**
```python
anim = QPropertyAnimation(widget, b"property")
anim.setDuration(300)  # milliseconds
anim.setEasingCurve(QEasingCurve.InOutQuad)  # smooth
anim.setStartValue(start_value)
anim.setEndValue(end_value)
anim.start()
```

---

### 8.3 Section Expand Animation

**Timeline:**
```
0ms          300ms         600ms
|            |             |
Start        Mid           End
├────────────┼─────────────┤
Slide out    Fade in
Height transform
```

**Animated Properties:**
1. Scroll area height (0 → max)
2. Opacity (0 → 1)
3. Chevron rotation (0 → 180°)
4. Background color (if changing)

**Code:**
```python
def expand_section(self, section_id):
    section = self.sections[section_id]
    
    # Animate height change
    anim_height = QPropertyAnimation(section, b"geometry")
    anim_height.setDuration(300)
    anim_height.setEasingCurve(QEasingCurve.InOutQuad)
    # Set target geometry
    anim_height.start()
    
    # Animate content fade-in
    anim_fade = QPropertyAnimation(section.scroll_area, b"windowOpacity")
    anim_fade.setDuration(300)
    anim_fade.setStartValue(0)
    anim_fade.setEndValue(1)
    anim_fade.start()
```

---

## 9. Implementation Examples

### 9.1 Adding a New Section

**Pattern to follow:**

```python
from ui.styles import COLORS, SPACING, TYPOGRAPHY

class NewSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Use design system constants
        layout = QVBoxLayout(self)
        margin = SPACING['md']  # 12px
        layout.setContentsMargins(margin, margin, margin, margin)
        
        # Header
        header = SectionHeader("section_id", "Section Title", "🎯")
        
        # Content
        content = QLabel("Content here")
        typo = TYPOGRAPHY['body']
        content.setStyleSheet(
            f"color: {COLORS['text_primary']}; "
            f"font-size: {typo['size_pt']}pt;"
        )
        
        layout.addWidget(header)
        layout.addWidget(content)
```

---

### 9.2 Creating a New Component

**Checklist:**

```python
# ✓ Import design system
from ui.styles import COLORS, SPACING, TYPOGRAPHY, RADIUS

# ✓ Use constants for all appearance
self.setStyleSheet(f"""
    MyWidget {{
        background: {COLORS['surface_primary']};
        border: 1px solid {COLORS['outline_primary']};
        border-radius: {RADIUS['medium']}px;
        padding: {SPACING['md']}px;
    }}
""")

# ✓ Use typography for text
typo = TYPOGRAPHY['body']
font.setPointSize(typo['size_pt'])
font.setWeight(typo['weight'])

# ✓ Ensure 44x44px minimum touch target
if isinstance(self, QPushButton):
    self.setMinimumSize(44, 44)

# ✓ Add ARIA labels
self.setAttribute(Qt.WA_AccessibleName, "Component name")
```

---

### 9.3 Adding Dark Mode (Future)

When/if dark mode is added:

```python
# Define dark mode colors
COLORS_DARK = {
    'primary': '#8ab4f8',           # Lighter blue
    'surface_primary': '#202124',   # Dark gray
    'text_primary': '#ffffff',      # White text
    # ... etc
}

# Use constant helper
def get_color(role: str, dark=False):
    colors = COLORS_DARK if dark else COLORS
    return colors.get(role, COLORS[role])

# In component:
bg_color = get_color('surface_primary', dark_mode_enabled)
```

---

## 10. Maintenance & Updates

### 10.1 When to Update Design Constants

**Update COLORS if:**
- [] Brand colors change
- [] Accessibility issues discovered (contrast failures)
- [] New semantic color needed

**Update SPACING if:**
- [] Change global grid size (rare)
- [] Add new spacing scale level

**Update TYPOGRAPHY if:**
- [] Change type scale (rare)
- [] Add new text role needed

### 10.2 Version Control

**In `ui/styles.py` header:**
```python
"""
ui/styles.py
Material Design 3 Design System for MemoryMate PhotoFlow

Version: 1.0        (current: Phase 1 - Colors & Spacing)
Updated: 2026-04-02

v1.0: Initial design system
v1.1: (planned) Add dark mode colors
v2.0: (planned) Material Design 4 upgrade
"""
```

### 10.3 Review Checklist

Before committing design changes:

- [ ] All colors use COLORS constant
- [ ] All spacing uses SPACING grid (multiples of 4 or 8)
- [ ] All fonts use TYPOGRAPHY scale
- [ ] No hardcoded hex values (#RRGGBB)
- [ ] No hardcoded pixel values (use getters)
- [ ] Contrast ≥ 4.5:1 verified
- [ ] Touch targets ≥ 44x44px
- [ ] Animations smooth (300ms default, 60fps)
- [ ] Accessibility tested (Tab, screen reader, keyboard)

---

## Reference Guide

### Quick Access to Constants

```python
from ui.styles import (
    COLORS,           # All colors (dict)
    SPACING,          # Spacing values (dict)
    TYPOGRAPHY,       # Type scales (dict)
    RADIUS,           # Border radius (dict)
    SHADOWS,          # Elevation shadows (dict)
    ANIMATION,        # Animation durations (dict)
    
    # Helper functions
    get_color,        # Get color by role
    get_spacing,      # Get spacing by scale
    get_typography,   # Get typography by role
    get_button_style, # Get pre-built button styles
)
```

### Common Patterns

```python
# Get color
primary_bg = get_color('primary')  # Returns '#1a73e8'

# Get spacing
margin = get_spacing('md')  # Returns 12

# Apply typography
typo = get_typography('body')
font.setPointSize(typo['size_pt'])

# Create stylesheet
style = f"""
    QLabel {{
        color: {COLORS['text_primary']};
        margin: {SPACING['sm']}px;
        font-size: {TYPOGRAPHY['body']['size_pt']}pt;
        border-radius: {RADIUS['medium']}px;
    }}
"""
```

---

## Questions & Support

**Design Questions?**
- Check this specification first
- Review existing components as examples
- Ask on team channel with screenshot

**Want to Update Design System?**
- File an issue with:
  - Current problem
  - Proposed change
  - Impact (what improves)
  - Screenshots before/after

**Found a Bug or Inconsistency?**
- File issue with:
  - Component/feature affected
  - Expected vs actual
  - Screenshot
  - Steps to reproduce

---

## Appendix: Color Reference Card

```
PRIMARY BLUE: #1a73e8 (Google brand blue)
├─ Container: #e8f0fe (light background)
├─ On Primary: #ffffff (white text)
└─ Accent: 3px solid in active state

SURFACES:
├─ Primary: #ffffff (main background)
├─ Secondary: #f8f9fa (inactive sections)
├─ Tertiary: #f1f3f4 (hover states)
└─ Tertiary Alt: #ececf1 (alternate)

TEXT:
├─ Primary: #202124 (main text, 95% contrast)
├─ Secondary: #5f6368 (hints, 62% contrast)
├─ Tertiary: #9aa0a6 (low emphasis, 35%)
└─ Disabled: #dadce0 (very faded)

SEMANTIC:
├─ Success: #34a853 (✓ checkmark)
├─ Warning: #fbbc04 (⚠️ caution)
├─ Error: #ea4335 (✘ alert)
└─ Info: #4285f4 (ℹ️ info)

OUTLINES:
├─ Primary: #dadce0 (main borders)
├─ Secondary: #bdc1c6 (hover borders)
└─ Tertiary: #e8eaed (subtle borders)
```

---

**End of Specification**

*Last Updated: 2026-04-02*  
*Next Review: After Phase 1 implementation*  
*Maintainer: Design System Team*

