# ui/accordion_sidebar/__init__.py
# Main orchestrator for modularized accordion sidebar

"""
Modularized Accordion Sidebar

This module provides a refactored version of the accordion sidebar,
broken down into manageable, testable components.

Structure:
- section_widgets.py: SectionHeader and AccordionSection UI components
- base_section.py: BaseSection abstract interface
- folders_section.py: Folders hierarchy implementation
- dates_section.py: Date hierarchy implementation
- videos_section.py: Videos filtering (stub)
- people_section.py: People/faces section (stub)
- quick_section.py: Quick dates section (stub)
- __init__.py: Main AccordionSidebar orchestrator (this file)

Phase 3 Task 3.2: Modularize AccordionSidebar (94KB → modules)
"""

import logging
from typing import Optional, Dict
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QScrollArea, QSizePolicy)
from PySide6.QtCore import Signal, Qt
from reference_db import ReferenceDB

from .section_widgets import AccordionSection
from .folders_section import FoldersSection
from .dates_section import DatesSection
from .videos_section import VideosSection
from .people_section import PeopleSection
from .quick_section import QuickSection

logger = logging.getLogger(__name__)


class AccordionSidebar(QWidget):
    """
    Main accordion sidebar widget (modularized version).

    Manages multiple collapsible sections with:
    - Vertical navigation bar (left side)
    - Expandable sections (right side)
    - One section expanded at a time
    - Thread-safe data loading
    - Generation tokens to prevent stale data

    This is a simplified orchestrator that delegates section logic
    to individual modules.
    """

    # Signals to parent (MainWindow/GooglePhotosLayout) for grid filtering
    selectBranch = Signal(str)     # branch_key (e.g., "all" or "face_john")
    selectFolder = Signal(int)     # folder_id
    selectDate   = Signal(str)     # date string (e.g., "2025", "2025-10")
    selectTag    = Signal(str)     # tag name
    selectPerson = Signal(str)     # person branch_key
    selectVideo  = Signal(str)     # video filter type

    # Section expansion signal
    sectionExpanding = Signal(str)  # section_id

    def __init__(self, project_id: Optional[int], parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.db = ReferenceDB()
        self.expanded_section_id: Optional[str] = None

        # Section instances (logic modules)
        self.section_logic: Dict[str, any] = {}

        # Section UI widgets (containers)
        self.section_widgets: Dict[str, AccordionSection] = {}

        # Navigation buttons
        self.nav_buttons: Dict[str, QPushButton] = {}

        logger.info(f"[AccordionSidebar] Initializing with project_id={project_id}")

        # Build UI
        self._init_ui()
        self._create_sections()
        self._connect_signals()

        # Expand first section by default
        if self.section_widgets:
            first_section_id = list(self.section_widgets.keys())[0]
            self._expand_section(first_section_id)

    def _init_ui(self):
        """Initialize main UI layout."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === LEFT: Vertical Navigation Bar ===
        nav_bar = QWidget()
        nav_bar.setFixedWidth(52)
        nav_bar.setStyleSheet("""
            QWidget {
                background: #ffffff;
                border-right: 1px solid #dadce0;
            }
        """)
        self.nav_layout = QVBoxLayout(nav_bar)
        self.nav_layout.setContentsMargins(6, 12, 6, 4)
        self.nav_layout.setSpacing(4)

        main_layout.addWidget(nav_bar)

        # === RIGHT: Sections Container ===
        self.sections_container = QWidget()
        self.sections_container.setStyleSheet("""
            QWidget {
                background: #f8f9fa;
            }
        """)
        self.sections_layout = QVBoxLayout(self.sections_container)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(2)

        # Scroll area for sections
        scroll = QScrollArea()
        scroll.setWidget(self.sections_container)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # BUGFIX: Use QFrame.NoFrame enum instead of integer
        from PySide6.QtWidgets import QFrame
        scroll.setFrameShape(QFrame.NoFrame)  # No frame

        main_layout.addWidget(scroll)

    def _create_sections(self):
        """Create all section instances."""

        # Create section logic modules
        self.section_logic = {
            "folders": FoldersSection(self),
            "dates": DatesSection(self),
            "videos": VideosSection(self),
            "people": PeopleSection(self),
            "quick": QuickSection(self)
        }

        # Set project ID and DB reference for all sections
        for section_id, section in self.section_logic.items():
            section.set_project(self.project_id)
            if hasattr(section, 'set_db'):
                section.set_db(self.db)

        # Create UI widgets for each section
        for section_id, section_logic in self.section_logic.items():
            # Create AccordionSection UI container
            section_widget = AccordionSection(
                section_id=section_id,
                title=section_logic.get_title(),
                icon=section_logic.get_icon()
            )
            section_widget.expandRequested.connect(self._on_section_expand_requested)

            # Store references
            self.section_widgets[section_id] = section_widget

            # Add to layout
            self.sections_layout.addWidget(section_widget)

            # Create navigation button
            nav_btn = QPushButton(section_logic.get_icon())
            nav_btn.setFixedSize(40, 40)
            nav_btn.setToolTip(section_logic.get_title())
            nav_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    font-size: 18px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background: #f1f3f4;
                }
                QPushButton:pressed {
                    background: #e8f0fe;
                }
            """)
            nav_btn.clicked.connect(lambda checked, sid=section_id: self._expand_section(sid))
            self.nav_buttons[section_id] = nav_btn
            self.nav_layout.addWidget(nav_btn)

        # Add spacer at bottom of nav bar
        self.nav_layout.addStretch()

        logger.info(f"[AccordionSidebar] Created {len(self.section_logic)} sections")

    def _connect_signals(self):
        """Connect section signals to accordion signals."""

        # Folders section
        folders = self.section_logic.get("folders")
        if folders and hasattr(folders, 'folderSelected'):
            folders.folderSelected.connect(self.selectFolder.emit)

        # Dates section
        dates = self.section_logic.get("dates")
        if dates and hasattr(dates, 'dateSelected'):
            dates.dateSelected.connect(self.selectDate.emit)

        # People section
        people = self.section_logic.get("people")
        if people and hasattr(people, 'personSelected'):
            people.personSelected.connect(self.selectPerson.emit)

        # Videos section
        videos = self.section_logic.get("videos")
        if videos and hasattr(videos, 'videoFilterSelected'):
            videos.videoFilterSelected.connect(self.selectVideo.emit)

        # Quick section
        quick = self.section_logic.get("quick")
        if quick and hasattr(quick, 'quickDateSelected'):
            quick.quickDateSelected.connect(self.selectDate.emit)

    def _on_section_expand_requested(self, section_id: str):
        """Handle section expand request."""
        self._expand_section(section_id)

    def _expand_section(self, section_id: str):
        """Expand specified section and collapse others."""
        if section_id not in self.section_widgets:
            logger.warning(f"[AccordionSidebar] Unknown section: {section_id}")
            return

        logger.info(f"[AccordionSidebar] Expanding section: {section_id}")

        # Emit expansion signal
        self.sectionExpanding.emit(section_id)

        # Collapse all sections
        for sid, widget in self.section_widgets.items():
            widget.set_expanded(sid == section_id)

        # Update expanded section ID
        self.expanded_section_id = section_id

        # Load section data if not already loaded
        section_logic = self.section_logic.get(section_id)
        if section_logic and not section_logic.is_loading():
            signals = getattr(section_logic, 'signals', None)
            loaded_signal = getattr(signals, 'loaded', None)

            # Connect before triggering load to avoid missing fast emissions
            if loaded_signal and not getattr(section_logic, '_loaded_connected', False):
                loaded_signal.connect(
                    lambda gen, data: self._on_section_loaded(section_id, gen, data)
                )
                section_logic._loaded_connected = True

            result = section_logic.load_section()

            # Fallback: some stub sections complete synchronously without emitting
            if not section_logic.is_loading():
                generation = getattr(section_logic, '_generation', 0)
                self._on_section_loaded(section_id, generation, result)

    def _on_section_loaded(self, section_id: str, generation: int, data):
        """Handle section data loaded."""
        section_logic = self.section_logic.get(section_id)
        section_widget = self.section_widgets.get(section_id)

        if not section_logic or not section_widget:
            return

        # Check generation (staleness)
        if generation != section_logic._generation:
            logger.debug(f"[AccordionSidebar] Discarding stale data for {section_id}")
            return

        # Create content widget
        content_widget = section_logic.create_content_widget(data)
        if content_widget:
            section_widget.set_content_widget(content_widget)

            # Update count if available
            if hasattr(data, '__len__'):
                section_widget.set_count(len(data))

        logger.info(f"[AccordionSidebar] Section {section_id} loaded and displayed")

    # === Public API ===

    def set_project(self, project_id: int):
        """Update all sections for new project."""
        logger.info(f"[AccordionSidebar] Switching project: {self.project_id} → {project_id}")

        self.project_id = project_id

        # Update all sections
        for section in self.section_logic.values():
            section.set_project(project_id)

        # Reload expanded section
        if self.expanded_section_id:
            section = self.section_logic.get(self.expanded_section_id)
            if section:
                section.load_section()

    def reload_all_sections(self):
        """Reload all sections from database."""
        logger.info("[AccordionSidebar] Reloading all sections")

        for section_id, section in self.section_logic.items():
            section.load_section()

    def cleanup(self):
        """Clean up resources before destruction."""
        logger.info("[AccordionSidebar] Cleanup")

        # Cleanup all sections
        for section in self.section_logic.values():
            if hasattr(section, 'cleanup'):
                section.cleanup()

        # Close database
        if hasattr(self, 'db') and self.db:
            try:
                self.db.close()
            except Exception as e:
                logger.error(f"[AccordionSidebar] Error closing database: {e}")

    def _dbg(self, msg: str):
        """Debug logging helper."""
        logger.debug(f"[AccordionSidebar] {msg}")


# Export main class
__all__ = ['AccordionSidebar']
