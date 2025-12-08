"""
Google Photos-style Accordion Sidebar

Replaces the tab-based sidebar with an accordion pattern where:
- One section expands to full sidebar height
- Other sections collapse to headers at bottom
- ONE universal scrollbar for expanded section content
- One-click section switching

Architecture:
- SectionHeader: Clickable header button (always visible)
- AccordionSection: Header + content (expandable/collapsible)
- AccordionSidebar: Main container managing all sections
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QSize, QThreadPool
from PySide6.QtGui import QFont, QIcon
from datetime import datetime

# Import database and UI components
from reference_db import ReferenceDB
from ui.people_list_view import PeopleListView


class SectionHeader(QFrame):
    """
    Clickable header for accordion section.
    Shows: Icon + Title + Count (optional) + Chevron

    States:
    - Active (expanded): Bold text, highlighted background, chevron down (▼)
    - Inactive (collapsed): Normal text, default background, chevron right (▶)
    """

    clicked = Signal()  # Emitted when header is clicked

    def __init__(self, section_id: str, title: str, icon: str = "", parent=None):
        super().__init__(parent)
        self.section_id = section_id
        self.title = title
        self.icon = icon
        self.is_active = False
        self.item_count = 0

        # Make the frame clickable
        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)

        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Icon + Title
        self.icon_label = QLabel(icon)
        self.icon_label.setFixedWidth(24)
        font = self.icon_label.font()
        font.setPointSize(14)
        self.icon_label.setFont(font)

        self.title_label = QLabel(title)
        self.title_font = self.title_label.font()

        # Count badge (optional)
        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #666; font-size: 11px;")
        self.count_label.setVisible(False)

        # Chevron (indicates expand/collapse state)
        self.chevron_label = QLabel("▶")  # Right arrow for collapsed
        self.chevron_label.setFixedWidth(20)
        chevron_font = self.chevron_label.font()
        chevron_font.setPointSize(10)
        self.chevron_label.setFont(chevron_font)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.count_label)
        layout.addWidget(self.chevron_label)

        # Initial styling
        self.set_active(False)

    def set_active(self, active: bool):
        """Set header to active (expanded) or inactive (collapsed) state."""
        self.is_active = active

        if active:
            # Active state: Bold, highlighted, chevron down
            self.title_font.setBold(True)
            self.title_label.setFont(self.title_font)
            self.chevron_label.setText("▼")  # Down arrow
            self.setStyleSheet("""
                SectionHeader {
                    background-color: #e3f2fd;
                    border: none;
                    border-radius: 4px;
                }
                SectionHeader:hover {
                    background-color: #bbdefb;
                }
            """)
        else:
            # Inactive state: Normal, default background, chevron right
            self.title_font.setBold(False)
            self.title_label.setFont(self.title_font)
            self.chevron_label.setText("▶")  # Right arrow
            self.setStyleSheet("""
                SectionHeader {
                    background-color: #f5f5f5;
                    border: none;
                    border-radius: 4px;
                }
                SectionHeader:hover {
                    background-color: #e0e0e0;
                }
            """)

    def set_count(self, count: int):
        """Update the count badge."""
        self.item_count = count
        if count > 0:
            self.count_label.setText(f"({count})")
            self.count_label.setVisible(True)
        else:
            self.count_label.setVisible(False)

    def mousePressEvent(self, event):
        """Handle mouse click on header."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AccordionSection(QWidget):
    """
    Individual accordion section.
    Contains:
    - Header (always visible)
    - Content widget (visible only when expanded)

    Can be expanded (shows content) or collapsed (header only).
    """

    # Signals
    expandRequested = Signal(str)  # section_id - Request to expand this section

    def __init__(self, section_id: str, title: str, icon: str = "", parent=None):
        super().__init__(parent)
        self.section_id = section_id
        self.title = title
        self.is_expanded = False

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header (always visible)
        self.header = SectionHeader(section_id, title, icon)
        self.header.clicked.connect(self._on_header_clicked)
        layout.addWidget(self.header)

        # Content area (visible only when expanded)
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # Scroll area for content (ONE scrollbar here)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.content_container)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVisible(False)  # Hidden by default

        layout.addWidget(self.scroll_area, stretch=1)  # Takes all available space when expanded

        # Set size policy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def _on_header_clicked(self):
        """Handle header click - request expansion."""
        self.expandRequested.emit(self.section_id)

    def set_expanded(self, expanded: bool):
        """Expand or collapse this section."""
        self.is_expanded = expanded
        self.header.set_active(expanded)
        self.scroll_area.setVisible(expanded)

        if expanded:
            # Expanded: Allow vertical expansion
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            # Collapsed: Fixed height (header only)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            self.setMaximumHeight(self.header.sizeHint().height())

    def set_content_widget(self, widget: QWidget):
        """Set the content widget for this section."""
        # Clear existing content
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new content
        if widget:
            self.content_layout.addWidget(widget)

    def set_count(self, count: int):
        """Update the count badge in header."""
        self.header.set_count(count)


class AccordionSidebar(QWidget):
    """
    Main accordion sidebar widget.

    Manages multiple AccordionSection widgets:
    - One section expanded at a time (takes full height)
    - Other sections collapsed to headers (at bottom)
    - ONE universal scrollbar (in expanded section)

    Signals match existing SidebarTabs for compatibility.
    """

    # Signals to parent (MainWindow/GooglePhotosLayout) for grid filtering
    selectBranch = Signal(str)     # branch_key e.g. "all" or "face_john"
    selectFolder = Signal(int)     # folder_id
    selectDate   = Signal(str)     # e.g. "2025-10" or "2025"
    selectTag    = Signal(str)     # tag name
    selectPerson = Signal(str)     # person branch_key

    def __init__(self, project_id: int | None, parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.sections = {}  # section_id -> AccordionSection
        self.expanded_section_id = None
        self.db = ReferenceDB()

        # Store content widgets for each section
        self.people_view = None

        self._dbg("AccordionSidebar __init__ started")

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # Container for all sections
        self.sections_container = QWidget()
        self.sections_layout = QVBoxLayout(self.sections_container)
        self.sections_layout.setContentsMargins(4, 4, 4, 4)
        self.sections_layout.setSpacing(4)

        main_layout.addWidget(self.sections_container)

        # Build sections
        self._build_sections()

        # Expand default section (People)
        self.expand_section("people")

        self._dbg("AccordionSidebar __init__ completed")

    def _dbg(self, msg):
        """Debug logging with timestamp."""
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] [AccordionSidebar] {msg}")

    def _build_sections(self):
        """Create all accordion sections."""
        self._dbg("Building accordion sections...")

        # Define sections in priority order
        sections_config = [
            ("people",   "👥 People",      "👥"),
            ("dates",    "📅 By Date",     "📅"),
            ("folders",  "📁 Folders",     "📁"),
            ("tags",     "🏷️  Tags",       "🏷️"),
            ("branches", "🌿 Branches",    "🌿"),
            ("quick",    "⚡ Quick Dates", "⚡"),
        ]

        for section_id, title, icon in sections_config:
            section = AccordionSection(section_id, title, icon)
            section.expandRequested.connect(self.expand_section)

            self.sections[section_id] = section
            self.sections_layout.addWidget(section)

        # Add stretch at the end to push collapsed sections to bottom
        self.sections_layout.addStretch()

        self._dbg(f"Created {len(self.sections)} sections")

    def expand_section(self, section_id: str):
        """
        Expand one section to full height, collapse all others.
        This is the core accordion behavior.
        """
        self._dbg(f"Expanding section: {section_id}")

        if section_id not in self.sections:
            self._dbg(f"⚠️ Section not found: {section_id}")
            return

        # Collapse all sections first
        for sid, section in self.sections.items():
            section.set_expanded(False)

        # Expand requested section
        self.sections[section_id].set_expanded(True)
        self.expanded_section_id = section_id

        # Reorder sections: expanded on top, collapsed at bottom
        self._reorder_sections()

        # Load content if needed
        self._load_section_content(section_id)

        self._dbg(f"✓ Section expanded: {section_id}")

    def _reorder_sections(self):
        """
        Reorder sections in layout:
        - Expanded section first (takes full height with stretch)
        - Collapsed sections below (no stretch, fixed size)
        """
        # Remove all sections from layout
        for section in self.sections.values():
            self.sections_layout.removeWidget(section)

        # Remove stretch if exists
        while self.sections_layout.count() > 0:
            item = self.sections_layout.takeAt(0)

        # Add expanded section first (with stretch to take full height)
        if self.expanded_section_id:
            expanded_section = self.sections[self.expanded_section_id]
            self.sections_layout.addWidget(expanded_section, stretch=1)

        # Add collapsed sections (no stretch, fixed size)
        for section_id, section in self.sections.items():
            if section_id != self.expanded_section_id:
                self.sections_layout.addWidget(section, stretch=0)

    def _load_section_content(self, section_id: str):
        """Load content for the specified section."""
        self._dbg(f"Loading content for section: {section_id}")

        if section_id == "people":
            self._load_people_section()
        elif section_id == "dates":
            self._load_dates_section()
        elif section_id == "folders":
            self._load_folders_section()
        elif section_id == "tags":
            self._load_tags_section()
        elif section_id == "branches":
            self._load_branches_section()
        elif section_id == "quick":
            self._load_quick_section()
        else:
            # Fallback placeholder
            section = self.sections[section_id]
            placeholder = QLabel(f"Content for {section_id} coming soon...")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 20px; color: #666;")
            section.set_content_widget(placeholder)

    def _load_people_section(self):
        """Load People/Face Clusters section content."""
        self._dbg("Loading People section...")

        section = self.sections.get("people")
        if not section or not self.project_id:
            return

        try:
            # Load face cluster data from database
            rows = self.db.get_face_clusters(self.project_id)
            self._dbg(f"Loaded {len(rows)} face clusters")

            # Create or reuse PeopleListView widget
            if not self.people_view:
                self.people_view = PeopleListView(self)
                self.people_view.set_database(self.db, self.project_id)

                # Connect signals
                self.people_view.personActivated.connect(self._on_person_activated)

            # Load people data
            self.people_view.load_people(rows)

            # Update count badge
            section.set_count(len(rows))

            # Set as content widget
            section.set_content_widget(self.people_view)

            self._dbg(f"✓ People section loaded with {len(rows)} clusters")

        except Exception as e:
            self._dbg(f"⚠️ Error loading people section: {e}")
            import traceback
            traceback.print_exc()

            # Show error placeholder
            error_label = QLabel(f"Error loading people:\n{str(e)}")
            error_label.setAlignment(Qt.AlignCenter)
            error_label.setStyleSheet("padding: 20px; color: #ff0000;")
            section.set_content_widget(error_label)

    def _on_person_activated(self, branch_key: str):
        """Handle person click - emit signal to filter grid."""
        self._dbg(f"Person activated: {branch_key}")
        # Emit branch selection signal for grid filtering
        self.selectBranch.emit(f"branch:{branch_key}")

    def _load_dates_section(self):
        """Load By Date section content. TODO: Phase 3"""
        section = self.sections.get("dates")
        if section:
            placeholder = QLabel("Dates content coming in Phase 3...")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 20px; color: #666;")
            section.set_content_widget(placeholder)

    def _load_folders_section(self):
        """Load Folders section content. TODO: Phase 3"""
        section = self.sections.get("folders")
        if section:
            placeholder = QLabel("Folders content coming in Phase 3...")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 20px; color: #666;")
            section.set_content_widget(placeholder)

    def _load_tags_section(self):
        """Load Tags section content. TODO: Phase 3"""
        section = self.sections.get("tags")
        if section:
            placeholder = QLabel("Tags content coming in Phase 3...")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 20px; color: #666;")
            section.set_content_widget(placeholder)

    def _load_branches_section(self):
        """Load Branches section content. TODO: Phase 3"""
        section = self.sections.get("branches")
        if section:
            placeholder = QLabel("Branches content coming in Phase 3...")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 20px; color: #666;")
            section.set_content_widget(placeholder)

    def _load_quick_section(self):
        """Load Quick Dates section content. TODO: Phase 3"""
        section = self.sections.get("quick")
        if section:
            placeholder = QLabel("Quick dates content coming in Phase 3...")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 20px; color: #666;")
            section.set_content_widget(placeholder)

    def set_project(self, project_id: int | None):
        """Update project and refresh all sections."""
        self._dbg(f"Setting project: {project_id}")
        self.project_id = project_id
        self.refresh_all(force=True)

    def refresh_all(self, force=False):
        """Refresh all sections (reload content)."""
        self._dbg(f"Refreshing all sections (force={force})")

        # Reload currently expanded section
        if self.expanded_section_id:
            self._load_section_content(self.expanded_section_id)

    def get_section(self, section_id: str) -> AccordionSection:
        """Get a specific section by ID."""
        return self.sections.get(section_id)


# For backward compatibility and testing
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Test the accordion sidebar
    sidebar = AccordionSidebar(project_id=1)
    sidebar.setMinimumWidth(300)
    sidebar.resize(350, 600)
    sidebar.show()

    sys.exit(app.exec())
