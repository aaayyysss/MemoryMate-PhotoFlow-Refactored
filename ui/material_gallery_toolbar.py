"""
Material Design 3 Gallery Toolbar
Precision Curator - Gallery Controls

Implements the gallery controls: title, photo count, and view mode toggles.

Author: MemoryMate Design System
Version: 1.0
"""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QButtonGroup
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from ui.styles import COLORS


class ViewModeToggle(QFrame):
    """Material Design 3 View Mode Toggle Buttons"""
    
    view_mode_changed = Signal(str)  # 'compact', 'normal', 'expanded'
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
            }}
        """)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Create button group for toggle
        self.button_group = QButtonGroup()
        
        # Compact view (grid)
        btn_compact = QPushButton()
        btn_compact.setText("grid_view")
        btn_compact.setFont(self._get_icon_font())
        btn_compact.setFixedSize(40, 40)
        btn_compact.setFlat(True)
        btn_compact.setStyleSheet(self._get_button_stylesheet(False))
        btn_compact.clicked.connect(lambda: self._on_view_mode_changed('compact'))
        self.button_group.addButton(btn_compact, 0)
        layout.addWidget(btn_compact)
        self.btn_compact = btn_compact
        
        # Normal view (apps)
        btn_normal = QPushButton()
        btn_normal.setText("apps")
        btn_normal.setFont(self._get_icon_font())
        btn_normal.setFixedSize(40, 40)
        btn_normal.setFlat(True)
        btn_normal.setStyleSheet(self._get_button_stylesheet(True))  # Default active
        btn_normal.clicked.connect(lambda: self._on_view_mode_changed('normal'))
        self.button_group.addButton(btn_normal, 1)
        layout.addWidget(btn_normal)
        self.btn_normal = btn_normal
        self.active_button = btn_normal
        
        # Expanded view (window)
        btn_expanded = QPushButton()
        btn_expanded.setText("window")
        btn_expanded.setFont(self._get_icon_font())
        btn_expanded.setFixedSize(40, 40)
        btn_expanded.setFlat(True)
        btn_expanded.setStyleSheet(self._get_button_stylesheet(False))
        btn_expanded.clicked.connect(lambda: self._on_view_mode_changed('expanded'))
        self.button_group.addButton(btn_expanded, 2)
        layout.addWidget(btn_expanded)
        self.btn_expanded = btn_expanded
        
        self.setLayout(layout)
    
    def _get_icon_font(self) -> QFont:
        """Get Material Symbols icon font"""
        font = QFont("Material Symbols Outlined")
        font.setPointSize(18)
        return font
    
    def _get_button_stylesheet(self, is_active: bool) -> str:
        """Get stylesheet for toggle button"""
        if is_active:
            return f"""
                QPushButton {{
                    background-color: {COLORS['surface_container_highest']};
                    border: none;
                    border-radius: 2px;
                    color: {COLORS['primary']};
                    padding: 0px;
                    margin: 4px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['surface_container_high']};
                }}
            """
        else:
            return f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    color: {COLORS['on_surface_variant']};
                    padding: 0px;
                    margin: 4px;
                }}
                QPushButton:hover {{
                    color: {COLORS['on_surface']};
                }}
            """
    
    def _on_view_mode_changed(self, mode: str):
        """Handle view mode change"""
        # Update button states
        buttons = {
            'compact': self.btn_compact,
            'normal': self.btn_normal,
            'expanded': self.btn_expanded,
        }
        
        for view_mode, btn in buttons.items():
            is_active = view_mode == mode
            btn.setStyleSheet(self._get_button_stylesheet(is_active))
            if is_active:
                self.active_button = btn
        
        self.view_mode_changed.emit(mode)


class GalleryToolbar(QFrame):
    """Material Design 3 Gallery Toolbar"""
    
    import_clicked = Signal()
    view_mode_changed = Signal(str)
    
    def __init__(self, title: str = "Photo Library", count: int = 1248, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
            }}
        """)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(48)
        
        # Left: Title and description
        title_layout = self._create_title_section(title, count)
        layout.addLayout(title_layout)
        
        # Right: Controls
        control_layout = self._create_controls()
        layout.addLayout(control_layout)
        
        self.setLayout(layout)
    
    def _create_title_section(self, title: str, count: int) -> QVBoxLayout:
        """Create title and description section"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Title
        title_label = QLabel(title)
        title_label.setFont(self._get_title_font())
        title_label.setStyleSheet(f"color: {COLORS['on_surface']};")
        
        # Description
        desc_label = QLabel(f"{count:,} items carefully curated")
        desc_label.setFont(self._get_desc_font())
        desc_label.setStyleSheet(f"color: {COLORS['on_surface_variant']};")
        
        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        
        return layout
    
    def _create_controls(self) -> QHBoxLayout:
        """Create control buttons (view mode, import)"""
        layout = QHBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # View mode toggle
        self.view_toggle = ViewModeToggle()
        self.view_toggle.view_mode_changed.connect(self.view_mode_changed.emit)
        layout.addWidget(self.view_toggle)
        
        # Import button
        import_btn = QPushButton()
        import_btn.setText("📁 Import Photos")
        import_btn.setFont(self._get_import_font())
        import_btn.setFixedHeight(40)
        import_btn.setMinimumWidth(160)
        import_btn.setStyleSheet(self._get_import_button_stylesheet())
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.clicked.connect(self.import_clicked.emit)
        layout.addWidget(import_btn)
        
        return layout
    
    def _get_title_font(self) -> QFont:
        """Get font for title"""
        font = QFont("Manrope")
        font.setPointSize(18)
        font.setWeight(700)
        return font
    
    def _get_desc_font(self) -> QFont:
        """Get font for description"""
        font = QFont("Inter")
        font.setPointSize(10)
        return font
    
    def _get_import_font(self) -> QFont:
        """Get font for import button"""
        font = QFont("Inter")
        font.setPointSize(10)
        font.setWeight(600)
        return font
    
    def _get_import_button_stylesheet(self) -> str:
        """Get stylesheet for import button"""
        return f"""
            QPushButton {{
                background: linear-gradient(135deg, {COLORS['primary']}, {COLORS['primary_container']});
                border: none;
                border-radius: 2px;
                color: {COLORS['on_primary']};
                padding: 6px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: linear-gradient(135deg, {COLORS['primary_dim']}, {COLORS['primary']});
            }}
            QPushButton:pressed {{
                transform: scale(0.98);
            }}
        """


class DateHeaderSection(QFrame):
    """Material Design 3 Date Section Header"""
    
    def __init__(self, date_label: str, photo_count: int, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(14, 14, 14, 0.90);
                backdrop-filter: blur(10px);
            }}
        """)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        # Date label
        date_label_widget = QLabel(date_label)
        date_label_widget.setFont(self._get_date_font())
        date_label_widget.setStyleSheet(f"color: {COLORS['on_surface']};")
        layout.addWidget(date_label_widget)
        
        # Divider line
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: rgba(71, 72, 72, 0.1);")
        layout.addWidget(divider, 1)
        
        # Count
        count_label = QLabel(f"{photo_count} Photos")
        count_label.setFont(self._get_count_font())
        count_label.setStyleSheet(f"color: {COLORS['on_surface_variant']};")
        layout.addWidget(count_label)
        
        self.setLayout(layout)
    
    def _get_date_font(self) -> QFont:
        """Get font for date label"""
        font = QFont("Manrope")
        font.setPointSize(12)
        font.setWeight(600)
        return font
    
    def _get_count_font(self) -> QFont:
        """Get font for count"""
        font = QFont("Inter")
        font.setPointSize(8)
        return font
