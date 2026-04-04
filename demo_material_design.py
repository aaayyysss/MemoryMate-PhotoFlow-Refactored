#!/usr/bin/env python3
"""
Material Design 3 Stitch Implementation - Demo
Precision Curator Photo Library

Quick demo of the Material Design 3 components integrated from Google Stitch.
Run this to preview the new UI before full integration.

Usage:
    python demo_material_design.py

Author: MemoryMate Design System
Version: 1.0
"""

import sys
from pathlib import Path

# Add workspace to path
WORKSPACE = Path(__file__).parent
sys.path.insert(0, str(WORKSPACE))

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon

# Import Material Design 3 components
from ui.material_gallery_view import MaterialGalleryMainWindow
from ui.styles import COLORS


class PrecisionCuratorDemo(QMainWindow):
    """Demo window for Material Design 3 Stitch implementation"""
    
    def __init__(self):
        super().__init__()
        self.setup_window()
        self.connect_signals()
        self.demo_operations()
    
    def setup_window(self):
        """Setup main window"""
        self.setWindowTitle("Precision Curator | Photo Library - Material Design 3")
        self.setWindowIcon(QIcon())
        self.resize(1600, 900)
        
        # Center on screen
        screen = self.screen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
        
        # Set dark theme background
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLORS['background']};
            }}
        """)
        
        # Create gallery widget and set as central
        self.gallery_window = MaterialGalleryMainWindow()
        self.setCentralWidget(self.gallery_window)
    
    def connect_signals(self):
        """Connect all component signals to handlers"""
        print("\n" + "="*70)
        print("MATERIAL DESIGN 3 STITCH IMPLEMENTATION - DEMO")
        print("="*70 + "\n")
        
        # Sidebar signals
        sidebar = self.gallery_window.sidebar
        sidebar.nav_clicked.connect(self.on_nav_clicked)
        sidebar.settings_clicked.connect(self.on_settings_clicked)
        sidebar.support_clicked.connect(self.on_support_clicked)
        
        print("✓ Sidebar signals connected")
        print(f"  Navigation items: {', '.join(sidebar.get_navigation_items())}\n")
        
        # Top nav signals
        top_nav = self.gallery_window.top_nav
        top_nav.search_clicked.connect(self.on_search)
        top_nav.menu_triggered.connect(self.on_menu_triggered)
        
        print("✓ Top navigation signals connected")
        print(f"  Menu items: File, Edit, View, Tools, Window\n")
        
        # Gallery signals
        gallery = self.gallery_window.gallery
        
        # Connect photo card signals
        all_cards = gallery.get_photo_cards()
        print(f"✓ Gallery loaded with {len(all_cards)} photo cards")
        print(f"  Sections: {', '.join(gallery.date_sections.keys())}\n")
        
        for card in all_cards:
            card.clicked.connect(lambda c=card: self.on_photo_clicked(c))
            card.favorited.connect(lambda c=card: self.on_photo_favorited(c))
            card.deleted.connect(lambda c=card: self.on_photo_deleted(c))
            card.info_clicked.connect(lambda c=card: self.on_photo_info_clicked(c))
        
        print("✓ Photo card signals connected")
        print(f"  Each card supports: click, favorite, delete, info\n")
        
        # Gallery toolbar signals
        gallery.toolbar.import_clicked.connect(self.on_import_clicked)
        gallery.toolbar.view_mode_changed.connect(self.on_view_mode_changed)
        
        print("✓ Gallery toolbar signals connected")
        print(f"  View modes: compact, normal, expanded\n")
    
    def demo_operations(self):
        """Demonstrate key operations"""
        print("="*70)
        print("DEMO FEATURES TO TRY")
        print("="*70)
        print("""
✓ SIDEBAR NAVIGATION
  - Click on: Library, People, Duplicates, Folders, Detail, Search
  - Each item becomes active with blue highlight
  - Settings and Support at bottom

✓ TOP MENU BAR
  - Menu items: File | Edit | View | Tools | Window
  - Search bar with "SEARCH CATALOG..." placeholder
  - Notification and Account buttons

✓ PHOTO GALLERY
  - Organized by date sections (Today, Yesterday, October 2026)
  - 6-column responsive grid layout
  - Each photo card shows count

✓ PHOTO CARDS
  - HOVER to reveal overlay with metadata
  - Click to select
  - Double-click card to select/deselect
  - Actions: ❤️ Favorite, 🗑️ Delete, ℹ️ Info button

✓ VIEW MODE TOGGLE
  - [grid_view] Compact view (small grid)
  - [apps] Normal view (6 columns) - ACTIVE
  - [window] Expanded view (fewer columns)

✓ IMPORT BUTTON
  - Gradient button with "📁 Import Photos" text
  - Ready to connect to file browser

✓ KEYBOARD NAVIGATION
  - Tab through all interactive elements
  - Enter/Space to activate buttons
  - Focus indicators on all elements

TECHNICAL FEATURES:
  ✓ Material Design 3 dark theme colors
  ✓ WCAG AA accessibility (4.5:1 contrast)
  ✓ Smooth scale animations on photos (1.02x hover)
  ✓ Keyboard navigation support
  ✓ Professional typography (Manrope, Inter)
  ✓ Material Symbols icons
  ✓ Dark backdrop scrollbars
  ✓ Responsive 6-column grid
""")
        print("="*70 + "\n")
        
        # Demo data loaded message
        gallery = self.gallery_window.gallery
        selected_count = len(gallery.get_selected_photos())
        print(f"Demo Status: Gallery ready with sample photos")
        print(f"Selected photos: {selected_count}\n")
    
    # Signal handlers
    def on_nav_clicked(self, item_name: str):
        """Handle sidebar navigation click"""
        print(f"📍 Navigation: {item_name}")
    
    def on_search(self, query: str):
        """Handle search submission"""
        print(f"🔍 Search: '{query}'")
    
    def on_menu_triggered(self, menu_name: str):
        """Handle top menu click"""
        print(f"📋 Menu: {menu_name}")
    
    def on_settings_clicked(self):
        """Handle settings click"""
        print(f"⚙️  Settings clicked")
    
    def on_support_clicked(self):
        """Handle support click"""
        print(f"❓ Support clicked")
    
    def on_photo_clicked(self, card):
        """Handle photo click"""
        print(f"📷 Photo card clicked")
    
    def on_photo_favorited(self, card):
        """Handle photo favorite"""
        print(f"❤️  Photo favorited")
    
    def on_photo_deleted(self, card):
        """Handle photo delete"""
        print(f"🗑️  Photo deleted")
    
    def on_photo_info_clicked(self, card):
        """Handle photo info"""
        print(f"ℹ️  Photo info requested")
    
    def on_import_clicked(self):
        """Handle import button"""
        print(f"📁 Import photos clicked - ready for file picker")
    
    def on_view_mode_changed(self, mode: str):
        """Handle view mode change"""
        print(f"👁️  View mode: {mode}")
    
    def closeEvent(self, event):
        """Handle window close"""
        print("\n" + "="*70)
        print("Demo closed. Thank you for testing Material Design 3!")
        print("="*70 + "\n")
        event.accept()


def main():
    """Run demo application"""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show demo window
    demo = PrecisionCuratorDemo()
    demo.show()
    
    # Exit code
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
