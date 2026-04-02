"""
ui/styles.py
Material Design 3 Design System for MemoryMate PhotoFlow

This module contains all design constants (colors, spacing, typography, shadows)
used throughout the application. Importing from here ensures visual consistency.

Usage:
    from ui.styles import COLORS, SPACING, TYPOGRAPHY
    
    # In Qt code:
    label.setStyleSheet(f"color: {COLORS['text_primary']};")
    
Author: Design System
Version: 1.0
"""

from typing import Dict, Any

# ============================================================================
# COLOR SYSTEM - Material Design 3
# ============================================================================
# All colors are hex strings (#RRGGBB format)
# Follows Material Design 3 semantic color tokens

COLORS: Dict[str, str] = {
    # ── PRIMARY COLOR ──
    # Google's signature blue - used for primary actions, active states
    'primary': '#1a73e8',                    # Primary action color
    'primary_container': '#e8f0fe',         # Light background for primary sections
    'on_primary': '#ffffff',                # Text on primary background
    
    # ── SURFACE COLORS ──
    # Background colors for different surface levels
    'surface_primary': '#ffffff',           # Main white background (highest elevation)
    'surface_secondary': '#f8f9fa',         # Off-white for inactive sections
    'surface_tertiary': '#f1f3f4',          # Light gray for hover states
    'surface_tertiary_alt': '#ececf1',      # Alternative light gray
    
    # ── OUTLINE COLORS ──
    # Borders and dividers
    'outline_primary': '#dadce0',           # Main border color
    'outline_secondary': '#bdc1c6',         # Secondary border (hover, emphasis)
    'outline_tertiary': '#e8eaed',          # Tertiary border (subtle)
    
    # ── TEXT COLORS ──
    # Text on white backgrounds (primary surface)
    'text_primary': '#202124',              # Main text (high contrast)
    'text_secondary': '#3d3d3d',            # Secondary text (66% contrast) - Phase 3: Updated for WCAG AA
    'text_tertiary': '#9aa0a6',             # Tertiary text (low emphasis)
    'text_disabled': '#dadce0',             # Disabled text (very low contrast)
    
    # ── SEMANTIC COLORS ──
    # Status-based colors (follows Material Design)
    'success': '#34a853',                   # Green - success, checkmark
    'warning': '#fbbc04',                   # Amber - warning, caution
    'error': '#ea4335',                     # Red - error, alert, delete
    'info': '#4285f4',                      # Blue - informational
    
    # ── SEMANTIC TEXT ──
    'on_success': '#ffffff',                # Text on success background
    'on_warning': '#202124',                # Text on warning background
    'on_error': '#ffffff',                  # Text on error background
    'on_info': '#ffffff',                   # Text on info background
    
    # ── SCRIM / OVERLAY ──
    # Semi-transparent overlays
    'scrim': 'rgba(0, 0, 0, 0.32)',        # Dark overlay for modals
    'scrim_light': 'rgba(0, 0, 0, 0.08)',  # Light overlay for elevation
}

# ============================================================================
# SPACING SYSTEM - 8px Grid
# ============================================================================
# All spacing values are multiples of 8px (0.5x to 3x grid)
# Follows Material Design's 8px grid system

SPACING: Dict[str, int] = {
    'xs': 4,        # 0.5x grid (4px) - Use for very tight spacing (rare)
    'sm': 8,        # 1x grid (8px) - Standard spacing
    'md': 12,       # 1.5x grid (12px) - Medium spacing
    'lg': 16,       # 2x grid (16px) - Large spacing
    'xl': 24,       # 3x grid (24px) - Extra large spacing
}

# Common spacing patterns for layouts
PADDING = {
    'none': 0,
    'default': SPACING['sm'],              # 8px default padding
    'compact': SPACING['xs'],              # 4px compact
    'section': SPACING['md'],              # 12px for section content
    'button': f"{SPACING['xs']} {SPACING['sm']}",  # 4px vertical, 8px horizontal
}

MARGIN = {
    'none': 0,
    'section': SPACING['sm'],              # 8px margin between sections
    'item': SPACING['xs'],                 # 4px margin between items
    'block': SPACING['md'],                # 12px block margin
}

# ============================================================================
# TYPOGRAPHY SYSTEM - Material Design Scale
# ============================================================================
# Size, weight, line-height for each typographic role

TYPOGRAPHY: Dict[str, Dict[str, Any]] = {
    'h1': {
        'size': 32,
        'size_pt': 24,              # Point size for Qt
        'weight': 400,              # Light
        'line_height': 40,          # 1.25x
    },
    'h2': {
        'size': 28,
        'size_pt': 21,
        'weight': 400,
        'line_height': 36,
    },
    'h3': {
        'size': 24,
        'size_pt': 18,
        'weight': 500,
        'line_height': 32,
    },
    # Most used in sidebar
    'h4': {
        'size': 20,
        'size_pt': 15,
        'weight': 500,
        'line_height': 28,
    },
    'title': {
        'size': 14,                 # Section headers, tab labels
        'size_pt': 10,              # Qt uses different scale
        'weight': 600,              # Semi-bold
        'line_height': 20,          # 1.43x
    },
    # Standard body text
    'body': {
        'size': 14,
        'size_pt': 10,
        'weight': 400,              # Regular
        'line_height': 20,
    },
    'body_small': {
        'size': 12,
        'size_pt': 9,
        'weight': 400,
        'line_height': 16,
    },
    # Small labels, badges, counts
    'label': {
        'size': 12,
        'size_pt': 9,
        'weight': 500,              # Medium
        'line_height': 16,
    },
    # Very small text: hints, captions, timestamps
    'caption': {
        'size': 12,
        'size_pt': 9,
        'weight': 400,
        'line_height': 16,
    },
    'caption_small': {
        'size': 11,
        'size_pt': 8,
        'weight': 400,
        'line_height': 14,
    },
}

# ============================================================================
# BORDER RADIUS - Corner Rounding
# ============================================================================
# Border radius values for different component types

RADIUS: Dict[str, int] = {
    'none': 0,
    'small': 4,      # Tight radius (buttons, small components)
    'medium': 6,     # Default (cards, sections)
    'large': 8,      # Large radius (modals, major containers)
    'full': 9999,    # Fully rounded (circles)
}

# ============================================================================
# SHADOWS - Elevation Effects (Material Design 3)
# ============================================================================
# Box-shadow values for elevation levels

SHADOWS: Dict[str, str] = {
    'none': 'none',
    # Level 1: Small elevation (cards, buttons on hover)
    'elevation_1': '0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24)',
    # Level 2: Medium elevation (dropdowns, popovers)
    'elevation_2': '0 3px 6px rgba(0, 0, 0, 0.16), 0 3px 6px rgba(0, 0, 0, 0.23)',
    # Level 3: High elevation (modals)
    'elevation_3': '0 10px 20px rgba(0, 0, 0, 0.19), 0 6px 6px rgba(0, 0, 0, 0.23)',
    # Level 4: Very high elevation (floating action buttons, notifications)
    'elevation_4': '0 15px 25px rgba(0, 0, 0, 0.15), 0 10px 10px rgba(0, 0, 0, 0.05)',
}

# ============================================================================
# TRANSITIONS / ANIMATIONS
# ============================================================================
# Animation durations and easing functions

ANIMATION: Dict[str, Any] = {
    'fast': 150,                # Fast transitions (hover states)
    'normal': 300,              # Normal transitions (state changes)
    'slow': 500,                # Slow transitions (major layout changes)
    'easing_standard': 'cubic-bezier(0.2, 0, 0, 1)',     # Material standard easing
    'easing_emphasis': 'cubic-bezier(0.3, 0, 0.8, 0.15)', # Emphasis easing
}

# ============================================================================
# COMPONENT-SPECIFIC STYLES
# ============================================================================
# Commonly used style combinations for specific components

BUTTON_STYLES: Dict[str, Dict[str, str]] = {
    'primary': {
        'background': COLORS['primary'],
        'color': COLORS['on_primary'],
        'border': 'none',
        'border_radius': f"{RADIUS['small']}px",
        'padding': '6px 12px',
        'font_size': f"{TYPOGRAPHY['body']['size_pt']}pt",
        'font_weight': '500',
    },
    'secondary': {
        'background': COLORS['surface_primary'],
        'color': COLORS['text_primary'],
        'border': f"1px solid {COLORS['outline_primary']}",
        'border_radius': f"{RADIUS['small']}px",
        'padding': '6px 12px',
        'font_size': f"{TYPOGRAPHY['body']['size_pt']}pt",
        'font_weight': '500',
    },
    'section_header_active': {
        'background': COLORS['primary_container'],
        'color': COLORS['text_primary'],
        'border': f"none",
        'border_left': f"3px solid {COLORS['primary']}",  # Left accent
        'border_radius': f"{RADIUS['medium']}px",
        'padding': f"{SPACING['md']}px {SPACING['sm']}px",
        'font_size': f"{TYPOGRAPHY['title']['size_pt']}pt",
        'font_weight': f"{TYPOGRAPHY['title']['weight']}",
    },
    'section_header_inactive': {
        'background': COLORS['surface_secondary'],
        'color': COLORS['text_primary'],
        'border': f"1px solid {COLORS['outline_tertiary']}",
        'border_radius': f"{RADIUS['medium']}px",
        'padding': f"{SPACING['md']}px {SPACING['sm']}px",
        'font_size': f"{TYPOGRAPHY['title']['size_pt']}pt",
        'font_weight': f"{TYPOGRAPHY['title']['weight']}",
    },
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_color(role: str) -> str:
    """
    Get a color by semantic role.
    
    Args:
        role: Color role (e.g., 'primary', 'error', 'text_primary')
    
    Returns:
        Hex color string or raises KeyError if role not found
    
    Example:
        color = get_color('primary')  # Returns '#1a73e8'
    """
    if role not in COLORS:
        raise KeyError(f"Color role '{role}' not found in COLORS. Available: {list(COLORS.keys())}")
    return COLORS[role]


def get_spacing(scale: str) -> int:
    """
    Get a spacing value by scale.
    
    Args:
        scale: Spacing scale ('xs', 'sm', 'md', 'lg', 'xl')
    
    Returns:
        Pixel value
    
    Example:
        margin = get_spacing('md')  # Returns 12
    """
    if scale not in SPACING:
        raise KeyError(f"Spacing scale '{scale}' not found. Available: {list(SPACING.keys())}")
    return SPACING[scale]


def get_typography(role: str) -> Dict[str, Any]:
    """
    Get typography by role.
    
    Args:
        role: Typography role ('h1', 'body', 'caption', etc.)
    
    Returns:
        Dict with 'size_pt', 'weight', 'line_height' for Qt usage
    
    Example:
        typo = get_typography('body')
        font.setPointSize(typo['size_pt'])
        font.setWeight(typo['weight'])
    """
    if role not in TYPOGRAPHY:
        raise KeyError(f"Typography role '{role}' not found. Available: {list(TYPOGRAPHY.keys())}")
    return TYPOGRAPHY[role]


def get_button_style(variant: str) -> Dict[str, str]:
    """
    Get button stylesheet dict.
    
    Args:
        variant: Button variant ('primary', 'secondary', etc.)
    
    Returns:
        Dict of CSS-like properties
    
    Example:
        style = get_button_style('primary')
        btn.setStyleSheet(f"background: {style['background']};")
    """
    if variant not in BUTTON_STYLES:
        raise KeyError(f"Button variant '{variant}' not found. Available: {list(BUTTON_STYLES.keys())}")
    return BUTTON_STYLES[variant]


# ============================================================================
# STYLESHEET GENERATORS
# ============================================================================
# Helpers to generate full Qt stylesheets from these constants

def generate_stylesheet(widget_name: str, **properties) -> str:
    """
    Generate a Qt stylesheet string.
    
    Args:
        widget_name: Qt widget class name (e.g., 'QLabel', 'QPushButton')
        **properties: CSS properties as kwargs
    
    Returns:
        Stylesheet string
    
    Example:
        style = generate_stylesheet('QLabel', 
            color='#202124',
            font_size='13px',
            padding='8px'
        )
    """
    props_str = '; '.join(f"{k.replace('_', '-')}: {v}" for k, v in properties.items())
    return f"{widget_name} {{ {props_str}; }}"


# Export public API
__all__ = [
    'COLORS',
    'SPACING',
    'TYPOGRAPHY',
    'RADIUS',
    'SHADOWS',
    'ANIMATION',
    'BUTTON_STYLES',
    'get_color',
    'get_spacing',
    'get_typography',
    'get_button_style',
    'generate_stylesheet',
]
