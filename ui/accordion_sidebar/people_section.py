# ui/accordion_sidebar/people_section.py
# People section - face clusters list

import io
import logging
import os
import threading
import traceback
from typing import Optional, List, Dict

from PySide6.QtCore import Signal, Qt, QObject, QSize, QRect, QPoint
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QLayout,
)

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = PeopleSectionSignals()
        self.signals.loaded.connect(self._on_data_loaded)
        self.signals.error.connect(self._on_error)

    def get_section_id(self) -> str:
        return "people"

    def get_title(self) -> str:
        return tr("sidebar.header_people") if callable(tr) else "People"

    def get_icon(self) -> str:
        return "👥"

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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        flow = FlowLayout(container, margin=6, spacing=8)

        for idx, row in enumerate(rows):
            branch_key = row.get("branch_key") or f"cluster_{idx}"
            display_name = row.get("display_name") or f"Person {idx + 1}"
            member_count = int(row.get("member_count") or 0)
            rep_path = row.get("rep_path")
            rep_thumb = row.get("rep_thumb_png")

            pixmap = self._load_face_thumbnail(rep_path, rep_thumb)
            card = PersonCard(branch_key, display_name, member_count, pixmap)
            card.clicked.connect(self.personSelected.emit)
            flow.addWidget(card)

        container.setLayout(flow)
        scroll.setWidget(container)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(scroll)

        logger.info(f"[PeopleSection] Grid built with {flow.count()} people")
        return wrapper

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


class PersonCard(QWidget):
    """Compact face card with circular thumbnail and counts."""

    clicked = Signal(str)

    def __init__(self, branch_key: str, display_name: str, member_count: int, face_pixmap: Optional[QPixmap], parent=None):
        super().__init__(parent)
        self.branch_key = branch_key
        self.display_name = display_name
        self.setFixedSize(88, 112)
        self.setCursor(Qt.PointingHandCursor)

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
            """
        )

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.branch_key)
        super().mouseReleaseEvent(event)

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

