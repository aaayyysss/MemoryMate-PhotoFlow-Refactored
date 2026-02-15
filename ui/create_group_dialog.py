# ui/create_group_dialog.py
# Dialog for creating/editing person groups
# Version: 1.1.0

"""
CreateGroupDialog - Create/Edit person groups

Multi-select dialog for choosing people to include in a group:
- Grid of people with circular thumbnails and file-path fallback
- Visual selection with blue ring + checkmark overlay (Google Photos style)
- Group name input with auto-suggestion
- Edit mode: loads existing members pre-selected, saves via update_group
- Pinned option
"""

import io
import logging
import os
from typing import Optional, List, Dict, Set

from PySide6.QtCore import Signal, Qt, QSize, QRect
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QColor, QPen, QFont, QBrush
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

AVATAR_SIZE = 64
CARD_WIDTH = 100
CARD_HEIGHT = 120


class PersonSelectCard(QWidget):
    """
    Selectable person card with circular avatar and checkmark overlay.

    Selection style follows Google Photos / Apple Photos pattern:
    - Unselected: subtle border, neutral background
    - Selected: blue ring around avatar, blue checkmark badge, tinted background
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
        self._base_thumbnail = thumbnail  # keep original for re-rendering

        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 4)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignCenter)

        # Avatar container (holds the rendered circular pixmap + overlay)
        self._avatar_label = QLabel()
        self._avatar_label.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self._avatar_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._avatar_label, alignment=Qt.AlignCenter)

        # Name
        name_label = QLabel(display_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setMaximumHeight(32)
        name_label.setStyleSheet("font-size: 10px; color: #202124;")
        layout.addWidget(name_label)

        self._render_avatar()
        self._update_card_style()

    def _render_avatar(self):
        """Render circular avatar with selection ring and checkmark."""
        size = AVATAR_SIZE
        result = QPixmap(size, size)
        result.fill(Qt.transparent)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._base_thumbnail and not self._base_thumbnail.isNull():
            # Clip to circle and draw thumbnail
            scaled = self._base_thumbnail.scaled(
                size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            clip = QPainterPath()
            clip.addEllipse(2, 2, size - 4, size - 4)
            painter.setClipPath(clip)
            # Center the scaled image
            x_off = (scaled.width() - size) // 2
            y_off = (scaled.height() - size) // 2
            painter.drawPixmap(-x_off + 2, -y_off + 2, scaled)
            painter.setClipping(False)
        else:
            # Placeholder circle
            painter.setBrush(QColor("#e8eaed"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(2, 2, size - 4, size - 4)
            painter.setPen(QColor("#9aa0a6"))
            font = QFont()
            font.setPixelSize(28)
            painter.setFont(font)
            painter.drawText(QRect(0, 0, size, size), Qt.AlignCenter, "\U0001F464")

        if self._selected:
            # Blue selection ring
            pen = QPen(QColor("#1a73e8"), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(1, 1, size - 2, size - 2)

            # Checkmark badge (bottom-right)
            badge_size = 20
            badge_x = size - badge_size - 1
            badge_y = size - badge_size - 1

            # White circle behind badge
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(badge_x - 1, badge_y - 1, badge_size + 2, badge_size + 2)

            # Blue circle
            painter.setBrush(QColor("#1a73e8"))
            painter.drawEllipse(badge_x, badge_y, badge_size, badge_size)

            # White checkmark
            painter.setPen(QPen(QColor("#ffffff"), 2.0))
            cx = badge_x + badge_size // 2
            cy = badge_y + badge_size // 2
            painter.drawLine(cx - 4, cy, cx - 1, cy + 3)
            painter.drawLine(cx - 1, cy + 3, cx + 5, cy - 3)

        painter.end()
        self._avatar_label.setPixmap(result)

    def _update_card_style(self):
        """Update card background based on selection state."""
        if self._selected:
            self.setStyleSheet("""
                PersonSelectCard {
                    background: rgba(26, 115, 232, 0.08);
                    border: 2px solid #1a73e8;
                    border-radius: 10px;
                }
            """)
        else:
            self.setStyleSheet("""
                PersonSelectCard {
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: 10px;
                }
                PersonSelectCard:hover {
                    background: rgba(0, 0, 0, 0.04);
                    border: 1px solid #dadce0;
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._selected = not self._selected
            self._render_avatar()
            self._update_card_style()
            self.toggled.emit(self.branch_key, self._selected)
        super().mousePressEvent(event)

    def is_selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool):
        self._selected = selected
        self._render_avatar()
        self._update_card_style()


class CreateGroupDialog(QDialog):
    """
    Dialog for creating or editing a person group.

    In edit mode, loads existing group data and saves changes via
    GroupService.update_group() on accept.
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

        # Results (read by caller after exec)
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
        title = "Edit Group" if self.is_edit_mode else "Create Group"
        self.setWindowTitle(title)
        self.setMinimumSize(520, 600)
        self.resize(620, 720)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header
        header_label = QLabel(
            "Edit group members" if self.is_edit_mode
            else "Select 2 or more people to create a group"
        )
        header_label.setStyleSheet("font-size: 13pt; color: #202124; font-weight: 500;")
        main_layout.addWidget(header_label)

        # Group name input
        name_container = QWidget()
        name_layout = QHBoxLayout(name_container)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(8)

        name_label = QLabel("Group name:")
        name_label.setStyleSheet("font-size: 11pt;")
        name_layout.addWidget(name_label)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g., Family, Trip Buddies")
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

        # People grid in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #fafafa; border-radius: 8px; }")

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(10, 10, 10, 10)
        self._grid_layout.setSpacing(8)

        scroll.setWidget(self._grid_container)
        main_layout.addWidget(scroll, 1)

        # Options row
        options_container = QWidget()
        options_layout = QHBoxLayout(options_container)
        options_layout.setContentsMargins(0, 0, 0, 0)

        self._pinned_checkbox = QCheckBox("Pin this group")
        self._pinned_checkbox.setStyleSheet("font-size: 10pt;")
        options_layout.addWidget(self._pinned_checkbox)
        options_layout.addStretch()

        main_layout.addWidget(options_container)

        # Buttons row
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)

        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
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

        btn_text = "Save" if self.is_edit_mode else "Create Group"
        self._create_btn = QPushButton(btn_text)
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
        """Load people from database with thumbnail fallback to file path."""
        try:
            from services.group_service import GroupService
            service = GroupService.instance()
            people = service.get_people_for_group_creation(self.project_id)

            logger.info(f"[CreateGroupDialog] Loaded {len(people)} people")

            columns = 5
            for idx, person in enumerate(people):
                branch_key = person["branch_key"]
                display_name = person["display_name"]
                thumb_blob = person.get("rep_thumb_png")
                rep_path = person.get("rep_path")

                # Try BLOB first, then file path
                thumbnail = None
                if thumb_blob:
                    thumbnail = self._load_thumbnail_blob(thumb_blob)
                if thumbnail is None and rep_path:
                    thumbnail = self._load_thumbnail_file(rep_path)

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

    def _load_thumbnail_blob(self, thumb_blob: bytes) -> Optional[QPixmap]:
        """Load thumbnail from in-DB PNG blob."""
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
            logger.warning(f"[CreateGroupDialog] Failed to load thumbnail blob: {e}")
            return None

    def _load_thumbnail_file(self, rep_path: str) -> Optional[QPixmap]:
        """Load thumbnail from file path (fallback when blob is unavailable)."""
        try:
            if not os.path.exists(rep_path):
                return None

            from PIL import Image

            with Image.open(rep_path) as img:
                img_rgb = img.convert("RGB")
                # Resize large images to avoid memory issues
                if img_rgb.width > 256 or img_rgb.height > 256:
                    img_rgb.thumbnail((256, 256), Image.Resampling.LANCZOS)

                data = img_rgb.tobytes("raw", "RGB")
                stride = img_rgb.width * 3
                qimg = QImage(data, img_rgb.width, img_rgb.height, stride, QImage.Format_RGB888)
                if qimg.isNull():
                    return None
                return QPixmap.fromImage(qimg)
        except Exception as e:
            logger.warning(f"[CreateGroupDialog] Failed to load thumbnail file {rep_path}: {e}")
            return None

    def _load_existing_group(self):
        """Load existing group data for edit mode."""
        try:
            from services.group_service import GroupService
            service = GroupService.instance()
            group = service.get_group(self.edit_group_id, self.project_id)

            if not group:
                logger.warning(f"[CreateGroupDialog] Group {self.edit_group_id} not found")
                return

            self._name_input.setText(group.get("name", ""))
            self._pinned_checkbox.setChecked(group.get("is_pinned", False))

            members = group.get("members", [])
            logger.info(f"[CreateGroupDialog] Edit mode: group has {len(members)} members")

            for member in members:
                branch_key = member.get("branch_key", "")
                if branch_key in self._people_cards:
                    self._people_cards[branch_key].set_selected(True)
                    self._selected_branch_keys.add(branch_key)
                else:
                    logger.warning(f"[CreateGroupDialog] Member {branch_key} not found in people cards")

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
            self._selection_label.setStyleSheet("color: #1a73e8; font-size: 10pt; font-weight: 600;")

        # Enable create/save button when >= 2 people selected
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
        # Resolve group name
        name = self._name_input.text().strip()
        if not name:
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

        # In edit mode, save changes immediately via service
        if self.is_edit_mode:
            try:
                from services.group_service import GroupService
                service = GroupService.instance()
                service.update_group(
                    group_id=self.edit_group_id,
                    name=self.group_name,
                    branch_keys=self.selected_people,
                    is_pinned=self.is_pinned,
                )
                logger.info(
                    f"[CreateGroupDialog] Updated group {self.edit_group_id}: "
                    f"name='{self.group_name}', members={len(self.selected_people)}"
                )
            except Exception as e:
                logger.error(f"[CreateGroupDialog] Failed to update group: {e}", exc_info=True)
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Update Failed", f"Failed to update group:\n{e}")
                return

        self.accept()
