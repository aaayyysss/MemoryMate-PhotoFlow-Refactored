# ui/accordion_sidebar/groups_section.py
# Groups sub-section under People - user-defined groups of face clusters
#
# Follows the same widget patterns as PeopleSection (PersonCard, PeopleGrid)
# but displays group tiles instead of individual person cards.

import io
import logging
import threading
import time
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Signal, Qt, QObject, QSize, QPoint, QEvent
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QPen, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from reference_db import ReferenceDB
from translation_manager import tr

logger = logging.getLogger(__name__)


# ======================================================================
# Signals for async loading
# ======================================================================

class GroupsSectionSignals(QObject):
    """Signals for async groups loading."""
    loaded = Signal(int, list)   # (generation, groups_list)
    error = Signal(int, str)     # (generation, error_message)


# ======================================================================
# GroupCard — card widget for a single group (horizontal info-dense layout)
# ======================================================================

class GroupCard(QWidget):
    """
    Card widget representing a single group.

    Horizontal layout following Google Photos / Lightroom pattern:
    - Left: Stacked circular face avatars (or fallback icon)
    - Center: Group name + stats row (members, photos, match mode)
    - Right: Context menu button (⋮)

    Supports stale badge, match mode display, and full context menu.
    """

    clicked = Signal(int)                      # group_id
    context_menu_requested = Signal(int, str)  # (group_id, action)

    def __init__(
        self,
        group_id: int,
        display_name: str,
        member_count: int,
        result_count: int,
        is_stale: bool = False,
        member_pixmaps: Optional[List[QPixmap]] = None,
        icon: Optional[str] = None,
        match_mode: str = "together",
        is_pinned: bool = False,
        cover_pixmap: Optional[QPixmap] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.group_id = group_id
        self.group_name = display_name
        self.display_name = display_name
        self.member_count = member_count
        self.result_count = result_count
        self.is_stale = is_stale
        self.match_mode = match_mode
        self.is_pinned = is_pinned

        self.setMinimumHeight(60)
        self.setCursor(Qt.PointingHandCursor)

        # Main layout: icon/avatars | info | menu
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # ── Left: Face avatars or fallback icon ──
        avatar_widget = self._build_avatar_area(member_pixmaps or [], icon)
        layout.addWidget(avatar_widget)

        # ── Center: Info column ──
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # Name row with optional badges
        name_row = QHBoxLayout()
        name_row.setSpacing(6)

        name_label = QLabel(display_name)
        name_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #202124;")
        name_row.addWidget(name_label)

        if is_pinned:
            pin_badge = QLabel("📌")
            pin_badge.setStyleSheet("font-size: 10px;")
            name_row.addWidget(pin_badge)

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
        stats_parts = []
        if member_count > 0:
            stats_parts.append(f"{member_count} people")
        if result_count >= 0:
            stats_parts.append(f"{result_count} photos")
        else:
            stats_parts.append("...")
        stats_parts.append(mode_text)
        stats_label = QLabel(" · ".join(stats_parts))
        stats_label.setStyleSheet("color: #5f6368; font-size: 10px;")
        info_layout.addWidget(stats_label)

        layout.addLayout(info_layout, 1)

        # ── Right: Menu button ──
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

    def _build_avatar_area(
        self, pixmaps: List[QPixmap], icon: Optional[str]
    ) -> QWidget:
        """Build the left area: stacked face avatars or fallback emoji icon."""
        container = QWidget()
        container.setFixedSize(56, 44)

        if pixmaps and any(p and not p.isNull() for p in pixmaps if p):
            # Stacked circular face avatars (Apple Photos / Google Photos style)
            label = QLabel(container)
            label.setFixedSize(container.size())

            avatar_size = 32
            overlap = 10
            max_show = min(len(pixmaps), 3)

            canvas = QPixmap(container.width(), container.height())
            canvas.fill(Qt.transparent)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.Antialiasing)

            for i in range(max_show):
                x = i * (avatar_size - overlap)
                y = (container.height() - avatar_size) // 2

                if i < len(pixmaps) and pixmaps[i] and not pixmaps[i].isNull():
                    scaled = pixmaps[i].scaled(
                        avatar_size, avatar_size,
                        Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
                    )
                    path = QPainterPath()
                    path.addEllipse(x, y, avatar_size, avatar_size)
                    painter.setClipPath(path)
                    painter.drawPixmap(x, y, scaled)
                    painter.setClipping(False)
                else:
                    painter.setBrush(QColor("#e8eaed"))
                    painter.setPen(QPen(QColor("#dadce0"), 1))
                    painter.drawEllipse(x, y, avatar_size, avatar_size)
                    painter.setPen(QColor("#5f6368"))
                    painter.setFont(QFont("", 12))
                    painter.drawText(x, y, avatar_size, avatar_size, Qt.AlignCenter, "?")

                # White border ring
                painter.setPen(QPen(QColor("white"), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(x, y, avatar_size, avatar_size)

            painter.end()
            label.setPixmap(canvas)
        else:
            # Fallback: emoji icon
            icon_label = QLabel(icon or "👥", container)
            icon_label.setStyleSheet("font-size: 24px;")
            icon_label.setFixedSize(container.size())
            icon_label.setAlignment(Qt.AlignCenter)

        return container

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.group_id)
        super().mousePressEvent(event)

    def _show_context_menu(self):
        """Show context menu for group actions."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)

        edit_action = menu.addAction("✏️ Edit Group")
        edit_action.triggered.connect(
            lambda: self.context_menu_requested.emit(self.group_id, "edit_members")
        )

        rename_action = menu.addAction("📝 Rename")
        rename_action.triggered.connect(
            lambda: self.context_menu_requested.emit(self.group_id, "rename")
        )

        pin_text = "📌 Unpin" if self.is_pinned else "📌 Pin to Top"
        pin_action = menu.addAction(pin_text)
        pin_action.triggered.connect(
            lambda: self.context_menu_requested.emit(self.group_id, "toggle_pin")
        )

        menu.addSeparator()

        recompute_together = menu.addAction("🔄 Recompute (Together)")
        recompute_together.triggered.connect(
            lambda: self.context_menu_requested.emit(self.group_id, "recompute_together")
        )

        recompute_event = menu.addAction("🔄 Recompute (Same Event)")
        recompute_event.triggered.connect(
            lambda: self.context_menu_requested.emit(self.group_id, "recompute_event")
        )

        menu.addSeparator()

        delete_action = menu.addAction("🗑️ Delete Group")
        delete_action.triggered.connect(
            lambda: self.context_menu_requested.emit(self.group_id, "delete")
        )

        menu.exec_(self.mapToGlobal(self.rect().bottomRight()))


# ======================================================================
# GroupsGrid — responsive grid of GroupCards
# ======================================================================

class GroupsGrid(QWidget):
    """Grid that automatically recalculates columns based on available width."""

    def __init__(self, cards: List[GroupCard], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.cards = cards
        self._card_width = cards[0].sizeHint().width() if cards else 110
        self._columns = 0
        self._viewport = None
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setHorizontalSpacing(8)
        self._layout.setVerticalSpacing(8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._relayout(force=True)

    def attach_viewport(self, viewport: QWidget) -> None:
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


# ======================================================================
# CreateGroupDialog — modal for creating/editing a group
# ======================================================================

class CreateGroupDialog(QDialog):
    """
    Dialog for creating or editing a people group.

    Shows a searchable list of all people in the project.
    User selects 2+ people, enters a name, and saves.
    """

    def __init__(
        self,
        project_id: int,
        existing_group: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.project_id = project_id
        self.existing_group = existing_group
        self._selected_branch_keys: List[str] = []
        self._people_data: List[Dict] = []

        self.setWindowTitle("Edit Group" if existing_group else "Create Group")
        self.setMinimumSize(400, 500)
        self.setModal(True)

        self._setup_ui()
        self._load_people()

        if existing_group:
            self._populate_existing()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Group name
        name_group = QWidget()
        name_layout = QHBoxLayout(name_group)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_label = QLabel("Group name:")
        name_label.setStyleSheet("font-weight: 600;")
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Family, Travel Buddies...")
        self._name_input.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px; border: 1px solid #dadce0;
                border-radius: 6px; font-size: 11pt;
            }
            QLineEdit:focus { border-color: #1a73e8; }
        """)
        name_layout.addWidget(name_label)
        name_layout.addWidget(self._name_input, 1)
        layout.addWidget(name_group)

        # Selected members chip area
        self._chips_label = QLabel("Selected: (none)")
        self._chips_label.setWordWrap(True)
        self._chips_label.setStyleSheet("color: #1a73e8; font-size: 10pt; padding: 4px;")
        layout.addWidget(self._chips_label)

        # Search people
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 Search people to add...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setStyleSheet("""
            QLineEdit {
                padding: 6px 10px; border: 1px solid #dadce0;
                border-radius: 6px; font-size: 10pt;
            }
            QLineEdit:focus { border-color: #1a73e8; }
        """)
        self._search_input.textChanged.connect(self._filter_people)
        layout.addWidget(self._search_input)

        # People list (multi-select)
        self._people_list = QListWidget()
        self._people_list.setSelectionMode(QListWidget.MultiSelection)
        self._people_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #dadce0; border-radius: 6px;
                font-size: 10pt; padding: 4px;
            }
            QListWidget::item { padding: 6px 8px; border-radius: 4px; }
            QListWidget::item:selected { background: #e8f0fe; color: #1a73e8; }
            QListWidget::item:hover { background: #f1f3f4; }
        """)
        self._people_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._people_list, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setStyleSheet("""
            QPushButton {
                padding: 8px 20px; border: 1px solid #dadce0;
                border-radius: 6px; background: white;
            }
            QPushButton:hover { background: #f1f3f4; }
        """)
        self._btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_cancel)

        self._btn_save = QPushButton("Create Group" if not self.existing_group else "Save Changes")
        self._btn_save.setEnabled(False)
        self._btn_save.setStyleSheet("""
            QPushButton {
                padding: 8px 20px; border: none; border-radius: 6px;
                background: #1a73e8; color: white; font-weight: 600;
            }
            QPushButton:hover { background: #1557b0; }
            QPushButton:disabled { background: #dadce0; color: #80868b; }
        """)
        self._btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(self._btn_save)

        layout.addLayout(btn_layout)

    def _load_people(self):
        """Load all people from the database."""
        try:
            db = ReferenceDB()
            rows = db.get_face_clusters(self.project_id) or []
            db.close()

            self._people_data = []
            for row in rows:
                if isinstance(row, dict):
                    bk = row.get("branch_key", "")
                    name = row.get("display_name", bk)
                    count = row.get("member_count", 0)
                else:
                    bk = row[0] if len(row) > 0 else ""
                    name = row[1] if len(row) > 1 else bk
                    count = row[2] if len(row) > 2 else 0

                # Skip unidentified cluster
                if bk == "face_unidentified":
                    continue

                self._people_data.append({
                    "branch_key": bk,
                    "display_name": name,
                    "count": count,
                })

            self._populate_list()
        except Exception as e:
            logger.error(f"[CreateGroupDialog] Failed to load people: {e}")

    def _populate_list(self, filter_text: str = ""):
        """Populate the list widget with people data."""
        self._people_list.clear()
        ft = filter_text.strip().lower()

        for p in self._people_data:
            name = p["display_name"]
            if ft and ft not in name.lower():
                continue

            item = QListWidgetItem(f"{name}  ({p['count']} photos)")
            item.setData(Qt.UserRole, p["branch_key"])
            self._people_list.addItem(item)

            # Re-select if was selected
            if p["branch_key"] in self._selected_branch_keys:
                item.setSelected(True)

    def _populate_existing(self):
        """Pre-fill dialog with existing group data."""
        if not self.existing_group:
            return
        self._name_input.setText(self.existing_group.get("name", ""))
        self._selected_branch_keys = [
            m["branch_key"] for m in self.existing_group.get("members", [])
        ]
        self._populate_list()
        self._update_chips()

    def _filter_people(self, text: str):
        self._populate_list(text)

    def _on_selection_changed(self):
        self._selected_branch_keys = []
        for item in self._people_list.selectedItems():
            bk = item.data(Qt.UserRole)
            if bk:
                self._selected_branch_keys.append(bk)
        self._update_chips()

    def _update_chips(self):
        """Update the selected members display and save button state."""
        if not self._selected_branch_keys:
            self._chips_label.setText("Selected: (none)")
            self._btn_save.setEnabled(False)
            return

        names = []
        for bk in self._selected_branch_keys:
            for p in self._people_data:
                if p["branch_key"] == bk:
                    names.append(p["display_name"])
                    break

        self._chips_label.setText(f"Selected ({len(names)}): {', '.join(names)}")
        self._btn_save.setEnabled(len(self._selected_branch_keys) >= 2)

        # Auto-suggest name if empty
        if not self._name_input.text().strip() and names:
            from services.group_service import GroupService
            self._name_input.setPlaceholderText(GroupService.suggest_group_name(names))

    def get_result(self) -> Dict[str, Any]:
        """Get the dialog result after accept."""
        name = self._name_input.text().strip()
        if not name:
            # Use auto-suggested name
            names = []
            for bk in self._selected_branch_keys:
                for p in self._people_data:
                    if p["branch_key"] == bk:
                        names.append(p["display_name"])
                        break
            from services.group_service import GroupService
            name = GroupService.suggest_group_name(names)

        return {
            "name": name,
            "branch_keys": list(self._selected_branch_keys),
        }


# ======================================================================
# GroupsSubsectionWidget — the main widget shown under People > Groups
# ======================================================================

class GroupsSubsectionWidget(QWidget):
    """
    Widget displayed when the user switches to the Groups tab
    within the People section.

    Provides:
    - "+ New Group" button
    - List/grid of existing groups
    - Search filter
    - Click → emits groupSelected(group_id, match_mode)

    Signal contract (consumed by PeopleSection._ensure_groups_tab):
        groupSelected(int, str)      — (group_id, match_mode)
        newGroupRequested()          — user clicked "+ New Group"
        editGroupRequested(int)      — (group_id)
        deleteGroupRequested(int)    — (group_id)
        recomputeRequested(int, str) — (group_id, match_mode)

    Legacy signals (consumed by accordion_sidebar.py _build_people_grid):
        groupCreated(int)            — new group_id
        groupDeleted(int)            — deleted group_id
        groupUpdated(int)            — updated group_id
        groupReindexRequested(int)   — group_id to reindex
    """

    # Signals expected by PeopleSection._ensure_groups_tab
    groupSelected = Signal(int, str)        # (group_id, match_mode)
    newGroupRequested = Signal()            # user wants to create a group
    editGroupRequested = Signal(int)        # (group_id)
    deleteGroupRequested = Signal(int)      # (group_id)
    recomputeRequested = Signal(int, str)   # (group_id, match_mode)

    # Legacy signals for accordion_sidebar.py backward compat
    groupCreated = Signal(int)              # new group_id
    groupDeleted = Signal(int)              # deleted group_id
    groupUpdated = Signal(int)              # updated group_id
    groupReindexRequested = Signal(int)     # group_id to reindex

    def __init__(self, project_id=0, parent: Optional[QWidget] = None):
        # Handle PeopleSection calling GroupsSection(self.parent()) — QWidget
        # passed as first positional arg instead of project_id
        if isinstance(project_id, QWidget):
            parent = project_id
            project_id = 0
        super().__init__(parent)
        self.project_id = int(project_id) if project_id else 0
        self._groups_data: List[Dict] = []
        self._cards: Dict[int, GroupCard] = {}
        # Public signals attribute (PeopleSection accesses gs.signals.loaded)
        self.signals = GroupsSectionSignals()
        self.signals.loaded.connect(self._on_groups_loaded)
        self._generation = 0

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header row: "+ New Group" button + count
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        btn_new = QPushButton("+ New Group")
        btn_new.setCursor(Qt.PointingHandCursor)
        btn_new.setStyleSheet("""
            QPushButton {
                padding: 6px 14px; border: 1px solid #1a73e8;
                border-radius: 6px; background: #1a73e8;
                color: white; font-weight: 600; font-size: 10pt;
            }
            QPushButton:hover { background: #1557b0; }
        """)
        btn_new.clicked.connect(self._on_create_group)
        header_layout.addWidget(btn_new)

        header_layout.addStretch()

        self._count_label = QLabel("0 groups")
        self._count_label.setStyleSheet("color: #5f6368; font-size: 9pt;")
        header_layout.addWidget(self._count_label)

        layout.addWidget(header)

        # Scroll area for group grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.NoFrame)

        # Empty state placeholder
        self._empty_label = QLabel("No groups yet.\nCreate a group to see photos where people appear together.")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("padding: 32px; color: #5f6368; font-size: 10pt;")
        self._scroll.setWidget(self._empty_label)

        layout.addWidget(self._scroll, 1)

    def set_db(self, db):
        """Accept a DB reference (no-op — we create per-thread instances)."""
        pass

    def load_section(self):
        """Load the groups section (alias for load_groups).

        Called by PeopleSection._ensure_groups_tab.
        """
        self.load_groups()

    def create_content_widget(self, data: list) -> "GroupsSubsectionWidget":
        """Build internal UI from pre-loaded groups data and return self.

        Called by PeopleSection.on_groups_loaded callback after signals.loaded
        fires.  Our _on_groups_loaded already built the cards, so just return
        ourselves as the content widget for the QStackedWidget.
        """
        return self

    def load_groups(self):
        """Load groups data in background thread."""
        if not self.project_id:
            return

        self._generation += 1
        current_gen = self._generation

        def work():
            try:
                from services.group_service import GroupService
                db = ReferenceDB()
                groups = GroupService.get_groups(db, self.project_id)

                # Get match counts and cover paths for each group
                for g in groups:
                    g["match_count"] = GroupService.get_cached_match_count(db, g["id"])
                    # Resolve cover: user-chosen or auto-derived from first match
                    if not g.get("cover_asset_path"):
                        g["cover_asset_path"] = GroupService.get_group_cover(
                            db, self.project_id, g["id"]
                        )

                db.close()
                self.signals.loaded.emit(current_gen, groups)
            except Exception as e:
                logger.error(f"[GroupsSubsection] Failed to load groups: {e}")
                self.signals.error.emit(current_gen, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _on_groups_loaded(self, generation: int, groups: list):
        if generation != self._generation:
            return

        self._groups_data = groups
        self._count_label.setText(f"{len(groups)} group{'s' if len(groups) != 1 else ''}")

        if not groups:
            self._empty_label.setVisible(True)
            self._scroll.setWidget(self._empty_label)
            return

        # Build group cards
        self._cards.clear()
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(6)

        for g in groups:
            # Load member face thumbnails (up to 3)
            member_pixmaps = []
            for member in g.get("members", [])[:3]:
                pm = self._load_member_thumb(member.get("rep_thumb_png"))
                member_pixmaps.append(pm)

            # Load cover thumbnail if available
            cover_pixmap = self._load_cover_thumb(g.get("cover_asset_path"))

            # Build display name from member labels
            member_names = [
                m.get("display_name", m.get("branch_key", "?"))
                for m in g.get("members", [])
            ]

            card = GroupCard(
                group_id=g["id"],
                display_name=g["name"],
                member_count=g["member_count"],
                result_count=g.get("match_count", -1),
                is_stale=False,
                member_pixmaps=member_pixmaps,
                match_mode="together",
                is_pinned=g.get("is_pinned", False),
                cover_pixmap=cover_pixmap,
            )
            card.clicked.connect(self._on_group_clicked)
            card.context_menu_requested.connect(self._on_group_context_menu)
            scroll_layout.addWidget(card)
            self._cards[g["id"]] = card

        scroll_layout.addStretch()
        self._scroll.setWidget(scroll_content)

    def _load_member_thumb(self, rep_thumb_png: Optional[bytes]) -> Optional[QPixmap]:
        """Load a small face thumbnail from BLOB."""
        if not rep_thumb_png:
            return None
        try:
            from PIL import Image
            img_data = io.BytesIO(rep_thumb_png)
            with Image.open(img_data) as img:
                img_rgb = img.convert("RGB")
                data = img_rgb.tobytes("raw", "RGB")
                qimg = QImage(data, img_rgb.width, img_rgb.height, img_rgb.width * 3, QImage.Format_RGB888)
                if qimg.isNull():
                    return None
                return QPixmap.fromImage(qimg).scaled(
                    48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
        except Exception:
            return None

    def _load_cover_thumb(self, cover_path: Optional[str]) -> Optional[QPixmap]:
        """Load a small cover thumbnail from a photo path (256px max edge)."""
        if not cover_path:
            return None
        try:
            import os
            if not os.path.exists(cover_path):
                return None
            from services.safe_image_loader import safe_decode_qimage
            qimg = safe_decode_qimage(cover_path, max_dim=256)
            if qimg.isNull():
                return None
            return QPixmap.fromImage(qimg)
        except Exception:
            return None

    def _on_group_clicked(self, group_id: int):
        # Resolve match_mode from group data (defaults to "together")
        match_mode = "together"
        for g in self._groups_data:
            if g.get("id") == group_id:
                match_mode = g.get("match_mode", "together")
                break
        self.groupSelected.emit(group_id, match_mode)

    def _on_group_context_menu(self, group_id: int, action: str):
        if action == "rename":
            self._rename_group(group_id)
        elif action == "toggle_pin":
            self._toggle_pin(group_id)
        elif action in ("edit_members", "edit"):
            self.editGroupRequested.emit(group_id)
            self._edit_group(group_id)
        elif action in ("reindex", "recompute_together"):
            self.recomputeRequested.emit(group_id, "together")
            self.groupReindexRequested.emit(group_id)
        elif action == "recompute_event":
            self.recomputeRequested.emit(group_id, "event")
            self.groupReindexRequested.emit(group_id)
        elif action == "delete":
            self.deleteGroupRequested.emit(group_id)
            self._delete_group(group_id)

    def _on_create_group(self):
        """Open CreateGroupDialog."""
        self.newGroupRequested.emit()
        dialog = CreateGroupDialog(self.project_id, parent=self)
        if dialog.exec() == QDialog.Accepted:
            result = dialog.get_result()
            try:
                from services.group_service import GroupService
                db = ReferenceDB()
                group_id = GroupService.create_group(
                    db, self.project_id, result["name"], result["branch_keys"]
                )
                # Compute initial matches
                GroupService.compute_and_store_matches(db, self.project_id, group_id)
                db.close()

                self.groupCreated.emit(group_id)
                self.load_groups()  # Refresh list
            except Exception as e:
                logger.error(f"[GroupsSubsection] Failed to create group: {e}")

    def _rename_group(self, group_id: int):
        """Rename a group via input dialog."""
        from PySide6.QtWidgets import QInputDialog

        current_name = ""
        for g in self._groups_data:
            if g["id"] == group_id:
                current_name = g["name"]
                break

        new_name, ok = QInputDialog.getText(
            self, "Rename Group", "New name:", text=current_name
        )
        if ok and new_name.strip():
            try:
                from services.group_service import GroupService
                db = ReferenceDB()
                GroupService.update_group(db, group_id, name=new_name.strip())
                db.close()
                self.groupUpdated.emit(group_id)
                self.load_groups()
            except Exception as e:
                logger.error(f"[GroupsSubsection] Failed to rename group: {e}")

    def _toggle_pin(self, group_id: int):
        """Toggle pinned state."""
        try:
            from services.group_service import GroupService
            current_pinned = False
            for g in self._groups_data:
                if g["id"] == group_id:
                    current_pinned = g.get("is_pinned", False)
                    break

            db = ReferenceDB()
            GroupService.update_group(db, group_id, is_pinned=not current_pinned)
            db.close()
            self.groupUpdated.emit(group_id)
            self.load_groups()
        except Exception as e:
            logger.error(f"[GroupsSubsection] Failed to toggle pin: {e}")

    def _edit_group(self, group_id: int):
        """Edit group members via dialog."""
        try:
            from services.group_service import GroupService
            db = ReferenceDB()
            group = GroupService.get_group(db, group_id, self.project_id)
            db.close()

            if not group:
                return

            dialog = CreateGroupDialog(self.project_id, existing_group=group, parent=self)
            if dialog.exec() == QDialog.Accepted:
                result = dialog.get_result()
                db = ReferenceDB()
                GroupService.update_group(
                    db, group_id,
                    name=result["name"],
                    branch_keys=result["branch_keys"],
                )
                GroupService.compute_and_store_matches(db, self.project_id, group_id)
                db.close()
                self.groupUpdated.emit(group_id)
                self.load_groups()
        except Exception as e:
            logger.error(f"[GroupsSubsection] Failed to edit group: {e}")

    def _delete_group(self, group_id: int):
        """Delete a group with confirmation."""
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Delete Group",
            "Are you sure you want to delete this group?\nThe people themselves won't be affected.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                from services.group_service import GroupService
                db = ReferenceDB()
                GroupService.delete_group(db, group_id)
                db.close()
                self.groupDeleted.emit(group_id)
                self.load_groups()
            except Exception as e:
                logger.error(f"[GroupsSubsection] Failed to delete group: {e}")

    def set_project(self, project_id: int):
        """Update project and reload."""
        self.project_id = project_id
        self._generation += 1
        self.load_groups()


# ======================================================================
# Backward-compatibility alias
# ======================================================================
# people_section.py (and possibly other modules) import the class as
# ``GroupsSection``.  Keep a public alias so both import paths work.
GroupsSection = GroupsSubsectionWidget
