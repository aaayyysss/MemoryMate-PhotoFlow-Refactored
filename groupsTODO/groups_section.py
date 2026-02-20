# ui/accordion_sidebar/groups_section.py
# Groups section - user-defined groups of people
# Version 1.0.0 dated 20260215

"""
GroupsSection - People Groups sub-section

Displays user-defined groups of 2+ people and allows users to find
photos where those people appear together.

Features:
- List of saved groups with member counts and result counts
- New group creation dialog
- Group selection to show matching photos
- Stale badge when results need refresh
- Recompute button for updating results
"""

import io
import logging
import threading
from typing import Optional, List, Dict

from PySide6.QtCore import Signal, Qt, QObject, QSize, QEvent
from PySide6.QtGui import QPixmap, QImage
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
    QFrame,
    QMenu,
)
from shiboken6 import isValid

from reference_db import ReferenceDB
from translation_manager import tr
from .base_section import BaseSection, SectionLoadSignals

logger = logging.getLogger(__name__)


class GroupsSectionSignals(QObject):
    """Signals for async groups loading."""
    loaded = Signal(int, list)  # (generation, groups_list)
    error = Signal(int, str)    # (generation, error_message)


class GroupsSection(BaseSection):
    """Groups section implementation showing user-defined people groups."""

    groupSelected = Signal(int, str)  # (group_id, match_mode)
    newGroupRequested = Signal()
    editGroupRequested = Signal(int)  # group_id
    deleteGroupRequested = Signal(int)  # group_id
    recomputeRequested = Signal(int, str)  # (group_id, match_mode)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = GroupsSectionSignals()
        self.signals.loaded.connect(self._on_data_loaded)
        self.signals.error.connect(self._on_error)

        # Keep reference to rendered cards
        self._cards: Dict[int, "GroupCard"] = {}
        self._header_widget: Optional[QWidget] = None

        # Search/filter state
        self._all_data: List[Dict] = []
        self._search_text: str = ""
        self._count_label: Optional[QLabel] = None
        self._selected_group_id: Optional[int] = None

    def get_section_id(self) -> str:
        return "groups"

    def get_title(self) -> str:
        return tr("sidebar.header_groups") if callable(tr) else "Groups"

    def get_icon(self) -> str:
        return "👥"

    def get_header_widget(self) -> Optional[QWidget]:
        """Provide compact controls beside the section title."""
        if self._header_widget:
            return self._header_widget

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        def build_btn(emoji: str, tooltip: str, callback):
            btn = QToolButton()
            btn.setText(emoji)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setAutoRaise(True)
            btn.setFixedSize(26, 26)
            btn.setToolTip(tooltip)
            btn.clicked.connect(callback)
            btn.setStyleSheet("""
                QToolButton {
                    border: 1px solid #dadce0;
                    border-radius: 6px;
                    background: #fff;
                }
                QToolButton:hover { background: #f1f3f4; }
                QToolButton:pressed { background: #e8f0fe; }
            """)
            layout.addWidget(btn)

        build_btn("➕", "Create New Group", self._on_new_group_clicked)
        build_btn("🔄", "Refresh Groups", lambda: self.load_section())

        self._header_widget = container
        return self._header_widget

    def _on_new_group_clicked(self):
        """Emit signal to request new group creation."""
        self.newGroupRequested.emit()

    def load_section(self) -> None:
        """Load groups section data in a background thread."""
        if not self.project_id:
            logger.warning("[GroupsSection] No project_id set")
            return

        self._generation += 1
        current_gen = self._generation
        self._loading = True

        logger.info(f"[GroupsSection] Loading groups (generation {current_gen})...")

        def work():
            db: Optional[ReferenceDB] = None
            try:
                db = ReferenceDB()

                # Import service here to avoid circular imports
                from services.people_group_service import PeopleGroupService
                service = PeopleGroupService(db)

                groups = service.get_all_groups(self.project_id)
                logger.info(f"[GroupsSection] Loaded {len(groups)} groups (gen {current_gen})")
                return groups
            except Exception as e:
                logger.error(f"[GroupsSection] Error loading groups: {e}")
                import traceback
                traceback.print_exc()
                return []
            finally:
                if db:
                    try:
                        db.close()
                    except Exception:
                        pass

        def on_complete():
            try:
                groups = work()
                self.signals.loaded.emit(current_gen, groups)
            except Exception as e:
                logger.error(f"[GroupsSection] Error in worker thread: {e}")
                import traceback
                traceback.print_exc()
                self.signals.error.emit(current_gen, str(e))

        threading.Thread(target=on_complete, daemon=True).start()

    def create_content_widget(self, data):
        """Create content widget for groups list."""
        groups: List[Dict] = data or []
        self._all_data = groups

        if not groups:
            # Empty state
            empty_container = QWidget()
            empty_layout = QVBoxLayout(empty_container)
            empty_layout.setContentsMargins(16, 32, 16, 32)
            empty_layout.setAlignment(Qt.AlignCenter)

            empty_icon = QLabel("👥")
            empty_icon.setStyleSheet("font-size: 48px;")
            empty_icon.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(empty_icon)

            empty_text = QLabel(
                "Create a group of people to find\nphotos of them together."
            )
            empty_text.setAlignment(Qt.AlignCenter)
            empty_text.setStyleSheet("color: #666; padding: 8px;")
            empty_layout.addWidget(empty_text)

            new_btn = QPushButton("➕ Create New Group")
            new_btn.setCursor(Qt.PointingHandCursor)
            new_btn.setStyleSheet("""
                QPushButton {
                    background: #1a73e8;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 20px;
                    font-weight: 600;
                }
                QPushButton:hover { background: #1557b0; }
                QPushButton:pressed { background: #104d97; }
            """)
            new_btn.clicked.connect(self.newGroupRequested.emit)
            empty_layout.addWidget(new_btn, alignment=Qt.AlignCenter)

            return empty_container

        # Main container with search and list
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
        search_input.setPlaceholderText("🔍 Search groups...")
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

        # "New Group" button (always visible when groups exist)
        new_group_btn = QPushButton("+ New Group")
        new_group_btn.setCursor(Qt.PointingHandCursor)
        new_group_btn.setStyleSheet("""
            QPushButton {
                background: #1a73e8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 10pt;
            }
            QPushButton:hover { background: #1557b0; }
            QPushButton:pressed { background: #104d97; }
        """)
        new_group_btn.clicked.connect(self.newGroupRequested.emit)
        main_layout.addWidget(new_group_btn)

        # Scroll area for groups list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        # Reset cache
        self._cards.clear()

        # Create group cards
        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(4, 4, 4, 4)
        list_layout.setSpacing(6)

        for group in groups:
            try:
                card = GroupCard(
                    group_id=group['id'],
                    display_name=group['display_name'],
                    member_count=group['member_count'],
                    result_count=group['result_count'],
                    is_stale=group['is_stale'],
                    icon=group.get('icon'),
                    match_mode=group.get('match_mode', 'together')
                )

                card.clicked.connect(self._on_group_clicked)
                card.contextMenuRequested.connect(self._on_group_context_menu)

                list_layout.addWidget(card)
                self._cards[group['id']] = card
            except Exception as e:
                logger.error(f"[GroupsSection] Failed to create card for group {group.get('id')}: {e}")

        list_layout.addStretch()
        scroll.setWidget(list_container)

        main_layout.addWidget(scroll, 1)

        logger.info(f"[GroupsSection] Created {len(self._cards)} group cards")
        return main_container

    def _on_search_changed(self, text: str):
        """Filter group cards based on search text."""
        self._search_text = text.strip().lower()
        visible_count = 0

        for group_id, card in self._cards.items():
            display_name = card.display_name.lower()
            is_match = self._search_text in display_name if self._search_text else True

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

    def _on_group_clicked(self, group_id: int):
        """Handle group card click."""
        # Toggle selection
        if self._selected_group_id == group_id:
            self._selected_group_id = None
            self.groupSelected.emit(-1, "")
        else:
            self._selected_group_id = group_id
            # Get match mode from card
            card = self._cards.get(group_id)
            match_mode = card.match_mode if card else 'together'
            self.groupSelected.emit(group_id, match_mode)

        # Update visual selection state
        for gid, card in self._cards.items():
            if isValid(card):
                card.setProperty("selected", gid == self._selected_group_id)
                card.style().unpolish(card)
                card.style().polish(card)

    def _on_group_context_menu(self, group_id: int, action: str):
        """Handle context menu action."""
        if action == "edit":
            self.editGroupRequested.emit(group_id)
        elif action == "delete":
            self.deleteGroupRequested.emit(group_id)
        elif action == "recompute_together":
            self.recomputeRequested.emit(group_id, "together")
        elif action == "recompute_event":
            self.recomputeRequested.emit(group_id, "event_window")

    def _on_error(self, generation: int, message: str):
        """Handle loading errors."""
        self._loading = False
        if generation != self._generation:
            return
        logger.error(f"[GroupsSection] Load error: {message}")

    def set_active_group(self, group_id: Optional[int]) -> None:
        """Highlight the active group card."""
        self._selected_group_id = group_id
        for gid, card in self._cards.items():
            if isValid(card):
                card.setProperty("selected", gid == group_id)
                card.style().unpolish(card)
                card.style().polish(card)


class GroupCard(QWidget):
    """Card widget representing a single group."""

    clicked = Signal(int)  # group_id
    contextMenuRequested = Signal(int, str)  # (group_id, action)

    def __init__(
        self,
        group_id: int,
        display_name: str,
        member_count: int,
        result_count: int,
        is_stale: bool,
        icon: Optional[str] = None,
        match_mode: str = 'together',
        parent=None
    ):
        super().__init__(parent)
        self.group_id = group_id
        self.display_name = display_name
        self.member_count = member_count
        self.result_count = result_count
        self.is_stale = is_stale
        self.match_mode = match_mode

        self.setMinimumHeight(60)
        self.setCursor(Qt.PointingHandCursor)

        # Main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Icon
        icon_label = QLabel(icon or "👥")
        icon_label.setStyleSheet("font-size: 24px;")
        icon_label.setFixedWidth(32)
        layout.addWidget(icon_label)

        # Info column
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # Name row with stale badge
        name_row = QHBoxLayout()
        name_row.setSpacing(6)

        name_label = QLabel(display_name)
        name_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #202124;")
        name_row.addWidget(name_label)

        if is_stale:
            stale_badge = QLabel("Stale")
            stale_badge.setStyleSheet("""
                background: #feefc3;
                color: #b06000;
                font-size: 9px;
                font-weight: 600;
                padding: 2px 6px;
                border-radius: 4px;
            """)
            name_row.addWidget(stale_badge)

        name_row.addStretch()
        info_layout.addLayout(name_row)

        # Stats row
        mode_text = "Together" if match_mode == "together" else "Same Event"
        stats_label = QLabel(f"{member_count} people • {result_count} photos • {mode_text}")
        stats_label.setStyleSheet("color: #5f6368; font-size: 10px;")
        info_layout.addWidget(stats_label)

        layout.addLayout(info_layout, 1)

        # Menu button
        menu_btn = QToolButton()
        menu_btn.setText("⋮")
        menu_btn.setAutoRaise(True)
        menu_btn.setFixedSize(24, 24)
        menu_btn.setStyleSheet("""
            QToolButton {
                color: #5f6368;
                font-size: 16px;
                border: none;
            }
            QToolButton:hover { background: #e8eaed; border-radius: 4px; }
        """)
        menu_btn.clicked.connect(self._show_context_menu)
        layout.addWidget(menu_btn)

        # Card styling
        self.setStyleSheet("""
            GroupCard {
                background: #fff;
                border: 1px solid #e8eaed;
                border-radius: 8px;
            }
            GroupCard:hover {
                background: #f8f9fa;
                border-color: #dadce0;
            }
            GroupCard[selected="true"] {
                background: #e8f0fe;
                border-color: #1a73e8;
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.group_id)
        super().mousePressEvent(event)

    def _show_context_menu(self):
        """Show context menu for group actions."""
        menu = QMenu(self)

        edit_action = menu.addAction("✏️ Edit Group")
        edit_action.triggered.connect(lambda: self.contextMenuRequested.emit(self.group_id, "edit"))

        menu.addSeparator()

        recompute_together = menu.addAction("🔄 Recompute (Together)")
        recompute_together.triggered.connect(
            lambda: self.contextMenuRequested.emit(self.group_id, "recompute_together")
        )

        recompute_event = menu.addAction("🔄 Recompute (Same Event)")
        recompute_event.triggered.connect(
            lambda: self.contextMenuRequested.emit(self.group_id, "recompute_event")
        )

        menu.addSeparator()

        delete_action = menu.addAction("🗑️ Delete Group")
        delete_action.triggered.connect(lambda: self.contextMenuRequested.emit(self.group_id, "delete"))

        menu.exec_(self.mapToGlobal(self.rect().bottomRight()))
