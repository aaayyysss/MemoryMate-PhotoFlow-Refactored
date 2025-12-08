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
    QScrollArea, QFrame, QSizePolicy, QTreeWidget, QTreeWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QSize, QThreadPool
from PySide6.QtGui import QFont, QIcon, QColor
from datetime import datetime
import threading
import traceback
import time

# Import database and UI components
from reference_db import ReferenceDB
from ui.people_list_view import PeopleListView
from services.tag_service import get_tag_service
from translation_manager import tr


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
        # CRITICAL FIX: If the widget is already in the layout, don't delete it
        # This prevents RuntimeError when reusing PeopleListView across reloads
        existing_widget = self.content_layout.itemAt(0).widget() if self.content_layout.count() > 0 else None

        if existing_widget is widget:
            # Widget is already set - no need to remove/re-add
            return

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

    # Internal signals for thread-safe UI updates
    _datesLoaded = Signal(dict)    # Thread → UI: dates data ready
    _foldersLoaded = Signal(list)  # Thread → UI: folders data ready
    _tagsLoaded = Signal(list)     # Thread → UI: tags data ready
    _branchesLoaded = Signal(list) # Thread → UI: branches data ready
    _quickLoaded = Signal(list)    # Thread → UI: quick dates data ready

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

        # Connect internal signals for thread-safe UI updates
        self._datesLoaded.connect(self._build_dates_tree, Qt.QueuedConnection)
        self._foldersLoaded.connect(self._build_folders_tree, Qt.QueuedConnection)
        self._tagsLoaded.connect(self._build_tags_table, Qt.QueuedConnection)
        self._branchesLoaded.connect(self._build_branches_table, Qt.QueuedConnection)
        self._quickLoaded.connect(self._build_quick_table, Qt.QueuedConnection)

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
        """Load By Date section with hierarchical tree (Year > Month > Day)."""
        self._dbg("Loading Dates section...")

        section = self.sections.get("dates")
        if not section or not self.project_id:
            return

        def work():
            try:
                # Get hierarchical date data: {year: {month: [days]}}
                hier = {}
                year_counts = {}

                if hasattr(self.db, "get_date_hierarchy"):
                    hier = self.db.get_date_hierarchy(self.project_id) or {}

                if hasattr(self.db, "list_years_with_counts"):
                    year_list = self.db.list_years_with_counts(self.project_id) or []
                    year_counts = {str(y): c for y, c in year_list}

                self._dbg(f"Loaded {len(hier)} years of date data")
                return {"hierarchy": hier, "year_counts": year_counts}
            except Exception as e:
                self._dbg(f"⚠️ Error loading dates: {e}")
                traceback.print_exc()
                return {"hierarchy": {}, "year_counts": {}}

        # Run in thread to avoid blocking UI (emit signal for thread-safe UI update)
        def on_complete():
            try:
                result = work()
                self._datesLoaded.emit(result)
            except Exception as e:
                self._dbg(f"⚠️ Error in dates thread: {e}")
                traceback.print_exc()

        threading.Thread(target=on_complete, daemon=True).start()

    def _build_dates_tree(self, result: dict):
        """Build dates tree widget from hierarchy data."""
        section = self.sections.get("dates")
        if not section:
            return

        hier = result.get("hierarchy", {})
        year_counts = result.get("year_counts", {})

        if not hier:
            placeholder = QLabel("No dates found")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 20px; color: #666;")
            section.set_content_widget(placeholder)
            return

        # Create tree widget: Years → Months → Days
        tree = QTreeWidget()
        tree.setHeaderLabels([tr('sidebar.header_year_month_day'), tr('sidebar.header_photos')])
        tree.setColumnCount(2)
        tree.setSelectionMode(QTreeWidget.SingleSelection)
        tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        tree.setAlternatingRowColors(True)
        tree.header().setStretchLastSection(False)
        tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tree.setStyleSheet("""
            QTreeWidget {
                border: none;
                background: transparent;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:hover {
                background: #f1f3f4;
            }
            QTreeWidget::item:selected {
                background: #e8f0fe;
                color: #1a73e8;
            }
        """)

        # Populate tree: Years (top level)
        month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        for year in sorted(hier.keys(), reverse=True):
            year_count = year_counts.get(str(year), 0)
            year_item = QTreeWidgetItem([str(year), str(year_count)])
            year_item.setData(0, Qt.UserRole, str(year))
            tree.addTopLevelItem(year_item)

            # Months (children of year)
            months_dict = hier[year]
            for month in sorted(months_dict.keys(), reverse=True):
                days_list = months_dict[month]
                month_num = int(month) if month.isdigit() else 0
                month_label = month_names[month_num] if 0 < month_num <= 12 else month

                # Get month count
                month_count = 0
                try:
                    if hasattr(self.db, "count_for_month"):
                        month_count = self.db.count_for_month(year, month)
                    else:
                        month_count = len(days_list)
                except Exception:
                    month_count = len(days_list)

                month_item = QTreeWidgetItem([f"{month_label} {year}", str(month_count)])
                month_item.setData(0, Qt.UserRole, f"{year}-{month}")
                year_item.addChild(month_item)

                # Days (children of month)
                for day in sorted(days_list, reverse=True):
                    day_count = 0
                    try:
                        if hasattr(self.db, "count_for_day"):
                            day_count = self.db.count_for_day(day, project_id=self.project_id)
                        else:
                            day_paths = self.db.get_images_by_date(day) if hasattr(self.db, "get_images_by_date") else []
                            day_count = len(day_paths) if day_paths else 0
                    except Exception:
                        day_count = 0

                    day_item = QTreeWidgetItem([str(day), str(day_count) if day_count > 0 else ""])
                    day_item.setData(0, Qt.UserRole, str(day))
                    month_item.addChild(day_item)

        # Connect double-click to emit date selection
        tree.itemDoubleClicked.connect(lambda item, col: self.selectDate.emit(item.data(0, Qt.UserRole)))

        # Update count badge
        section.set_count(len(hier))

        # Set as content widget
        section.set_content_widget(tree)

        self._dbg(f"✓ Dates section loaded with {len(hier)} years")

    def _load_folders_section(self):
        """Load Folders section with hierarchical tree structure."""
        self._dbg("Loading Folders section...")

        section = self.sections.get("folders")
        if not section or not self.project_id:
            return

        def work():
            try:
                # Get all folders for the project
                rows = self.db.get_all_folders(self.project_id) or []
                self._dbg(f"Loaded {len(rows)} folders")
                return rows
            except Exception as e:
                self._dbg(f"⚠️ Error loading folders: {e}")
                traceback.print_exc()
                return []

        # Run in thread to avoid blocking UI (emit signal for thread-safe UI update)
        def on_complete():
            try:
                rows = work()
                self._foldersLoaded.emit(rows)
            except Exception as e:
                self._dbg(f"⚠️ Error in folders thread: {e}")
                traceback.print_exc()

        threading.Thread(target=on_complete, daemon=True).start()

    def _build_folders_tree(self, rows: list):
        """Build folders tree widget from database data."""
        section = self.sections.get("folders")
        if not section:
            return

        # Create tree widget
        tree = QTreeWidget()
        tree.setHeaderLabels([tr('sidebar.header_folder'), tr('sidebar.header_photos')])
        tree.setColumnCount(2)
        tree.setSelectionMode(QTreeWidget.SingleSelection)
        tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        tree.setAlternatingRowColors(True)
        tree.header().setStretchLastSection(False)
        tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tree.setStyleSheet("""
            QTreeWidget {
                border: none;
                background: transparent;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:hover {
                background: #f1f3f4;
            }
            QTreeWidget::item:selected {
                background: #e8f0fe;
                color: #1a73e8;
            }
        """)

        # Build tree structure recursively
        try:
            self._add_folder_tree_items(tree, None)
        except Exception as e:
            self._dbg(f"⚠️ Error building folders tree: {e}")
            traceback.print_exc()

        if tree.topLevelItemCount() == 0:
            placeholder = QLabel("No folders found")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 20px; color: #666;")
            section.set_content_widget(placeholder)
            return

        # Connect double-click to emit folder selection
        tree.itemDoubleClicked.connect(
            lambda item, col: self.selectFolder.emit(item.data(0, Qt.UserRole)) if item.data(0, Qt.UserRole) else None
        )

        # Update count badge
        folder_count = self._count_tree_folders(tree)
        section.set_count(folder_count)

        # Set as content widget
        section.set_content_widget(tree)

        self._dbg(f"✓ Folders section loaded with {folder_count} folders")

    def _add_folder_tree_items(self, parent_widget_or_item, parent_id=None):
        """Recursively add folder items to QTreeWidget."""
        try:
            rows = self.db.get_child_folders(parent_id, project_id=self.project_id)
        except Exception as e:
            self._dbg(f"⚠️ get_child_folders({parent_id}) failed: {e}")
            return

        for row in rows:
            name = row["name"]
            fid = row["id"]

            # Get recursive photo count (includes subfolders)
            if hasattr(self.db, "get_image_count_recursive"):
                photo_count = int(self.db.get_image_count_recursive(fid) or 0)
            else:
                try:
                    folder_paths = self.db.get_images_by_folder(fid, project_id=self.project_id)
                    photo_count = len(folder_paths) if folder_paths else 0
                except Exception:
                    photo_count = 0

            # Create tree item with emoji prefix
            item = QTreeWidgetItem([f"📁 {name}", f"{photo_count:>5}"])
            item.setData(0, Qt.UserRole, int(fid))

            # Set count column formatting (right-aligned, grey color)
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            item.setForeground(1, QColor("#888888"))

            # Add to parent
            if isinstance(parent_widget_or_item, QTreeWidget):
                parent_widget_or_item.addTopLevelItem(item)
            else:
                parent_widget_or_item.addChild(item)

            # Recursively add child folders
            self._add_folder_tree_items(item, fid)

    def _count_tree_folders(self, tree):
        """Count total folders in tree."""
        count = 0
        def count_recursive(parent_item):
            nonlocal count
            for i in range(parent_item.childCount()):
                count += 1
                count_recursive(parent_item.child(i))

        for i in range(tree.topLevelItemCount()):
            count += 1
            count_recursive(tree.topLevelItem(i))
        return count

    def _load_tags_section(self):
        """Load Tags section with tag names and photo counts."""
        self._dbg("Loading Tags section...")

        section = self.sections.get("tags")
        if not section or not self.project_id:
            return

        def work():
            try:
                # Use TagService for proper layered architecture
                tag_service = get_tag_service()
                rows = tag_service.get_all_tags_with_counts(self.project_id) or []
                self._dbg(f"Loaded {len(rows)} tags")
                return rows
            except Exception as e:
                self._dbg(f"⚠️ Error loading tags: {e}")
                traceback.print_exc()
                return []

        # Run in thread to avoid blocking UI (emit signal for thread-safe UI update)
        def on_complete():
            try:
                rows = work()
                self._tagsLoaded.emit(rows)
            except Exception as e:
                self._dbg(f"⚠️ Error in tags thread: {e}")
                traceback.print_exc()

        threading.Thread(target=on_complete, daemon=True).start()

    def _build_tags_table(self, rows: list):
        """Build tags table widget from database data."""
        section = self.sections.get("tags")
        if not section:
            return

        # Process rows which can be: tuples (tag, count), dicts, or strings
        tag_items = []
        for r in (rows or []):
            if isinstance(r, tuple) and len(r) == 2:
                tag_name, count = r
                tag_items.append((tag_name, count))
            elif isinstance(r, dict):
                tag_name = r.get("tag") or r.get("name") or r.get("label")
                count = r.get("count", 0)
                if tag_name:
                    tag_items.append((tag_name, count))
            else:
                tag_name = str(r)
                if tag_name:
                    tag_items.append((tag_name, 0))

        if not tag_items:
            placeholder = QLabel("No tags found")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 20px; color: #666;")
            section.set_content_widget(placeholder)
            return

        # Create 2-column table: Tag | Photos
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels([tr('sidebar.tag'), tr('sidebar.header_photos')])
        table.setRowCount(len(tag_items))
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.setStyleSheet("""
            QTableWidget {
                border: none;
                background: transparent;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:hover {
                background: #f1f3f4;
            }
            QTableWidget::item:selected {
                background: #e8f0fe;
                color: #1a73e8;
            }
        """)

        for row, (tag_name, count) in enumerate(tag_items):
            # Column 0: Tag name
            item_name = QTableWidgetItem(tag_name)
            item_name.setData(Qt.UserRole, tag_name)
            table.setItem(row, 0, item_name)

            # Column 1: Count badge (right-aligned)
            count_str = str(count) if count else ""
            badge = QLabel(count_str)
            badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            badge.setStyleSheet("QLabel { background-color: #E8F4FD; color: #245; border: 1px solid #B3D9F2; border-radius: 10px; padding: 2px 6px; min-width: 24px; }")
            table.setCellWidget(row, 1, badge)

        # Connect double-click to emit tag selection
        table.cellDoubleClicked.connect(lambda row, col: self.selectTag.emit(table.item(row, 0).data(Qt.UserRole)))

        # Update count badge
        section.set_count(len(tag_items))

        # Set as content widget
        section.set_content_widget(table)

        self._dbg(f"✓ Tags section loaded with {len(tag_items)} tags")

    def _load_branches_section(self):
        """Load Branches section with branch list and member counts."""
        self._dbg("Loading Branches section...")

        section = self.sections.get("branches")
        if not section or not self.project_id:
            return

        def work():
            try:
                rows = self.db.get_branches(self.project_id) or []
                self._dbg(f"Loaded {len(rows)} branches")
                return rows
            except Exception as e:
                self._dbg(f"⚠️ Error loading branches: {e}")
                traceback.print_exc()
                return []

        # Run in thread to avoid blocking UI (emit signal for thread-safe UI update)
        def on_complete():
            try:
                rows = work()
                self._branchesLoaded.emit(rows)
            except Exception as e:
                self._dbg(f"⚠️ Error in branches thread: {e}")
                traceback.print_exc()

        threading.Thread(target=on_complete, daemon=True).start()

    def _build_branches_table(self, rows: list):
        """Build branches table widget from database data."""
        section = self.sections.get("branches")
        if not section:
            return

        # Normalize to [(key, name, count)]
        norm = []
        for r in (rows or []):
            count = None
            if isinstance(r, (tuple, list)) and len(r) >= 2:
                key, name = r[0], r[1]
                count = r[2] if len(r) >= 3 else None
            elif isinstance(r, dict):
                key = r.get("branch_key") or r.get("key") or r.get("id") or r.get("name")
                name = r.get("display_name") or r.get("label") or r.get("name") or str(key)
                count = r.get("count")
            else:
                key = name = str(r)
            if key is None:
                continue
            norm.append((str(key), str(name), count))

        if not norm:
            placeholder = QLabel("No branches found")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 20px; color: #666;")
            section.set_content_widget(placeholder)
            return

        # Create 2-column table: Branch/Folder | Photos
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Branch/Folder", "Photos"])
        table.setRowCount(len(norm))
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.setStyleSheet("""
            QTableWidget {
                border: none;
                background: transparent;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:hover {
                background: #f1f3f4;
            }
            QTableWidget::item:selected {
                background: #e8f0fe;
                color: #1a73e8;
            }
        """)

        for row, (key, name, count) in enumerate(norm):
            # Column 0: Branch name
            item_name = QTableWidgetItem(name)
            item_name.setData(Qt.UserRole, key)
            table.setItem(row, 0, item_name)

            # Column 1: Count (right-aligned, light grey)
            count_str = str(count) if count is not None else "0"
            item_count = QTableWidgetItem(count_str)
            item_count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item_count.setForeground(QColor("#BBBBBB"))
            table.setItem(row, 1, item_count)

        # Connect double-click to emit branch selection
        table.cellDoubleClicked.connect(lambda row, col: self.selectBranch.emit(table.item(row, 0).data(Qt.UserRole)))

        # Update count badge
        section.set_count(len(norm))

        # Set as content widget
        section.set_content_widget(table)

        self._dbg(f"✓ Branches section loaded with {len(norm)} branches")

    def _load_quick_section(self):
        """Load Quick Dates section with quick date shortcuts."""
        self._dbg("Loading Quick Dates section...")

        section = self.sections.get("quick")
        if not section:
            return

        def work():
            try:
                if hasattr(self.db, "get_quick_date_counts"):
                    rows = self.db.get_quick_date_counts() or []
                else:
                    # Fallback: simple list without counts
                    rows = [
                        {"key": "today", "label": "Today", "count": 0},
                        {"key": "this-week", "label": "This Week", "count": 0},
                        {"key": "this-month", "label": "This Month", "count": 0}
                    ]
                self._dbg(f"Loaded {len(rows)} quick date items")
                return rows
            except Exception as e:
                self._dbg(f"⚠️ Error loading quick dates: {e}")
                traceback.print_exc()
                return []

        # Run in thread to avoid blocking UI (emit signal for thread-safe UI update)
        def on_complete():
            try:
                rows = work()
                self._quickLoaded.emit(rows)
            except Exception as e:
                self._dbg(f"⚠️ Error in quick dates thread: {e}")
                traceback.print_exc()

        threading.Thread(target=on_complete, daemon=True).start()

    def _build_quick_table(self, rows: list):
        """Build quick dates table widget from database data."""
        section = self.sections.get("quick")
        if not section:
            return

        # Normalize rows to (key, label, count)
        quick_items = []
        for r in (rows or []):
            if isinstance(r, dict):
                key = r.get("key", "")
                label = r.get("label", "")
                count = r.get("count", 0)
                # Strip "date:" prefix from key if present
                if key.startswith("date:"):
                    key = key[5:]
                quick_items.append((key, label, count))
            elif isinstance(r, (tuple, list)) and len(r) >= 2:
                key, label = r[0], r[1]
                count = r[2] if len(r) >= 3 else 0
                quick_items.append((key, label, count))

        if not quick_items:
            placeholder = QLabel("No quick dates")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 20px; color: #666;")
            section.set_content_widget(placeholder)
            return

        # Create 2-column table: Period | Photos
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Period", "Photos"])
        table.setRowCount(len(quick_items))
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.setStyleSheet("""
            QTableWidget {
                border: none;
                background: transparent;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:hover {
                background: #f1f3f4;
            }
            QTableWidget::item:selected {
                background: #e8f0fe;
                color: #1a73e8;
            }
        """)

        for row, (key, label, count) in enumerate(quick_items):
            # Column 0: Period label
            item_name = QTableWidgetItem(label)
            item_name.setData(Qt.UserRole, key)
            table.setItem(row, 0, item_name)

            # Column 1: Count badge (right-aligned, light badge)
            badge = QLabel(str(count))
            badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            badge.setStyleSheet("QLabel { background-color: #F0F6FF; color: #456; border: 1px solid #C7DAF7; border-radius: 10px; padding: 2px 6px; min-width: 24px; }")
            table.setCellWidget(row, 1, badge)

        # Connect double-click to emit date selection
        table.cellDoubleClicked.connect(lambda row, col: self.selectDate.emit(table.item(row, 0).data(Qt.UserRole)))

        # Update count badge
        section.set_count(len(quick_items))

        # Set as content widget
        section.set_content_widget(table)

        self._dbg(f"✓ Quick dates section loaded with {len(quick_items)} items")

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
