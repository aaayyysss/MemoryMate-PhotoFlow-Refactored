# Sidebar Accordion Design - Google Photos UX Pattern

## Problem Statement

**Current Implementation:**
- Uses QTabWidget with horizontal tabs at top
- Each section (Branches, Folders, Dates, Tags, People, Quick) has its own scrollable area
- Multiple sections compete for vertical space
- User must switch tabs to see different sections
- Difficult to quickly navigate between sections

**User Request:**
- Make the selected section expand to **full sidebar height**
- Collapse all other sections to headers at bottom
- Remove per-section scrollbars
- Implement **ONE universal scrollbar** for entire sidebar
- Follow Google Photos DNA/UX patterns

---

## Google Photos UX Analysis

### How Google Photos Sidebar Works

1. **Vertical Stack Layout**
   - Sections stacked vertically (not tabs)
   - Clicking a section header expands it
   - Only ONE section expanded at a time

2. **Expanded Section Behavior**
   - Takes full available sidebar height
   - Shows all items with one scrollbar
   - Clear visual emphasis (selected state)

3. **Collapsed Section Behavior**
   - Reduced to just a header button
   - Shows icon + section name
   - Small height (40-50px)
   - Accumulated at bottom of sidebar

4. **Navigation Pattern**
   ```
   ┌─────────────────────┐
   │  [📷 Photos]  ← Expanded (full height)
   │   • All photos      │
   │   • Favorites       │
   │   • Recently added  │
   │   ...               │
   │   (scrollable)      │
   │                     │
   ├─────────────────────┤ ← Collapsed headers below
   │  [📁 Albums]        │
   │  [👥 People]        │
   │  [📍 Places]        │
   │  [🏷️  Things]       │
   └─────────────────────┘
   ```

5. **One Universal Scrollbar**
   - Single scrollbar for entire sidebar
   - Scrolls expanded section content only
   - Collapsed headers stay fixed at bottom

---

## Recommended Design

### Architecture: Accordion Widget

Replace `QTabWidget` with custom accordion widget:

```python
class AccordionSidebar(QWidget):
    """
    Google Photos-style accordion sidebar.
    - One section expanded at a time (full height)
    - Other sections collapsed to headers (bottom)
    - One universal scrollbar
    """

    def __init__(self):
        self.sections = [
            AccordionSection("people", "👥 People"),
            AccordionSection("dates", "📅 By Date"),
            AccordionSection("folders", "📁 Folders"),
            AccordionSection("tags", "🏷️  Tags"),
            AccordionSection("branches", "🌿 Branches"),
            AccordionSection("quick", "⚡ Quick Dates"),
        ]
        self.expanded_section = None  # Track which section is expanded
```

### Section Structure

```python
class AccordionSection(QWidget):
    """
    Individual accordion section.
    Can be expanded (full content) or collapsed (header only).
    """

    def __init__(self, section_id, title):
        self.section_id = section_id
        self.title = title
        self.is_expanded = False

        # Header (always visible)
        self.header = SectionHeader(title)
        self.header.clicked.connect(self.toggle_expand)

        # Content (visible only when expanded)
        self.content_widget = QScrollArea()
        self.content_widget.setVisible(False)
```

### Layout Structure

```
┌─────────────────────────────────┐
│ Sidebar (QVBoxLayout)           │
│                                 │
│ ┌─────────────────────────────┐ │
│ │ Expanded Section            │ │
│ │ (stretch=1, full height)    │ │
│ │                             │ │
│ │ QScrollArea:                │ │ ← ONE scrollbar here
│ │  - All people clusters      │ │
│ │  - All dates                │ │
│ │  - etc.                     │ │
│ │                             │ │
│ └─────────────────────────────┘ │
│                                 │
│ ┌─────────────────────────────┐ │
│ │ Collapsed Headers           │ │ ← No stretch, fixed size
│ │ [📅 By Date]                │ │
│ │ [📁 Folders]                │ │
│ │ [🏷️  Tags]                  │ │
│ │ [🌿 Branches]               │ │
│ └─────────────────────────────┘ │
└─────────────────────────────────┘
```

---

## Implementation Strategy

### Phase 1: Core Accordion Structure

1. **Create AccordionSection widget**
   - Header button (always visible)
   - Content area (QScrollArea)
   - Expand/collapse logic

2. **Create AccordionSidebar widget**
   - Vertical layout
   - Manages section expansion (one at a time)
   - Handles section switching

3. **Replace SidebarTabs with AccordionSidebar**
   - Maintain same signals (selectBranch, selectFolder, etc.)
   - Preserve all existing functionality
   - Drop-in replacement

### Phase 2: Expand/Collapse Logic

```python
def expand_section(self, section_id):
    """Expand one section, collapse all others."""
    for section in self.sections:
        if section.section_id == section_id:
            # Expand this section
            section.set_expanded(True)
            section.content_widget.setVisible(True)
            section.header.set_active(True)

            # Add to layout with stretch (takes all space)
            self.layout.addWidget(section, stretch=1)

            self.expanded_section = section
        else:
            # Collapse other sections
            section.set_expanded(False)
            section.content_widget.setVisible(False)
            section.header.set_active(False)

            # Add to layout without stretch (header only)
            self.layout.addWidget(section, stretch=0)
```

### Phase 3: Universal Scrollbar

**Key Implementation:**
- QScrollArea ONLY for expanded section content
- No scrollbars for collapsed headers
- Sidebar itself does NOT scroll (fixed layout)
- Only content inside expanded section scrolls

```python
# Expanded section
self.content_scroll = QScrollArea()
self.content_scroll.setWidgetResizable(True)
self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
self.content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # ONE scrollbar
self.content_scroll.setWidget(self.content_widget)

# Layout
layout = QVBoxLayout()
layout.addWidget(self.content_scroll, stretch=1)  # Takes all space
layout.addWidget(self.collapsed_headers, stretch=0)  # Fixed size
```

---

## Visual Design

### Expanded Section Header

```
┌────────────────────────────────┐
│ 👥 People                    ▼ │ ← Active state (bold, highlighted)
└────────────────────────────────┘
```

**Styling:**
- Bold text
- Background: Slightly darker or themed color
- Icon: Section icon
- Chevron: Down arrow (▼)
- Height: 48px

### Collapsed Section Header

```
┌────────────────────────────────┐
│ 📅 By Date                    ▶ │ ← Inactive state
└────────────────────────────────┘
```

**Styling:**
- Normal text weight
- Background: Lighter/default
- Icon: Section icon
- Chevron: Right arrow (▶)
- Height: 40px
- Hover effect: Slight highlight

### Content Area (Expanded)

```
┌────────────────────────────────┐
│ 👥 People                    ▼ │
├────────────────────────────────┤
│ 📸 John Doe            (142)   │ ← Scrollable content
│ 📸 Jane Smith          (89)    │
│ 📸 Baby Alex           (312)   │
│ 📸 Unknown Person 1    (12)    │
│ ...                            │
│                                │ ← ONE scrollbar here
│                                │
│                                │
├────────────────────────────────┤
│ 📅 By Date                   ▶ │ ← Collapsed headers
│ 📁 Folders                   ▶ │
│ 🏷️  Tags                     ▶ │
└────────────────────────────────┘
```

---

## Interaction Patterns

### 1. Clicking Collapsed Header
```python
# User clicks "📅 By Date" while "👥 People" is expanded
1. Collapse "👥 People"
   - Hide people content
   - Change header to inactive state
   - Move to collapsed headers area

2. Expand "📅 By Date"
   - Show date content
   - Change header to active state
   - Take full sidebar height
   - Load content if not already loaded
```

### 2. Clicking Expanded Header
```python
# User clicks already-expanded "👥 People" header
# Option A: Do nothing (Google Photos behavior)
# Option B: Collapse to "home" state (show all sections equally)
# Recommendation: Option A (always keep one expanded)
```

### 3. Initial State
```python
# On app launch, expand most relevant section
# Default: "People" (most commonly used)
self.expand_section("people")
```

---

## Benefits of This Design

### ✅ User Experience
1. **Focus**: One section at a time, no distraction
2. **Space**: Full sidebar height for browsing
3. **Speed**: Quick section switching with one click
4. **Clarity**: Clear visual hierarchy (expanded vs collapsed)
5. **Familiarity**: Matches Google Photos DNA

### ✅ Technical Benefits
1. **Performance**: Only render expanded section's content
2. **Memory**: Lazy load collapsed sections
3. **Scrolling**: One scrollbar = simpler scroll management
4. **Responsive**: Adapts to any sidebar height

### ✅ vs Current Tab Design
| Aspect | Current (Tabs) | New (Accordion) |
|--------|----------------|-----------------|
| Space | Shared equally | Full height for active |
| Navigation | Tab click at top | Section click in-place |
| Scrolling | Per-tab scrollbar | One universal scrollbar |
| Visibility | One tab visible | All sections visible (collapsed) |
| Switching | Tab switch (top) | Section click (anywhere) |
| UX Pattern | Desktop software | Modern web/mobile app |

---

## Recommended Section Order

### Primary (Most Used)
1. **👥 People** - Most engaging, face recognition
2. **📅 By Date** - Common browsing pattern
3. **📁 Folders** - Filesystem organization

### Secondary (Less Frequent)
4. **🏷️  Tags** - Manual organization
5. **🌿 Branches** - Technical/advanced
6. **⚡ Quick Dates** - Convenience feature

**Rationale:** Place most-used sections at top for quick access.

---

## Migration Path

### Step 1: Create Accordion Widget (New File)
```bash
accordion_sidebar.py  # New accordion implementation
```

### Step 2: Parallel Implementation
```python
# Keep existing SidebarTabs for now
# Add new AccordionSidebar alongside
# Test thoroughly before switching
```

### Step 3: Switch Layout
```python
# In layouts/google_layout.py or main_window_qt.py
# Replace:
self.sidebar = SidebarTabs(project_id)
# With:
self.sidebar = AccordionSidebar(project_id)
```

### Step 4: Remove Old Code
```python
# Once confirmed working, remove SidebarTabs
# Clean up unused tab-related code
```

---

## Code Structure

```
sidebar_qt.py (current file) - Keep for now
accordion_sidebar.py (new) - New accordion implementation
  ├── AccordionSidebar       # Main widget
  ├── AccordionSection       # Individual section
  ├── SectionHeader          # Clickable header
  └── Section content widgets (reuse existing)
      ├── PeopleTreeWidget
      ├── FoldersTreeWidget
      ├── DatesTreeWidget
      ├── TagsTreeWidget
      ├── BranchesTreeWidget
      └── QuickDatesTreeWidget
```

---

## Recommended Next Steps

1. **Create design mockup** (optional visual)
2. **Implement AccordionSection widget**
3. **Implement AccordionSidebar widget**
4. **Test with one section** (e.g., People)
5. **Add all sections**
6. **Test expand/collapse behavior**
7. **Integrate with main layout**
8. **Polish styling and animations**
9. **Remove old tab widget**

---

## Questions for Consideration

1. **Animation**: Smooth expand/collapse animation or instant?
   - Recommendation: Smooth (200ms) for polish

2. **Remember state**: Remember last expanded section on app restart?
   - Recommendation: Yes, save to user preferences

3. **Keyboard navigation**: Arrow keys to switch sections?
   - Recommendation: Yes, plus Ctrl+1-6 shortcuts

4. **Mobile/touch**: Touch-friendly header size?
   - Recommendation: Yes, 48px minimum height

---

## Estimated Implementation Time

- **Core accordion widget**: 4-6 hours
- **Integration with existing code**: 2-3 hours
- **Testing and bug fixes**: 2-3 hours
- **Styling and polish**: 1-2 hours
- **Total**: ~10-14 hours

---

## Conclusion

The accordion-style sidebar design:
- ✅ Matches Google Photos UX DNA
- ✅ Provides full-height content viewing
- ✅ Simplifies scrolling (one universal scrollbar)
- ✅ Improves focus and clarity
- ✅ Maintains all existing functionality
- ✅ Enables future enhancements (animations, shortcuts)

This is the **recommended approach** for modernizing the sidebar UI.
