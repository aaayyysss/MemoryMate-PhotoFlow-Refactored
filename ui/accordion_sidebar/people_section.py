# ui/accordion_sidebar/people_section.py
# People section - face clusters list

import io
import logging
import os
import threading
import traceback
from typing import Optional, List, Dict

from PySide6.QtCore import Signal, Qt, QObject, QSize, QRect, QPoint, QEvent
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QLayout,
    QGridLayout,
    QSizePolicy,
    QToolButton,
)
from shiboken6 import isValid

from reference_db import ReferenceDB
from translation_manager import tr
from .base_section import BaseSection

logger = logging.getLogger(__name__)


class PeopleSectionSignals(QObject):
    """Signals for async people loading."""

    loaded = Signal(int, list)  # (generation, face_rows)
    error = Signal(int, str)    # (generation, error_message)


class PeopleSection(BaseSection):
    """People section implementation showing detected face clusters."""

    personSelected = Signal(str)  # person_branch_key
    contextMenuRequested = Signal(str, str)  # (branch_key, action)
    dragMergeRequested = Signal(str, str)  # (source_branch, target_branch)
    mergeHistoryRequested = Signal()
    undoMergeRequested = Signal()
    redoMergeRequested = Signal()
    peopleToolsRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = PeopleSectionSignals()
        self.signals.loaded.connect(self._on_data_loaded)
        self.signals.error.connect(self._on_error)

        # Keep a reference to rendered cards so selection state can be updated externally
        self._cards: Dict[str, "PersonCard"] = {}
        self._header_widget: Optional[QWidget] = None

    def get_section_id(self) -> str:
        return "people"

    def get_title(self) -> str:
        return tr("sidebar.header_people") if callable(tr) else "People"

    def get_icon(self) -> str:
        return "👥"

    def get_header_widget(self) -> Optional[QWidget]:
        """Provide compact post-detection controls beside the section title."""
        if self._header_widget:
            return self._header_widget

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        def build_btn(emoji: str, tooltip_key: str, fallback: str, callback):
            btn = QToolButton()
            btn.setText(emoji)
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
                }
                QToolButton:hover { background: #f1f3f4; }
                QToolButton:pressed { background: #e8f0fe; }
                """
            )
            layout.addWidget(btn)

        build_btn("🕑", "sidebar.people_actions.merge_history", "View Merge History", self.mergeHistoryRequested.emit)
        build_btn("↩️", "sidebar.people_actions.undo_last_merge", "Undo Last Merge", self.undoMergeRequested.emit)
        build_btn("↪️", "sidebar.people_actions.redo_last_undo", "Redo Last Undo", self.redoMergeRequested.emit)
        build_btn("🧰", "sidebar.people_actions.people_tools", "Open People Tools", self.peopleToolsRequested.emit)

        self._header_widget = container
        return self._header_widget

    def load_section(self) -> None:
        """Load people section data in a background thread."""
        if not self.project_id:
            logger.warning("[PeopleSection] No project_id set")
            return

        self._generation += 1
        current_gen = self._generation
        self._loading = True

        logger.info(f"[PeopleSection] Loading face clusters (generation {current_gen})…")

        def work():
            db: Optional[ReferenceDB] = None
            try:
                db = ReferenceDB()
                rows = db.get_face_clusters(self.project_id) or []
                logger.info(f"[PeopleSection] Loaded {len(rows)} clusters (gen {current_gen})")
                return rows
            except Exception as e:
                logger.error(f"[PeopleSection] Error loading face clusters: {e}")
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
                rows = work()
                if current_gen == self._generation:
                    self.signals.loaded.emit(current_gen, rows)
                else:
                    logger.debug(
                        f"[PeopleSection] Discarding stale data (gen {current_gen} vs {self._generation})"
                    )
            except Exception as e:
                logger.error(f"[PeopleSection] Error in worker thread: {e}")
                traceback.print_exc()
                if current_gen == self._generation:
                    self.signals.error.emit(current_gen, str(e))

        threading.Thread(target=on_complete, daemon=True).start()

    def create_content_widget(self, data):
        """Create a flow-wrapped grid of faces (multi-row people view)."""
        rows: List[Dict] = data or []
        if not rows:
            placeholder = QLabel(tr("sidebar.people.empty") if callable(tr) else "No people detected yet")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 16px; color: #666;")
            return placeholder

        # Quick action bar for post-detection tools
        actions = QWidget()
        actions_layout = FlowLayout(actions, margin=8, spacing=6)

        def _make_action(text_key: str, fallback: str, callback):
            btn = QPushButton(fallback if not callable(tr) else f"{fallback.split(' ', 1)[0]} {tr(text_key)}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                """
                QPushButton {
                    padding: 6px 10px;
                    border: 1px solid #dadce0;
                    border-radius: 6px;
                    background: #f8f9fa;
                }
                QPushButton:hover { background: #eef3fd; }
                QPushButton:pressed { background: #e8f0fe; }
                """
            )
            btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            btn.clicked.connect(callback)
            actions_layout.addWidget(btn)

        _make_action('sidebar.people_actions.merge_history', '🕑 View Merge History', self.mergeHistoryRequested.emit)
        _make_action('sidebar.people_actions.undo_last_merge', '↩️ Undo Last Merge', self.undoMergeRequested.emit)
        _make_action('sidebar.people_actions.redo_last_undo', '↪️ Redo Last Undo', self.redoMergeRequested.emit)
        _make_action('sidebar.people_actions.people_tools', '🧰 Open People Tools', self.peopleToolsRequested.emit)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)

        # Reset cache of rendered cards
        self._cards.clear()

        cards: List[PersonCard] = []

        for idx, row in enumerate(rows):
            branch_key = row.get("branch_key") or f"cluster_{idx}"
            display_name = row.get("display_name") or f"Person {idx + 1}"
            member_count = int(row.get("member_count") or 0)
            rep_path = row.get("rep_path")
            rep_thumb = row.get("rep_thumb_png")

            pixmap = self._load_face_thumbnail(rep_path, rep_thumb)
            card = PersonCard(branch_key, display_name, member_count, pixmap)
            card.clicked.connect(self.personSelected.emit)
            card.context_menu_requested.connect(self.contextMenuRequested.emit)
            card.drag_merge_requested.connect(self.dragMergeRequested.emit)

            cards.append(card)
            self._cards[branch_key] = card

        container = PeopleGrid(cards)
        container.attach_viewport(scroll.viewport())
        scroll.setWidget(container)

        logger.info(f"[PeopleSection] Grid built with {len(cards)} people")
        return scroll

    # --- Selection helpers ---
    def set_active_branch(self, branch_key: Optional[str]) -> None:
        """Highlight the active person card for visual feedback in the sidebar."""
        try:
            for key, card in self._cards.items():
                is_active = branch_key is not None and key == branch_key
                card.setProperty("selected", is_active)
                card.style().unpolish(card)
                card.style().polish(card)
        except Exception:
            logger.debug("[PeopleSection] Failed to update active state", exc_info=True)

    def _load_face_thumbnail(self, rep_path: Optional[str], rep_thumb_png: Optional[bytes]) -> Optional[QPixmap]:
        """Load a face thumbnail from BLOB or file path."""
        try:
            FACE_ICON_SIZE = 48

            if rep_thumb_png:
                try:
                    image_data = io.BytesIO(rep_thumb_png)
                    from PIL import Image

                    with Image.open(image_data) as img:
                        img_rgb = img.convert("RGB")
                        data = img_rgb.tobytes("raw", "RGB")
                        qimg = QImage(data, img.width, img.height, QImage.Format_RGB888)
                        return QPixmap.fromImage(qimg).scaled(
                            FACE_ICON_SIZE, FACE_ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                except Exception as blob_error:
                    logger.debug(f"[PeopleSection] Failed to load thumbnail from BLOB: {blob_error}")

            if rep_path and os.path.exists(rep_path):
                try:
                    from PIL import Image

                    with Image.open(rep_path) as img:
                        img_rgb = img.convert("RGB")
                        data = img_rgb.tobytes("raw", "RGB")
                        qimg = QImage(data, img.width, img.height, QImage.Format_RGB888)
                        return QPixmap.fromImage(qimg).scaled(
                            FACE_ICON_SIZE, FACE_ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                except Exception as file_error:
                    logger.debug(f"[PeopleSection] Failed to load thumbnail from {rep_path}: {file_error}")

            return None
        except Exception as e:
            logger.debug(f"[PeopleSection] Error in _load_face_thumbnail: {e}")
            return None

    def _on_error(self, generation: int, message: str):
        """Handle loading errors."""
        if generation != self._generation:
            return
        self._loading = False
        logger.error(f"[PeopleSection] Load error: {message}")

class FlowLayout(QLayout):
    """Simple flow layout for wrapping person cards across rows."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = -1):
        super().__init__(parent)
        self.itemList = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing if spacing >= 0 else 6)

    def addItem(self, item):
        self.itemList.append(item)

    def addWidget(self, widget):
        super().addWidget(widget)
        self.itemList.append(self.itemAt(self.count() - 1))

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
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x, y = rect.x(), rect.y()
        line_height = 0
        spacing = self.spacing()
        for item in self.itemList:
            widget = item.widget()
            if not widget:
                continue

            next_x = x + item.sizeHint().width() + spacing
            if next_x - spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + spacing
                next_x = x + item.sizeHint().width() + spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()


class PeopleGrid(QWidget):
    """Grid that automatically recalculates columns based on available width."""

    def __init__(self, cards: List["PersonCard"], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.cards = cards
        self._card_width = cards[0].sizeHint().width() if cards else 96
        self._columns = 0
        self._viewport = None
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setHorizontalSpacing(10)
        self._layout.setVerticalSpacing(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._relayout(force=True)

    def attach_viewport(self, viewport: QWidget) -> None:
        """Track the scroll viewport so column count follows sidebar width."""
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

        # Clear existing layout positions without deleting widgets
        while self._layout.count():
            self._layout.takeAt(0)

        for idx, card in enumerate(self.cards):
            row = idx // columns
            col = idx % columns
            self._layout.addWidget(card, row, col)


class PersonCard(QWidget):
    """Compact face card with circular thumbnail and counts."""

    clicked = Signal(str)
    context_menu_requested = Signal(str, str)  # (branch_key, action)
    drag_merge_requested = Signal(str, str)  # (source_branch, target_branch)

    def __init__(self, branch_key: str, display_name: str, member_count: int, face_pixmap: Optional[QPixmap], parent=None):
        super().__init__(parent)
        self.branch_key = branch_key
        self.display_name = display_name
        self.setFixedSize(88, 112)
        self.setCursor(Qt.PointingHandCursor)

        self._press_pos: Optional[QPoint] = None
        self._drag_active = False

        # Enable drag-and-drop for face merging
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        avatar = QLabel()
        avatar.setFixedSize(64, 64)
        avatar.setAlignment(Qt.AlignCenter)
        if face_pixmap and not face_pixmap.isNull():
            avatar.setPixmap(self._make_circular(face_pixmap, 64))
        else:
            avatar.setText("👤")
            avatar.setStyleSheet("background:#e8eaed;border-radius:32px;font-size:24px;")
        layout.addWidget(avatar)

        name_label = QLabel(display_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-weight:600;font-size:11px;color:#202124;")
        layout.addWidget(name_label)

        count_label = QLabel(f"{member_count} photos")
        count_label.setAlignment(Qt.AlignCenter)
        count_label.setStyleSheet("color:#5f6368;font-size:10px;")
        layout.addWidget(count_label)

        self.setStyleSheet(
            """
            PersonCard { background: transparent; border-radius: 8px; }
            PersonCard:hover { background: rgba(26,115,232,0.08); }
            PersonCard[selected="true"] { background: rgba(26,115,232,0.12); border: 1px solid #1a73e8; }
            PersonCard[dragging="true"] { background: rgba(26,115,232,0.12); border: 1px dashed #1a73e8; }
            PersonCard[dragTarget="true"] { background: rgba(26,115,232,0.08); border: 1px dashed #1a73e8; }
            """
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            self._drag_active = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._press_pos:
            distance = (event.position().toPoint() - self._press_pos).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._begin_drag()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._drag_active:
            self.clicked.emit(self.branch_key)
        self._press_pos = None
        self._drag_active = False
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Show context menu for rename/merge/delete actions."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        menu = QMenu(self)

        rename_action = QAction("✏️ " + (tr("sidebar.people_actions.rename") if callable(tr) else "Rename"), self)
        rename_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "rename"))
        menu.addAction(rename_action)

        merge_action = QAction(
            "🔗 " + (tr("sidebar.people_actions.merge_hint") if callable(tr) else "Merge (use drag-drop)"), self
        )
        merge_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "merge"))
        menu.addAction(merge_action)

        menu.addSeparator()

        details_action = QAction("ℹ️ " + (tr("sidebar.people_actions.details") if callable(tr) else "Details"), self)
        details_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "details"))
        menu.addAction(details_action)

        delete_action = QAction("🗑️ " + (tr("sidebar.people_actions.delete") if callable(tr) else "Delete"), self)
        delete_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "delete"))
        menu.addAction(delete_action)

        tools_menu = menu.addMenu(
            "🧰 " + (tr("sidebar.people_actions.post_detection") if callable(tr) else "Post-Face Detection")
        )

        history_action = QAction(
            "🕑 " + (tr("sidebar.people_actions.merge_history") if callable(tr) else "View Merge History"), self
        )
        history_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "merge_history"))
        tools_menu.addAction(history_action)

        undo_action = QAction(
            "↩️ " + (tr("sidebar.people_actions.undo_last_merge") if callable(tr) else "Undo Last Merge"), self
        )
        undo_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "undo_merge"))
        tools_menu.addAction(undo_action)

        redo_action = QAction(
            "↪️ " + (tr("sidebar.people_actions.redo_last_undo") if callable(tr) else "Redo Last Undo"), self
        )
        redo_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "redo_merge"))
        tools_menu.addAction(redo_action)

        people_tools_action = QAction(
            "🧭 " + (tr("sidebar.people_actions.people_tools") if callable(tr) else "Open People Tools"), self
        )
        people_tools_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "people_tools"))
        tools_menu.addAction(people_tools_action)

        menu.exec_(event.globalPos())

    def dragEnterEvent(self, event):
        """Accept drag events from other PersonCards."""
        if event.mimeData().hasText() and event.mimeData().text().startswith("person:"):
            self._set_drag_target_highlight(True)
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle drop event - merge source person into this person."""
        if event.mimeData().hasText():
            source_data = event.mimeData().text()
            if source_data.startswith("person:"):
                source_branch = source_data.split(":", 1)[1]
                if source_branch != self.branch_key:
                    self.drag_merge_requested.emit(source_branch, self.branch_key)
                    event.acceptProposedAction()
        if isValid(self):
            self._set_drag_target_highlight(False)

    def dragLeaveEvent(self, event):
        self._set_drag_target_highlight(False)
        super().dragLeaveEvent(event)

    def _make_circular(self, pixmap: QPixmap, size: int) -> QPixmap:
        scaled = pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        mask = QPixmap(size, size)
        mask.fill(Qt.transparent)
        from PySide6.QtGui import QPainter, QPainterPath

        painter = QPainter(mask)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return mask

    # === Drag helpers ===
    def _begin_drag(self):
        """Start a drag with a visual pixmap and safe state handling."""
        from PySide6.QtGui import QDrag
        from PySide6.QtCore import QMimeData

        self._drag_active = True
        self.setProperty("dragging", True)
        self.style().unpolish(self)
        self.style().polish(self)

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"person:{self.branch_key}")
        drag.setMimeData(mime_data)

        drag_pixmap = self.grab()
        if not drag_pixmap.isNull():
            drag.setPixmap(drag_pixmap)
            drag.setHotSpot(drag_pixmap.rect().center())

        drag.exec_(Qt.MoveAction)

        self._drag_active = False
        self._press_pos = None

        if isValid(self):
            # Restore visual state only if the widget still exists
            self.setProperty("dragging", False)
            self.style().unpolish(self)
            self.style().polish(self)

    def _set_drag_target_highlight(self, enabled: bool):
        if not isValid(self):
            return

        self.setProperty("dragTarget", enabled)
        self.style().unpolish(self)
        self.style().polish(self)

