# Material Design 3 Stitch Implementation Guide

## Overview

This implementation provides a complete Material Design 3 dark theme UI for MemoryMate PhotoFlow, based on the "Precision Curator" design from Google Stitch.

## New Components Created

### 1. **Color System** (`ui/styles.py` - Updated)
- Switched from light theme to Material Design 3 Dark theme
- Key colors match the Stitch prototype:
  - Primary: `#8fcdff` (bright blue for dark backgrounds)
  - Background: `#0e0e0e` (very dark)
  - Surface containers at various elevation levels
  - WCAG AA accessibility compliance

### 2. **Material Design 3 Sidebar** (`ui/material_sidebar.py`)
For fixed width (320px) navigation:
- **NavItem**: Individual navigation button with icon + label
  - Active state with right border highlight
  - Hover state with background color change
  - Keyboard focus support
  
- **UserProfileCard**: Profile display at bottom
  - User avatar, name, and plan
  - Compact frame with subtle styling
  
- **MaterialSidebar**: Main sidebar container
  - Navigation items: Library, People, Duplicates, Folders, Detail, Search
  - Settings & Support buttons
  - User profile card
  - Scrollable navigation with Material Design icons

**Signals:**
- `nav_clicked(str)` - When nav item clicked
- `settings_clicked()` 
- `support_clicked()`

### 3. **Top Menu Bar** (`ui/material_top_nav.py`)
Replaces traditional menu bar:
- **TopMenuBar**: Header with menu items + search
  - Menu items: File, Edit, View, Tools, Window
  - Underline highlight for active menu
  - Search bar with Material Symbols icon
  - Notification and account buttons
  - WCAG AA keyboard navigation

**Signals:**
- `search_clicked(str)` - When search submitted
- `menu_triggered(str)` - When menu item clicked

### 4. **Photo Card** (`ui/material_photo_card.py`)
Interactive photo grid card:
- Dimension: 200x200px (aspect square)
- **Hover Effects:**
  - Scale animation (1.02x smooth)
  - Show overlay with metadata
  - Show selection checkbox
  
- **Overlay Features:**
  - Top: Favorite and delete buttons
  - Bottom: EXIF metadata and info button
  - 40% dark background
  
- **Selection:**
  - Checkbox in top-left corner
  - Double-click to toggle

**Signals:**
- `clicked()`
- `favorited()`
- `deleted()`
- `info_clicked()`

### 5. **Gallery Toolbar** (`ui/material_gallery_toolbar.py`)
Gallery controls and title:
- **GalleryToolbar:**
  - Title display (e.g., "Photo Library")
  - Photo count
  - View mode toggle (compact/normal/expanded)
  - Import button with gradient
  
- **ViewModeToggle:**
  - 3-button toggle group
  - Icons: grid_view, apps, window
  - Active button highlighted
  
- **DateHeaderSection:**
  - Date label
  - Divider line
  - Photo count
  - Sticky header with backdrop blur effect

### 6. **Gallery View** (`ui/material_gallery_view.py`)
Complete gallery layout:
- **PhotoGalleryView:**
  - Date-grouped sections (Today, Yesterday, October 2026, etc.)
  - Responsive 6-column grid
  - 12px gaps between cards
  - Dark scrollbar with custom styling
  - Sample data loader
  
- **MaterialGalleryMainWindow:**
  - Complete left-right layout
  - Sidebar + TopNav + Gallery combined
  - Provides access to all components

## Integration Instructions

### Step 1: Import the new components

```python
from ui.material_sidebar import MaterialSidebar, NavItem
from ui.material_top_nav import TopMenuBar
from ui.material_photo_card import PhotoCard
from ui.material_gallery_toolbar import GalleryToolbar, DateHeaderSection
from ui.material_gallery_view import PhotoGalleryView, MaterialGalleryMainWindow
```

### Step 2: Replace existing main window

Option A - Use complete Material window:
```python
from ui.material_gallery_view import MaterialGalleryMainWindow

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.gallery_widget = MaterialGalleryMainWindow()
        self.setCentralWidget(self.gallery_widget)
        
        # Connect signals
        self.gallery_widget.sidebar.nav_clicked.connect(self.on_nav_clicked)
        self.gallery_widget.top_nav.search_clicked.connect(self.on_search)
```

Option B - Use individual components:
```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        container = QWidget()
        layout = QHBoxLayout(container)
        
        # Add sidebar
        self.sidebar = MaterialSidebar()
        layout.addWidget(self.sidebar)
        
        # Add content with top nav
        content = QWidget()
        content_layout = QVBoxLayout(content)
        self.top_nav = TopMenuBar()
        self.gallery = PhotoGalleryView()
        content_layout.addWidget(self.top_nav)
        content_layout.addWidget(self.gallery, 1)
        
        layout.addWidget(content, 1)
        self.setCentralWidget(container)
```

### Step 3: Connect signals to your business logic

```python
# Sidebar navigation
self.sidebar.nav_clicked.connect(self.handle_nav_change)

def handle_nav_change(self, item_name: str):
    print(f"Navigated to: {item_name}")
    if item_name == "Library":
        self.show_library()
    elif item_name == "People":
        self.show_people()
    # ... etc

# Search
self.top_nav.search_clicked.connect(self.handle_search)

def handle_search(self, query: str):
    print(f"Search: {query}")
    # Perform search

# Photo actions
for card in self.gallery.get_photo_cards():
    card.clicked.connect(lambda c=card: self.on_photo_clicked(c))
    card.favorited.connect(lambda c=card: self.on_favorite(c))
    card.deleted.connect(lambda c=card: self.on_delete(c))
    card.info_clicked.connect(lambda c=card: self.on_show_info(c))
```

### Step 4: Load real photo data

```python
def load_gallery(self):
    """Load photos from database grouped by date"""
    self.gallery.content_layout.clear()  # Clear sample data
    
    # Group photos by date
    photo_groups = self.group_photos_by_date()
    
    for date_label, photo_list in photo_groups.items():
        # Create metadata for each photo
        photo_data = []
        for photo in photo_list:
            photo_data.append({
                'id': photo.id,
                'path': photo.path,
                'exif': f"1/{photo.shutter_speed}s f/{photo.aperture} ISO {photo.iso}",
            })
        
        # Add section to gallery
        self.gallery.add_photo_section(date_label, photo_data, len(photo_data))

def group_photos_by_date(self):
    """Get photos grouped by date from database"""
    # Query your database
    # Return dict: {date_label: [photo_objects]}
    pass
```

### Step 5: Update photo card with real images

```python
def load_photo_cards(self):
    """Load actual photo pixmaps into cards"""
    for date_label, cards in self.gallery.date_sections.items():
        for card, photo_id in zip(cards, ...):  # Your photo data
            # Load photo thumbnail
            pixmap = QPixmap(photo.thumbnail_path)
            card.set_pixmap(pixmap)
            
            # Update metadata
            card.set_metadata({
                'exif': f"1/{photo.shutter_speed}s f/{photo.aperture} ISO {photo.iso}",
                'id': photo.id,
                'path': photo.path,
            })
```

## Styling & Customization

### Colors
All colors are defined in `ui/styles.py` in the `COLORS` dictionary. To change theme colors:

```python
from ui.styles import COLORS

# Use colors in stylesheets:
COLORS['primary']                     # #8fcdff (bright blue)
COLORS['background']                 # #0e0e0e (very dark)
COLORS['on_surface']                 # #e7e5e5 (light text)
COLORS['surface_container_high']     # #1f2020 (elevated surface)
```

### Fonts
- **Headline**: Manrope (700 weight) - For titles
- **Body**: Inter (400 weight) - For content
- **Icons**: Material Symbols Outlined - For Material Design icons

To use custom fonts:
```python
from PySide6.QtGui import QFont

font = QFont("Your Font Name")
font.setPointSize(12)
font.setWeight(600)
widget.setFont(font)
```

### Size & Spacing
```python
from ui.styles import SPACING, RADIUS

SPACING['sm']       # 8px
SPACING['md']       # 12px
SPACING['lg']       # 16px
SPACING['xl']       # 24px

RADIUS['small']     # 4px
RADIUS['medium']    # 6px
RADIUS['large']     # 8px
```

## Accessibility Features

✅ **WCAG AA Compliance:**
- Minimum 4.5:1 contrast ratio for all text/icons
- Keyboard navigation support
- Focus indicators on all interactive elements
- Semantic Material Design structure
- Proper color usage (not color-only)

✅ **Keyboard Navigation:**
- Tab through all interactive elements
- Enter/Space to activate buttons
- Arrow keys in navigation (optional enhancement)
- Focus visible outlines

## Known Limitations & TODOs

1. **Icon Font**: Uses Material Symbols Outlined via system font fallback
   - For offline/bundled app: Include Material Symbols font file
   - Alternative: Use emoji or custom icon library

2. **Photo Grid Responsiveness**: Currently 6-column layout
   - Can be made responsive with QScreen detection
   - Implementation: Query screen width, adjust columns dynamically

3. **Animation Performance**: Scale animation uses QPropertyAnimation
   - Smooth on desktop, may need optimization on low-end systems
   - Alternative: Use CSS-based transitions if available

4. **Sticky Headers**: DateHeaderSection with backdrop blur
   - Blur effect is CSS only (PySide6 limitation)
   - Workaround: Use semi-transparent background instead

## Testing

Run the demo:
```bash
python -m ui.material_gallery_view
```

Or create a simple test window:
```python
from PySide6.QtWidgets import QApplication
from ui.material_gallery_view import MaterialGalleryMainWindow

app = QApplication([])
window = MaterialGalleryMainWindow()
window.setWindowTitle("Precision Curator - Material Design 3")
window.resize(1600, 900)
window.show()

app.exec()
```

## Common Patterns

### Add new navigation item:
```python
# In material_sidebar.py, add to NAV_ITEMS:
NAV_ITEMS = [
    ('photo_library', 'Library'),
    ('face', 'People'),
    ('new_icon', 'New Item'),  # <-- Add here
]
```

### Change primary color:
```python
# In ui/styles.py:
COLORS['primary'] = '#your_hex_color'
```

### Adjust sidebar width:
```python
# In material_sidebar.py:
self.setFixedWidth(350)  # From 320
```

### Modify grid columns:
```python
# In material_gallery_view.py:
row = idx // 4  # 4 columns instead of 6
col = idx % 4
```

## Integration with Existing Code

### Connecting to existing database:
```python
from reference_db import ReferenceDB

db = ReferenceDB()

# Query photos by date
photos_today = db.query_photos_by_date('today')

# Add to gallery
for photo in photos_today:
    card = PhotoCard(metadata={'exif': photo.exif_data})
    # Configure card...
```

### Using with existing services:
```python
from services.scan_worker_adapter import ScanWorker

# Scan for new photos
worker = ScanWorker()
worker.finished.connect(lambda photos: self.load_gallery())

# Tag service integration
from services.tag_service import get_tag_service
tag_service = get_tag_service()
```

## Support & Issues

For icon font issues:
1. Ensure Material Symbols font is installed: `sudo apt install fonts-material-design-icons`
2. Or download from: https://fonts.google.com/icons
3. Place in: `/workspaces/.../fonts/`

For styling issues:
1. Check `ui/styles.py` for color definitions
2. Verify `setStyleSheet()` syntax
3. Use `qss-lint` to validate stylesheets

---

**Version**: 1.0  
**Author**: MemoryMate Design System  
**Date**: 2026-04-02  
**Stitch Design Source**: https://stitch.withgoogle.com/projects/7143542709216348157
