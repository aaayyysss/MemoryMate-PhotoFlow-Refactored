# ui/accordion_sidebar/quick_section.py
# Quick dates section - stub implementation

import logging
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Signal, Qt
from .base_section import BaseSection

logger = logging.getLogger(__name__)


class QuickSection(BaseSection):
    """
    Quick dates section implementation (simplified).
    
    Quick access to recent dates (Today, Yesterday, This Week, etc.)
    TODO: Implement full quick dates logic.
    """

    quickDateSelected = Signal(str)  # quick_date_key (e.g., "today", "this_week")

    def __init__(self, parent=None):
        super().__init__(parent)

    def get_section_id(self) -> str:
        return "quick"

    def get_title(self) -> str:
        return "Quick Dates"

    def get_icon(self) -> str:
        return "⚡"

    def load_section(self) -> None:
        """Load quick dates section data."""
        logger.info("[QuickSection] Load section (stub)")
        self._loading = False

    def create_content_widget(self, data):
        """Create quick dates section widget."""
        # TODO: Implement full quick dates UI
        placeholder = QLabel("Quick dates section\n(implementation pending)")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("padding: 20px; color: #666;")
        return placeholder
