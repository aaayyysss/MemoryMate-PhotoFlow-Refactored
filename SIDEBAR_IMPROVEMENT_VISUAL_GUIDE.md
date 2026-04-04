# Sidebar Design Improvement - Visual Guide & Code Examples
## Implementation Guide | 2026-04-02

---

## Visual Comparison: Current vs Proposed

### 1. Navigation Bar Redesign

```
CURRENT (52px, icon-only):
┌─────────────┐
│   👥      │ ← Unclear what section is
│   📅      │   Hard to see state
│   📁      │   No labels
│   🎬      │   Subtle hover
│   ⭐      │   Only tooltip feedback
│   🏷️      │
│   🔀      │
│   ⚡      │
│   ℹ️      │
└─────────────┘
Problem: Users don't know current section without hovering


PROPOSED (64px, icon + hover label):
┌──────────────────────────┐
│ 👥 People          │ ← Blue left border = active
│ 📅 Dates           │   Shows on hover: "People (23)"
│ 📁 Folders         │   Red dot on "Activity" = alerts
│ 🎬 Videos          │   Smooth transitions (200ms)
│ ⭐ Duplicates      │   Better touch target (48x48px)
│ 🏷️  Tags            │   Clear hierarchy
│ 🔀 Branches        │   Professional appearance
│ ⚡ Quick           │
│                    │
│ ℹ️  Activity  🔴   │ ← Badge for alerts
└──────────────────────────┘
Benefit: Clear section labels, better discoverability, badge support
```

**Key Changes:**
- Width: 52px → 64px flexible
- Add: Hover label tooltip (not just browser tooltip)
- Add: Blue 3px left border on active section
- Add: Badge support (red dot for alerts)
- Animation: 200ms smooth transition on hover/click

---

### 2. Section Header Redesign

```
CURRENT:
┌────────────────────────────────────────┐  Light background
│ 👥 People (23)                    ▶   │  Subtle border
└────────────────────────────────────────┘  Can't see state
Problem: Inactive and active look too similar


PROPOSED - ACTIVE:
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  
┃ 👥 People (23)                    ▼   ┃  Solid background #e8f0fe
┃                                      ┃  Left border: 3px #1a73e8
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  Bold title font
  └─ 3px blue left border = ACTIVE      Chevron down = open


PROPOSED - INACTIVE:
┌────────────────────────────────────────┐
│ 📅 Dates (156)                    ▶   │  Background #f8f9fa
│                                      │  Left border: 1px #dadce0
└────────────────────────────────────────┘  Normal font weight
  └─ 1px gray left border = INACTIVE     Chevron right = closed


HOVER STATE:
┌────────────────────────────────────────┐
│ 📅 Dates (156)                    ▶   │  Background slightly darker
│                                      │  Hints link affordance
└────────────────────────────────────────┘  Mouse pointer = hand


TRANSITION ANIMATION:
Active ────(200ms)──→ Inactive
- Background color fades
- Left border color fades  
- Chevron rotates 180°
- Title weight changes (bold ↔ normal)
```

**Code Example:**

```python
# BEFORE (Basic, instant change):
if active:
    self.setStyleSheet("background-color: #e8f0fe;")
else:
    self.setStyleSheet("background-color: #f8f9fa;")

# AFTER (Animated, better visual feedback):
class AnimatedSectionHeader(SectionHeader):
    def set_active(self, active: bool):
        self.is_active = active
        
        # Create animation
        anim = QPropertyAnimation(self, b"background_color")
        anim.setDuration(200)  # 200ms smooth transition
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        
        if active:
            anim.setEndValue(QColor("#e8f0fe"))
            self.title_font.setBold(True)
            # Rotate chevron 180°
            self._animate_chevron_rotation(0, 180)
        else:
            anim.setEndValue(QColor("#f8f9fa"))
            self.title_font.setBold(False)
            # Rotate chevron back
            self._animate_chevron_rotation(180, 0)
        
        anim.start()
        self._active_anim = anim  # Keep reference

    def _animate_chevron_rotation(self, start, end):
        """Animate chevron rotation."""
        anim = QPropertyAnimation(self.chevron_label, b"rotation")
        anim.setDuration(200)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.start()
```

---

### 3. Color System Visual

```
CURRENT PROBLEM:
Active Section BG:     #e8f0fe (too light, hard to see)
Inactive Section BG:   #f8f9fa (indistinguishable)
Hover State:           rgba(26, 115, 232, 0.10) (too subtle)
Result: All sections look the same!


PROPOSED IMPROVED:
┌─────────────────────────────────────────────────────────┐
│ EXPANDED SECTION (Active)                              │
│ ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓ │
│ ┃ 👥 People (23)                               ▼    ┃ │
│ ┃ ┃                                                   ┃ │
│ ┃ ┃ Background: #e8f0fe (solid, visible)           ┃ │
│ ┃ ┃ Left border: 3px #1a73e8 (blue accent)         ┃ │
│ ┃ ┃ Title: Bold, #202124                           ┃ │
│ ┃ ┃                                                   ┃ │
│ ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛ │
│                                                        │
│ COLLAPSED SECTIONS (Below active)                     │
│ ┌──────────────────────────────────────────────────┐ │
│ │ 📅 Dates (156)                              ▶   │ │
│ └──────────────────────────────────────────────────┘ │
│ Background: #f8f9fa (neutral)                       │
│ Left border: 1px #dadce0 (gray)                     │
│ Title: Normal weight, #202124                       │
│                                                        │
│ ┌──────────────────────────────────────────────────┐ │
│ │ 📁 Folders (12)                             ▶   │ │
│ └──────────────────────────────────────────────────┘ │
│                                                        │
│ ┌──────────────────────────────────────────────────┐ │
│ │ 🎬 Videos (8)                               ▶   │ │
│ └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

Clear Distinction 3x:
1. Background color (solid blue vs neutral gray)
2. Left border (3px blue vs 1px gray)
3. Font weight (bold vs normal)
```

---

### 4. People Grid - Layout Improvements

```
CURRENT (Too small):
┌─────────────────────────┐
│ [👤]  [👤]             │ ← 80x100px cards
│ John  Sarah             │   2 per row
│ (24)  (18)              │   Only 6 visible
│                          │
│ [👤]  [👤]             │
│ Mike  Jane              │
│ (5)⚠ (42)              │
│                          │
│ [👤]  [👤]             │
│ Alex  Bob               │
│ (11)  (7)               │
│                          │
│ [    +4 more   ]       │ ← Need scrolling
│     people...          │
└─────────────────────────┘

Issues:
- Too many cards in view (confusing)
- Cards too small (can't see faces clearly)
- Scrolling required to see all
- Awkward 2-column layout


PROPOSED (Better proportions):
┌─────────────────────────────────────┐
│ [👤]  [👤]  [👤]                   │ ← 100x120px cards
│ John  Sarah Michael                 │   3 per row
│ 24🔵  18🔵  5⚠️                     │   Larger faces
│                                     │
│ [👤]  [👤]  [👤]                   │   Better density
│ Jane  Alex  Bob                     │   Scroll smoothly
│ 42🔵  11🔵  7🔵                     │
│                                     │
│ [👤]  [👤]  [        ]             │   "+2 more" indicator
│ Carol David +2 more                │
│ 8🟡   3🔴    people               │
│                                     │
│ [Load more people ▼]              │
└─────────────────────────────────────┘

Benefits:
- 3 columns better use of width
- Cards visible = faces recognizable
- Confidence icons clearer (🔵🟡🔴)
- Lazy loading to "Load more"
- Scrollable without crowding
```

**Code Example:**

```python
# BEFORE (Fixed 340px minimum, tight constraints):
class PeopleGridView(QWidget):
    def __init__(self, parent=None):
        self.grid_container = QWidget()
        self.flow_layout = FlowLayout(self.grid_container, margin=4, spacing=8)
        self.grid_container.setMinimumHeight(340)  # HARD-CODED


# AFTER (Flexible, responsive):
class PeopleGridView(QWidget):
    def __init__(self, parent=None):
        self.grid_container = QWidget()
        
        # Use grid layout instead of flow layout
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(12)  # Better spacing
        self.grid_layout.setContentsMargins(8, 8, 8, 8)
        
        # Make responsive (2-3 columns based on width)
        self.cards_per_row = 3
        self.card_width = 100
        self.card_height = 120
        
        # Minimum height = 1.5 rows (allows showing 4-5 cards)
        self.grid_container.setMinimumHeight(int(self.card_height * 1.5))
        
        # Maximum height = 3 rows (before scrolling)
        self.grid_container.setMaximumHeight(int(self.card_height * 3 + 24))
        
        self.people_cards = []
        self.load_more_button = None
    
    def add_person(self, branch_key, display_name, face_pixmap, photo_count):
        """Add person card with responsive sizing."""
        card = PersonCard(branch_key, display_name, face_pixmap, photo_count)
        card.setFixedSize(self.card_width, self.card_height)  # Larger cards
        
        row = len(self.people_cards) // self.cards_per_row
        col = len(self.people_cards) % self.cards_per_row
        
        self.grid_layout.addWidget(card, row, col)
        self.people_cards.append(card)
        
        # Add "Load more" button after showing first 6
        if len(self.people_cards) == 6:
            self._add_load_more_button()
    
    def _add_load_more_button(self):
        """Add expandable 'Load more' button."""
        row = 6 // self.cards_per_row
        col = 0
        
        btn = QPushButton("Load more people ↓")
        btn.clicked.connect(self._expand_to_show_all)
        self.load_more_button = btn
        
        self.grid_layout.addWidget(btn, row, col, 1, self.cards_per_row)
```

---

### 5. Loading State Visualization

```
CURRENT (No feedback):
┌─────────────────────────────────────┐
│ 👥 People                         │
├─────────────────────────────────────┤
│                                     │ ← Empty, but no indicator
│                                     │   User thinks: "Loading? Broken?"
│                                     │   Frustration increases...
└─────────────────────────────────────┘


PROPOSED (Clear feedback):
┌─────────────────────────────────────┐
│ 👥 People                      🔄  │ ← Refresh icon (hover = "Reload")
├─────────────────────────────────────┤
│                                     │
│           ⟳ Loading faces...       │ ← Spinner animation
│                                     │   User understands progress
│          (50% complete)             │ ← Optional: progress ≥3 secs
│                                     │
└─────────────────────────────────────┘

AFTER LOAD:
┌─────────────────────────────────────┐
│ 👥 People (12)                  🔄  │ ← Count badge
├─────────────────────────────────────┤
│ [👤]  [👤]  [👤]                   │
│ John  Sarah Michael                 │
│ 24🔵  18🔵  5⚠️                     │
│                                     │
└─────────────────────────────────────┘

Smooth fade-in transition (300ms) on content load
```

**Code Example:**

```python
def _build_people_grid(self, rows: list):
    """Build people grid with loading feedback."""
    section = self.sections.get("people")
    if not section:
        return
    
    # Show loading indicator
    self._show_section_loading(section, "Loading faces...")
    
    try:
        # Create grid
        grid = PeopleGridView()
        
        # Populate with fade-in animation
        for idx, row in enumerate(rows):
            # ... extract data ...
            
            card = PersonCard(...)
            
            # Fade in each card sequentially
            anim = QPropertyAnimation(card, b"windowOpacity")
            anim.setDuration(150)
            anim.setStartValue(0)
            anim.setEndValue(1)
            anim.setDelay(idx * 50)  # Stagger cards
            anim.start()
            
            grid.add_person(...)
        
        # Set total count in header
        section.set_count(len(rows))
        
        # Transition to content
        section.set_content_widget(grid)
        
    except Exception as e:
        # Show error
        self._show_section_error(section, str(e))

def _show_section_loading(self, section, message):
    """Show loading spinner in section."""
    loading_widget = QWidget()
    layout = QVBoxLayout(loading_widget)
    layout.setAlignment(Qt.AlignCenter)
    
    spinner = QLabel("⟳")  # Unicode spinner
    spinner.setStyleSheet("font-size: 24pt;")
    spinner.setAlignment(Qt.AlignCenter)
    
    # Create rotation animation
    anim = QPropertyAnimation(spinner, b"rotation")
    anim.setDuration(1000)
    anim.setStartValue(0)
    anim.setEndValue(360)
    anim.setLoopCount(-1)  # Infinite loop
    anim.start()
    
    msg = QLabel(message)
    msg.setAlignment(Qt.AlignCenter)
    msg.setStyleSheet("color: #5f6368; font-size: 11pt;")
    
    layout.addStretch()
    layout.addWidget(spinner)
    layout.addWidget(msg)
    layout.addStretch()
    
    section.set_content_widget(loading_widget)
    self._section_loading_anim[section.section_id] = anim
```

---

### 6. Typography Scale Visual

```
CURRENT (Inconsistent):
Section Header:  "People"          ← 14pt? 12pt? unclear
Tab Label:       "Individuals"     ← 10pt, too small
List Item:       "John (24 photos)"← 13pt
Count Badge:     "(23)"            ← 11px
Hint Text:       "No people yet"   ← 9pt, almost unreadable
Navigation Icon: 👥               ← 20pt
Section Icon:    👥               ← 14pt
Result: Chaotic sizing, hard to scan


PROPOSED (Clear scale):
┌────────────────────────────────────┐
│ 👥 People (23)          [icon 18pt] │ ← Title: 14pt, weight 600
├────────────────────────────────────┤
│ [Individuals] [Groups]              │ ← Tabs: 13pt, weight 500
│                                    │
│  👤 John           24 photos 🔵   │ ← Item: 13pt, weight 400
│  👤 Sarah          18 photos 🔵   │   Count: 11pt, weight 400
│  👤 Michael        5 photos ⚠️    │   Icon: 16pt
│                                    │
│  Show 4 more people ↓              │ ← CTA: 12pt, weight 500
│                                    │   Color: #1a73e8 (blue)
│ Last updated 2 hours ago           │ ← Hint: 10pt, weight 400
│                                    │   Color: #5f6368 (gray)
└────────────────────────────────────┘

Clear visual hierarchy:
- Title largest (14pt, bold)
- Tabs clear (13pt, medium weight)
- Items readable (13pt)
- Hints small but not unreadable (10-11pt)
- Icon sizes normalized (16-18pt for list icons)
```

**CSS/Stylesheet Definition:**

```python
# Define a typography system as constants
TYPOGRAPHY = {
    'header': {
        'size': 14,      # px
        'weight': 600,   # 600 = semi-bold
        'line_height': 20,
        'color': '#202124'
    },
    'tab': {
        'size': 13,
        'weight': 500,
        'line_height': 20,
        'color': '#202124'
    },
    'body': {
        'size': 13,
        'weight': 400,
        'line_height': 20,
        'color': '#202124'
    },
    'small': {
        'size': 11,
        'weight': 400,
        'line_height': 16,
        'color': '#5f6368'
    },
    'caption': {
        'size': 10,
        'weight': 400,
        'line_height': 14,
        'color': '#5f6368'
    }
}

# Use in code:
def apply_typography(widget, role):
    """Apply typography to widget."""
    style = TYPOGRAPHY.get(role, TYPOGRAPHY['body'])
    font = widget.font()
    font.setPointSize(style['size'])
    font.setWeight(style['weight'])
    widget.setFont(font)
    widget.setStyleSheet(f"color: {style['color']};")
```

---

### 7. Spacing & Layout Grid

```
CURRENT (Ad-hoc spacing):
Nav bar margin: 6px
Section margin: 3px
Header padding: 10px 6px (inconsistent)
Content padding: 8px
Result: Misaligned, random-looking


PROPOSED (8px grid):
┌─────────────────────────────────────┐
│     [6px margin on all sides]       │
│  ┌─────────────────────────────────┐│
│  │ 👥 People               [icon] ││  Header 48px height
│  │ [padding: 12px 8px]             ││  = 12px content padding
│  │                                 ││    + 12px content padding
│  │ [3px margin bottom]             ││    + 12px content padding
│  └─────────────────────────────────┘│  (total: 48px)
│                                     │
│  ┌─────────────────────────────────┐│
│  │ 📅 Dates                   ▶  ││  Header 48px
│  │                                 ││
│  └─────────────────────────────────┘│
│  [3px margin bottom]                │
│                                     │
│  ┌─────────────────────────────────┐│
│  │ 📁 Folders                 ▶  ││  Header 48px
│  │                                 ││
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘

All values multiples of 8px:
- Container: 8px gutters (1x 8px)
- Section headers: 12px padding (1.5x 8px)
- Section spacing: 3px? NO → Use 8px (1x 8px)
- List items: 12px 8px (1.5x 8px, 1x 8px)
- Cards: 8px spacing (1x 8px)
- Icon sizes: 16px, 24px (2x, 3x 8px)

Benefit: Professional, aligned look
All components snap to grid
```

---

### 8. Interactive State Visualization

```
BUTTON STATES (Proposed):

Default:
┌──────────────┐
│ Save Changes │  Background: white
│              │  Border: 1px #dadce0
└──────────────┘  Color: #202124
                  Cursor: default


Hover:
┌──────────────┐
│ Save Changes │  Background: #f1f3f4
│              │  Border: 1px #bdc1c6
└──────────────┘  Color: #202124
                  Cursor: pointer
                  Shadow: subtle (0 1px 2px rgba(0,0,0,0.04))


Active/Pressed:
┏━━━━━━━━━━━━━━━┓
┃ Save Changes ┃  Background: #e8eaed
┃              ┃  Border: 1px solid
┗━━━━━━━━━━━━━━┛  Color: #202124
                  Slight inset effect


Disabled:
┌──────────────┐
│Save Changes │  Background: #f1f3f4
│              │  Border: 1px #dadce0
└──────────────┘  Color: #9aa0a6 (grayed out)
                  Cursor: not-allowed
                  Opacity: 0.6


Loading:
┌──────────────┐
│   ⟳ Please  │  Rotating spinner
│   wait...    │  Text changes dynamically
└──────────────┘  Button disabled during action
```

---

## Specific Code Improvements

### Issue: Inconsistent Section Header Styling

**CURRENT CODE (accordion_sidebar.py):**

```python
def set_active(self, active: bool):
    self.is_active = active
    if active:
        self.title_font.setBold(True)
        self.title_label.setFont(self.title_font)
        self.chevron_label.setText("▼")
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
```

**PROBLEMS:**
1. ❌ Only background color changes (not distinctive enough)
2. ❌ No animation (instant, jarring)
3. ❌ Hover color (#d2e3fc) doesn't match design system
4. ❌ `border: none` removes ability for left accent

**IMPROVED CODE:**

```python
def set_active(self, active: bool):
    """Set header to active or inactive state with smooth animation."""
    self.is_active = active
    
    # Animate background color
    self._animate_background_color(
        "#e8f0fe" if active else "#f8f9fa",
        duration=200
    )
    
    # Update title weight
    self.title_font.setBold(active)
    self.title_label.setFont(self.title_font)
    
    # Rotate chevron
    self._animate_chevron_rotation(
        180 if active else 0,
        duration=200
    )
    
    # Apply consistent stylesheet
    stylesheet = self._get_header_stylesheet(active)
    self.setStyleSheet(stylesheet)

def _get_header_stylesheet(self, active: bool) -> str:
    """Get stylesheet based on state."""
    if active:
        return """
            SectionHeader {
                background-color: #e8f0fe;
                border: none;
                border-left: 3px solid #1a73e8;  /* Add blue accent */
                border-radius: 6px;
                padding-left: 8px;
            }
            SectionHeader:hover {
                background-color: #d2e3fc;  /* Darker on hover */
            }
        """
    else:
        return """
            SectionHeader {
                background-color: #f8f9fa;
                border: 1px solid #dadce0;
                border-left: none;  /* No accent when inactive */
                border-radius: 6px;
            }
            SectionHeader:hover {
                background-color: #f1f3f4;
            }
        """

def _animate_background_color(self, target_color: str, duration: int = 200):
    """Smoothly animate background color change."""
    # Create animation
    anim = QPropertyAnimation(self, b"background_color")
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.InOutQuad)
    anim.setEndValue(QColor(target_color))
    anim.start()
    self._bg_anim = anim  # Keep reference

def _animate_chevron_rotation(self, target_angle: int, duration: int = 200):
    """Smoothly rotate chevron icon."""
    # Create transform animation
    start_angle = 0 if target_angle == 180 else 180
    
    anim = QPropertyAnimation(self.chevron_label, b"rotation")
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.InOutQuad)
    anim.setStartValue(start_angle)
    anim.setEndValue(target_angle)
    
    # Update text on completion
    def on_complete():
        self.chevron_label.setText("▼" if target_angle == 180 else "▶")
    
    anim.finished.connect(on_complete)
    anim.start()
    self._chevron_anim = anim
```

---

### Issue: Hard-Coded People Grid Size

**CURRENT CODE:**

```python
class PeopleGridView(QWidget):
    def __init__(self, parent=None):
        self.grid_container = QWidget()
        self.flow_layout = FlowLayout(self.grid_container, margin=4, spacing=8)
        self.grid_container.setMinimumHeight(340)  # ❌ Hard-coded
```

**IMPROVED CODE:**

```python
class PeopleGridView(QWidget):
    # Typography/Layout constants
    CARD_WIDTH = 100
    CARD_HEIGHT = 120
    CARDS_PER_ROW = 3
    SPACING = 12
    MIN_ROWS_VISIBLE = 2  # Show at least 2 rows
    MAX_ROWS_VISIBLE = 3  # Max 3 rows before scroll
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Use responsive layout
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(self.SPACING)
        self.grid_layout.setContentsMargins(8, 8, 8, 8)
        
        # Calculate minimum height (shows 2 rows of cards)
        min_height = (
            self.CARD_HEIGHT * self.MIN_ROWS_VISIBLE +
            self.SPACING * (self.MIN_ROWS_VISIBLE - 1) +
            16  # margins
        )
        self.setMinimumHeight(min_height)
        
        # Calculate maximum height (shows 3 rows before scroll)
        max_height = (
            self.CARD_HEIGHT * self.MAX_ROWS_VISIBLE +
            self.SPACING * (self.MAX_ROWS_VISIBLE - 1) +
            16  # margins
        )
        self.setMaximumHeight(max_height)
        
        # Enable scrolling
        self.scroll_area = QScrollArea()
        self.scroll_content = QWidget()
        self.scroll_layout = QGridLayout(self.scroll_content)
        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_area.setWidgetResizable(True)
        
        self.people_cards = []
    
    def add_person(self, branch_key, display_name, face_pixmap, photo_count):
        """Add person card to grid."""
        card = PersonCard(
            branch_key,
            display_name,
            face_pixmap,
            photo_count
        )
        # Use responsive card size
        card.setFixedSize(self.CARD_WIDTH, self.CARD_HEIGHT)
        
        # Add to grid with calculated position
        row = len(self.people_cards) // self.CARDS_PER_ROW
        col = len(self.people_cards) % self.CARDS_PER_ROW
        
        self.scroll_layout.addWidget(card, row, col)
        self.people_cards.append(card)
        
        # After showing limit, add load-more button
        if len(self.people_cards) == (self.CARDS_PER_ROW * self.MAX_ROWS_VISIBLE):
            self._add_load_more_button()
    
    def _add_load_more_button(self):
        """Add expandable load-more button."""
        btn = QPushButton("Load more people ↓")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._expand)
        
        row = len(self.people_cards) // self.CARDS_PER_ROW
        self.scroll_layout.addWidget(btn, row, 0, 1, self.CARDS_PER_ROW)
```

---

### Issue: Missing Loading State

**CURRENT CODE:**

```python
def _build_people_grid(self, rows: list):
    # No indication of loading
    # Just appears/disappears
    section = self.sections.get("people")
    # ... populate grid ...
    section.set_content_widget(outer)
```

**IMPROVED CODE:**

```python
def _load_people_section(self):
    """Load People section with loading feedback."""
    section = self.sections.get("people")
    if not section:
        return
    
    # SHOW LOADING STATE IMMEDIATELY
    self._show_loading_placeholder(section)
    
    # Load in background
    def work():
        try:
            db = ReferenceDB()
            rows = db.get_face_clusters(self.project_id)
            return rows
        except Exception as e:
            return None
        finally:
            if db:
                db.close()
    
    def on_complete():
        rows = work()
        if rows is not None:
            self._build_people_grid(rows)
        else:
            self._show_error_placeholder(section, "Failed to load people")
    
    threading.Thread(target=on_complete, daemon=True).start()

def _show_loading_placeholder(self, section):
    """Show loading spinner while fetching data."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setAlignment(Qt.AlignCenter)
    layout.setSpacing(12)
    
    # Spinner
    spinner = QLabel("⟳")
    spinner.setStyleSheet("font-size: 32pt; color: #1a73e8;")
    spinner.setAlignment(Qt.AlignCenter)
    
    # Animate spinner
    timer = QTimer()
    rotation = [0]
    
    def update_spinner():
        rotation[0] = (rotation[0] + 45) % 360
        transform = QTransform().rotate(rotation[0])
        # Update visual (simplified - full implementation uses QPropertyAnimation)
    
    timer.timeout.connect(update_spinner)
    timer.start(50)
    self._spinner_timer = timer
    
    # Message
    msg = QLabel("Loading faces...\nThis may take a moment")
    msg.setAlignment(Qt.AlignCenter)
    msg.setStyleSheet("color: #5f6368; font-size: 11pt;")
    
    layout.addStretch()
    layout.addWidget(spinner)
    layout.addWidget(msg)
    layout.addStretch()
    
    section.set_content_widget(container)

def _show_error_placeholder(self, section, error_msg):
    """Show error message."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setAlignment(Qt.AlignCenter)
    
    icon = QLabel("⚠️")
    icon.setStyleSheet("font-size: 24pt;")
    icon.setAlignment(Qt.AlignCenter)
    
    msg = QLabel(f"Error: {error_msg}\nPlease try again")
    msg.setAlignment(Qt.AlignCenter)
    msg.setStyleSheet("color: #ea4335; font-size: 11pt;")
    
    btn_retry = QPushButton("🔄 Retry")
    btn_retry.clicked.connect(lambda: self._load_people_section())
    
    layout.addStretch()
    layout.addWidget(icon)
    layout.addWidget(msg)
    layout.addWidget(btn_retry)
    layout.addStretch()
    
    section.set_content_widget(container)
```

---

## Implementation Checklist

**Phase 1: Visual Polish (3-4 days)**
- [ ] Update color palette throughout codebase
- [ ] Implement consistent typography scale
- [ ] Fix spacing (convert to 8px grid)
- [ ] Improve section header styling
- [ ] Add animations for state changes

**Phase 2: Navigation Improvements (2-3 days)**
- [ ] Redesign nav bar (width, labels, badges)
- [ ] Add animation on section switching
- [ ] Improve button hover states
- [ ] Add keyboard navigation support

**Phase 3: Content UX (2-3 days)**
- [ ] Redesign people grid (responsive layout)
- [ ] Add loading states with spinners
- [ ] Implement lazy loading
- [ ] Add error handling UI

**Phase 4: Polish & Testing (1-2 days)**
- [ ] Cross-browser testing
- [ ] Accessibility audit
- [ ] Performance testing
- [ ] User feedback

---

**Total Estimated Effort:** 2-3 weeks

**Recommended Start:** Phase 1 (colors + spacing) for immediate ROI

