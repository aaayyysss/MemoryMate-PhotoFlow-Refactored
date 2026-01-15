# layouts/google_components/duplicates_dialog.py
# Version 01.00.00.00 dated 20260115
# Duplicate review and management dialog for Google Layout

"""
DuplicatesDialog - Review and manage exact duplicates

This dialog shows a list of duplicate assets and allows users to:
- Review duplicate groups
- Compare instances side-by-side
- Keep/delete specific instances
- Merge metadata (future)
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem
)
from PySide6.QtCore import Signal, Qt
from typing import Optional, List, Dict, Any
from logging_config import get_logger

logger = get_logger(__name__)


class DuplicatesDialog(QDialog):
    """
    Dialog for reviewing and managing exact duplicates.

    Displays:
    - List of duplicate assets (left panel)
    - Instance details for selected asset (right panel)
    - Actions: Keep All, Delete Selected, Set Representative

    Signals:
    - duplicate_action_taken: Emitted when user takes action on duplicates
    """

    # Signals
    duplicate_action_taken = Signal(str, int)  # action, asset_id

    def __init__(self, project_id: int, parent=None):
        """
        Initialize DuplicatesDialog.

        Args:
            project_id: Project ID
            parent: Parent widget
        """
        super().__init__(parent)
        self.project_id = project_id

        self.setWindowTitle("Review Duplicates")
        self.setMinimumSize(800, 600)

        self._init_ui()
        self._load_duplicates()

    def _init_ui(self):
        """Initialize UI components (placeholder)."""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Duplicate Photo Review")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        layout.addWidget(title)

        # Placeholder message
        message = QLabel(
            "This dialog will display duplicate assets and allow review/management.\n\n"
            "Implementation pending:\n"
            "- Load duplicates from AssetService\n"
            "- Display asset list with instance counts\n"
            "- Show instance details and comparison\n"
            "- Actions: Keep All, Delete Selected, Set Representative"
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _load_duplicates(self):
        """Load duplicate assets from database (placeholder)."""
        # TODO: Implement
        # from services.asset_service import AssetService
        # duplicates = asset_service.list_duplicates(self.project_id)
        pass
