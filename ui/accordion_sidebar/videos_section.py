# ui/accordion_sidebar/videos_section.py
# Videos section - stub implementation

import logging
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Signal, Qt
from .base_section import BaseSection

logger = logging.getLogger(__name__)


class VideosSection(BaseSection):
    """
    Videos section implementation (simplified).
    
    TODO: Implement full video filtering and display logic.
    """

    videoFilterSelected = Signal(str)  # filter_type (e.g., "all", "hd", "short")

    def __init__(self, parent=None):
        super().__init__(parent)

    def get_section_id(self) -> str:
        return "videos"

    def get_title(self) -> str:
        return "Videos"

    def get_icon(self) -> str:
        return "🎬"

    def load_section(self) -> None:
        """Load videos section data."""
        logger.info("[VideosSection] Load section (stub)")
        self._loading = False

    def create_content_widget(self, data):
        """Create videos section widget."""
        # TODO: Implement full videos section UI
        placeholder = QLabel("Videos section\n(implementation pending)")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("padding: 20px; color: #666;")
        return placeholder
