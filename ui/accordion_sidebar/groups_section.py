# ui/accordion_sidebar/groups_section.py
# Groups section - user-defined person groups for "Together (AND)" matching
# Version: 1.0.0

"""
GroupsSection - Groups sub-section under People

Displays user-defined groups of people with:
- Stacked circular avatars (member thumbnails)
- Group name and photo count
- "+ New Group" button
- Pinned groups at top

Based on:
- Apple Photos: People → Groups
- Google Photos: Face groups combination
- Existing PeopleSection pattern
"""

import io
import logging
import threading
from typing import Optional, List, Dict

from PySide6.QtCore import Signal, Qt, QObject, QSize, QRect, QPoint, QEvent
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QColor, QPen
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QSizePolicy,
    QToolButton,
    QLineEdit,
)
from shiboken6 import isValid

from translation_manager import tr
from .base_section import BaseSection

logger = logging.getLogger(__name__)


# ============================================================================
# SIGNALS
# ============================================================================

class GroupsSectionSignals(QObject):
    """Signals for async groups loading."""

    loaded = Signal(int, list)  # (generation, groups_data)
    error = Signal(int, str)    # (generation, error_message)


# ============================================================================
# GROUPS SECTION
# ============================================================================

class GroupsSection(BaseSection):
    """
    Groups section implementation showing user-defined person groups.

    This appears as a sub-section under People in the sidebar,
    displaying groups with stacked avatar thumbnails.
    """

    # UI action signals
    groupSelected = Signal(int)          # group_id
    createGroupRequested = Signal()      # Open create group dialog
    editGroupRequested = Signal(int)     # group_id
    deleteGroupRequested = Signal(int)   # group_id
    groupToolsRequested = Signal()       # Open groups tools

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = GroupsSectionSignals()
        self.signals.loaded.connect(self._on_data_loaded)
        self.signals.error.connect(self._on_error)

        # Cache of rendered cards
        self._cards: Dict[int, "GroupCard"] = {}
        self._header_widget: Optional[QWidget] = None

        # Search/filter state
        self._all_data: List[Dict] = []
        self._search_text: str = ""
        self._count_label: Optional[QLabel] = None

    def get_section_id(self) -> str:
        return "groups"

    def get_title(self) -> str:
        return tr("sidebar.header_groups") if callable(tr) else "Groups"

    def get_icon(self) -> str:
        return "👨‍👩‍👧‍👦"  # Family emoji for groups

    def get_header_widget(self) -> Optional[QWidget]:
        """Provide action buttons beside the section title."""
        if self._header_widget:
            return self._header_widget

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        def build_btn(text: str, tooltip_key: str, fallback: str, callback):
            btn = QToolButton()
            btn.setText(text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setAutoRaise(True)
            btn.setFixedSize(26, 26)
            btn.setToolTip(tr(tooltip_key) if callable(tr) else fallback)
            btn.clicked.connect(callback)
            btn.setStyleSheet(
                """
                QToolButton {
                    border: 1px solid #dadce0;
                    border-radius: 6px;
                    background: #fff;
                    font-size: 12px;
                }
                QToolButton:hover { background: #f1f3f4; }
                QToolButton:pressed { background: #e8f0fe; }
                """
            )
            layout.addWidget(btn)

        # + New Group button (primary action)
        build_btn("+", "sidebar.groups_actions.create", "Create New Group", self.createGroupRequested.emit)

        self._header_widget = container
        return self._header_widget

    def load_section(self) -> None:
        """Load groups in a background thread."""
        if not self.project_id:
            logger.warning("[GroupsSection] No project_id set")
            return

        self._generation += 1
        current_gen = self._generation
        self._loading = True

        logger.info(f"[GroupsSection] Loading groups (generation {current_gen})...")

        def work():
            try:
                from services.group_service import GroupService
                service = GroupService.instance()
                groups = service.get_groups(self.project_id)
                logger.info(f"[GroupsSection] Loaded {len(groups)} groups (gen {current_gen})")
                return groups
            except Exception as e:
                logger.error(f"[GroupsSection] Error loading groups: {e}", exc_info=True)
                return []

        def on_complete():
            try:
                groups = work()
                self.signals.loaded.emit(current_gen, groups)
            except Exception as e:
                logger.error(f"[GroupsSection] Error in worker thread: {e}", exc_info=True)
                self.signals.error.emit(current_gen, str(e))

        threading.Thread(target=on_complete, daemon=True).start()

    def create_content_widget(self, data):
        """Create a grid of group cards with search."""
        groups: List[Dict] = data or []
        self._all_data = groups

        if not groups:
            # Empty state with CTA
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setAlignment(Qt.AlignCenter)
            layout.setSpacing(16)

            empty_label = QLabel(tr("sidebar.groups.empty") if callable(tr) else "No groups yet")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("padding: 16px; color: #666; font-size: 12pt;")
            layout.addWidget(empty_label)

            hint_label = QLabel(
                tr("sidebar.groups.hint") if callable(tr)
                else "Create a group to see photos where multiple people appear together"
            )
            hint_label.setAlignment(Qt.AlignCenter)
            hint_label.setWordWrap(True)
            hint_label.setStyleSheet("padding: 8px; color: #888; font-size: 10pt;")
            layout.addWidget(hint_label)

            create_btn = QPushButton("+ Create Group")
            create_btn.setCursor(Qt.PointingHandCursor)
            create_btn.setStyleSheet("""
                QPushButton {
                    padding: 10px 24px;
                    border: none;
                    border-radius: 8px;
                    background: #1a73e8;
                    color: white;
                    font-size: 11pt;
                    font-weight: 600;
                }
                QPushButton:hover { background: #1557b0; }
                QPushButton:pressed { background: #0d47a1; }
            """)
            create_btn.clicked.connect(self.createGroupRequested.emit)
            layout.addWidget(create_btn, alignment=Qt.AlignCenter)

            return container

        # Main container with search and grid
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Search bar with count
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)

        search_input = QLineEdit()
        search_input.setPlaceholderText("Search groups...")
        search_input.setClearButtonEnabled(True)
        search_input.setStyleSheet("""
            QLineEdit {
                padding: 6px 10px;
                border: 1px solid #dadce0;
                border-radius: 6px;
                background: #fff;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 1px solid #1a73e8;
            }
        """)
        search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(search_input, 1)

        # Count label
        self._count_label = QLabel(f"{len(groups)} groups")
        self._count_label.setStyleSheet("color: #5f6368; font-size: 9pt; padding: 4px;")
        search_layout.addWidget(self._count_label)

        main_layout.addWidget(search_container)

        # Scroll area for groups grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)

        # Reset cache
        self._cards.clear()

        cards: List[GroupCard] = []

        for group in groups:
            try:
                group_id = group["id"]
                name = group["name"]
                photo_count = group.get("photo_count", 0)
                members = group.get("members", [])
                pinned = group.get("pinned", False)

                # Create stacked avatars from member thumbnails
                member_pixmaps = []
                for member in members[:4]:  # Max 4 avatars in stack
                    thumb = member.get("rep_thumb_png")
                    if thumb:
                        pixmap = self._load_thumbnail(thumb)
                        if pixmap:
                            member_pixmaps.append(pixmap)

                card = GroupCard(
                    group_id=group_id,
                    name=name,
                    photo_count=photo_count,
                    member_count=len(members),
                    member_pixmaps=member_pixmaps,
                    pinned=pinned
                )

                card.clicked.connect(self.groupSelected.emit)
                card.edit_requested.connect(self.editGroupRequested.emit)
                card.delete_requested.connect(self.deleteGroupRequested.emit)

                cards.append(card)
                self._cards[group_id] = card

            except Exception as e:
                logger.error(f"[GroupsSection] Failed to create card for group: {e}", exc_info=True)

        # Create grid
        grid_container = GroupsGrid(cards)
        grid_container.attach_viewport(scroll.viewport())
        scroll.setWidget(grid_container)

        main_layout.addWidget(scroll, 1)

        logger.info(f"[GroupsSection] Grid built with {len(cards)} groups")
        return main_container

    def _on_search_changed(self, text: str):
        """Filter group cards based on search text."""
        self._search_text = text.strip().lower()
        visible_count = 0

        for group_id, card in self._cards.items():
            name = card.name.lower()
            is_match = self._search_text in name if self._search_text else True

            if isValid(card):
                card.setVisible(is_match)
                if is_match:
                    visible_count += 1

        if self._count_label and isValid(self._count_label):
            total_count = len(self._cards)
            if self._search_text:
                self._count_label.setText(f"{visible_count} of {total_count} groups")
            else:
                self._count_label.setText(f"{total_count} groups")

    def _load_thumbnail(self, thumb_blob: bytes) -> Optional[QPixmap]:
        """Load thumbnail from PNG blob."""
        try:
            from PIL import Image

            image_data = io.BytesIO(thumb_blob)
            with Image.open(image_data) as img:
                img_rgb = img.convert("RGB")
                data = img_rgb.tobytes("raw", "RGB")
                qimg = QImage(data, img_rgb.width, img_rgb.height, img_rgb.width * 3, QImage.Format_RGB888)
                if qimg.isNull():
                    return None
                pixmap = QPixmap.fromImage(qimg)
                return pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception as e:
            logger.warning(f"[GroupsSection] Failed to load thumbnail: {e}")
            return None

    def _on_error(self, generation: int, message: str):
        """Handle loading errors."""
        self._loading = False
        if generation != self._generation:
            return
        logger.error(f"[GroupsSection] Load error: {message}")

    def set_active_group(self, group_id: Optional[int]) -> None:
        """Highlight the active group card."""
        try:
            for gid, card in self._cards.items():
                is_active = group_id is not None and gid == group_id
                card.setProperty("selected", is_active)
                card.style().unpolish(card)
                card.style().polish(card)
        except Exception:
            logger.debug("[GroupsSection] Failed to update active state", exc_info=True)


# ============================================================================
# GROUPS GRID
# ============================================================================

class GroupsGrid(QWidget):
    """Grid that automatically recalculates columns based on available width."""

    def __init__(self, cards: List["GroupCard"], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.cards = cards
        self._card_width = cards[0].sizeHint().width() if cards else 160
        self._columns = 0
        self._viewport = None
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setHorizontalSpacing(10)
        self._layout.setVerticalSpacing(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._relayout(force=True)

    def attach_viewport(self, viewport: QWidget) -> None:
        """Track the scroll viewport for responsive column count."""
        if not viewport:
            return
        self._viewport = viewport
        viewport.installEventFilter(self)
        self._relayout(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def eventFilter(self, obj, event):
        if obj is self._viewport and event.type() == QEvent.Resize:
            self._relayout(force=True)
        return super().eventFilter(obj, event)

    def _relayout(self, force: bool = False):
        margins = self._layout.contentsMargins()
        base_width = self._viewport.width() if self._viewport else self.width()
        available_width = max(base_width - margins.left() - margins.right(), 0)
        spacing = self._layout.horizontalSpacing() or 0
        columns = max(1, int(available_width / (self._card_width + spacing)) if (self._card_width + spacing) > 0 else 1)

        if not force and columns == self._columns:
            return

        self._columns = columns

        while self._layout.count():
            self._layout.takeAt(0)

        for idx, card in enumerate(self.cards):
            row = idx // columns
            col = idx % columns
            self._layout.addWidget(card, row, col)


# ============================================================================
# GROUP CARD
# ============================================================================

class GroupCard(QWidget):
    """
    Compact group card with stacked avatars.

    Visual design:
    - Stacked circular avatars (up to 4 members)
    - Group name (bold)
    - Photo count and member count
    - Pin indicator for pinned groups
    """

    clicked = Signal(int)           # group_id
    edit_requested = Signal(int)    # group_id
    delete_requested = Signal(int)  # group_id

    def __init__(
        self,
        group_id: int,
        name: str,
        photo_count: int,
        member_count: int,
        member_pixmaps: List[QPixmap],
        pinned: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.group_id = group_id
        self.name = name
        self.photo_count = photo_count
        self.member_count = member_count
        self.member_pixmaps = member_pixmaps
        self.pinned = pinned

        self.setFixedSize(150, 100)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        # Stacked avatars widget
        avatar_stack = self._create_stacked_avatars()
        layout.addWidget(avatar_stack, alignment=Qt.AlignCenter)

        # Group name with pin indicator
        name_text = f"{'📌 ' if pinned else ''}{name}"
        name_label = QLabel(name_text)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-weight: 600; font-size: 11px; color: #202124;")
        layout.addWidget(name_label)

        # Photo and member counts
        counts_label = QLabel(f"{photo_count} photos · {member_count} people")
        counts_label.setAlignment(Qt.AlignCenter)
        counts_label.setStyleSheet("color: #5f6368; font-size: 10px;")
        layout.addWidget(counts_label)

        self.setStyleSheet(
            """
            GroupCard {
                background: transparent;
                border-radius: 8px;
            }
            GroupCard:hover {
                background: rgba(26, 115, 232, 0.08);
            }
            GroupCard[selected="true"] {
                background: rgba(26, 115, 232, 0.12);
                border: 1px solid #1a73e8;
            }
            """
        )

    def _create_stacked_avatars(self) -> QLabel:
        """Create stacked circular avatars label."""
        AVATAR_SIZE = 32
        OVERLAP = 10
        MAX_AVATARS = 4

        pixmaps = self.member_pixmaps[:MAX_AVATARS]
        count = len(pixmaps)

        if count == 0:
            # Fallback: single emoji placeholder
            label = QLabel("👥")
            label.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(f"""
                background: #e8eaed;
                border-radius: {AVATAR_SIZE // 2}px;
                font-size: 20px;
            """)
            return label

        # Calculate total width needed
        total_width = AVATAR_SIZE + (count - 1) * (AVATAR_SIZE - OVERLAP)

        # Create composite pixmap
        result = QPixmap(total_width, AVATAR_SIZE)
        result.fill(Qt.transparent)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        for i, pixmap in enumerate(pixmaps):
            x_offset = i * (AVATAR_SIZE - OVERLAP)

            # Draw white border circle
            border_path = QPainterPath()
            border_path.addEllipse(x_offset, 0, AVATAR_SIZE, AVATAR_SIZE)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor("#ffffff"))
            painter.drawPath(border_path)

            # Clip to circle and draw avatar
            clip_path = QPainterPath()
            clip_path.addEllipse(x_offset + 1, 1, AVATAR_SIZE - 2, AVATAR_SIZE - 2)
            painter.setClipPath(clip_path)

            scaled = pixmap.scaled(AVATAR_SIZE - 2, AVATAR_SIZE - 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap(x_offset + 1, 1, scaled)

            painter.setClipping(False)

        # Draw member count badge if > 4 members
        if self.member_count > MAX_AVATARS:
            extra = self.member_count - MAX_AVATARS
            badge_x = total_width - 16
            badge_y = AVATAR_SIZE - 14

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#5f6368"))
            painter.drawEllipse(badge_x, badge_y, 14, 14)

            painter.setPen(QColor("#ffffff"))
            from PySide6.QtGui import QFont
            font = QFont()
            font.setPixelSize(9)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRect(badge_x, badge_y, 14, 14), Qt.AlignCenter, f"+{extra}")

        painter.end()

        label = QLabel()
        label.setFixedSize(total_width, AVATAR_SIZE)
        label.setPixmap(result)
        return label

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.group_id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Show context menu for edit/delete actions."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        menu = QMenu(self)

        edit_action = QAction(
            "✏️ " + (tr("sidebar.groups_actions.edit") if callable(tr) else "Edit Group"),
            self
        )
        edit_action.triggered.connect(lambda: self.edit_requested.emit(self.group_id))
        menu.addAction(edit_action)

        menu.addSeparator()

        delete_action = QAction(
            "🗑️ " + (tr("sidebar.groups_actions.delete") if callable(tr) else "Delete Group"),
            self
        )
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self.group_id))
        menu.addAction(delete_action)

        menu.exec_(event.globalPos())

    def sizeHint(self):
        return QSize(150, 100)
