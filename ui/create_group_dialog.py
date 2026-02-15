# ui/create_group_dialog.py
# Dialog for creating person groups
# Version: 1.0.0

"""
CreateGroupDialog - Create/Edit person groups

Multi-select dialog for choosing people to include in a group:
- Grid of people with circular thumbnails
- Multi-selection with checkboxes
- Group name input with auto-suggestion
- Pinned option

Based on Apple Photos "Add to Group" flow and existing PeopleManagerDialog patterns.
"""

import io
import logging
from typing import Optional, List, Dict, Set

from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
    QGridLayout,
    QCheckBox,
    QFrame,
    QSizePolicy,
)

from translation_manager import tr

logger = logging.getLogger(__name__)


class PersonSelectCard(QWidget):
    """
    Selectable person card for group creation.

    Features:
    - Circular avatar thumbnail
    - Person name
    - Checkbox for selection
    - Visual highlight when selected
    """

    toggled = Signal(str, bool)  # (branch_key, is_selected)

    def __init__(
        self,
        branch_key: str,
        display_name: str,
        thumbnail: Optional[QPixmap],
        selected: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.branch_key = branch_key
        self.display_name = display_name
        self._selected = selected

        self.setFixedSize(100, 110)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        # Checkbox (small, top-right overlay - handled via click on whole card)
        # For simplicity, we make the whole card clickable

        # Avatar
        avatar = QLabel()
        avatar.setFixedSize(56, 56)
        avatar.setAlignment(Qt.AlignCenter)

        if thumbnail and not thumbnail.isNull():
            circular = self._make_circular(thumbnail, 56)
            avatar.setPixmap(circular)
        else:
            avatar.setText("👤")
            avatar.setStyleSheet("background: #e8eaed; border-radius: 28px; font-size: 24px;")

        layout.addWidget(avatar, alignment=Qt.AlignCenter)

        # Name
        name_label = QLabel(display_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-size: 10px; color: #202124;")
        layout.addWidget(name_label)

        # Selection indicator (checkmark overlay)
        self._update_style()

    def _make_circular(self, pixmap: QPixmap, size: int) -> QPixmap:
        """Create circular version of pixmap."""
        scaled = pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        mask = QPixmap(size, size)
        mask.fill(Qt.transparent)

        painter = QPainter(mask)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()

        return mask

    def _update_style(self):
        """Update visual style based on selection state."""
        if self._selected:
            self.setStyleSheet("""
                PersonSelectCard {
                    background: rgba(26, 115, 232, 0.12);
                    border: 2px solid #1a73e8;
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                PersonSelectCard {
                    background: transparent;
                    border: 1px solid #dadce0;
                    border-radius: 8px;
                }
                PersonSelectCard:hover {
                    background: rgba(26, 115, 232, 0.04);
                    border: 1px solid #1a73e8;
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._selected = not self._selected
            self._update_style()
            self.toggled.emit(self.branch_key, self._selected)
        super().mousePressEvent(event)

    def is_selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()


class CreateGroupDialog(QDialog):
    """
    Dialog for creating or editing a person group.

    Usage:
        dialog = CreateGroupDialog(project_id, parent=main_window)
        if dialog.exec() == QDialog.Accepted:
            group_name = dialog.group_name
            selected_people = dialog.selected_people
            is_pinned = dialog.is_pinned
    """

    def __init__(
        self,
        project_id: int,
        edit_group_id: Optional[int] = None,
        parent=None
    ):
        super().__init__(parent)
        self.project_id = project_id
        self.edit_group_id = edit_group_id
        self.is_edit_mode = edit_group_id is not None

        # Results
        self.group_name: str = ""
        self.selected_people: List[str] = []
        self.is_pinned: bool = False

        # Internal state
        self._people_cards: Dict[str, PersonSelectCard] = {}
        self._selected_branch_keys: Set[str] = set()

        self._setup_ui()
        self._load_people()

        if self.is_edit_mode:
            self._load_existing_group()

    def _setup_ui(self):
        """Setup dialog UI."""
        title = tr("dialogs.edit_group.title") if self.is_edit_mode else tr("dialogs.create_group.title")
        title = title if callable(tr) else ("Edit Group" if self.is_edit_mode else "Create Group")
        self.setWindowTitle(title)
        self.setMinimumSize(500, 600)
        self.resize(600, 700)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # Header
        header_label = QLabel(
            tr("dialogs.create_group.header") if callable(tr)
            else "Select 2 or more people to create a group"
        )
        header_label.setStyleSheet("font-size: 13pt; color: #202124;")
        main_layout.addWidget(header_label)

        # Group name input
        name_container = QWidget()
        name_layout = QHBoxLayout(name_container)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(8)

        name_label = QLabel(tr("dialogs.create_group.name") if callable(tr) else "Group name:")
        name_label.setStyleSheet("font-size: 11pt;")
        name_layout.addWidget(name_label)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText(
            tr("dialogs.create_group.name_placeholder") if callable(tr)
            else "e.g., Family, Trip Buddies"
        )
        self._name_input.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #dadce0;
                border-radius: 6px;
                font-size: 11pt;
            }
            QLineEdit:focus {
                border: 1px solid #1a73e8;
            }
        """)
        name_layout.addWidget(self._name_input, 1)

        main_layout.addWidget(name_container)

        # Selection count and hint
        self._selection_label = QLabel("Select at least 2 people")
        self._selection_label.setStyleSheet("color: #5f6368; font-size: 10pt;")
        main_layout.addWidget(self._selection_label)

        # People grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: #fafafa; border-radius: 8px;")

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(8, 8, 8, 8)
        self._grid_layout.setSpacing(10)

        scroll.setWidget(self._grid_container)
        main_layout.addWidget(scroll, 1)

        # Options
        options_container = QWidget()
        options_layout = QHBoxLayout(options_container)
        options_layout.setContentsMargins(0, 0, 0, 0)

        self._pinned_checkbox = QCheckBox(
            tr("dialogs.create_group.pinned") if callable(tr) else "Pin this group"
        )
        self._pinned_checkbox.setStyleSheet("font-size: 10pt;")
        options_layout.addWidget(self._pinned_checkbox)
        options_layout.addStretch()

        main_layout.addWidget(options_container)

        # Buttons
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)

        button_layout.addStretch()

        cancel_btn = QPushButton(tr("dialogs.cancel") if callable(tr) else "Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 24px;
                border: 1px solid #dadce0;
                border-radius: 6px;
                background: white;
                font-size: 11pt;
            }
            QPushButton:hover { background: #f1f3f4; }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self._create_btn = QPushButton(
            tr("dialogs.save") if self.is_edit_mode else tr("dialogs.create")
            if callable(tr) else ("Save" if self.is_edit_mode else "Create Group")
        )
        self._create_btn.setEnabled(False)
        self._create_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 24px;
                border: none;
                border-radius: 6px;
                background: #1a73e8;
                color: white;
                font-size: 11pt;
                font-weight: 600;
            }
            QPushButton:hover { background: #1557b0; }
            QPushButton:disabled { background: #dadce0; color: #9aa0a6; }
        """)
        self._create_btn.clicked.connect(self._on_create)
        button_layout.addWidget(self._create_btn)

        main_layout.addWidget(button_container)

    def _load_people(self):
        """Load people from database."""
        try:
            from services.group_service import GroupService
            service = GroupService.instance()
            people = service.get_people_for_group_creation(self.project_id)

            logger.info(f"[CreateGroupDialog] Loaded {len(people)} people")

            columns = 4
            for idx, person in enumerate(people):
                branch_key = person["branch_key"]
                display_name = person["display_name"]
                thumb_blob = person.get("rep_thumb_png")

                thumbnail = None
                if thumb_blob:
                    thumbnail = self._load_thumbnail(thumb_blob)

                card = PersonSelectCard(
                    branch_key=branch_key,
                    display_name=display_name,
                    thumbnail=thumbnail
                )
                card.toggled.connect(self._on_person_toggled)

                row = idx // columns
                col = idx % columns
                self._grid_layout.addWidget(card, row, col)
                self._people_cards[branch_key] = card

        except Exception as e:
            logger.error(f"[CreateGroupDialog] Failed to load people: {e}", exc_info=True)

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
                return QPixmap.fromImage(qimg)
        except Exception as e:
            logger.warning(f"[CreateGroupDialog] Failed to load thumbnail: {e}")
            return None

    def _load_existing_group(self):
        """Load existing group data for edit mode."""
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            with db._connect() as conn:
                # Get group info
                cur = conn.execute(
                    "SELECT name, pinned FROM person_groups WHERE id = ?",
                    (self.edit_group_id,)
                )
                row = cur.fetchone()
                if row:
                    self._name_input.setText(row[0])
                    self._pinned_checkbox.setChecked(bool(row[1]))

                # Get members
                cur = conn.execute(
                    "SELECT person_id FROM person_group_members WHERE group_id = ?",
                    (self.edit_group_id,)
                )
                for row in cur.fetchall():
                    branch_key = row[0]
                    if branch_key in self._people_cards:
                        self._people_cards[branch_key].set_selected(True)
                        self._selected_branch_keys.add(branch_key)

            db.close()
            self._update_selection_ui()

        except Exception as e:
            logger.error(f"[CreateGroupDialog] Failed to load group: {e}", exc_info=True)

    def _on_person_toggled(self, branch_key: str, is_selected: bool):
        """Handle person selection change."""
        if is_selected:
            self._selected_branch_keys.add(branch_key)
        else:
            self._selected_branch_keys.discard(branch_key)

        self._update_selection_ui()

    def _update_selection_ui(self):
        """Update selection count and button state."""
        count = len(self._selected_branch_keys)

        if count == 0:
            self._selection_label.setText("Select at least 2 people")
            self._selection_label.setStyleSheet("color: #5f6368; font-size: 10pt;")
        elif count == 1:
            self._selection_label.setText("1 person selected (need at least 2)")
            self._selection_label.setStyleSheet("color: #ea4335; font-size: 10pt;")
        else:
            self._selection_label.setText(f"{count} people selected")
            self._selection_label.setStyleSheet("color: #1a73e8; font-size: 10pt;")

        # Enable create button if >= 2 people selected
        self._create_btn.setEnabled(count >= 2)

        # Auto-suggest group name if empty
        if not self._name_input.text().strip() and count >= 2:
            names = []
            for branch_key in list(self._selected_branch_keys)[:3]:
                if branch_key in self._people_cards:
                    names.append(self._people_cards[branch_key].display_name)

            suggested = " + ".join(names)
            if count > 3:
                suggested += f" + {count - 3} more"

            self._name_input.setPlaceholderText(f"Suggested: {suggested}")

    def _on_create(self):
        """Handle create/save button click."""
        # Get group name (use suggested if empty)
        name = self._name_input.text().strip()
        if not name:
            # Use auto-suggested name
            names = []
            for branch_key in list(self._selected_branch_keys)[:3]:
                if branch_key in self._people_cards:
                    names.append(self._people_cards[branch_key].display_name)
            name = " + ".join(names)
            if len(self._selected_branch_keys) > 3:
                name += f" + {len(self._selected_branch_keys) - 3} more"

        self.group_name = name
        self.selected_people = list(self._selected_branch_keys)
        self.is_pinned = self._pinned_checkbox.isChecked()

        self.accept()
