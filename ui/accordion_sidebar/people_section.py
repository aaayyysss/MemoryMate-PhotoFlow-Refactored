# ui/accordion_sidebar/people_section.py
# People section - face clusters list

import io
import logging
import os
import threading
import traceback
from typing import Optional, List, Dict

from PySide6.QtCore import Signal, Qt, QObject
from PySide6.QtGui import QIcon, QPixmap, QImage
from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QSizePolicy, QHeaderView

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
        """Create a tree with people, thumbnails, and counts."""
        rows: List[Dict] = data or []
        if not rows:
            placeholder = QLabel(tr("sidebar.people.empty") if callable(tr) else "No people detected yet")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 16px; color: #666;")
            return placeholder

        tree = QTreeWidget()
        tree.setHeaderLabels([self.get_title(), tr("sidebar.count") if callable(tr) else "Photos"])
        tree.setColumnCount(2)
        tree.setSelectionMode(QTreeWidget.SingleSelection)
        tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        tree.setAlternatingRowColors(True)
        tree.setMinimumHeight(200)
        tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tree.header().setStretchLastSection(False)
        tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tree.setStyleSheet(
            """
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
            """
        )

        for idx, row in enumerate(rows):
            branch_key = row.get("branch_key") or f"cluster_{idx}"
            display_name = row.get("display_name") or f"Person {idx + 1}"
            member_count = int(row.get("member_count") or 0)
            rep_path = row.get("rep_path")
            rep_thumb = row.get("rep_thumb_png")

            item = QTreeWidgetItem([display_name, str(member_count)])
            item.setData(0, Qt.UserRole, branch_key)

            pixmap = self._load_face_thumbnail(rep_path, rep_thumb)
            if pixmap:
                icon = QIcon(pixmap)
                item.setIcon(0, icon)

            tree.addTopLevelItem(item)

        tree.itemDoubleClicked.connect(
            lambda item, col: self.personSelected.emit(item.data(0, Qt.UserRole))
            if item and item.data(0, Qt.UserRole) else None
        )

        logger.info(f"[PeopleSection] Tree built with {tree.topLevelItemCount()} people")
        return tree

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

