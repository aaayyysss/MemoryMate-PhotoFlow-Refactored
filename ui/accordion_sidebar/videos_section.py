# ui/accordion_sidebar/videos_section.py
# Videos section for accordion sidebar

import threading
import traceback
import logging
from typing import Optional
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QSizePolicy, QLabel
from PySide6.QtCore import Signal, Qt, QObject
from PySide6.QtGui import QColor
from translation_manager import tr
from .base_section import BaseSection

logger = logging.getLogger(__name__)


class VideosSectionSignals(QObject):
    """Signals for videos section loading."""
    loaded = Signal(int, list)  # (generation, videos_list)
    error = Signal(int, str)    # (generation, error_message)


class VideosSection(BaseSection):
    """
    Videos section implementation.

    Displays video filtering options:
    - All Videos
    - By Duration (Short/Medium/Long)
    - By Quality (HD/4K)
    """

    videoFilterSelected = Signal(str)  # filter_type (e.g., "all", "short", "hd")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = VideosSectionSignals()
        self.signals.loaded.connect(self._on_data_loaded)
        self.signals.error.connect(self._on_error)

    def get_section_id(self) -> str:
        return "videos"

    def get_title(self) -> str:
        return "Videos"

    def get_icon(self) -> str:
        return "🎬"

    def load_section(self) -> None:
        """Load videos from database in background thread."""
        if not self.project_id:
            logger.warning("[VideosSection] No project_id set")
            return

        # Increment generation
        self._generation += 1
        current_gen = self._generation
        self._loading = True

        logger.info(f"[VideosSection] Loading videos (generation {current_gen})...")

        # Background worker
        def work():
            try:
                from services.video_service import VideoService
                video_service = VideoService()
                videos = video_service.get_videos_by_project(self.project_id) if self.project_id else []
                logger.info(f"[VideosSection] Loaded {len(videos)} videos (gen {current_gen})")
                return videos
            except Exception as e:
                error_msg = f"Error loading videos: {e}"
                logger.error(f"[VideosSection] {error_msg}")
                traceback.print_exc()
                return []

        # Run in thread
        def on_complete():
            try:
                videos = work()
                # Only emit if generation still matches
                if current_gen == self._generation:
                    self.signals.loaded.emit(current_gen, videos)
                else:
                    logger.debug(f"[VideosSection] Discarding stale data (gen {current_gen} vs {self._generation})")
            except Exception as e:
                logger.error(f"[VideosSection] Error in worker thread: {e}")
                traceback.print_exc()
                if current_gen == self._generation:
                    self.signals.error.emit(current_gen, str(e))

        threading.Thread(target=on_complete, daemon=True).start()

    def create_content_widget(self, data):
        """Create videos tree widget."""
        videos = data  # List of video dictionaries from VideoService

        # Create tree widget
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setIndentation(16)
        tree.setMinimumHeight(200)
        tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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

        total_videos = len(videos)

        if total_videos == 0:
            # No videos - show message
            no_videos_item = QTreeWidgetItem(["  (No videos yet)"])
            no_videos_item.setForeground(0, QColor("#888888"))
            tree.addTopLevelItem(no_videos_item)
            return tree

        # All Videos
        all_item = QTreeWidgetItem([f"All Videos ({total_videos})"])
        all_item.setData(0, Qt.UserRole, {"type": "all_videos"})
        tree.addTopLevelItem(all_item)

        # By Duration
        # Use 'duration_seconds' field from video metadata
        short_videos = [v for v in videos if v.get("duration_seconds") and v["duration_seconds"] < 30]
        medium_videos = [v for v in videos if v.get("duration_seconds") and 30 <= v["duration_seconds"] < 300]
        long_videos = [v for v in videos if v.get("duration_seconds") and v["duration_seconds"] >= 300]

        # Count videos WITH duration metadata
        videos_with_duration = [v for v in videos if v.get("duration_seconds")]
        duration_parent = QTreeWidgetItem([f"⏱️ By Duration ({len(videos_with_duration)})"])
        duration_parent.setData(0, Qt.UserRole, {"type": "duration_header"})
        tree.addTopLevelItem(duration_parent)

        if short_videos:
            short_item = QTreeWidgetItem([f"  Short (< 30s) - {len(short_videos)}"])
            short_item.setData(0, Qt.UserRole, {"type": "duration", "filter": "short"})
            duration_parent.addChild(short_item)

        if medium_videos:
            medium_item = QTreeWidgetItem([f"  Medium (30s-5m) - {len(medium_videos)}"])
            medium_item.setData(0, Qt.UserRole, {"type": "duration", "filter": "medium"})
            duration_parent.addChild(medium_item)

        if long_videos:
            long_item = QTreeWidgetItem([f"  Long (> 5m) - {len(long_videos)}"])
            long_item.setData(0, Qt.UserRole, {"type": "duration", "filter": "long"})
            duration_parent.addChild(long_item)

        # By Quality (if width/height available)
        hd_videos = [v for v in videos if v.get("width") and v["width"] >= 1280]
        four_k_videos = [v for v in videos if v.get("width") and v["width"] >= 3840]

        if hd_videos or four_k_videos:
            quality_parent = QTreeWidgetItem([f"📺 By Quality"])
            quality_parent.setData(0, Qt.UserRole, {"type": "quality_header"})
            tree.addTopLevelItem(quality_parent)

            if four_k_videos:
                four_k_item = QTreeWidgetItem([f"  4K+ - {len(four_k_videos)}"])
                four_k_item.setData(0, Qt.UserRole, {"type": "quality", "filter": "4k"})
                quality_parent.addChild(four_k_item)

            if hd_videos:
                hd_item = QTreeWidgetItem([f"  HD - {len(hd_videos)}"])
                hd_item.setData(0, Qt.UserRole, {"type": "quality", "filter": "hd"})
                quality_parent.addChild(hd_item)

        # Connect double-click to emit filter selection
        tree.itemDoubleClicked.connect(
            lambda item, col: self._on_item_double_clicked(item)
        )

        logger.info(f"[VideosSection] Tree built with {total_videos} videos")
        return tree

    def _on_item_double_clicked(self, item: QTreeWidgetItem):
        """Handle double-click on video filter item."""
        data = item.data(0, Qt.UserRole)
        if data and isinstance(data, dict):
            filter_type = data.get("type")
            if filter_type == "all_videos":
                self.videoFilterSelected.emit("all")
            elif filter_type in ["duration", "quality"]:
                filter_value = data.get("filter", "")
                if filter_value:
                    self.videoFilterSelected.emit(filter_value)

    def _on_data_loaded(self, generation: int, videos: list):
        """Callback when videos data is loaded."""
        if generation != self._generation:
            logger.debug(f"[VideosSection] Discarding stale data (gen {generation} vs {self._generation})")
            return

        self._loading = False
        logger.info(f"[VideosSection] Data loaded successfully (gen {generation}, {len(videos)} videos)")

    def _on_error(self, generation: int, error_msg: str):
        """Callback when videos loading fails."""
        if generation != self._generation:
            return

        self._loading = False
        logger.error(f"[VideosSection] Load failed: {error_msg}")
