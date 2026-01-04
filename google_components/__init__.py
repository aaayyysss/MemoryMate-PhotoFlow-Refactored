"""
Google Photos Layout Components
Extracted components from google_layout.py for better organization and maintainability.

Phase 3A: UI Widgets
- FlowLayout, CollapsibleSection, PersonCard, PeopleGridView

Phase 3C: Media Lightbox
- MediaLightbox, TrimMarkerSlider
- PreloadImageSignals, PreloadImageWorker
- ProgressiveImageSignals, ProgressiveImageWorker

Future phases will extract:
- Timeline view component
- People/face management component
- Sidebar manager component
"""

from google_components.widgets import (
    FlowLayout,
    CollapsibleSection,
    PersonCard,
    PeopleGridView
)

from google_components.media_lightbox import (
    MediaLightbox,
    TrimMarkerSlider,
    PreloadImageSignals,
    PreloadImageWorker,
    ProgressiveImageSignals,
    ProgressiveImageWorker
)

__all__ = [
    # Phase 3A: UI Widgets
    'FlowLayout',
    'CollapsibleSection',
    'PersonCard',
    'PeopleGridView',

    # Phase 3C: Media Lightbox
    'MediaLightbox',
    'TrimMarkerSlider',
    'PreloadImageSignals',
    'PreloadImageWorker',
    'ProgressiveImageSignals',
    'ProgressiveImageWorker',
]
