"""
Material Design 3 Gallery Content View
Precision Curator - Main Gallery Layout

Combines the gallery toolbar, photo grid, and date sections into one cohesive view.

Author: MemoryMate Design System
Version: 1.0
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QGridLayout
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QImage, QFont
from typing import List, Dict, Optional
from ui.styles import COLORS
from ui.material_gallery_toolbar import GalleryToolbar, DateHeaderSection
from ui.material_photo_card import PhotoCard


class PhotoGalleryView(QFrame):
    """Material Design 3 Photo Gallery View with date grouping"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['background']};
            }}
        """)
        
        # Dictionary to store sections by date
        self.date_sections: Dict[str, List[PhotoCard]] = {}
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup gallery view UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(0)
        
        # Gallery Toolbar
        self.toolbar = GalleryToolbar()
        layout.addWidget(self.toolbar)
        layout.addSpacing(48)
        
        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {COLORS['background']};
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['outline_variant']};
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {COLORS['outline']};
            }}
        """)
        
        # Content widget
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(56)
        
        self.content_widget.setLayout(self.content_layout)
        scroll.setWidget(self.content_widget)
        
        layout.addWidget(scroll, 1)
        
        self.setLayout(layout)
        
        # Add sample data
        self._add_sample_gallery()
    
    def _add_sample_gallery(self):
        """Add sample photo gallery data"""
        # Sample data structure
        gallery_data = {
            'Today': {
                'count': 12,
                'photos': [
                    {'id': i, 'exif': f'1/{500+i*50}s f/{2.8:.1f} ISO {100}'} 
                    for i in range(6)
                ]
            },
            'Yesterday': {
                'count': 24,
                'photos': [
                    {'id': i+100, 'exif': f'1/{500+i*50}s f/{2.8:.1f} ISO {400}'} 
                    for i in range(6)
                ]
            },
            'October 2026': {
                'count': 156,
                'photos': [
                    {'id': i+200, 'exif': f'ISO {400} • 35mm'} 
                    for i in range(3)
                ]
            }
        }
        
        # Add sections
        for date_label, data in gallery_data.items():
            self.add_photo_section(date_label, data['photos'], data['count'])
    
    def add_photo_section(self, date_label: str, photos: List[Dict], count: int):
        """Add a date section with photos"""
        # Date header
        header = DateHeaderSection(date_label, count)
        self.content_layout.addWidget(header)
        
        # Container for photo grid
        grid_container = QFrame()
        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 16, 0, 0)
        grid_layout.setSpacing(12)
        
        # Create photo cards in grid (6 columns)
        cards = []
        for idx, photo_data in enumerate(photos):
            card = PhotoCard(metadata=photo_data)
            cards.append(card)
            
            row = idx // 6  # 6 columns
            col = idx % 6
            
            grid_layout.addWidget(card, row, col)
        
        # Store cards by date
        self.date_sections[date_label] = cards
        
        # Add stretch to fill empty cells
        grid_layout.setColumnStretch(5, 1)
        
        grid_container.setLayout(grid_layout)
        self.content_layout.addWidget(grid_container)
    
    def get_photo_cards(self, date_label: Optional[str] = None) -> List[PhotoCard]:
        """Get photo cards from section or all cards"""
        if date_label:
            return self.date_sections.get(date_label, [])
        
        # Return all cards
        all_cards = []
        for cards in self.date_sections.values():
            all_cards.extend(cards)
        return all_cards
    
    def get_selected_photos(self) -> List[PhotoCard]:
        """Get all selected photo cards"""
        selected = []
        for cards in self.date_sections.values():
            for card in cards:
                if card.is_selected:
                    selected.append(card)
        return selected
    
    def clear_selection(self):
        """Clear all photo selections"""
        for cards in self.date_sections.values():
            for card in cards:
                if card.is_selected:
                    card.toggle_selection()


class MaterialGalleryMainWindow(QFrame):
    """
    Complete Material Design 3 Main Window
    Combines sidebar, top nav, and gallery view
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['background']};
            }}
        """)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup complete main window"""
        from ui.material_sidebar import MaterialSidebar
        from ui.material_top_nav import TopMenuBar
        
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Left: Sidebar
        self.sidebar = MaterialSidebar()
        main_layout.addWidget(self.sidebar)
        
        # Right: Main content area
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Top: Menu bar
        self.top_nav = TopMenuBar()
        content_layout.addWidget(self.top_nav)
        
        # Center: Gallery view
        self.gallery = PhotoGalleryView()
        content_layout.addWidget(self.gallery, 1)
        
        # Content container
        content_widget = QWidget()
        content_widget.setLayout(content_layout)
        main_layout.addWidget(content_widget, 1)
        
        self.setLayout(main_layout)
    
    def get_sidebar(self):
        """Get sidebar reference"""
        return self.sidebar
    
    def get_gallery(self):
        """Get gallery view reference"""
        return self.gallery
    
    def get_top_nav(self):
        """Get top navigation reference"""
        return self.top_nav
