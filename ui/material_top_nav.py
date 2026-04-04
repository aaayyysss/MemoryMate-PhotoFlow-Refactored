"""
Material Design 3 Top Navigation Bar
Precision Curator - Menu and Search Bar

Implements the top navigation with menu items (File, Edit, View, Tools, Window)
and search functionality with Material Symbols icons.

Author: MemoryMate Design System
Version: 1.0
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QMenu, QMenuBar
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QColor
from ui.styles import COLORS, SPACING, TYPOGRAPHY


class TopMenuBar(QFrame):
    """Material Design 3 Top Menu Bar with search"""
    
    search_clicked = Signal(str)  # Emitted when search is performed
    menu_triggered = Signal(str)  # Emitted when menu item is clicked
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)  # 14px is a common header height in Material Design
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['background']};
                border-bottom: 1px solid {COLORS['outline_variant']};
            }}
        """)
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup top menu bar UI"""
        layout = QHBoxLayout()
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(32)
        
        # Left: Menu items (File, Edit, View, Tools, Window)
        menu_layout = self._create_menu_items()
        layout.addLayout(menu_layout)
        
        # Stretch to separate menu from search
        layout.addStretch()
        
        # Right: Search bar and options
        search_layout = self._create_search_area()
        layout.addLayout(search_layout)
        
        self.setLayout(layout)
    
    def _create_menu_items(self) -> QHBoxLayout:
        """Create menu items layout (File, Edit, View, Tools, Window)"""
        layout = QHBoxLayout()
        layout.setSpacing(24)
        layout.setContentsMargins(0, 0, 0, 0)
        
        menu_items = ['File', 'Edit', 'View', 'Tools', 'Window']
        self.menu_buttons = {}
        
        for item in menu_items:
            btn = QPushButton(item)
            btn.setStyleSheet(self._get_menu_item_stylesheet(item == 'File'))
            btn.setFlat(True)
            btn.setFont(self._get_menu_font())
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.StrongFocus)
            btn.clicked.connect(lambda checked, m=item: self._on_menu_clicked(m))
            
            self.menu_buttons[item] = btn
            layout.addWidget(btn)
        
        return layout
    
    def _create_search_area(self) -> QHBoxLayout:
        """Create search area with icon and input field"""
        layout = QHBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Search container with icon
        search_container = QFrame()
        search_container.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface_container_high']};
                border: 1px solid {COLORS['outline_variant']};
                border-radius: 2px;
            }}
        """)
        search_container.setFixedHeight(40)
        
        container_layout = QHBoxLayout()
        container_layout.setContentsMargins(12, 0, 12, 0)
        container_layout.setSpacing(8)
        
        # Search icon
        search_icon = QLabel("search")
        search_icon.setFont(self._get_icon_font())
        search_icon.setStyleSheet(f"color: {COLORS['on_surface_variant']};")
        search_icon.setFixedSize(20, 24)
        search_icon.setAlignment(Qt.AlignCenter)
        
        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("SEARCH CATALOG...")
        self.search_input.setStyleSheet(self._get_search_input_stylesheet())
        self.search_input.setFont(self._get_search_font())
        self.search_input.setMinimumWidth(400)
        self.search_input.returnPressed.connect(self._on_search)
        
        container_layout.addWidget(search_icon)
        container_layout.addWidget(self.search_input)
        search_container.setLayout(container_layout)
        
        layout.addWidget(search_container)
        
        # Notification button
        notif_btn = QPushButton()
        notif_btn.setText("notifications")
        notif_btn.setFont(self._get_icon_font())
        notif_btn.setFlat(True)
        notif_btn.setStyleSheet(self._get_icon_button_stylesheet())
        notif_btn.setFixedSize(40, 40)
        notif_btn.setCursor(Qt.PointingHandCursor)
        layout.addWidget(notif_btn)
        
        # Account button
        account_btn = QPushButton()
        account_btn.setText("account_circle")
        account_btn.setFont(self._get_icon_font())
        account_btn.setFlat(True)
        account_btn.setStyleSheet(self._get_icon_button_stylesheet())
        account_btn.setFixedSize(40, 40)
        account_btn.setCursor(Qt.PointingHandCursor)
        layout.addWidget(account_btn)
        
        return layout
    
    def _get_menu_item_stylesheet(self, is_active: bool = False) -> str:
        """Get stylesheet for menu items"""
        if is_active:
            return f"""
                QPushButton {{
                    color: {COLORS['on_surface']};
                    background-color: transparent;
                    border: none;
                    border-bottom: 2px solid {COLORS['primary']};
                    padding: 0px 0px 8px 0px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    color: {COLORS['primary']};
                }}
                QPushButton:focus {{
                    outline: 2px solid {COLORS['primary']};
                }}
            """
        else:
            return f"""
                QPushButton {{
                    color: {COLORS['on_surface_variant']};
                    background-color: transparent;
                    border: none;
                    padding: 0px 0px 8px 0px;
                }}
                QPushButton:hover {{
                    color: {COLORS['primary']};
                }}
                QPushButton:focus {{
                    outline: 2px solid {COLORS['primary']};
                    outline-offset: -2px;
                }}
            """
    
    def _get_search_input_stylesheet(self) -> str:
        """Get stylesheet for search input"""
        return f"""
            QLineEdit {{
                background-color: transparent;
                border: none;
                color: {COLORS['on_surface']};
                outline: none;
                font-size: 10pt;
                font-family: 'Inter';
                letter-spacing: 0.1em;
            }}
            QLineEdit::placeholder {{
                color: {COLORS['on_surface_variant']};
            }}
            QLineEdit:focus {{
                background-color: transparent;
                border: none;
            }}
        """
    
    def _get_icon_button_stylesheet(self) -> str:
        """Get stylesheet for icon buttons"""
        return f"""
            QPushButton {{
                color: {COLORS['on_surface_variant']};
                background-color: transparent;
                border: none;
                border-radius: 2px;
                font-size: 20pt;
                font-family: 'Material Symbols Outlined';
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COLORS['primary']};
                background-color: {COLORS['surface_container']};
            }}
            QPushButton:focus {{
                outline: 2px solid {COLORS['primary']};
                outline-offset: -2px;
            }}
        """
    
    def _get_menu_font(self) -> QFont:
        """Get font for menu items"""
        font = QFont("Inter")
        font.setPointSize(8)
        font.setWeight(700)
        return font
    
    def _get_icon_font(self) -> QFont:
        """Get Material Symbols icon font"""
        font = QFont("Material Symbols Outlined")
        font.setPointSize(18)
        return font
    
    def _get_search_font(self) -> QFont:
        """Get font for search input"""
        font = QFont("Inter")
        font.setPointSize(8)
        return font
    
    def _on_menu_clicked(self, menu_name: str):
        """Handle menu item click"""
        self.menu_triggered.emit(menu_name)
        
        # Update underline to show active menu
        for name, btn in self.menu_buttons.items():
            is_active = name == menu_name
            btn.setStyleSheet(self._get_menu_item_stylesheet(is_active))
    
    def _on_search(self):
        """Handle search submission"""
        query = self.search_input.text()
        self.search_clicked.emit(query)
    
    def get_search_query(self) -> str:
        """Get current search query"""
        return self.search_input.text()
    
    def clear_search(self):
        """Clear search input"""
        self.search_input.clear()
