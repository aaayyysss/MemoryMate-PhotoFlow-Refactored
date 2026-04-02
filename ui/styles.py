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
    # ──────────────────────────────────────────────────────────────
    # DARK THEME (Stitch / Material Design 3)
    # ────────────────────────────────────────────────────────────── 
    # Google's Material Design 3 dark color scheme optimized for accessibility
    # Designed with WCAG AA compliance in mind (min 4.5:1 contrast ratio)
    # ──────────────────────────────────────────────────────────────
    
    # ── PRIMARY COLOR ──
    # Bright blue for dark backgrounds - high visibility
    'primary': '#8fcdff',                   # Primary action color (bright blue)
    'primary_dim': '#6bc1ff',              # Dimmed primary for inactive states
    'primary_container': '#004b71',         # Dark container for primary sections
    'on_primary': '#004467',                # Text on primary background
    'on_primary_container': '#a5d6ff',     # Text on primary container
    'primary_fixed': '#cbe6ff',            # Fixed color for consistency
    'primary_fixed_dim': '#aed9ff',        # Fixed dimmed variant
    
    # ── SECONDARY COLOR ──
    # Supporting blue tone
    'secondary': '#9c9ea4',                # Secondary action color
    'secondary_dim': '#9c9ea4',            # Dimmed secondary
    'secondary_container': '#393b41',      # Dark container for secondary
    'on_secondary': '#1e2025',             # Text on secondary background
    'on_secondary_container': '#bebfc5',   # Text on secondary container
    'secondary_fixed': '#e1e2e9',          # Fixed secondary
    'secondary_fixed_dim': '#d3d4da',      # Fixed dimmed secondary
    
    # ── TERTIARY COLOR ──
    # Purple/lavender accent
    'tertiary': '#edecff',                 # Tertiary action color
    'tertiary_dim': '#cecfef',             # Dimmed tertiary
    'tertiary_container': '#dcddfe',       # Container for tertiary
    'on_tertiary': '#545671',              # Text on tertiary background
    'on_tertiary_container': '#4c4e69',    # Text on tertiary container
    'tertiary_fixed': '#dcddfe',           # Fixed tertiary
    'tertiary_fixed_dim': '#cecfef',       # Fixed dimmed tertiary
    
    # ── NEUTRAL COLORS ──
    # Core neutral palette for surfaces
    'background': '#0e0e0e',               # Main dark background
    'surface': '#0e0e0e',                  # Primary surface
    'surface_dim': '#0e0e0e',              # Dimmed surface
    'surface_bright': '#2b2c2c',           # Bright surface
    'surface_container_lowest': '#000000', # Lowest elevation surface
    'surface_container_low': '#131313',    # Low elevation surface
    'surface_container': '#191a1a',        # Default surface container
    'surface_container_high': '#1f2020',   # High elevation surface
    'surface_container_highest': '#252626', # Highest elevation surface
    'surface_variant': '#252626',          # Variant surface
    'surface_tint': '#8fcdff',             # Surface tint (primary)
    'inverse_surface': '#fcf9f8',          # Inverse surface (light)
    
    # ── TEXT COLORS (ON DARK SURFACES) ──
    # High contrast text for dark backgrounds
    'on_surface': '#e7e5e5',               # Main text on dark surfaces
    'on_surface_variant': '#acabab',       # Secondary text (low emphasis)
    'on_background': '#e7e5e5',            # Text on background
    'inverse_on_surface': '#565555',       # Text on inverse surface
    
    # ── OUTLINE COLORS ──
    # Borders and dividers
    'outline': '#757575',                  # Main border/divider
    'outline_variant': '#474848',          # Secondary outline
    
    # ── ERROR & STATUS ──
    'error': '#ee7d77',                    # Error/destructive actions
    'error_dim': '#bb5551',                # Dimmed error
    'error_container': '#7f2927',          # Error container
    'on_error': '#490106',                 # Text on error surface
    'on_error_container': '#ff9993',       # Text on error container
    
    # ── SEMANTIC COLORS (LIGHT THEME - for reference) ──
    # These are kept for compatibility but dark theme uses above
    'success': '#34a853',                  # Green - success, checkmark
    'warning': '#fbbc04',                  # Amber - warning, caution
    'info': '#4285f4',                     # Blue - informational
    
    # ── SEMANTIC TEXT ──
    'on_success': '#ffffff',               # Text on success background
    'on_warning': '#202124',               # Text on warning background
    'on_info': '#ffffff',                  # Text on info background
    
    # ── SCRIM / OVERLAY ──
    # Semi-transparent overlays
    'scrim': 'rgba(0, 0, 0, 0.40)',        # Dark overlay for modals
    'scrim_light': 'rgba(0, 0, 0, 0.12)',  # Light overlay for elevation
    
    # ──────────────────────────────────────────────────────────────
    # BACKWARD COMPATIBILITY ALIASES (Light theme → Dark theme mapping)
    # ────────────────────────────────────────────────────────────── 
    # These aliases maintain compatibility with existing code that
    # references old light theme color names
    # ──────────────────────────────────────────────────────────────
    'surface_primary': '#191a1a',          # Old light alias → dark surface_container
    'surface_secondary': '#1f2020',        # Old light alias → dark surface_container_high
    'surface_tertiary': '#252626',         # Old light alias → dark surface_variant
    'surface_tertiary_alt': '#252626',     # Old light alias → dark surface_variant
    'outline_primary': '#474848',          # Old light alias → dark outline_variant
    'outline_secondary': '#757575',        # Old light alias → dark outline
    'outline_tertiary': '#474848',         # Old light alias → dark outline_variant
    'text_primary': '#e7e5e5',             # Old light alias → dark on_surface
    'text_secondary': '#acabab',           # Old light alias → dark on_surface_variant
    'text_tertiary': '#acabab',            # Old light alias → dark on_surface_variant
    'text_disabled': '#474848',            # Old light alias → dark outline_variant
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
