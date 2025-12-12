# ui/accordion_sidebar/people_section.py
# People section - stub implementation

import logging
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Signal, Qt
from .base_section import BaseSection

logger = logging.getLogger(__name__)


class PeopleSection(BaseSection):
    """
    People section implementation (simplified).
    
    TODO: Implement full people/face recognition display logic.
    """

    personSelected = Signal(str)  # person_branch_key

    def __init__(self, parent=None):
        super().__init__(parent)

    def get_section_id(self) -> str:
        return "people"

    def get_title(self) -> str:
        return "People"

    def get_icon(self) -> str:
        return "👤"

    def load_section(self) -> None:
        """Load people section data."""
        logger.info("[PeopleSection] Load section (stub)")
        self._loading = False

    def create_content_widget(self, data):
        """Create people section widget."""
        # TODO: Implement full people section UI
        placeholder = QLabel("People section\n(implementation pending)")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("padding: 20px; color: #666;")
        return placeholder
