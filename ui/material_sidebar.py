"""
Material Design 3 Sidebar Component
Precision Curator Photo Library Navigation

Implements the Material Design 3 dark theme sidebar from the Stitch prototype.
Features:
- Fixed 320px width sidebar
- Primary navigation (Library, People, Duplicates, etc.)
- Secondary actions (Settings, Support)
- User profile card
- Full keyboard navigation support
- WCAG AA accessibility compliance

Author: MemoryMate Design System
Version: 1.0
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame
)
from PySide6.QtCore import (
    Qt, Signal, QSize, QPropertyAnimation, QEasingCurve, QTimer
)
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor, QPainter
from PySide6.QtSvg import QSvgWidget
from typing import Optional, Dict, List
from ui.styles import COLORS, SPACING, TYPOGRAPHY


class NavItem(QPushButton):
    """Material Design 3 Navigation Item"""
    
    def __init__(self, icon_name: str, label: str, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.label = label
        self.is_active = False
        
        # Setup layout
        layout = QHBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)  # 16px horizontal, 12px vertical
        layout.setSpacing(16)  # Gap between icon and text
        
        # Icon label (using Material Symbols)
        self.icon_label = QLabel()
        self.icon_label.setText(icon_name)
        self.icon_label.setFont(self._get_icon_font())
        self.icon_label.setFixedSize(24, 24)
        self.icon_label.setAlignment(Qt.AlignCenter)
        
        # Text label
        self.text_label = QLabel(label)
        self.text_label.setFont(self._get_text_font())
        
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()
        
        self.setLayout(layout)
        
        # Button styling
        self.setStyleSheet(self._get_stylesheet())
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.clicked.connect(self._on_clicked)
        
    def _get_icon_font(self) -> QFont:
        """Get Material Symbols icon font"""
        font = QFont("Material Symbols Outlined")
        font.setPointSize(20)
        return font
    
    def _get_text_font(self) -> QFont:
        """Get label text font"""
        font = QFont("Manrope")
        font.setPointSize(11)
        font.setWeight(600)
        return font
    
    def _get_stylesheet(self) -> str:
        """Get dynamic stylesheet based on active state"""
        if self.is_active:
            return f"""
                NavItem {{
                    background-color: {COLORS['surface_container_high']};
                    border: none;
                    border-right: 3px solid {COLORS['primary']};
                    color: {COLORS['primary']};
                    padding: 0px;
                    margin: 4px 0px;
                    border-radius: 0px;
                }}
                NavItem:hover {{
                    background-color: {COLORS['surface_container_high']};
                }}
            """
        else:
            return f"""
                NavItem {{
                    background-color: transparent;
                    border: none;
                    color: {COLORS['on_surface_variant']};
                    padding: 0px;
                    margin: 4px 0px;
                    border-radius: 0px;
                }}
                NavItem:hover {{
                    background-color: {COLORS['surface_container']};
                    color: {COLORS['on_surface']};
                }}
                NavItem:focus {{
                    outline: 2px solid {COLORS['primary']};
                    outline-offset: -2px;
                }}
            """
    
    def set_active(self, active: bool):
        """Set active state"""
        self.is_active = active
        self.setStyleSheet(self._get_stylesheet())
        
        # Update icon and text colors
        if active:
            self.icon_label.setStyleSheet(f"color: {COLORS['primary']};")
            self.text_label.setStyleSheet(f"color: {COLORS['primary']}; font-weight: 600;")
        else:
            self.icon_label.setStyleSheet(f"color: {COLORS['on_surface_variant']};")
            self.text_label.setStyleSheet(f"color: {COLORS['on_surface_variant']};")
    
    def _on_clicked(self):
        """Handle click"""
        self.set_active(True)


class UserProfileCard(QFrame):
    """Material Design 3 User Profile Card at bottom of sidebar"""
    
    def __init__(self, user_name: str = "Guest", plan: str = "Free", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface_container']};
                border-radius: 4px;
                border: 1px solid {COLORS['outline_variant']};
            }}
        """)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Profile picture placeholder
        profile_pic = QLabel()
        profile_pic.setFixedSize(32, 32)
        profile_pic.setStyleSheet(f"""
            background-color: {COLORS['primary']};
            border-radius: 4px;
        """)
        profile_pic.setAlignment(Qt.AlignCenter)
        profile_pic.setText("👤")
        profile_pic.setFont(QFont("Arial", 16))
        
        # User info
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        
        name_label = QLabel(user_name)
        name_label.setFont(self._get_name_font())
        name_label.setStyleSheet(f"color: {COLORS['on_surface']};")
        
        plan_label = QLabel(plan)
        plan_label.setFont(self._get_plan_font())
        plan_label.setStyleSheet(f"color: {COLORS['on_surface_variant']};")
        
        info_layout.addWidget(name_label)
        info_layout.addWidget(plan_label)
        
        layout.addWidget(profile_pic)
        layout.addLayout(info_layout)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def _get_name_font(self) -> QFont:
        font = QFont("Inter")
        font.setPointSize(9)
        font.setWeight(600)
        return font
    
    def _get_plan_font(self) -> QFont:
        font = QFont("Inter")
        font.setPointSize(8)
        return font


class MaterialSidebar(QFrame):
    """Material Design 3 Sidebar - Precision Curator Photo Library"""
    
    # Signals
    nav_clicked = Signal(str)  # Emitted when navigation item clicked with item name
    settings_clicked = Signal()
    support_clicked = Signal()
    
    # Navigation items definition
    NAV_ITEMS = [
        ('photo_library', 'Library'),
        ('face', 'People'),
        ('collections_bookmark', 'Duplicates'),
        ('folder_open', 'Folders'),
        ('fullscreen', 'Detail'),
        ('filter_alt', 'Search'),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface_container_low']};
                border-right: 1px solid {COLORS['outline_variant']};
            }}
        """)
        
        self.nav_buttons: Dict[str, NavItem] = {}
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup sidebar UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header_widget = self._create_header()
        layout.addWidget(header_widget)
        
        # Main navigation
        nav_scroll = self._create_navigation()
        layout.addWidget(nav_scroll, 1)
        
        # Footer (Settings, Support, User Profile)
        footer_widget = self._create_footer()
        layout.addWidget(footer_widget)
        
        self.setLayout(layout)
    
    def _create_header(self) -> QFrame:
        """Create sidebar header with app title"""
        header = QFrame()
        header.setFixedHeight(80)
        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(32, 32, 32, 0)
        header_layout.setSpacing(4)
        
        title = QLabel("Precision Curator")
        title.setFont(self._get_header_font())
        title.setStyleSheet(f"color: {COLORS['on_surface']};")
        
        subtitle = QLabel("Professional Mode")
        subtitle.setFont(self._get_subheader_font())
        subtitle.setStyleSheet(f"color: {COLORS['on_surface_variant']};")
        
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        
        header.setLayout(header_layout)
        return header
    
    def _create_navigation(self) -> QScrollArea:
        """Create main navigation area"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {COLORS['surface_container_low']};
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['outline_variant']};
                border-radius: 3px;
            }}
        """)
        
        nav_widget = QFrame()
        nav_layout = QVBoxLayout()
        nav_layout.setContentsMargins(16, 8, 16, 16)
        nav_layout.setSpacing(8)
        
        # Create navigation items
        for icon, label in self.NAV_ITEMS:
            item = NavItem(icon, label)
            item.clicked.connect(lambda checked=False, i=label: self._on_nav_clicked(i))
            self.nav_buttons[label] = item
            nav_layout.addWidget(item)
        
        # Set Library as active by default
        if 'Library' in self.nav_buttons:
            self.nav_buttons['Library'].set_active(True)
        
        nav_layout.addStretch()
        nav_widget.setLayout(nav_layout)
        scroll.setWidget(nav_widget)
        
        return scroll
    
    def _create_footer(self) -> QFrame:
        """Create footer with settings and user profile"""
        footer = QFrame()
        footer.setStyleSheet("background-color: transparent;")
        footer_layout = QVBoxLayout()
        footer_layout.setContentsMargins(16, 0, 16, 16)
        footer_layout.setSpacing(8)
        
        # Settings and Support buttons
        settings_btn = NavItem('settings', 'Settings')
        settings_btn.clicked.connect(self.settings_clicked.emit)
        self.nav_buttons['Settings'] = settings_btn
        
        support_btn = NavItem('help_outline', 'Support')
        support_btn.clicked.connect(self.support_clicked.emit)
        self.nav_buttons['Support'] = support_btn
        
        footer_layout.addWidget(settings_btn)
        footer_layout.addWidget(support_btn)
        
        # Divider
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {COLORS['outline_variant']};")
        footer_layout.addWidget(divider)
        
        # User profile card
        profile_card = UserProfileCard("Alex Mercer", "Pro Plan")
        footer_layout.addWidget(profile_card)
        
        footer.setLayout(footer_layout)
        return footer
    
    def _get_header_font(self) -> QFont:
        """Get header font"""
        font = QFont("Manrope")
        font.setPointSize(14)
        font.setWeight(700)
        return font
    
    def _get_subheader_font(self) -> QFont:
        """Get subheader font"""
        font = QFont("Inter")
        font.setPointSize(7)
        return font
    
    def _on_nav_clicked(self, item_name: str):
        """Handle navigation item click"""
        # Deactivate all nav items except the clicked one
        for name, btn in self.nav_buttons.items():
            if name not in ['Settings', 'Support']:
                btn.set_active(name == item_name)
        
        self.nav_clicked.emit(item_name)
    
    def set_active_nav_item(self, item_name: str):
        """Programmatically set active navigation item"""
        if item_name in self.nav_buttons:
            self._on_nav_clicked(item_name)
    
    def get_navigation_items(self) -> List[str]:
        """Get list of navigation item names"""
        return [label for icon, label in self.NAV_ITEMS]
