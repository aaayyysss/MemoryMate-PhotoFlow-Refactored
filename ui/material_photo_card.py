"""
Material Design 3 Photo Card Component
Precision Curator - Interactive Photo Grid

Implements the photo card with hover effects, selection, and metadata display.
Features:
- Hover scale animation (1.02x)
- Selection indicator (checkbox)
- Hover overlay with metadata and actions
- EXIF data display (shutter speed, f-stop, ISO, etc.)

Author: MemoryMate Design System
Version: 1.0
"""

from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QPushButton,
    QFrame
)
from PySide6.QtCore import (
    Qt, Signal, QSize, QPropertyAnimation, QEasingCurve,
    QRect, QTimer, QPoint
)
from PySide6.QtGui import (
    QPixmap, QIcon, QFont, QColor, QPainter, QPainterPath,
    QCursor
)
from ui.styles import COLORS
from typing import Optional, Dict


class PhotoCard(QFrame):
    """Material Design 3 Photo Card with hover effects and metadata"""
    
    # Signals
    clicked = Signal()
    deleted = Signal()
    favorited = Signal()
    info_clicked = Signal()
    
    def __init__(self, pixmap: QPixmap = None, metadata: Dict = None, parent=None):
        super().__init__(parent)
        
        self.pixmap = pixmap
        self.metadata = metadata or {}
        self.is_selected = False
        self.is_hovered = False
        
        # Animation
        self.hover_animation = None
        self.scale = 1.0
        
        self.setFixedSize(200, 200)  # Aspect square
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface_container']};
                border: 1px solid {COLORS['outline_variant']};
                border-radius: 2px;
            }}
        """)
        
        self._setup_ui()
        
        # Mouse events
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
    
    def _setup_ui(self):
        """Setup photo card UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Image container
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        
        if self.pixmap:
            scaled_pixmap = self.pixmap.scaledToWidth(200, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
        else:
            # Placeholder
            placeholder = QPixmap(200, 200)
            placeholder.fill(QColor(COLORS['surface_container_high']))
            self.image_label.setPixmap(placeholder)
        
        layout.addWidget(self.image_label)
        
        # Overlay (hidden by default)
        self.overlay = self._create_overlay()
        
        # Selection indicator (checkbox)
        self.selection_indicator = self._create_selection_indicator()
        
        self.setLayout(layout)
    
    def _create_selection_indicator(self) -> QFrame:
        """Create selection checkbox in top-left corner"""
        indicator = QFrame(self)
        indicator.setGeometry(12, 12, 20, 20)
        indicator.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 2px;
            }}
        """)
        indicator.hide()
        return indicator
    
    def _create_overlay(self) -> QFrame:
        """Create hover overlay with metadata and actions"""
        overlay = QFrame(self)
        overlay.setGeometry(self.rect())
        overlay.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(0, 0, 0, 0.4);
                border-radius: 2px;
            }}
        """)
        overlay.hide()
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)
        
        # Top: Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        favorite_btn = self._create_action_button('favorite', self._on_favorite)
        delete_btn = self._create_action_button('delete', self._on_delete)
        
        button_layout.addWidget(favorite_btn)
        button_layout.addWidget(delete_btn)
        button_layout.setSpacing(8)
        
        layout.addLayout(button_layout)
        layout.addStretch()
        
        # Bottom: Metadata and info button
        bottom_layout = QHBoxLayout()
        
        metadata_label = QLabel()
        metadata_text = self.metadata.get('exif', '1/500s f/2.8 ISO 100')
        metadata_label.setText(metadata_text)
        metadata_label.setFont(self._get_metadata_font())
        metadata_label.setStyleSheet(f"color: rgba(255, 255, 255, 0.8);")
        
        info_btn = self._create_action_button('info', self._on_info, bg_color=COLORS['primary'])
        
        bottom_layout.addWidget(metadata_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(info_btn)
        bottom_layout.setSpacing(8)
        
        layout.addLayout(bottom_layout)
        
        overlay.setLayout(layout)
        
        # Store button references
        self.overlay_favorite_btn = favorite_btn
        self.overlay_metadata_label = metadata_label
        
        return overlay
    
    def _create_action_button(self, icon: str, callback, bg_color: str = 'surface_container_highest') -> QPushButton:
        """Create an action button for overlay"""
        btn = QPushButton()
        btn.setText(icon)
        btn.setFont(self._get_icon_font())
        btn.setFixedSize(32, 32)
        btn.setFlat(True)
        
        if bg_color.startswith('#'):
            bg = bg_color
        else:
            bg = COLORS.get(bg_color, COLORS['surface_container_highest'])
        
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                border: none;
                border-radius: 2px;
                color: {COLORS['on_surface']};
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary']} if '{bg}' != '{COLORS['primary']}' else {COLORS['primary_dim']};
            }}
        """)
        
        btn.clicked.connect(callback)
        btn.setCursor(Qt.PointingHandCursor)
        
        return btn
    
    def _get_icon_font(self) -> QFont:
        """Get Material Symbols icon font"""
        font = QFont("Material Symbols Outlined")
        font.setPointSize(14)
        return font
    
    def _get_metadata_font(self) -> QFont:
        """Get font for metadata text"""
        font = QFont("Inter")
        font.setPointSize(7)
        return font
    
    def mousePressEvent(self, event):
        """Handle mouse press"""
        self.clicked.emit()
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Handle double click"""
        self.toggle_selection()
    
    def enterEvent(self, event):
        """Handle mouse enter"""
        self.is_hovered = True
        self.overlay.show()
        self.selection_indicator.show()
        self._animate_scale(1.02)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leave"""
        self.is_hovered = False
        if not self.is_selected:
            self.overlay.hide()
            self.selection_indicator.hide()
        self._animate_scale(1.0)
        super().leaveEvent(event)
    
    def _animate_scale(self, target_scale: float):
        """Animate scale with easing"""
        if self.hover_animation:
            self.hover_animation.stop()
        
        self.hover_animation = QPropertyAnimation(self, b"geometry")
        self.hover_animation.setDuration(300)
        self.hover_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # Calculate scaled geometry from center
        current_rect = self.geometry()
        center_x = current_rect.x() + current_rect.width() / 2
        center_y = current_rect.y() + current_rect.height() / 2
        
        new_width = int(200 * target_scale)
        new_height = int(200 * target_scale)
        new_x = int(center_x - new_width / 2)
        new_y = int(center_y - new_height / 2)
        
        self.hover_animation.setEndValue(QRect(new_x, new_y, new_width, new_height))
        self.hover_animation.start()
    
    def _on_favorite(self):
        """Handle favorite action"""
        self.favorited.emit()
    
    def _on_delete(self):
        """Handle delete action"""
        self.deleted.emit()
    
    def _on_info(self):
        """Handle info action"""
        self.info_clicked.emit()
    
    def toggle_selection(self):
        """Toggle selection state"""
        self.is_selected = not self.is_selected
        
        if self.is_selected:
            self.selection_indicator.setStyleSheet(f"""
                QFrame {{
                    background-color: {COLORS['primary']};
                    border: 2px solid {COLORS['on_primary']};
                    border-radius: 2px;
                }}
            """)
            # Add check mark
            label = QLabel(self.selection_indicator)
            label.setText("✓")
            label.setAlignment(Qt.AlignCenter)
            label.setFont(QFont("Arial", 12, QFont.Bold))
            label.setStyleSheet(f"color: {COLORS['on_primary']};")
        else:
            self.selection_indicator.setStyleSheet(f"""
                QFrame {{
                    background-color: transparent;
                    border: 2px solid rgba(255, 255, 255, 0.3);
                    border-radius: 2px;
                }}
            """)
    
    def set_metadata(self, metadata: Dict):
        """Update card metadata"""
        self.metadata = metadata
        if hasattr(self, 'overlay_metadata_label'):
            exif_text = metadata.get('exif', '1/500s f/2.8 ISO 100')
            self.overlay_metadata_label.setText(exif_text)
    
    def set_pixmap(self, pixmap: QPixmap):
        """Update card image"""
        self.pixmap = pixmap
        if hasattr(self, 'image_label'):
            scaled_pixmap = pixmap.scaledToWidth(200, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
