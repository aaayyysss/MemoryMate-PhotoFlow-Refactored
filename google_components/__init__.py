"""
Google Photos Layout Components
Extracted components from google_layout.py for better organization and maintainability.

Phase 3A: UI Widgets
- FlowLayout, CollapsibleSection, PersonCard, PeopleGridView

Future phases will extract:
- Timeline view component
- People/face management component
- Sidebar manager component
- Media lightbox component
"""

from google_components.widgets import (
    FlowLayout,
    CollapsibleSection,
    PersonCard,
    PeopleGridView
)

__all__ = [
    'FlowLayout',
    'CollapsibleSection',
    'PersonCard',
    'PeopleGridView',
]
