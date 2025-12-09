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
    QTableWidget, QTableWidgetItem, QHeaderView, QGridLayout, QLayout, QMenu, QMessageBox, QInputDialog
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QSize, QThreadPool, QRect, QPoint, QMimeData
from PySide6.QtGui import QFont, QIcon, QColor, QPixmap, QPainter, QPainterPath, QDrag, QImage
from datetime import datetime
import threading
import traceback
import time
import io

# Import database and UI components
from reference_db import ReferenceDB
from services.tag_service import get_tag_service
from translation_manager import tr


class FlowLayout(QLayout):
    """
    Flow layout that arranges items left-to-right, wrapping to next row when needed.
    Perfect for grid views where items should flow naturally.

    Based on Qt's Flow Layout example, adapted for sidebar people grid.
    """
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margin, _, _, _ = self.getContentsMargins()
        size += QSize(2 * margin, 2 * margin)
        return size

    def _do_layout(self, rect, test_only):
        """Arrange items in flow layout."""
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self.itemList:
            widget = item.widget()
            space_x = spacing + widget.style().layoutSpacing(
                QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal
            )
            space_y = spacing + widget.style().layoutSpacing(
                QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Vertical
            )

            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()


class PersonCard(QWidget):
    """
    Single person card with circular face thumbnail and name.

    Features:
    - 80x100px compact card size
    - Circular face thumbnail (64px diameter)
    - Name label (truncated if long)
    - Photo count badge
    - Hover effect
    - Click to filter by person
    - Context menu for rename/merge/delete
    - Drag-and-drop merge support
    """
    clicked = Signal(str)  # Emits branch_key when clicked
    context_menu_requested = Signal(str, str)  # Emits (branch_key, action)
    drag_merge_requested = Signal(str, str)  # Emits (source_branch, target_branch)

    def __init__(self, branch_key, display_name, face_pixmap, photo_count, parent=None):
        """
        Args:
            branch_key: Unique identifier for this person (e.g., "cluster_0")
            display_name: Human-readable name to display (e.g., "John" or "Unnamed")
            face_pixmap: QPixmap with face thumbnail
            photo_count: Number of photos with this person
        """
        super().__init__(parent)
        self.branch_key = branch_key
        self.display_name = display_name
        self.person_name = branch_key  # Keep for backward compatibility
        self.setFixedSize(80, 100)
        self.setCursor(Qt.PointingHandCursor)

        # Enable drag-and-drop
        self.setAcceptDrops(True)

        self.setStyleSheet("""
            PersonCard {
                background: transparent;
                border-radius: 6px;
            }
            PersonCard:hover {
                background: rgba(26, 115, 232, 0.08);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        # Circular face thumbnail
        self.face_label = QLabel()
        if face_pixmap and not face_pixmap.isNull():
            # Make circular mask
            circular_pixmap = self._make_circular(face_pixmap, 64)
            self.face_label.setPixmap(circular_pixmap)
        else:
            # Placeholder if no face image
            self.face_label.setPixmap(QPixmap())
            self.face_label.setFixedSize(64, 64)
            self.face_label.setStyleSheet("""
                QLabel {
                    background: #e8eaed;
                    border-radius: 32px;
                    font-size: 24pt;
                }
            """)
            self.face_label.setText("👤")
            self.face_label.setAlignment(Qt.AlignCenter)

        self.face_label.setFixedSize(64, 64)
        self.face_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.face_label)

        # Name label
        self.name_label = QLabel(display_name if len(display_name) <= 10 else display_name[:9] + "…")
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(False)
        self.name_label.setStyleSheet("""
            QLabel {
                font-size: 9pt;
                color: #202124;
                font-weight: 500;
            }
        """)
        self.name_label.setToolTip(f"{display_name} ({photo_count} photos)")
        layout.addWidget(self.name_label)

        # Count badge with confidence icon
        conf = "✅" if photo_count >= 10 else ("⚠️" if photo_count >= 5 else "❓")
        self.count_label = QLabel(f"{conf} ({photo_count})")
        self.count_label.setAlignment(Qt.AlignCenter)
        self.count_label.setStyleSheet("""
            QLabel {
                font-size: 8pt;
                color: #5f6368;
            }
        """)
        layout.addWidget(self.count_label)

    def _make_circular(self, pixmap, size):
        """Convert pixmap to circular thumbnail."""
        # Scale to size while maintaining aspect ratio
        scaled = pixmap.scaled(
            size, size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )

        # Crop to square
        if scaled.width() > size or scaled.height() > size:
            x = (scaled.width() - size) // 2
            y = (scaled.height() - size) // 2
            scaled = scaled.copy(x, y, size, size)

        # Create circular mask
        output = QPixmap(size, size)
        output.fill(Qt.transparent)

        painter = QPainter(output)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Draw circle path
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)

        # Draw image
        painter.drawPixmap(0, 0, scaled)
        painter.end()

        return output

    def mousePressEvent(self, event):
        """Handle click and drag initiation on person card."""
        if event.button() == Qt.LeftButton:
            # Store drag start position for drag detection
            self.drag_start_pos = event.pos()
        elif event.button() == Qt.RightButton:
            # Show context menu
            self._show_context_menu(event.globalPos())

    def mouseMoveEvent(self, event):
        """Handle drag operation."""
        if not (event.buttons() & Qt.LeftButton):
            return
        if not hasattr(self, 'drag_start_pos'):
            return

        # Check if drag threshold exceeded
        from PySide6.QtWidgets import QApplication
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        # Start drag operation
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"person_branch:{self.branch_key}:{self.display_name}")
        drag.setMimeData(mime_data)

        # Create drag pixmap (semi-transparent face)
        if self.face_label.pixmap() and not self.face_label.pixmap().isNull():
            drag_pixmap = QPixmap(self.face_label.pixmap())
        else:
            # Create placeholder
            drag_pixmap = QPixmap(64, 64)
            drag_pixmap.fill(Qt.transparent)
            painter = QPainter(drag_pixmap)
            painter.drawText(drag_pixmap.rect(), Qt.AlignCenter, "👤")
            painter.end()

        drag.setPixmap(drag_pixmap)
        drag.setHotSpot(QPoint(32, 32))

        # Execute drag
        drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, event):
        """Handle click after mouse release (if not dragged)."""
        if event.button() == Qt.LeftButton:
            # Only emit click if we didn't drag
            if hasattr(self, 'drag_start_pos'):
                if (event.pos() - self.drag_start_pos).manhattanLength() < 5:
                    self.clicked.emit(self.branch_key)
                    print(f"[PersonCard] Clicked: {self.display_name} (branch: {self.branch_key})")
                delattr(self, 'drag_start_pos')

    def dragEnterEvent(self, event):
        """Handle drag enter (highlight as drop target)."""
        if event.mimeData().hasText() and event.mimeData().text().startswith("person_branch:"):
            # Extract source branch
            parts = event.mimeData().text().split(":")
            if len(parts) >= 2:
                source_branch = parts[1]
                # Don't allow dropping onto self
                if source_branch != self.branch_key:
                    event.acceptProposedAction()
                    self.setStyleSheet("""
                        PersonCard {
                            background: rgba(26, 115, 232, 0.2);
                            border: 2px dashed #1a73e8;
                            border-radius: 6px;
                        }
                    """)

    def dragLeaveEvent(self, event):
        """Handle drag leave (remove highlight)."""
        self.setStyleSheet("""
            PersonCard {
                background: transparent;
                border-radius: 6px;
            }
            PersonCard:hover {
                background: rgba(26, 115, 232, 0.08);
            }
        """)

    def dropEvent(self, event):
        """Handle drop (initiate merge)."""
        if event.mimeData().hasText() and event.mimeData().text().startswith("person_branch:"):
            parts = event.mimeData().text().split(":")
            if len(parts) >= 3:
                source_branch = parts[1]
                source_name = parts[2]

                # Confirm merge
                reply = QMessageBox.question(
                    self,
                    "Confirm Drag-Drop Merge",
                    f"🔄 Merge '{source_name}' into '{self.display_name}'?\n\n"
                    f"This will move all faces from '{source_name}' to '{self.display_name}'.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply == QMessageBox.Yes:
                    event.acceptProposedAction()
                    self.drag_merge_requested.emit(source_branch, self.branch_key)

                # Reset style
                self.setStyleSheet("""
                    PersonCard {
                        background: transparent;
                        border-radius: 6px;
                    }
                    PersonCard:hover {
                        background: rgba(26, 115, 232, 0.08);
                    }
                """)

    def _show_context_menu(self, global_pos):
        """Show context menu for rename/merge/delete."""
        menu = QMenu(self)

        # Rename action
        rename_action = menu.addAction("✏️ Rename Person")
        rename_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "rename"))

        # Merge action
        merge_action = menu.addAction("🔗 Merge with Another Person")
        merge_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "merge"))

        # View details action
        details_action = menu.addAction("👁️ View Details…")
        details_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "details"))

        menu.addSeparator()

        # Delete action
        delete_action = menu.addAction("🗑️ Delete Person")
        delete_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "delete"))

        menu.exec(global_pos)


class PeopleGridView(QWidget):
    """
    Grid view for displaying people with face thumbnails.

    Replaces tree view for better space utilization.
    Uses FlowLayout to arrange PersonCards in responsive grid.

    Features:
    - Flow layout (wraps to next row automatically)
    - Scrollable (can handle 100+ people)
    - Circular face thumbnails
    - Click to filter by person
    - Empty state message
    - Drag-and-drop merge support
    """
    person_clicked = Signal(str)  # Emits branch_key when clicked
    context_menu_requested = Signal(str, str)  # Emits (branch_key, action)
    drag_merge_requested = Signal(str, str)  # Emits (source_branch, target_branch)

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # CRITICAL FIX: Set minimum height so faces are visible (not tiny!)
        # With 80x100px cards + spacing, 3 rows = ~340px minimum
        self.scroll_area.setMinimumHeight(340)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
        """)

        # Container with flow layout
        self.grid_container = QWidget()
        self.flow_layout = FlowLayout(self.grid_container, margin=4, spacing=8)

        # Empty state label (hidden when people added)
        self.empty_label = QLabel("No people detected yet\n\nRun face detection to see people here")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("""
            QLabel {
                color: #5f6368;
                font-size: 10pt;
                padding: 20px;
            }
        """)
        self.empty_label.hide()

        # Add to scroll
        self.scroll_area.setWidget(self.grid_container)
        main_layout.addWidget(self.scroll_area)
        main_layout.addWidget(self.empty_label)

    def add_person(self, branch_key, display_name, face_pixmap, photo_count):
        """
        Add person to grid.

        Args:
            branch_key: Unique identifier (e.g., "cluster_0")
            display_name: Display name (e.g., "John" or "Unnamed")
            face_pixmap: Face thumbnail
            photo_count: Number of photos
        """
        card = PersonCard(branch_key, display_name, face_pixmap, photo_count)
        card.clicked.connect(self._on_person_clicked)
        card.context_menu_requested.connect(self._on_context_menu_requested)
        card.drag_merge_requested.connect(self._on_drag_merge_requested)
        self.flow_layout.addWidget(card)
        self.empty_label.hide()

    def _on_person_clicked(self, branch_key):
        """Forward person click signal."""
        self.person_clicked.emit(branch_key)

    def _on_context_menu_requested(self, branch_key, action):
        """Forward context menu request."""
        self.context_menu_requested.emit(branch_key, action)

    def _on_drag_merge_requested(self, source_branch, target_branch):
        """Forward drag-drop merge request."""
        self.drag_merge_requested.emit(source_branch, target_branch)

    def clear(self):
        """Remove all person cards."""
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.empty_label.show()

    def count(self):
        """Return number of people in grid."""
        return self.flow_layout.count()

    def sizeHint(self):
        """
        Return recommended size for the grid.

        Returns:
            QSize: Recommended size (width flexible, height based on content)
        """
        # Calculate based on number of cards and card size
        card_count = self.flow_layout.count()
        if card_count == 0:
            # Empty state - small height
            return QSize(200, 100)

        # Card size: 80x100px per PersonCard + spacing
        card_height = 100
        spacing = 8
        cards_per_row = 2  # Sidebar width ~240px / 80px cards = ~2 per row

        # Calculate rows needed
        rows = (card_count + cards_per_row - 1) // cards_per_row

        # Total height: rows * (card_height + spacing) + margins
        # Cap at 400px to allow scrolling for many faces
        content_height = min(rows * (card_height + spacing) + 20, 400)

        return QSize(200, content_height)


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
        layout.setContentsMargins(10, 6, 10, 6)
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
                    background-color: #e8f0fe;
                    border: none;
                    border-radius: 6px;
                }
                SectionHeader:hover {
                    background-color: #d2e3fc;
                }
            """)
        else:
            # Inactive state: Normal, default background, chevron right
            self.title_font.setBold(False)
            self.title_label.setFont(self.title_font)
            self.chevron_label.setText("▶")  # Right arrow
            self.setStyleSheet("""
                SectionHeader {
                    background-color: #f8f9fa;
                    border: 1px solid #e8eaed;
                    border-radius: 6px;
                }
                SectionHeader:hover {
                    background-color: #f1f3f4;
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
        layout.addWidget(self.header, stretch=0)

        # Content area (visible only when expanded)
        self.content_container = QWidget()
        self.content_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(0)

        # Scroll area for content (ONE scrollbar here)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.content_container)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVisible(False)  # Hidden by default
        self.scroll_area.setMinimumHeight(300)  # CRITICAL: Ensure minimum content height

        layout.addWidget(self.scroll_area, stretch=100)  # Takes all available space when expanded

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
            # Expanded: Allow vertical expansion and remove height constraints
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.setMaximumHeight(16777215)  # Remove any maximum height constraint
            self.setMinimumHeight(400)  # Ensure expanded section has substantial height
        else:
            # Collapsed: Fixed height (header only)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.setMaximumHeight(50)  # Compact header
            self.setMinimumHeight(50)

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
            # CRITICAL: Ensure widget has proper size policy for expansion
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            widget.setVisible(True)  # Ensure widget is visible
            self.content_layout.addWidget(widget, stretch=1)

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
        self.nav_buttons = {}  # section_id -> QPushButton

        self._dbg("AccordionSidebar __init__ started")

        # MAIN HORIZONTAL LAYOUT: [Vertical Nav Bar] | [Sections]
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === LEFT: Vertical Navigation Bar (MS Outlook style) ===
        nav_bar = QWidget()
        nav_bar.setFixedWidth(52)
        nav_bar.setStyleSheet("""
            QWidget {
                background: #ffffff;
                border-right: 1px solid #dadce0;
            }
        """)
        nav_layout = QVBoxLayout(nav_bar)
        nav_layout.setContentsMargins(6, 12, 6, 4)
        nav_layout.setSpacing(4)

        # Navigation buttons (will be created in _build_sections)
        self.nav_layout = nav_layout

        main_layout.addWidget(nav_bar)

        # === RIGHT: Container for all sections ===
        self.sections_container = QWidget()
        self.sections_container.setStyleSheet("""
            QWidget {
                background: #ffffff;
            }
        """)
        self.sections_layout = QVBoxLayout(self.sections_container)
        self.sections_layout.setContentsMargins(6, 6, 6, 6)
        self.sections_layout.setSpacing(3)  # Tighter spacing between sections

        main_layout.addWidget(self.sections_container, stretch=1)

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
        """Create all accordion sections AND vertical navigation buttons."""
        self._dbg("Building accordion sections...")

        # Define sections in priority order
        sections_config = [
            ("people",   "👥 People",      "👥"),
            ("videos",   "🎬 Videos",      "🎬"),
            ("dates",    "📅 By Date",     "📅"),
            ("folders",  "📁 Folders",     "📁"),
            ("tags",     "🏷️  Tags",       "🏷️"),
            ("branches", "🔀 Branches",    "🔀"),
            ("quick",    "⚡ Quick Dates", "⚡"),
        ]

        for section_id, title, icon in sections_config:
            # Create section
            section = AccordionSection(section_id, title, icon)
            section.expandRequested.connect(self.expand_section)

            self.sections[section_id] = section
            self.sections_layout.addWidget(section)

            # Create navigation button in vertical nav bar
            nav_btn = QPushButton(icon)
            nav_btn.setToolTip(title)
            nav_btn.setFixedSize(44, 44)
            nav_btn.setCursor(Qt.PointingHandCursor)
            nav_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    border-radius: 10px;
                    font-size: 20pt;
                }
                QPushButton:hover {
                    background: rgba(26, 115, 232, 0.10);
                }
                QPushButton:pressed {
                    background: rgba(26, 115, 232, 0.20);
                }
            """)
            nav_btn.clicked.connect(lambda checked, sid=section_id: self.expand_section(sid))

            self.nav_buttons[section_id] = nav_btn
            self.nav_layout.addWidget(nav_btn)

        # Add stretch at the end of nav bar only
        self.nav_layout.addStretch()
        # NO stretch in sections_layout - will be managed by _reorder_sections()

        self._dbg(f"Created {len(self.sections)} sections with nav buttons")

    def expand_section(self, section_id: str):
        """
        Expand one section to full height, collapse all others.
        This is the core accordion behavior.

        Also updates vertical navigation bar button highlighting.
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

        # Update navigation button highlighting
        self._update_nav_buttons(section_id)

        # Reorder sections: expanded on top, collapsed at bottom
        self._reorder_sections()

        # Load content if needed
        self._load_section_content(section_id)

        self._dbg(f"✓ Section expanded: {section_id}")

    def _update_nav_buttons(self, active_section_id: str):
        """Update navigation button styles to highlight active section."""
        for sid, btn in self.nav_buttons.items():
            if sid == active_section_id:
                # Highlight active button with Google blue accent
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(26, 115, 232, 0.20);
                        border: none;
                        border-radius: 10px;
                        font-size: 20pt;
                    }
                    QPushButton:hover {
                        background: rgba(26, 115, 232, 0.30);
                    }
                """)
            else:
                # Reset inactive buttons
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: none;
                        border-radius: 10px;
                        font-size: 20pt;
                    }
                    QPushButton:hover {
                        background: rgba(26, 115, 232, 0.10);
                    }
                    QPushButton:pressed {
                        background: rgba(26, 115, 232, 0.20);
                    }
                """)

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

        # Add expanded section first (with HIGH stretch to take maximum height)
        if self.expanded_section_id:
            expanded_section = self.sections[self.expanded_section_id]
            self.sections_layout.addWidget(expanded_section, stretch=100)

        # Add collapsed sections (no stretch, fixed size)
        for section_id, section in self.sections.items():
            if section_id != self.expanded_section_id:
                self.sections_layout.addWidget(section, stretch=0)

        # NO stretch spacer at the end - let collapsed sections sit at bottom naturally

    def _load_section_content(self, section_id: str):
        """Load content for the specified section."""
        self._dbg(f"Loading content for section: {section_id}")

        if section_id == "people":
            self._load_people_section()
        elif section_id == "videos":
            self._load_videos_section()
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

    def reload_section(self, section_id: str):
        """
        Public method to reload a specific section's content.

        This is useful for refreshing the sidebar after:
        - Photo scanning completes
        - Face detection finishes
        - Tags are added/modified
        - Folders are reorganized

        Args:
            section_id: Section to reload ("people", "dates", "folders", "tags", "branches", "quick")
        """
        self._dbg(f"Reloading section: {section_id}")
        if section_id in self.sections:
            self._load_section_content(section_id)
        else:
            self._dbg(f"⚠️ Section '{section_id}' not found")

    def reload_all_sections(self):
        """
        Reload all sections in the sidebar.

        This is useful for refreshing the entire sidebar after major operations
        like bulk photo imports or database migrations.
        """
        self._dbg("Reloading all sections...")
        for section_id in self.sections.keys():
            self._load_section_content(section_id)

    def _load_people_section(self):
        """Load People/Face Clusters section content with flow grid layout and full features."""
        self._dbg("Loading People section...")

        section = self.sections.get("people")
        if not section or not self.project_id:
            return

        try:
            # Load face cluster data from database
            rows = self.db.get_face_clusters(self.project_id)
            self._dbg(f"Loaded {len(rows)} face clusters")

            # Create PeopleGridView
            people_grid = PeopleGridView()

            # Connect signals
            people_grid.person_clicked.connect(self._on_person_clicked)
            people_grid.context_menu_requested.connect(self._on_person_context_menu)
            people_grid.drag_merge_requested.connect(self._on_person_drag_merge)

            if len(rows) == 0:
                # Empty state is handled by PeopleGridView
                section.set_content_widget(people_grid)
                section.set_count(0)
                return

            # Add each person to the grid
            for idx, row in enumerate(rows):
                # CRITICAL FIX: Use correct column names from database
                branch_key = row[0] if isinstance(row, tuple) else row.get("branch_key", f"cluster_{idx}")
                display_name = row[1] if isinstance(row, tuple) else row.get("display_name", f"Person {idx + 1}")
                member_count = row[2] if isinstance(row, tuple) else row.get("member_count", 1)
                rep_path = row[3] if isinstance(row, tuple) else row.get("rep_path")
                rep_thumb_png = row[4] if isinstance(row, tuple) else row.get("rep_thumb_png")

                # Load face thumbnail
                face_pixmap = self._load_face_thumbnail(rep_path, rep_thumb_png)

                # Add to grid
                people_grid.add_person(branch_key, display_name, face_pixmap, member_count)

            # Update count badge
            section.set_count(len(rows))

            # Set as content widget
            section.set_content_widget(people_grid)

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

    def _load_face_thumbnail(self, rep_path: str, rep_thumb_png: bytes) -> QPixmap:
        """
        Load face thumbnail from rep_path or rep_thumb_png BLOB with circular masking.

        Args:
            rep_path: Path to representative face crop image
            rep_thumb_png: PNG thumbnail as BLOB data

        Returns:
            QPixmap with face thumbnail, or None if unavailable
        """
        try:
            from PIL import Image
            import os

            FACE_ICON_SIZE = 64

            # Try loading from BLOB first (faster, already in DB)
            if rep_thumb_png:
                try:
                    # Load from BLOB
                    image_data = io.BytesIO(rep_thumb_png)
                    with Image.open(image_data) as img:
                        # Convert to QPixmap
                        img_rgb = img.convert('RGB')
                        data = img_rgb.tobytes('raw', 'RGB')
                        qimg = QImage(data, img.width, img.height, QImage.Format_RGB888)
                        pixmap = QPixmap.fromImage(qimg)
                        return pixmap
                except Exception as blob_error:
                    self._dbg(f"Failed to load thumbnail from BLOB: {blob_error}")

            # Fallback: Try loading from file path
            if rep_path and os.path.exists(rep_path):
                try:
                    with Image.open(rep_path) as img:
                        # Convert to QPixmap
                        img_rgb = img.convert('RGB')
                        data = img_rgb.tobytes('raw', 'RGB')
                        qimg = QImage(data, img.width, img.height, QImage.Format_RGB888)
                        pixmap = QPixmap.fromImage(qimg)
                        return pixmap
                except Exception as file_error:
                    self._dbg(f"Failed to load thumbnail from {rep_path}: {file_error}")

            return None

        except Exception as e:
            self._dbg(f"Error in _load_face_thumbnail: {e}")
            return None

    def _on_person_clicked(self, branch_key: str):
        """Handle person card click - emit signal to filter grid."""
        self._dbg(f"Person clicked: {branch_key}")
        self.selectBranch.emit(f"branch:{branch_key}")

    def _on_person_context_menu(self, branch_key: str, action: str):
        """Handle person context menu actions."""
        self._dbg(f"Context menu action: {action} for {branch_key}")

        if action == "rename":
            self._handle_rename_person(branch_key)
        elif action == "merge":
            self._handle_merge_person(branch_key)
        elif action == "details":
            self._handle_person_details(branch_key)
        elif action == "delete":
            self._handle_delete_person(branch_key)

    def _on_person_drag_merge(self, source_branch: str, target_branch: str):
        """Handle drag-and-drop merge from People grid."""
        try:
            # Get source name for confirmation feedback
            with self.db._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT label FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                    (self.project_id, source_branch)
                )
                row = cur.fetchone()
                source_name = row[0] if row and row[0] else source_branch

            self._dbg(f"Drag-drop merge: {source_name} -> {target_branch}")

            # Perform merge (you need to implement this in your main layout)
            # For now, just show a message
            QMessageBox.information(
                None,
                "Merge Initiated",
                f"✅ Merging {source_name} into {target_branch}\n\n"
                f"This feature requires integration with your main layout's merge handler."
            )

            # Reload people section to reflect changes
            self._load_people_section()

        except Exception as e:
            self._dbg(f"Drag-drop merge failed: {e}")
            import traceback
            traceback.print_exc()

    def _handle_rename_person(self, branch_key: str):
        """Handle rename person action."""
        # Get current name
        with self.db._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT label FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                (self.project_id, branch_key)
            )
            row = cur.fetchone()
            current_name = row[0] if row and row[0] else branch_key

        # Show input dialog
        new_name, ok = QInputDialog.getText(
            None,
            "Rename Person",
            f"Enter new name for '{current_name}':",
            text=current_name
        )

        if ok and new_name and new_name != current_name:
            try:
                # Update in database
                with self.db._connect() as conn:
                    conn.execute(
                        "UPDATE face_branch_reps SET label = ? WHERE project_id = ? AND branch_key = ?",
                        (new_name, self.project_id, branch_key)
                    )
                    conn.commit()

                self._dbg(f"Renamed {current_name} to {new_name}")

                # Reload people section
                self._load_people_section()

                QMessageBox.information(
                    None,
                    "Rename Successful",
                    f"✅ Renamed '{current_name}' to '{new_name}'"
                )

            except Exception as e:
                self._dbg(f"Rename failed: {e}")
                QMessageBox.critical(None, "Rename Failed", f"Error: {e}")

    def _handle_merge_person(self, branch_key: str):
        """Handle merge person action."""
        QMessageBox.information(
            None,
            "Merge Person",
            f"Merge functionality for {branch_key}\n\n"
            f"Use drag-and-drop to merge: drag one person card onto another."
        )

    def _handle_person_details(self, branch_key: str):
        """Handle view person details action."""
        # Get person details from database
        with self.db._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT label, count, rep_path FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                (self.project_id, branch_key)
            )
            row = cur.fetchone()

        if row:
            name = row[0] or "Unnamed"
            count = row[1] or 0
            rep_path = row[2] or "None"

            QMessageBox.information(
                None,
                "Person Details",
                f"👤 {name}\n\n"
                f"Branch Key: {branch_key}\n"
                f"Photo Count: {count}\n"
                f"Representative Path: {rep_path}"
            )

    def _handle_delete_person(self, branch_key: str):
        """Handle delete person action."""
        # Get person name
        with self.db._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT label FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                (self.project_id, branch_key)
            )
            row = cur.fetchone()
            person_name = row[0] if row and row[0] else branch_key

        # Confirm deletion
        reply = QMessageBox.question(
            None,
            "Confirm Delete",
            f"🗑️ Delete '{person_name}'?\n\n"
            f"This will remove this person and all associated face data.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # Delete from database
                with self.db._connect() as conn:
                    conn.execute(
                        "DELETE FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                        (self.project_id, branch_key)
                    )
                    conn.commit()

                self._dbg(f"Deleted person: {person_name}")

                # Reload people section
                self._load_people_section()

                QMessageBox.information(
                    None,
                    "Delete Successful",
                    f"✅ Deleted '{person_name}'"
                )

            except Exception as e:
                self._dbg(f"Delete failed: {e}")
                QMessageBox.critical(None, "Delete Failed", f"Error: {e}")

    def _make_circular_pixmap(self, pixmap: QPixmap, size: int) -> QPixmap:
        """Create a circular pixmap from a square one."""
        from PySide6.QtGui import QPainter, QPainterPath

        scaled = pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        circular = QPixmap(size, size)
        circular.fill(Qt.transparent)

        painter = QPainter(circular)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)

        x_offset = (scaled.width() - size) // 2
        y_offset = (scaled.height() - size) // 2
        painter.drawPixmap(-x_offset, -y_offset, scaled)
        painter.end()

        return circular

    def _on_person_activated(self, branch_key: str):
        """Handle person click - emit signal to filter grid."""
        self._dbg(f"Person activated: {branch_key}")
        # Emit branch selection signal for grid filtering
        self.selectBranch.emit(f"branch:{branch_key}")

    def _load_videos_section(self):
        """Load Videos section with hierarchical tree (based on previous working version)."""
        self._dbg("Loading Videos section...")

        section = self.sections.get("videos")
        if not section or not self.project_id:
            self._dbg(f"⚠️ Section or project_id missing: section={section}, project_id={self.project_id}")
            return

        try:
            # Use VideoService to get videos (as in previous working version)
            from services.video_service import VideoService
            video_service = VideoService()

            self._dbg(f"Fetching videos for project_id={self.project_id}")
            videos = video_service.get_videos_by_project(self.project_id) if self.project_id else []
            total_videos = len(videos)
            self._dbg(f"Loaded {total_videos} videos from VideoService")

            # DEBUG: Check database directly if VideoService returns 0
            if total_videos == 0:
                self._dbg("⚠️ VideoService returned empty - checking database directly...")
                try:
                    with self.db._connect() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT COUNT(*) FROM video_metadata WHERE project_id = ?", (self.project_id,))
                        count = cur.fetchone()[0]
                        self._dbg(f"Direct query: video_metadata has {count} rows for project {self.project_id}")

                        if count > 0:
                            cur.execute("SELECT id, path, metadata_status, project_id FROM video_metadata WHERE project_id = ? LIMIT 3", (self.project_id,))
                            samples = cur.fetchall()
                            for sample in samples:
                                self._dbg(f"Sample video in DB: id={sample[0]}, path={sample[1]}, status={sample[2]}, project={sample[3]}")
                except Exception as db_err:
                    self._dbg(f"Database check failed: {db_err}")
                    import traceback
                    traceback.print_exc()

            if total_videos == 0:
                # Show "No videos" placeholder
                placeholder = QLabel("No videos found.\n\nScan your repository to index videos.")
                placeholder.setAlignment(Qt.AlignCenter)
                placeholder.setStyleSheet("padding: 40px 20px; color: #666; font-size: 11pt;")
                section.set_content_widget(placeholder)
                section.set_count(0)
                return

            # Create tree widget for videos (like the previous version)
            tree = QTreeWidget()
            tree.setHeaderHidden(True)
            tree.setIndentation(12)
            tree.setMinimumHeight(200)
            tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            tree.setStyleSheet("""
                QTreeWidget {
                    background: white;
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                }
                QTreeWidget::item {
                    padding: 6px 4px;
                }
                QTreeWidget::item:hover {
                    background: #f5f5f5;
                }
                QTreeWidget::item:selected {
                    background: #e8f0fe;
                    color: #1a73e8;
                }
            """)

            # All Videos
            all_item = QTreeWidgetItem([f"📁 All Videos ({total_videos})"])
            all_item.setData(0, Qt.UserRole, {"type": "all_videos"})
            tree.addTopLevelItem(all_item)

            # By Duration
            short_videos = [v for v in videos if v.get('duration_seconds') and v['duration_seconds'] < 30]
            medium_videos = [v for v in videos if v.get('duration_seconds') and 30 <= v['duration_seconds'] < 300]
            long_videos = [v for v in videos if v.get('duration_seconds') and v['duration_seconds'] >= 300]

            if short_videos or medium_videos or long_videos:
                duration_parent = QTreeWidgetItem(["⏱️  By Duration"])
                tree.addTopLevelItem(duration_parent)

                if short_videos:
                    short_item = QTreeWidgetItem([f"  Short < 30s ({len(short_videos)})"])
                    short_item.setData(0, Qt.UserRole, {"type": "duration", "key": "short", "videos": short_videos})
                    duration_parent.addChild(short_item)

                if medium_videos:
                    medium_item = QTreeWidgetItem([f"  Medium 30s-5m ({len(medium_videos)})"])
                    medium_item.setData(0, Qt.UserRole, {"type": "duration", "key": "medium", "videos": medium_videos})
                    duration_parent.addChild(medium_item)

                if long_videos:
                    long_item = QTreeWidgetItem([f"  Long > 5m ({len(long_videos)})"])
                    long_item.setData(0, Qt.UserRole, {"type": "duration", "key": "long", "videos": long_videos})
                    duration_parent.addChild(long_item)

            # By Resolution
            sd_videos = [v for v in videos if v.get('width') and v.get('height') and v['height'] < 720]
            hd_videos = [v for v in videos if v.get('width') and v.get('height') and 720 <= v['height'] < 1080]
            fhd_videos = [v for v in videos if v.get('width') and v.get('height') and 1080 <= v['height'] < 2160]
            uhd_videos = [v for v in videos if v.get('width') and v.get('height') and v['height'] >= 2160]

            if sd_videos or hd_videos or fhd_videos or uhd_videos:
                res_parent = QTreeWidgetItem(["📺 By Resolution"])
                tree.addTopLevelItem(res_parent)

                if sd_videos:
                    sd_item = QTreeWidgetItem([f"  SD < 720p ({len(sd_videos)})"])
                    sd_item.setData(0, Qt.UserRole, {"type": "resolution", "key": "sd", "videos": sd_videos})
                    res_parent.addChild(sd_item)

                if hd_videos:
                    hd_item = QTreeWidgetItem([f"  HD 720p ({len(hd_videos)})"])
                    hd_item.setData(0, Qt.UserRole, {"type": "resolution", "key": "hd", "videos": hd_videos})
                    res_parent.addChild(hd_item)

                if fhd_videos:
                    fhd_item = QTreeWidgetItem([f"  Full HD 1080p ({len(fhd_videos)})"])
                    fhd_item.setData(0, Qt.UserRole, {"type": "resolution", "key": "fhd", "videos": fhd_videos})
                    res_parent.addChild(fhd_item)

                if uhd_videos:
                    uhd_item = QTreeWidgetItem([f"  4K 2160p+ ({len(uhd_videos)})"])
                    uhd_item.setData(0, Qt.UserRole, {"type": "resolution", "key": "4k", "videos": uhd_videos})
                    res_parent.addChild(uhd_item)

            # By Date (Year/Month hierarchy)
            try:
                video_hier = self.db.get_video_date_hierarchy(self.project_id) or {}

                if video_hier:
                    date_parent = QTreeWidgetItem(["📅 By Date"])
                    tree.addTopLevelItem(date_parent)

                    for year in sorted(video_hier.keys(), key=lambda y: int(str(y)), reverse=True):
                        year_count = self.db.count_videos_for_year(year, self.project_id)
                        year_item = QTreeWidgetItem([f"  {year} ({year_count})"])
                        year_item.setData(0, Qt.UserRole, {"type": "video_year", "year": year})
                        date_parent.addChild(year_item)

                        # Month nodes under year
                        months = video_hier[year]
                        for month in sorted(months.keys(), key=lambda m: int(str(m))):
                            month_label = f"{int(month):02d}"
                            month_count = self.db.count_videos_for_month(year, month, self.project_id)
                            month_item = QTreeWidgetItem([f"    {month_label} ({month_count})"])
                            month_item.setData(0, Qt.UserRole, {"type": "video_month", "year": year, "month": month_label})
                            year_item.addChild(month_item)
            except Exception as e:
                self._dbg(f"Failed to build video date hierarchy: {e}")

            # Connect click handler
            tree.itemClicked.connect(self._on_video_tree_clicked)

            # Update count and set content
            section.set_count(total_videos)
            section.set_content_widget(tree)

            self._dbg(f"✓ Videos section loaded with {total_videos} videos")

        except Exception as e:
            self._dbg(f"⚠️ Error loading videos section: {e}")
            import traceback
            traceback.print_exc()

            # Show error placeholder
            error_label = QLabel(f"Error loading videos:\n{str(e)}")
            error_label.setAlignment(Qt.AlignCenter)
            error_label.setStyleSheet("padding: 20px; color: #ff0000;")
            section.set_content_widget(error_label)

    def _on_video_tree_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle video tree item click."""
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        item_type = data.get("type")
        self._dbg(f"Video tree item clicked: {item_type}")

        # For now, just log - can implement filtering later
        # self.selectBranch.emit(f"video:{item_type}")

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
        tree.setMinimumHeight(200)  # CRITICAL: Ensure tree is visible
        tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        tree.setMinimumHeight(200)  # CRITICAL: Ensure tree is visible
        tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        table.setMinimumHeight(200)  # CRITICAL: Ensure table is visible
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        table.setMinimumHeight(200)  # CRITICAL: Ensure table is visible
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        table.setMinimumHeight(200)  # CRITICAL: Ensure table is visible
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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

        # CRITICAL FIX: Reload ALL sections, not just the expanded one
        # This ensures all sections have fresh data after project changes
        for section_id in self.sections.keys():
            self._load_section_content(section_id)

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
