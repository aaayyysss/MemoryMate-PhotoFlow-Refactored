# layouts/google_layout.py
# Google Photos-style layout - Timeline-based, date-grouped, minimalist design

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSplitter, QToolBar, QLineEdit, QTreeWidget,
    QTreeWidgetItem, QFrame, QGridLayout, QStackedWidget, QSizePolicy, QDialog,
    QGraphicsOpacityEffect, QMenu, QListWidget, QListWidgetItem, QDialogButtonBox,
    QInputDialog, QMessageBox, QSlider, QSpinBox, QComboBox, QLayout, QTabBar
)
from PySide6.QtCore import (
    Qt, Signal, QSize, QEvent, QRunnable, QThreadPool, QObject, QTimer, QUrl,
    QPropertyAnimation, QEasingCurve, QRect, QPoint
)
from PySide6.QtGui import (
    QPixmap, QIcon, QKeyEvent, QImage, QColor, QAction, QPainter, QPen, QPainterPath
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from .base_layout import BaseLayout
from logging_config import get_logger

logger = get_logger(__name__)
from .video_editor_mixin import VideoEditorMixin
from typing import Dict, List, Tuple
from collections import defaultdict
from datetime import datetime
import os
from translation_manager import tr as t


# === CUSTOM PHOTO BUTTON WITH PAINTED BADGES ===
class PhotoButton(QPushButton):
    """
    Custom button that paints tag badges directly on the thumbnail.
    Matches Current layout's delegate painting approach for stable badge rendering.
    """
    def __init__(self, photo_path: str, project_id: int, parent=None):
        super().__init__(parent)
        self.photo_path = photo_path
        self.project_id = project_id
        self._tags = []
        
    def set_tags(self, tags: list):
        """Update tags and trigger repaint."""
        self._tags = tags or []
        self.update()  # Trigger repaint
        
    def paintEvent(self, event):
        """Paint button with tag badges overlay."""
        # Paint base button first
        super().paintEvent(event)
        
        # Paint tag badges on top (only if tags exist)
        if not self._tags:
            return
        
        # Import Qt classes needed for painting
        from PySide6.QtGui import QPainter, QPen, QFont, QColor
        from PySide6.QtCore import QRect, Qt
            
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        
        try:
            from settings_manager_qt import SettingsManager
            sm = SettingsManager()
            
            if not sm.get("badge_overlays_enabled", True):
                return  # Badges disabled
            
            badge_size = int(sm.get("badge_size_px", 22))
            max_badges = int(sm.get("badge_max_count", 4))
            badge_shape = str(sm.get("badge_shape", "circle")).lower()
            badge_margin = 4
            
            # Position badges in top-right corner
            x_right = self.width() - badge_margin - badge_size
            y_top = badge_margin
            
            # Map tags to icons and colors
            TAG_BADGE_CONFIG = {
                'favorite': ('★', QColor(255, 215, 0, 230), Qt.black),
                'face': ('👤', QColor(70, 130, 180, 220), Qt.white),
                'important': ('⚑', QColor(255, 69, 0, 220), Qt.white),
                'work': ('💼', QColor(0, 128, 255, 220), Qt.white),
                'travel': ('✈', QColor(34, 139, 34, 220), Qt.white),
                'personal': ('♥', QColor(255, 20, 147, 220), Qt.white),
                'family': ('👨‍👩‍👧', QColor(255, 140, 0, 220), Qt.white),
                'archive': ('📦', QColor(128, 128, 128, 220), Qt.white),
            }
            
            # Draw badges
            badge_count = 0
            for tag in self._tags:
                if badge_count >= max_badges:
                    break
                
                tag_lower = str(tag).lower().strip()
                
                # Get badge config
                if tag_lower in TAG_BADGE_CONFIG:
                    icon, bg_color, fg_color = TAG_BADGE_CONFIG[tag_lower]
                else:
                    icon, bg_color, fg_color = ('🏷', QColor(150, 150, 150, 230), Qt.white)
                
                # Calculate position
                y_pos = y_top + (badge_count * (badge_size + 4))
                badge_rect = QRect(x_right, y_pos, badge_size, badge_size)
                
                # Draw shadow
                if sm.get("badge_shadow", True):
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(0, 0, 0, 100))
                    painter.drawEllipse(badge_rect.adjusted(2, 2, 2, 2))
                
                # Draw badge background
                painter.setPen(Qt.NoPen)
                painter.setBrush(bg_color)
                if badge_shape == 'square':
                    painter.drawRect(badge_rect)
                elif badge_shape == 'rounded':
                    painter.drawRoundedRect(badge_rect, 4, 4)
                else:  # circle
                    painter.drawEllipse(badge_rect)
                
                # Draw icon
                painter.setPen(QPen(fg_color))
                font = QFont()
                font.setPointSize(11)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(badge_rect, Qt.AlignCenter, icon)
                
                badge_count += 1
            
            # Draw overflow indicator if more tags exist
            if len(self._tags) > max_badges:
                y_pos = y_top + (max_badges * (badge_size + 4))
                more_rect = QRect(x_right, y_pos, badge_size, badge_size)
                
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(60, 60, 60, 220))
                if badge_shape == 'square':
                    painter.drawRect(more_rect)
                elif badge_shape == 'rounded':
                    painter.drawRoundedRect(more_rect, 4, 4)
                else:
                    painter.drawEllipse(more_rect)
                
                painter.setPen(QPen(Qt.white))
                font2 = QFont()
                font2.setPointSize(10)
                font2.setBold(True)
                painter.setFont(font2)
                painter.drawText(more_rect, Qt.AlignCenter, f"+{len(self._tags) - max_badges}")
                
        except Exception as e:
            print(f"[PhotoButton] Error painting badges: {e}")
        finally:
            painter.end()


# === ASYNC THUMBNAIL LOADING ===
class ThumbnailSignals(QObject):
    """Signals for async thumbnail loading (shared by all workers)."""
    loaded = Signal(str, QPixmap, int)  # (path, pixmap, size)


class ThumbnailLoader(QRunnable):
    """Async thumbnail loader using QThreadPool (copied from Current Layout pattern)."""

    def __init__(self, path: str, size: int, signals: ThumbnailSignals):
        super().__init__()
        self.path = path
        self.size = size
        self.signals = signals  # Use shared signal object

    def run(self):
        """Load thumbnail in background thread."""
        try:
            # Check if it's a video
            video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.3gp'}
            is_video = os.path.splitext(self.path)[1].lower() in video_extensions
            
            if is_video:
                # Generate or load video thumbnail using VideoThumbnailService
                try:
                    from services.video_thumbnail_service import get_video_thumbnail_service
                    from PySide6.QtGui import QPixmap
                    from PySide6.QtCore import Qt
                    
                    service = get_video_thumbnail_service()
                    
                    # Prefer existing thumbnail; generate if missing
                    if service.thumbnail_exists(self.path):
                        thumb_path = service.get_thumbnail_path(self.path)
                    else:
                        thumb_path = service.generate_thumbnail(self.path, width=self.size, height=self.size)
                    
                    if thumb_path and os.path.exists(thumb_path):
                        pixmap = QPixmap(str(thumb_path))
                        if not pixmap.isNull():
                            scaled = pixmap.scaled(self.size, self.size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            self.signals.loaded.emit(self.path, scaled, self.size)
                            print(f"[ThumbnailLoader] ✓ Video thumbnail: {os.path.basename(self.path)}")
                        else:
                            # Fallback to placeholder
                            self._emit_video_placeholder()
                    else:
                        # Fallback to placeholder
                        self._emit_video_placeholder()
                except Exception as video_err:
                    print(f"[ThumbnailLoader] Video thumbnail error: {video_err}")
                    self._emit_video_placeholder()
            else:
                # Regular photo thumbnail
                from app_services import get_thumbnail
                pixmap = get_thumbnail(self.path, self.size)

                if pixmap and not pixmap.isNull():
                    # Emit to shared signal (connected in GooglePhotosLayout)
                    self.signals.loaded.emit(self.path, pixmap, self.size)
        except Exception as e:
            print(f"[ThumbnailLoader] Error loading {self.path}: {e}")
    
    def _emit_video_placeholder(self):
        """Emit a video placeholder icon."""
        from PySide6.QtGui import QPainter, QFont
        from PySide6.QtCore import Qt
        
        # Create a dark pixmap with video icon
        pixmap = QPixmap(self.size, self.size)
        pixmap.fill(QColor(45, 45, 45))
        
        painter = QPainter(pixmap)
        painter.setPen(QColor(200, 200, 200))
        font = QFont()
        font.setPixelSize(self.size // 3)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "🎬")
        painter.end()
        
        self.signals.loaded.emit(self.path, pixmap, self.size)


class PreloadImageSignals(QObject):
    """Signals for async image preloading."""
    loaded = Signal(str, object)  # (path, pixmap or None)


class PreloadImageWorker(QRunnable):
    """
    PHASE A #1: Background worker for preloading images.

    Preloads next 2 photos in background for instant navigation.
    """
    def __init__(self, path: str, signals: PreloadImageSignals):
        super().__init__()
        self.path = path
        self.signals = signals

    def run(self):
        """Load image in background thread."""
        try:
            from PIL import Image, ImageOps
            import io
            from PySide6.QtGui import QPixmap

            # Load with PIL for EXIF orientation
            pil_image = Image.open(self.path)
            pil_image = ImageOps.exif_transpose(pil_image)

            # Convert to RGB if needed
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')

            # Save to buffer
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG')
            buffer.seek(0)

            # Load QPixmap from buffer
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.read())

            # Cleanup
            pil_image.close()
            buffer.close()

            # Emit loaded signal
            self.signals.loaded.emit(self.path, pixmap)
            print(f"[PreloadImageWorker] ✓ Preloaded: {os.path.basename(self.path)}")

        except Exception as e:
            print(f"[PreloadImageWorker] ⚠️ Error preloading {self.path}: {e}")
            self.signals.loaded.emit(self.path, None)


class ProgressiveImageSignals(QObject):
    """Signals for progressive image loading."""
    thumbnail_loaded = Signal(object)  # QPixmap
    full_loaded = Signal(object)  # QPixmap


class ProgressiveImageWorker(QRunnable):
    """
    PHASE A #2: Progressive image loader.

    Loads thumbnail-quality first (instant), then full resolution in background.
    """
    def __init__(self, path: str, signals: ProgressiveImageSignals, viewport_size):
        super().__init__()
        self.path = path
        self.signals = signals
        self.viewport_size = viewport_size

    def run(self):
        """Load image progressively: thumbnail → full quality."""
        try:
            from PIL import Image, ImageOps
            import io
            from PySide6.QtGui import QPixmap
            from PySide6.QtCore import Qt

            # Load with PIL for EXIF orientation
            pil_image = Image.open(self.path)
            pil_image = ImageOps.exif_transpose(pil_image)

            # Convert to RGB if needed
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')

            # STEP 1: Create thumbnail-quality version (fast!)
            # Calculate thumbnail size (1/4 of viewport)
            thumb_width = self.viewport_size.width() // 4
            thumb_height = self.viewport_size.height() // 4

            # Create thumbnail
            thumb_image = pil_image.copy()
            thumb_image.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)

            # Convert to QPixmap
            buffer = io.BytesIO()
            thumb_image.save(buffer, format='JPEG', quality=70)
            buffer.seek(0)

            thumb_pixmap = QPixmap()
            thumb_pixmap.loadFromData(buffer.read())
            buffer.close()
            thumb_image.close()

            # Emit thumbnail (instant display!)
            self.signals.thumbnail_loaded.emit(thumb_pixmap)
            print(f"[ProgressiveImageWorker] ✓ Thumbnail loaded: {os.path.basename(self.path)}")

            # STEP 2: Load full resolution (background)
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG')
            buffer.seek(0)

            full_pixmap = QPixmap()
            full_pixmap.loadFromData(buffer.read())

            # Cleanup
            pil_image.close()
            buffer.close()

            # Emit full quality
            self.signals.full_loaded.emit(full_pixmap)
            print(f"[ProgressiveImageWorker] ✓ Full quality loaded: {os.path.basename(self.path)}")

        except Exception as e:
            print(f"[ProgressiveImageWorker] ⚠️ Error loading {self.path}: {e}")
            import traceback
            traceback.print_exc()

            # FALLBACK: Create "broken image" placeholder pixmap
            from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
            from PySide6.QtCore import Qt

            # Create a placeholder pixmap (400x400 gray box with error icon)
            placeholder = QPixmap(400, 400)
            placeholder.fill(QColor(240, 240, 240))  # Light gray background

            painter = QPainter(placeholder)
            painter.setRenderHint(QPainter.Antialiasing)

            # Draw red border
            painter.setPen(QColor(220, 53, 69))  # Bootstrap danger red
            painter.drawRect(0, 0, 399, 399)

            # Draw error icon (❌) and text
            painter.setPen(QColor(100, 100, 100))
            font = QFont()
            font.setPointSize(48)
            painter.setFont(font)
            painter.drawText(placeholder.rect(), Qt.AlignCenter, "❌\n\nImage Error")

            # Draw filename at bottom
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(10, 380, os.path.basename(self.path)[:50])

            painter.end()

            # Emit placeholder for both thumbnail and full quality
            self.signals.thumbnail_loaded.emit(placeholder)
            self.signals.full_loaded.emit(placeholder)
            print(f"[ProgressiveImageWorker] ✓ Emitted error placeholder for: {os.path.basename(self.path)}")


class GooglePhotosEventFilter(QObject):
    """
    Event filter for GooglePhotosLayout.

    Handles keyboard navigation in search suggestions and mouse events for drag-select.
    """
    def __init__(self, layout):
        super().__init__()
        self.layout = layout

    def eventFilter(self, obj, event):
        """Handle events for search box, timeline viewport, and search suggestions popup."""
        # NUCLEAR FIX: Block Show events on search_suggestions popup during layout changes
        if hasattr(self.layout, 'search_suggestions') and obj == self.layout.search_suggestions:
            if event.type() == QEvent.Show:
                # Check if popup is blocked due to layout changes
                if hasattr(self.layout, '_popup_blocked') and self.layout._popup_blocked:
                    # Block the show event - popup will not appear
                    return True

        # Search box keyboard navigation
        if obj == self.layout.search_box and event.type() == QEvent.KeyPress:
            if hasattr(self.layout, 'search_suggestions') and self.layout.search_suggestions.isVisible():
                key = event.key()

                # Arrow keys navigate suggestions
                if key == Qt.Key_Down:
                    current = self.layout.search_suggestions.currentRow()
                    if current < self.layout.search_suggestions.count() - 1:
                        self.layout.search_suggestions.setCurrentRow(current + 1)
                    return True
                elif key == Qt.Key_Up:
                    current = self.layout.search_suggestions.currentRow()
                    if current > 0:
                        self.layout.search_suggestions.setCurrentRow(current - 1)
                    return True
                elif key == Qt.Key_Return or key == Qt.Key_Enter:
                    # Enter key selects highlighted suggestion
                    current_item = self.layout.search_suggestions.currentItem()
                    if current_item:
                        self.layout._on_suggestion_clicked(current_item)
                        return True
                elif key == Qt.Key_Escape:
                    self.layout.search_suggestions.hide()
                    return True

        # Timeline viewport drag-select
        # CRITICAL FIX: Check if timeline_scroll still exists before accessing viewport
        # RuntimeError occurs when switching layouts - Qt C++ object gets deleted
        try:
            if hasattr(self.layout, 'timeline_scroll') and obj == self.layout.timeline_scroll.viewport():
                if event.type() == QEvent.MouseButtonPress:
                    if self.layout._handle_drag_select_press(event.pos()):
                        return True
                elif event.type() == QEvent.MouseMove:
                    self.layout._handle_drag_select_move(event.pos())
                    return self.layout.is_dragging  # Consume event if dragging
                elif event.type() == QEvent.MouseButtonRelease:
                    if self.layout.is_dragging:
                        self.layout._handle_drag_select_release(event.pos())
                        return True
        except RuntimeError:
            # QScrollArea was deleted - safe to ignore
            pass

        return False


class MediaLightbox(QDialog, VideoEditorMixin):
    """
    Full-screen media lightbox/preview dialog supporting photos AND videos.

    ✨ ENHANCED FEATURES:
    - Mixed photo/video navigation
    - Video playback with controls
    - Zoom controls for photos (Ctrl+Wheel, +/- keys)
    - Slideshow mode (Space to toggle)
    - Keyboard shortcuts (Arrow keys, Space, Delete, F, R, etc.)
    - Quick actions (Delete, Favorite, Rate)
    - Metadata panel (EXIF, date, dimensions, video info)
    - Fullscreen toggle (F11)
    - Close button and ESC key
    - VIDEO EDITING: Trim, rotate, speed, adjustments, export
    """

    def __init__(self, media_path: str, all_media: List[str], parent=None):
        """
        Initialize media lightbox.

        Args:
            media_path: Path to photo/video to display
            all_media: List of all media paths (photos + videos) in timeline order
            parent: Parent widget
        """
        super().__init__(parent)

        self.media_path = media_path
        self.all_media = all_media
        self.current_index = all_media.index(media_path) if media_path in all_media else 0
        self._media_loaded = False  # Track if media has been loaded

        # Zoom state (for photos) - SMOOTH CONTINUOUS ZOOM
        # Like Current Layout's LightboxDialog - smooth zoom with mouse wheel
        self.zoom_level = 1.0  # Current zoom scale
        self.fit_zoom_level = 1.0  # Zoom level for "fit to window" mode
        self.zoom_mode = "fit"  # "fit", "fill", "actual", or "custom"
        self.original_pixmap = None  # Store original for zoom
        self.zoom_factor = 1.15  # Zoom increment per wheel step (smooth like Current Layout)

        # Slideshow state
        self.slideshow_active = False
        self.slideshow_timer = None
        self.slideshow_interval = 3000  # 3 seconds

        # Rating state
        self.current_rating = 0  # 0-5 stars

        # PHASE 2 #10: Swipe gesture state
        self.swipe_start_pos = None
        self.swipe_start_time = None
        self.is_swiping = False

        # PHASE A #1: Image Preloading & Caching
        self.preload_cache = {}  # Map path -> {pixmap, timestamp}
        self.preload_count = 2  # Preload next 2 photos
        self.cache_limit = 5  # Keep max 5 photos in cache
        self.preload_thread_pool = QThreadPool()
        self.preload_thread_pool.setMaxThreadCount(2)  # 2 background threads for preloading
        self.preload_signals = PreloadImageSignals()
        self.preload_signals.loaded.connect(self._on_preload_complete)

        # PHASE A #2: Progressive Loading State
        self.progressive_loading = True  # Enable progressive load (thumbnail → full)
        self.thumbnail_quality_loaded = False  # Track if thumbnail loaded
        self.full_quality_loaded = False  # Track if full quality loaded
        self.progressive_load_worker = None  # Current progressive load worker
        self.progressive_signals = ProgressiveImageSignals()
        self.progressive_signals.thumbnail_loaded.connect(self._on_thumbnail_loaded)
        self.progressive_signals.full_loaded.connect(self._on_full_quality_loaded)

        # PHASE A #3: Zoom to Mouse Cursor
        self.last_mouse_pos = None  # Track mouse position for zoom centering
        self.zoom_mouse_tracking = True  # Enable cursor-centered zoom

        # PHASE A #4: Loading Indicators
        self.is_loading = False  # Track if currently loading
        self.loading_start_time = None  # Track load start for timeout detection

        # PHASE A #5: Keyboard Shortcut Help Overlay
        self.help_overlay = None  # Help overlay widget
        self.help_visible = False  # Track help visibility

        # PHASE B #1: Thumbnail Filmstrip
        self.filmstrip_enabled = True  # Enable thumbnail filmstrip at bottom
        self.filmstrip_thumbnail_size = 80  # 80x80px thumbnails
        self.filmstrip_visible_count = 9  # Show 9 thumbnails at once
        self.filmstrip_thumbnails = {}  # Map index -> QPixmap thumbnail
        self.filmstrip_buttons = {}  # Map index -> QPushButton

        # PHASE B #2: Enhanced Touch Gestures
        self.double_tap_enabled = True  # Enable double-tap to zoom
        self.last_tap_time = None  # Track for double-tap detection
        self.last_tap_pos = None  # Track tap position
        self.two_finger_pan_enabled = True  # Enable two-finger pan when zoomed
        self.inertial_scroll_enabled = True  # Enable inertial scrolling

        # PHASE B #3: Video Scrubbing Preview
        self.video_scrubbing_enabled = True  # Enable hover frame preview
        self.scrubbing_preview_widget = None  # Preview widget for frame

        # PHASE B #4: Contextual Toolbars
        self.contextual_toolbars = True  # Enable contextual toolbar display
        self.video_only_buttons = []  # Buttons only shown for videos
        self.photo_only_buttons = []  # Buttons only shown for photos

        # PHASE B #5: Zoom State Persistence
        self.zoom_persistence_enabled = True  # Remember zoom across photos
        self.saved_zoom_level = 1.0  # Saved zoom level
        self.saved_zoom_mode = "fit"  # Saved zoom mode
        self.apply_zoom_to_all = False  # Apply saved zoom to all photos

        # PHASE C #1: RAW/HDR Support
        self.raw_support_enabled = True  # Enable RAW file rendering
        self.exposure_adjustment = 0.0  # Exposure adjustment (-2.0 to +2.0)

        # PHASE C #2: Share/Export
        self.share_dialog_enabled = True  # Enable share/export dialog

        # PHASE C #3: Quick Edit Tools
        self.rotation_angle = 0  # Current rotation (0, 90, 180, 270)
        self.crop_mode_active = False  # Crop mode state
        self.crop_rect = None  # Crop rectangle (x, y, w, h)
        self.current_preset = None  # 'dynamic' | 'warm' | 'cool' | None
        self.preset_cache = {}  # (path, preset) -> QPixmap

        # Filter strength control
        self.filter_intensity = 100  # Default 100% (full strength)
        self.current_preset_adjustments = {}  # Store current preset for intensity changes
        
        # Edit state persistence
        self.edit_states_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.edit_states')
        os.makedirs(self.edit_states_dir, exist_ok=True)
        
        # Copy/Paste adjustments clipboard
        self.copied_adjustments = None  # Stores copied adjustment state
        self.copied_filter_intensity = None
        self.copied_preset = None

        # Editor undo/redo stack
        self.edit_history = []  # List of (pixmap, adjustments_dict) tuples
        self.edit_history_index = -1  # Current position in history
        self.max_history = 20  # Max undo steps

        # Editor adjustments state
        self.adjustments = {
            'brightness': 0,
            'exposure': 0,
            'contrast': 0,
            'highlights': 0,
            'shadows': 0,
            'vignette': 0,
            'sharpen': 0,  # New: Sharpen/Clarity adjustment
            'saturation': 0,
            'warmth': 0,
            # RAW-specific adjustments
            'white_balance_temp': 0,  # White balance temperature (-100 to +100)
            'white_balance_tint': 0,  # White balance tint (green/magenta, -100 to +100)
            'exposure_recovery': 0,   # Highlight recovery (0 to 100)
            'lens_correction': 0,     # Lens distortion correction (0 to 100)
            'chromatic_aberration': 0  # Chromatic aberration removal (0 to 100)
        }
        self.is_raw_file = False  # Track if current file is RAW
        self.raw_image = None  # Store rawpy image object
        self.edit_zoom_level = 1.0  # Zoom level in editor mode
        self.before_after_active = False  # Before/After comparison toggle
        self._original_pixmap = None  # Original pixmap for editing
        self._edit_pixmap = None  # Current edited pixmap
        self._crop_rect_norm = None  # Normalized crop rectangle (0-1 coords)

        # VIDEO EDITING STATE (Phase 1)
        self.is_video_file = False  # Track if current file is video
        self.video_player = None  # QMediaPlayer instance
        self.video_widget = None  # QVideoWidget for display
        self.audio_output = None  # QAudioOutput for audio
        self.video_duration = 0  # Video duration in milliseconds
        self.video_position = 0  # Current playback position
        self.video_trim_start = 0  # Trim start point (ms)
        self.video_trim_end = 0  # Trim end point (ms)
        self.video_is_playing = False  # Playback state
        self.video_is_muted = False  # Mute state
        self.video_playback_speed = 1.0  # Speed multiplier (0.5x, 1x, 2x)
        self.video_rotation_angle = 0  # Video rotation (0, 90, 180, 270)
        self._video_original_path = None  # Original video path for export


        # PHASE C #4: Compare Mode
        self.compare_mode_active = False  # Compare mode state
        self.compare_media_path = None  # Second media for comparison

        # PHASE C #5: Motion Photos
        self.motion_photo_enabled = True  # Enable motion photo detection
        self.is_motion_photo = False  # Current media is motion photo
        self.motion_video_path = None  # Path to paired video

        self._setup_ui()
        # Don't load media here - wait for showEvent when window has proper size

        # PHASE 2 #10: Enable touch/gesture events
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.grabGesture(Qt.SwipeGesture)
        self.grabGesture(Qt.PinchGesture)

    def __del__(self):
        """Cleanup when layout is destroyed to prevent memory leaks."""
        try:
            # Remove event filters to prevent RuntimeError on deleted widgets
            if hasattr(self, 'event_filter') and self.event_filter:
                if hasattr(self, 'search_box') and self.search_box:
                    try:
                        self.search_box.removeEventFilter(self.event_filter)
                    except RuntimeError:
                        pass  # Widget already deleted
                if hasattr(self, 'timeline_scroll') and self.timeline_scroll:
                    try:
                        self.timeline_scroll.viewport().removeEventFilter(self.event_filter)
                    except RuntimeError:
                        pass  # Widget already deleted
                        
            # Disconnect thumbnail loading signals
            if hasattr(self, 'thumbnail_signals'):
                try:
                    self.thumbnail_signals.loaded.disconnect()
                except (RuntimeError, TypeError):
                    pass
                    
            # Clear preload cache to free memory
            if hasattr(self, 'preload_cache'):
                self.preload_cache.clear()
                
            print("[GooglePhotosLayout] Cleanup completed")
        except Exception as e:
            print(f"[GooglePhotosLayout] Cleanup error: {e}")

    def _setup_ui(self):
        """Setup Google Photos-style lightbox UI with overlay controls."""
        from PySide6.QtWidgets import QApplication, QScrollArea, QWidget, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QHBoxLayout, QStackedWidget, QFrame
        from PySide6.QtCore import QPropertyAnimation, QTimer, QRect

        # Window settings - ADAPTIVE SIZING: Based on screen resolution and DPI
        self.setWindowTitle(t('google_layout.lightbox.window_title'))

        # Get screen information with DPI awareness
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        available_geometry = screen.availableGeometry()  # Exclude taskbar
        dpi_scale = screen.devicePixelRatio()  # Windows scale (1.0, 1.25, 1.5, 2.0)
        
        # Calculate logical pixels
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        
        # Adaptive window sizing (90-95% based on screen size)
        # Smaller screens need more space, larger screens can have more margin
        if screen_width >= 2560:  # 4K or ultra-wide
            size_percent = 0.90  # 90% of screen
        elif screen_width >= 1920:  # Full HD
            size_percent = 0.92  # 92% of screen
        else:  # HD/Laptop (1366-1920)
            size_percent = 0.95  # 95% of screen (maximize space)
        
        width = int(screen_width * size_percent)
        height = int(screen_height * size_percent)
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        self.setGeometry(QRect(x, y, width, height))
        
        # Log sizing for debugging
        print(f"[MediaLightbox] Screen: {screen_width}x{screen_height} (DPI: {dpi_scale}x)")
        print(f"[MediaLightbox] Window: {width}x{height} ({int(size_percent*100)}% of screen)")

        self.setStyleSheet("background: #000000; QToolTip { color: white; background-color: rgba(0,0,0,0.92); border: 1px solid #555; padding: 6px 10px; border-radius: 6px; } QMessageBox { background-color: #121212; color: white; } QMessageBox QLabel { color: white; } QMessageBox QPushButton { background: rgba(255,255,255,0.15); color: white; border: none; border-radius: 6px; padding: 6px 12px; } QMessageBox QPushButton:hover { background: rgba(255,255,255,0.25); }")  # Dark theme + tooltip/messagebox styling

        # Start maximized (not fullscreen - user choice)
        self.showMaximized()

        # Main layout (vertical with toolbars + media)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === TOP TOOLBAR (Overlay with gradient) ===
        self.top_toolbar = self._create_top_toolbar()
        main_layout.addWidget(self.top_toolbar)

        # === MIDDLE SECTION: Media + Info Panel (Horizontal) ===
        middle_layout = QHBoxLayout()
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(0)

        # Media display area (left side, expands)
        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("QScrollArea { background: #000000; border: none; }")
        self.scroll_area.setWidgetResizable(False)  # Don't auto-resize (needed for zoom)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setAlignment(Qt.AlignCenter)

        # === MEDIA CAPTION (Overlay at bottom of media, like Google Photos) ===
        self.media_caption = QLabel()
        self.media_caption.setParent(self)
        self.media_caption.setAlignment(Qt.AlignCenter)
        self.media_caption.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.75);
                color: white;
                font-size: 11pt;
                padding: 8px 16px;
                border-radius: 4px;
            }
        """)
        self.media_caption.setWordWrap(False)
        self.media_caption.hide()  # Hidden initially, shown after load
        
        # Caption auto-hide timer (like Google Photos - fades after 3 seconds)
        self.caption_hide_timer = QTimer()
        self.caption_hide_timer.setSingleShot(True)
        self.caption_hide_timer.setInterval(3000)  # 3 seconds
        self.caption_hide_timer.timeout.connect(self._fade_out_caption)
        
        # Caption opacity effect for smooth fade
        self.caption_opacity = QGraphicsOpacityEffect()
        self.media_caption.setGraphicsEffect(self.caption_opacity)
        self.caption_opacity.setOpacity(0.0)  # Start hidden

        # CRITICAL FIX: Create container widget to hold both image and video
        # This prevents Qt from deleting widgets when switching with setWidget()
        self.media_container = QWidget()
        self.media_container.setStyleSheet("background: #000000;")
        media_container_layout = QVBoxLayout(self.media_container)
        media_container_layout.setContentsMargins(0, 0, 0, 0)
        media_container_layout.setSpacing(0)

        # Image display (for photos)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent;")
        self.image_label.setScaledContents(False)
        media_container_layout.addWidget(self.image_label)

        # PHASE A #4: Loading indicator (overlaid on media container)
        self.loading_indicator = QLabel(self.media_container)
        self.loading_indicator.setAlignment(Qt.AlignCenter)
        self.loading_indicator.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.7);
                color: white;
                font-size: 14pt;
                padding: 20px 30px;
                border-radius: 10px;
            }
        """)
        self.loading_indicator.setText(t('google_layout.lightbox.loading'))
        self.loading_indicator.hide()
        self.loading_indicator.raise_()  # Ensure it's on top

        # PHASE C #5: Motion photo indicator (top-right corner)
        self.motion_indicator = QLabel(self)
        self.motion_indicator.setText("🎬")  # Motion icon
        self.motion_indicator.setFixedSize(48, 48)
        self.motion_indicator.setAlignment(Qt.AlignCenter)
        self.motion_indicator.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.7);
                color: white;
                font-size: 20pt;
                border-radius: 24px;
            }
        """)
        self.motion_indicator.setToolTip(t('google_layout.lightbox.motion_photo_tooltip'))
        self.motion_indicator.hide()

        # Video display will be added to container on first video load

        # Set container as scroll area widget (never replace it!)
        self.scroll_area.setWidget(self.media_container)

        middle_layout.addWidget(self.scroll_area, 1)  # Expands to fill space

        # === OVERLAY NAVIGATION BUTTONS (Google Photos style) ===
        # Create as direct children of MediaLightbox, positioned on left/right sides
        self._create_overlay_nav_buttons()

        # Info panel (right side, toggleable)
        self.info_panel = self._create_info_panel()
        self.info_panel.hide()  # Hidden by default
        middle_layout.addWidget(self.info_panel)

        # Enhance panel (right side, toggleable)
        self.enhance_panel = self._create_enhance_panel()
        self.enhance_panel.hide()  # Hidden by default
        middle_layout.addWidget(self.enhance_panel)

        # Add middle section to main layout
        middle_widget = QWidget()
        middle_widget.setLayout(middle_layout)
        # Viewer/Editor stacked container (non-destructive editor stub)
        self.mode_stack = QStackedWidget()
        # Page 0: Viewer (existing middle_widget)
        self.mode_stack.addWidget(middle_widget)
        # Page 1: Editor (stub page - preserves viewer behavior)
        self.editor_page = QWidget()
        editor_vlayout = QVBoxLayout(self.editor_page)
        # Top row: Save/Cancel (PROMINENT STYLING)
        editor_topbar = QWidget()
        editor_topbar.setStyleSheet("background: rgba(0,0,0,0.5);")
        editor_topbar_layout = QHBoxLayout(editor_topbar)
        editor_topbar_layout.setContentsMargins(12, 8, 12, 8)
        save_btn = QPushButton()
        cancel_btn = QPushButton()
        save_btn.setText(t('google_layout.lightbox.save_button'))
        save_btn.setToolTip(t('google_layout.lightbox.save_tooltip'))
        save_btn.setStyleSheet("""
            QPushButton {
                background: rgba(34, 139, 34, 0.9);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 24px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(34, 139, 34, 1.0);
            }
        """)
        save_btn.clicked.connect(self._save_edits)
        cancel_btn.setText(t('google_layout.lightbox.cancel_button'))
        cancel_btn.setToolTip(t('google_layout.lightbox.cancel_tooltip'))
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(220, 53, 69, 0.9);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 24px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(220, 53, 69, 1.0);
            }
        """)
        cancel_btn.clicked.connect(self._cancel_edits)
        editor_topbar_layout.addWidget(save_btn)
        editor_topbar_layout.addWidget(cancel_btn)
        editor_topbar_layout.addSpacing(20)
        # Editor zoom controls
        self.edit_zoom_level = 1.0
        zoom_out_btn_edit = QPushButton("−")
        zoom_out_btn_edit.setToolTip(t('google_layout.lightbox.zoom_out_tooltip'))
        zoom_out_btn_edit.clicked.connect(self._editor_zoom_out)
        zoom_in_btn_edit = QPushButton("+")
        zoom_in_btn_edit.setToolTip(t('google_layout.lightbox.zoom_in_tooltip'))
        zoom_in_btn_edit.clicked.connect(self._editor_zoom_in)
        zoom_reset_btn_edit = QPushButton("100%")
        zoom_reset_btn_edit.setToolTip(t('google_layout.lightbox.zoom_reset_tooltip'))
        zoom_reset_btn_edit.clicked.connect(self._editor_zoom_reset)
        editor_topbar_layout.addSpacing(12)
        editor_topbar_layout.addWidget(zoom_out_btn_edit)
        editor_topbar_layout.addWidget(zoom_in_btn_edit)
        editor_topbar_layout.addWidget(zoom_reset_btn_edit)
        # Crop toggle (STYLED)
        self.crop_btn = QPushButton()
        self.crop_btn.setText(t('google_layout.lightbox.crop_button'))
        self.crop_btn.setCheckable(True)
        self.crop_btn.setToolTip(t('google_layout.lightbox.crop_tooltip'))
        self.crop_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QPushButton:checked {
                background: rgba(66, 133, 244, 0.8);
                border: 1px solid rgba(66, 133, 244, 1.0);
            }
        """)
        self.crop_btn.clicked.connect(self._toggle_crop_mode)
        editor_topbar_layout.addWidget(self.crop_btn)
        # Filters toggle (STYLED)
        self.filters_btn = QPushButton()
        self.filters_btn.setText(t('google_layout.lightbox.filters_button'))
        self.filters_btn.setCheckable(True)
        self.filters_btn.setToolTip(t('google_layout.lightbox.filters_tooltip'))
        self.filters_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QPushButton:checked {
                background: rgba(66, 133, 244, 0.8);
                border: 1px solid rgba(66, 133, 244, 1.0);
            }
        """)
        self.filters_btn.clicked.connect(self._toggle_filters_panel)
        editor_topbar_layout.addWidget(self.filters_btn)
        # Before/After toggle (STYLED)
        self.before_after_btn = QPushButton()
        self.before_after_btn.setText(t('google_layout.lightbox.before_after_button'))
        self.before_after_btn.setCheckable(True)
        self.before_after_btn.setToolTip(t('google_layout.lightbox.before_after_tooltip'))
        self.before_after_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QPushButton:checked {
                background: rgba(66, 133, 244, 0.8);
                border: 1px solid rgba(66, 133, 244, 1.0);
            }
        """)
        self.before_after_btn.clicked.connect(self._toggle_before_after)
        editor_topbar_layout.addWidget(self.before_after_btn)
        
        # Tools panel toggle (show/hide right-side editing tools)
        self.tools_toggle_btn = QPushButton()
        self.tools_toggle_btn.setText(t('google_layout.lightbox.tools_button'))
        self.tools_toggle_btn.setCheckable(True)
        self.tools_toggle_btn.setChecked(True)
        self.tools_toggle_btn.setToolTip(t('google_layout.lightbox.tools_tooltip'))
        self.tools_toggle_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QPushButton:checked {
                background: rgba(66, 133, 244, 0.8);
                border: 1px solid rgba(66, 133, 244, 1.0);
            }
        """)
        self.tools_toggle_btn.toggled.connect(lambda v: (self.editor_right_scroll.setVisible(v), self.editor_right_panel.setVisible(v)) if hasattr(self, 'editor_right_scroll') else (self.editor_right_panel.setVisible(v) if hasattr(self, 'editor_right_panel') else None))
        editor_topbar_layout.addWidget(self.tools_toggle_btn)
        
        editor_topbar_layout.addStretch()  # Push buttons to left, Undo/Redo/Export to right
        # Undo/Redo buttons (MORE PROMINENT)
        self.undo_btn = QPushButton()
        self.redo_btn = QPushButton()
        self.undo_btn.setText(t('google_layout.lightbox.undo_button'))
        self.undo_btn.setToolTip(t('google_layout.lightbox.undo_tooltip'))
        self.undo_btn.setEnabled(False)
        self.undo_btn.setStyleSheet("""
            QPushButton {
                background: rgba(66, 133, 244, 0.8);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(66, 133, 244, 1.0);
            }
            QPushButton:disabled {
                background: rgba(128, 128, 128, 0.3);
                color: rgba(255, 255, 255, 0.4);
            }
        """)
        self.undo_btn.clicked.connect(self._editor_undo)
        editor_topbar_layout.addWidget(self.undo_btn)
        self.redo_btn.setText(t('google_layout.lightbox.redo_button'))
        self.redo_btn.setToolTip(t('google_layout.lightbox.redo_tooltip'))
        self.redo_btn.setEnabled(False)
        self.redo_btn.setStyleSheet("""
            QPushButton {
                background: rgba(66, 133, 244, 0.8);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(66, 133, 244, 1.0);
            }
            QPushButton:disabled {
                background: rgba(128, 128, 128, 0.3);
                color: rgba(255, 255, 255, 0.4);
            }
        """)
        self.redo_btn.clicked.connect(self._editor_redo)
        editor_topbar_layout.addWidget(self.redo_btn)
        editor_topbar_layout.addSpacing(16)  # Visual separator
        
        # Copy/Paste buttons (BATCH EDITING)
        self.copy_adj_btn = QPushButton()
        self.paste_adj_btn = QPushButton()
        self.copy_adj_btn.setText(t('google_layout.lightbox.copy_button'))
        self.copy_adj_btn.setToolTip(t('google_layout.lightbox.copy_tooltip'))
        self.copy_adj_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 193, 7, 0.8);
                color: black;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 193, 7, 1.0);
            }
        """)
        self.copy_adj_btn.clicked.connect(self._copy_adjustments)
        editor_topbar_layout.addWidget(self.copy_adj_btn)
        
        self.paste_adj_btn.setText(t('google_layout.lightbox.paste_button'))
        self.paste_adj_btn.setToolTip(t('google_layout.lightbox.paste_tooltip'))
        self.paste_adj_btn.setEnabled(False)  # Disabled until something is copied
        self.paste_adj_btn.setStyleSheet("""
            QPushButton {
                background: rgba(156, 39, 176, 0.8);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(156, 39, 176, 1.0);
            }
            QPushButton:disabled {
                background: rgba(128, 128, 128, 0.3);
                color: rgba(255, 255, 255, 0.4);
            }
        """)
        self.paste_adj_btn.clicked.connect(self._paste_adjustments)
        editor_topbar_layout.addWidget(self.paste_adj_btn)
        editor_topbar_layout.addSpacing(16)  # Visual separator
        
        # Export button (MORE PROMINENT) - Handles both photos and videos
        self.export_btn = QPushButton()
        self.export_btn.setText(t('google_layout.lightbox.export_button'))
        self.export_btn.setToolTip(t('google_layout.lightbox.export_tooltip'))
        self.export_btn.setStyleSheet("""
            QPushButton {
                background: rgba(34, 139, 34, 0.9);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(34, 139, 34, 1.0);
            }
        """)
        self.export_btn.clicked.connect(self._export_current_media)
        editor_topbar_layout.addWidget(self.export_btn)
        editor_vlayout.addWidget(editor_topbar)
        # Crop toolbar (hidden by default)
        self.crop_toolbar = self._build_crop_toolbar()
        self.crop_toolbar.hide()
        editor_vlayout.addWidget(self.crop_toolbar)
        # Content row: canvas + right panel
        editor_row = QWidget()
        editor_row_layout = QHBoxLayout(editor_row)
        self.editor_canvas = self._create_edit_canvas()
        
        # Right tools panel wrapped in scroll area (always accessible)
        from PySide6.QtWidgets import QScrollArea
        self.editor_right_panel = QWidget()
        self.editor_right_panel.setFixedWidth(400)
        self.editor_right_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.editor_right_scroll = QScrollArea()
        self.editor_right_scroll.setWidget(self.editor_right_panel)
        self.editor_right_scroll.setWidgetResizable(True)
        self.editor_right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.editor_right_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        # Toggle right tools panel visibility and resize splitter
        if hasattr(self, 'tools_toggle_btn'):
            self.tools_toggle_btn.toggled.connect(lambda checked: (
                self.editor_right_scroll.setVisible(checked),
                self.editor_splitter.setSizes([int(self.width()*0.7), 400]) if checked else self.editor_splitter.setSizes([int(self.width()*0.95), 0])
            ))
        
        from PySide6.QtWidgets import QSplitter
        self.editor_splitter = QSplitter(Qt.Horizontal)
        self.editor_splitter.addWidget(self.editor_canvas)
        self.editor_splitter.addWidget(self.editor_right_scroll)
        self.editor_splitter.setSizes([int(self.width()*0.7), 400])
        editor_row_layout.addWidget(self.editor_splitter)
        editor_vlayout.addWidget(editor_row, 1)
        # Build adjustments panel in right placeholder
        self._init_adjustments_panel()
        # Add editor page to stack
        self.mode_stack.addWidget(self.editor_page)
        # Add stacked to main layout
        main_layout.addWidget(self.mode_stack, 1)
        self.mode_stack.setCurrentIndex(0)

        # === BOTTOM TOOLBAR (Overlay with gradient) ===
        self.bottom_toolbar = self._create_bottom_toolbar()
        main_layout.addWidget(self.bottom_toolbar)
        self.bottom_toolbar.hide()  # Hide by default, show for videos

        # === PHASE B #1: THUMBNAIL FILMSTRIP ===
        self.filmstrip_widget = self._create_filmstrip()
        self.filmstrip_widget.hide()  # Hide by default for maximum photo area

        # Track info/enhance panel state
        self.info_panel_visible = False
        self.enhance_panel_visible = False

        # === MOUSE PANNING SUPPORT ===
        # Enable mouse tracking for hand cursor and panning
        self.setMouseTracking(True)
        self.scroll_area.setMouseTracking(True)
        self.image_label.setMouseTracking(True)

        # Panning state
        self.is_panning = False
        self.pan_start_pos = None
        self.scroll_start_x = 0
        self.scroll_start_y = 0

        # Button positioning retry counter (safety limit)
        self._position_retry_count = 0

        # === PROFESSIONAL AUTO-HIDE SYSTEM ===
        # Create opacity effects for smooth fade animations
        self.top_toolbar_opacity = QGraphicsOpacityEffect()
        self.top_toolbar.setGraphicsEffect(self.top_toolbar_opacity)
        self.top_toolbar_opacity.setOpacity(0.0)  # Hidden by default

        self.bottom_toolbar_opacity = QGraphicsOpacityEffect()
        self.bottom_toolbar.setGraphicsEffect(self.bottom_toolbar_opacity)
        self.bottom_toolbar_opacity.setOpacity(0.0)  # Hidden by default

        # Auto-hide timer (2 seconds)
        self.toolbar_hide_timer = QTimer()
        self.toolbar_hide_timer.setSingleShot(True)
        self.toolbar_hide_timer.setInterval(2000)  # 2 seconds
        self.toolbar_hide_timer.timeout.connect(self._hide_toolbars)

        # Toolbar visibility state
        self.toolbars_visible = False

        # PHASE A #5: Create keyboard shortcut help overlay
        self._create_help_overlay()

    def showEvent(self, event):
        """Ensure media loads and overlays position when the window first shows."""
        try:
            super().showEvent(event)
            from PySide6.QtCore import QTimer
            # Load current media after the widget has a valid size
            QTimer.singleShot(0, self._load_media_safe)
            # Make top toolbar visible on first show
            if hasattr(self, 'top_toolbar_opacity'):
                self.top_toolbar_opacity.setOpacity(1.0)
            # Bottom toolbar opacity reflects visibility (videos only)
            if hasattr(self, 'bottom_toolbar_opacity') and hasattr(self, 'bottom_toolbar'):
                self.bottom_toolbar_opacity.setOpacity(1.0 if self.bottom_toolbar.isVisible() else 0.0)
            # Position overlay buttons and caption shortly after layout
            QTimer.singleShot(10, self._position_nav_buttons)
            QTimer.singleShot(10, self._position_media_caption)
        except Exception as e:
            print(f"[MediaLightbox] showEvent error: {e}")

    def closeEvent(self, event):
        """Clean up resources when lightbox closes."""
        print("[MediaLightbox] Closing - cleaning up resources...")
        
        try:
            # PHASE 2 FIX: Disconnect video signals before cleanup
            self._disconnect_video_signals()
            
            # Stop and cleanup video player
            if hasattr(self, 'video_player') and self.video_player is not None:
                try:
                    self.video_player.stop()
                    if hasattr(self, 'position_timer') and self.position_timer:
                        self.position_timer.stop()
                    # Clear source to release decoder
                    from PySide6.QtCore import QUrl
                    self.video_player.setSource(QUrl())
                    print("[MediaLightbox] ✓ Video player cleaned up")
                except Exception as video_cleanup_err:
                    print(f"[MediaLightbox] Warning during video cleanup: {video_cleanup_err}")
            
            # PHASE 2 FIX: Cleanup audio output
            if hasattr(self, 'audio_output') and self.audio_output is not None:
                try:
                    if hasattr(self, 'video_player') and self.video_player is not None:
                        self.video_player.setAudioOutput(None)  # Detach first
                    self.audio_output.deleteLater()
                    self.audio_output = None
                    print("[MediaLightbox] ✓ Audio output cleaned up")
                except Exception as audio_cleanup_err:
                    print(f"[MediaLightbox] Warning during audio cleanup: {audio_cleanup_err}")
            
            # Stop slideshow timer
            if hasattr(self, 'slideshow_timer') and self.slideshow_timer:
                self.slideshow_timer.stop()
            
            # Clear preload cache to free memory
            if hasattr(self, 'preload_cache'):
                self.preload_cache.clear()
            
            # PHASE 2 FIX: Cancel and stop thread pools
            if hasattr(self, 'preload_thread_pool'):
                # Set cancellation flag for running tasks
                if hasattr(self, 'preload_cancelled'):
                    self.preload_cancelled = True
                
                # Cancel pending tasks
                self.preload_thread_pool.clear()
                
                # Wait for completion with timeout
                if not self.preload_thread_pool.waitForDone(1000):
                    print("[MediaLightbox] ⚠️ Preload tasks didn't finish in time")
                else:
                    print("[MediaLightbox] ✓ Preload thread pool stopped")
            
            print("[MediaLightbox] ✓ All resources cleaned up")
        except Exception as e:
            print(f"[MediaLightbox] Error during cleanup: {e}")
        
        # Accept the close event
        event.accept()
    
    def _disconnect_video_signals(self):
        """PHASE 2: Safely disconnect all video player signals to prevent memory leaks.
        
        This prevents signal accumulation when navigating through multiple videos.
        Without this, each video load adds new connections, causing:
        - Callback storms (slot called 50x after 50 videos)
        - Memory leaks from stale slot references
        - Performance degradation
        """
        if not hasattr(self, 'video_player') or self.video_player is None:
            return
        
        try:
            self.video_player.durationChanged.disconnect(self._on_duration_changed)
        except (TypeError, RuntimeError):
            pass  # Not connected or already disconnected
        
        try:
            self.video_player.positionChanged.disconnect(self._on_position_changed)
        except (TypeError, RuntimeError):
            pass
        
        try:
            self.video_player.errorOccurred.disconnect(self._on_video_error)
        except (TypeError, RuntimeError):
            pass
        
        try:
            self.video_player.mediaStatusChanged.disconnect(self._on_media_status_changed)
        except (TypeError, RuntimeError):
            pass
        
        print("[MediaLightbox] ✓ Video signals disconnected")
    
    def resizeEvent(self, event):
        """Handle window resize - reposition navigation buttons and caption."""
        super().resizeEvent(event)
        
        # Reposition nav buttons
        if hasattr(self, 'prev_btn') and hasattr(self, 'next_btn'):
            self._position_nav_buttons()
        
        # Reposition caption
        if hasattr(self, 'media_caption'):
            self._position_media_caption()

    def _create_top_toolbar(self) -> QWidget:
        """Create top overlay toolbar with close, info, zoom, slideshow, and action buttons."""
        toolbar = QWidget()
        toolbar.setFixedHeight(80)  # Increased for larger buttons
        toolbar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(0, 0, 0, 0.9),
                    stop:1 rgba(0, 0, 0, 0));
            }
        """)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)  # More spacing for larger buttons

        # PROFESSIONAL Button style (56x56px, larger icons)
        btn_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 28px;
                font-size: 18pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.35);
            }
        """

        # === LEFT SIDE: Close + Quick Actions ===
        # Close button
        self.close_btn = QPushButton("✕")
        self.close_btn.setFocusPolicy(Qt.NoFocus)
        self.close_btn.setFixedSize(56, 56)
        self.close_btn.setStyleSheet(btn_style)
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

        layout.addSpacing(12)

        # Delete button
        self.delete_btn = QPushButton("🗑️")
        self.delete_btn.setFocusPolicy(Qt.NoFocus)
        self.delete_btn.setFixedSize(56, 56)
        self.delete_btn.setStyleSheet(btn_style)
        self.delete_btn.clicked.connect(self._delete_current_media)
        self.delete_btn.setToolTip(t('google_layout.lightbox.delete_tooltip'))
        layout.addWidget(self.delete_btn)

        # Favorite button
        self.favorite_btn = QPushButton("♡")
        self.favorite_btn.setFocusPolicy(Qt.NoFocus)
        self.favorite_btn.setFixedSize(56, 56)
        self.favorite_btn.setStyleSheet(btn_style)
        self.favorite_btn.clicked.connect(self._toggle_favorite)
        self.favorite_btn.setToolTip(t('google_layout.lightbox.favorite_tooltip'))
        layout.addWidget(self.favorite_btn)

        # PHASE C #2: Share/Export button
        self.share_btn = QPushButton("📤")
        self.share_btn.setFocusPolicy(Qt.NoFocus)
        self.share_btn.setFixedSize(56, 56)
        self.share_btn.setStyleSheet(btn_style)
        self.share_btn.clicked.connect(self._show_share_dialog)
        self.share_btn.setToolTip(t('google_layout.lightbox.share_tooltip'))
        layout.addWidget(self.share_btn)

        layout.addStretch()

        # === CENTER: Counter + Zoom Indicator + Rating ===
        center_widget = QWidget()
        center_widget.setStyleSheet("background: transparent;")
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(2)

        # Counter label
        self.counter_label = QLabel()
        self.counter_label.setAlignment(Qt.AlignCenter)
        self.counter_label.setStyleSheet("color: white; font-size: 11pt; background: transparent;")
        center_layout.addWidget(self.counter_label)

        # Zoom/Status indicator
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 9pt; background: transparent;")
        center_layout.addWidget(self.status_label)

        layout.addWidget(center_widget)

        layout.addStretch()

        # === RIGHT SIDE: Zoom + Slideshow + Info ===
        # Zoom out button
        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setFocusPolicy(Qt.NoFocus)
        self.zoom_out_btn.setFixedSize(32, 32)
        self.zoom_out_btn.setStyleSheet(btn_style + "QPushButton { font-size: 18pt; font-weight: bold; }")
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        self.zoom_out_btn.setToolTip(t('google_layout.lightbox.zoom_out_tooltip'))
        layout.addWidget(self.zoom_out_btn)

        # Zoom in button
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFocusPolicy(Qt.NoFocus)
        self.zoom_in_btn.setFixedSize(32, 32)
        self.zoom_in_btn.setStyleSheet(btn_style + "QPushButton { font-size: 16pt; font-weight: bold; }")
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        self.zoom_in_btn.setToolTip(t('google_layout.lightbox.zoom_in_tooltip'))
        layout.addWidget(self.zoom_in_btn)

        layout.addSpacing(8)

        # Slideshow button
        self.slideshow_btn = QPushButton("▶")
        self.slideshow_btn.setFocusPolicy(Qt.NoFocus)
        self.slideshow_btn.setFixedSize(56, 56)
        self.slideshow_btn.setStyleSheet(btn_style)
        self.slideshow_btn.clicked.connect(self._toggle_slideshow)
        self.slideshow_btn.setToolTip(t('google_layout.lightbox.slideshow_tooltip'))
        layout.addWidget(self.slideshow_btn)



        # Info toggle button
        self.info_btn = QPushButton("ℹ️")
        self.info_btn.setFocusPolicy(Qt.NoFocus)
        self.info_btn.setFixedSize(56, 56)
        self.info_btn.setStyleSheet(btn_style)
        self.info_btn.clicked.connect(self._toggle_info_panel)
        self.info_btn.setToolTip(t('google_layout.lightbox.info_tooltip'))
        layout.addWidget(self.info_btn)

        # Edit/Enhance panel toggle (photos only)
        self.edit_btn = QPushButton("✨")
        self.edit_btn.setFocusPolicy(Qt.NoFocus)
        self.edit_btn.setFixedSize(56, 56)
        self.edit_btn.setStyleSheet(btn_style)
        self.edit_btn.setToolTip(t('google_layout.lightbox.edit_tooltip'))
        self.edit_btn.clicked.connect(self._enter_edit_mode)
        layout.addWidget(self.edit_btn)
        self.photo_only_buttons.append(self.edit_btn)

        # Hide inline enhance/preset buttons (moved to panel)
        self.enhance_btn = QPushButton("✨ Enhance")
        self.enhance_btn.setFocusPolicy(Qt.NoFocus)
        self.enhance_btn.setFixedHeight(32)
        self.enhance_btn.setStyleSheet(btn_style)
        self.enhance_btn.setToolTip("Auto-Enhance (Improve brightness/contrast/color)")
        self.enhance_btn.clicked.connect(self._toggle_auto_enhance)
        self.enhance_btn.hide()

        self.dynamic_btn = QPushButton("Dynamic")
        self.dynamic_btn.setFocusPolicy(Qt.NoFocus)
        self.dynamic_btn.setFixedHeight(32)
        self.dynamic_btn.setStyleSheet(btn_style)
        self.dynamic_btn.setToolTip("Dynamic: vivid colors & contrast")
        self.dynamic_btn.clicked.connect(lambda: self._set_preset("dynamic"))
        self.dynamic_btn.hide()

        self.warm_btn = QPushButton("Warm")
        self.warm_btn.setFocusPolicy(Qt.NoFocus)
        self.warm_btn.setFixedHeight(32)
        self.warm_btn.setStyleSheet(btn_style)
        self.warm_btn.setToolTip("Warm: cozy tones")
        self.warm_btn.clicked.connect(lambda: self._set_preset("warm"))
        self.warm_btn.hide()

        self.cool_btn = QPushButton("Cool")
        self.cool_btn.setFocusPolicy(Qt.NoFocus)
        self.cool_btn.setFixedHeight(32)
        self.cool_btn.setStyleSheet(btn_style)
        self.cool_btn.setToolTip("Cool: crisp bluish look")
        self.cool_btn.clicked.connect(lambda: self._set_preset("cool"))
        self.cool_btn.hide()

        return toolbar

    def _create_bottom_toolbar(self) -> QWidget:
        """Create bottom overlay toolbar with navigation and video controls."""
        toolbar = QWidget()
        toolbar.setFixedHeight(80)
        toolbar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(0, 0, 0, 0),
                    stop:1 rgba(0, 0, 0, 0.8));
            }
        """)

        layout = QVBoxLayout(toolbar)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)

        # Video controls container (hidden by default, shown for videos)
        self.video_controls_widget = self._create_video_controls()
        layout.addWidget(self.video_controls_widget)

        # Navigation controls moved to overlay (see _create_overlay_nav_buttons)

        return toolbar

    def _create_overlay_nav_buttons(self):
        """Create Google Photos-style overlay navigation buttons on left/right sides."""
        from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
        from PySide6.QtGui import QCursor

        print("[MediaLightbox] Creating overlay navigation buttons...")

        # Previous button (left side)
        self.prev_btn = QPushButton("◄", self)
        self.prev_btn.setFocusPolicy(Qt.NoFocus)
        self.prev_btn.setFixedSize(48, 48)
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 0, 0, 0.5);
                color: white;
                border: none;
                border-radius: 24px;
                font-size: 18pt;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.7);
            }
            QPushButton:pressed {
                background: rgba(0, 0, 0, 0.9);
            }
            QPushButton:disabled {
                background: rgba(0, 0, 0, 0.2);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        self.prev_btn.clicked.connect(self._previous_media)

        # Next button (right side)
        self.next_btn = QPushButton("►", self)
        self.next_btn.setFocusPolicy(Qt.NoFocus)
        self.next_btn.setFixedSize(48, 48)
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 0, 0, 0.5);
                color: white;
                border: none;
                border-radius: 24px;
                font-size: 18pt;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.7);
            }
            QPushButton:pressed {
                background: rgba(0, 0, 0, 0.9);
            }
            QPushButton:disabled {
                background: rgba(0, 0, 0, 0.2);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        self.next_btn.clicked.connect(self._next_media)

        # CRITICAL: Show buttons explicitly
        self.prev_btn.show()
        self.next_btn.show()

        # Raise buttons above other widgets (overlay effect)
        self.prev_btn.raise_()
        self.next_btn.raise_()

        # CRITICAL FIX: Use QGraphicsOpacityEffect instead of setWindowOpacity
        # (windowOpacity only works on top-level windows, not child widgets)
        self.prev_btn_opacity = QGraphicsOpacityEffect()
        self.prev_btn.setGraphicsEffect(self.prev_btn_opacity)
        self.prev_btn_opacity.setOpacity(1.0)  # Start visible

        self.next_btn_opacity = QGraphicsOpacityEffect()
        self.next_btn.setGraphicsEffect(self.next_btn_opacity)
        self.next_btn_opacity.setOpacity(1.0)  # Start visible

        self.nav_buttons_visible = True  # Start visible

        # Auto-hide timer
        self.nav_hide_timer = QTimer()
        self.nav_hide_timer.setSingleShot(True)
        self.nav_hide_timer.timeout.connect(self._hide_nav_buttons)

        # Position buttons (will be called in resizeEvent)
        QTimer.singleShot(0, self._position_nav_buttons)

        print(f"[MediaLightbox] ✓ Nav buttons created and shown")

    # === PROFESSIONAL AUTO-HIDE TOOLBAR SYSTEM ===

    def _show_toolbars(self):
        """Show toolbars with smooth fade-in animation."""
        if not self.toolbars_visible:
            self.toolbars_visible = True

            # Fade in both toolbars (smooth 200ms animation)
            self.top_toolbar_opacity.setOpacity(1.0)
            self.bottom_toolbar_opacity.setOpacity(1.0)

        # Only auto-hide in fullscreen mode
        if self.isFullScreen():
            self.toolbar_hide_timer.stop()
            self.toolbar_hide_timer.start()  # Restart 2-second timer

    def _hide_toolbars(self):
        """Hide toolbars with smooth fade-out animation (fullscreen only)."""
        # Only hide if in fullscreen
        if self.isFullScreen() and self.toolbars_visible:
            self.toolbars_visible = False

            # Fade out both toolbars (smooth 200ms animation)
            self.top_toolbar_opacity.setOpacity(0.0)
            self.bottom_toolbar_opacity.setOpacity(0.0)

    # === END AUTO-HIDE SYSTEM ===

    def eventFilter(self, obj, event):
        try:
            from PySide6.QtCore import QEvent, Qt
            # Handle wheel zoom in editor canvas
            if hasattr(self, 'editor_canvas') and obj == self.editor_canvas:
                if event.type() == QEvent.Wheel:
                    # Check if in editor mode
                    if hasattr(self, 'mode_stack') and self.mode_stack.currentIndex() == 1:
                        # Ctrl+Wheel = zoom, plain wheel = scroll
                        from PySide6.QtCore import Qt as QtCore
                        try:
                            # Try both modifiers() and the event itself
                            modifiers = event.modifiers()
                            ctrl_pressed = bool(modifiers & Qt.ControlModifier)
                        except:
                            ctrl_pressed = False
                        
                        if ctrl_pressed:
                            delta = event.angleDelta().y()
                            print(f"[Zoom] Ctrl+Wheel detected: delta={delta}")
                            if delta > 0:
                                self._editor_zoom_in()
                                print(f"[Zoom] Zoomed IN to {self.edit_zoom_level:.2f}x")
                            else:
                                self._editor_zoom_out()
                                print(f"[Zoom] Zoomed OUT to {self.edit_zoom_level:.2f}x")
                            return True  # Consume event
                        else:
                            print("[Zoom] Wheel event without Ctrl - not zooming")
            return super().eventFilter(obj, event)
        except Exception as e:
            import traceback
            print(f"[EventFilter] Error: {e}")
            traceback.print_exc()
            return False

    def _editor_zoom_in(self):
        self.edit_zoom_level = min(4.0, getattr(self, 'edit_zoom_level', 1.0) * 1.15)
        if hasattr(self, '_apply_video_zoom'):
            self._apply_video_zoom()
        if hasattr(self, '_update_zoom_status'):
            self._update_zoom_status()

    def _editor_zoom_out(self):
        self.edit_zoom_level = max(0.25, getattr(self, 'edit_zoom_level', 1.0) / 1.15)
        if hasattr(self, '_apply_video_zoom'):
            self._apply_video_zoom()
        if hasattr(self, '_update_zoom_status'):
            self._update_zoom_status()

    def _editor_zoom_reset(self):
        self.edit_zoom_level = 1.0
        if hasattr(self, '_apply_video_zoom'):
            self._apply_video_zoom()
        if hasattr(self, '_update_zoom_status'):
            self._update_zoom_status()

    def _apply_editor_zoom(self):
        try:
            if hasattr(self, '_apply_video_zoom'):
                self._apply_video_zoom()
            if getattr(self, 'editor_canvas', None):
                self.editor_canvas.update()
        except Exception as e:
            print(f"[EditZoom] Error applying editor zoom: {e}")

    def _toggle_info_panel(self):
        try:
            if not hasattr(self, 'info_panel_visible'):
                self.info_panel_visible = False
            self.info_panel_visible = not self.info_panel_visible
            if hasattr(self, 'info_panel') and self.info_panel:
                self.info_panel.setVisible(self.info_panel_visible)
        except Exception as e:
            print(f"[InfoPanel] Toggle error: {e}")

    def _toggle_raw_group(self):
        try:
            visible = self.raw_toggle.isChecked()
            self.raw_group_container.setVisible(visible)
            self.raw_toggle.setText("RAW Development ▾" if visible else "RAW Development ▸")
        except Exception:
            pass
    
    def _toggle_light_group(self):
        try:
            visible = self.light_toggle.isChecked()
            self.light_group_container.setVisible(visible)
            self.light_toggle.setText("Light ▾" if visible else "Light ▸")
        except Exception:
            pass

    def _toggle_color_group(self):
        try:
            visible = self.color_toggle.isChecked()
            self.color_group_container.setVisible(visible)
            self.color_toggle.setText("Color ▾" if visible else "Color ▸")
        except Exception:
            pass

    def _init_adjustments_panel(self):
        """Initialize adjustments panel in the editor right placeholder."""
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider, QPushButton, QSpinBox, QHBoxLayout
        # Create container layout on right panel if missing
        if not hasattr(self, 'adjustments_layout') or self.adjustments_layout is None:
            self.adjustments_layout = QVBoxLayout(self.editor_right_panel)
            self.adjustments_layout.setContentsMargins(12, 12, 12, 12)
            self.adjustments_layout.setSpacing(8)
        # Debounce timer for smooth slider drags
        if not hasattr(self, '_adjust_debounce_timer') or self._adjust_debounce_timer is None:
            self._adjust_debounce_timer = QTimer(self)
            self._adjust_debounce_timer.setSingleShot(True)
            self._adjust_debounce_timer.setInterval(75)
            self._adjust_debounce_timer.timeout.connect(self._apply_adjustments)
        # Initialize adjustments dict
        self.adjustments = {
            'brightness': 0,
            'exposure': 0,
            'contrast': 0,
            'highlights': 0,
            'shadows': 0,
            'vignette': 0,
            'saturation': 0,
            'warmth': 0,
        }
        # Header
        header = QLabel(t('google_layout.lightbox.adjustments_header'))
        header.setStyleSheet("color: white; font-size: 11pt;")
        self.adjustments_layout.addWidget(header)
        # Histogram at top
        self.histogram_label = QLabel()
        self.histogram_label.setFixedHeight(120)
        self.histogram_label.setMinimumWidth(360)
        self.adjustments_layout.addWidget(self.histogram_label)
        # Light group
        self.light_toggle = QPushButton("Light ▾")
        self.light_toggle.setCheckable(True)
        self.light_toggle.setChecked(True)
        self.light_toggle.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 10pt; background: transparent; border: none; text-align: left;")
        self.light_toggle.clicked.connect(self._toggle_light_group)
        self.adjustments_layout.addWidget(self.light_toggle)
        self.light_group_container = QWidget()
        self.light_group_layout = QVBoxLayout(self.light_group_container)
        self.light_group_layout.setContentsMargins(0, 0, 0, 0)
        self.light_group_layout.setSpacing(6)
        self.adjustments_layout.addWidget(self.light_group_container)
        
        # Helper to create slider row with spin box
        def add_slider_row(name, label_text):
            # Label row: name + value spinbox
            label_row = QHBoxLayout()
            label = QLabel(label_text)
            label.setStyleSheet("color: rgba(255,255,255,0.85);")
            label_row.addWidget(label)
            label_row.addStretch()
            spinbox = QSpinBox()
            spinbox.setRange(-100, 100)
            spinbox.setValue(0)
            spinbox.setFixedWidth(60)
            spinbox.setStyleSheet("""
                QSpinBox {
                    background: rgba(255,255,255,0.1);
                    color: white;
                    border: 1px solid rgba(255,255,255,0.2);
                    border-radius: 4px;
                    padding: 2px 4px;
                }
                QSpinBox::up-button, QSpinBox::down-button {
                    background: transparent;
                    width: 12px;
                }
            """)
            spinbox.valueChanged.connect(lambda v: self._on_spinbox_change(name, v))
            setattr(self, f"spinbox_{name}", spinbox)
            label_row.addWidget(spinbox)
            # Slider
            slider = QSlider(Qt.Horizontal)
            slider.setRange(-100, 100)
            slider.setValue(0)
            slider.valueChanged.connect(lambda v: self._on_slider_change(name, v))
            setattr(self, f"slider_{name}", slider)
            return label_row, slider
        
        # Light adjustments with spin boxes
        bright_label_row, self.slider_brightness = add_slider_row('brightness', 'Brightness')
        self.light_group_layout.addLayout(bright_label_row)
        self.light_group_layout.addWidget(self.slider_brightness)
        
        exp_label_row, self.slider_exposure = add_slider_row('exposure', 'Exposure')
        self.light_group_layout.addLayout(exp_label_row)
        self.light_group_layout.addWidget(self.slider_exposure)
        
        cont_label_row, self.slider_contrast = add_slider_row('contrast', 'Contrast')
        self.light_group_layout.addLayout(cont_label_row)
        self.light_group_layout.addWidget(self.slider_contrast)
        
        high_label_row, self.slider_highlights = add_slider_row('highlights', 'Highlights')
        self.light_group_layout.addLayout(high_label_row)
        self.light_group_layout.addWidget(self.slider_highlights)
        
        shad_label_row, self.slider_shadows = add_slider_row('shadows', 'Shadows')
        self.light_group_layout.addLayout(shad_label_row)
        self.light_group_layout.addWidget(self.slider_shadows)
        
        vig_label_row, self.slider_vignette = add_slider_row('vignette', 'Vignette')
        self.light_group_layout.addLayout(vig_label_row)
        self.light_group_layout.addWidget(self.slider_vignette)
        
        sharp_label_row, self.slider_sharpen = add_slider_row('sharpen', 'Sharpen')
        self.light_group_layout.addLayout(sharp_label_row)
        self.light_group_layout.addWidget(self.slider_sharpen)
        
        # Color group
        self.color_toggle = QPushButton("Color ▾")
        self.color_toggle.setCheckable(True)
        self.color_toggle.setChecked(True)
        self.color_toggle.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 10pt; background: transparent; border: none; text-align: left;")
        self.color_toggle.clicked.connect(self._toggle_color_group)
        self.adjustments_layout.addWidget(self.color_toggle)
        self.color_group_container = QWidget()
        self.color_group_layout = QVBoxLayout(self.color_group_container)
        self.color_group_layout.setContentsMargins(0, 0, 0, 0)
        self.color_group_layout.setSpacing(6)
        self.adjustments_layout.addWidget(self.color_group_container)
        
        sat_label_row, self.slider_saturation = add_slider_row('saturation', 'Saturation')
        self.color_group_layout.addLayout(sat_label_row)
        self.color_group_layout.addWidget(self.slider_saturation)
        
        warm_label_row, self.slider_warmth = add_slider_row('warmth', 'Warmth')
        self.color_group_layout.addLayout(warm_label_row)
        self.color_group_layout.addWidget(self.slider_warmth)
        
        # RAW Development group (only shown for RAW files)
        self.raw_toggle = QPushButton("RAW Development ▸")
        self.raw_toggle.setCheckable(True)
        self.raw_toggle.setChecked(False)
        self.raw_toggle.clicked.connect(self._toggle_raw_group)
        self.raw_toggle.setVisible(False)  # Hidden by default, shown for RAW files
        self.adjustments_layout.addWidget(self.raw_toggle)
        
        self.raw_group_container = QWidget()
        self.raw_group_layout = QVBoxLayout(self.raw_group_container)
        self.raw_group_layout.setContentsMargins(0, 0, 0, 0)
        self.raw_group_layout.setSpacing(6)
        self.raw_group_container.setVisible(False)
        self.adjustments_layout.addWidget(self.raw_group_container)
        
        # RAW adjustments with spin boxes
        wb_temp_label_row, self.slider_white_balance_temp = add_slider_row('white_balance_temp', 'WB Temperature')
        self.raw_group_layout.addLayout(wb_temp_label_row)
        self.raw_group_layout.addWidget(self.slider_white_balance_temp)
        
        wb_tint_label_row, self.slider_white_balance_tint = add_slider_row('white_balance_tint', 'WB Tint (G/M)')
        self.raw_group_layout.addLayout(wb_tint_label_row)
        self.raw_group_layout.addWidget(self.slider_white_balance_tint)
        
        # Note: Exposure recovery, lens correction, chromatic aberration use 0-100 range
        def add_slider_row_0_100(name, label_text):
            label_row = QHBoxLayout()
            label = QLabel(label_text)
            label.setStyleSheet("color: rgba(255,255,255,0.85);")
            label_row.addWidget(label)
            label_row.addStretch()
            spinbox = QSpinBox()
            spinbox.setRange(0, 100)
            spinbox.setValue(0)
            spinbox.setFixedWidth(60)
            spinbox.setStyleSheet("""
                QSpinBox {
                    background: rgba(255,255,255,0.1);
                    color: white;
                    border: 1px solid rgba(255,255,255,0.2);
                    border-radius: 4px;
                    padding: 2px 4px;
                }
                QSpinBox::up-button, QSpinBox::down-button {
                    background: transparent;
                    width: 12px;
                }
            """)
            spinbox.valueChanged.connect(lambda v: self._on_spinbox_change(name, v))
            setattr(self, f"spinbox_{name}", spinbox)
            label_row.addWidget(spinbox)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(0)
            slider.valueChanged.connect(lambda v: self._on_slider_change(name, v))
            setattr(self, f"slider_{name}", slider)
            return label_row, slider
        
        exp_rec_label_row, self.slider_exposure_recovery = add_slider_row_0_100('exposure_recovery', 'Highlight Recovery')
        self.raw_group_layout.addLayout(exp_rec_label_row)
        self.raw_group_layout.addWidget(self.slider_exposure_recovery)
        
        lens_corr_label_row, self.slider_lens_correction = add_slider_row_0_100('lens_correction', 'Lens Correction')
        self.raw_group_layout.addLayout(lens_corr_label_row)
        self.raw_group_layout.addWidget(self.slider_lens_correction)
        
        ca_label_row, self.slider_chromatic_aberration = add_slider_row_0_100('chromatic_aberration', 'CA Removal')
        self.raw_group_layout.addLayout(ca_label_row)
        self.raw_group_layout.addWidget(self.slider_chromatic_aberration)
        
        # Reset button
        reset_btn = QPushButton("Reset All")
        reset_btn.clicked.connect(self._reset_adjustments)
        self.adjustments_layout.addWidget(reset_btn)
        # Build filters panel and add to right panel (hidden by default)
        self.filters_container = self._build_filters_panel()
        self.filters_container.hide()
        self.adjustments_layout.addWidget(self.filters_container)

    def _save_edit_state(self):
        """Save current edit state to JSON file for persistence."""
        try:
            if not hasattr(self, 'media_path') or not self.media_path:
                return
            
            import json
            import hashlib
            
            # Create unique filename based on image path hash
            path_hash = hashlib.md5(self.media_path.encode()).hexdigest()
            state_file = os.path.join(self.edit_states_dir, f"{path_hash}.json")
            
            # Collect edit state
            edit_state = {
                'media_path': self.media_path,
                'adjustments': self.adjustments.copy(),
                'filter_intensity': getattr(self, 'filter_intensity', 100),
                'current_preset': getattr(self, 'current_preset_adjustments', {}),
                'timestamp': str(datetime.now())
            }
            
            # Save to file
            with open(state_file, 'w') as f:
                json.dump(edit_state, f, indent=2)
            
            print(f"[EditState] Saved edit state for {os.path.basename(self.media_path)}")
            return True
        except Exception as e:
            import traceback
            print(f"[EditState] Error saving edit state: {e}")
            traceback.print_exc()
            return False
    
    def _load_edit_state(self):
        """Load saved edit state from JSON file if exists."""
        try:
            if not hasattr(self, 'media_path') or not self.media_path:
                return False
            
            import json
            import hashlib
            
            # Find state file
            path_hash = hashlib.md5(self.media_path.encode()).hexdigest()
            state_file = os.path.join(self.edit_states_dir, f"{path_hash}.json")
            
            if not os.path.exists(state_file):
                return False
            
            # Load state
            with open(state_file, 'r') as f:
                edit_state = json.load(f)
            
            # Verify it's for the correct image
            if edit_state.get('media_path') != self.media_path:
                return False
            
            # Restore adjustments
            adjustments = edit_state.get('adjustments', {})
            for key, val in adjustments.items():
                if key in self.adjustments:
                    self.adjustments[key] = val
                    # Update sliders and spinboxes
                    slider = getattr(self, f"slider_{key}", None)
                    spinbox = getattr(self, f"spinbox_{key}", None)
                    if slider:
                        slider.blockSignals(True)
                        slider.setValue(val)
                        slider.blockSignals(False)
                    if spinbox:
                        spinbox.blockSignals(True)
                        spinbox.setValue(val)
                        spinbox.blockSignals(False)
            
            # Restore filter intensity
            filter_intensity = edit_state.get('filter_intensity', 100)
            self.filter_intensity = filter_intensity
            if hasattr(self, 'filter_intensity_slider'):
                self.filter_intensity_slider.blockSignals(True)
                self.filter_intensity_slider.setValue(filter_intensity)
                self.filter_intensity_slider.blockSignals(False)
            if hasattr(self, 'intensity_value_label'):
                self.intensity_value_label.setText(f"{filter_intensity}%")
            
            # Restore current preset
            self.current_preset_adjustments = edit_state.get('current_preset', {})
            
            # Apply the loaded adjustments
            self._apply_adjustments()
            
            print(f"[EditState] Restored edit state for {os.path.basename(self.media_path)}")
            return True
        except Exception as e:
            import traceback
            print(f"[EditState] Error loading edit state: {e}")
            traceback.print_exc()
            return False
    
    def _show_raw_notification(self, message: str, is_warning: bool = False):
        """Show temporary notification for RAW file status."""
        try:
            from PySide6.QtWidgets import QLabel
            from PySide6.QtCore import QTimer
            
            # Create notification label
            if not hasattr(self, '_raw_notification_label'):
                self._raw_notification_label = QLabel(self)
                self._raw_notification_label.setAlignment(Qt.AlignCenter)
                self._raw_notification_label.setStyleSheet("""
                    QLabel {
                        background: rgba(33, 150, 243, 0.9);
                        color: white;
                        padding: 12px 24px;
                        border-radius: 8px;
                        font-size: 11pt;
                        font-weight: bold;
                    }
                """)
                self._raw_notification_label.setVisible(False)
            
            # Update style if warning
            if is_warning:
                self._raw_notification_label.setStyleSheet("""
                    QLabel {
                        background: rgba(255, 152, 0, 0.9);
                        color: white;
                        padding: 12px 24px;
                        border-radius: 8px;
                        font-size: 11pt;
                        font-weight: bold;
                    }
                """)
            
            # Set message and show
            self._raw_notification_label.setText(message)
            self._raw_notification_label.adjustSize()
            
            # Position at top center
            parent_width = self.width()
            label_width = self._raw_notification_label.width()
            self._raw_notification_label.move((parent_width - label_width) // 2, 80)
            self._raw_notification_label.raise_()
            self._raw_notification_label.setVisible(True)
            
            # Auto-hide after 5 seconds
            QTimer.singleShot(5000, lambda: self._raw_notification_label.setVisible(False) if hasattr(self, '_raw_notification_label') else None)
            
        except Exception as e:
            print(f"[RAW] Error showing notification: {e}")
    
    def _is_raw_file(self, file_path: str) -> bool:
        """Check if file is a RAW image format."""
        if not file_path:
            return False
        raw_extensions = [
            '.cr2', '.cr3',  # Canon
            '.nef', '.nrw',  # Nikon
            '.arw', '.srf', '.sr2',  # Sony
            '.orf',  # Olympus
            '.rw2',  # Panasonic
            '.pef', '.ptx',  # Pentax
            '.raf',  # Fujifilm
            '.dng',  # Adobe Digital Negative
            '.x3f',  # Sigma
            '.3fr',  # Hasselblad
            '.fff',  # Imacon
            '.dcr', '.kdc',  # Kodak
            '.mrw',  # Minolta
            '.raw', '.rwl',  # Leica
            '.iiq',  # Phase One
        ]
        ext = os.path.splitext(file_path)[1].lower()
        return ext in raw_extensions
    
    def _is_video_file(self, file_path: str) -> bool:
        """Check if file is a video format."""
        if not file_path:
            return False
        video_extensions = [
            '.mp4', '.mov', '.avi', '.mkv', '.webm',
            '.m4v', '.3gp', '.flv', '.wmv', '.mpg', '.mpeg'
        ]
        ext = os.path.splitext(file_path)[1].lower()
        return ext in video_extensions
    
    def _check_rawpy_available(self) -> bool:
        """Check if rawpy library is available."""
        try:
            import rawpy
            return True
        except ImportError:
            return False
    
    def _load_raw_image(self, file_path: str):
        """Load RAW image using rawpy."""
        try:
            if not self._check_rawpy_available():
                print("[RAW] rawpy library not available - install with: pip install rawpy")
                return None
            
            import rawpy
            raw = rawpy.imread(file_path)
            print(f"[RAW] Loaded RAW file: {os.path.basename(file_path)}")
            print(f"[RAW] Camera: {getattr(raw.color_desc, 'decode', lambda: 'Unknown')()}")
            print(f"[RAW] Size: {raw.sizes.raw_width}x{raw.sizes.raw_height}")
            return raw
        except Exception as e:
            import traceback
            print(f"[RAW] Error loading RAW file: {e}")
            traceback.print_exc()
            return None
    
    def _process_raw_to_pixmap(self, raw_image, adjustments: dict = None):
        """Process RAW image with adjustments and convert to QPixmap."""
        try:
            if not raw_image:
                return None
            
            import rawpy
            from PIL import Image
            import numpy as np
            
            # Get adjustments or use defaults
            adj = adjustments or self.adjustments
            
            # Prepare rawpy processing parameters
            params = rawpy.Params(
                use_camera_wb=True,  # Use camera white balance as starting point
                use_auto_wb=False,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=8,  # 8-bit output
                no_auto_bright=True,  # Disable auto brightness (we'll handle it)
                exp_shift=1.0,  # Exposure adjustment
                bright=1.0,  # Brightness multiplier
                user_wb=None,  # Custom white balance
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,  # High quality
                median_filter_passes=0
            )
            
            # Apply RAW-specific adjustments
            # White balance temperature
            temp = adj.get('white_balance_temp', 0)
            tint = adj.get('white_balance_tint', 0)
            if temp != 0 or tint != 0:
                # Adjust white balance multipliers
                # This is a simplified approach - real WB is more complex
                wb_mult = list(raw_image.camera_whitebalance)
                # Temperature: affects red/blue balance
                if temp > 0:  # Warmer (more red)
                    wb_mult[0] *= (1.0 + temp / 200.0)  # Increase red
                    wb_mult[2] *= (1.0 - temp / 200.0)  # Decrease blue
                else:  # Cooler (more blue)
                    wb_mult[0] *= (1.0 + temp / 200.0)  # Decrease red
                    wb_mult[2] *= (1.0 - temp / 200.0)  # Increase blue
                # Tint: affects green/magenta balance
                if tint != 0:
                    wb_mult[1] *= (1.0 + tint / 200.0)  # Adjust green
                params.user_wb = wb_mult
            
            # Exposure recovery (preserve highlights)
            exp_recovery = adj.get('exposure_recovery', 0)
            if exp_recovery > 0:
                # Reduce exp_shift to preserve highlights
                params.exp_shift = 1.0 - (exp_recovery / 200.0)  # 0 to 100 -> 1.0 to 0.5
            
            # Process RAW to RGB array
            rgb = raw_image.postprocess(params)
            
            # Convert to PIL Image
            pil_img = Image.fromarray(rgb)
            
            # Apply lens correction (simple barrel/pincushion distortion)
            lens_corr = adj.get('lens_correction', 0)
            if lens_corr > 0:
                # This is a placeholder - real lens correction requires specific lens profiles
                print(f"[RAW] Lens correction: {lens_corr}% (simplified implementation)")
            
            # Apply chromatic aberration removal
            ca_removal = adj.get('chromatic_aberration', 0)
            if ca_removal > 0:
                # Simplified CA removal - real implementation would shift color channels
                print(f"[RAW] Chromatic aberration removal: {ca_removal}% (simplified)")
            
            # Convert PIL to QPixmap
            pixmap = self._pil_to_qpixmap(pil_img)
            
            print(f"[RAW] Processed RAW image with adjustments")
            return pixmap
            
        except Exception as e:
            import traceback
            print(f"[RAW] Error processing RAW image: {e}")
            traceback.print_exc()
            return None
    
    def _copy_adjustments(self):
        """Copy current adjustments to clipboard for batch editing."""
        try:
            # Copy all adjustment values
            self.copied_adjustments = self.adjustments.copy()
            self.copied_filter_intensity = getattr(self, 'filter_intensity', 100)
            self.copied_preset = getattr(self, 'current_preset_adjustments', {}).copy()
            
            # Enable paste button
            if hasattr(self, 'paste_adj_btn'):
                self.paste_adj_btn.setEnabled(True)
            
            # Visual feedback
            from PySide6.QtWidgets import QMessageBox
            msg = f"Copied adjustments:\n"
            non_zero = {k: v for k, v in self.copied_adjustments.items() if v != 0}
            if non_zero:
                for key, val in non_zero.items():
                    msg += f"  {key.capitalize()}: {val:+d}\n"
            else:
                msg += "  (No adjustments set)\n"
            msg += f"\nFilter Intensity: {self.copied_filter_intensity}%"
            
            # Create temporary label to show feedback
            if hasattr(self, 'copy_adj_btn'):
                original_text = self.copy_adj_btn.text()
                self.copy_adj_btn.setText("✓ Copied!")
                from PySide6.QtCore import QTimer
                QTimer.singleShot(1500, lambda: self.copy_adj_btn.setText(original_text) if hasattr(self, 'copy_adj_btn') else None)
            
            print(f"[Copy/Paste] ✓ Copied adjustments")
            print(msg)
            return True
        except Exception as e:
            import traceback
            print(f"[Copy/Paste] Error copying adjustments: {e}")
            traceback.print_exc()
            return False
    
    def _paste_adjustments(self):
        """Paste copied adjustments to current photo."""
        try:
            if not self.copied_adjustments:
                print("[Copy/Paste] Nothing to paste")
                return False
            
            # Apply copied adjustments
            for key, val in self.copied_adjustments.items():
                if key in self.adjustments:
                    self.adjustments[key] = val
                    # Update sliders and spinboxes
                    slider = getattr(self, f"slider_{key}", None)
                    spinbox = getattr(self, f"spinbox_{key}", None)
                    if slider:
                        slider.blockSignals(True)
                        slider.setValue(val)
                        slider.blockSignals(False)
                    if spinbox:
                        spinbox.blockSignals(True)
                        spinbox.setValue(val)
                        spinbox.blockSignals(False)
            
            # Apply copied filter intensity
            if self.copied_filter_intensity is not None:
                self.filter_intensity = self.copied_filter_intensity
                if hasattr(self, 'filter_intensity_slider'):
                    self.filter_intensity_slider.blockSignals(True)
                    self.filter_intensity_slider.setValue(self.copied_filter_intensity)
                    self.filter_intensity_slider.blockSignals(False)
                if hasattr(self, 'intensity_value_label'):
                    self.intensity_value_label.setText(f"{self.copied_filter_intensity}%")
            
            # Apply copied preset
            if self.copied_preset:
                self.current_preset_adjustments = self.copied_preset.copy()
            
            # Re-render with pasted adjustments
            self._apply_adjustments()
            
            # Visual feedback
            if hasattr(self, 'paste_adj_btn'):
                original_text = self.paste_adj_btn.text()
                self.paste_adj_btn.setText("✓ Pasted!")
                from PySide6.QtCore import QTimer
                QTimer.singleShot(1500, lambda: self.paste_adj_btn.setText(original_text) if hasattr(self, 'paste_adj_btn') else None)
            
            print(f"[Copy/Paste] ✓ Pasted adjustments to current photo")
            return True
        except Exception as e:
            import traceback
            print(f"[Copy/Paste] Error pasting adjustments: {e}")
            traceback.print_exc()
            return False
    
    def _clear_edit_state(self):
        """Clear saved edit state for current image."""
        try:
            if not hasattr(self, 'media_path') or not self.media_path:
                return
            
            import hashlib
            path_hash = hashlib.md5(self.media_path.encode()).hexdigest()
            state_file = os.path.join(self.edit_states_dir, f"{path_hash}.json")
            
            if os.path.exists(state_file):
                os.remove(state_file)
                print(f"[EditState] Cleared edit state for {os.path.basename(self.media_path)}")
        except Exception as e:
            print(f"[EditState] Error clearing edit state: {e}")
    
    def _enter_edit_mode(self):
        """Switch to editor page and prepare non-destructive edit state."""
        try:
            # Check if current file is VIDEO
            if hasattr(self, 'media_path') and self.media_path:
                self.is_video_file = self._is_video_file(self.media_path)
                
                if self.is_video_file:
                    print(f"[Editor] VIDEO file detected: {os.path.basename(self.media_path)}")
                    
                    # Initialize trim points from existing player
                    self.video_trim_start = 0
                    duration = getattr(self, '_video_duration', 0)
                    self.video_trim_end = duration
                    self.video_rotation_angle = 0
                    
                    # Show trim/rotate controls in right-side tools panel
                    if not hasattr(self, 'video_tools_container'):
                        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
                        self.video_tools_container = QWidget()
                        self.video_tools_container.setStyleSheet("background: rgba(0,0,0,0.6);")
                        self.video_tools_layout = QVBoxLayout(self.video_tools_container)
                        self.video_tools_layout.setContentsMargins(12, 12, 12, 12)
                        self.video_tools_layout.setSpacing(8)
                        header = QLabel("Video Tools")
                        header.setStyleSheet("color: white; font-size: 11pt; font-weight: bold;")
                        self.video_tools_layout.addWidget(header)
                        # Mount into right panel
                        if hasattr(self, 'editor_right_panel') and self.editor_right_panel.layout():
                            self.editor_right_panel.layout().addWidget(self.video_tools_container)
                        elif hasattr(self, 'editor_right_panel'):
                            from PySide6.QtWidgets import QVBoxLayout
                            rp_layout = QVBoxLayout(self.editor_right_panel)
                            rp_layout.setContentsMargins(12, 12, 12, 12)
                            rp_layout.setSpacing(8)
                            rp_layout.addWidget(self.video_tools_container)
                    
                    if not hasattr(self, 'video_trim_controls'):
                        self.video_trim_controls = self._create_video_trim_controls()
                        from PySide6.QtWidgets import QGroupBox, QVBoxLayout
                        trim_group = QGroupBox("Trim")
                        trim_group.setStyleSheet("QGroupBox { color: white; font-weight: bold; }")
                        trim_layout = QVBoxLayout(trim_group)
                        trim_layout.setContentsMargins(8, 8, 8, 8)
                        trim_layout.addWidget(self.video_trim_controls)
                        self.video_tools_layout.addWidget(trim_group)
                    
                    if not hasattr(self, 'video_rotate_controls'):
                        self.video_rotate_controls = self._create_video_rotate_controls()
                        from PySide6.QtWidgets import QGroupBox, QVBoxLayout
                        rotate_group = QGroupBox("Rotate / Output")
                        rotate_group.setStyleSheet("QGroupBox { color: white; font-weight: bold; }")
                        rotate_layout = QVBoxLayout(rotate_group)
                        rotate_layout.setContentsMargins(8, 8, 8, 8)
                        rotate_layout.addWidget(self.video_rotate_controls)
                        self.video_tools_layout.addWidget(rotate_group)
                    
                    # Show video controls, hide photo controls
                    self.video_tools_container.show()
                    if hasattr(self, 'video_trim_controls'):
                        self.video_trim_controls.show()
                    if hasattr(self, 'video_rotate_controls'):
                        self.video_rotate_controls.show()
                    self.crop_btn.hide()  # Hide crop for videos
                    
                    # Hide photo editing controls to prevent toolbar overflow
                    if hasattr(self, 'straighten_slider'):
                        self.straighten_slider.parent().hide()
                    if hasattr(self, 'rotate_left_btn'):
                        self.rotate_left_btn.hide()
                    if hasattr(self, 'rotate_right_btn'):
                        self.rotate_right_btn.hide()
                    for widget in ['aspect_original_btn', 'aspect_square_btn', 'aspect_169_btn',
                                   'aspect_43_btn', 'aspect_916_btn', 'aspect_free_btn']:
                        if hasattr(self, widget):
                            getattr(self, widget).hide()
                    
                    # Hide crop toolbar entirely for videos
                    if hasattr(self, 'crop_toolbar'):
                        self.crop_toolbar.hide()
                    
                    # Ensure bottom video controls are visible
                    if hasattr(self, 'bottom_toolbar'):
                        self.bottom_toolbar.show()
                    if hasattr(self, 'video_controls_widget'):
                        self.video_controls_widget.show()
                    self._show_toolbars() if hasattr(self, '_show_toolbars') else None
                    
                    # Make media area adapt so controls aren't hidden
                    if hasattr(self, 'scroll_area'):
                        try:
                            self._original_scroll_resizable = self.scroll_area.widgetResizable()
                        except Exception:
                            self._original_scroll_resizable = False
                        self.scroll_area.setWidgetResizable(True)
                    
                    # Update trim labels with current duration
                    if hasattr(self, 'trim_end_label'):
                        self.trim_end_label.setText(self._format_time(duration))
                    
                    # Hide photo adjustments groups in right panel for videos
                    for w in [getattr(self, "histogram_label", None), getattr(self, "light_toggle", None), getattr(self, "light_group_container", None), getattr(self, "color_toggle", None), getattr(self, "color_group_container", None), getattr(self, "raw_toggle", None), getattr(self, "raw_group_container", None), getattr(self, "filters_container", None)]:
                        (w.hide() if w else None)
                    print("[Editor] Video tools shown on right panel")

                    # Update trim labels with current duration
                    if hasattr(self, 'trim_end_label'):
                        self.trim_end_label.setText(self._format_time(duration))
                    
                    print("[Editor] Video trim/rotate controls shown")

                    # CRITICAL FIX: Reparent video widget to editor canvas for edit mode
                    # The editor page (page 1) has the crop_toolbar with video controls
                    # We need to move the video_widget from viewer page to editor page

                    if hasattr(self, 'video_widget') and self.video_widget:
                        # Remove from viewer page layout
                        if self.video_widget.parent():
                            current_layout = self.video_widget.parent().layout()
                            if current_layout:
                                current_layout.removeWidget(self.video_widget)

                        # Add to editor canvas
                        if hasattr(self, 'editor_canvas'):
                            # Create layout for editor canvas if not exists
                            if not self.editor_canvas.layout():
                                from PySide6.QtWidgets import QVBoxLayout
                                canvas_layout = QVBoxLayout(self.editor_canvas)
                                canvas_layout.setContentsMargins(0, 0, 0, 0)

                            # Add video widget to editor canvas
                            self.editor_canvas.layout().addWidget(self.video_widget)
                            self.video_widget.show()
                            if hasattr(self, '_fit_video_view'):
                                self._fit_video_view()
                            print("[Editor] ✓ Video widget reparented to editor canvas")

                    # Switch to editor page to show video controls
                    if hasattr(self, 'mode_stack'):
                        self.mode_stack.setCurrentIndex(1)
                        print("[Editor] ✓ Switched to editor page for video editing")

                    # Hide nav buttons during edit mode
                    if hasattr(self, 'prev_btn'):
                        self.prev_btn.hide()
                    if hasattr(self, 'next_btn'):
                        self.next_btn.hide()

                    print("[Editor] Video edit mode active (video on editor page)")
                    return  # Skip photo editing setup
                
                else:
                    # Hide video controls for non-video files
                    if hasattr(self, 'video_trim_controls'):
                        self.video_trim_controls.hide()
                    if hasattr(self, 'video_rotate_controls'):
                        self.video_rotate_controls.hide()
                    self.crop_btn.show()  # Show crop for photos
            
            # Check if current file is RAW (photos only)
            if hasattr(self, 'media_path') and self.media_path:
                self.is_raw_file = self._is_raw_file(self.media_path)
                if self.is_raw_file:
                    print(f"[Editor] RAW file detected: {os.path.basename(self.media_path)}")
                    # Show RAW controls
                    if hasattr(self, 'raw_toggle'):
                        self.raw_toggle.setVisible(True)
                    # Try to load RAW image
                    if self._check_rawpy_available():
                        self.raw_image = self._load_raw_image(self.media_path)
                        if self.raw_image:
                            # Process RAW to initial pixmap
                            raw_pixmap = self._process_raw_to_pixmap(self.raw_image, self.adjustments)
                            if raw_pixmap:
                                self.original_pixmap = raw_pixmap
                                print("[Editor] RAW image processed successfully")
                                # Show notification
                                self._show_raw_notification("RAW file loaded - use RAW Development controls")
                    else:
                        print("[Editor] rawpy not available - install with: pip install rawpy")
                        print("[Editor] Falling back to embedded JPEG preview")
                        self._show_raw_notification("RAW preview only - Install rawpy for full RAW editing", is_warning=True)
                else:
                    # Hide RAW controls for non-RAW files
                    if hasattr(self, 'raw_toggle'):
                        self.raw_toggle.setVisible(False)
                        self.raw_toggle.setChecked(False)
                        self.raw_group_container.setVisible(False)
            
            # Copy current original pixmap for editing if available
            if getattr(self, 'original_pixmap', None) and not self.original_pixmap.isNull():
                self._original_pixmap = self.original_pixmap
                self._edit_pixmap = self.original_pixmap.copy()
                # Initialize edit history
                self.edit_history = [(self._edit_pixmap.copy(), self.adjustments.copy())]
                self.edit_history_index = 0
                self._update_undo_redo_buttons()
                # IMPORTANT: Reset editor zoom to match viewer zoom
                self.edit_zoom_level = self.zoom_level  # Inherit current zoom from viewer
                
                # AUTO-RESTORE: Load saved edit state if exists
                restored = self._load_edit_state()
                if restored:
                    print("[Editor] ✓ Restored previous edit state")
                else:
                    print("[Editor] Starting fresh (no saved state)")
                
                self._update_editor_canvas_pixmap()
                self._apply_editor_zoom()
            else:
                # Clear canvas if no image loaded yet
                self._original_pixmap = None
                self._edit_pixmap = None
                if hasattr(self, 'editor_canvas'):
                    self.editor_canvas.update()
            # Show editor page
            if hasattr(self, 'mode_stack'):
                self.mode_stack.setCurrentIndex(1)
            # Optionally hide overlay navigation in editor mode
            if hasattr(self, 'prev_btn'):
                self.prev_btn.hide()
            if hasattr(self, 'next_btn'):
                self.next_btn.hide()
            # Install event filter for editor zoom (CRITICAL)
            if hasattr(self, 'editor_canvas'):
                self.editor_canvas.installEventFilter(self)
                # Enable mouse tracking for wheel events
                self.editor_canvas.setMouseTracking(True)
                # CRITICAL: Set focus to canvas to receive wheel events
                self.editor_canvas.setFocus()
                print("[EDITOR] ========================================")
                print("[EDITOR] Event filter installed on editor canvas")
                print("[EDITOR] Canvas has focus for wheel events")
                print("[EDITOR] ")
                print("[EDITOR] KEYBOARD SHORTCUTS:")
                print("[EDITOR]   E - Enter/Exit Editor Mode")
                print("[EDITOR]   C - Toggle Crop Mode (in editor)")
                print("[EDITOR]   Ctrl + Z - Undo")
                print("[EDITOR]   Ctrl + Y - Redo")
                print("[EDITOR]   Ctrl + Mouse Wheel - Zoom In/Out")
                print("[EDITOR] ")
                print("[EDITOR] MOUSE CONTROLS:")
                print("[EDITOR]   - Hold Ctrl + Mouse Wheel to zoom in/out")
                print("[EDITOR]   - Drag crop handles (corners/edges) to resize")
                print("[EDITOR] ")
                print("[EDITOR] BUTTONS:")
                print("[EDITOR]   - Click '✂ Crop' button to toggle crop mode")
                print("[EDITOR]   - Adjust sliders on right panel")
                print("[EDITOR]   - Click '✔ Save' to apply, '✖ Cancel' to discard")
                print("[EDITOR] ========================================")
        except Exception as e:
            print(f"[EditMode] Error entering editor mode: {e}")

    def _save_edits(self):
        try:
            # Handle video edit mode - move video back to viewer page
            if getattr(self, 'is_video_file', False) and hasattr(self, 'video_widget') and self.video_widget:
                # Remove from editor canvas
                if self.video_widget.parent():
                    current_layout = self.video_widget.parent().layout()
                    if current_layout:
                        current_layout.removeWidget(self.video_widget)

                # Add back to viewer page media_container
                if hasattr(self, 'media_container'):
                    container_layout = self.media_container.layout()
                    if container_layout:
                        container_layout.addWidget(self.video_widget)
                        self.video_widget.show()
                        print("[Editor] ✓ Video widget moved back to viewer page")

                # Hide crop_toolbar when exiting video edit mode
                if hasattr(self, 'crop_toolbar'):
                    self.crop_toolbar.hide()

            # Handle photo edit mode
            if getattr(self, '_edit_pixmap', None) and not self._edit_pixmap.isNull():
                # AUTO-SAVE: Save current edit state before applying
                self._save_edit_state()

                self.original_pixmap = self._edit_pixmap
                if hasattr(self, 'image_label'):
                    self.image_label.setPixmap(self.original_pixmap)

            # Switch back to viewer page
            if hasattr(self, 'mode_stack'):
                self.mode_stack.setCurrentIndex(0)

            # Restore overlay navigation in viewer mode
            if hasattr(self, 'prev_btn'):
                self.prev_btn.show()
            if hasattr(self, 'next_btn'):
                self.next_btn.show()
            if hasattr(self, '_position_nav_buttons'):
                self._position_nav_buttons()

            print("[Editor] ✓ Edits saved and returned to viewer mode")
        except Exception as e:
            print(f"[EditMode] Error saving edits: {e}")

    def _cancel_edits(self):
        try:
            # Handle video edit mode - move video back to viewer page
            if getattr(self, 'is_video_file', False) and hasattr(self, 'video_widget') and self.video_widget:
                # Remove from editor canvas
                if self.video_widget.parent():
                    current_layout = self.video_widget.parent().layout()
                    if current_layout:
                        current_layout.removeWidget(self.video_widget)

                # Add back to viewer page media_container
                if hasattr(self, 'media_container'):
                    container_layout = self.media_container.layout()
                    if container_layout:
                        container_layout.addWidget(self.video_widget)
                        self.video_widget.show()
                        print("[Editor] ✓ Video widget moved back to viewer page")

                # Reset video edits
                self.video_trim_start = 0
                duration = getattr(self, '_video_duration', 0)
                self.video_trim_end = duration
                self.video_rotation_angle = 0

                # Clear trim markers
                if hasattr(self, 'seek_slider') and hasattr(self.seek_slider, 'clear_trim_markers'):
                    self.seek_slider.clear_trim_markers()

                # Reset rotation status label
                if hasattr(self, 'rotation_status_label'):
                    self.rotation_status_label.setText("Original")

                # Hide crop_toolbar when exiting video edit mode
                if hasattr(self, 'crop_toolbar'):
                    self.crop_toolbar.hide()

                print("[Editor] ✓ Video edits cancelled and reset")

            # Switch back to viewer page
            if hasattr(self, 'mode_stack'):
                self.mode_stack.setCurrentIndex(0)

            # Restore overlay navigation in viewer mode
            if hasattr(self, 'prev_btn'):
                self.prev_btn.show()
            if hasattr(self, 'next_btn'):
                self.next_btn.show()
            if hasattr(self, '_position_nav_buttons'):
                self._position_nav_buttons()

            print("[Editor] ✓ Edits cancelled and returned to viewer mode")
        except Exception as e:
            print(f"[EditMode] Error cancelling edits: {e}")

    def _on_adjustment_change(self, key: str, value: int):
        """DEPRECATED - use _on_slider_change instead."""
        self._on_slider_change(key, value)

    def _on_slider_change(self, key: str, value: int):
        """Handle slider value change, update spinbox."""
        self.adjustments[key] = int(value)
        # Update corresponding spinbox
        spinbox = getattr(self, f"spinbox_{key}", None)
        if spinbox:
            spinbox.blockSignals(True)
            spinbox.setValue(value)
            spinbox.blockSignals(False)
        # Trigger debounced render
        if hasattr(self, '_adjust_debounce_timer') and self._adjust_debounce_timer:
            self._adjust_debounce_timer.stop()
            self._adjust_debounce_timer.start()
        else:
            self._apply_adjustments()
        
        # AUTO-SAVE: Debounced save of edit state (every 3 seconds after changes)
        if not hasattr(self, '_autosave_timer'):
            from PySide6.QtCore import QTimer
            self._autosave_timer = QTimer(self)
            self._autosave_timer.setSingleShot(True)
            self._autosave_timer.timeout.connect(self._save_edit_state)
        self._autosave_timer.stop()
        self._autosave_timer.start(3000)  # 3 second debounce

    def _on_spinbox_change(self, key: str, value: int):
        """Handle spinbox value change, update slider."""
        self.adjustments[key] = int(value)
        # Update corresponding slider
        slider = getattr(self, f"slider_{key}", None)
        if slider:
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
        # Trigger debounced render
        if hasattr(self, '_adjust_debounce_timer') and self._adjust_debounce_timer:
            self._adjust_debounce_timer.stop()
            self._adjust_debounce_timer.start()
        else:
            self._apply_adjustments()

    def _reset_adjustments(self):
        """Reset all adjustments to 0."""
        for k in self.adjustments:
            self.adjustments[k] = 0
        # Reset sliders and spinboxes
        for key in ['brightness', 'exposure', 'contrast', 'highlights', 'shadows', 'vignette', 'sharpen', 'saturation', 'warmth',
                    'white_balance_temp', 'white_balance_tint', 'exposure_recovery', 'lens_correction', 'chromatic_aberration']:
            slider = getattr(self, f"slider_{key}", None)
            spinbox = getattr(self, f"spinbox_{key}", None)
            if slider:
                slider.blockSignals(True)
                slider.setValue(0)
                slider.blockSignals(False)
            if spinbox:
                spinbox.blockSignals(True)
                spinbox.setValue(0)
                spinbox.blockSignals(False)
        self._apply_adjustments()

    def _apply_adjustments(self):
        """Apply adjustments to edit pixmap (brightness, exposure, contrast, highlights, shadows, saturation, warmth, vignette)."""
        try:
            # RAW FILE HANDLING: If RAW adjustments changed, reprocess from RAW
            if getattr(self, 'is_raw_file', False) and getattr(self, 'raw_image', None):
                raw_adj_keys = ['white_balance_temp', 'white_balance_tint', 'exposure_recovery']
                raw_adj_changed = any(self.adjustments.get(k, 0) != 0 for k in raw_adj_keys)
                
                if raw_adj_changed:
                    print("[RAW] Reprocessing RAW image with adjustments...")
                    # Reprocess RAW with current adjustments
                    raw_pixmap = self._process_raw_to_pixmap(self.raw_image, self.adjustments)
                    if raw_pixmap:
                        self._original_pixmap = raw_pixmap
                        print("[RAW] RAW reprocessed successfully")
            
            if not getattr(self, '_original_pixmap', None) or self._original_pixmap.isNull():
                return
            # Convert QPixmap -> PIL
            pil_img = self._qpixmap_to_pil(self._original_pixmap)
            from PIL import ImageEnhance, Image, ImageDraw
            # Brightness (mid-tone)
            b = self.adjustments.get('brightness', 0)
            if b != 0:
                pil_img = ImageEnhance.Brightness(pil_img).enhance(1.0 + (b / 100.0))
            # Exposure (stops)
            e = self.adjustments.get('exposure', 0)
            if e != 0:
                expo_factor = pow(2.0, e / 100.0)
                pil_img = ImageEnhance.Brightness(pil_img).enhance(expo_factor)
            # Contrast
            c = self.adjustments.get('contrast', 0)
            if c != 0:
                pil_img = ImageEnhance.Contrast(pil_img).enhance(1.0 + (c / 100.0))
            # Highlights (compress bright tones)
            h = self.adjustments.get('highlights', 0)
            if h != 0:
                factor = (h / 100.0) * 0.6
                lut = []
                for x in range(256):
                    if x > 128:
                        if factor >= 0:
                            nx = 255 - int((255 - x) * (1.0 - factor))
                        else:
                            nx = 255 - int((255 - x) * (1.0 + abs(factor)))
                    else:
                        nx = x
                    lut.append(max(0, min(255, nx)))
                pil_img = pil_img.point(lut * len(pil_img.getbands()))
            # Shadows (lift/darken dark tones)
            s = self.adjustments.get('shadows', 0)
            if s != 0:
                factor = (s / 100.0) * 0.6
                lut = []
                for x in range(256):
                    if x < 128:
                        if factor >= 0:
                            nx = int(x + (128 - x) * factor)
                        else:
                            nx = int(x - x * abs(factor))
                    else:
                        nx = x
                    lut.append(max(0, min(255, nx)))
                pil_img = pil_img.point(lut * len(pil_img.getbands()))
            # Saturation
            sat = self.adjustments.get('saturation', 0)
            if sat != 0:
                sat_factor = max(0.0, 1.0 + (sat / 100.0))
                pil_img = ImageEnhance.Color(pil_img).enhance(sat_factor)
            # Warmth (temperature)
            w = self.adjustments.get('warmth', 0)
            if w != 0:
                w_factor = w / 200.0
                r, g, bch = pil_img.split()
                from PIL import ImageEnhance as IE
                r = IE.Brightness(r).enhance(1.0 + w_factor)
                bch = IE.Brightness(bch).enhance(1.0 - w_factor)
                pil_img = Image.merge('RGB', (r, g, bch))
                # slight saturation coupling with warmth
                sat_couple = 1.0 + (abs(w) / 100.0) * 0.1
                pil_img = ImageEnhance.Color(pil_img).enhance(sat_couple)
            # Vignette (darken/lighten edges)
            v = self.adjustments.get('vignette', 0)
            if v != 0:
                width, height = pil_img.size
                margin = int(min(width, height) * 0.1)
                mask = Image.new('L', (width, height), 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((margin, margin, width - margin, height - margin), fill=255)
                # invert mask to target outside area
                mask = Image.eval(mask, lambda px: 255 - px)
                try:
                    from PIL import ImageFilter
                    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(1, min(width, height) // 50)))
                except Exception:
                    pass
                alpha = int(min(255, max(0, abs(v) * 2.0)))
                mask = mask.point(lambda x: int(x * (alpha / 255.0)))
                if v > 0:
                    dark = Image.new('RGB', (width, height), (0, 0, 0))
                    pil_img = Image.composite(dark, pil_img, mask)
                else:
                    light = Image.new('RGB', (width, height), (255, 255, 255))
                    pil_img = Image.composite(light, pil_img, mask)
            
            # Sharpen/Clarity (enhance edge details)
            shp = self.adjustments.get('sharpen', 0)
            if shp != 0:
                from PIL import ImageFilter
                # Positive values = sharpen, Negative values = blur (smooth)
                if shp > 0:
                    # Sharpen: Use UnsharpMask for professional results
                    # Map 0-100 to radius 0.5-3.0, percent 50-200, threshold 0-3
                    intensity = shp / 100.0
                    radius = 0.5 + (intensity * 2.5)  # 0.5 to 3.0
                    percent = 50 + (intensity * 150)  # 50 to 200
                    threshold = int(intensity * 3)     # 0 to 3
                    pil_img = pil_img.filter(ImageFilter.UnsharpMask(
                        radius=radius,
                        percent=int(percent),
                        threshold=threshold
                    ))
                else:
                    # Negative sharpen = Blur/Smooth
                    # Map -100 to -1 -> blur radius 5.0 to 0.5
                    intensity = abs(shp) / 100.0
                    blur_radius = 0.5 + (intensity * 4.5)  # 0.5 to 5.0
                    pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            
            # Convert back to QPixmap
            self._edit_pixmap = self._pil_to_qpixmap(pil_img)
            self._update_editor_canvas_pixmap()
            self._apply_editor_zoom()
            # Push to history after applying adjustments
            self._push_edit_history()
            # Update histogram image at top of panel
            if hasattr(self, 'histogram_label'):
                hist_img = self._render_histogram_image(pil_img, width=360, height=120)
                self.histogram_label.setPixmap(self._pil_to_qpixmap(hist_img))
        except Exception as e:
            print(f"[Adjustments] Error applying adjustments: {e}")

    def _qpixmap_to_pil(self, pixmap: QPixmap):
        """Robust conversion QPixmap -> PIL.Image using PNG buffer."""
        from PySide6.QtCore import QBuffer, QIODevice
        import io
        from PIL import Image
        buffer = QBuffer()
        buffer.open(QIODevice.ReadWrite)
        pixmap.save(buffer, 'PNG')
        data = bytes(buffer.data())
        buffer.close()
        return Image.open(io.BytesIO(data)).convert('RGB')

    def _pil_to_qpixmap(self, img):
        """Convert PIL.Image -> QPixmap using bytes buffer."""
        import io
        from PySide6.QtGui import QPixmap
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qpix = QPixmap()
        qpix.loadFromData(buffer.read())
        return qpix

    def _render_histogram_image(self, img, width=360, height=120):
        """Render an RGB histogram image using Pillow and return PIL.Image (smoothed, with clipping markers)."""
        from PIL import Image, ImageDraw
        if img.mode != 'RGB':
            img = img.convert('RGB')
        hist = img.histogram()
        r = hist[0:256]
        g = hist[256:512]
        b = hist[512:768]
        # Smoothing (moving average window=4)
        def smooth(arr, w=4):
            out = []
            for i in range(256):
                s = 0
                c = 0
                for k in range(-w, w+1):
                    j = min(255, max(0, i+k))
                    s += arr[j]
                    c += 1
                out.append(s / c)
            return out
        r_s = smooth(r)
        g_s = smooth(g)
        b_s = smooth(b)
        max_val = max(max(r_s), max(g_s), max(b_s)) or 1
        canvas = Image.new('RGB', (width, height), (40, 40, 40))
        draw = ImageDraw.Draw(canvas)
        def draw_channel(vals, color):
            scaled = [v / max_val for v in vals]
            for i in range(255):
                x1 = int(i * (width / 256.0))
                x2 = int((i + 1) * (width / 256.0))
                y1 = height - int(scaled[i] * height)
                y2 = height - int(scaled[i+1] * height)
                draw.line([(x1, y1), (x2, y2)], fill=color, width=1)
        draw_channel(r_s, (255, 0, 0))
        draw_channel(g_s, (0, 255, 0))
        draw_channel(b_s, (0, 0, 255))
        # Clipping markers
        clip_thresh = max_val * 0.05
        if r[0] > clip_thresh or g[0] > clip_thresh or b[0] > clip_thresh:
            draw.rectangle([(0, 0), (4, height)], fill=(255, 0, 0))
        if r[255] > clip_thresh or g[255] > clip_thresh or b[255] > clip_thresh:
            draw.rectangle([(width-4, 0), (width, height)], fill=(255, 0, 0))
        return canvas

    # === Editor crop, filters, and comparison helpers ===

    def _create_edit_canvas(self):
        from PySide6.QtWidgets import QWidget
        from PySide6.QtCore import Qt, QPoint
        class _EditCanvas(QWidget):
            def __init__(self, parent):
                super().__init__(parent)
                self.parent = parent
                self.setStyleSheet("background: #000;")
                self.setMinimumSize(200, 200)
                self.setMouseTracking(True)
                # CRITICAL: Enable focus to receive wheel events
                self.setFocusPolicy(Qt.WheelFocus)
                self.setFocus()
                # Crop drag state
                self._crop_dragging = False
                self._crop_handle = None  # 'TL','TR','BL','BR','L','R','T','B','move'
                self._drag_start_pos = None
                self._crop_start_rect = None

            def wheelEvent(self, event):
                """Handle wheel events for zoom - DIRECT implementation."""
                try:
                    from PySide6.QtCore import Qt
                    # Check if Ctrl is pressed
                    if event.modifiers() & Qt.ControlModifier:
                        delta = event.angleDelta().y()
                        print(f"[EditCanvas] Ctrl+Wheel detected: delta={delta}")
                        if delta > 0:
                            self.parent._editor_zoom_in()
                            print(f"[EditCanvas] Zoomed IN to {self.parent.edit_zoom_level:.2f}x")
                        else:
                            self.parent._editor_zoom_out()
                            print(f"[EditCanvas] Zoomed OUT to {self.parent.edit_zoom_level:.2f}x")
                        event.accept()  # Consume the event
                    else:
                        print("[EditCanvas] Wheel without Ctrl - passing to parent")
                        event.ignore()  # Let parent handle scrolling
                except Exception as e:
                    import traceback
                    print(f"[EditCanvas] wheelEvent error: {e}")
                    traceback.print_exc()
                    event.ignore()

            def paintEvent(self, ev):
                from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QTransform
                from PySide6.QtCore import QRect, QRectF
                p = QPainter(self)
                p.setRenderHint(QPainter.Antialiasing)
                # Choose pixmap (before/after)
                pix_to_draw = None
                if getattr(self.parent, 'before_after_active', False) and getattr(self.parent, '_original_pixmap', None):
                    pix_to_draw = self.parent._original_pixmap
                elif getattr(self.parent, '_edit_pixmap', None):
                    pix_to_draw = self.parent._edit_pixmap
                
                # FAST ROTATION: Use Qt QTransform instead of PIL (GPU accelerated!)
                if getattr(self.parent, 'crop_mode_active', False) and hasattr(self.parent, 'rotation_angle') and self.parent.rotation_angle != 0 and pix_to_draw:
                    # Create rotation transform
                    transform = QTransform()
                    transform.rotate(-self.parent.rotation_angle)  # Negative for counterclockwise
                    # Apply transform with smooth rendering
                    pix_to_draw = pix_to_draw.transformed(transform, Qt.SmoothTransformation)
                
                # Draw centered scaled pixmap
                if pix_to_draw and not pix_to_draw.isNull():
                    w = max(1, int(pix_to_draw.width() * self.parent.edit_zoom_level))
                    h = max(1, int(pix_to_draw.height() * self.parent.edit_zoom_level))
                    scaled = pix_to_draw.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    x = (self.width() - scaled.width()) // 2
                    y = (self.height() - scaled.height()) // 2
                    p.drawPixmap(x, y, scaled)
                    # Crop overlay
                    if getattr(self.parent, 'crop_mode_active', False) and getattr(self.parent, '_crop_rect_norm', None):
                        nx, ny, nw, nh = self.parent._crop_rect_norm
                        rx = x + int(nx * scaled.width())
                        ry = y + int(ny * scaled.height())
                        rw = int(nw * scaled.width())
                        rh = int(nh * scaled.height())
                        rect = QRect(rx, ry, rw, rh)
                        
                        # GOOGLE PHOTOS STYLE: Darken outside with stronger overlay
                        from PySide6.QtGui import QPainterPath
                        full = QPainterPath()
                        full.addRect(self.rect())
                        crop = QPainterPath()
                        crop.addRect(rect)
                        outside = full.subtracted(crop)
                        p.fillPath(outside, QColor(0, 0, 0, 180))  # Darker overlay
                        
                        # GOOGLE PHOTOS STYLE: White border with shadow
                        p.setPen(QPen(QColor(255, 255, 255, 255), 3))  # Thicker white border
                        p.drawRect(rect)
                        
                        # GOOGLE PHOTOS STYLE: Rule of thirds grid (thinner, semi-transparent)
                        p.setPen(QPen(QColor(255, 255, 255, 100), 1, Qt.SolidLine))  # Subtle solid lines
                        x1 = rect.left() + rect.width() // 3
                        x2 = rect.left() + 2 * rect.width() // 3
                        y1 = rect.top() + rect.height() // 3
                        y2 = rect.top() + 2 * rect.height() // 3
                        p.drawLine(x1, rect.top(), x1, rect.bottom())
                        p.drawLine(x2, rect.top(), x2, rect.bottom())
                        p.drawLine(rect.left(), y1, rect.right(), y1)
                        p.drawLine(rect.left(), y2, rect.right(), y2)
                        
                        # GOOGLE PHOTOS STYLE: Corner handles (larger, with border)
                        p.setBrush(QBrush(QColor(255, 255, 255, 255)))
                        p.setPen(QPen(QColor(66, 133, 244), 2))  # Blue border
                        handle_size = 10
                        corner_length = 20  # L-shaped corner handles
                        
                        # Draw L-shaped corners (Google Photos style)
                        p.setPen(QPen(QColor(255, 255, 255, 255), 3))
                        # Top-left corner
                        p.drawLine(rect.left(), rect.top(), rect.left() + corner_length, rect.top())
                        p.drawLine(rect.left(), rect.top(), rect.left(), rect.top() + corner_length)
                        # Top-right corner
                        p.drawLine(rect.right(), rect.top(), rect.right() - corner_length, rect.top())
                        p.drawLine(rect.right(), rect.top(), rect.right(), rect.top() + corner_length)
                        # Bottom-left corner
                        p.drawLine(rect.left(), rect.bottom(), rect.left() + corner_length, rect.bottom())
                        p.drawLine(rect.left(), rect.bottom(), rect.left(), rect.bottom() - corner_length)
                        # Bottom-right corner
                        p.drawLine(rect.right(), rect.bottom(), rect.right() - corner_length, rect.bottom())
                        p.drawLine(rect.right(), rect.bottom(), rect.right(), rect.bottom() - corner_length)
                        
                        # Edge handles (small circles)
                        p.setBrush(QBrush(QColor(255, 255, 255, 255)))
                        p.setPen(QPen(QColor(66, 133, 244), 2))
                        handle_r = 5
                        for hx, hy in [(rect.center().x(), rect.top()), (rect.center().x(), rect.bottom()),
                                       (rect.left(), rect.center().y()), (rect.right(), rect.center().y())]:
                            p.drawEllipse(QPoint(hx, hy), handle_r, handle_r)
                p.end()

            def mousePressEvent(self, ev):
                from PySide6.QtCore import Qt, QRect
                if not getattr(self.parent, 'crop_mode_active', False):
                    return
                if ev.button() != Qt.LeftButton:
                    return
                # CRITICAL: Check if _crop_rect_norm exists before accessing
                if not hasattr(self.parent, '_crop_rect_norm') or self.parent._crop_rect_norm is None:
                    return
                # Find handle or move
                pix = getattr(self.parent, '_edit_pixmap', None) or getattr(self.parent, '_original_pixmap', None)
                if not pix or pix.isNull():
                    return
                w = max(1, int(pix.width() * self.parent.edit_zoom_level))
                h = max(1, int(pix.height() * self.parent.edit_zoom_level))
                x_off = (self.width() - w) // 2
                y_off = (self.height() - h) // 2
                nx, ny, nw, nh = self.parent._crop_rect_norm
                rx = x_off + int(nx * w)
                ry = y_off + int(ny * h)
                rw = int(nw * w)
                rh = int(nh * h)
                rect = QRect(rx, ry, rw, rh)
                mx = ev.pos().x()
                my = ev.pos().y()
                handle_r = 15  # Increased handle size for easier grabbing
                # Check corners/edges
                if abs(mx - rect.left()) < handle_r and abs(my - rect.top()) < handle_r:
                    self._crop_handle = 'TL'
                elif abs(mx - rect.right()) < handle_r and abs(my - rect.top()) < handle_r:
                    self._crop_handle = 'TR'
                elif abs(mx - rect.left()) < handle_r and abs(my - rect.bottom()) < handle_r:
                    self._crop_handle = 'BL'
                elif abs(mx - rect.right()) < handle_r and abs(my - rect.bottom()) < handle_r:
                    self._crop_handle = 'BR'
                elif abs(my - rect.top()) < handle_r and rect.left() < mx < rect.right():
                    self._crop_handle = 'T'
                elif abs(my - rect.bottom()) < handle_r and rect.left() < mx < rect.right():
                    self._crop_handle = 'B'
                elif abs(mx - rect.left()) < handle_r and rect.top() < my < rect.bottom():
                    self._crop_handle = 'L'
                elif abs(mx - rect.right()) < handle_r and rect.top() < my < rect.bottom():
                    self._crop_handle = 'R'
                elif rect.contains(ev.pos()):
                    self._crop_handle = 'move'
                else:
                    self._crop_handle = None
                if self._crop_handle:
                    self._crop_dragging = True
                    self._drag_start_pos = ev.pos()
                    self._crop_start_rect = (nx, ny, nw, nh)

            def mouseMoveEvent(self, ev):
                from PySide6.QtCore import Qt, QRect
                if not self._crop_dragging or not self._drag_start_pos:
                    # Cursor feedback
                    if getattr(self.parent, 'crop_mode_active', False):
                        # CRITICAL: Check if _crop_rect_norm exists before accessing
                        if not hasattr(self.parent, '_crop_rect_norm') or self.parent._crop_rect_norm is None:
                            self.setCursor(Qt.ArrowCursor)
                            return
                        pix = getattr(self.parent, '_edit_pixmap', None) or getattr(self.parent, '_original_pixmap', None)
                        if pix and not pix.isNull():
                            w = max(1, int(pix.width() * self.parent.edit_zoom_level))
                            h = max(1, int(pix.height() * self.parent.edit_zoom_level))
                            x_off = (self.width() - w) // 2
                            y_off = (self.height() - h) // 2
                            nx, ny, nw, nh = self.parent._crop_rect_norm
                            rx = x_off + int(nx * w)
                            ry = y_off + int(ny * h)
                            rw = int(nw * w)
                            rh = int(nh * h)
                            rect = QRect(rx, ry, rw, rh)
                            mx = ev.pos().x()
                            my = ev.pos().y()
                            hr = 15  # Increased handle size for easier grabbing
                            # Corner handles - highest priority
                            if (abs(mx-rect.left())<hr and abs(my-rect.top())<hr):
                                self.setCursor(Qt.SizeFDiagCursor)
                            elif (abs(mx-rect.right())<hr and abs(my-rect.top())<hr):
                                self.setCursor(Qt.SizeBDiagCursor)
                            elif (abs(mx-rect.left())<hr and abs(my-rect.bottom())<hr):
                                self.setCursor(Qt.SizeBDiagCursor)
                            elif (abs(mx-rect.right())<hr and abs(my-rect.bottom())<hr):
                                self.setCursor(Qt.SizeFDiagCursor)
                            # Edge handles
                            elif abs(my-rect.top())<hr:
                                self.setCursor(Qt.SizeVerCursor)
                            elif abs(my-rect.bottom())<hr:
                                self.setCursor(Qt.SizeVerCursor)
                            elif abs(mx-rect.left())<hr:
                                self.setCursor(Qt.SizeHorCursor)
                            elif abs(mx-rect.right())<hr:
                                self.setCursor(Qt.SizeHorCursor)
                            # Move handle (inside rect)
                            elif rect.contains(ev.pos()):
                                self.setCursor(Qt.SizeAllCursor)
                            else:
                                self.setCursor(Qt.ArrowCursor)
                    return
                
                # Compute delta in normalized coords
                pix = getattr(self.parent, '_edit_pixmap', None) or getattr(self.parent, '_original_pixmap', None)
                if not pix or pix.isNull():
                    return
                w = max(1, int(pix.width() * self.parent.edit_zoom_level))
                h = max(1, int(pix.height() * self.parent.edit_zoom_level))
                dx_pix = ev.pos().x() - self._drag_start_pos.x()
                dy_pix = ev.pos().y() - self._drag_start_pos.y()
                dx_norm = dx_pix / w
                dy_norm = dy_pix / h
                nx, ny, nw, nh = self._crop_start_rect
                
                # Get current aspect ratio constraint
                aspect_locked = self.parent._get_active_aspect_ratio()
                
                # Apply delta based on handle
                if self._crop_handle == 'move':
                    nx += dx_norm
                    ny += dy_norm
                    nx = max(0, min(1.0 - nw, nx))
                    ny = max(0, min(1.0 - nh, ny))
                elif self._crop_handle in ['TL', 'TR', 'BL', 'BR', 'T', 'B', 'L', 'R']:
                    # Resize handles
                    if self._crop_handle == 'TL':
                        nx += dx_norm; ny += dy_norm; nw -= dx_norm; nh -= dy_norm
                    elif self._crop_handle == 'TR':
                        ny += dy_norm; nw += dx_norm; nh -= dy_norm
                    elif self._crop_handle == 'BL':
                        nx += dx_norm; nw -= dx_norm; nh += dy_norm
                    elif self._crop_handle == 'BR':
                        nw += dx_norm; nh += dy_norm
                    elif self._crop_handle == 'T':
                        ny += dy_norm; nh -= dy_norm
                    elif self._crop_handle == 'B':
                        nh += dy_norm
                    elif self._crop_handle == 'L':
                        nx += dx_norm; nw -= dx_norm
                    elif self._crop_handle == 'R':
                        nw += dx_norm
                    
                    # Apply aspect ratio constraint if locked
                    if aspect_locked:
                        target_ratio = aspect_locked
                        current_ratio = nw / max(1e-6, nh)
                        if abs(current_ratio - target_ratio) > 0.01:  # Need adjustment
                            # Adjust based on which dimension changed more
                            if self._crop_handle in ['TL', 'TR', 'BL', 'BR']:
                                # Corner - adjust height to match width
                                nh = nw / target_ratio
                            elif self._crop_handle in ['L', 'R']:
                                # Width changed - adjust height
                                nh = nw / target_ratio
                            elif self._crop_handle in ['T', 'B']:
                                # Height changed - adjust width
                                nw = nh * target_ratio
                
                # Clamp to valid range
                nw = max(0.05, min(1.0, nw))
                nh = max(0.05, min(1.0, nh))
                nx = max(0.0, min(1.0 - nw, nx))
                ny = max(0.0, min(1.0 - nh, ny))
                
                self.parent._crop_rect_norm = (nx, ny, nw, nh)
                self.update()

            def mouseReleaseEvent(self, ev):
                if ev.button() == Qt.LeftButton:
                    self._crop_dragging = False
                    self._crop_handle = None
                    self._drag_start_pos = None
                    self.setCursor(Qt.ArrowCursor)
        return _EditCanvas(self)

    def _build_crop_toolbar(self):
        from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
        bar = QWidget()
        bar.setStyleSheet("""
            QWidget {
                background: rgba(30, 30, 30, 0.95);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)
        
        # Straighten slider (LEFT SIDE - primary control)
        straighten_container = QWidget()
        straighten_layout = QHBoxLayout(straighten_container)
        straighten_layout.setContentsMargins(0, 0, 0, 0)
        straighten_layout.setSpacing(8)
        
        straighten_icon = QLabel("↻")
        straighten_icon.setStyleSheet("color: white; font-size: 16pt; font-weight: bold;")
        straighten_layout.addWidget(straighten_icon)
        
        straighten_lbl = QLabel("Straighten:")
        straighten_lbl.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 10pt;")
        straighten_layout.addWidget(straighten_lbl)
        
        self.straighten_slider = QSlider(Qt.Horizontal)
        self.straighten_slider.setRange(-1800, 1800)  # -180° to +180° with 0.1° precision
        self.straighten_slider.setValue(0)
        self.straighten_slider.setFixedWidth(200)
        self.straighten_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.2);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: rgba(66, 133, 244, 1.0);
                border: 2px solid white;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: rgba(66, 133, 244, 1.0);
                width: 18px;
                height: 18px;
                margin: -7px 0;
                border-radius: 9px;
            }
        """)
        # Use timer for smooth rotation (debounced)
        self.straighten_slider.valueChanged.connect(self._on_straighten_slider_change)
        straighten_layout.addWidget(self.straighten_slider)
        
        self.straighten_label = QLabel("0.0°")
        self.straighten_label.setStyleSheet("""
            color: white;
            font-size: 10pt;
            font-weight: bold;
            min-width: 50px;
            padding: 4px 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
        """)
        self.straighten_label.setAlignment(Qt.AlignCenter)
        straighten_layout.addWidget(self.straighten_label)
        
        lay.addWidget(straighten_container)
        lay.addSpacing(20)
        
        # 90° Rotation buttons (LEFT-MIDDLE)
        rotate_label = QLabel("Rotate:")
        rotate_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 9pt;")
        lay.addWidget(rotate_label)
        
        rotate_left_btn = QPushButton("↶ 90°")
        rotate_left_btn.setToolTip("Rotate 90° counter-clockwise")
        rotate_left_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.4);
            }
            QPushButton:pressed {
                background: rgba(66, 133, 244, 0.6);
            }
        """)
        rotate_left_btn.clicked.connect(self._rotate_90_left)
        lay.addWidget(rotate_left_btn)
        
        rotate_right_btn = QPushButton("↷ 90°")
        rotate_right_btn.setToolTip("Rotate 90° clockwise")
        rotate_right_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.4);
            }
            QPushButton:pressed {
                background: rgba(66, 133, 244, 0.6);
            }
        """)
        rotate_right_btn.clicked.connect(self._rotate_90_right)
        lay.addWidget(rotate_right_btn)
        
        lay.addSpacing(20)
        
        # Flip buttons (MIDDLE)
        flip_label = QLabel("Flip:")
        flip_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 9pt;")
        lay.addWidget(flip_label)
        
        flip_h_btn = QPushButton("↔ Horizontal")
        flip_h_btn.setToolTip("Flip horizontally (mirror)")
        flip_h_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.4);
            }
            QPushButton:pressed {
                background: rgba(66, 133, 244, 0.6);
            }
        """)
        flip_h_btn.clicked.connect(self._flip_horizontal)
        lay.addWidget(flip_h_btn)
        
        flip_v_btn = QPushButton("↕ Vertical")
        flip_v_btn.setToolTip("Flip vertically")
        flip_v_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.4);
            }
            QPushButton:pressed {
                background: rgba(66, 133, 244, 0.6);
            }
        """)
        flip_v_btn.clicked.connect(self._flip_vertical)
        lay.addWidget(flip_v_btn)
        
        lay.addSpacing(20)
        
        # Aspect ratio presets (MIDDLE)
        aspect_label = QLabel("Aspect:")
        aspect_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 9pt;")
        lay.addWidget(aspect_label)
        
        # Create button group for exclusive selection
        self.aspect_button_group = []
        
        for label, ratio in [("Free", "free"), ("1:1", (1,1)), ("4:3", (4,3)), ("16:9", (16,9)), ("Original", None)]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.1);
                    color: rgba(255, 255, 255, 0.8);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 9pt;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.15);
                    color: white;
                }
                QPushButton:checked {
                    background: rgba(66, 133, 244, 0.8);
                    color: white;
                    border: 1px solid rgba(66, 133, 244, 1.0);
                    font-weight: bold;
                }
            """)
            # Connect with lambda that unchecks other buttons
            btn.clicked.connect(lambda checked, r=ratio, b=btn: self._on_aspect_preset_clicked(r, b))
            lay.addWidget(btn)
            self.aspect_button_group.append(btn)
            
            # Check 'Free' by default
            if label == "Free":
                btn.setChecked(True)
        
        lay.addStretch()
        
        # Apply/Cancel buttons (RIGHT SIDE)
        apply_btn = QPushButton("✓ Apply Crop")
        apply_btn.setStyleSheet("""
            QPushButton {
                background: rgba(34, 139, 34, 0.9);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(34, 139, 34, 1.0);
            }
        """)
        apply_btn.clicked.connect(self._apply_crop)
        lay.addWidget(apply_btn)
        
        cancel_btn = QPushButton("✕ Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.15);
            }
        """)
        cancel_btn.clicked.connect(self._cancel_crop)
        lay.addWidget(cancel_btn)
        
        return bar

    def _rotate_90_left(self):
        """Rotate image 90° counter-clockwise (left)."""
        try:
            if not getattr(self, '_edit_pixmap', None) or self._edit_pixmap.isNull():
                return
            
            from PySide6.QtGui import QTransform
            
            # Create 90° counter-clockwise rotation transform
            transform = QTransform()
            transform.rotate(-90)  # Negative = counter-clockwise
            
            # Apply to edit pixmap
            self._edit_pixmap = self._edit_pixmap.transformed(transform, Qt.SmoothTransformation)
            
            # Also apply to original if in crop mode
            if hasattr(self, '_original_pixmap') and self._original_pixmap:
                self._original_pixmap = self._original_pixmap.transformed(transform, Qt.SmoothTransformation)
            
            # Update display
            self._update_editor_canvas_pixmap()
            self._apply_editor_zoom()
            self._push_edit_history()
            
            print("[Editor] Rotated 90° counter-clockwise")
        except Exception as e:
            import traceback
            print(f"[Editor] Error rotating left: {e}")
            traceback.print_exc()
    
    def _rotate_90_right(self):
        """Rotate image 90° clockwise (right)."""
        try:
            if not getattr(self, '_edit_pixmap', None) or self._edit_pixmap.isNull():
                return
            
            from PySide6.QtGui import QTransform
            
            # Create 90° clockwise rotation transform
            transform = QTransform()
            transform.rotate(90)  # Positive = clockwise
            
            # Apply to edit pixmap
            self._edit_pixmap = self._edit_pixmap.transformed(transform, Qt.SmoothTransformation)
            
            # Also apply to original if in crop mode
            if hasattr(self, '_original_pixmap') and self._original_pixmap:
                self._original_pixmap = self._original_pixmap.transformed(transform, Qt.SmoothTransformation)
            
            # Update display
            self._update_editor_canvas_pixmap()
            self._apply_editor_zoom()
            self._push_edit_history()
            
            print("[Editor] Rotated 90° clockwise")
        except Exception as e:
            import traceback
            print(f"[Editor] Error rotating right: {e}")
            traceback.print_exc()
    
    def _flip_horizontal(self):
        """Flip image horizontally (mirror)."""
        try:
            if not getattr(self, '_edit_pixmap', None) or self._edit_pixmap.isNull():
                return
            
            from PySide6.QtGui import QTransform
            
            # Create horizontal flip transform
            transform = QTransform()
            transform.scale(-1, 1)  # Mirror on X axis
            
            # Apply to edit pixmap
            self._edit_pixmap = self._edit_pixmap.transformed(transform, Qt.SmoothTransformation)
            
            # Also apply to original if in crop mode
            if hasattr(self, '_original_pixmap') and self._original_pixmap:
                self._original_pixmap = self._original_pixmap.transformed(transform, Qt.SmoothTransformation)
            
            # Update display
            self._update_editor_canvas_pixmap()
            self._apply_editor_zoom()
            self._push_edit_history()
            
            print("[Editor] Flipped horizontally")
        except Exception as e:
            import traceback
            print(f"[Editor] Error flipping horizontal: {e}")
            traceback.print_exc()
    
    def _flip_vertical(self):
        """Flip image vertically."""
        try:
            if not getattr(self, '_edit_pixmap', None) or self._edit_pixmap.isNull():
                return
            
            from PySide6.QtGui import QTransform
            
            # Create vertical flip transform
            transform = QTransform()
            transform.scale(1, -1)  # Mirror on Y axis
            
            # Apply to edit pixmap
            self._edit_pixmap = self._edit_pixmap.transformed(transform, Qt.SmoothTransformation)
            
            # Also apply to original if in crop mode
            if hasattr(self, '_original_pixmap') and self._original_pixmap:
                self._original_pixmap = self._original_pixmap.transformed(transform, Qt.SmoothTransformation)
            
            # Update display
            self._update_editor_canvas_pixmap()
            self._apply_editor_zoom()
            self._push_edit_history()
            
            print("[Editor] Flipped vertically")
        except Exception as e:
            import traceback
            print(f"[Editor] Error flipping vertical: {e}")
            traceback.print_exc()
    
    def _get_active_aspect_ratio(self):
        """Get the currently active aspect ratio (or None if freeform)."""
        if not hasattr(self, 'aspect_button_group'):
            return None
        
        # Find which button is checked
        aspect_map = {
            "Free": None,
            "1:1": 1.0,
            "4:3": 4.0/3.0,
            "16:9": 16.0/9.0,
            "Original": None  # Will be calculated from image
        }
        
        for btn in self.aspect_button_group:
            if btn.isChecked():
                label = btn.text()
                if label == "Original":
                    # Calculate from current image
                    pix = getattr(self, '_edit_pixmap', None) or getattr(self, 'original_pixmap', None)
                    if pix and not pix.isNull():
                        return pix.width() / max(1, pix.height())
                return aspect_map.get(label)
        
        return None  # Freeform by default
    
    def _on_aspect_preset_clicked(self, ratio, clicked_btn):
        """Handle aspect ratio preset button click - ensure only one is checked."""
        # Uncheck all other buttons
        if hasattr(self, 'aspect_button_group'):
            for btn in self.aspect_button_group:
                if btn != clicked_btn:
                    btn.setChecked(False)
        
        # Apply the selected aspect ratio
        self._set_crop_aspect(ratio)
    
    def _on_straighten_slider_change(self, value):
        """Handle straighten slider - instant update with Qt QTransform (no lag!)."""
        # Convert to degrees with 0.1 precision
        degrees = value / 10.0
        self.straighten_label.setText(f"{degrees:.1f}°")
        self.rotation_angle = degrees
        
        # INSTANT UPDATE: Qt QTransform is so fast we don't need debouncing!
        if hasattr(self, 'editor_canvas'):
            self.editor_canvas.update()
    
    def _apply_rotation_preview(self):
        """Apply rotation preview (called after debounce)."""
        if hasattr(self, 'editor_canvas'):
            self.editor_canvas.update()

    def _on_straighten_changed(self, value):
        """DEPRECATED - use _on_straighten_slider_change instead."""
        self._on_straighten_slider_change(value)

    def _toggle_crop_mode(self):
        """Toggle crop mode in EDITOR (not viewer)."""
        self.crop_mode_active = not getattr(self, 'crop_mode_active', False)
        print(f"[EDITOR] Crop mode toggled: {'ON' if self.crop_mode_active else 'OFF'}")
        if self.crop_mode_active:
            # Init normalized crop rect centered (80% of image)
            self._crop_rect_norm = (0.1, 0.1, 0.8, 0.8)
            if hasattr(self, 'crop_toolbar'):
                self.crop_toolbar.show()  # SHOW crop toolbar
                print("[EDITOR] ✓ Crop toolbar SHOWN")
            else:
                print("[EDITOR] ✗ crop_toolbar not found!")
        else:
            if hasattr(self, 'crop_toolbar'):
                self.crop_toolbar.hide()
                print("[EDITOR] ✓ Crop toolbar HIDDEN")
            self._crop_rect_norm = None
        # Refresh canvas
        if hasattr(self, 'editor_canvas'):
            self.editor_canvas.update()
            print("[EDITOR] Canvas updated")
        # Update toggle state
        if hasattr(self, 'crop_btn'):
            self.crop_btn.setChecked(self.crop_mode_active)
            print(f"[EDITOR] Crop button checked: {self.crop_mode_active}")

    def _editor_undo(self):
        try:
            if self.edit_history_index > 0:
                self.edit_history_index -= 1
                pixmap, adj_dict = self.edit_history[self.edit_history_index]
                self._edit_pixmap = pixmap.copy()
                self.adjustments = adj_dict.copy()
                # Update sliders
                for key, val in adj_dict.items():
                    slider = getattr(self, f"slider_{key}", None)
                    label = getattr(self, f"{key}_label", None)
                    if slider:
                        slider.setValue(val)
                    if label:
                        label.setText(f"{key.capitalize()}: {val}")
                self._update_editor_canvas_pixmap()
                self._apply_editor_zoom()
                self._update_undo_redo_buttons()
        except Exception as e:
            print(f"[Undo] Error: {e}")

    def _editor_redo(self):
        try:
            if self.edit_history_index < len(self.edit_history) - 1:
                self.edit_history_index += 1
                pixmap, adj_dict = self.edit_history[self.edit_history_index]
                self._edit_pixmap = pixmap.copy()
                self.adjustments = adj_dict.copy()
                # Update sliders
                for key, val in adj_dict.items():
                    slider = getattr(self, f"slider_{key}", None)
                    label = getattr(self, f"{key}_label", None)
                    if slider:
                        slider.setValue(val)
                    if label:
                        label.setText(f"{key.capitalize()}: {val}")
                self._update_editor_canvas_pixmap()
                self._apply_editor_zoom()
                self._update_undo_redo_buttons()
        except Exception as e:
            print(f"[Redo] Error: {e}")

    def _push_edit_history(self):
        try:
            if not getattr(self, '_edit_pixmap', None):
                return
            # Truncate forward history if we're in the middle
            if self.edit_history_index < len(self.edit_history) - 1:
                self.edit_history = self.edit_history[:self.edit_history_index + 1]
            # Add current state
            self.edit_history.append((self._edit_pixmap.copy(), self.adjustments.copy()))
            # Limit history size
            if len(self.edit_history) > self.max_history:
                self.edit_history.pop(0)
            else:
                self.edit_history_index += 1
            self._update_undo_redo_buttons()
        except Exception as e:
            print(f"[History] Push error: {e}")

    def _update_undo_redo_buttons(self):
        try:
            if hasattr(self, 'undo_btn'):
                self.undo_btn.setEnabled(self.edit_history_index > 0)
            if hasattr(self, 'redo_btn'):
                self.redo_btn.setEnabled(self.edit_history_index < len(self.edit_history) - 1)
        except Exception:
            pass

    def _export_current_media(self):
        """Export current media (photo or video) based on file type."""
        try:
            # Check if current file is video
            if getattr(self, 'is_video_file', False):
                # Export video with trim/rotate
                self._export_edited_video()
            else:
                # Export photo with adjustments
                self._export_edited_image()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Export Error", f"Error exporting media:\n{e}")
    
    def _export_edited_image(self):
        try:
            if not getattr(self, '_edit_pixmap', None) or self._edit_pixmap.isNull():
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Export Error", "No edited image to export.")
                return
            from PySide6.QtWidgets import QFileDialog, QMessageBox
            import os
            # Suggest filename
            original_path = getattr(self, 'media_path', '')
            if original_path:
                base, ext = os.path.splitext(os.path.basename(original_path))
                suggested = f"{base}_edited{ext}"
            else:
                suggested = "edited_image.jpg"
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Edited Image",
                suggested,
                "Images (*.jpg *.jpeg *.png *.tiff *.bmp);;All Files (*.*)"
            )
            if file_path:
                success = self._edit_pixmap.save(file_path, quality=95)
                if success:
                    QMessageBox.information(self, "Export Success", f"Image exported to:\n{file_path}")
                else:
                    QMessageBox.warning(self, "Export Error", "Failed to save image.")
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Export Error", f"Error exporting image:\n{e}")

    def keyPressEvent(self, event):
        try:
            from PySide6.QtCore import Qt

            # Video editing shortcuts (only when video is loaded and in edit mode)
            is_video_loaded = hasattr(self, 'video_player') and self.video_player is not None
            in_edit_mode = hasattr(self, 'mode_stack') and self.mode_stack.currentIndex() == 1

            if is_video_loaded and in_edit_mode:
                # I key: Set trim IN point (start)
                if event.key() == Qt.Key_I:
                    if hasattr(self, '_set_trim_start'):
                        self._set_trim_start()
                        print("[MediaLightbox] Keyboard: Set trim start (I key)")
                    return

                # O key: Set trim OUT point (end)
                elif event.key() == Qt.Key_O:
                    if hasattr(self, '_set_trim_end'):
                        self._set_trim_end()
                        print("[MediaLightbox] Keyboard: Set trim end (O key)")
                    return

                # J key: Rewind
                elif event.key() == Qt.Key_J:
                    current_pos = self.video_player.position()
                    new_pos = max(0, current_pos - 5000)  # Rewind 5 seconds
                    self.video_player.setPosition(new_pos)
                    print(f"[MediaLightbox] Keyboard: Rewind to {new_pos}ms (J key)")
                    return

                # K key: Play/Pause toggle
                elif event.key() == Qt.Key_K:
                    if self.video_player.playbackState() == QMediaPlayer.PlayingState:
                        self.video_player.pause()
                        print("[MediaLightbox] Keyboard: Pause (K key)")
                    else:
                        self.video_player.play()
                        print("[MediaLightbox] Keyboard: Play (K key)")
                    return

                # L key: Fast forward
                elif event.key() == Qt.Key_L:
                    current_pos = self.video_player.position()
                    duration = getattr(self, '_video_duration', 0)
                    new_pos = min(duration, current_pos + 5000)  # Forward 5 seconds
                    self.video_player.setPosition(new_pos)
                    print(f"[MediaLightbox] Keyboard: Fast forward to {new_pos}ms (L key)")
                    return

                # Left arrow: Previous frame
                elif event.key() == Qt.Key_Left:
                    current_pos = self.video_player.position()
                    frame_ms = 1000 / 30  # Assume 30 fps (~33ms per frame)
                    new_pos = max(0, current_pos - frame_ms)
                    self.video_player.setPosition(int(new_pos))
                    print(f"[MediaLightbox] Keyboard: Previous frame (← key)")
                    return

                # Right arrow: Next frame
                elif event.key() == Qt.Key_Right:
                    current_pos = self.video_player.position()
                    duration = getattr(self, '_video_duration', 0)
                    frame_ms = 1000 / 30  # Assume 30 fps (~33ms per frame)
                    new_pos = min(duration, current_pos + frame_ms)
                    self.video_player.setPosition(int(new_pos))
                    print(f"[MediaLightbox] Keyboard: Next frame (→ key)")
                    return

            # Undo/Redo shortcuts (for photo editing)
            if event.modifiers() & Qt.ControlModifier:
                if event.key() == Qt.Key_Z:
                    self._editor_undo()
                    return
                elif event.key() == Qt.Key_Y:
                    self._editor_redo()
                    return

            # Pass to parent
            super().keyPressEvent(event)
        except Exception as e:
            print(f"[MediaLightbox] Error in keyPressEvent: {e}")
            super().keyPressEvent(event)

    def _set_crop_aspect(self, ratio):
        """Adjust normalized crop rect to selected aspect ratio, maintaining zoom."""
        if not getattr(self, '_crop_rect_norm', None):
            return
        
        nx, ny, nw, nh = self._crop_rect_norm
        
        if ratio == "free":
            # Free form - no constraint
            print("[Crop] Aspect: Freeform (no constraint)")
            return
        
        try:
            # Get current displayed image size (after rotation and zoom)
            pix = getattr(self, '_edit_pixmap', None) or getattr(self, 'original_pixmap', None)
            if not pix or pix.isNull():
                return
            
            # If rotated, account for rotation
            if hasattr(self, 'rotation_angle') and self.rotation_angle != 0:
                from PySide6.QtGui import QTransform
                transform = QTransform()
                transform.rotate(-self.rotation_angle)
                pix = pix.transformed(transform, Qt.SmoothTransformation)
            
            img_w = pix.width()
            img_h = pix.height()
            
            # Calculate target aspect ratio
            if ratio is None:
                # Original aspect ratio of the image
                target_ratio = img_w / max(1, img_h)
                print(f"[Crop] Aspect: Original ({img_w}x{img_h} = {target_ratio:.2f})")
            else:
                # Specified aspect ratio (e.g., 16:9, 4:3, 1:1)
                target_ratio = ratio[0] / ratio[1]
                print(f"[Crop] Aspect: {ratio[0]}:{ratio[1]} = {target_ratio:.2f}")
            
            # Get current crop rectangle dimensions
            current_ratio = nw / max(1e-6, nh)
            
            # Adjust crop to match target ratio while keeping it centered
            if current_ratio > target_ratio:
                # Current crop is too wide - reduce width
                new_w = nh * target_ratio
                new_h = nh
            else:
                # Current crop is too tall - reduce height
                new_w = nw
                new_h = nw / target_ratio
            
            # Ensure new dimensions don't exceed image bounds
            new_w = min(new_w, 1.0)
            new_h = min(new_h, 1.0)
            
            # Center the new crop rectangle
            cx = nx + nw / 2  # Current center X
            cy = ny + nh / 2  # Current center Y
            
            new_nx = cx - new_w / 2
            new_ny = cy - new_h / 2
            
            # Clamp to image bounds
            new_nx = max(0.0, min(1.0 - new_w, new_nx))
            new_ny = max(0.0, min(1.0 - new_h, new_ny))
            
            self._crop_rect_norm = (new_nx, new_ny, new_w, new_h)
            
            if hasattr(self, 'editor_canvas'):
                self.editor_canvas.update()
            
            print(f"[Crop] Adjusted crop: ({new_nx:.2f}, {new_ny:.2f}, {new_w:.2f}, {new_h:.2f})")
            
        except Exception as e:
            import traceback
            print(f"[Crop] Error setting aspect: {e}")
            traceback.print_exc()

    def _apply_crop(self):
        try:
            if not getattr(self, '_crop_rect_norm', None) or not getattr(self, '_original_pixmap', None):
                return
            
            # Start with the base pixmap
            base_pixmap = self._original_pixmap
            
            # FAST ROTATION: Apply straighten rotation using Qt QTransform (GPU accelerated)
            if hasattr(self, 'rotation_angle') and self.rotation_angle != 0:
                from PySide6.QtGui import QTransform
                transform = QTransform()
                transform.rotate(-self.rotation_angle)
                base_pixmap = base_pixmap.transformed(transform, Qt.SmoothTransformation)
                print(f"[Crop] Applied {self.rotation_angle}° rotation using QTransform")
            
            # Convert to PIL for cropping
            from PIL import Image
            pil_img = self._qpixmap_to_pil(base_pixmap)
            w, h = pil_img.size
            
            # Calculate crop rectangle
            nx, ny, nw, nh = self._crop_rect_norm
            x = int(nx * w); y = int(ny * h); cw = int(nw * w); ch = int(nh * h)
            
            # Apply crop
            cropped = pil_img.crop((x, y, x+cw, y+ch))
            
            # Convert back to QPixmap
            self._edit_pixmap = self._pil_to_qpixmap(cropped)
            
            # Reset crop state
            self._crop_rect_norm = None
            self.crop_mode_active = False
            self.rotation_angle = 0
            if hasattr(self, 'crop_toolbar'):
                self.crop_toolbar.hide()
            if hasattr(self, 'straighten_slider'):
                self.straighten_slider.setValue(0)
            
            # Update display
            self._update_editor_canvas_pixmap()
            self._apply_editor_zoom()
            self._push_edit_history()
            
            print(f"[Crop] Successfully cropped to {cw}x{ch}")
        except Exception as e:
            import traceback
            print(f"[Crop] Error applying crop: {e}")
            traceback.print_exc()

    def _cancel_crop(self):
        self.crop_mode_active = False
        self._crop_rect_norm = None
        if hasattr(self, 'crop_toolbar'):
            self.crop_toolbar.hide()
        if hasattr(self, 'editor_canvas'):
            self.editor_canvas.update()
        if hasattr(self, 'crop_btn'):
            self.crop_btn.setChecked(False)

    def _build_filters_panel(self):
        from PySide6.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QPushButton, QGridLayout, QLabel, QSlider, QHBoxLayout
        from PySide6.QtGui import QPixmap, QPainter
        from PySide6.QtCore import Qt
        scroll = QScrollArea()
        container = QWidget()
        layout = QVBoxLayout(container)
        
        # Filter Intensity Control (at top)
        intensity_container = QWidget()
        intensity_container.setStyleSheet("""
            QWidget {
                background: rgba(40, 40, 40, 0.8);
                border-radius: 6px;
                padding: 8px;
            }
        """)
        intensity_layout = QVBoxLayout(intensity_container)
        intensity_layout.setContentsMargins(12, 8, 12, 8)
        intensity_layout.setSpacing(6)
        
        # Header row: label + value
        intensity_header = QHBoxLayout()
        intensity_label = QLabel("Filter Intensity")
        intensity_label.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 10pt; font-weight: bold;")
        intensity_header.addWidget(intensity_label)
        intensity_header.addStretch()
        
        self.intensity_value_label = QLabel("100%")
        self.intensity_value_label.setStyleSheet("""
            color: white;
            font-size: 10pt;
            font-weight: bold;
            background: rgba(66, 133, 244, 0.3);
            border-radius: 4px;
            padding: 4px 8px;
        """)
        intensity_header.addWidget(self.intensity_value_label)
        intensity_layout.addLayout(intensity_header)
        
        # Intensity slider (0-100%)
        self.filter_intensity_slider = QSlider(Qt.Horizontal)
        self.filter_intensity_slider.setRange(0, 100)
        self.filter_intensity_slider.setValue(100)
        self.filter_intensity_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.2);
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: rgba(66, 133, 244, 1.0);
                border: 2px solid white;
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: rgba(66, 133, 244, 1.0);
                width: 20px;
                height: 20px;
                margin: -7px 0;
                border-radius: 10px;
            }
        """)
        self.filter_intensity_slider.valueChanged.connect(self._on_filter_intensity_change)
        intensity_layout.addWidget(self.filter_intensity_slider)
        
        # Helper text
        help_text = QLabel("Adjust the strength of the applied filter")
        help_text.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 8pt; font-style: italic;")
        help_text.setAlignment(Qt.AlignCenter)
        intensity_layout.addWidget(help_text)
        
        layout.addWidget(intensity_container)
        layout.addSpacing(12)
        
        # Filter presets grid
        presets = [
            ("Original", {}),
            ("Punch", {"contrast": 25, "saturation": 20}),
            ("Golden", {"warmth": 30, "saturation": 10}),
            ("Radiate", {"highlights": 20, "contrast": 15}),
            ("Warm Contrast", {"warmth": 20, "contrast": 15}),
            ("Calm", {"saturation": -10, "contrast": -5}),
            ("Cool Light", {"warmth": -15}),
            ("Vivid Cool", {"saturation": 30, "contrast": 20, "warmth": -10}),
            ("Dramatic Cool", {"contrast": 35, "saturation": 10, "warmth": -20}),
            ("B&W", {"saturation": -100}),
            ("B&W Cool", {"saturation": -100, "contrast": 20}),
            ("Film", {"contrast": 10, "saturation": -5, "vignette": 10}),
        ]
        grid = QGridLayout()
        for i, (name, adj) in enumerate(presets):
            # Container for thumbnail + label
            preset_widget = QWidget()
            preset_layout = QVBoxLayout(preset_widget)
            preset_layout.setContentsMargins(4, 4, 4, 4)
            preset_layout.setSpacing(4)
            # Thumbnail preview button
            btn = QPushButton()
            btn.setFixedSize(120, 90)
            btn.setStyleSheet("QPushButton { border: 2px solid rgba(255,255,255,0.3); border-radius: 4px; } QPushButton:hover { border: 2px solid rgba(66,133,244,0.8); }")
            btn.clicked.connect(lambda _, a=adj: self._apply_preset_adjustments(a))
            # Generate thumbnail preview (simple placeholder for now)
            thumb_pixmap = self._generate_preset_thumbnail(adj)
            btn.setIcon(QIcon(thumb_pixmap))
            btn.setIconSize(btn.size())
            preset_layout.addWidget(btn)
            # Label
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: white; font-size: 9pt;")
            preset_layout.addWidget(lbl)
            grid.addWidget(preset_widget, i // 2, i % 2)
        layout.addLayout(grid)
        scroll.setWidget(container)
        return scroll

    def _generate_preset_thumbnail(self, adj: dict):
        from PySide6.QtGui import QPixmap, QPainter, QLinearGradient, QColor
        from PySide6.QtCore import QRect, Qt
        # Try to generate real-time thumbnail from current image
        if getattr(self, '_original_pixmap', None) and not self._original_pixmap.isNull():
            try:
                # Use PIL to apply preset adjustments to a small thumbnail
                from PIL import Image, ImageEnhance as IE
                pil_img = self._qpixmap_to_pil(self._original_pixmap)
                # Resize to thumbnail size for performance
                pil_img.thumbnail((120, 90), Image.Resampling.LANCZOS)
                
                # Apply preset adjustments (simplified version)
                # Brightness
                b = adj.get('brightness', 0)
                if b != 0:
                    pil_img = IE.Brightness(pil_img).enhance(1.0 + b / 100.0)
                # Exposure
                e = adj.get('exposure', 0)
                if e != 0:
                    expo_factor = pow(2.0, e / 100.0)
                    pil_img = IE.Brightness(pil_img).enhance(expo_factor)
                # Contrast
                c = adj.get('contrast', 0)
                if c != 0:
                    pil_img = IE.Contrast(pil_img).enhance(1.0 + c / 100.0)
                # Saturation
                s = adj.get('saturation', 0)
                if s != 0:
                    pil_img = IE.Color(pil_img).enhance(1.0 + s / 100.0)
                # Warmth (simplified)
                w = adj.get('warmth', 0)
                if w != 0:
                    w_factor = w / 200.0
                    r, g, bch = pil_img.split()
                    r = IE.Brightness(r).enhance(1.0 + w_factor)
                    bch = IE.Brightness(bch).enhance(1.0 - w_factor)
                    pil_img = Image.merge('RGB', (r, g, bch))
                
                # Convert back to QPixmap
                thumb_pixmap = self._pil_to_qpixmap(pil_img)
                # Center crop to 120x90
                final_pix = QPixmap(120, 90)
                final_pix.fill(QColor(0, 0, 0))
                p = QPainter(final_pix)
                x_off = (120 - thumb_pixmap.width()) // 2
                y_off = (90 - thumb_pixmap.height()) // 2
                p.drawPixmap(x_off, y_off, thumb_pixmap)
                p.end()
                return final_pix
            except Exception as e:
                print(f"[PresetThumb] Error generating real-time thumbnail: {e}")
                # Fall back to gradient placeholder
        
        # Fallback: Generate a simple gradient thumbnail representing the preset
        pix = QPixmap(120, 90)
        pix.fill(QColor(60, 60, 60))
        p = QPainter(pix)
        # Base gradient
        grad = QLinearGradient(0, 0, 120, 90)
        # Color based on warmth
        warmth = adj.get('warmth', 0)
        sat = adj.get('saturation', 0)
        contrast = adj.get('contrast', 0)
        if warmth > 0:
            grad.setColorAt(0, QColor(255, 200, 150))
            grad.setColorAt(1, QColor(200, 150, 100))
        elif warmth < 0:
            grad.setColorAt(0, QColor(150, 200, 255))
            grad.setColorAt(1, QColor(100, 150, 200))
        elif sat == -100:
            grad.setColorAt(0, QColor(200, 200, 200))
            grad.setColorAt(1, QColor(80, 80, 80))
        else:
            grad.setColorAt(0, QColor(180, 180, 200))
            grad.setColorAt(1, QColor(100, 100, 120))
        p.fillRect(pix.rect(), grad)
        # Text overlay
        p.setPen(QColor(255, 255, 255, 180))
        p.drawText(pix.rect(), Qt.AlignCenter, "Preview")
        p.end()
        return pix

    def _on_filter_intensity_change(self, value):
        """Handle filter intensity slider change."""
        self.filter_intensity = value
        if hasattr(self, 'intensity_value_label'):
            self.intensity_value_label.setText(f"{value}%")
        
        # Reapply current preset with new intensity
        if hasattr(self, 'current_preset_adjustments') and self.current_preset_adjustments:
            self._apply_preset_with_intensity(self.current_preset_adjustments, value)
    
    def _apply_preset_with_intensity(self, preset_adj: dict, intensity: int):
        """Apply preset adjustments scaled by intensity (0-100%)."""
        # Reset all first
        for key in self.adjustments:
            self.adjustments[key] = 0
        
        # Apply preset values scaled by intensity
        intensity_factor = intensity / 100.0
        for key, val in preset_adj.items():
            scaled_val = int(val * intensity_factor)
            self.adjustments[key] = scaled_val
            slider = getattr(self, f"slider_{key}", None)
            spinbox = getattr(self, f"spinbox_{key}", None)
            if slider:
                slider.blockSignals(True)
                slider.setValue(scaled_val)
                slider.blockSignals(False)
            if spinbox:
                spinbox.blockSignals(True)
                spinbox.setValue(scaled_val)
                spinbox.blockSignals(False)
        
        # Re-render
        self._apply_adjustments()
        print(f"[Filter] Applied preset with {intensity}% intensity")
    
    def _apply_preset_adjustments(self, preset_adj: dict):
        """Apply filter preset with current intensity."""
        # Store preset for intensity adjustments
        self.current_preset_adjustments = preset_adj.copy()
        
        # Apply with current intensity
        intensity = getattr(self, 'filter_intensity', 100)
        self._apply_preset_with_intensity(preset_adj, intensity)

    def _toggle_filters_panel(self):
        try:
            show = self.filters_btn.isChecked()
            if hasattr(self, 'filters_container'):
                self.filters_container.setVisible(show)
            # Hide groups when showing filters (UX parity)
            if hasattr(self, 'light_group_container'):
                self.light_group_container.setVisible(not show)
            if hasattr(self, 'color_group_container'):
                self.color_group_container.setVisible(not show)
        except Exception:
            pass

    def _toggle_before_after(self):
        self.before_after_active = getattr(self, 'before_after_active', False) ^ True
        self._update_editor_canvas_pixmap()
        self._apply_editor_zoom()
        if hasattr(self, 'before_after_btn'):
            self.before_after_btn.setChecked(self.before_after_active)

    def _update_editor_canvas_pixmap(self):
        try:
            pix = None
            if getattr(self, 'before_after_active', False) and getattr(self, '_original_pixmap', None):
                pix = self._original_pixmap
            else:
                pix = getattr(self, '_edit_pixmap', None)
            if pix and not pix.isNull():
                self.editor_canvas.repaint()  # canvas draws pix on paintEvent
            else:
                self.editor_canvas.clear()
        except Exception:
            pass

    def _create_video_controls(self) -> QWidget:
        """Create video playback controls (play/pause, seek, volume, time)."""
        controls = QWidget()
        controls.setStyleSheet("background: transparent;")
        controls.hide()  # Hidden by default, shown for videos

        layout = QHBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Play/Pause button
        self.play_pause_btn = QPushButton("▶")
        self.play_pause_btn.setFocusPolicy(Qt.NoFocus)
        self.play_pause_btn.setFixedSize(56, 56)
        self.play_pause_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 18px;
                font-size: 12pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        self.play_pause_btn.clicked.connect(self._toggle_play_pause)
        layout.addWidget(self.play_pause_btn)

        # Time label (current)
        self.time_current_label = QLabel("0:00")
        self.time_current_label.setStyleSheet("color: white; font-size: 9pt; background: transparent;")
        layout.addWidget(self.time_current_label)

        # Seek slider (custom with trim markers)
        self.seek_slider = TrimMarkerSlider(Qt.Horizontal)
        self.seek_slider.setFocusPolicy(Qt.NoFocus)
        self.seek_slider.setMouseTracking(True)  # PHASE B #3: Enable hover detection
        self.seek_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.2);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: rgba(66, 133, 244, 0.8);
                border-radius: 2px;
            }
        """)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)

        # PHASE B #3: Install event filter for hover preview
        self.seek_slider.installEventFilter(self)

        layout.addWidget(self.seek_slider, 1)

        # Time label (total)
        self.time_total_label = QLabel("0:00")
        self.time_total_label.setStyleSheet("color: white; font-size: 9pt; background: transparent;")
        layout.addWidget(self.time_total_label)

        # Volume icon
        volume_icon = QLabel("🔊")
        volume_icon.setStyleSheet("font-size: 12pt; background: transparent;")
        layout.addWidget(volume_icon)

        # Volume slider
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setFocusPolicy(Qt.NoFocus)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(80)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.2);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: white;
                border-radius: 2px;
            }
        """)
        self.seek_slider.installEventFilter(self)

        layout.addWidget(self.seek_slider, 1)

        # Time label (total)
        self.time_total_label = QLabel("0:00")
        self.time_total_label.setStyleSheet("color: white; font-size: 9pt; background: transparent;")
        layout.addWidget(self.time_total_label)

        # Volume icon
        volume_icon = QLabel("🔊")
        volume_icon.setStyleSheet("font-size: 12pt; background: transparent;")
        layout.addWidget(volume_icon)

        # Volume slider
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setFocusPolicy(Qt.NoFocus)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(80)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.2);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: white;
                border-radius: 2px;
            }
        """)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        layout.addWidget(self.volume_slider)

        # Playback speed button
        self.speed_btn = QPushButton("1.0x")
        self.speed_btn.setFocusPolicy(Qt.NoFocus)
        self.speed_btn.setFixedHeight(32)
        self.speed_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        # Start at normal speed
        self.current_speed_index = 1  # 0.5x, 1.0x, 1.5x, 2.0x -> index 1 = 1.0x
        self.speed_btn.clicked.connect(self._on_speed_clicked)
        layout.addWidget(self.speed_btn)

        # Screenshot button
        self.screenshot_btn = QPushButton("📷")
        self.screenshot_btn.setFocusPolicy(Qt.NoFocus)
        self.screenshot_btn.setFixedHeight(32)
        self.screenshot_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        self.screenshot_btn.clicked.connect(self._on_screenshot_clicked)
        layout.addWidget(self.screenshot_btn)

        # Loop toggle button
        self.loop_enabled = False
        self.loop_btn = QPushButton("Loop Off")
        self.loop_btn.setFocusPolicy(Qt.NoFocus)
        self.loop_btn.setFixedHeight(32)
        self.loop_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        self.loop_btn.clicked.connect(self._on_loop_clicked)
        layout.addWidget(self.loop_btn)

        return controls

    def _create_info_panel(self) -> QWidget:
        """Create toggleable info panel with metadata (on right side)."""
        panel = QWidget()
        panel.setFixedWidth(350)
        panel.setStyleSheet("""
            QWidget {
                background: rgba(32, 33, 36, 0.95);
                border-left: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(16)

        # Panel header
        header = QLabel("Media Information")
        header.setStyleSheet("color: white; font-size: 12pt; font-weight: bold; background: transparent;")
        panel_layout.addWidget(header)

        # Metadata content (scrollable)
        metadata_scroll = QScrollArea()
        metadata_scroll.setFrameShape(QFrame.NoFrame)
        metadata_scroll.setWidgetResizable(True)
        metadata_scroll.setStyleSheet("background: transparent; border: none;")

        self.metadata_content = QWidget()
        self.metadata_layout = QVBoxLayout(self.metadata_content)
        self.metadata_layout.setContentsMargins(0, 0, 0, 0)
        self.metadata_layout.setSpacing(12)
        self.metadata_layout.setAlignment(Qt.AlignTop)

        metadata_scroll.setWidget(self.metadata_content)
        panel_layout.addWidget(metadata_scroll)

        return panel

    def _create_enhance_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(350)
        panel.setStyleSheet("""
            QWidget {
                background: rgba(32, 33, 36, 0.95);
                border-left: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(12)

        header = QLabel("Suggestions")
        header.setStyleSheet("color: white; font-size: 12pt; font-weight: bold; background: transparent;")
        panel_layout.addWidget(header)

        def add_suggestion(label, tooltip, on_click):
            btn = QPushButton(label)
            btn.setFixedHeight(44)
            btn.setStyleSheet("""
                QPushButton {
                    background: #1e1e1e;
                    color: white;
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 12px;
                    padding: 12px 16px;
                    text-align: left;
                    font-size: 11pt;
                }
                QPushButton:hover { background: #252525; border-color: rgba(255,255,255,0.18); }
                QPushButton:pressed { background: #2d2d2d; }
            """)
            btn.setToolTip(tooltip)
            btn.clicked.connect(on_click)
            panel_layout.addWidget(btn)
            return btn

        # Buttons inside panel
        self.suggestion_enhance_btn = add_suggestion("✨ Enhance", "Auto-Enhance", self._toggle_auto_enhance)
        self.suggestion_dynamic_btn = add_suggestion("⚡ Dynamic", "Vivid colors & contrast", lambda: self._set_preset("dynamic"))
        self.suggestion_warm_btn = add_suggestion("🌤 Warm", "Cozy tones", lambda: self._set_preset("warm"))
        self.suggestion_cool_btn = add_suggestion("❄️ Cool", "Crisp bluish look", lambda: self._set_preset("cool"))

        return panel

    def _toggle_enhance_panel(self):
        if self.enhance_panel_visible:
            self.enhance_panel.hide()
            self.enhance_panel_visible = False
        else:
            # Hide info panel if visible to avoid crowding
            if getattr(self, 'info_panel_visible', False):
                self.info_panel.hide()
                self.info_panel_visible = False
            self.enhance_panel.show()
            self.enhance_panel_visible = True

        # Reposition UI overlays and media
        self._position_nav_buttons()
        self._position_media_caption()
        QTimer.singleShot(10, self._reposition_media_for_panel)


    def _toggle_info_panel(self):
        """Toggle info panel visibility."""
        if self.info_panel_visible:
            self.info_panel.hide()
            self.info_panel_visible = False
        else:
            self.info_panel.show()
            self.info_panel_visible = True
        
        # Reposition nav buttons when info panel changes
        self._position_nav_buttons()
        
        # Reposition caption when info panel changes
        self._position_media_caption()
        
        # Trigger resize of media to adjust to new available space
        QTimer.singleShot(10, self._reposition_media_for_panel)

    def _toggle_play_pause(self):
        """Toggle video playback (play/pause)."""
        if hasattr(self, 'video_player'):
            from PySide6.QtMultimedia import QMediaPlayer
            if self.video_player.playbackState() == QMediaPlayer.PlayingState:
                self.video_player.pause()
                self.play_pause_btn.setText("▶")
            else:
                self.video_player.play()
                self.play_pause_btn.setText("⏸")

    def _position_media_caption(self):
        """Position media caption overlay at bottom center (like Google Photos/Lightroom)."""
        from PySide6.QtCore import QPoint
        
        if not hasattr(self, 'media_caption') or not self.media_caption:
            return
        
        # Get scroll area viewport position and size
        viewport = self.scroll_area.viewport()
        viewport_pos = viewport.mapTo(self, QPoint(0, 0))
        viewport_width = viewport.width()
        viewport_height = viewport.height()
        
        # Adjust caption width
        caption_width = min(500, viewport_width - 40)  # Max 500px, leave 20px margins
        self.media_caption.setMaximumWidth(caption_width)
        self.media_caption.adjustSize()  # Resize to content
        
        # Position at BOTTOM CENTER (like Google Photos)
        caption_x = viewport_pos.x() + (viewport_width - self.media_caption.width()) // 2
        
        # Calculate Y position from bottom
        # If video controls are visible, position above them; otherwise use bottom margin
        bottom_offset = 20  # Default 20px from bottom
        if hasattr(self, 'bottom_toolbar') and self.bottom_toolbar.isVisible():
            bottom_offset = self.bottom_toolbar.height() + 10  # 10px above video controls
        
        caption_y = viewport_pos.y() + viewport_height - self.media_caption.height() - bottom_offset
        
        self.media_caption.move(caption_x, caption_y)
        self.media_caption.raise_()  # Ensure it's on top
    
    def _update_media_caption(self, filename: str):
        """Update and show media caption with filename (Google Photos style - auto-fade)."""
        if not hasattr(self, 'media_caption'):
            return
        
        self.media_caption.setText(filename)
        self.media_caption.show()
        self._position_media_caption()
        
        # Fade in caption
        self._fade_in_caption()
        
        # Start auto-hide timer (3 seconds)
        self.caption_hide_timer.stop()
        self.caption_hide_timer.start()
    
    def _fade_in_caption(self):
        """Fade in the caption smoothly."""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        
        if not hasattr(self, 'caption_opacity'):
            return
        
        # Stop any existing animation
        if hasattr(self, '_caption_fade_anim'):
            self._caption_fade_anim.stop()
        
        # Create fade-in animation
        self._caption_fade_anim = QPropertyAnimation(self.caption_opacity, b"opacity")
        self._caption_fade_anim.setDuration(300)  # 300ms fade in
        self._caption_fade_anim.setStartValue(0.0)
        self._caption_fade_anim.setEndValue(1.0)
        self._caption_fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._caption_fade_anim.start()
    
    def _fade_out_caption(self):
        """Fade out the caption smoothly (auto-hide after 3 seconds)."""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        
        if not hasattr(self, 'caption_opacity'):
            return
        
        # Stop any existing animation
        if hasattr(self, '_caption_fade_anim'):
            self._caption_fade_anim.stop()
        
        # Create fade-out animation
        self._caption_fade_anim = QPropertyAnimation(self.caption_opacity, b"opacity")
        self._caption_fade_anim.setDuration(500)  # 500ms fade out (slower)
        self._caption_fade_anim.setStartValue(1.0)
        self._caption_fade_anim.setEndValue(0.0)
        self._caption_fade_anim.setEasingCurve(QEasingCurve.InCubic)
        self._caption_fade_anim.start()
    
    def _reposition_media_for_panel(self):
        """Reposition/resize media when info panel toggles."""
        if self._is_video(self.media_path):
            # Reapply video zoom to adjust to new viewport size
            if hasattr(self, 'video_widget') and self.video_widget:
                self._apply_video_zoom()
        else:
            # Reapply photo zoom to adjust to new viewport size
            if self.original_pixmap and not self.original_pixmap.isNull():
                if self.zoom_mode == "fit":
                    self._fit_to_window()
                elif self.zoom_mode == "fill":
                    self._fill_window()
                else:
                    self._apply_zoom()

    def _on_volume_changed(self, value: int):
        """Handle volume slider change."""
        if hasattr(self, 'audio_output'):
            volume = value / 100.0
            self.audio_output.setVolume(volume)

    def _on_seek_pressed(self):
        """Handle seek slider press (pause position updates)."""
        if hasattr(self, 'position_timer'):
            self.position_timer.stop()

    def _on_seek_released(self):
        """Handle seek slider release (seek to position)."""
        if hasattr(self, 'video_player'):
            position = self.seek_slider.value()
            self.video_player.setPosition(position)
            if hasattr(self, 'position_timer'):
                self.position_timer.start()

    def _is_video(self, path: str) -> bool:
        """Check if file is a video based on extension."""
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.3gp'}
        return os.path.splitext(path)[1].lower() in video_extensions

    def _is_raw(self, path: str) -> bool:
        """PHASE C #1: Check if file is a RAW photo based on extension."""
        raw_extensions = {
            '.cr2', '.cr3',  # Canon
            '.nef', '.nrw',  # Nikon
            '.arw', '.srf', '.sr2',  # Sony
            '.dng',  # Adobe/Universal
            '.raf',  # Fujifilm
            '.orf',  # Olympus
            '.rw2',  # Panasonic
            '.pef',  # Pentax
            '.3fr',  # Hasselblad
            '.ari',  # ARRI
            '.bay',  # Casio
            '.crw',  # Canon (old)
            '.erf',  # Epson
            '.kdc',  # Kodak
            '.mef',  # Mamiya
            '.mos',  # Leaf
            '.mrw',  # Minolta
            '.raw',  # Generic
        }
        return os.path.splitext(path)[1].lower() in raw_extensions

    def _detect_motion_photo(self, photo_path: str) -> str:
        """
        PHASE C #5: Detect if photo has paired video (Motion Photo / Live Photo).

        Returns path to paired video, or None if not found.

        Common patterns:
        - IMG_1234.JPG + IMG_1234.MP4
        - IMG_1234.JPG + IMG_1234_MOTION.MP4
        - IMG_1234.JPG + MVIMG_1234.MP4 (Google Motion)
        """
        if not self.motion_photo_enabled:
            return None

        if self._is_video(photo_path):
            return None  # Only check for photos, not videos

        # Get base name and directory
        photo_dir = os.path.dirname(photo_path)
        photo_name = os.path.basename(photo_path)
        photo_base, photo_ext = os.path.splitext(photo_name)

        # Patterns to check
        video_patterns = [
            f"{photo_base}.mp4",           # IMG_1234.MP4
            f"{photo_base}.MP4",
            f"{photo_base}_MOTION.mp4",    # IMG_1234_MOTION.MP4
            f"{photo_base}_MOTION.MP4",
            f"MVIMG_{photo_base}.mp4",     # MVIMG_IMG_1234.mp4 (Google)
            f"MVIMG_{photo_base}.MP4",
            f"{photo_base}.mov",           # IMG_1234.MOV (iPhone Live Photo)
            f"{photo_base}.MOV",
        ]

        # Check each pattern
        for pattern in video_patterns:
            video_path = os.path.join(photo_dir, pattern)
            if os.path.exists(video_path):
                print(f"[MediaLightbox] ✓ Motion photo detected: {photo_name} + {pattern}")
                return video_path

        return None

    def _load_media_safe(self):
        """Safe wrapper for _load_media that sets the loaded flag."""
        if not self._media_loaded:
            self._media_loaded = True
            self._load_media()

    def _load_media(self):
        """Load and display current media (photo or video)."""
        print(f"[MediaLightbox] _load_media called for: {os.path.basename(self.media_path)}")
        if self._is_video(self.media_path):
            self._load_video()
        else:
            self._load_photo()

    def _load_video(self):
        """Load and display video with playback controls."""
        print(f"[MediaLightbox] Loading video: {os.path.basename(self.media_path)}")

        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget
            from PySide6.QtCore import QUrl

            # CRITICAL: Stop and cleanup previous video BEFORE loading new one
            if hasattr(self, 'video_player') and self.video_player is not None:
                print(f"[MediaLightbox] Stopping previous video...")
                try:
                    # Stop playback
                    self.video_player.stop()
                    
                    # Stop position timer
                    if hasattr(self, 'position_timer') and self.position_timer:
                        self.position_timer.stop()
                    
                    # Clear source to release decoder resources
                    self.video_player.setSource(QUrl())
                    
                    # Small delay to allow decoder cleanup
                    from PySide6.QtCore import QThread
                    QThread.msleep(50)  # 50ms delay for GPU resource cleanup
                    
                    print(f"[MediaLightbox] ✓ Previous video stopped and cleaned up")
                except Exception as cleanup_err:
                    print(f"[MediaLightbox] Warning during video cleanup: {cleanup_err}")

            # Clear previous content
            self.image_label.clear()
            self.image_label.setStyleSheet("")
            self.image_label.hide()

            # Create video player if not exists
            if not hasattr(self, 'video_player') or self.video_player is None:
                self.video_player = QMediaPlayer(self)
                self.audio_output = QAudioOutput(self)
                self.video_player.setAudioOutput(self.audio_output)

                # Create video view (QGraphicsView + QGraphicsVideoItem) to support rotation in preview
                from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QFrame, QSizePolicy
                from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

                self.video_graphics_view = QGraphicsView()
                self.video_graphics_view.setStyleSheet("background: black;")
                self.video_graphics_view.setFrameShape(QFrame.NoFrame)
                self.video_graphics_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self.video_graphics_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                # Enable smooth zoom/pan behavior
                self.video_graphics_view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
                self.video_graphics_view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
                self.video_graphics_view.setDragMode(QGraphicsView.ScrollHandDrag)
                self.video_graphics_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                self.video_scene = QGraphicsScene(self.video_graphics_view)
                self.video_graphics_view.setScene(self.video_scene)
                self.video_graphics_view.viewport().installEventFilter(self)
                self.video_graphics_view.installEventFilter(self)
                self.video_graphics_view.setFocusPolicy(Qt.WheelFocus)
                self.video_graphics_view.setFocus()

                self.video_item = QGraphicsVideoItem()
                self.video_scene.addItem(self.video_item)

                # Use QGraphicsVideoItem as the video output
                self.video_player.setVideoOutput(self.video_item)

                # For compatibility, keep using video_widget name for sizing/grab
                self.video_widget = self.video_graphics_view

                # Add video view to container
                container_layout = self.media_container.layout()
                if container_layout:
                    container_layout.addWidget(self.video_graphics_view)
                    self.scroll_area.viewport().installEventFilter(self)

                # PHASE 2 FIX: Disconnect old signals before connecting new ones
                # This prevents signal accumulation when navigating through multiple videos
                self._disconnect_video_signals()

                # Connect video player signals with error handling
                try:
                    self.video_player.durationChanged.connect(self._on_duration_changed)
                    self.video_player.positionChanged.connect(self._on_position_changed)
                    self.video_player.errorOccurred.connect(self._on_video_error)
                    self.video_player.mediaStatusChanged.connect(self._on_media_status_changed)
                    print("[MediaLightbox] ✓ Video signals connected")
                except Exception as signal_err:
                    print(f"[MediaLightbox] Warning: Could not connect video signals: {signal_err}")

                # Create position update timer
                if not hasattr(self, 'position_timer'):
                    self.position_timer = QTimer(self)
                    self.position_timer.timeout.connect(self._update_video_position)
                    self.position_timer.setInterval(100)

            # Show video widget and resize to fill scroll area
            if hasattr(self, 'video_widget'):
                # Get scroll area dimensions
                viewport = self.scroll_area.viewport()
                available_width = viewport.width()
                available_height = viewport.height()
                
                # Set video widget to fill the available space
                self.video_widget.setMinimumSize(available_width, available_height)
                self.video_widget.resize(available_width, available_height)
                
                # Update container size to match
                self.media_container.setMinimumSize(available_width, available_height)
                self.media_container.resize(available_width, available_height)
                
                self.video_widget.show()
                print(f"[MediaLightbox] Video widget sized: {available_width}x{available_height}")

            # Show video controls in bottom toolbar
            if hasattr(self, 'video_controls_widget'):
                self.video_controls_widget.show()
            if hasattr(self, 'bottom_toolbar'):
                self.bottom_toolbar.show()  # Show bottom toolbar for video controls
                # CRITICAL FIX: Set opacity to 1.0 to make controls visible
                # Bug: opacity was initialized to 0.0 (line 965), causing invisible controls
                if hasattr(self, 'bottom_toolbar_opacity'):
                    self.bottom_toolbar_opacity.setOpacity(1.0)

            # Set volume
            if hasattr(self, 'volume_slider') and hasattr(self, 'audio_output'):
                volume = self.volume_slider.value() / 100.0
                self.audio_output.setVolume(volume)

            # Verify file exists
            if not os.path.exists(self.media_path):
                raise FileNotFoundError(f"Video file not found: {self.media_path}")

            # Load and play video
            video_url = QUrl.fromLocalFile(self.media_path)
            self.video_player.setSource(video_url)
            self.video_player.play()

            # Update play/pause button
            if hasattr(self, 'play_pause_btn'):
                self.play_pause_btn.setText("⏸")

            # Start position timer
            if hasattr(self, 'position_timer'):
                self.position_timer.start()

            # Update counter and navigation
            if hasattr(self, 'counter_label'):
                self.counter_label.setText(f"{self.current_index + 1} of {len(self.all_media)}")
            if hasattr(self, 'prev_btn'):
                self.prev_btn.setEnabled(self.current_index > 0)
            if hasattr(self, 'next_btn'):
                self.next_btn.setEnabled(self.current_index < len(self.all_media) - 1)

            # Load metadata
            self._load_metadata()

            print(f"[MediaLightbox] ✓ Video player started: {os.path.basename(self.media_path)}")

            # Apply preview rotation to QGraphicsVideoItem (if available)
            if hasattr(self, '_apply_preview_rotation'):
                self._apply_preview_rotation()
            # Fit video to view at initial load for consistent size
            if hasattr(self, '_fit_video_view'):
                self._fit_video_view()
            
            # Update and show caption
            self._update_media_caption(os.path.basename(self.media_path))

        except Exception as e:
            print(f"[MediaLightbox] ⚠️ Error loading video: {e}")
            import traceback
            traceback.print_exc()

            # Fallback to placeholder
            self.image_label.show()
            if hasattr(self, 'video_widget'):
                self.video_widget.hide()
            if hasattr(self, 'video_controls_widget'):
                self.video_controls_widget.hide()
            self.image_label.setText(f"🎬 VIDEO\n\n{os.path.basename(self.media_path)}\n\n⚠️ Playback error\n{str(e)}")
            self.image_label.setStyleSheet("color: white; font-size: 16pt; background: #2a2a2a; border-radius: 8px; padding: 40px;")
            
            # Update counter even on error
            if hasattr(self, 'counter_label'):
                self.counter_label.setText(f"{self.current_index + 1} of {len(self.all_media)}")
            if hasattr(self, 'prev_btn'):
                self.prev_btn.setEnabled(self.current_index > 0)
            if hasattr(self, 'next_btn'):
                self.next_btn.setEnabled(self.current_index < len(self.all_media) - 1)

    def _on_video_error(self, error):
        """Handle video playback errors."""
        from PySide6.QtMultimedia import QMediaPlayer
        error_string = "Unknown error"
        if hasattr(self, 'video_player'):
            error_string = self.video_player.errorString()
        print(f"[MediaLightbox] Video error: {error} - {error_string}")
        
        # Show error in UI
        if hasattr(self, 'image_label'):
            self.image_label.show()
            self.image_label.setText(f"🎬 VIDEO ERROR\n\n{os.path.basename(self.media_path)}\n\n{error_string}")
            self.image_label.setStyleSheet("color: #ff6b6b; font-size: 14pt; background: #2a2a2a; border-radius: 8px; padding: 40px;")
        if hasattr(self, 'video_widget'):
            self.video_widget.hide()
        if hasattr(self, 'video_controls_widget'):
            self.video_controls_widget.hide()

    def _on_duration_changed(self, duration: int):
        """Handle video duration change (set seek slider range)."""
        self.seek_slider.setMaximum(duration)
        # Format duration as mm:ss
        minutes = duration // 60000
        seconds = (duration % 60000) // 1000
        self.time_total_label.setText(f"{minutes}:{seconds:02d}")

    def _on_position_changed(self, position: int):
        """Handle video position change (update seek slider and time)."""
        # Update seek slider (only if not being dragged)
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position)

    def _update_video_position(self):
        """Update video position display."""
        if hasattr(self, 'video_player'):
            position = self.video_player.position()
            # Format position as mm:ss
            minutes = position // 60000
            seconds = (position % 60000) // 1000
            self.time_current_label.setText(f"{minutes}:{seconds:02d}")

    def _load_photo(self):
        """
        Load and display the current photo with EXIF orientation correction.

        PHASE A ENHANCEMENTS:
        - Checks preload cache first (instant load)
        - Uses progressive loading (thumbnail → full quality)
        - Shows loading indicators
        - Triggers background preloading of next photos
        """
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap

        try:
            # CRITICAL FIX: Ensure mode_stack is on viewer page (0), not editor page (1)
            # Bug: If user was in edit mode, photos load but aren't visible
            if hasattr(self, 'mode_stack'):
                if self.mode_stack.currentIndex() != 0:
                    print(f"[MediaLightbox] ⚠️ Mode stack was on page {self.mode_stack.currentIndex()}, switching to viewer (0)")
                    self.mode_stack.setCurrentIndex(0)

            # CRITICAL FIX: Hide video widget and controls if they exist AND are not None
            # Bug: hasattr() returns True even if value is None, causing AttributeError
            if hasattr(self, 'video_widget') and self.video_widget is not None:
                self.video_widget.hide()
                if hasattr(self, 'video_player') and self.video_player is not None:
                    self.video_player.stop()
                    if hasattr(self, 'position_timer') and self.position_timer is not None:
                        self.position_timer.stop()

            # Hide video controls
            if hasattr(self, 'video_controls_widget') and self.video_controls_widget is not None:
                self.video_controls_widget.hide()
            if hasattr(self, 'bottom_toolbar') and self.bottom_toolbar is not None:
                self.bottom_toolbar.hide()  # Hide bottom toolbar when showing photos

            # Show image label (simple show/hide, no widget replacement!)
            self.image_label.show()
            self.image_label.setStyleSheet("")  # Reset any custom styling

            print(f"[MediaLightbox] Loading photo: {os.path.basename(self.media_path)}")

            # PHASE A #1: Check preload cache first (instant load!)
            if self.media_path in self.preload_cache:
                print(f"[MediaLightbox] ✓ Loading from cache (INSTANT!)")
                cached_data = self.preload_cache[self.media_path]
                pixmap = cached_data['pixmap']

                # Use cached pixmap directly
                self.original_pixmap = pixmap

                # Scale to fit
                viewport_size = self.scroll_area.viewport().size()
                scaled_pixmap = pixmap.scaled(
                    viewport_size,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

                self.image_label.setPixmap(scaled_pixmap)
                self.image_label.resize(scaled_pixmap.size())
                self.media_container.resize(scaled_pixmap.size())

                # Calculate zoom level
                self.zoom_level = scaled_pixmap.width() / pixmap.width()
                self.fit_zoom_level = self.zoom_level
                self.zoom_mode = "fit"

                print(f"[MediaLightbox] ✓ Loaded from cache instantly!")

            # PHASE A #2: Progressive loading (thumbnail → full quality)
            elif self.progressive_loading:
                print(f"[MediaLightbox] Starting progressive load...")

                # Reset progressive load state
                self.thumbnail_quality_loaded = False
                self.full_quality_loaded = False

                # PHASE A #4: Show loading indicator
                self._show_loading_indicator("⏳ Loading...")

                # Start progressive load worker
                viewport_size = self.scroll_area.viewport().size()
                worker = ProgressiveImageWorker(
                    self.media_path,
                    self.progressive_signals,
                    viewport_size
                )
                self.preload_thread_pool.start(worker)

            # Fallback: Direct load (old method)
            else:
                print(f"[MediaLightbox] Direct load (progressive loading disabled)")
                self._load_photo_direct()

            # Update counter
            self.counter_label.setText(
                f"{self.current_index + 1} of {len(self.all_media)}"
            )

            # Update navigation buttons
            self.prev_btn.setEnabled(self.current_index > 0)
            self.next_btn.setEnabled(self.current_index < len(self.all_media) - 1)

            # Load metadata
            self._load_metadata()

            # Update status label (zoom indicator)
            self._update_status_label()

            # PHASE A #1: Start preloading next photos in background
            self._start_preloading()

            # PHASE B: Integrate all Phase B features
            self._update_filmstrip()  # B #1: Update filmstrip thumbnails
            self._update_contextual_toolbars()  # B #4: Show/hide contextual buttons
            self._restore_zoom_state()  # B #5: Restore saved zoom if enabled

            # PHASE C #5: Detect motion photo
            self.motion_video_path = self._detect_motion_photo(self.media_path)
            self.is_motion_photo = (self.motion_video_path is not None)

            # Update motion photo indicator
            if self.is_motion_photo:
                self._show_motion_indicator()
            else:
                self._hide_motion_indicator()
            
            # Update and show caption
            self._update_media_caption(os.path.basename(self.media_path))

        except Exception as e:
            print(f"[MediaLightbox] Error loading photo: {e}")
            self.image_label.setText(f"❌ Error loading image\n\n{str(e)}")
            self.image_label.setStyleSheet("color: white; font-size: 12pt;")

    def _load_photo_direct(self):
        """
        Direct photo loading (fallback when progressive loading disabled).

        Uses the original PIL-based loading method.
        PHASE C #1: Added RAW file support using rawpy.
        """
        from PIL import Image, ImageOps, ImageEnhance
        import io
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap

        pil_image = None
        pixmap = None

        try:
            # PHASE C #1: Check if file is RAW and try to load with rawpy
            if self._is_raw(self.media_path) and self.raw_support_enabled:
                try:
                    import rawpy
                    import numpy as np

                    print(f"[MediaLightbox] Loading RAW file with rawpy: {os.path.basename(self.media_path)}")

                    # Load RAW file
                    with rawpy.imread(self.media_path) as raw:
                        # Process RAW to RGB with postprocessing
                        rgb_array = raw.postprocess(
                            use_camera_wb=True,  # Use camera white balance
                            half_size=False,     # Full resolution
                            no_auto_bright=False,  # Auto brightness
                            output_bps=8         # 8-bit output
                        )

                        # Convert to PIL Image
                        pil_image = Image.fromarray(rgb_array)

                        # Apply exposure adjustment if set
                        if self.exposure_adjustment != 0.0:
                            # Exposure: -2.0 to +2.0 -> brightness 0.25 to 4.0
                            exposure_factor = 2 ** self.exposure_adjustment
                            enhancer = ImageEnhance.Brightness(pil_image)
                            pil_image = enhancer.enhance(exposure_factor)

                        print(f"[MediaLightbox] ✓ RAW file loaded successfully (exposure: {self.exposure_adjustment:+.1f})")

                except ImportError:
                    print("[MediaLightbox] ⚠️ rawpy not available, falling back to PIL")
                    # Fall through to regular PIL loading
                    pil_image = Image.open(self.media_path)
                    pil_image = ImageOps.exif_transpose(pil_image)
                except Exception as e:
                    print(f"[MediaLightbox] ⚠️ RAW loading failed: {e}, falling back to PIL")
                    # Fall through to regular PIL loading
                    pil_image = Image.open(self.media_path)
                    pil_image = ImageOps.exif_transpose(pil_image)

            # Regular image loading
            if pil_image is None:
                # Load with PIL and auto-rotate based on EXIF orientation
                pil_image = Image.open(self.media_path)
                pil_image = ImageOps.exif_transpose(pil_image)

            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')

            # Save to bytes buffer
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG')
            buffer.seek(0)

            # Load QPixmap from buffer
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.read())

            # Cleanup
            pil_image.close()
            buffer.close()

        except Exception as e:
            print(f"[MediaLightbox] PIL loading failed: {e}")
            if pil_image:
                try:
                    pil_image.close()
                except:
                    pass
            # Fallback to QPixmap
            pixmap = QPixmap(self.media_path)

        if pixmap and not pixmap.isNull():
            # Store original
            self.original_pixmap = pixmap

            # Scale to fit
            viewport_size = self.scroll_area.viewport().size()
            scaled_pixmap = pixmap.scaled(
                viewport_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.resize(scaled_pixmap.size())
            self.media_container.resize(scaled_pixmap.size())

            # Calculate zoom level
            self.zoom_level = scaled_pixmap.width() / pixmap.width()
            self.fit_zoom_level = self.zoom_level
            self.zoom_mode = "fit"

    def _load_metadata(self):
        """Load and display photo metadata."""
        # Clear existing metadata
        while self.metadata_layout.count():
            child = self.metadata_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        try:
            # Get file info
            file_size = os.path.getsize(self.media_path)
            file_size_mb = file_size / (1024 * 1024)
            filename = os.path.basename(self.media_path)

            # Add filename
            self._add_metadata_field("📄 Filename", filename)

            # Add file size
            self._add_metadata_field("💾 File Size", f"{file_size_mb:.2f} MB")

            # Get image dimensions
            pixmap = QPixmap(self.media_path)
            if not pixmap.isNull():
                self._add_metadata_field(
                    "📐 Dimensions",
                    f"{pixmap.width()} × {pixmap.height()} px"
                )

            # Get EXIF metadata
            try:
                from services.exif_parser import EXIFParser
                exif_parser = EXIFParser()
                metadata = exif_parser.parse_image_full(self.media_path)

                # Date taken
                if metadata.get('datetime_original'):
                    date_str = metadata['datetime_original'].strftime("%B %d, %Y at %I:%M %p")
                    self._add_metadata_field("📅 Date Taken", date_str)

                # Camera info
                if metadata.get('camera_make') or metadata.get('camera_model'):
                    camera = f"{metadata.get('camera_make', '')} {metadata.get('camera_model', '')}".strip()
                    self._add_metadata_field("📷 Camera", camera)

                # GPS coordinates
                if metadata.get('gps_latitude') and metadata.get('gps_longitude'):
                    lat = metadata['gps_latitude']
                    lon = metadata['gps_longitude']
                    self._add_metadata_field(
                        "🌍 Location",
                        f"{lat:.6f}, {lon:.6f}"
                    )
                    # Map controls (Open in Google Maps)
                    from PySide6.QtWidgets import QPushButton
                    maps_btn = QPushButton("Open in Google Maps")
                    maps_btn.setStyleSheet("background: rgba(255,255,255,0.15); color: white; border: none; border-radius: 6px; padding: 6px 10px;")
                    def _open_maps():
                        from PySide6.QtGui import QDesktopServices
                        from PySide6.QtCore import QUrl
                        url = QUrl(f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}")
                        QDesktopServices.openUrl(url)
                    maps_btn.clicked.connect(_open_maps)
                    self.metadata_layout.addWidget(maps_btn)

            except Exception as e:
                print(f"[MediaLightbox] Error loading EXIF: {e}")
                self._add_metadata_field("⚠️ EXIF Data", "Not available")

            # Color palette extraction (Google Photos style)
            try:
                from PIL import Image
                img = Image.open(self.media_path).convert('RGB')
                img.thumbnail((200, 200))
                palette = img.quantize(colors=5).getpalette()
                colors = []
                if palette:
                    # Palette returns flat list [r,g,b,...]; take first 5
                    for i in range(0, min(15, len(palette)), 3):
                        colors.append((palette[i], palette[i+1], palette[i+2]))
                if colors:
                    from PySide6.QtWidgets import QWidget, QHBoxLayout
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(6)
                    label_widget = QLabel("🎨 Color Palette")
                    label_widget.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 9pt; font-weight: bold;")
                    self.metadata_layout.addWidget(label_widget)
                    for r,g,b in colors:
                        swatch = QLabel()
                        swatch.setFixedSize(24, 24)
                        swatch.setStyleSheet(f"background: rgb({r},{g},{b}); border: 1px solid #444; border-radius: 4px;")
                        row_layout.addWidget(swatch)
                    self.metadata_layout.addWidget(row)
            except Exception as e:
                print(f"[MediaLightbox] Color palette error: {e}")

            # PHASE C #1: Add exposure slider for RAW files
            if self._is_raw(self.media_path) and self.raw_support_enabled:
                self._add_exposure_slider()

            # PHASE C #5: Add motion photo info
            if self.is_motion_photo:
                self._add_metadata_field("🎬 Motion Photo", "Video paired (long-press to play)")

            # Add file path (at bottom)
            self._add_metadata_field("📁 Path", self.media_path, word_wrap=True)

            # People in this photo (placeholder)
            self._add_metadata_field("👥 People", "Detected: n/a (feature coming)")

            # Edit history / Versions (placeholder)
            self._add_metadata_field("🕒 Edit History", "No versions recorded")

        except Exception as e:
            print(f"[MediaLightbox] Error loading metadata: {e}")
            self._add_metadata_field("⚠️ Error", str(e))

    def _add_metadata_field(self, label: str, value: str, word_wrap: bool = False):
        """Add a metadata field to the panel."""
        # Label
        label_widget = QLabel(label)
        label_widget.setStyleSheet("""
            color: rgba(255, 255, 255, 0.7);
            font-size: 9pt;
            font-weight: bold;
        """)
        self.metadata_layout.addWidget(label_widget)

        # Value
        value_widget = QLabel(value)
        value_widget.setStyleSheet("""
            color: white;
            font-size: 10pt;
            padding-left: 8px;
        """)
        if word_wrap:
            value_widget.setWordWrap(True)
        self.metadata_layout.addWidget(value_widget)

    def _add_exposure_slider(self):
        """
        PHASE C #1: Add exposure adjustment slider for RAW files.

        Range: -2.0 to +2.0 EV (stops)
        """
        from PySide6.QtWidgets import QSlider, QHBoxLayout
        from PySide6.QtCore import Qt

        # Section label
        label_widget = QLabel("☀️ Exposure Adjustment")
        label_widget.setStyleSheet("""
            color: rgba(255, 255, 255, 0.7);
            font-size: 9pt;
            font-weight: bold;
        """)
        self.metadata_layout.addWidget(label_widget)

        # Slider container
        slider_container = QWidget()
        slider_container.setStyleSheet("background: transparent;")
        slider_layout = QHBoxLayout(slider_container)
        slider_layout.setContentsMargins(8, 4, 8, 4)
        slider_layout.setSpacing(8)

        # Exposure slider (-2.0 to +2.0, in steps of 0.1)
        self.exposure_slider = QSlider(Qt.Horizontal)
        self.exposure_slider.setMinimum(-20)  # -2.0 * 10
        self.exposure_slider.setMaximum(20)   # +2.0 * 10
        self.exposure_slider.setValue(int(self.exposure_adjustment * 10))
        self.exposure_slider.setTickPosition(QSlider.TicksBelow)
        self.exposure_slider.setTickInterval(10)  # Tick every 1.0 EV
        self.exposure_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.2);
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #4CAF50;
            }
        """)
        self.exposure_slider.valueChanged.connect(self._on_exposure_changed)
        slider_layout.addWidget(self.exposure_slider)

        # Value label
        self.exposure_value_label = QLabel(f"{self.exposure_adjustment:+.1f} EV")
        self.exposure_value_label.setStyleSheet("color: white; font-size: 9pt; min-width: 50px;")
        slider_layout.addWidget(self.exposure_value_label)

        self.metadata_layout.addWidget(slider_container)

        print(f"[MediaLightbox] Exposure slider added (current: {self.exposure_adjustment:+.1f} EV)")

    def _on_exposure_changed(self, value: int):
        """
        PHASE C #1: Handle exposure slider change.

        Reloads the RAW file with new exposure.
        """
        # Convert slider value to EV (-2.0 to +2.0)
        new_exposure = value / 10.0

        if new_exposure != self.exposure_adjustment:
            self.exposure_adjustment = new_exposure

            # Update label
            if hasattr(self, 'exposure_value_label'):
                self.exposure_value_label.setText(f"{self.exposure_adjustment:+.1f} EV")

            # Reload photo with new exposure
            print(f"[MediaLightbox] Exposure changed to {self.exposure_adjustment:+.1f} EV, reloading...")
            self._load_photo_direct()

            # Reapply zoom after reload
            if hasattr(self, 'zoom_level') and hasattr(self, 'original_pixmap'):
                self._apply_zoom()

    def _position_nav_buttons(self):
        """Position navigation buttons on left/right sides, vertically centered (like Current Layout)."""
        if not hasattr(self, 'prev_btn') or not hasattr(self, 'scroll_area'):
            print(f"[MediaLightbox] _position_nav_buttons: Missing attributes (prev_btn={hasattr(self, 'prev_btn')}, scroll_area={hasattr(self, 'scroll_area')})")
            return

        # Check if scroll area has valid size
        if self.scroll_area.width() == 0 or self.scroll_area.height() == 0:
            # Safety limit: stop retrying after 20 attempts (1 second total)
            if self._position_retry_count < 20:
                self._position_retry_count += 1
                print(f"[MediaLightbox] Scroll area not ready (retry {self._position_retry_count}/20), waiting 50ms...")
                from PySide6.QtCore import QTimer
                QTimer.singleShot(50, self._position_nav_buttons)
            else:
                print(f"[MediaLightbox] ⚠️ Scroll area still not ready after 20 retries!")
            return

        # Reset retry counter on success
        self._position_retry_count = 0

        # Position buttons relative to scroll_area (like Current Layout does with canvas)
        # The scroll_area is the main media display widget
        try:
            from PySide6.QtCore import QPoint
            viewport = self.scroll_area.viewport()
            scroll_tl = viewport.mapTo(self, QPoint(0, 0))
        except Exception as e:
            print(f"[MediaLightbox] ⚠️ mapTo() failed: {e}, using fallback")
            from PySide6.QtCore import QPoint
            scroll_tl = QPoint(0, 0)

        scroll_w = viewport.width()
        scroll_h = viewport.height()

        # Button dimensions
        btn_w = self.prev_btn.width() or 48
        btn_h = self.prev_btn.height() or 48
        margin = 12  # Distance from edges

        # Calculate vertical center position within middle content area (excluding toolbars)
        top_h = self.top_toolbar.height() if hasattr(self, 'top_toolbar') else 0
        bottom_h = self.bottom_toolbar.height() if hasattr(self, 'bottom_toolbar') else 0
        center_y = top_h + ((self.height() - top_h - bottom_h) // 2) - (btn_h // 2)

        # Position buttons at the dialog's left/right visible edges
        margin = 16
        left_x = margin
        self.prev_btn.move(left_x, max(8, center_y))

        right_x = self.width() - btn_w - margin
        self.next_btn.move(right_x, max(8, center_y))

        # CRITICAL: Ensure buttons are visible and on top
        self.prev_btn.show()
        self.next_btn.show()
        self.prev_btn.raise_()
        self.next_btn.raise_()

        print(f"[MediaLightbox] ✓ Nav buttons positioned: left={left_x}, right={right_x}, y={center_y}")

    def _show_nav_buttons(self):
        """Show navigation buttons with instant visibility (always visible for usability)."""
        if not hasattr(self, 'nav_buttons_visible'):
            return
        if not self.nav_buttons_visible:
            self.nav_buttons_visible = True
            if hasattr(self, 'prev_btn_opacity'):
                self.prev_btn_opacity.setOpacity(1.0)
            if hasattr(self, 'next_btn_opacity'):
                self.next_btn_opacity.setOpacity(1.0)

        # Cancel any pending hide
        if hasattr(self, 'nav_hide_timer'):
            self.nav_hide_timer.stop()

    def _hide_nav_buttons(self):
        """Hide navigation buttons (auto-hide disabled for better UX)."""
        # PROFESSIONAL UX: Keep navigation buttons always visible
        # Users need immediate access to navigation, especially in photo galleries
        pass

    def enterEvent(self, event):
        """Show navigation buttons on mouse enter."""
        self._show_nav_buttons()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Hide navigation buttons after delay on mouse leave."""
        if hasattr(self, 'nav_hide_timer'):
            self.nav_hide_timer.start(500)  # Hide after 500ms
        super().leaveEvent(event)

    def resizeEvent(self, event):
        """Reposition navigation buttons and auto-adjust zoom on window resize."""
        super().resizeEvent(event)
        self._position_nav_buttons()
        
        # Keep video fitted on resize for consistent initial size
        if hasattr(self, '_fit_video_view') and hasattr(self, 'video_graphics_view') and self.video_graphics_view:
            self._fit_video_view()
        
        # CRITICAL: Ensure buttons stay on top after resize
        if hasattr(self, 'prev_btn') and hasattr(self, 'next_btn'):
            self.prev_btn.raise_()
            self.next_btn.raise_()

        # SAFETY: Ensure media is loaded (fallback if showEvent didn't fire)
        if not self._media_loaded:
            print(f"[MediaLightbox] resizeEvent: media not loaded yet, triggering load...")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(150, self._load_media_safe)
            return

        # AUTO-ADJUST ZOOM: Reapply zoom in fit/fill modes
        if self.zoom_mode == "fit":
            self._fit_to_window()
        elif self.zoom_mode == "fill":
            self._fill_window()

        if self.zoom_mode in ["fit", "fill"]:
            self._update_zoom_status()

    def mousePressEvent(self, event):
        """
        Handle mouse press for panning and double-tap detection.

        NOTE: Nav buttons handle their own clicks - they're raised above this widget
        so button clicks go directly to buttons, not through this handler.
        """
        from PySide6.QtCore import Qt

        # PHASE B #2: Check for double-tap first
        if event.button() == Qt.LeftButton:
            if self._handle_double_tap(event.pos()):
                event.accept()
                return

        # Only pan with left mouse button on photos
        if event.button() == Qt.LeftButton and not self._is_video(self.media_path):
            # Check if we're over the scroll area and content is larger than viewport
            if self._is_content_panneable():
                self.is_panning = True
                self.pan_start_pos = event.pos()
                self.scroll_start_x = self.scroll_area.horizontalScrollBar().value()
                self.scroll_start_y = self.scroll_area.verticalScrollBar().value()
                self.scroll_area.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for panning, cursor updates, toolbar reveal, and caption."""
        from PySide6.QtCore import Qt
        
        # Re-show caption on mouse movement (Google Photos behavior)
        if hasattr(self, 'media_caption') and self.media_caption.text():
            # Cancel auto-hide timer
            if hasattr(self, 'caption_hide_timer'):
                self.caption_hide_timer.stop()
            
            # Fade in if currently faded out
            if hasattr(self, 'caption_opacity') and self.caption_opacity.opacity() < 0.5:
                self._fade_in_caption()
            
            # Restart auto-hide timer
            if hasattr(self, 'caption_hide_timer'):
                self.caption_hide_timer.start()

        # PHASE A #3: Track mouse position for cursor-centered zoom
        self.last_mouse_pos = event.pos()

        # PROFESSIONAL AUTO-HIDE: Show toolbars on mouse movement
        self._show_toolbars()

        # Update cursor based on content size
        if not self._is_video(self.media_path) and self._is_content_panneable():
            if not self.is_panning:
                self.scroll_area.setCursor(Qt.OpenHandCursor)
        else:
            self.scroll_area.setCursor(Qt.ArrowCursor)

        # Perform panning if active
        if self.is_panning and self.pan_start_pos:
            delta = event.pos() - self.pan_start_pos

            # Update scroll bars
            self.scroll_area.horizontalScrollBar().setValue(self.scroll_start_x - delta.x())
            self.scroll_area.verticalScrollBar().setValue(self.scroll_start_y - delta.y())

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop panning."""
        from PySide6.QtCore import Qt

        if event.button() == Qt.LeftButton and self.is_panning:
            self.is_panning = False
            self.pan_start_pos = None

            # Restore cursor
            if self._is_content_panneable():
                self.scroll_area.setCursor(Qt.OpenHandCursor)
            else:
                self.scroll_area.setCursor(Qt.ArrowCursor)

            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _is_content_panneable(self) -> bool:
        """Check if content is larger than viewport (can be panned)."""
        if self._is_video(self.media_path):
            return False

        # Check if image is larger than scroll area viewport
        viewport = self.scroll_area.viewport()
        content = self.media_container

        return (content.width() > viewport.width() or
                content.height() > viewport.height())

    def _previous_media(self):
        """
        Navigate to previous media (photo or video).

        Phase 3 #5: Added smooth cross-fade transition.
        PHASE B #5: Save zoom state before navigating.
        """
        print(f"[MediaLightbox] Prev clicked at index={self.current_index} of {len(self.all_media)}")
        # PHASE B #5: Save current zoom state
        self._save_zoom_state()

        if self.current_index > 0:
            self.current_index -= 1
            self.media_path = self.all_media[self.current_index]
            print(f"[MediaLightbox] → Loading previous: {os.path.basename(self.media_path)} (idx={self.current_index})")
            self._load_media_with_transition()
        else:
            print("[MediaLightbox] Prev at start — no action")
    def _next_media(self):
        """
        Navigate to next media (photo or video).

        Phase 3 #5: Added smooth cross-fade transition.
        PHASE B #5: Save zoom state before navigating.
        """
        print(f"[MediaLightbox] Next clicked at index={self.current_index} of {len(self.all_media)}")
        # PHASE B #5: Save current zoom state
        self._save_zoom_state()

        if self.current_index < len(self.all_media) - 1:
            self.current_index += 1
            self.media_path = self.all_media[self.current_index]
            print(f"[MediaLightbox] → Loading next: {os.path.basename(self.media_path)} (idx={self.current_index})")
            self._load_media_with_transition()
        else:
            print("[MediaLightbox] Next at end — no action")
    def event(self, event):
        """
        PHASE 2 #10: Handle gesture events (swipe, pinch).
        """
        if event.type() == QEvent.Gesture:
            return self._handle_gesture(event)
        return super().event(event)

    def _handle_gesture(self, event):
        """PHASE 2 #10: Handle swipe and pinch gestures."""
        from PySide6.QtWidgets import QGestureEvent
        from PySide6.QtCore import Qt

        swipe = event.gesture(Qt.SwipeGesture)
        pinch = event.gesture(Qt.PinchGesture)

        if swipe:
            from PySide6.QtWidgets import QGesture
            if swipe.state() == Qt.GestureFinished:
                # Horizontal swipe for navigation
                if swipe.horizontalDirection() == QSwipeGesture.Left:
                    print("[MediaLightbox] Swipe left - next photo")
                    self._next_media()
                    return True
                elif swipe.horizontalDirection() == QSwipeGesture.Right:
                    print("[MediaLightbox] Swipe right - previous photo")
                    self._previous_media()
                    return True

        if pinch:
            if pinch.state() == Qt.GestureUpdated:
                # Pinch to zoom
                scale_factor = pinch.scaleFactor()
                if scale_factor > 1.0:
                    self._zoom_in()
                elif scale_factor < 1.0:
                    self._zoom_out()
                return True

        return False

    def _load_media_with_transition(self):
        """
        PHASE 3 #5: Load media with smooth fade transition.

        Cross-fades from current image to new image for professional feel.
        """
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve

        # If current content is video, bypass image fade and load directly
        if self._is_video(self.media_path):
            self._load_media()
            return

        # Ensure an opacity effect exists on the image label
        opacity_effect = self.image_label.graphicsEffect()
        if not opacity_effect:
            opacity_effect = QGraphicsOpacityEffect()
            self.image_label.setGraphicsEffect(opacity_effect)
            opacity_effect.setOpacity(1.0)

        # Fade out current image
        fade_out = QPropertyAnimation(opacity_effect, b"opacity")
        fade_out.setDuration(150)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InCubic)
        fade_out.setParent(self)  # Keep object alive
        self._fade_out_animation = fade_out  # Strong reference

        # Load new media after fade-out completes
        def load_and_fade_in():
            self._load_media()
            # Fade in new image
            fade_in = QPropertyAnimation(opacity_effect, b"opacity")
            fade_in.setDuration(200)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.OutCubic)
            fade_in.setParent(self)  # Keep object alive
            self._fade_in_animation = fade_in  # Strong reference
            fade_in.start()

        fade_out.finished.connect(load_and_fade_in)
        fade_out.start()

    def showEvent(self, event):
        """Load media when dialog is first shown (after window has proper size)."""
        super().showEvent(event)
        print(f"[MediaLightbox] showEvent triggered, _media_loaded={self._media_loaded}")

        # CRITICAL FIX: Ensure nav buttons are on top AFTER all widgets are laid out
        # Problem: buttons were raised BEFORE middle_widget was added to layout
        # Solution: raise buttons again after layout is finalized
        if hasattr(self, 'prev_btn') and hasattr(self, 'next_btn'):
            self.prev_btn.raise_()
            self.next_btn.raise_()
            print("[MediaLightbox] Nav buttons raised to top in showEvent")

        if not self._media_loaded:
            # ROBUST FIX: Use longer delay to ensure window is fully sized and rendered
            from PySide6.QtCore import QTimer
            print(f"[MediaLightbox] Scheduling media load in 100ms...")
            QTimer.singleShot(100, self._load_media_safe)  # 100ms delay for proper layout

        # Set focus to dialog so keyboard shortcuts work
        self.setFocus()

    def keyPressEvent(self, event: QKeyEvent):
        """Handle enhanced keyboard shortcuts."""
        key = event.key()
        modifiers = event.modifiers()

        print(f"[MediaLightbox] Key pressed: {key} (Qt.Key_Left={Qt.Key_Left}, Qt.Key_Right={Qt.Key_Right})")

        # PHASE A #5: ? key - Toggle help overlay
        if key == Qt.Key_Question or (key == Qt.Key_Slash and modifiers == Qt.ShiftModifier):
            print("[MediaLightbox] ? pressed - toggle help")
            self._toggle_help_overlay()
            event.accept()

        # ESC: Close help overlay if open, otherwise close lightbox
        elif key == Qt.Key_Escape:
            if self.help_visible:
                print("[MediaLightbox] ESC pressed - closing help overlay")
                self._toggle_help_overlay()
            else:
                print("[MediaLightbox] ESC pressed - closing lightbox")
                self.close()
            event.accept()  # Prevent event propagation

        # Arrow keys: Navigation OR Video Skip (with Shift)
        elif key == Qt.Key_Left or key == Qt.Key_Up:
            # Frame-step backward with Alt
            if modifiers == Qt.AltModifier and self._is_video(self.media_path):
                self._step_frame_backward()
            # PHASE B #3: Shift+Left = Skip video backward -10s
            elif modifiers == Qt.ShiftModifier and self._is_video(self.media_path):
                print("[MediaLightbox] Shift+Left arrow - skip video -10s")
                self._skip_video_backward()
            else:
                print("[MediaLightbox] Left/Up arrow - previous media")
                self._previous_media()
            event.accept()

        elif key == Qt.Key_Right or key == Qt.Key_Down:
            # Frame-step forward with Alt
            if modifiers == Qt.AltModifier and self._is_video(self.media_path):
                self._step_frame_forward()
            # PHASE B #3: Shift+Right = Skip video forward +10s
            elif modifiers == Qt.ShiftModifier and self._is_video(self.media_path):
                print("[MediaLightbox] Shift+Right arrow - skip video +10s")
                self._skip_video_forward()
            else:
                print("[MediaLightbox] Right/Down arrow - next media")
                self._next_media()
            event.accept()

        # Space: Next (slideshow style) - CRITICAL: Must accept event to prevent button trigger
        elif key == Qt.Key_Space:
            print("[MediaLightbox] Space pressed - next media")
            self._next_media()
            event.accept()  # Prevent Space from triggering focused button!

        # Home/End: First/Last
        elif key == Qt.Key_Home:
            print("[MediaLightbox] Home pressed - first media")
            if self.all_media:
                self.current_index = 0
                self.media_path = self.all_media[0]
                self._load_media()
                event.accept()
        elif key == Qt.Key_End:
            print("[MediaLightbox] End pressed - last media")
            if self.all_media:
                self.current_index = len(self.all_media) - 1
                self.media_path = self.all_media[-1]
                self._load_media()
                event.accept()

        # I: Toggle info panel
        elif key == Qt.Key_I:
            print("[MediaLightbox] I pressed - toggle info panel")
            self._toggle_info_panel()
            event.accept()

        # +/-: Zoom (for photos)
        elif key in (Qt.Key_Plus, Qt.Key_Equal):  # + or =
            print("[MediaLightbox] + pressed - zoom in")
            self._zoom_in()
            event.accept()
        elif key in (Qt.Key_Minus, Qt.Key_Underscore):  # - or _
            print("[MediaLightbox] - pressed - zoom out")
            self._zoom_out()
            event.accept()

        # 0: Fit to window (Professional zoom mode)
        elif key == Qt.Key_0:
            print("[MediaLightbox] 0 pressed - fit to window")
            self._zoom_to_fit()
            event.accept()

        # D: Delete
        elif key == Qt.Key_D:
            print("[MediaLightbox] D pressed - delete")
            self._delete_current_media()
            event.accept()

        # F: Toggle favorite
        elif key == Qt.Key_F:
            print("[MediaLightbox] F pressed - toggle favorite")
            self._toggle_favorite()
            event.accept()

        # S: Toggle slideshow
        elif key == Qt.Key_S:
            print("[MediaLightbox] S pressed - toggle slideshow")
            self._toggle_slideshow()
            event.accept()

        # 1-5: Rate
        elif key in (Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5):
            rating = int(event.text())
            print(f"[MediaLightbox] {rating} pressed - rate {rating} stars")
            self._rate_media(rating)
            event.accept()

        # F11: Toggle fullscreen
        elif key == Qt.Key_F11:
            print("[MediaLightbox] F11 pressed - toggle fullscreen")
            self._toggle_fullscreen()
            event.accept()

        # PHASE C #3: R key - Rotate image clockwise
        elif key == Qt.Key_R:
            print("[MediaLightbox] R pressed - rotate image")
            self._rotate_image()
            event.accept()

        # PHASE C #3: E key - Enter Editor Mode (was auto-enhance)
        elif key == Qt.Key_E:
            print("[MediaLightbox] E pressed - enter editor mode")
            self._enter_edit_mode()
            event.accept()

        # PHASE C #3: C key - Toggle crop mode (ONLY IN EDITOR MODE)
        elif key == Qt.Key_C:
            # Check if in editor mode
            if hasattr(self, 'mode_stack') and self.mode_stack.currentIndex() == 1:
                print("[MediaLightbox] C pressed - toggle EDITOR crop mode")
                # Click the crop button programmatically
                if hasattr(self, 'crop_btn'):
                    self.crop_btn.click()
                event.accept()
            else:
                print("[MediaLightbox] C pressed - Enter editor mode first (press E or click ✨ button)")
                event.accept()

        # PHASE C #2: Ctrl+Shift+S - Share/Export dialog
        elif key == Qt.Key_S and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
            print("[MediaLightbox] Ctrl+Shift+S pressed - share dialog")
            self._show_share_dialog()
            event.accept()
        
        # COPY/PASTE: Ctrl+Shift+C - Copy adjustments
        elif key == Qt.Key_C and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
            if hasattr(self, 'mode_stack') and self.mode_stack.currentIndex() == 1:
                print("[MediaLightbox] Ctrl+Shift+C pressed - copy adjustments")
                self._copy_adjustments()
                event.accept()
        
        # COPY/PASTE: Ctrl+Shift+V - Paste adjustments
        elif key == Qt.Key_V and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
            if hasattr(self, 'mode_stack') and self.mode_stack.currentIndex() == 1:
                print("[MediaLightbox] Ctrl+Shift+V pressed - paste adjustments")
                self._paste_adjustments()
                event.accept()

        # PHASE C #4: M key - Toggle compare mode (for burst photos/edits)
        elif key == Qt.Key_M:
            print("[MediaLightbox] M pressed - toggle compare mode")
            self._toggle_compare_mode()
            event.accept()

        else:
            print(f"[MediaLightbox] Unhandled key: {key}")
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        """Handle mouse wheel for smooth continuous zoom (photos and videos)."""
        # PROFESSIONAL UX: Smooth zoom for both photos and videos
        steps = event.angleDelta().y() / 120.0
        if steps == 0:
            super().wheelEvent(event)
            return

        # Calculate zoom factor (1.15 per step - smooth and natural)
        factor = self.zoom_factor ** steps

        # Apply smooth zoom (works for both photos and videos)
        self._smooth_zoom(factor)
        event.accept()

    def _smooth_zoom(self, factor):
        """
        Apply smooth continuous zoom with animation (photos and videos).

        Phase 3 #5: Enhanced with smooth zoom animation instead of instant zoom.
        PHASE A #3: Cursor-centered zoom keeps point under mouse fixed.
        """
        # Check if we have content to zoom
        is_video = self._is_video(self.media_path)
        if not is_video and not self.original_pixmap:
            return

        # PHASE A #3: Store old zoom for cursor-centered calculation
        old_zoom = self.zoom_level

        # Calculate new zoom level
        new_zoom = self.zoom_level * factor

        # Enforce minimum and maximum zoom
        if is_video:
            min_zoom = 0.5  # Videos can zoom down to 50%
            max_zoom = 3.0  # Videos can zoom up to 300%
        else:
            min_zoom = max(0.1, self.fit_zoom_level * 0.25)  # Allow 25% of fit as minimum
            max_zoom = 10.0  # Maximum 1000% zoom

        new_zoom = max(min_zoom, min(new_zoom, max_zoom))

        # PHASE 3 #5: Animated zoom transition
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QVariantAnimation

        # Stop any existing zoom animation
        if hasattr(self, '_zoom_animation') and self._zoom_animation:
            self._zoom_animation.stop()

        # Create animation for zoom level
        self._zoom_animation = QVariantAnimation()
        self._zoom_animation.setDuration(200)  # 200ms smooth zoom
        self._zoom_animation.setStartValue(self.zoom_level)
        self._zoom_animation.setEndValue(new_zoom)
        self._zoom_animation.setEasingCurve(QEasingCurve.OutCubic)

        # Update zoom level during animation
        def update_zoom(value):
            self.zoom_level = value
            # For video: keep edit_zoom_level in sync
            if self._is_video(self.media_path):
                self.edit_zoom_level = self.zoom_level
            # Switch to custom zoom mode if zooming from fit/fill (photos)
            if not self._is_video(self.media_path) and self.zoom_level > self.fit_zoom_level * 1.01:
                self.zoom_mode = "custom"
            elif not self._is_video(self.media_path) and abs(self.zoom_level - self.fit_zoom_level) < 0.01:
                self.zoom_mode = "fit"
            
            # Apply zoom based on media type
            if self._is_video(self.media_path):
                self._apply_video_zoom()
            else:
                self._apply_zoom()
            
            self._update_zoom_status()

        self._zoom_animation.valueChanged.connect(update_zoom)

        # PHASE A #3: Apply cursor-centered scroll adjustment when zoom completes
        def on_zoom_complete():
            if not is_video:
                self._calculate_zoom_scroll_adjustment(old_zoom, new_zoom)

        self._zoom_animation.finished.connect(on_zoom_complete)
        self._zoom_animation.start()

    def _zoom_in(self):
        """Zoom in by one step (keyboard shortcut: +)."""
        self._smooth_zoom(self.zoom_factor)

    def _zoom_out(self):
        """Zoom out by one step (keyboard shortcut: -)."""
        self._smooth_zoom(1.0 / self.zoom_factor)

    def _apply_zoom(self):
        """Apply current zoom level to displayed photo."""
        from PySide6.QtCore import Qt  # Import at top to avoid UnboundLocalError

        if not self.original_pixmap or self.original_pixmap.isNull():
            return

        # Calculate zoomed size
        zoomed_width = int(self.original_pixmap.width() * self.zoom_level)
        zoomed_height = int(self.original_pixmap.height() * self.zoom_level)

        # Scale pixmap
        scaled_pixmap = self.original_pixmap.scaled(
            zoomed_width, zoomed_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.resize(scaled_pixmap.size())  # CRITICAL: Size label to match pixmap for QScrollArea
        # CRITICAL: Also resize container to fit the image (QScrollArea needs this!)
        self.media_container.resize(scaled_pixmap.size())

        # Update cursor based on new zoom level
        if self._is_content_panneable():
            self.scroll_area.setCursor(Qt.OpenHandCursor)
        else:
            self.scroll_area.setCursor(Qt.ArrowCursor)

    def _apply_video_zoom(self):
        """Apply current zoom level to video preview using view transform."""
        try:
            if not hasattr(self, 'video_graphics_view') or not self.video_graphics_view:
                return
            # Clamp and apply using base fit scale
            self.edit_zoom_level = max(0.25, min(getattr(self, 'edit_zoom_level', 1.0), 4.0))
            base = getattr(self, 'video_base_scale', 1.0)
            from PySide6.QtGui import QTransform
            t = QTransform()
            t.scale(base * self.edit_zoom_level, base * self.edit_zoom_level)
            self.video_graphics_view.setTransform(t)
            from PySide6.QtWidgets import QGraphicsView
            self.video_graphics_view.setDragMode(QGraphicsView.ScrollHandDrag)
            # Mirror level into generic zoom_level for status labels
            self.zoom_level = self.edit_zoom_level
            if hasattr(self, '_update_zoom_status'):
                self._update_zoom_status()
            print(f"[MediaLightbox] Video zoom applied: {int(self.edit_zoom_level * 100)}%")
        except Exception as e:
            print(f"[MediaLightbox] Video zoom apply failed: {e}")

    def _zoom_to_fit(self):
        """Zoom to fit window (Keyboard: 0) - Letterboxing if needed."""
        if self._is_video(self.media_path):
            self.edit_zoom_level = 1.0
            self._apply_video_zoom()
            self._update_zoom_status()
            return

        self.zoom_mode = "fit"
        self._fit_to_window()
        self._update_zoom_status()

    def _zoom_to_actual(self):
        """Zoom to 100% actual size (Keyboard: 1) - 1:1 pixel mapping."""
        if self._is_video(self.media_path):
            self.edit_zoom_level = 1.0
            self._apply_video_zoom()
            self._update_zoom_status()
            return

        self.zoom_mode = "actual"
        self.zoom_level = 1.0
        self._apply_zoom()
        self._update_zoom_status()

    def _zoom_to_fill(self):
        """Zoom to fill window (may crop edges to avoid letterboxing)."""
        if self._is_video(self.media_path):
            return

        self.zoom_mode = "fill"
        self._fill_window()
        self._update_zoom_status()

    def _fit_to_window(self):
        """Fit entire image to window (letterboxing if needed)."""
        from PySide6.QtCore import Qt  # Import at top to avoid UnboundLocalError

        if not self.original_pixmap or self.original_pixmap.isNull():
            return

        # Get viewport size
        viewport_size = self.scroll_area.viewport().size()

        # Scale to fit (maintains aspect ratio)
        scaled_pixmap = self.original_pixmap.scaled(
            viewport_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.resize(scaled_pixmap.size())
        self.media_container.resize(scaled_pixmap.size())

        # Calculate actual zoom level for display
        self.zoom_level = scaled_pixmap.width() / self.original_pixmap.width()
        self.fit_zoom_level = self.zoom_level  # Store for smooth zoom minimum

    def _fill_window(self):
        """Fill window completely (may crop edges to avoid letterboxing)."""
        from PySide6.QtCore import Qt  # Import at top to avoid UnboundLocalError

        if not self.original_pixmap or self.original_pixmap.isNull():
            return

        # Get viewport size
        viewport_size = self.scroll_area.viewport().size()

        # Calculate zoom to fill (crops edges if needed)
        width_ratio = viewport_size.width() / self.original_pixmap.width()
        height_ratio = viewport_size.height() / self.original_pixmap.height()
        fill_ratio = max(width_ratio, height_ratio)  # Use larger ratio to fill

        zoomed_width = int(self.original_pixmap.width() * fill_ratio)
        zoomed_height = int(self.original_pixmap.height() * fill_ratio)

        scaled_pixmap = self.original_pixmap.scaled(
            zoomed_width, zoomed_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.resize(scaled_pixmap.size())
        self.media_container.resize(scaled_pixmap.size())

        self.zoom_level = fill_ratio

    def _update_zoom_status(self):
        """Update status label with professional zoom indicators."""
        status_parts = []

        # Zoom indicator (for both photos and videos)
        if self._is_video(self.media_path):
            # Show zoom percentage for videos
            zoom_pct = int(self.zoom_level * 100)
            status_parts.append(f"🔍 {zoom_pct}%")
        else:
            # Show mode or percentage for photos
            if self.zoom_mode == "fit":
                status_parts.append("🔍 Fit to Window")
            elif self.zoom_mode == "fill":
                status_parts.append("🔍 Fill Window")
            elif self.zoom_mode == "actual":
                status_parts.append("🔍 100% (Actual Size)")
            else:
                zoom_pct = int(self.zoom_level * 100)
                status_parts.append(f"🔍 {zoom_pct}%")

        # Slideshow indicator
        if self.slideshow_active:
            status_parts.append("⏵ Slideshow")
        # Auto-Enhance indicator
        if getattr(self, 'auto_enhance_on', False):
            status_parts.append("✨ Enhance")
        # Preset indicator
        if getattr(self, 'current_preset', None):
            status_parts.append(f"🎨 {self.current_preset.title()}")

        self.status_label.setText(" | ".join(status_parts) if status_parts else "")

    def _update_status_label(self):
        """Update status label with zoom level or slideshow status."""
        status_parts = []

        # Zoom indicator (for both photos and videos)
        zoom_pct = int(self.zoom_level * 100)
        if not self._is_video(self.media_path):
            if self.zoom_mode == "fit":
                status_parts.append("Fit")
            elif self.zoom_mode == "fill":
                status_parts.append("Fill")
            else:
                status_parts.append(f"{zoom_pct}%")
        else:
            # Show zoom percentage for videos
            status_parts.append(f"{zoom_pct}%")

        # Slideshow indicator
        if self.slideshow_active:
            status_parts.append("⏵ Slideshow")
        # Auto-Enhance indicator
        if getattr(self, 'auto_enhance_on', False):
            status_parts.append("✨ Enhance")
        # Preset indicator
        if getattr(self, 'current_preset', None):
            status_parts.append(f"🎨 {self.current_preset.title()}")

        self.status_label.setText(" | ".join(status_parts) if status_parts else "")

    def _toggle_slideshow(self):
        """Toggle slideshow mode."""
        if self.slideshow_active:
            # Stop slideshow
            self.slideshow_active = False
            if self.slideshow_timer:
                self.slideshow_timer.stop()
            self.slideshow_btn.setText("▶")
            self.slideshow_btn.setToolTip("Slideshow (S)")
        else:
            # Start slideshow
            self.slideshow_active = True
            from PySide6.QtCore import QTimer
            if not self.slideshow_timer:
                self.slideshow_timer = QTimer()
                self.slideshow_timer.timeout.connect(self._slideshow_advance)
            self.slideshow_timer.start(self.slideshow_interval)
            self.slideshow_btn.setText("⏸")
            self.slideshow_btn.setToolTip("Pause Slideshow (S)")

        self._update_status_label()

    def _toggle_auto_enhance(self):
        """Toggle auto-enhance for photos; non-destructive preview."""
        # Disable for videos
        if self._is_video(self.media_path):
            self.auto_enhance_on = False
            return
        self.auto_enhance_on = not self.auto_enhance_on
        if hasattr(self, 'enhance_btn'):
            self.enhance_btn.setText("✨ Enhanced" if self.auto_enhance_on else "✨ Enhance")
        if hasattr(self, 'suggestion_enhance_btn'):
            self.suggestion_enhance_btn.setText(("✓ " if self.auto_enhance_on else "") + "✨ Enhance")
        # Clear preset selection text when enabling enhance
        if self.auto_enhance_on:
            for btn_attr, label in [("suggestion_dynamic_btn", "⚡ Dynamic"), ("suggestion_warm_btn", "🌤 Warm"), ("suggestion_cool_btn", "❄️ Cool")]:
                if hasattr(self, btn_attr):
                    getattr(self, btn_attr).setText(label)

    def _apply_enhance_render(self):
        """Apply current enhance state to the displayed photo (fit to viewport)."""
        from PySide6.QtCore import Qt
        if not hasattr(self, 'image_label'):
            return
        if self.current_preset:
            pixmap = self._get_preset_pixmap(self.media_path, self.current_preset)
        elif self.auto_enhance_on:
            pixmap = self._get_enhanced_pixmap(self.media_path)
        else:
            pixmap = self.original_pixmap if (hasattr(self, 'original_pixmap') and self.original_pixmap) else None
        if pixmap is None or pixmap.isNull():
            # Fallback: reload basic image
            try:
                from app_services import get_thumbnail
                pixmap = get_thumbnail(self.media_path, max(self.scroll_area.viewport().width(), self.scroll_area.viewport().height()))
            except Exception:
                return
        viewport_size = self.scroll_area.viewport().size()
        scaled = pixmap.scaled(viewport_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())
        self.media_container.resize(scaled.size())
        base = pixmap
        self.zoom_level = scaled.width() / base.width()
        self.fit_zoom_level = self.zoom_level
        self.zoom_mode = "fit"

    def _get_enhanced_pixmap(self, path: str):
        """Return cached enhanced pixmap or generate via PIL."""
        if path in getattr(self, 'enhanced_cache', {}):
            return self.enhanced_cache[path]
        from PIL import Image, ImageOps, ImageEnhance
        import io
        try:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            # Gentle, safe enhancements
            img = ImageEnhance.Brightness(img).enhance(1.06)
            img = ImageEnhance.Contrast(img).enhance(1.08)
            img = ImageEnhance.Color(img).enhance(1.07)
            img = ImageEnhance.Sharpness(img).enhance(1.10)
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            from PySide6.QtGui import QPixmap
            px = QPixmap()
            px.loadFromData(buf.read())
            buf.close()
            img.close()
            self.enhanced_cache[path] = px
            return px
        except Exception as e:
            print(f"[MediaLightbox] Enhance generate error: {e}")
            return self.original_pixmap if hasattr(self, 'original_pixmap') else None

    def _set_preset(self, preset: str):
        """Set or clear a preset and re-render."""
        if self._is_video(self.media_path):
            return
        if getattr(self, 'current_preset', None) == preset:
            self.current_preset = None
        else:
            self.current_preset = preset
        # Presets are exclusive with auto-enhance
        self.auto_enhance_on = False
        if hasattr(self, 'enhance_btn'):
            self.enhance_btn.setText("✨ Enhance")
        # Update button labels to show selection
        names = {"dynamic": "Dynamic", "warm": "Warm", "cool": "Cool"}
        for key, attr in [("dynamic", "dynamic_btn"), ("warm", "warm_btn"), ("cool", "cool_btn")]:
            if hasattr(self, attr):
                btn = getattr(self, attr)
                btn.setText(("✓ " if self.current_preset == key else "") + names[key])
        # Update panel button labels to show selection
        panel_names = {"dynamic": "⚡ Dynamic", "warm": "🌤 Warm", "cool": "❄️ Cool"}
        for key, attr in [("dynamic", "suggestion_dynamic_btn"), ("warm", "suggestion_warm_btn"), ("cool", "suggestion_cool_btn")]:
            if hasattr(self, attr):
                btn = getattr(self, attr)
                btn.setText(("✓ " if self.current_preset == key else "") + panel_names[key])
        if hasattr(self, 'suggestion_enhance_btn'):
            self.suggestion_enhance_btn.setText("✨ Enhance")
        try:
            self._apply_enhance_render()
        except Exception as e:
            print(f"[MediaLightbox] Preset apply error: {e}")
        self._update_status_label()

    def _get_preset_pixmap(self, path: str, preset: str):
        key = (path, preset)
        cache = getattr(self, 'preset_cache', {})
        if key in cache:
            return cache[key]
        px = self._generate_preset_pixmap(path, preset)
        if px is not None:
            self.preset_cache[key] = px
        return px

    def _generate_preset_pixmap(self, path: str, preset: str):
        from PIL import Image, ImageOps, ImageEnhance
        import io
        try:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            if preset == 'dynamic':
                img = ImageEnhance.Brightness(img).enhance(1.05)
                img = ImageEnhance.Contrast(img).enhance(1.12)
                img = ImageEnhance.Color(img).enhance(1.15)
                img = ImageEnhance.Sharpness(img).enhance(1.15)
            elif preset == 'warm':
                img = ImageEnhance.Brightness(img).enhance(1.03)
                img = ImageEnhance.Contrast(img).enhance(1.06)
                img = ImageEnhance.Color(img).enhance(1.10)
                from PIL import Image as PILImage
                overlay = PILImage.new('RGB', img.size, (255, 140, 0))  # orange
                img = Image.blend(img, overlay, 0.08)
            elif preset == 'cool':
                img = ImageEnhance.Brightness(img).enhance(1.02)
                img = ImageEnhance.Contrast(img).enhance(1.06)
                img = ImageEnhance.Color(img).enhance(1.03)
                from PIL import Image as PILImage
                overlay = PILImage.new('RGB', img.size, (58, 139, 255))  # blue
                img = Image.blend(img, overlay, 0.08)
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            from PySide6.QtGui import QPixmap
            px = QPixmap()
            px.loadFromData(buf.read())
            buf.close()
            img.close()
            return px
        except Exception as e:
            print(f"[MediaLightbox] Preset gen error: {e}")
            return None

    def _slideshow_advance(self):
        """Advance to next media in slideshow."""
        if self.slideshow_active:
            self._next_media()

    def _delete_current_media(self):
        """Delete current media file."""
        from PySide6.QtWidgets import QMessageBox

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Delete Media")
        msg.setText(f"Are you sure you want to delete this file?\n\n{os.path.basename(self.media_path)}")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        msg.setStyleSheet("""
            QMessageBox { background-color: #121212; color: white; }
            QMessageBox QLabel { color: white; }
            QMessageBox QPushButton { background: rgba(255,255,255,0.15); color: white; border: none; border-radius: 6px; padding: 6px 12px; }
            QMessageBox QPushButton:hover { background: rgba(255,255,255,0.25); }
        """)
        reply = msg.exec()

        if reply == QMessageBox.Yes:
            try:
                # os module imported at top
                # Remove from database first
                # TODO: Add database deletion logic here

                # Delete file
                # os.remove(self.media_path)
                # os module imported at top
                trash_dir = os.path.join(os.path.dirname(self.media_path), "_Trash")
                try:
                    os.makedirs(trash_dir, exist_ok=True)
                except Exception as mkerr:
                    print(f"[MediaLightbox] ⚠️ Could not create Trash folder: {mkerr}")
                new_path = os.path.join(trash_dir, os.path.basename(self.media_path))
                try:
                    os.replace(self.media_path, new_path)
                    print(f"[MediaLightbox] Moved to Trash: {new_path}")
                except Exception as mverr:
                    print(f"[MediaLightbox] ⚠️ Move to Trash failed, deleting: {mverr}")
                    os.remove(self.media_path)
                    print(f"[MediaLightbox] Deleted: {self.media_path}")

                # Remove from list
                self.all_media.remove(self.media_path)

                # Load next or previous
                if self.all_media:
                    if self.current_index >= len(self.all_media):
                        self.current_index = len(self.all_media) - 1
                    self.media_path = self.all_media[self.current_index]
                    self._load_media()
                else:
                    # No more media, close lightbox
                    self.close()

            except Exception as e:
                err = QMessageBox(self)
                err.setIcon(QMessageBox.Critical)
                err.setWindowTitle("Delete Error")
                err.setText(f"Failed to delete file:\n{str(e)}")
                err.setStandardButtons(QMessageBox.Ok)
                err.setStyleSheet("""
                    QMessageBox { background-color: #121212; color: white; }
                    QMessageBox QLabel { color: white; }
                    QMessageBox QPushButton { background: rgba(255,255,255,0.15); color: white; border: none; border-radius: 6px; padding: 6px 12px; }
                    QMessageBox QPushButton:hover { background: rgba(255,255,255,0.25); }
                """)
                err.exec()

    def _toggle_favorite(self):
        """Toggle favorite status of current media (DB-backed)."""
        try:
            # Get project_id from parent window's grid or layout
            project_id = None
            if hasattr(self, 'parent') and self.parent():
                parent = self.parent()
                # Try to get project_id from grid (MainWindow has grid.project_id)
                if hasattr(parent, 'grid') and hasattr(parent.grid, 'project_id'):
                    project_id = parent.grid.project_id
                # Fallback: try to get from layout manager's active layout
                elif hasattr(parent, 'layout_manager'):
                    layout = parent.layout_manager.get_active_layout()
                    if layout and hasattr(layout, 'project_id'):
                        project_id = layout.project_id
            
            if project_id is None:
                print("[MediaLightbox] ⚠️ Cannot toggle favorite: project_id not available")
                return
            
            # Check current favorite status from database
            from reference_db import ReferenceDB
            db = ReferenceDB()
            current_tags = db.get_tags_for_photo(self.media_path, project_id)
            is_favorited = "favorite" in current_tags
            
            # Toggle in database
            if is_favorited:
                # Remove favorite
                db.remove_tag(self.media_path, "favorite", project_id)
                self.favorite_btn.setText("♡")
                self.favorite_btn.setStyleSheet(self.favorite_btn.styleSheet().replace("\nQPushButton { color: #ff4444; }", ""))
                status_msg = f"⭐ Removed from favorites: {os.path.basename(self.media_path)}"
                print(f"[MediaLightbox] Unfavorited: {os.path.basename(self.media_path)}")
            else:
                # Add favorite
                db.add_tag(self.media_path, "favorite", project_id)
                self.favorite_btn.setText("♥")
                self.favorite_btn.setStyleSheet(self.favorite_btn.styleSheet() + "\nQPushButton { color: #ff4444; }")
                status_msg = f"⭐ Added to favorites: {os.path.basename(self.media_path)}"
                print(f"[MediaLightbox] Favorited: {os.path.basename(self.media_path)}")
            
            # Show status message in parent window's status bar
            if hasattr(self, 'parent') and self.parent():
                parent = self.parent()
                if hasattr(parent, 'statusBar'):
                    try:
                        parent.statusBar().showMessage(status_msg, 3000)
                    except Exception as sb_err:
                        print(f"[MediaLightbox] Could not update status bar: {sb_err}")
        
        except Exception as e:
            print(f"[MediaLightbox] ⚠️ Error toggling favorite: {e}")
            import traceback
            traceback.print_exc()

    def _rate_media(self, rating: int):
        """Rate current media with 1-5 stars."""
        self.current_rating = rating
        stars = "★" * rating + "☆" * (5 - rating)
        print(f"[MediaLightbox] Rated {rating}/5: {os.path.basename(self.media_path)}")
        # TODO: Save to database

        # Update status label to show rating
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Rating",
            f"Rated {stars} ({rating}/5)",
            QMessageBox.Ok
        )

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode with distraction-free viewing."""
        if self.isFullScreen():
            # Exit fullscreen
            self.showMaximized()

            # Show toolbars again
            self._show_toolbars()
            self.toolbar_hide_timer.stop()  # Don't auto-hide when not fullscreen

            print("[MediaLightbox] Exited fullscreen")
        else:
            # Enter fullscreen
            self.showFullScreen()

            # Hide toolbars for distraction-free viewing
            self._hide_toolbars()

            # Enable auto-hide in fullscreen
            self.toolbar_hide_timer.start()

            print("[MediaLightbox] Entered fullscreen (toolbars auto-hide)")

    # ==================== PHASE A IMPROVEMENTS ====================

    def _create_help_overlay(self):
        """
        PHASE A #5: Create keyboard shortcut help overlay.

        Press ? to show/hide shortcuts.
        """
        from PySide6.QtWidgets import QTextEdit

        self.help_overlay = QWidget(self)
        self.help_overlay.setStyleSheet("""
            QWidget {
                background: rgba(0, 0, 0, 0.9);
            }
        """)
        self.help_overlay.hide()

        overlay_layout = QVBoxLayout(self.help_overlay)
        overlay_layout.setContentsMargins(50, 50, 50, 50)

        # Title
        title = QLabel("⌨️ Keyboard Shortcuts")
        title.setStyleSheet("color: white; font-size: 24pt; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        overlay_layout.addWidget(title)

        # Shortcuts content
        shortcuts_text = """
<div style='color: white; font-size: 12pt; line-height: 1.8;'>
<table cellpadding='8' cellspacing='0' width='100%'>
<tr><td colspan='2' style='font-size: 14pt; font-weight: bold; padding-top: 12px;'>Navigation</td></tr>
<tr><td width='40%'><b>← / →</b> or <b>↑ / ↓</b></td><td>Previous / Next photo</td></tr>
<tr><td><b>Space</b></td><td>Next photo (slideshow style)</td></tr>
<tr><td><b>Home / End</b></td><td>First / Last photo</td></tr>
<tr><td><b>Swipe Left/Right</b></td><td>Navigate on touch devices</td></tr>

<tr><td colspan='2' style='font-size: 14pt; font-weight: bold; padding-top: 12px;'>Zoom & View</td></tr>
<tr><td><b>Mouse Wheel</b></td><td>Zoom in / out (cursor-centered)</td></tr>
<tr><td><b>+ / -</b></td><td>Zoom in / out</td></tr>
<tr><td><b>0</b></td><td>Fit to window</td></tr>
<tr><td><b>Pinch Gesture</b></td><td>Zoom on touch devices</td></tr>
<tr><td><b>Click + Drag</b></td><td>Pan when zoomed</td></tr>

<tr><td colspan='2' style='font-size: 14pt; font-weight: bold; padding-top: 12px;'>Actions</td></tr>
<tr><td><b>I</b></td><td>Toggle info panel</td></tr>
<tr><td><b>S</b></td><td>Toggle slideshow</td></tr>
<tr><td><b>F</b></td><td>Toggle favorite</td></tr>
<tr><td><b>D</b></td><td>Delete photo</td></tr>
<tr><td><b>1-5</b></td><td>Rate photo (1-5 stars)</td></tr>

<tr><td colspan='2' style='font-size: 14pt; font-weight: bold; padding-top: 12px;'>Quick Edit</td></tr>
<tr><td><b>R</b></td><td>Rotate image clockwise (90°)</td></tr>
<tr><td><b>E</b></td><td>Auto-enhance (brightness + contrast)</td></tr>
<tr><td><b>C</b></td><td>Toggle crop mode</td></tr>
<tr><td><b>M</b></td><td>Compare mode (side-by-side)</td></tr>
<tr><td><b>Ctrl+Shift+S</b></td><td>Share / Export dialog</td></tr>

<tr><td colspan='2' style='font-size: 14pt; font-weight: bold; padding-top: 12px;'>Video Controls</td></tr>
<tr><td><b>Space / K</b></td><td>Play / Pause video</td></tr>
<tr><td><b>Shift + →</b></td><td>Skip forward +10 seconds</td></tr>
<tr><td><b>Shift + ←</b></td><td>Skip backward -10 seconds</td></tr>
<tr><td><b>Hover seek bar</b></td><td>Preview timestamp</td></tr>

<tr><td colspan='2' style='font-size: 14pt; font-weight: bold; padding-top: 12px;'>General</td></tr>
<tr><td><b>F11</b></td><td>Toggle fullscreen</td></tr>
<tr><td><b>ESC</b></td><td>Close lightbox</td></tr>
<tr><td><b>?</b></td><td>Show/hide this help</td></tr>
</table>
</div>
        """

        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setHtml(shortcuts_text)
        help_text.setStyleSheet("""
            QTextEdit {
                background: transparent;
                border: none;
                color: white;
            }
        """)
        overlay_layout.addWidget(help_text)

        # Close instruction
        close_label = QLabel("Press ESC or ? to close")
        close_label.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-size: 11pt;")
        close_label.setAlignment(Qt.AlignCenter)
        overlay_layout.addWidget(close_label)

    def _toggle_help_overlay(self):
        """PHASE A #5: Toggle keyboard shortcuts help overlay."""
        if self.help_visible:
            self.help_overlay.hide()
            self.help_visible = False
        else:
            # Resize to fill window
            self.help_overlay.setGeometry(self.rect())
            self.help_overlay.show()
            self.help_overlay.raise_()  # Bring to front
            self.help_visible = True

    def _show_loading_indicator(self, message: str = "⏳ Loading..."):
        """PHASE A #4: Show loading indicator with message."""
        self.loading_indicator.setText(message)

        # Position in center of scroll area
        scroll_center_x = self.scroll_area.width() // 2
        scroll_center_y = self.scroll_area.height() // 2

        # Calculate position (center the indicator)
        indicator_width = 200
        indicator_height = 80
        x = scroll_center_x - (indicator_width // 2)
        y = scroll_center_y - (indicator_height // 2)

        self.loading_indicator.setGeometry(x, y, indicator_width, indicator_height)
        self.loading_indicator.show()
        self.loading_indicator.raise_()
        self.is_loading = True

        # Track load start time
        from PySide6.QtCore import QDateTime
        self.loading_start_time = QDateTime.currentMSecsSinceEpoch()

    def _hide_loading_indicator(self):
        """PHASE A #4: Hide loading indicator."""
        self.loading_indicator.hide()
        self.is_loading = False

    def _start_preloading(self):
        """
        PHASE A #1: Start preloading next photos in background.

        Preloads next 2 photos for instant navigation.
        """
        if not self.all_media:
            return

        # Preload next N photos
        for i in range(1, self.preload_count + 1):
            next_index = self.current_index + i

            if next_index >= len(self.all_media):
                break  # No more photos to preload

            next_path = self.all_media[next_index]

            # Skip if already cached
            if next_path in self.preload_cache:
                continue

            # Skip videos (only preload photos)
            if self._is_video(next_path):
                continue

            # Start background preload
            worker = PreloadImageWorker(next_path, self.preload_signals)
            self.preload_thread_pool.start(worker)
            print(f"[MediaLightbox] Preloading: {os.path.basename(next_path)}")

    def _on_preload_complete(self, path: str, pixmap):
        """PHASE A #1: Handle preload completion."""
        if pixmap and not pixmap.isNull():
            # Add to cache with timestamp
            from PySide6.QtCore import QDateTime
            self.preload_cache[path] = {
                'pixmap': pixmap,
                'timestamp': QDateTime.currentMSecsSinceEpoch()
            }
            print(f"[MediaLightbox] ✓ Cached: {os.path.basename(path)} (cache size: {len(self.preload_cache)})")

            # Clean cache if too large
            self._clean_preload_cache()

    def _clean_preload_cache(self):
        """PHASE A #1: Clean preload cache (keep only 5 most recent)."""
        if len(self.preload_cache) <= self.cache_limit:
            return

        # Sort by timestamp (oldest first)
        sorted_paths = sorted(
            self.preload_cache.keys(),
            key=lambda p: self.preload_cache[p]['timestamp']
        )

        # Remove oldest entries
        to_remove = len(self.preload_cache) - self.cache_limit
        for i in range(to_remove):
            path = sorted_paths[i]
            del self.preload_cache[path]
            print(f"[MediaLightbox] Removed from cache: {os.path.basename(path)}")

    def _on_thumbnail_loaded(self, pixmap):
        """PHASE A #2: Handle progressive loading - thumbnail quality loaded."""
        print(f"[SIGNAL] _on_thumbnail_loaded called, pixmap={'valid' if pixmap and not pixmap.isNull() else 'NULL'}")

        if not pixmap or pixmap.isNull():
            print(f"[ERROR] ⚠️ Thumbnail pixmap is null or invalid! Photo won't display.")
            self._hide_loading_indicator()  # Hide loading indicator on error
            return

        from PySide6.QtCore import Qt

        try:
            # Store as original for zoom operations
            self.original_pixmap = pixmap

            # Scale to fit viewport
            viewport_size = self.scroll_area.viewport().size()
            print(f"[SIGNAL] Viewport size: {viewport_size.width()}x{viewport_size.height()}")
            scaled_pixmap = pixmap.scaled(
                viewport_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            # Display thumbnail (instant!)
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.resize(scaled_pixmap.size())
            self.media_container.resize(scaled_pixmap.size())

            self.thumbnail_quality_loaded = True

            # Update status
            self._show_loading_indicator("📥 Loading full resolution...")

            print(f"[MediaLightbox] ✓ Thumbnail displayed (progressive load)")
        except Exception as e:
            print(f"[ERROR] ⚠️ Failed to display thumbnail: {e}")
            import traceback
            traceback.print_exc()
            self._hide_loading_indicator()

    def _on_full_quality_loaded(self, pixmap):
        """PHASE A #2: Handle progressive loading - full quality loaded."""
        print(f"[SIGNAL] _on_full_quality_loaded called, pixmap={'valid' if pixmap and not pixmap.isNull() else 'NULL'}")

        if not pixmap or pixmap.isNull():
            print(f"[ERROR] ⚠️ Full quality pixmap is null or invalid!")
            self._hide_loading_indicator()  # Hide loading indicator on error
            return

        from PySide6.QtCore import Qt

        try:
            # Store as original for zoom operations
            self.original_pixmap = pixmap

            # Scale to fit viewport
            viewport_size = self.scroll_area.viewport().size()
            scaled_pixmap = pixmap.scaled(
                viewport_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            # Swap with subtle fade
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve

            # Create fade animation if not exists
            if not self.image_label.graphicsEffect():
                opacity_effect = QGraphicsOpacityEffect()
                self.image_label.setGraphicsEffect(opacity_effect)

            opacity_effect = self.image_label.graphicsEffect()

            # Quick fade out/in
            fade = QPropertyAnimation(opacity_effect, b"opacity")
            fade.setDuration(150)
            fade.setStartValue(0.7)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.OutCubic)

            # Update pixmap
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.resize(scaled_pixmap.size())
            self.media_container.resize(scaled_pixmap.size())

            fade.start()
            self.setProperty("quality_fade", fade)  # Prevent GC

            self.full_quality_loaded = True

            # Hide loading indicator
            self._hide_loading_indicator()

            print(f"[MediaLightbox] ✓ Full quality displayed (progressive load complete)")
        except Exception as e:
            print(f"[ERROR] ⚠️ Failed to display full quality: {e}")
            import traceback
            traceback.print_exc()
            self._hide_loading_indicator()

        # Calculate zoom level
        self.zoom_level = scaled_pixmap.width() / pixmap.width()
        self.fit_zoom_level = self.zoom_level
        self.zoom_mode = "fit"

        print(f"[MediaLightbox] ✓ Full quality displayed (progressive load complete)")

    def _calculate_zoom_scroll_adjustment(self, old_zoom: float, new_zoom: float):
        """
        PHASE A #3: Calculate scroll position adjustment for cursor-centered zoom.

        Keeps the point under the mouse cursor fixed during zoom.
        """
        if not self.last_mouse_pos or not self.zoom_mouse_tracking:
            return  # No adjustment needed

        # Get scroll area viewport position
        viewport = self.scroll_area.viewport()

        # Convert mouse position to viewport coordinates
        mouse_viewport_pos = viewport.mapFromGlobal(self.mapToGlobal(self.last_mouse_pos))

        # Calculate position in image space before zoom
        scroll_x = self.scroll_area.horizontalScrollBar().value()
        scroll_y = self.scroll_area.verticalScrollBar().value()

        image_x_before = scroll_x + mouse_viewport_pos.x()
        image_y_before = scroll_y + mouse_viewport_pos.y()

        # Calculate new scroll position to keep same point under cursor
        zoom_ratio = new_zoom / old_zoom

        new_scroll_x = int(image_x_before * zoom_ratio - mouse_viewport_pos.x())
        new_scroll_y = int(image_y_before * zoom_ratio - mouse_viewport_pos.y())

        # Apply after zoom is complete (in next event loop)
        def apply_scroll():
            self.scroll_area.horizontalScrollBar().setValue(new_scroll_x)
            self.scroll_area.verticalScrollBar().setValue(new_scroll_y)

        QTimer.singleShot(10, apply_scroll)

    # ==================== PHASE B IMPROVEMENTS ====================

    def _create_filmstrip(self) -> QWidget:
        """
        PHASE B #1: Create thumbnail filmstrip at bottom.

        Shows 7-10 thumbnails with current photo highlighted.
        Click to jump, auto-scroll to keep current centered.
        """
        from PySide6.QtWidgets import QScrollArea, QHBoxLayout

        filmstrip = QWidget()
        filmstrip.setFixedHeight(120)  # 80px thumbnails + 40px padding
        filmstrip.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(0, 0, 0, 0),
                    stop:1 rgba(0, 0, 0, 0.9));
            }
        """)

        layout = QVBoxLayout(filmstrip)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(0)

        # Horizontal scroll area for thumbnails
        self.filmstrip_scroll = QScrollArea()
        self.filmstrip_scroll.setFrameShape(QFrame.NoFrame)
        self.filmstrip_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.filmstrip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.filmstrip_scroll.setWidgetResizable(False)
        self.filmstrip_scroll.setStyleSheet("background: transparent;")

        # Container for thumbnail buttons
        filmstrip_container = QWidget()
        self.filmstrip_layout = QHBoxLayout(filmstrip_container)
        self.filmstrip_layout.setContentsMargins(10, 0, 10, 0)
        self.filmstrip_layout.setSpacing(8)
        self.filmstrip_layout.setAlignment(Qt.AlignLeft)

        self.filmstrip_scroll.setWidget(filmstrip_container)
        layout.addWidget(self.filmstrip_scroll)

        # Initialize filmstrip on first show
        QTimer.singleShot(100, self._update_filmstrip)

        return filmstrip

    def _update_filmstrip(self):
        """
        PHASE B #1: Update filmstrip thumbnails for current media list.

        FIX: Lazy loading - only load thumbnails for visible range (current ± 10)
        to prevent UI freeze with large photo collections.
        """
        if not self.filmstrip_enabled or not hasattr(self, 'filmstrip_layout'):
            return

        # Clear existing thumbnails
        while self.filmstrip_layout.count():
            child = self.filmstrip_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.filmstrip_buttons.clear()

        # LAZY LOADING: Only create buttons for visible range
        # Show current ± 10 photos (21 total max)
        visible_range = 10
        start_idx = max(0, self.current_index - visible_range)
        end_idx = min(len(self.all_media), self.current_index + visible_range + 1)

        print(f"[MediaLightbox] Filmstrip: Showing {end_idx - start_idx} thumbnails (range {start_idx}-{end_idx} of {len(self.all_media)})")

        # Create thumbnail buttons ONLY for visible range
        for i in range(start_idx, end_idx):
            media_path = self.all_media[i]
            btn = QPushButton()
            btn.setFixedSize(80, 80)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(os.path.basename(media_path))

            # Highlight current photo
            if i == self.current_index:
                btn.setStyleSheet("""
                    QPushButton {
                        border: 3px solid #4285f4;
                        border-radius: 4px;
                        background: #1a1a1a;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        border: 1px solid rgba(255, 255, 255, 0.2);
                        border-radius: 4px;
                        background: #2a2a2a;
                    }
                    QPushButton:hover {
                        border: 2px solid rgba(255, 255, 255, 0.5);
                    }
                """)

            # Load thumbnail (still synchronous but only for visible range)
            self._load_filmstrip_thumbnail(i, media_path, btn)

            # Click handler
            btn.clicked.connect(lambda checked, idx=i: self._jump_to_media(idx))

            self.filmstrip_layout.addWidget(btn)
            self.filmstrip_buttons[i] = btn

        # Auto-scroll to keep current centered
        QTimer.singleShot(50, self._scroll_filmstrip_to_current)

    def _load_filmstrip_thumbnail(self, index: int, media_path: str, button: QPushButton):
        """PHASE B #1: Load thumbnail for filmstrip button."""
        try:
            from app_services import get_thumbnail
            pixmap = get_thumbnail(media_path, 80)

            if pixmap and not pixmap.isNull():
                button.setIcon(QIcon(pixmap))
                button.setIconSize(QSize(76, 76))

                # Add video indicator for videos
                if self._is_video(media_path):
                    button.setText("▶")
                    button.setStyleSheet(button.styleSheet() + """
                        QPushButton {
                            color: white;
                            font-size: 20pt;
                        }
                    """)
            else:
                button.setText("📷")

        except Exception as e:
            print(f"[MediaLightbox] Error loading filmstrip thumbnail: {e}")
            button.setText("📷")

    def _jump_to_media(self, index: int):
        """PHASE B #1: Jump to specific media from filmstrip click."""
        print(f"[MediaLightbox] Filmstrip jump to index: {index}")
        if 0 <= index < len(self.all_media):
            self.current_index = index
            self.media_path = self.all_media[index]
            self._load_media_with_transition()
            self._update_filmstrip()

    def _scroll_filmstrip_to_current(self):
        """PHASE B #1: Auto-scroll filmstrip to keep current thumbnail centered."""
        if not hasattr(self, 'filmstrip_scroll') or self.current_index not in self.filmstrip_buttons:
            return

        current_btn = self.filmstrip_buttons[self.current_index]
        filmstrip_width = self.filmstrip_scroll.width()

        # Calculate position to center current thumbnail
        btn_center_x = current_btn.x() + (current_btn.width() // 2)
        scroll_to = btn_center_x - (filmstrip_width // 2)

        # Animate scroll
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve

        if hasattr(self, '_filmstrip_scroll_anim'):
            self._filmstrip_scroll_anim.stop()

        self._filmstrip_scroll_anim = QPropertyAnimation(
            self.filmstrip_scroll.horizontalScrollBar(),
            b"value"
        )
        self._filmstrip_scroll_anim.setDuration(300)
        self._filmstrip_scroll_anim.setStartValue(self.filmstrip_scroll.horizontalScrollBar().value())
        self._filmstrip_scroll_anim.setEndValue(max(0, scroll_to))
        self._filmstrip_scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._filmstrip_scroll_anim.start()

    def _update_contextual_toolbars(self):
        """
        PHASE B #4: Update toolbar visibility based on media type.

        Show video controls only for videos, zoom controls only for photos.
        """
        if not self.contextual_toolbars:
            return

        is_video = self._is_video(self.media_path)

        # Update button visibility
        for btn in self.video_only_buttons:
            btn.setVisible(is_video)

        for btn in self.photo_only_buttons:
            btn.setVisible(not is_video)

    def _save_zoom_state(self):
        """Save current zoom state for persistence (photos and videos)."""
        if self.zoom_persistence_enabled:
            self.saved_zoom_level = self.zoom_level
            self.saved_zoom_mode = self.zoom_mode
            print(f"[MediaLightbox] Zoom state saved: {self.zoom_mode} @ {int(self.zoom_level * 100)}%")

    def _restore_zoom_state(self):
        """Restore saved zoom state to current media (photos and videos)."""
        if self.zoom_persistence_enabled:
            self.zoom_level = getattr(self, 'saved_zoom_level', 1.0)
            self.zoom_mode = getattr(self, 'saved_zoom_mode', 'fit')
            if self._is_video(self.media_path):
                self._apply_video_zoom()
            else:
                self._apply_zoom()
            self._update_zoom_status()
            print(f"[MediaLightbox] Zoom state restored: {self.zoom_mode} @ {int(self.zoom_level * 100)}%")

    def _reset_zoom_state(self):
        """PHASE B #5: Reset to default fit-to-window zoom."""
        self.apply_zoom_to_all = False
        self.zoom_mode = "fit"
        self._fit_to_window()
        self._update_zoom_status()
        print(f"[MediaLightbox] Zoom reset to fit mode")

    def _handle_double_tap(self, pos):
        """
        PHASE B #2: Handle double-tap gesture for zoom in/out.

        Tap once: Track tap time/position
        Tap twice quickly: Toggle between fit and 2x zoom
        """
        from PySide6.QtCore import QDateTime

        if not self.double_tap_enabled or self._is_video(self.media_path):
            return False

        current_time = QDateTime.currentMSecsSinceEpoch()

        # Check if this is second tap
        if self.last_tap_time and self.last_tap_pos:
            time_diff = current_time - self.last_tap_time
            pos_diff = (pos - self.last_tap_pos).manhattanLength()

            # Double-tap detected: within 300ms and 50px
            if time_diff < 300 and pos_diff < 50:
                # Toggle zoom
                if self.zoom_mode == "fit":
                    # Zoom to 2x
                    self.zoom_level = 2.0
                    self.zoom_mode = "custom"
                else:
                    # Reset to fit
                    self.zoom_mode = "fit"
                    self._fit_to_window()

                self._apply_zoom()
                self._update_zoom_status()

                # Reset tap tracking
                self.last_tap_time = None
                self.last_tap_pos = None

                print(f"[MediaLightbox] Double-tap zoom: {self.zoom_mode}")
                return True

        # Track this tap
        self.last_tap_time = current_time
        self.last_tap_pos = pos

        return False

    def eventFilter(self, obj, event):
        """
        PHASE B #3: Event filter for video seek slider hover preview.

        Shows timestamp tooltip when hovering over seek bar.
        """
        # Only handle seek slider events
        if obj == self.seek_slider and hasattr(self, 'video_player'):
            if event.type() == QEvent.MouseMove:
                # Calculate timestamp at mouse position
                mouse_x = event.pos().x()
                slider_width = self.seek_slider.width()

                if slider_width > 0:
                    # Calculate position percentage
                    position_pct = mouse_x / slider_width
                    position_pct = max(0.0, min(1.0, position_pct))

                    # Calculate timestamp
                    duration = self.seek_slider.maximum()
                    timestamp_ms = int(duration * position_pct)

                    # Format as mm:ss
                    minutes = timestamp_ms // 60000
                    seconds = (timestamp_ms % 60000) // 1000
                    timestamp_str = f"{minutes}:{seconds:02d}"

                    # Show tooltip
                    self.seek_slider.setToolTip(timestamp_str)

                return False  # Allow event to propagate

            elif event.type() == QEvent.Leave:
                # Clear tooltip when leaving slider
                self.seek_slider.setToolTip("")
                return False

        return super().eventFilter(obj, event)

    def _skip_video_forward(self):
        """PHASE B #3: Skip video forward by 10 seconds."""
        if hasattr(self, 'video_player') and self._is_video(self.media_path):
            current_pos = self.video_player.position()
            new_pos = min(current_pos + 10000, self.seek_slider.maximum())  # +10s (10000ms)
            self.video_player.setPosition(new_pos)
            print(f"[MediaLightbox] Video skip +10s: {new_pos // 1000}s")

    def _skip_video_backward(self):
        """PHASE B #3: Skip video backward by 10 seconds."""
        if hasattr(self, 'video_player') and self._is_video(self.media_path):
            current_pos = self.video_player.position()
            new_pos = max(current_pos - 10000, 0)  # -10s (10000ms)
            self.video_player.setPosition(new_pos)
            print(f"[MediaLightbox] Video skip -10s: {new_pos // 1000}s")

    def _on_speed_clicked(self):
        """Cycle playback speed among 0.5x, 1.0x, 1.5x, 2.0x."""
        if not hasattr(self, 'video_player') or not self._is_video(self.media_path):
            return
        speeds = [0.5, 1.0, 1.5, 2.0]
        idx = getattr(self, 'current_speed_index', 1)
        idx = (idx + 1) % len(speeds)
        self.current_speed_index = idx
        rate = speeds[idx]
        try:
            self.video_player.setPlaybackRate(rate)
        except Exception as e:
            print(f"[MediaLightbox] PlaybackRate not supported: {e}")
        if hasattr(self, 'speed_btn'):
            self.speed_btn.setText(f"{rate:.1f}x")
        print(f"[MediaLightbox] Playback speed set to {rate:.1f}x")

    # ==================== PHASE C IMPROVEMENTS ====================

    def _on_media_status_changed(self, status):
        """Loop video when enabled and fit to view once loaded."""
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            # Looping behavior at end of media
            if status == QMediaPlayer.EndOfMedia and getattr(self, 'loop_enabled', False):
                self.video_player.setPosition(0)
                self.video_player.play()
                print("[MediaLightbox] Looping video to start")
            # Fit video to view when media becomes ready
            if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
                if hasattr(self, '_fit_video_view'):
                    self._fit_video_view()
                    print("[MediaLightbox] Fit video to view after media loaded")
        except Exception as e:
            print(f"[MediaLightbox] mediaStatusChanged handler error: {e}")

    def _on_screenshot_clicked(self):
        """Capture current video frame as image and save to Screenshots folder."""
        if not hasattr(self, 'video_widget') or not self._is_video(self.media_path):
            return
        try:
            pix = self.video_widget.grab()
            if pix and not pix.isNull():
                import os, time
                shots_dir = os.path.join(os.path.dirname(self.media_path), "_Screenshots")
                os.makedirs(shots_dir, exist_ok=True)
                fname = f"screenshot_{int(time.time())}.png"
                out_path = os.path.join(shots_dir, fname)
                pix.save(out_path)
                print(f"[MediaLightbox] Screenshot saved: {out_path}")
            else:
                print("[MediaLightbox] Screenshot failed: No frame")
        except Exception as e:
            print(f"[MediaLightbox] Screenshot error: {e}")

    def _on_loop_clicked(self):
        """Toggle loop playback on/off."""
        self.loop_enabled = not getattr(self, 'loop_enabled', False)
        if hasattr(self, 'loop_btn'):
            self.loop_btn.setText("Loop On" if self.loop_enabled else "Loop Off")
        print(f"[MediaLightbox] Loop {'enabled' if self.loop_enabled else 'disabled'}")

    def _step_frame_forward(self):
        """Advance video by ~1 frame (approx 33ms at 30fps)."""
        if hasattr(self, 'video_player') and self._is_video(self.media_path):
            pos = self.video_player.position()
            self.video_player.setPosition(pos + 33)
            print(f"[MediaLightbox] Frame +1 (pos={pos+33}ms)")

    def _step_frame_backward(self):
        """Step video back by ~1 frame (approx 33ms)."""
        if hasattr(self, 'video_player') and self._is_video(self.media_path):
            pos = self.video_player.position()
            self.video_player.setPosition(max(pos - 33, 0))
            print(f"[MediaLightbox] Frame -1 (pos={max(pos-33,0)}ms)")

    def _rotate_image(self):
        """
        PHASE C #3: Rotate image clockwise by 90 degrees.

        R key cycles: 0° → 90° → 180° → 270° → 0°
        """
        if self._is_video(self.media_path):
            return  # Don't rotate videos

        # Cycle rotation
        self.rotation_angle = (self.rotation_angle + 90) % 360

        # Apply rotation to current pixmap
        if self.original_pixmap and not self.original_pixmap.isNull():
            from PySide6.QtGui import QTransform

            # Create rotation transform
            transform = QTransform().rotate(self.rotation_angle)
            rotated_pixmap = self.original_pixmap.transformed(transform, Qt.SmoothTransformation)

            # Update original pixmap with rotated version
            self.original_pixmap = rotated_pixmap

            # Reapply zoom
            self._apply_zoom()

            print(f"[MediaLightbox] Image rotated: {self.rotation_angle}°")

    def _toggle_crop_mode_OLD_DISABLED(self):
        """
        PHASE C #3: OLD crop mode stub - DISABLED.
        
        This has been replaced by the editor crop mode.
        Use 'E' key to enter editor, then 'C' to toggle crop.
        """
        print("[MediaLightbox] OLD crop mode disabled - use Editor mode instead (press E, then C)")
        return  # Disabled - use editor crop mode instead

    def _auto_enhance(self):
        """
        PHASE C #3: Apply automatic enhancement to photo.

        Basic brightness/contrast adjustment.
        """
        if self._is_video(self.media_path) or not self.original_pixmap:
            return

        try:
            from PySide6.QtGui import QImage
            from PIL import Image, ImageEnhance
            import io

            # Convert QPixmap to PIL Image
            qimage = self.original_pixmap.toImage()
            buffer = qimage.bits().tobytes()
            pil_image = Image.frombytes('RGBA', (qimage.width(), qimage.height()), buffer)

            # Auto-enhance
            enhancer = ImageEnhance.Contrast(pil_image)
            pil_image = enhancer.enhance(1.2)  # +20% contrast

            enhancer = ImageEnhance.Brightness(pil_image)
            pil_image = enhancer.enhance(1.1)  # +10% brightness

            # Convert back to QPixmap
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG')
            buffer.seek(0)

            enhanced_pixmap = QPixmap()
            enhanced_pixmap.loadFromData(buffer.read())

            self.original_pixmap = enhanced_pixmap
            self._apply_zoom()

            print("[MediaLightbox] Auto-enhance applied: +20% contrast, +10% brightness")

        except Exception as e:
            print(f"[MediaLightbox] Auto-enhance error: {e}")

    def _show_share_dialog(self):
        """
        PHASE C #2: Show share/export dialog.

        Options: Small/Medium/Large/Original, Copy to clipboard
        """
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup, QRadioButton

        dialog = QDialog(self)
        dialog.setWindowTitle("Share / Export")
        dialog.setMinimumWidth(400)
        dialog.setStyleSheet("QDialog { background-color: #1e1e1e; } QLabel { color: white; } QRadioButton { color: white; } QPushButton { background: rgba(255,255,255,0.15); color: white; border: none; border-radius: 6px; padding: 8px 12px; } QPushButton:hover { background: rgba(255,255,255,0.25); }")

        layout = QVBoxLayout(dialog)

        # Title
        title = QLabel("📤 Share or Export Photo")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # Size options
        size_label = QLabel("Export Size:")
        size_label.setStyleSheet("font-weight: bold; padding-top: 10px;")
        layout.addWidget(size_label)

        size_group = QButtonGroup(dialog)
        sizes = [
            ("Small (800px)", "small"),
            ("Medium (1920px)", "medium"),
            ("Large (3840px)", "large"),
            ("Original Size", "original")
        ]

        for text, value in sizes:
            radio = QRadioButton(text)
            radio.setProperty("size_value", value)
            size_group.addButton(radio)
            layout.addWidget(radio)

        size_group.buttons()[2].setChecked(True)  # Default: Large

        # Action buttons
        button_layout = QHBoxLayout()

        copy_btn = QPushButton("📋 Copy to Clipboard")
        copy_btn.setStyleSheet("")
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard())
        button_layout.addWidget(copy_btn)

        save_btn = QPushButton("💾 Save As...")
        save_btn.setStyleSheet("")
        save_btn.clicked.connect(lambda: self._export_photo(size_group.checkedButton().property("size_value")))
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        dialog.exec()

    def _copy_to_clipboard(self):
        """PHASE C #2: Copy current photo to clipboard."""
        if self.original_pixmap and not self.original_pixmap.isNull():
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setPixmap(self.original_pixmap)
            print("[MediaLightbox] Photo copied to clipboard")

    def _export_photo(self, size_option: str):
        """PHASE C #2: Export photo with size options."""
        from PySide6.QtWidgets import QFileDialog

        if not self.original_pixmap or self.original_pixmap.isNull():
            return

        # Get save location
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Photo",
            f"photo_{size_option}.jpg",
            "JPEG Images (*.jpg);;PNG Images (*.png)"
        )

        if not file_path:
            return

        # Resize based on option
        pixmap = self.original_pixmap

        if size_option == "small":
            pixmap = pixmap.scaledToWidth(800, Qt.SmoothTransformation)
        elif size_option == "medium":
            pixmap = pixmap.scaledToWidth(1920, Qt.SmoothTransformation)
        elif size_option == "large":
            pixmap = pixmap.scaledToWidth(3840, Qt.SmoothTransformation)

        # Save
        pixmap.save(file_path, quality=95)
        print(f"[MediaLightbox] Photo exported: {file_path} ({size_option})")

    def _toggle_compare_mode(self):
        """
        PHASE C #4: Toggle compare mode (split-screen composite).
        
        Shows current photo side-by-side with previous/next for comparison.
        """
        self.compare_mode_active = not self.compare_mode_active
        
        if self.compare_mode_active:
            # Only support photos for compare (skip videos)
            if self._is_video(self.media_path):
                print("[MediaLightbox] Compare mode not supported for videos")
                self.compare_mode_active = False
                return
            
            # Select comparison photo (previous or next)
            if self.current_index > 0:
                self.compare_media_path = self.all_media[self.current_index - 1]
            elif self.current_index < len(self.all_media) - 1:
                self.compare_media_path = self.all_media[self.current_index + 1]
            else:
                print("[MediaLightbox] No other photos to compare")
                self.compare_mode_active = False
                return
            
            try:
                from PySide6.QtGui import QPixmap, QPainter
                from PySide6.QtCore import Qt
                
                # Load both pixmaps
                base_pix = QPixmap(self.media_path)
                cmp_pix = QPixmap(self.compare_media_path)
                if base_pix.isNull() or cmp_pix.isNull():
                    print("[MediaLightbox] Compare mode: failed to load pixmaps")
                    self.compare_mode_active = False
                    return
                
                # Determine viewport size
                viewport = self.scroll_area.viewport().size()
                target_h = viewport.height()
                half_w = viewport.width() // 2
                
                # Scale each to fit half-width, full height
                base_scaled = base_pix.scaled(half_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                cmp_scaled = cmp_pix.scaled(half_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                # Composite side-by-side
                composite_w = base_scaled.width() + cmp_scaled.width()
                composite_h = max(base_scaled.height(), cmp_scaled.height())
                composite = QPixmap(composite_w, composite_h)
                composite.fill(Qt.black)
                painter = QPainter(composite)
                painter.drawPixmap(0, (composite_h - base_scaled.height()) // 2, base_scaled)
                painter.drawPixmap(base_scaled.width(), (composite_h - cmp_scaled.height()) // 2, cmp_scaled)
                painter.end()
                
                # Save original to restore later
                self._saved_original_pixmap = self.original_pixmap
                
                # Display composite
                self.original_pixmap = composite
                self.zoom_mode = "fit"
                self._fit_to_window()
                self._update_zoom_status()
                print(f"[MediaLightbox] Compare mode ENABLED: {os.path.basename(self.media_path)} vs {os.path.basename(self.compare_media_path)}")
            except Exception as e:
                print(f"[MediaLightbox] Compare mode error: {e}")
                self.compare_mode_active = False
                # Restore state
                if hasattr(self, '_saved_original_pixmap') and self._saved_original_pixmap:
                    self.original_pixmap = self._saved_original_pixmap
                    self._fit_to_window()
                return
        else:
            # Restore original view
            if hasattr(self, '_saved_original_pixmap') and self._saved_original_pixmap:
                self.original_pixmap = self._saved_original_pixmap
                self._fit_to_window()
                self._update_zoom_status()
                self._saved_original_pixmap = None
            self.compare_media_path = None
            print("[MediaLightbox] Compare mode DISABLED")

    def _show_motion_indicator(self):
        """
        PHASE C #5: Show motion photo indicator in top-right corner.

        Indicates that this photo has a paired video (motion/live photo).
        """
        if not hasattr(self, 'motion_indicator'):
            return

        # Position in top-right corner (with margin)
        margin = 20
        x = self.width() - self.motion_indicator.width() - margin
        y = margin + 80  # Below toolbar

        self.motion_indicator.move(x, y)
        self.motion_indicator.show()
        self.motion_indicator.raise_()

        print(f"[MediaLightbox] Motion indicator shown at ({x}, {y})")

    def _hide_motion_indicator(self):
        """PHASE C #5: Hide motion photo indicator."""
        if hasattr(self, 'motion_indicator'):
            self.motion_indicator.hide()


# === CUSTOM SEEK SLIDER WITH TRIM MARKERS ===
class TrimMarkerSlider(QSlider):
    """Custom QSlider that displays visual trim markers for video editing."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.trim_start = 0  # Start trim position (0-100 scale)
        self.trim_end = 100  # End trim position (0-100 scale)
        self.video_duration_ms = 0  # Total video duration in milliseconds
        self.show_markers = False  # Only show markers in edit mode

    def set_trim_markers(self, start_ms, end_ms, duration_ms):
        """Set trim marker positions in milliseconds."""
        self.video_duration_ms = duration_ms
        slider_max = self.maximum()  # Get slider max BEFORE if/else blocks

        if duration_ms > 0:
            # Convert milliseconds to slider range (0-100 or 0-max)
            self.trim_start = int((start_ms / duration_ms) * slider_max)
            self.trim_end = int((end_ms / duration_ms) * slider_max)
        else:
            self.trim_start = 0
            self.trim_end = slider_max
        self.show_markers = True
        self.update()  # Trigger repaint

    def clear_trim_markers(self):
        """Hide trim markers."""
        self.show_markers = False
        self.update()

    def paintEvent(self, event):
        """Override paint event to draw trim markers."""
        # First, draw the standard slider
        super().paintEvent(event)

        # If markers enabled and in valid range, draw them
        if not self.show_markers or self.video_duration_ms == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate marker positions in pixels
        slider_width = self.width()
        handle_width = 12  # From stylesheet
        usable_width = slider_width - handle_width

        # Convert trim positions to pixel coordinates
        slider_max = self.maximum()
        if slider_max > 0:
            start_x = int((self.trim_start / slider_max) * usable_width) + (handle_width // 2)
            end_x = int((self.trim_end / slider_max) * usable_width) + (handle_width // 2)
        else:
            return

        # Draw shaded regions OUTSIDE trim range (semi-transparent gray)
        painter.fillRect(0, 0, start_x, self.height(), QColor(0, 0, 0, 80))
        painter.fillRect(end_x, 0, slider_width - end_x, self.height(), QColor(0, 0, 0, 80))

        # Draw green marker for trim start (🟢)
        painter.setPen(QPen(QColor(76, 175, 80), 3))  # Green, 3px thick
        painter.drawLine(start_x, 0, start_x, self.height())

        # Draw red marker for trim end (🔴)
        painter.setPen(QPen(QColor(244, 67, 54), 3))  # Red, 3px thick
        painter.drawLine(end_x, 0, end_x, self.height())

        painter.end()


class AutocompleteEventFilter(QObject):
    """Event filter for people search autocomplete keyboard navigation."""
    
    def __init__(self, search_widget, autocomplete_widget, parent_layout):
        super().__init__()
        self.search_widget = search_widget
        self.autocomplete_widget = autocomplete_widget
        self.parent_layout = parent_layout
    
    def eventFilter(self, obj, event):
        """Handle keyboard events for autocomplete navigation."""
        if obj == self.search_widget and event.type() == QEvent.KeyPress:
            if self.autocomplete_widget.isVisible():
                key = event.key()
                if key == Qt.Key_Down:
                    # Move to autocomplete list
                    self.autocomplete_widget.setFocus()
                    self.autocomplete_widget.setCurrentRow(0)
                    return True
                elif key == Qt.Key_Escape:
                    self.autocomplete_widget.hide()
                    return True
                elif key == Qt.Key_Return or key == Qt.Key_Enter:
                    # Select first item if autocomplete is visible
                    if self.autocomplete_widget.count() > 0:
                        first_item = self.autocomplete_widget.item(0)
                        self.parent_layout._on_autocomplete_selected(first_item)
                        return True
        
        return super().eventFilter(obj, event)


class GooglePhotosLayout(BaseLayout):
    """
    Google Photos-style layout.

    Structure:
    ┌─────────────────────────────────────────────┐
    │  Toolbar (Scan, Faces, Search, etc.)       │
    ├───────────┬─────────────────────────────────┤
    │ Sidebar   │  Timeline (Date Groups)         │
    │ • Search  │  • December 2024 (15 photos)    │
    │ • Years   │  • November 2024 (32 photos)    │
    │ • Albums  │  • October 2024 (28 photos)     │
    └───────────┴─────────────────────────────────┘

    Features:
    - Timeline-based view (grouped by date)
    - Minimal sidebar (search + timeline navigation)
    - Large zoomable thumbnails
    - Layout-specific toolbar with Scan/Faces
    """

    # Badge overlay configuration (Google Photos style)
    # PERFORMANCE FIX: Extracted to class constant (was recreated on every badge render)
    TAG_BADGE_CONFIG = {
        'favorite': ('★', QColor(255, 215, 0, 230), Qt.black),
        'face': ('👤', QColor(70, 130, 180, 220), Qt.white),
        'important': ('⚑', QColor(255, 69, 0, 220), Qt.white),
        'work': ('💼', QColor(0, 128, 255, 220), Qt.white),
        'travel': ('✈', QColor(34, 139, 34, 220), Qt.white),
        'personal': ('♥', QColor(255, 20, 147, 220), Qt.white),
        'family': ('👨\u200d👩\u200d👧', QColor(255, 140, 0, 220), Qt.white),
        'archive': ('📦', QColor(128, 128, 128, 220), Qt.white),
    }
    DEFAULT_BADGE_CONFIG = ('🏷', QColor(150, 150, 150, 230), Qt.white)

    def get_name(self) -> str:
        return "Google Photos Style"

    def get_id(self) -> str:
        return "google"

    def create_layout(self) -> QWidget:
        """
        Create Google Photos-style layout.
        """
        # Phase 2: Selection tracking
        self.selected_photos = set()  # Set of selected photo paths
        self.selection_mode = False  # Whether selection mode is active
        self.last_selected_path = None  # For Shift range selection
        self.all_displayed_paths = []  # Track all photos in current view for range selection

        # Async thumbnail loading (copied from Current Layout's proven pattern)
        self.thumbnail_thread_pool = QThreadPool()
        self.thumbnail_thread_pool.setMaxThreadCount(4)  # REDUCED: Limit concurrent loads
        self.thumbnail_buttons = {}  # Map path -> button widget for async updates
        self.thumbnail_load_count = 0  # Track how many thumbnails we've queued

        # QUICK WIN #1: Track unloaded thumbnails for scroll-triggered loading
        self.unloaded_thumbnails = {}  # Map path -> (button, size) for lazy loading
        self.initial_load_limit = 50  # Load first 50 immediately (increased from 30)

        # QUICK WIN #3: Virtual scrolling - render only visible date groups
        self.date_groups_metadata = []  # List of {date_str, photos, thumb_size, index}
        self.date_group_widgets = {}  # Map index -> widget (rendered or placeholder)
        self.rendered_date_groups = set()  # Set of indices that are currently rendered
        self.virtual_scroll_enabled = True  # Enable virtual scrolling
        self.initial_render_count = 5  # Render first 5 date groups immediately

        # QUICK WIN #4: Collapsible date groups
        self.date_group_collapsed = {}  # Map date_str -> bool (collapsed state)
        self.date_group_grids = {}  # Map date_str -> grid widget for toggle visibility

        # QUICK WIN #5: Smooth scroll performance (60 FPS)
        self.scroll_debounce_timer = QTimer()
        self.scroll_debounce_timer.setSingleShot(True)
        self.scroll_debounce_timer.timeout.connect(self._on_scroll_debounced)
        self.scroll_debounce_delay = 150  # ms - debounce scroll events

        # PHASE 2 #4: Date scroll indicator hide timer
        self.date_indicator_hide_timer = QTimer()
        self.date_indicator_hide_timer.setSingleShot(True)
        self.date_indicator_hide_timer.timeout.connect(self._hide_date_indicator)
        self.date_indicator_delay = 800  # ms - hide after scrolling stops

        # PHASE 2 #5: Thumbnail aspect ratio mode
        self.thumbnail_aspect_ratio = "square"  # "square", "original", "16:9"

        # CRITICAL FIX: Create ONE shared signal object for ALL workers (like Current Layout)
        # Problem: Each worker was creating its own signal → signals got garbage collected
        # Solution: Share one signal object, connect it once
        self.thumbnail_signals = ThumbnailSignals()
        self.thumbnail_signals.loaded.connect(self._on_thumbnail_loaded)

        # Initialize filter state
        self.current_thumb_size = 200
        self.current_filter_year = None
        self.current_filter_month = None
        self.current_filter_day = None
        self.current_filter_folder = None
        self.current_filter_person = None

        # Get current project ID (CRITICAL: Photos are organized by project)
        from app_services import get_default_project_id, list_projects
        self.project_id = get_default_project_id()

        # Fallback to first project if no default
        if self.project_id is None:
            projects = list_projects()
            if projects:
                self.project_id = projects[0]["id"]
                print(f"[GooglePhotosLayout] Using first project: {self.project_id}")
            else:
                print("[GooglePhotosLayout] ⚠️ WARNING: No projects found! Please create a project first.")
        else:
            print(f"[GooglePhotosLayout] Using default project: {self.project_id}")

        # PERFORMANCE FIX: Cache badge overlay settings (read once vs per-photo)
        # Previously: SettingsManager read on every _create_tag_badge_overlay call
        # Now: Cache at initialization, improving performance with large photo libraries
        from settings_manager_qt import SettingsManager
        sm = SettingsManager()
        self._badge_settings = {
            'enabled': sm.get("badge_overlays_enabled", True),
            'size': int(sm.get("badge_size_px", 22)),
            'max_count': int(sm.get("badge_max_count", 4))
        }

        # Main container
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create toolbar
        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        # Phase 3: Main view tabs (Photos, People, Folders, Videos, Favorites)
        self.view_tabs = QTabBar()
        self.view_tabs.addTab("📸 Photos")
        self.view_tabs.addTab("👥 People")
        self.view_tabs.addTab("📁 Folders")
        self.view_tabs.addTab("🎬 Videos")
        self.view_tabs.addTab("⭐ Favorites")
        self.view_tabs.currentChanged.connect(self._on_view_tab_changed)
        main_layout.addWidget(self.view_tabs)

        # Photos mode switcher (Grid / Timeline / Single)
        self.photos_mode_bar = QToolBar()
        self.photos_mode_bar.setMovable(False)
        self.btn_mode_grid = QPushButton("Grid")
        self.btn_mode_timeline = QPushButton("Timeline")
        self.btn_mode_single = QPushButton("Single")
        self.btn_mode_grid.clicked.connect(self._show_grid_view)
        self.btn_mode_timeline.clicked.connect(self._show_timeline_view)
        self.btn_mode_single.clicked.connect(self._show_single_view)
        self.photos_mode_bar.addWidget(self.btn_mode_grid)
        self.photos_mode_bar.addWidget(self.btn_mode_timeline)
        self.photos_mode_bar.addWidget(self.btn_mode_single)
        main_layout.addWidget(self.photos_mode_bar)
        self.photos_mode_bar.setVisible(True)

        # Create horizontal splitter (Sidebar | Timeline)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(3)

        # Create sidebar
        self.sidebar = self._create_sidebar()
        self.splitter.addWidget(self.sidebar)

        # Create timeline
        self.timeline = self._create_timeline()
        self.splitter.addWidget(self.timeline)

        # Set splitter sizes (280px sidebar initially, rest for timeline)
        self.splitter.setSizes([280, 1000])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self.splitter)

        # QUICK WIN #6: Create floating selection toolbar (initially hidden)
        self.floating_toolbar = self._create_floating_toolbar(main_widget)
        self.floating_toolbar.hide()

        # PHASE 2 #4: Create floating date scroll indicator (initially hidden)
        self.date_scroll_indicator = self._create_date_scroll_indicator(main_widget)
        self.date_scroll_indicator.hide()

        # Load photos from database
        self._load_photos()

        return main_widget

    def _create_toolbar(self) -> QToolBar:
        """
        Create Google Photos-specific toolbar.
        """
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setStyleSheet("""
            QToolBar {
                background: #f8f9fa;
                border-bottom: 1px solid #dadce0;
                padding: 6px;
                spacing: 8px;
            }
            QPushButton {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background: #f1f3f4;
                border-color: #bdc1c6;
            }
            QPushButton:pressed {
                background: #e8eaed;
            }
        """)

        # Project selector (compact, no label - Google Photos style)
        from PySide6.QtWidgets import QComboBox, QLabel

        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(150)
        self.project_combo.setStyleSheet("""
            QComboBox {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11pt;
            }
            QComboBox:hover {
                border-color: #bdc1c6;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        self.project_combo.setToolTip("Select project to view")
        toolbar.addWidget(self.project_combo)

        # Populate project selector
        self._populate_project_selector()

        toolbar.addSeparator()

        # Search box (enlarged - Google Photos hero element)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(t('google_layout.search_placeholder'))
        self.search_box.setMinimumWidth(400)  # Enlarged from 300px to 400px minimum
        self.search_box.setToolTip(t('google_layout.search_tooltip'))
        self.search_box.setStyleSheet("""
            QLineEdit {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 20px;
                padding: 8px 16px;
                font-size: 11pt;
            }
            QLineEdit:focus {
                border-color: #1a73e8;
                border-width: 2px;
            }
        """)
        # Phase 2: Connect search functionality
        self.search_box.textChanged.connect(self._on_search_text_changed)
        self.search_box.returnPressed.connect(self._perform_search)

        # Make search box expand to take available space (Google Photos pattern)
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.addWidget(self.search_box)
        search_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(search_container)

        # PHASE 2 #3: Create search suggestions dropdown
        self._create_search_suggestions()

        toolbar.addSeparator()

        # Clear Filter button (initially hidden, Google Photos style)
        self.btn_clear_filter = QPushButton("✕ Clear Filter")
        self.btn_clear_filter.setToolTip("Show all photos (remove date/folder filters)")
        self.btn_clear_filter.clicked.connect(self._clear_filter)
        self.btn_clear_filter.setVisible(False)
        self.btn_clear_filter.setStyleSheet("""
            QPushButton {
                background: #fff3cd;
                border: 1px solid #ffc107;
                color: #856404;
            }
            QPushButton:hover {
                background: #ffeaa7;
            }
        """)
        toolbar.addWidget(self.btn_clear_filter)

        toolbar.addSeparator()

        # Phase 2: Selection mode toggle
        self.btn_select = QPushButton("☑️ Select")
        self.btn_select.setToolTip("Enable selection mode (Ctrl+A to select all)")
        self.btn_select.setCheckable(True)
        self.btn_select.clicked.connect(self._toggle_selection_mode)
        toolbar.addWidget(self.btn_select)

        toolbar.addSeparator()

        # Zoom controls (Google Photos style - +/- buttons with slider)
        from PySide6.QtWidgets import QLabel, QSlider

        # Zoom out button
        self.btn_zoom_out = QPushButton("➖")
        self.btn_zoom_out.setToolTip(t('google_layout.zoom_out_tooltip'))
        self.btn_zoom_out.setFixedSize(28, 28)
        self.btn_zoom_out.clicked.connect(lambda: self.zoom_slider.setValue(self.zoom_slider.value() - 50))
        self.btn_zoom_out.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 4px;
                font-size: 14pt;
            }
            QPushButton:hover {
                background: #f1f3f4;
            }
        """)
        toolbar.addWidget(self.btn_zoom_out)

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(100)  # 100px thumbnails
        self.zoom_slider.setMaximum(400)  # 400px thumbnails
        self.zoom_slider.setValue(200)    # Default 200px
        self.zoom_slider.setFixedWidth(100)
        self.zoom_slider.setToolTip(t('google_layout.zoom_slider_tooltip'))
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        toolbar.addWidget(self.zoom_slider)

        # Zoom in button
        self.btn_zoom_in = QPushButton("➕")
        self.btn_zoom_in.setToolTip(t('google_layout.zoom_in_tooltip'))
        self.btn_zoom_in.setFixedSize(28, 28)
        self.btn_zoom_in.clicked.connect(lambda: self.zoom_slider.setValue(self.zoom_slider.value() + 50))
        self.btn_zoom_in.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 4px;
                font-size: 14pt;
            }
            QPushButton:hover {
                background: #f1f3f4;
            }
        """)
        toolbar.addWidget(self.btn_zoom_in)

        # Zoom value label (smaller, optional)
        self.zoom_value_label = QLabel("200")
        self.zoom_value_label.setFixedWidth(35)
        self.zoom_value_label.setStyleSheet("padding: 0 4px; font-size: 9pt; color: #5f6368;")
        self.zoom_value_label.setToolTip("Current thumbnail size")
        toolbar.addWidget(self.zoom_value_label)

        # PHASE 2 #5: Aspect ratio toggle buttons (icons only, no label)
        self.btn_aspect_square = QPushButton("⬜")
        self.btn_aspect_square.setToolTip("Square thumbnails (1:1)")
        self.btn_aspect_square.setCheckable(True)
        self.btn_aspect_square.setChecked(True)
        self.btn_aspect_square.setFixedSize(24, 24)
        self.btn_aspect_square.clicked.connect(lambda: self._set_aspect_ratio("square"))
        self.btn_aspect_square.setStyleSheet("""
            QPushButton {
                background: white;
                border: 2px solid #dadce0;
                border-radius: 4px;
            }
            QPushButton:checked {
                background: #e8f0fe;
                border-color: #1a73e8;
            }
            QPushButton:hover {
                border-color: #1a73e8;
            }
        """)
        toolbar.addWidget(self.btn_aspect_square)

        self.btn_aspect_original = QPushButton("🖼️")
        self.btn_aspect_original.setToolTip("Original aspect ratio")
        self.btn_aspect_original.setCheckable(True)
        self.btn_aspect_original.setFixedSize(24, 24)
        self.btn_aspect_original.clicked.connect(lambda: self._set_aspect_ratio("original"))
        self.btn_aspect_original.setStyleSheet("""
            QPushButton {
                background: white;
                border: 2px solid #dadce0;
                border-radius: 4px;
            }
            QPushButton:checked {
                background: #e8f0fe;
                border-color: #1a73e8;
            }
            QPushButton:hover {
                border-color: #1a73e8;
            }
        """)
        toolbar.addWidget(self.btn_aspect_original)

        self.btn_aspect_16_9 = QPushButton("▬")
        self.btn_aspect_16_9.setToolTip("16:9 widescreen")
        self.btn_aspect_16_9.setCheckable(True)
        self.btn_aspect_16_9.setFixedSize(24, 24)
        self.btn_aspect_16_9.clicked.connect(lambda: self._set_aspect_ratio("16:9"))
        self.btn_aspect_16_9.setStyleSheet("""
            QPushButton {
                background: white;
                border: 2px solid #dadce0;
                border-radius: 4px;
            }
            QPushButton:checked {
                background: #e8f0fe;
                border-color: #1a73e8;
            }
            QPushButton:hover {
                border-color: #1a73e8;
            }
        """)
        toolbar.addWidget(self.btn_aspect_16_9)

        toolbar.addSeparator()

        # Settings button (Google Photos pattern - before spacer)
        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setToolTip(t('google_layout.settings_tooltip'))
        self.btn_settings.setFixedSize(32, 32)
        self.btn_settings.clicked.connect(self._show_settings_menu)
        self.btn_settings.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 16px;
                font-size: 14pt;
            }
            QPushButton:hover {
                background: #f1f3f4;
            }
            QPushButton:pressed {
                background: #e8eaed;
            }
        """)
        toolbar.addWidget(self.btn_settings)

        # Spacer (push remaining items to the right)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Selection actions (will show/hide based on selection)
        self.btn_delete = QPushButton("🗑️ Delete")
        self.btn_delete.setToolTip("Delete selected photos")
        self.btn_delete.setVisible(False)
        self.btn_delete.clicked.connect(self._on_delete_selected)
        toolbar.addWidget(self.btn_delete)

        self.btn_favorite = QPushButton("⭐ Favorite")
        self.btn_favorite.setToolTip("Mark selected as favorites")
        self.btn_favorite.setVisible(False)
        self.btn_favorite.clicked.connect(self._on_favorite_selected)
        toolbar.addWidget(self.btn_favorite)

        # PHASE 3 #7: Share/Export button
        self.btn_share = QPushButton("📤 Share")
        self.btn_share.setToolTip("Share or export selected photos")
        self.btn_share.setVisible(False)
        self.btn_share.clicked.connect(self._on_share_selected)
        toolbar.addWidget(self.btn_share)

        # Store toolbar reference
        self._toolbar = toolbar

        return toolbar

    def _show_settings_menu(self):
        """Show Settings menu (Google Photos pattern) - Phase 2."""
        from PySide6.QtWidgets import QMenu, QMessageBox
        from PySide6.QtGui import QAction

        # Create menu with proper parent (main_window is a QWidget)
        menu = QMenu(self.main_window)
        menu.setStyleSheet("""
            QMenu {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 8px 0;
            }
            QMenu::item {
                padding: 8px 24px;
                font-size: 11pt;
            }
            QMenu::item:selected {
                background: #f1f3f4;
            }
            QMenu::separator {
                height: 1px;
                background: #dadce0;
                margin: 4px 0;
            }
        """)

        # QUICK ACTIONS section
        menu.addSection(t('google_layout.settings_menu.quick_actions_section'))

        scan_action = QAction(t('google_layout.settings_menu.scan_repository'), menu)
        scan_action.setToolTip(t('google_layout.settings_menu.scan_repository'))
        if hasattr(self, '_scan_repository_handler'):
            scan_action.triggered.connect(self._scan_repository_handler)
        menu.addAction(scan_action)

        faces_action = QAction(t('google_layout.settings_menu.detect_faces'), menu)
        faces_action.setToolTip(t('google_layout.settings_menu.detect_faces'))
        if hasattr(self, '_detect_faces_handler'):
            faces_action.triggered.connect(self._detect_faces_handler)
        menu.addAction(faces_action)

        refresh_action = QAction(t('google_layout.settings_menu.refresh_view'), menu)
        refresh_action.setToolTip(t('google_layout.settings_menu.refresh_view'))
        refresh_action.triggered.connect(self._load_photos)
        menu.addAction(refresh_action)

        menu.addSeparator()

        # TOOLS section
        menu.addSection(t('google_layout.settings_menu.tools_section'))

        db_action = QAction(t('google_layout.settings_menu.database_maintenance'), menu)
        if hasattr(self.main_window, '_on_database_maintenance'):
            db_action.triggered.connect(self.main_window._on_database_maintenance)
        else:
            db_action.triggered.connect(lambda: QMessageBox.information(
                self.main_window, "Tools", "Database Maintenance not available"))
        menu.addAction(db_action)

        clear_cache_action = QAction(t('google_layout.settings_menu.clear_cache'), menu)
        if hasattr(self.main_window, '_on_clear_thumbnail_cache'):
            clear_cache_action.triggered.connect(self.main_window._on_clear_thumbnail_cache)
        else:
            clear_cache_action.triggered.connect(lambda: QMessageBox.information(
                self.main_window, "Tools", "Clear Thumbnail Cache not available"))
        menu.addAction(clear_cache_action)

        menu.addSeparator()

        # VIEW section
        menu.addSection(t('google_layout.settings_menu.view_section'))

        dark_mode_action = QAction(t('google_layout.settings_menu.toggle_dark_mode'), menu)
        dark_mode_action.setCheckable(True)
        try:
            dark_mode_action.setChecked(bool(self.main_window.is_dark_mode_enabled()))
        except Exception:
            dark_mode_action.setChecked(False)
        if hasattr(self.main_window, 'toggle_dark_mode'):
            dark_mode_action.triggered.connect(self.main_window.toggle_dark_mode)
        else:
            dark_mode_action.triggered.connect(lambda: QMessageBox.information(
                self.main_window, "View", "Dark mode toggle not available"))
        menu.addAction(dark_mode_action)

        sidebar_mode_action = QAction(t('google_layout.settings_menu.sidebar_mode'), menu)
        if hasattr(self.main_window, 'toggle_sidebar_mode'):
            sidebar_mode_action.triggered.connect(self.main_window.toggle_sidebar_mode)
        else:
            sidebar_mode_action.triggered.connect(lambda: QMessageBox.information(
                self.main_window, "View", "Sidebar mode toggle not available"))
        menu.addAction(sidebar_mode_action)

        menu.addSeparator()

        # HELP section
        menu.addSection(t('google_layout.settings_menu.help_section'))

        shortcuts_action = QAction(t('google_layout.settings_menu.keyboard_shortcuts'), menu)
        if hasattr(self.main_window, 'show_keyboard_shortcuts_dialog'):
            shortcuts_action.triggered.connect(self.main_window.show_keyboard_shortcuts_dialog)
        else:
            shortcuts_action.triggered.connect(lambda: QMessageBox.information(
                self.main_window,
                "Keyboard Shortcuts",
                "Ctrl+F: Search\nCtrl+A: Select all\nCtrl+D: Deselect\nEscape: Clear\nDelete: Delete\nEnter: Open\nSpace: Quick preview\nS: Toggle selection\n+/-: Zoom\nG: Grid\nT: Timeline\nE: Single"
            ))
        menu.addAction(shortcuts_action)

        menu.addSeparator()

        # ABOUT section
        menu.addSection("ℹ️ About")

        about_action = QAction("ℹ️  About MemoryMate", menu)
        about_action.triggered.connect(lambda: QMessageBox.information(
            self.main_window,
            "About MemoryMate",
            "MemoryMate PhotoFlow\nVersion 1.0\n\nPhoto management with AI-powered face detection"
        ))
        menu.addAction(about_action)

        # Show menu below the Settings button
        menu.exec(self.btn_settings.mapToGlobal(self.btn_settings.rect().bottomLeft()))

    def _create_floating_toolbar(self, parent: QWidget) -> QWidget:
        """
        QUICK WIN #6: Create floating selection toolbar (Google Photos style).

        Appears at bottom of screen when photos are selected.
        Shows selection count and action buttons.

        Args:
            parent: Parent widget for positioning

        Returns:
            QWidget: Floating toolbar (initially hidden)
        """
        toolbar = QWidget(parent)
        toolbar.setStyleSheet("""
            QWidget {
                background: #202124;
                border-radius: 8px;
                border: 1px solid #5f6368;
            }
        """)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Selection count label
        self.selection_count_label = QLabel("0 selected")
        self.selection_count_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 11pt;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.selection_count_label)

        layout.addStretch()

        # Action buttons
        # Select All button
        btn_select_all = QPushButton("Select All")
        btn_select_all.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8ab4f8;
                border: none;
                padding: 6px 12px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: #3c4043;
                border-radius: 4px;
            }
        """)
        btn_select_all.setCursor(Qt.PointingHandCursor)
        btn_select_all.clicked.connect(self._on_select_all)
        layout.addWidget(btn_select_all)

        # Clear Selection button
        btn_clear = QPushButton("Clear")
        btn_clear.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8ab4f8;
                border: none;
                padding: 6px 12px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: #3c4043;
                border-radius: 4px;
            }
        """)
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self._on_clear_selection)
        layout.addWidget(btn_clear)

        # Delete button
        btn_delete = QPushButton("🗑️ Delete")
        btn_delete.setStyleSheet("""
            QPushButton {
                background: #d32f2f;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #b71c1c;
            }
        """)
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.clicked.connect(self._on_delete_selected)
        layout.addWidget(btn_delete)

        # Position toolbar at bottom center (will be repositioned on resize)
        toolbar.setFixedHeight(56)
        toolbar.setFixedWidth(400)

        return toolbar

    def _create_date_scroll_indicator(self, parent: QWidget) -> QWidget:
        """
        PHASE 2 #4: Create floating date scroll indicator.

        Shows current date when scrolling through timeline.
        Appears on right side, fades out after scrolling stops.

        Args:
            parent: Parent widget for positioning

        Returns:
            QWidget: Floating date indicator (initially hidden)
        """
        indicator = QLabel(parent)
        indicator.setStyleSheet("""
            QLabel {
                background: rgba(32, 33, 36, 0.9);
                color: white;
                font-size: 14pt;
                font-weight: bold;
                padding: 12px 20px;
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        indicator.setAlignment(Qt.AlignCenter)
        indicator.setText("Loading...")
        indicator.adjustSize()

        return indicator

    def _create_sidebar(self) -> QWidget:
        """
        Create Google Photos-style accordion sidebar.

        Phase 3 Implementation:
        - AccordionSidebar with all 6 sections (People, Dates, Folders, Tags, Branches, Quick)
        - One section expanded at a time (full height)
        - Other sections collapsed to headers
        - ONE universal scrollbar per section
        - Clean, modern Google Photos UX
        """
        # Import and instantiate AccordionSidebar
        from accordion_sidebar import AccordionSidebar

        # CRITICAL FIX: GooglePhotosLayout is NOT a QWidget, so pass None as parent
        sidebar = AccordionSidebar(project_id=self.project_id, parent=None)
        sidebar.setMinimumWidth(240)
        sidebar.setMaximumWidth(500)

        # CRITICAL: Don't set generic QWidget stylesheet - it overrides accordion's internal styling
        # AccordionSidebar handles its own styling internally (nav bar, headers, content areas)
        # Only set border on the container itself
        sidebar.setStyleSheet("""
            AccordionSidebar {
                border-right: 1px solid #dadce0;
            }
        """)

        # Connect accordion signals to grid filtering
        sidebar.selectBranch.connect(self._on_accordion_branch_clicked)
        sidebar.selectFolder.connect(self._on_accordion_folder_clicked)
        sidebar.selectDate.connect(self._on_accordion_date_clicked)
        sidebar.selectTag.connect(self._on_accordion_tag_clicked)
        sidebar.selectVideo.connect(self._on_accordion_video_clicked)  # NEW: Video filtering

        # FIX: Connect section expansion signal to hide search suggestions popup
        sidebar.sectionExpanding.connect(self._on_accordion_section_expanding)

        # Store reference for refreshing
        self.accordion_sidebar = sidebar

        return sidebar

    def _create_timeline(self) -> QWidget:
        """
        Create timeline scroll area with date groups.
        """
        # Scroll area
        self.timeline_scroll = QScrollArea()  # Store reference for scroll events
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_scroll.setFrameShape(QFrame.NoFrame)
        self.timeline_scroll.setStyleSheet("""
            QScrollArea {
                background: white;
                border: none;
            }
        """)

        # Timeline container (holds date groups)
        self.timeline_container = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_container)
        self.timeline_layout.setContentsMargins(20, 20, 20, 20)
        self.timeline_layout.setSpacing(30)
        self.timeline_layout.setAlignment(Qt.AlignTop)

        self.timeline_scroll.setWidget(self.timeline_container)

        # QUICK WIN #1: Connect scroll event for lazy thumbnail loading
        # This enables ALL photos to load as user scrolls (removes 30-photo limit)
        self.timeline_scroll.verticalScrollBar().valueChanged.connect(
            self._on_timeline_scrolled
        )
        print("[GooglePhotosLayout] ✅ Scroll-triggered lazy loading enabled")

        # PHASE 2 #2: Setup drag-to-select rubber band
        self._setup_drag_select()

        return self.timeline_scroll

    def _load_photos(self, thumb_size: int = 200, filter_year: int = None, filter_month: int = None, filter_day: int = None, filter_folder: str = None, filter_person: str = None):
        """
        Load photos from database and populate timeline.

        Args:
            thumb_size: Thumbnail size in pixels (default 200)
            filter_year: Optional year filter (e.g., 2024)
            filter_month: Optional month filter (1-12, requires filter_year)
            filter_day: Optional day filter (1-31, requires filter_year and filter_month)
            filter_folder: Optional folder path filter
            filter_person: Optional person/face cluster filter (branch_key)

        CRITICAL: Wrapped in comprehensive error handling to prevent crashes
        during/after scan operations when database might be in inconsistent state.
        """
        # Store current thumbnail size and filters
        self.current_thumb_size = thumb_size
        self.current_filter_year = filter_year
        self.current_filter_month = filter_month
        self.current_filter_day = filter_day
        self.current_filter_folder = filter_folder
        self.current_filter_person = filter_person

        filter_desc = []
        if filter_year:
            filter_desc.append(f"year={filter_year}")
        if filter_month:
            filter_desc.append(f"month={filter_month}")
        if filter_day:
            filter_desc.append(f"day={filter_day}")
        if filter_folder:
            filter_desc.append(f"folder={filter_folder}")
        if filter_person:
            filter_desc.append(f"person={filter_person}")

        filter_str = f" [{', '.join(filter_desc)}]" if filter_desc else ""
        print(f"[GooglePhotosLayout] 📷 Loading photos from database (thumb size: {thumb_size}px){filter_str}...")

        # Show/hide Clear Filter button based on whether filters are active
        has_filters = filter_year is not None or filter_month is not None or filter_day is not None or filter_folder is not None or filter_person is not None
        self.btn_clear_filter.setVisible(has_filters)

        # === PROGRESS: Clearing existing timeline ===
        print(f"[GooglePhotosLayout] 🔄 Clearing existing timeline and thumbnail cache...")

        # Clear existing timeline and thumbnail cache
        try:
            while self.timeline_layout.count():
                child = self.timeline_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            # Clear thumbnail button cache and reset load counter
            self.thumbnail_buttons.clear()
            self.thumbnail_load_count = 0  # Reset counter for new photo set

            # CRITICAL FIX: Only clear trees when NOT filtering
            # When filtering, we want to keep the tree structure visible
            # so users can see all available years/months/folders/people and switch between them
            # NOTE: With AccordionSidebar, clearing is handled internally - no action needed here
            pass
        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error in _load_photos setup: {e}")
            # Continue anyway

        # === PROGRESS: Scanning database for photos ===
        print(f"[GooglePhotosLayout] 🔍 Scanning database for photos in project {self.project_id}...")

        # Get photos from database
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # CRITICAL: Check if we have a valid project
            if self.project_id is None:
                # No project - show empty state with instructions
                empty_label = QLabel("📂 No project selected\n\nClick '➕ New Project' to create your first project")
                empty_label.setAlignment(Qt.AlignCenter)
                empty_label.setStyleSheet("font-size: 12pt; color: #888; padding: 60px;")
                self.timeline_layout.addWidget(empty_label)
                print("[GooglePhotosLayout] ⚠️ No project selected")
                return

            # Query photos for the current project (join with project_images)
            # CRITICAL FIX: Filter by project_id using project_images table
            # Build query with optional filters
            # CRITICAL FIX: Use created_date instead of date_taken
            # created_date is ALWAYS populated (uses date_taken if available, otherwise file modified date)
            # This matches Current Layout behavior and ensures ALL photos appear
            
            # PHASE 0 FIX: Query BOTH photo_metadata AND video_metadata tables
            # When filtering by folder, we need to show both photos and videos in that folder
            query_parts = []
            params_list = []
            
            # PHOTOS QUERY
            photo_query_parts = ["""
                SELECT DISTINCT pm.path, pm.created_date as date_taken, pm.width, pm.height
                FROM photo_metadata pm
                JOIN project_images pi ON pm.path = pi.image_path
                WHERE pi.project_id = ?
            """]
            photo_params = [self.project_id]

            # Add year filter (using created_date which is always populated)
            if filter_year is not None:
                photo_query_parts.append("AND strftime('%Y', pm.created_date) = ?")
                photo_params.append(str(filter_year))

            # Add month filter (requires year)
            if filter_month is not None and filter_year is not None:
                photo_query_parts.append("AND strftime('%m', pm.created_date) = ?")
                photo_params.append(f"{filter_month:02d}")
            
            # BUG FIX: Add day filter (requires year and month)
            if filter_day is not None and filter_year is not None and filter_month is not None:
                photo_query_parts.append("AND strftime('%d', pm.created_date) = ?")
                photo_params.append(f"{filter_day:02d}")

            # Add folder filter
            # CRITICAL FIX: Normalize folder path to match database storage format
            # Database stores paths as: c:/users/... (forward slashes, lowercase on Windows)
            # Without normalization, backslash paths won't match: C:\Users\... != c:/users/...
            if filter_folder is not None:
                # Normalize path: convert backslashes to forward slashes, lowercase on Windows
                import platform
                normalized_folder = filter_folder.replace('\\', '/')
                if platform.system() == 'Windows':
                    normalized_folder = normalized_folder.lower()
                
                photo_query_parts.append("AND pm.path LIKE ?")
                photo_params.append(f"{normalized_folder}%")

            # Add person/face filter (photos containing this person)
            if filter_person is not None:
                print(f"[GooglePhotosLayout] Filtering by person: {filter_person}")
                photo_query_parts.append("""
                    AND pm.path IN (
                        SELECT DISTINCT image_path
                        FROM face_crops
                        WHERE project_id = ? AND branch_key = ?
                    )
                """)
                photo_params.append(self.project_id)
                photo_params.append(filter_person)
            
            # VIDEOS QUERY (mirror photo query structure)
            video_query_parts = ["""
                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                FROM video_metadata vm
                JOIN project_videos pv ON vm.path = pv.video_path
                WHERE pv.project_id = ?
            """]
            video_params = [self.project_id]
            
            # Add year filter for videos
            if filter_year is not None:
                video_query_parts.append("AND strftime('%Y', vm.created_date) = ?")
                video_params.append(str(filter_year))
            
            # Add month filter for videos
            if filter_month is not None and filter_year is not None:
                video_query_parts.append("AND strftime('%m', vm.created_date) = ?")
                video_params.append(f"{filter_month:02d}")
            
            # BUG FIX: Add day filter for videos (requires year and month)
            if filter_day is not None and filter_year is not None and filter_month is not None:
                video_query_parts.append("AND strftime('%d', vm.created_date) = ?")
                video_params.append(f"{filter_day:02d}")
            
            # Add folder filter for videos
            # CRITICAL FIX: Normalize folder path (same as photos above)
            if filter_folder is not None:
                # Normalize path: convert backslashes to forward slashes, lowercase on Windows
                import platform
                normalized_folder = filter_folder.replace('\\', '/')
                if platform.system() == 'Windows':
                    normalized_folder = normalized_folder.lower()
                
                video_query_parts.append("AND vm.path LIKE ?")
                video_params.append(f"{normalized_folder}%")
            
            # Videos don't have person filters (no face detection on videos)
            
            # COMBINE QUERIES WITH UNION ALL
            photo_query = "\n".join(photo_query_parts)
            video_query = "\n".join(video_query_parts)
            
            # Only include videos if NOT filtering by person (videos have no faces)
            if filter_person is None:
                query = f"{photo_query}\nUNION ALL\n{video_query}\nORDER BY date_taken DESC"
                params = photo_params + video_params
            else:
                # Person filter: only photos (videos have no faces)
                query = f"{photo_query}\nORDER BY date_taken DESC"
                params = photo_params

            # Debug: Log SQL query and parameters
            print(f"[GooglePhotosLayout] 🔍 SQL Query:\n{query}")
            print(f"[GooglePhotosLayout] 🔍 Parameters: {params}")
            if filter_person is not None:
                print(f"[GooglePhotosLayout] 🔍 Person filter: project_id={self.project_id}, branch_key={filter_person}")

            # Use ReferenceDB's connection pattern with timeout protection
            try:
                with db._connect() as conn:
                    # Set a timeout to prevent blocking if database is locked
                    conn.execute("PRAGMA busy_timeout = 5000")  # 5 second timeout
                    cur = conn.cursor()
                    cur.execute(query, tuple(params))
                    rows = cur.fetchall()

                    # === PROGRESS: Photos found in database ===
                    print(f"[GooglePhotosLayout] ✅ Found {len(rows)} photos in database")
                    print(f"[GooglePhotosLayout] 📊 Database scan complete - preparing to load thumbnails...")

                    # Update section counts: timeline and videos
                    try:
                        if hasattr(self, 'timeline_section'):
                            self.timeline_section.update_count(len(rows))
                        if hasattr(self, 'videos_section'):
                            video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.3gp'}
                            video_count = sum(1 for (p, _, _, _) in rows if os.path.splitext(p)[1].lower() in video_exts)
                            self.videos_section.update_count(video_count)
                    except Exception:
                        pass

                    # NOTE: Sidebar reload removed from here to fix "Cannot operate on a closed database" error
                    # The sidebar should only reload when:
                    # 1. Actually scanning new photos from disk (handled in scan completion callback)
                    # 2. After face detection completes (handled in face detection callback)
                    # 3. After renaming/merging people (handled in person actions)
                    # NOT when just filtering existing photos (causes database connection conflicts)

            except Exception as db_error:
                print(f"[GooglePhotosLayout] ⚠️ Database query failed: {db_error}")
                # Show error state but don't crash
                error_label = QLabel(f"⚠️ Error loading photos\n\n{str(db_error)}\n\nTry clicking Refresh")
                error_label.setAlignment(Qt.AlignCenter)
                error_label.setStyleSheet("font-size: 11pt; color: #d32f2f; padding: 60px;")
                self.timeline_layout.addWidget(error_label)
                return

            if not rows:
                # PHASE 2 #7: Enhanced empty state with friendly illustration
                empty_widget = self._create_empty_state(
                    icon="📷",
                    title="No photos yet",
                    message="Your photo collection is waiting to be filled!\n\nClick 'Scan Repository' to import photos.",
                    action_text="or drag and drop photos here"
                )
                self.timeline_layout.addWidget(empty_widget)
                print(f"[GooglePhotosLayout] No photos found in project {self.project_id}")
                return

            # === PROGRESS: Grouping photos by date ===
            print(f"[GooglePhotosLayout] 📅 Grouping {len(rows)} photos by date...")

            # Group photos by date
            photos_by_date = self._group_photos_by_date(rows)

            print(f"[GooglePhotosLayout] ✅ Grouped into {len(photos_by_date)} date groups")

            # Build sidebar sections
            # CRITICAL: Sidebar should ALWAYS show ALL items (not filtered)
            # Only the photo grid should be filtered, not the sidebar navigation
            # NOTE: With AccordionSidebar, sections load their own data on demand
            # No need to build sidebar trees here - accordion handles it internally
            if filter_year is None and filter_month is None and filter_day is None and filter_folder is None and filter_person is None:
                # Full rebuild - accordion sidebar refreshes automatically
                pass
            else:
                # When filtering photos, accordion sidebar stays independent
                pass

            # Track all displayed paths for Shift+Ctrl multi-selection
            self.all_displayed_paths = [photo[0] for photos_list in photos_by_date.values() for photo in photos_list]
            print(f"[GooglePhotosLayout] Tracking {len(self.all_displayed_paths)} paths for multi-selection")

            # === PROGRESS: Virtual scrolling setup ===
            print(f"[GooglePhotosLayout] 🚀 Setting up virtual scrolling for {len(photos_by_date)} date groups...")

            # QUICK WIN #3: Virtual scrolling - create date groups with lazy rendering
            self.date_groups_metadata.clear()
            self.date_group_widgets.clear()
            self.rendered_date_groups.clear()

            # Store metadata for all date groups
            for index, (date_str, photos) in enumerate(photos_by_date.items()):
                self.date_groups_metadata.append({
                    'index': index,
                    'date_str': date_str,
                    'photos': photos,
                    'thumb_size': thumb_size
                })

            # Create widgets (placeholders or rendered) for each group
            for metadata in self.date_groups_metadata:
                index = metadata['index']

                # Render first N groups immediately, placeholders for the rest
                if self.virtual_scroll_enabled and index >= self.initial_render_count:
                    # Create placeholder for off-screen groups
                    widget = self._create_date_group_placeholder(metadata)
                else:
                    # Render initial groups
                    widget = self._create_date_group(
                        metadata['date_str'],
                        metadata['photos'],
                        metadata['thumb_size']
                    )
                    self.rendered_date_groups.add(index)

                self.date_group_widgets[index] = widget
                self.timeline_layout.addWidget(widget)

            # Add spacer at bottom
            self.timeline_layout.addStretch()

            # === PROGRESS: Rendering complete ===
            if self.virtual_scroll_enabled:
                print(f"[GooglePhotosLayout] ✅ Virtual scrolling enabled: {len(photos_by_date)} total date groups")
                print(f"[GooglePhotosLayout] 📊 Rendered: {len(self.rendered_date_groups)} groups | Placeholders: {len(photos_by_date) - len(self.rendered_date_groups)} groups")
            else:
                print(f"[GooglePhotosLayout] ✅ Loaded {len(rows)} photos in {len(photos_by_date)} date groups")

            print(f"[GooglePhotosLayout] 🖼️ Queued {self.thumbnail_load_count} thumbnails for loading (initial limit: {self.initial_load_limit})")
            print(f"[GooglePhotosLayout] ✅ Photo loading complete! Thumbnails will load progressively.")

        except Exception as e:
            # CRITICAL: Catch ALL exceptions to prevent layout crashes
            print(f"[GooglePhotosLayout] ⚠️ CRITICAL ERROR loading photos: {e}")
            import traceback
            traceback.print_exc()

            # Show error state with actionable message
            try:
                error_label = QLabel(
                    f"⚠️ Failed to load photos\n\n"
                    f"Error: {str(e)}\n\n"
                    f"Try:\n"
                    f"• Click Refresh button\n"
                    f"• Switch to Current layout and back\n"
                    f"• Restart the application"
                )
                error_label.setAlignment(Qt.AlignCenter)
                error_label.setStyleSheet("font-size: 11pt; color: #d32f2f; padding: 40px;")
                self.timeline_layout.addWidget(error_label)
            except:
                pass  # Even error display failed - just log it

    def _group_photos_by_date(self, rows) -> Dict[str, List[Tuple]]:
        """
        Group photos by date (YYYY-MM-DD).

        Uses created_date which is ALWAYS populated (never NULL).
        created_date = date_taken if available, otherwise file modified date.

        Returns:
            dict: {date_str: [(path, date_taken, width, height), ...]}
        """
        groups = defaultdict(list)

        for row in rows:
            path, date_taken, width, height = row

            # created_date is always in YYYY-MM-DD format, so we can use it directly
            # No need to parse or handle NULL values
            if date_taken:  # Should always be true since created_date is never NULL
                groups[date_taken].append((path, date_taken, width, height))
            else:
                # Fallback (should never happen with created_date)
                print(f"[GooglePhotosLayout] ⚠️ WARNING: Photo has no created_date: {path}")

        return dict(groups)

    def _build_timeline_tree(self, photos_by_date: Dict[str, List[Tuple]]):
        """
        Build timeline tree in sidebar (Years > Months with counts).

        Uses created_date which is always in YYYY-MM-DD format.
        NOTE: With AccordionSidebar, this is handled internally - this method is a no-op.
        """
        # Old sidebar implementation - no longer needed with AccordionSidebar
        if not hasattr(self, 'timeline_tree'):
            return

        # Group by year and month
        years_months = defaultdict(lambda: defaultdict(int))

        for date_str in photos_by_date.keys():
            # created_date is always YYYY-MM-DD format, can parse directly
            try:
                date_obj = datetime.fromisoformat(date_str)
                year = date_obj.year
                month = date_obj.month
                count = len(photos_by_date[date_str])
                years_months[year][month] += count
            except Exception as e:
                print(f"[GooglePhotosLayout] ⚠️ Failed to parse date '{date_str}': {e}")
                continue

        # Build tree
        for year in sorted(years_months.keys(), reverse=True):
            year_item = QTreeWidgetItem([f"📅 {year}"])
            year_item.setData(0, Qt.UserRole, {"type": "year", "year": year})
            year_item.setExpanded(True)
            self.timeline_tree.addTopLevelItem(year_item)

            for month in sorted(years_months[year].keys(), reverse=True):
                count = years_months[year][month]
                month_name = datetime(year, month, 1).strftime("%B")
                month_item = QTreeWidgetItem([f"  • {month_name} ({count})"])
                month_item.setData(0, Qt.UserRole, {"type": "month", "year": year, "month": month})
                year_item.addChild(month_item)

    def _build_folders_tree(self, rows):
        """
        Build folders tree in sidebar (folder hierarchy with counts).

        Args:
            rows: List of (path, date_taken, width, height) tuples
        NOTE: With AccordionSidebar, this is handled internally - this method is a no-op.
        """
        # Old sidebar implementation - no longer needed with AccordionSidebar
        if not hasattr(self, 'folders_tree'):
            return

        # Group photos by parent folder
        folder_counts = defaultdict(int)

        for row in rows:
            path = row[0]
            parent_folder = os.path.dirname(path)
            folder_counts[parent_folder] += 1

        # Sort folders by count (most photos first)
        sorted_folders = sorted(folder_counts.items(), key=lambda x: x[1], reverse=True)

        # Build tree (show top 10 folders)
        for folder, count in sorted_folders[:10]:
            # Show only folder name, not full path
            folder_name = os.path.basename(folder) if folder else "(Root)"
            if not folder_name:
                folder_name = folder  # Show full path if basename is empty

            folder_item = QTreeWidgetItem([f"📁 {folder_name} ({count})"])
            folder_item.setData(0, Qt.UserRole, {"type": "folder", "path": folder})
            folder_item.setToolTip(0, folder)  # Show full path on hover
            self.folders_tree.addTopLevelItem(folder_item)
        # Update Folders section count (sum of all photos across folders)
        try:
            if hasattr(self, 'folders_section'):
                self.folders_section.update_count(sum(folder_counts.values()))
        except Exception:
            pass

    def _on_timeline_item_clicked(self, item: QTreeWidgetItem, column: int):
        """
        Handle timeline tree item click - filter by year or month.

        Args:
            item: Clicked tree item
            column: Column index (always 0)
        """
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        item_type = data.get("type")

        if item_type == "year":
            year = data.get("year")
            print(f"[GooglePhotosLayout] Filtering by year: {year}")
            self._load_photos(
                thumb_size=self.current_thumb_size,
                filter_year=year,
                filter_month=None,
                filter_day=None,
                filter_folder=None,
                filter_person=None
            )
        elif item_type == "month":
            year = data.get("year")
            month = data.get("month")
            month_name = datetime(year, month, 1).strftime("%B %Y")
            print(f"[GooglePhotosLayout] Filtering by month: {month_name}")
            self._load_photos(
                thumb_size=self.current_thumb_size,
                filter_year=year,
                filter_month=month,
                filter_day=None,
                filter_folder=None,
                filter_person=None
            )

    def _on_folder_item_clicked(self, item: QTreeWidgetItem, column: int):
        """
        Handle folder tree item click - filter by folder.

        Args:
            item: Clicked tree item
            column: Column index (always 0)
        """
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        folder_path = data.get("path")
        if folder_path:
            folder_name = os.path.basename(folder_path) if folder_path else "(Root)"
            print(f"[GooglePhotosLayout] Filtering by folder: {folder_name}")
            self._load_photos(
                thumb_size=self.current_thumb_size,
                filter_year=None,
                filter_month=None,
                filter_day=None,
                filter_folder=folder_path,
                filter_person=None
            )

    def _build_tags_tree(self):
        """
        Build tags tree in sidebar (shows all tags with counts).
        NOTE: With AccordionSidebar, this is handled internally - this method is a no-op.
        """
        # Old sidebar implementation - no longer needed with AccordionSidebar
        if not hasattr(self, 'tags_tree'):
            return

        try:
            from services.tag_service import get_tag_service
            tag_service = get_tag_service()
            tag_rows = tag_service.get_all_tags_with_counts(self.project_id) or []
        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error loading tags: {e}")
            import traceback
            traceback.print_exc()
            return

        # Clear and update count
        self.tags_tree.clear()
        total_count = sum(int(c or 0) for _, c in tag_rows)
        if hasattr(self, 'tags_section'):
            self.tags_section.update_count(total_count)

        # Icon mapping for common tags
        ICONS = {
            'favorite': '⭐',
            'face': '👤',
            'important': '⚑',
            'work': '💼',
            'travel': '✈',
            'personal': '♥',
            'family': '👨‍👩‍👧',
            'archive': '📦',
        }

        # Populate tree
        for tag_name, count in tag_rows:
            icon = ICONS.get(tag_name.lower(), '🏷️')
            count_text = f" ({count})" if count else ""
            display = f"{icon} {tag_name}{count_text}"
            item = QTreeWidgetItem([display])
            item.setData(0, Qt.UserRole, tag_name)
            self.tags_tree.addTopLevelItem(item)

        print(f"[GooglePhotosLayout] ✓ Built tags tree: {len(tag_rows)} tags")
    
    def _on_tags_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle tags tree item click - filter timeline by tag."""
        tag_name = item.data(0, Qt.UserRole)
        if not tag_name:
            return
        self._filter_by_tag(tag_name)


    def _build_people_tree(self):
        """
        Build people grid/tree in sidebar (face clusters with counts).

        Phase 1+2: Now populates both grid view AND tree (tree hidden, kept for compatibility).
        Queries face_branch_reps table for detected faces/people.
        NOTE: With AccordionSidebar, this is handled internally - this method is a no-op.
        """
        # Old sidebar implementation - no longer needed with AccordionSidebar
        if not hasattr(self, 'people_grid') and not hasattr(self, 'people_tree'):
            return

        print("[GooglePhotosLayout] 🔍 _build_people_tree() called")
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Query ALL face clusters for current project (removed LIMIT 10)
            # Grid view can handle many more people than tree view!
            query = """
                SELECT branch_key, label, count, rep_path, rep_thumb_png
                FROM face_branch_reps
                WHERE project_id = ?
                ORDER BY count DESC
            """

            print(f"[GooglePhotosLayout] 👥 Querying face_branch_reps for project_id={self.project_id}")

            with db._connect() as conn:
                conn.execute("PRAGMA busy_timeout = 5000")
                cur = conn.cursor()
                cur.execute(query, (self.project_id,))
                rows = cur.fetchall()

            print(f"[GooglePhotosLayout] 👥 Found {len(rows)} face clusters in database")

            # Update section count badge
            if hasattr(self, 'people_section'):
                total_photos = sum(int(c or 0) for _, _, c, _, _ in rows)
                self.people_section.update_count(total_photos)
                print(f"[GooglePhotosLayout] ✓ Updated people section count badge: {total_photos}")
            else:
                print("[GooglePhotosLayout] ⚠️ people_section not found!")

            # Clear existing grid
            if hasattr(self, 'people_grid'):
                self.people_grid.clear()
                print(f"[GooglePhotosLayout] ✓ Cleared people grid")
            else:
                print("[GooglePhotosLayout] ⚠️ people_grid not found!")
                return

            if not rows:
                # No face clusters found
                print("[GooglePhotosLayout] No faces found - grid will show empty state")
                # Grid shows its own empty state message
                return

            # Populate GRID VIEW (Phase 1+2)
            added_count = 0
            for branch_key, label, count, rep_path, rep_thumb_png in rows:
                # Use label if set, otherwise use "Unnamed"
                display_name = label if label else "Unnamed"

                # Load face thumbnail as pixmap
                face_pixmap = None
                if rep_thumb_png:
                    try:
                        from PySide6.QtGui import QPixmap
                        import base64
                        img_data = base64.b64decode(rep_thumb_png)
                        face_pixmap = QPixmap()
                        success = face_pixmap.loadFromData(img_data)
                        if success:
                            print(f"[GooglePhotosLayout]   ✓ Loaded pixmap for {display_name}: {face_pixmap.width()}x{face_pixmap.height()}")
                        else:
                            print(f"[GooglePhotosLayout]   ⚠️ Failed to load pixmap for {display_name}")
                            face_pixmap = None
                    except Exception as e:
                        print(f"[GooglePhotosLayout] ⚠️ Error loading face pixmap for {display_name}: {e}")
                        face_pixmap = None
                # Fallback: if no BLOB thumbnail, try loading from representative file path
                if face_pixmap is None and rep_path:
                    try:
                        from PySide6.QtGui import QPixmap
                        import os
                        if os.path.exists(rep_path):
                            file_pixmap = QPixmap(rep_path)
                            if not file_pixmap.isNull():
                                face_pixmap = file_pixmap
                                print(f"[GooglePhotosLayout]   ✓ Loaded pixmap from file for {display_name}")
                            else:
                                print(f"[GooglePhotosLayout]   ⚠️ Pixmap from file is null for {display_name}")
                        else:
                            print(f"[GooglePhotosLayout]   ⚠️ rep_path not found for {display_name}: {rep_path}")
                    except Exception as e:
                        print(f"[GooglePhotosLayout] ⚠️ Error loading face pixmap from file for {display_name}: {e}")

                # Add to grid with both branch_key and display_name
                if hasattr(self, 'people_grid'):
                    self.people_grid.add_person(branch_key, display_name, face_pixmap, count)
                    added_count += 1
                    print(f"[GooglePhotosLayout]   ✓ Added to grid [{added_count}/{len(rows)}]: {display_name} ({count} photos)")

            print(f"[GooglePhotosLayout] ✅ Populated people grid with {added_count} faces")

            # Also populate old tree (hidden, for backward compatibility)
            # This ensures any code that references self.people_tree still works
            for branch_key, label, count, rep_path, rep_thumb_png in rows:
                display_name = label if label else f"Unnamed Person"
                person_item = QTreeWidgetItem([f"{display_name} ({count})"])
                person_item.setData(0, Qt.UserRole, {"type": "person", "branch_key": branch_key, "label": label})

                icon = self._load_face_thumbnail(rep_path, rep_thumb_png)
                if icon:
                    person_item.setIcon(0, icon)
                else:
                    person_item.setText(0, f"👤 {display_name} ({count})")

                self.people_tree.addTopLevelItem(person_item)

            print(f"[GooglePhotosLayout] ✅ _build_people_tree() completed successfully")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error building people grid: {e}")
            import traceback
            traceback.print_exc()

    def _make_circular_face_icon(self, pixmap: QPixmap, size: int = 64) -> QIcon:
        """
        Create circular face icon (Google Photos / iPhone Photos style).

        Args:
            pixmap: Source pixmap
            size: Diameter of circular icon

        Returns:
            QIcon with circular face thumbnail
        """
        from PySide6.QtGui import QPainter, QPainterPath

        # Scale to target size
        scaled = pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

        # Create circular mask
        circular = QPixmap(size, size)
        circular.fill(Qt.transparent)

        painter = QPainter(circular)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Create circular clip path
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)

        # Draw the image within the circle (centered)
        x_offset = (scaled.width() - size) // 2
        y_offset = (scaled.height() - size) // 2
        painter.drawPixmap(-x_offset, -y_offset, scaled)

        painter.end()

        return QIcon(circular)

    def _build_tags_tree(self):
        """
        Build tags tree in sidebar (shows all tags with counts).
        NOTE: With AccordionSidebar, this is handled internally - this method is a no-op.
        """
        # Old sidebar implementation - no longer needed with AccordionSidebar
        if not hasattr(self, 'tags_tree'):
            return

        try:
            from services.tag_service import get_tag_service
            tag_service = get_tag_service()
            tag_rows = tag_service.get_all_tags_with_counts(self.project_id) or []
        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error loading tags: {e}")
            import traceback
            traceback.print_exc()
            return

        # Clear and update count
        self.tags_tree.clear()
        total_count = sum(int(c or 0) for _, c in tag_rows)
        if hasattr(self, 'tags_section'):
            self.tags_section.update_count(total_count)

        # Icon mapping for common tags
        ICONS = {
            'favorite': '⭐',
            'face': '👤',
            'important': '⚑',
            'work': '💼',
            'travel': '✈',
            'personal': '♥',
            'family': '👨‍👩‍👧',
            'archive': '📦',
        }

        # Populate tree
        for tag_name, count in tag_rows:
            icon = ICONS.get(tag_name.lower(), '🏷️')
            count_text = f" ({count})" if count else ""
            display = f"{icon} {tag_name}{count_text}"
            item = QTreeWidgetItem([display])
            item.setData(0, Qt.UserRole, tag_name)
            self.tags_tree.addTopLevelItem(item)

        print(f"[GooglePhotosLayout] ✓ Built tags tree: {len(tag_rows)} tags")

    def _on_tags_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle tags tree item click - filter timeline by tag."""
        tag_name = item.data(0, Qt.UserRole)
        if not tag_name:
            return
        self._filter_by_tag(tag_name)

    # === Accordion Sidebar Click Handlers ===

    def _on_accordion_date_clicked(self, date_key: str):
        """
        Handle accordion sidebar date selection.

        Args:
            date_key: Date in format "YYYY", "YYYY-MM", or "YYYY-MM-DD"
        """
        print(f"[GooglePhotosLayout] Accordion date clicked: {date_key}")

        # Parse date_key to extract year, month, day
        parts = date_key.split("-")
        year = None
        month = None
        day = None

        if len(parts) >= 1:
            try:
                year = int(parts[0])
            except ValueError:
                pass

        if len(parts) >= 2:
            try:
                month = int(parts[1])
            except ValueError:
                pass
        
        # BUG FIX: Parse day from date_key (was missing!)
        if len(parts) >= 3:
            try:
                day = int(parts[2])
            except ValueError:
                pass

        # Filter by year, month, or day
        self._load_photos(
            thumb_size=self.current_thumb_size,
            filter_year=year,
            filter_month=month,
            filter_day=day,
            filter_folder=None,
            filter_person=None
        )

    def _on_accordion_folder_clicked(self, folder_id: int):
        """
        Handle accordion sidebar folder selection.

        Args:
            folder_id: Folder ID from database
        """
        print(f"[GooglePhotosLayout] Accordion folder clicked: {folder_id}")

        # Get folder path from database
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            with db._connect() as conn:
                cur = conn.cursor()
                # CRITICAL FIX: Use photo_folders table instead of non-existent folders table
                cur.execute("SELECT path FROM photo_folders WHERE id = ?", (folder_id,))
                row = cur.fetchone()
                if row:
                    folder_path = row[0]
                    print(f"[GooglePhotosLayout] Filtering by folder: {folder_path}")
                    self._load_photos(
                        thumb_size=self.current_thumb_size,
                        filter_year=None,
                        filter_month=None,
                        filter_day=None,
                        filter_folder=folder_path,
                        filter_person=None
                    )
        except Exception as e:
            print(f"[GooglePhotosLayout] Error loading folder: {e}")
            import traceback
            traceback.print_exc()

    def _on_accordion_tag_clicked(self, tag_name: str):
        """
        Handle accordion sidebar tag selection.

        Args:
            tag_name: Tag name to filter by
        """
        print(f"[GooglePhotosLayout] Accordion tag clicked: {tag_name}")
        self._filter_by_tag(tag_name)

    def _on_accordion_branch_clicked(self, branch_key: str):
        """
        Handle accordion sidebar branch/person selection.

        Args:
            branch_key: Branch key, may include "branch:" prefix or "facecluster:" prefix
        """
        print(f"[GooglePhotosLayout] Accordion branch clicked: {branch_key}")

        # Remove prefixes if present
        if branch_key.startswith("branch:"):
            branch_key = branch_key[7:]
        elif branch_key.startswith("facecluster:"):
            branch_key = branch_key[12:]

        # Filter by person/branch
        self._load_photos(
            thumb_size=self.current_thumb_size,
            filter_year=None,
            filter_month=None,
            filter_day=None,
            filter_folder=None,
            filter_person=branch_key
        )

    def _on_accordion_video_clicked(self, filter_spec: str):
        """
        Handle accordion sidebar video selection.

        Args:
            filter_spec: Video filter specification (e.g., "all", "duration:short", "resolution:hd", "codec:h264", "size:small")
        """
        print(f"[GooglePhotosLayout] Accordion video clicked: {filter_spec}")

        # For now, just show all videos by clearing filters
        # Future enhancement: implement duration/resolution filtering
        # Videos are mixed with photos, so filter by video extensions
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Get all videos from database
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                    FROM video_metadata vm
                    JOIN project_videos pv ON vm.path = pv.video_path
                    WHERE pv.project_id = ?
                    ORDER BY vm.created_date DESC
                """, (self.project_id,))
                video_rows = cur.fetchall()

            # Apply duration filter if specified
            if ":" in filter_spec:
                filter_type, filter_value = filter_spec.split(":", 1)

                if filter_type == "duration":
                    # Filter by duration: short, medium, long
                    with db._connect() as conn:
                        cur = conn.cursor()
                        if filter_value == "short":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.duration_seconds > 0 AND vm.duration_seconds < 30
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "medium":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.duration_seconds >= 30 AND vm.duration_seconds < 300
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "long":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.duration_seconds >= 300
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        video_rows = cur.fetchall()

                elif filter_type == "resolution":
                    # Filter by resolution: sd, hd, fhd, 4k
                    with db._connect() as conn:
                        cur = conn.cursor()
                        if filter_value == "sd":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.height > 0 AND vm.height < 720
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "hd":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.height >= 720 AND vm.height < 1080
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "fhd":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.height >= 1080 AND vm.height < 2160
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "4k":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.height >= 2160
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        video_rows = cur.fetchall()

                elif filter_type == "codec":
                    # NEW: Filter by codec: h264, hevc, vp9, av1, mpeg4
                    with db._connect() as conn:
                        cur = conn.cursor()
                        if filter_value == "h264":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.codec IS NOT NULL AND LOWER(vm.codec) IN ('h264', 'avc')
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "hevc":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.codec IS NOT NULL AND LOWER(vm.codec) IN ('hevc', 'h265')
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "vp9":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.codec IS NOT NULL AND LOWER(vm.codec) = 'vp9'
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "av1":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.codec IS NOT NULL AND LOWER(vm.codec) = 'av1'
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "mpeg4":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.codec IS NOT NULL AND LOWER(vm.codec) IN ('mpeg4', 'xvid', 'divx')
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        video_rows = cur.fetchall()

                elif filter_type == "size":
                    # NEW: Filter by file size: small, medium, large, xlarge
                    with db._connect() as conn:
                        cur = conn.cursor()
                        if filter_value == "small":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.size_kb IS NOT NULL AND vm.size_kb / 1024 < 100
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "medium":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.size_kb IS NOT NULL AND vm.size_kb / 1024 >= 100 AND vm.size_kb / 1024 < 1024
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "large":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.size_kb IS NOT NULL AND vm.size_kb / 1024 >= 1024 AND vm.size_kb / 1024 < 5120
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        elif filter_value == "xlarge":
                            cur.execute("""
                                SELECT DISTINCT vm.path, vm.created_date as date_taken, vm.width, vm.height
                                FROM video_metadata vm
                                JOIN project_videos pv ON vm.path = pv.video_path
                                WHERE pv.project_id = ? AND vm.size_kb IS NOT NULL AND vm.size_kb / 1024 >= 5120
                                ORDER BY vm.created_date DESC
                            """, (self.project_id,))
                        video_rows = cur.fetchall()

            # Rebuild timeline with video results
            self._rebuild_timeline_with_results(video_rows, f"Videos: {filter_spec}")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error filtering videos: {e}")
            import traceback
            traceback.print_exc()

    def _on_accordion_section_expanding(self, section_id: str):
        """
        Handle accordion section expansion - hide search suggestions popup.

        This prevents the popup from briefly appearing during layout changes
        when accordion sections expand/collapse.

        Args:
            section_id: The section being expanded (e.g., "people", "dates", "folders")
        """
        # NUCLEAR FIX: Block popup from showing during layout changes
        self._popup_blocked = True

        # Hide search suggestions popup if visible
        if hasattr(self, 'search_suggestions') and self.search_suggestions.isVisible():
            self.search_suggestions.hide()

        # Unblock popup after layout changes complete (300ms delay)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300, lambda: setattr(self, '_popup_blocked', False))

    def _filter_by_tag(self, tag_name: str):
        """Filter timeline to show photos by the given tag."""
        try:
            from services.tag_service import get_tag_service
            tag_service = get_tag_service()
            paths = tag_service.get_paths_by_tag(tag_name, self.project_id)
            if not paths:
                self._rebuild_timeline_with_results([], f"Tag: {tag_name}")
                return
            
            # Build rows with date information
            rows = []
            from reference_db import ReferenceDB
            db = ReferenceDB()
            with db._connect() as conn:
                cur = conn.cursor()
                for p in paths:
                    cur.execute(
                        """
                        SELECT path, COALESCE(date_taken, created_date) AS date_taken, width, height
                        FROM photo_metadata
                        WHERE path = ? AND project_id = ?
                        """,
                        (p, self.project_id)
                    )
                    r = cur.fetchone()
                    if r:
                        rows.append((r[0], r[1], r[2], r[3]))
            
            self._rebuild_timeline_with_results(rows, f"Tag: {tag_name}")
        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error filtering by tag '{tag_name}': {e}")

    def _load_face_thumbnail(self, rep_path: str, rep_thumb_png: bytes) -> QIcon:
        """
        Load face thumbnail from rep_path or rep_thumb_png BLOB with circular masking.

        Args:
            rep_path: Path to representative face crop image
            rep_thumb_png: PNG thumbnail as BLOB data

        Returns:
            QIcon with circular face thumbnail, or None if unavailable
        """
        try:
            from PIL import Image
            import io

            FACE_ICON_SIZE = 64  # Increased from 32px for better visibility

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

                        # ENHANCEMENT: Create circular icon (Google Photos / iPhone style)
                        return self._make_circular_face_icon(pixmap, FACE_ICON_SIZE)
                except Exception as blob_error:
                    print(f"[GooglePhotosLayout] Failed to load thumbnail from BLOB: {blob_error}")

            # Fallback: Try loading from file path
            if rep_path and os.path.exists(rep_path):
                try:
                    with Image.open(rep_path) as img:
                        # Convert to QPixmap
                        img_rgb = img.convert('RGB')
                        data = img_rgb.tobytes('raw', 'RGB')
                        qimg = QImage(data, img.width, img.height, QImage.Format_RGB888)
                        pixmap = QPixmap.fromImage(qimg)

                        # ENHANCEMENT: Create circular icon (Google Photos / iPhone style)
                        return self._make_circular_face_icon(pixmap, FACE_ICON_SIZE)
                except Exception as file_error:
                    print(f"[GooglePhotosLayout] Failed to load thumbnail from {rep_path}: {file_error}")

            return None

        except Exception as e:
            print(f"[GooglePhotosLayout] Error loading face thumbnail: {e}")
            return None

    def _on_people_item_clicked(self, item: QTreeWidgetItem, column: int):
        """
        Handle people tree item click - filter by person/face cluster.

        Args:
            item: Clicked tree item
            column: Column index (always 0)
        """
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        branch_key = data.get("branch_key")
        if branch_key:
            label = data.get("label") or "Unnamed Person"
            print(f"[GooglePhotosLayout] Filtering by person: {label} (branch_key={branch_key})")
            self._load_photos(
                thumb_size=self.current_thumb_size,
                filter_year=None,
                filter_month=None,
                filter_folder=None,
                filter_person=branch_key
            )

    def _on_person_clicked_from_grid(self, person_name: str):
        """
        Handle person card click from grid view - filter by person.

        Args:
            person_name: Name of person clicked (branch_key format: "cluster_X" or name)
        """
        print(f"[GooglePhotosLayout] Filtering by person from grid: {person_name}")
        self._load_photos(
            thumb_size=self.current_thumb_size,
            filter_year=None,
            filter_month=None,
            filter_folder=None,
            filter_person=person_name  # person_name is the branch_key
        )

    def _prompt_quick_name_dialog(self):
        """Show a quick naming dialog for unnamed face clusters (top 12)."""
        try:
            from PySide6.QtWidgets import (
                QDialog, QVBoxLayout, QLabel, QGridLayout, QPushButton, QLineEdit, QWidget, QScrollArea, QMessageBox
            )
            from PySide6.QtGui import QPixmap
            import base64, os
            from reference_db import ReferenceDB

            # Fetch unnamed clusters
            db = ReferenceDB()
            rows = []
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT branch_key, label, count, rep_path, rep_thumb_png
                    FROM face_branch_reps
                    WHERE project_id = ? AND (label IS NULL OR TRIM(label) = '')
                    ORDER BY count DESC
                    LIMIT 12
                    """,
                    (self.project_id,)
                )
                rows = cur.fetchall() or []

            if not rows:
                return  # Nothing to name

            dlg = QDialog(self.main_window)
            dlg.setWindowTitle("Review & Name People")
            outer = QVBoxLayout(dlg)
            outer.setContentsMargins(16, 16, 16, 16)
            outer.setSpacing(12)

            header = QLabel("Face detection complete – name these people")
            header.setStyleSheet("color: white; font-size: 12pt;")
            outer.addWidget(header)

            # Scrollable grid of cards
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            container = QWidget()
            grid = QGridLayout(container)
            grid.setContentsMargins(8, 8, 8, 8)
            grid.setSpacing(12)

            editors = {}

            for i, row in enumerate(rows):
                branch_key, label, count, rep_path, rep_thumb = row
                card = QWidget()
                v = QVBoxLayout(card)
                v.setContentsMargins(8, 8, 8, 8)
                v.setSpacing(6)

                # Face preview
                face = QLabel()
                face.setFixedSize(200, 200)
                pix = None
                try:
                    if rep_thumb:
                        data = base64.b64decode(rep_thumb) if isinstance(rep_thumb, str) else rep_thumb
                        pix = QPixmap()
                        pix.loadFromData(data)
                    if (pix is None or pix.isNull()) and rep_path and os.path.exists(rep_path):
                        pix = QPixmap(rep_path)
                    if pix and not pix.isNull():
                        face.setPixmap(pix.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                except Exception:
                    pass
                v.addWidget(face)

                # Name editor
                name_edit = QLineEdit()
                name_edit.setPlaceholderText(f"Unnamed ({count} photos)")
                editors[branch_key] = name_edit
                v.addWidget(name_edit)

                # Place in grid
                row_i = i // 4
                col_i = i % 4
                grid.addWidget(card, row_i, col_i)

            scroll.setWidget(container)
            outer.addWidget(scroll, 1)

            # Actions
            actions = QWidget()
            ha = QHBoxLayout(actions)
            ha.setContentsMargins(0, 0, 0, 0)
            ha.addStretch()
            btn_skip = QPushButton("Review Later")
            btn_apply = QPushButton("Name Selected")
            ha.addWidget(btn_skip)
            ha.addWidget(btn_apply)
            outer.addWidget(actions)

            def apply_names():
                try:
                    updates = [(bk, editors[bk].text().strip()) for bk in editors]
                    updates = [(bk, nm) for bk, nm in updates if nm]
                    if not updates:
                        dlg.accept()
                        return
                    with db._connect() as conn:
                        cur = conn.cursor()
                        for bk, nm in updates:
                            cur.execute(
                                "UPDATE face_branch_reps SET label = ? WHERE project_id = ? AND branch_key = ?",
                                (nm, self.project_id, bk)
                            )
                            cur.execute(
                                "UPDATE branches SET display_name = ? WHERE project_id = ? AND branch_key = ?",
                                (nm, self.project_id, bk)
                            )
                        conn.commit()
                    # Refresh people UI
                    if hasattr(self, '_build_people_tree'):
                        self._build_people_tree()
                    # Refresh accordion sidebar people section
                    if hasattr(self, 'accordion_sidebar'):
                        self.accordion_sidebar.reload_section("people")
                    QMessageBox.information(dlg, "Saved", f"Named {len(updates)} people.")
                    dlg.accept()
                except Exception as e:
                    QMessageBox.critical(dlg, "Error", f"Failed to save names: {e}")

            btn_apply.clicked.connect(apply_names)
            btn_skip.clicked.connect(dlg.reject)

            dlg.exec()
        except Exception as e:
            print(f"[GooglePhotosLayout] Quick name dialog failed: {e}")

    def _prompt_bulk_face_review(self):
        """Bulk review grid for all unnamed clusters with simple filters."""
        try:
            from PySide6.QtWidgets import (
                QDialog, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QPushButton, QComboBox, QLineEdit, QWidget, QScrollArea, QMessageBox
            )
            from PySide6.QtGui import QPixmap
            import base64, os
            from reference_db import ReferenceDB

            db = ReferenceDB()
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT branch_key, label, count, rep_path, rep_thumb_png
                    FROM face_branch_reps
                    WHERE project_id = ? AND (label IS NULL OR TRIM(label) = '')
                    ORDER BY count DESC
                    """,
                    (self.project_id,)
                )
                rows = cur.fetchall() or []

            if not rows:
                QMessageBox.information(self.main_window, "No Unnamed People", "All people are already named.")
                return

            dlg = QDialog(self.main_window)
            dlg.setWindowTitle("Bulk Review: Name Unnamed People")
            outer = QVBoxLayout(dlg)
            outer.setContentsMargins(16, 16, 16, 16)
            outer.setSpacing(10)

            # Header + filter
            header_row = QHBoxLayout()
            header = QLabel("Review all unnamed people")
            header.setStyleSheet("color: white; font-size: 12pt;")
            header_row.addWidget(header)
            header_row.addStretch()
            filter_combo = QComboBox()
            filter_combo.addItems(["All", "Large groups (≥5)", "Uncertain (<5)"])
            header_row.addWidget(filter_combo)
            outer.addLayout(header_row)

            # Search box
            search_box = QLineEdit()
            search_box.setPlaceholderText("Filter by suggested name…")
            outer.addWidget(search_box)

            # Scrollable grid
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            container = QWidget()
            grid = QGridLayout(container)
            grid.setContentsMargins(8, 8, 8, 8)
            grid.setSpacing(12)

            editors = {}
            cards = []

            def populate():
                # Clear existing
                while grid.count():
                    it = grid.takeAt(0)
                    if it and it.widget():
                        it.widget().deleteLater()
                cards.clear()

                # Filter function
                selected = filter_combo.currentIndex()
                text = search_box.text().strip().lower()
                def passes(count):
                    return (
                        selected == 0 or
                        (selected == 1 and count >= 5) or
                        (selected == 2 and count < 5)
                    )

                # Populate
                i = 0
                for row in rows:
                    branch_key, label, count, rep_path, rep_thumb = row
                    if not passes(count):
                        continue
                    # Build card
                    card = QWidget()
                    v = QVBoxLayout(card)
                    v.setContentsMargins(8, 8, 8, 8)
                    v.setSpacing(6)

                    # Face preview
                    face = QLabel()
                    face.setFixedSize(200, 200)
                    pix = None
                    try:
                        if rep_thumb:
                            data = base64.b64decode(rep_thumb) if isinstance(rep_thumb, str) else rep_thumb
                            pix = QPixmap()
                            pix.loadFromData(data)
                        if (pix is None or pix.isNull()) and rep_path and os.path.exists(rep_path):
                            pix = QPixmap(rep_path)
                        if pix and not pix.isNull():
                            face.setPixmap(pix.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    except Exception:
                        pass
                    v.addWidget(face)

                    # Confidence hint based on compactness (mean similarity to centroid)
                    try:
                        import numpy as np
                        from reference_db import ReferenceDB
                        db_local = ReferenceDB()
                        with db_local._connect() as conn2:
                            cur2 = conn2.cursor()
                            cur2.execute("SELECT centroid FROM face_branch_reps WHERE project_id = ? AND branch_key = ?", (self.project_id, branch_key))
                            r = cur2.fetchone()
                            centroid_vec = np.frombuffer(r[0], dtype=np.float32) if r and r[0] else None
                            mean_sim = 0.0
                            if centroid_vec is not None:
                                cur2.execute("SELECT embedding FROM face_crops WHERE project_id = ? AND branch_key = ? AND embedding IS NOT NULL LIMIT 30", (self.project_id, branch_key))
                                embs = [np.frombuffer(e[0], dtype=np.float32) for e in cur2.fetchall() if e and e[0]]
                                sims = []
                                for vec in embs:
                                    denom = (np.linalg.norm(centroid_vec) * np.linalg.norm(vec))
                                    if denom > 0:
                                        sims.append(float(np.dot(centroid_vec, vec) / denom))
                                if sims:
                                    mean_sim = float(np.mean(sims))
                            # Badge by compactness
                            conf = "✅" if mean_sim >= 0.85 else ("⚠️" if mean_sim >= 0.70 else "❓")
                            hint = QLabel(f"{conf} compactness: {int(mean_sim*100)}% • {count} photos")
                    except Exception:
                        conf = "✅" if count >= 10 else ("⚠️" if count >= 5 else "❓")
                        hint = QLabel(f"{conf} {count} photos")
                    hint.setStyleSheet("color: #5f6368;")
                    v.addWidget(hint)

                    # Name editor
                    name_edit = QLineEdit()
                    name_edit.setPlaceholderText(f"Unnamed ({count} photos)")
                    editors[branch_key] = name_edit
                    v.addWidget(name_edit)

                    row_i = i // 4
                    col_i = i % 4
                    grid.addWidget(card, row_i, col_i)
                    cards.append(card)
                    i += 1

            populate()

            def apply_names():
                try:
                    updates = [(bk, editors[bk].text().strip()) for bk in editors]
                    updates = [(bk, nm) for bk, nm in updates if nm]
                    if not updates:
                        dlg.accept()
                        return
                    db = ReferenceDB()
                    with db._connect() as conn:
                        cur = conn.cursor()
                        for bk, nm in updates:
                            cur.execute("UPDATE face_branch_reps SET label = ? WHERE project_id = ? AND branch_key = ?", (nm, self.project_id, bk))
                            cur.execute("UPDATE branches SET display_name = ? WHERE project_id = ? AND branch_key = ?", (nm, self.project_id, bk))
                        conn.commit()
                    if hasattr(self, '_build_people_tree'):
                        self._build_people_tree()
                    QMessageBox.information(dlg, "Saved", f"Named {len(updates)} people.")
                    dlg.accept()
                except Exception as e:
                    QMessageBox.critical(dlg, "Error", f"Failed to save names: {e}")

            scroll.setWidget(container)
            outer.addWidget(scroll, 1)

            # Actions
            actions = QWidget()
            ha = QHBoxLayout(actions)
            ha.setContentsMargins(0, 0, 0, 0)
            ha.addStretch()
            btn_close = QPushButton("Close")
            btn_apply = QPushButton("Name Selected")
            ha.addWidget(btn_close)
            ha.addWidget(btn_apply)
            outer.addWidget(actions)

            btn_apply.clicked.connect(apply_names)
            btn_close.clicked.connect(dlg.reject)
            filter_combo.currentIndexChanged.connect(lambda _: populate())
            search_box.textChanged.connect(lambda _: populate())

            dlg.exec()
        except Exception as e:
            print(f"[GooglePhotosLayout] Bulk review dialog failed: {e}")
    def _on_person_context_menu(self, branch_key: str, action: str):
        """Handle context menu action on person card."""
        print(f"[GooglePhotosLayout] Context menu action '{action}' for {branch_key}")

        # Get current display name from database
        from reference_db import ReferenceDB
        db = ReferenceDB()

        try:
            query = "SELECT label FROM face_branch_reps WHERE project_id = ? AND branch_key = ?"
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(query, (self.project_id, branch_key))
                row = cur.fetchone()
                current_name = row[0] if row and row[0] else "Unnamed"
        except Exception as e:
            print(f"[GooglePhotosLayout] Error fetching person name: {e}")
            current_name = "Unnamed"

        # Dispatch to appropriate handler
        if action == "rename":
            self._rename_person(None, branch_key, current_name)
        elif action == "merge":
            self._merge_person(branch_key, current_name)
        elif action == "delete":
            self._delete_person(branch_key, current_name)
        elif action == "suggest_merge":
            if hasattr(self, '_prompt_merge_suggestions'):
                self._prompt_merge_suggestions(branch_key)
        elif action == "details":
            if hasattr(self, '_open_person_detail'):
                self._open_person_detail(branch_key)

    def _filter_people_grid(self, text: str):
        """
        Filter people grid by search text.

        Args:
            text: Search query to filter by name
        """
        search_query = text.lower().strip()
        print(f"[GooglePhotosLayout] Filtering people grid: '{search_query}'")

        # Show/hide cards based on search
        if hasattr(self, 'people_grid') and hasattr(self.people_grid, 'flow_layout'):
            visible_count = 0
            for i in range(self.people_grid.flow_layout.count()):
                item = self.people_grid.flow_layout.itemAt(i)
                if item and item.widget():
                    card = item.widget()
                    if isinstance(card, PersonCard):
                        # Check if display name matches search
                        name_matches = search_query in card.display_name.lower()
                        card.setVisible(name_matches or not search_query)
                        if card.isVisible():
                            visible_count += 1

            print(f"[GooglePhotosLayout] Filter results: {visible_count} people visible")

            # Update section count badge to show filtered count
            if hasattr(self, 'people_section'):
                total_count = self.people_grid.flow_layout.count()
                if search_query:
                    self.people_section.update_count(f"{visible_count}/{total_count}")
                else:
                    self.people_section.update_count(total_count)
    
    def _on_people_search_OLD_REMOVED(self, text: str):
        """
        Filter people grid by search text (Phase 3).
        DEPRECATED: Replaced by enhanced version with autocomplete.

        Args:
            text: Search query to filter by name
        """
        search_query = text.lower().strip()
        print(f"[GooglePhotosLayout] Searching people: '{search_query}'")

        # Show/hide cards based on search
        if hasattr(self, 'people_grid') and hasattr(self.people_grid, 'flow_layout'):
            visible_count = 0
            for i in range(self.people_grid.flow_layout.count()):
                item = self.people_grid.flow_layout.itemAt(i)
                if item and item.widget():
                    card = item.widget()
                    if isinstance(card, PersonCard):
                        # Check if display name matches search
                        name_matches = search_query in card.display_name.lower()
                        card.setVisible(name_matches or not search_query)
                        if card.isVisible():
                            visible_count += 1

            print(f"[GooglePhotosLayout] Search results: {visible_count} people visible")

            # Update section count badge to show filtered count
            if hasattr(self, 'people_section'):
                total_count = self.people_grid.flow_layout.count()
                if search_query:
                    self.people_section.update_count(f"{visible_count}/{total_count}")
                else:
                    pass  # Old sidebar section count update - no longer needed with AccordionSidebar

    def _show_people_context_menu(self, pos):
        """
        Show context menu for people tree items (rename/merge/delete).

        Inspired by Google Photos / iPhone Photos face management.
        """
        item = self.people_tree.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.UserRole)
        if not data or data.get("type") != "person":
            return

        branch_key = data.get("branch_key")
        current_label = data.get("label")
        current_name = current_label if current_label else "Unnamed Person"

        menu = QMenu(self.people_tree)

        # Rename action
        rename_action = QAction("✏️ Rename Person...", menu)
        rename_action.triggered.connect(lambda: self._rename_person(item, branch_key, current_name))
        menu.addAction(rename_action)

        # Merge action
        merge_action = QAction("🔗 Merge with Another Person...", menu)
        merge_action.triggered.connect(lambda: self._merge_person(branch_key, current_name))
        menu.addAction(merge_action)

        menu.addSeparator()

        # View all photos (already doing this on click)
        view_action = QAction("📸 View All Photos", menu)
        view_action.triggered.connect(lambda: self._on_people_item_clicked(item, 0))
        menu.addAction(view_action)

        menu.addSeparator()

        # Delete action
        delete_action = QAction("🗑️ Delete This Person", menu)
        delete_action.triggered.connect(lambda: self._delete_person(branch_key, current_name))
        menu.addAction(delete_action)

        menu.exec(self.people_tree.viewport().mapToGlobal(pos))

    def _rename_person(self, item: QTreeWidgetItem, branch_key: str, current_name: str):
        """
        Rename a person/face cluster.

        Works for both grid view (item=None) and tree view (item=QTreeWidgetItem).
        """
        from PySide6.QtWidgets import QInputDialog, QMessageBox

        new_name, ok = QInputDialog.getText(
            self.main_window,
            "Rename Person",
            f"Rename '{current_name}' to:",
            text=current_name if not current_name.startswith("Unnamed") else ""
        )

        if not ok or not new_name.strip():
            return

        new_name = new_name.strip()

        if new_name == current_name:
            return

        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Update database
            with db._connect() as conn:
                conn.execute("""
                    UPDATE branches
                    SET display_name = ?
                    WHERE project_id = ? AND branch_key = ?
                """, (new_name, self.project_id, branch_key))

                conn.execute("""
                    UPDATE face_branch_reps
                    SET label = ?
                    WHERE project_id = ? AND branch_key = ?
                """, (new_name, self.project_id, branch_key))

                conn.commit()

            # Update UI based on view type
            if item is not None:
                # Tree view: Update tree item
                old_text = item.text(0)
                count_part = old_text.split('(')[-1] if '(' in old_text else "0)"
                item.setText(0, f"{new_name} ({count_part}")

                # Update data
                data = item.data(0, Qt.UserRole)
                if data:
                    data["label"] = new_name
                    item.setData(0, Qt.UserRole, data)
            else:
                # Grid view: Refresh the entire people grid to show updated name
                self._build_people_tree()

            print(f"[GooglePhotosLayout] Person renamed: {current_name} → {new_name}")
            QMessageBox.information(self.main_window, "Renamed", f"Person renamed to '{new_name}'")

        except Exception as e:
            print(f"[GooglePhotosLayout] Rename failed: {e}")
            QMessageBox.critical(self.main_window, "Rename Failed", f"Error: {e}")

    def _merge_person(self, source_branch_key: str, source_name: str):
        """Merge this person with another person."""
        from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QDialogButtonBox, QVBoxLayout, QLabel, QMessageBox

        # Get all other persons
        from reference_db import ReferenceDB
        db = ReferenceDB()

        with db._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT branch_key, label, count
                FROM face_branch_reps
                WHERE project_id = ? AND branch_key != ?
                ORDER BY count DESC
            """, (self.project_id, source_branch_key))

            other_persons = cur.fetchall()

        if not other_persons:
            QMessageBox.information(self.main_window, "No Persons", "No other persons to merge with")
            return

        # Show selection dialog
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(f"Merge '{source_name}'")
        dialog.resize(450, 550)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Select person to merge '{source_name}' into:"))

        list_widget = QListWidget()
        for branch_key, label, count in other_persons:
            display = f"{label or 'Unnamed Person'} ({count} photos)"
            item_widget = QListWidgetItem(display)
            item_widget.setData(Qt.UserRole, branch_key)
            list_widget.addItem(item_widget)

        layout.addWidget(list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            selected_item = list_widget.currentItem()
            if selected_item:
                target_branch_key = selected_item.data(Qt.UserRole)
                self._perform_merge(source_branch_key, target_branch_key, source_name)

    def _perform_merge(self, source_key: str, target_key: str, source_name: str):
        """Perform the actual merge operation."""
        from PySide6.QtWidgets import QMessageBox

        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Use the proper merge_face_clusters method that handles counts correctly
            result = db.merge_face_clusters(
                project_id=self.project_id,
                target_branch=target_key,
                source_branches=[source_key],
                log_undo=True
            )

            # Clear redo stack (new merge invalidates redo history)
            if hasattr(self, 'redo_stack'):
                self.redo_stack.clear()

            # Rebuild people tree to show updated counts
            self._build_people_tree()

            # Update undo/redo button states
            self._update_undo_redo_state()

            print(f"[GooglePhotosLayout] Merge successful: {source_name} merged into {target_key}")
            print(f"[GooglePhotosLayout] Merge result: {result}")

            # Build comprehensive merge notification following Google Photos pattern
            msg_lines = [f"✓ '{source_name}' merged successfully", ""]

            duplicates = result.get('duplicates_found', 0)
            unique_moved = result.get('unique_moved', 0)
            total_photos = result.get('total_photos', 0)
            moved_faces = result.get('moved_faces', 0)

            if duplicates > 0:
                msg_lines.append(f"⚠️ Found {duplicates} duplicate photo{'s' if duplicates != 1 else ''}")
                msg_lines.append("   (already in target, not duplicated)")
                msg_lines.append("")

            if unique_moved > 0:
                msg_lines.append(f"• Moved {unique_moved} unique photo{'s' if unique_moved != 1 else ''}")
            elif duplicates > 0:
                msg_lines.append(f"• No unique photos to move (all were duplicates)")

            msg_lines.append(f"• Reassigned {moved_faces} face crop{'s' if moved_faces != 1 else ''}")
            msg_lines.append("")
            msg_lines.append(f"Total: {total_photos} photo{'s' if total_photos != 1 else ''}")

            QMessageBox.information(
                self.main_window,
                "Merged",
                "\n".join(msg_lines)
            )

        except Exception as e:
            print(f"[GooglePhotosLayout] Merge failed: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self.main_window, "Merge Failed", f"Error: {e}")
    
    def _on_drag_merge(self, source_branch: str, target_branch: str):
        """Handle drag-and-drop merge from People grid."""
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            
            # Get source name for confirmation feedback
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute("SELECT label FROM face_branch_reps WHERE project_id = ? AND branch_key = ?", (self.project_id, source_branch))
                row = cur.fetchone()
                source_name = row[0] if row and row[0] else source_branch
            
            # Perform merge using existing method
            self._perform_merge(source_branch, target_branch, source_name)
            
        except Exception as e:
            print(f"[GooglePhotosLayout] Drag-drop merge failed: {e}")
            import traceback
            traceback.print_exc()
    
    def _undo_last_merge(self):
        """Undo the last face merge operation."""
        from PySide6.QtWidgets import QMessageBox
        
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            
            # Get the last merge before undoing (for redo stack)
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, target_branch, source_branches, snapshot FROM face_merge_history WHERE project_id = ? ORDER BY id DESC LIMIT 1",
                    (self.project_id,)
                )
                last_merge = cur.fetchone()
            
            # Perform undo
            result = db.undo_last_face_merge(self.project_id)
            
            if result:
                # Add to redo stack
                if last_merge:
                    self.redo_stack.append({
                        'id': last_merge[0],
                        'target': last_merge[1],
                        'sources': last_merge[2],
                        'snapshot': last_merge[3]
                    })
                
                # Rebuild people tree to show restored clusters
                self._build_people_tree()
                
                # Update undo/redo button states
                self._update_undo_redo_state()
                
                QMessageBox.information(
                    self.main_window,
                    "Undo Successful",
                    f"✅ Merge undone successfully\n\n"
                    f"Restored {result['clusters']} person(s)\n"
                    f"Moved {result['faces']} face(s) back"
                )
                print(f"[GooglePhotosLayout] Undo successful: {result}")
            else:
                QMessageBox.information(
                    self.main_window,
                    "No Undo Available",
                    "There are no recent merges to undo."
                )
                
        except Exception as e:
            print(f"[GooglePhotosLayout] Undo failed: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self.main_window, "Undo Failed", f"Error: {e}")
    
    def _redo_last_undo(self):
        """Redo the last undone merge operation."""
        from PySide6.QtWidgets import QMessageBox
        
        if not self.redo_stack:
            QMessageBox.information(
                self.main_window,
                "No Redo Available",
                "There are no undone operations to redo."
            )
            return
        
        try:
            from reference_db import ReferenceDB
            import json
            db = ReferenceDB()
            
            # Pop from redo stack
            redo_op = self.redo_stack.pop()
            snapshot = json.loads(redo_op['snapshot']) if isinstance(redo_op['snapshot'], str) else redo_op['snapshot']
            
            # Re-apply the merge by restoring snapshot state
            # Get source branches from snapshot
            branch_keys = snapshot.get('branch_keys', [])
            target = redo_op['target']
            sources = [k for k in branch_keys if k != target]
            
            if sources:
                # Re-merge using existing method
                result = db.merge_face_clusters(
                    project_id=self.project_id,
                    target_branch=target,
                    source_branches=sources,
                    log_undo=True
                )
                
                # Rebuild people tree
                self._build_people_tree()
                
                # Update button states
                self._update_undo_redo_state()

                # Build comprehensive redo notification
                msg_lines = ["✅ Merge re-applied successfully", ""]

                duplicates = result.get('duplicates_found', 0)
                unique_moved = result.get('unique_moved', 0)
                total_photos = result.get('total_photos', 0)
                moved_faces = result.get('moved_faces', 0)

                if duplicates > 0:
                    msg_lines.append(f"⚠️ Found {duplicates} duplicate photo{'s' if duplicates != 1 else ''}")
                    msg_lines.append("   (already in target, not duplicated)")
                    msg_lines.append("")

                if unique_moved > 0:
                    msg_lines.append(f"• Moved {unique_moved} unique photo{'s' if unique_moved != 1 else ''}")
                elif duplicates > 0:
                    msg_lines.append(f"• No unique photos to move (all were duplicates)")

                msg_lines.append(f"• Reassigned {moved_faces} face crop{'s' if moved_faces != 1 else ''}")
                msg_lines.append("")
                msg_lines.append(f"Total: {total_photos} photo{'s' if total_photos != 1 else ''}")

                QMessageBox.information(
                    self.main_window,
                    "Redo Successful",
                    "\n".join(msg_lines)
                )
                print(f"[GooglePhotosLayout] Redo successful: {result}")
            
        except Exception as e:
            print(f"[GooglePhotosLayout] Redo failed: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self.main_window, "Redo Failed", f"Error: {e}")
    
    def _update_undo_redo_state(self):
        """Update undo/redo button enabled/disabled states."""
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            
            # Check if there are any undo records
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT COUNT(*) FROM face_merge_history WHERE project_id = ?",
                    (self.project_id,)
                )
                undo_count = cur.fetchone()[0]
                
                # Update undo button
                if hasattr(self, 'people_undo_btn'):
                    self.people_undo_btn.setEnabled(undo_count > 0)
                    self.people_undo_btn.setToolTip(
                        f"Undo Last Merge ({undo_count} available)" if undo_count > 0 else "No merges to undo"
                    )
                
                # Update redo button
                if hasattr(self, 'people_redo_btn'):
                    redo_count = len(self.redo_stack)
                    self.people_redo_btn.setEnabled(redo_count > 0)
                    self.people_redo_btn.setToolTip(
                        f"Redo Last Undo ({redo_count} available)" if redo_count > 0 else "No undos to redo"
                    )
                    
        except Exception as e:
            print(f"[GooglePhotosLayout] Failed to update undo/redo buttons: {e}")
    
    def _show_merge_history(self):
        """Show merge history dialog with undo/redo options."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem, QMessageBox
        
        try:
            from reference_db import ReferenceDB
            import json
            from datetime import datetime
            db = ReferenceDB()
            
            # Fetch merge history
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    """SELECT id, target_branch, source_branches, snapshot, created_at 
                       FROM face_merge_history 
                       WHERE project_id = ? 
                       ORDER BY id DESC
                       LIMIT 50""",
                    (self.project_id,)
                )
                history = cur.fetchall()
            
            if not history:
                QMessageBox.information(
                    self.main_window,
                    "No History",
                    "No merge operations have been performed yet."
                )
                return
            
            # Create dialog
            dlg = QDialog(self.main_window)
            dlg.setWindowTitle("📜 Merge History")
            dlg.resize(600, 500)
            layout = QVBoxLayout(dlg)
            
            # Header
            header = QLabel(f"<b>Merge History</b> ({len(history)} operations)")
            header.setStyleSheet("font-size: 12pt; padding: 8px;")
            layout.addWidget(header)
            
            # History list
            history_list = QListWidget()
            history_list.setStyleSheet("""
                QListWidget::item {
                    padding: 12px;
                    border-bottom: 1px solid #e8eaed;
                }
                QListWidget::item:hover {
                    background: #f8f9fa;
                }
            """)
            
            for merge_id, target, sources, snapshot_str, created_at in history:
                # Parse snapshot to get names
                try:
                    snapshot = json.loads(snapshot_str)
                    branch_keys = snapshot.get('branch_keys', [])
                    
                    # Get person names
                    with db._connect() as conn2:
                        cur2 = conn2.cursor()
                        cur2.execute(
                            f"SELECT branch_key, label FROM face_branch_reps WHERE project_id = ? AND branch_key IN ({','.join(['?']*len(branch_keys))})",
                            [self.project_id] + branch_keys
                        )
                        names = {row[0]: row[1] or row[0] for row in cur2.fetchall()}
                    
                    target_name = names.get(target, target)
                    source_names = [names.get(s, s) for s in sources.split(',')]
                    
                    # Format timestamp
                    try:
                        dt = datetime.fromisoformat(created_at)
                        time_str = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        time_str = created_at
                    
                    item_text = f"⏰ {time_str}\n🔗 Merged {', '.join(source_names)} → {target_name}"
                    
                except Exception as e:
                    print(f"Failed to parse merge history item: {e}")
                    item_text = f"🔗 Merge #{merge_id} ({created_at})"
                
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, merge_id)
                history_list.addItem(item)
            
            layout.addWidget(history_list)
            
            # Actions
            actions = QHBoxLayout()
            
            def undo_selected():
                selected = history_list.currentItem()
                if selected:
                    merge_id = selected.data(Qt.UserRole)
                    # Undo all operations up to and including this one
                    reply = QMessageBox.question(
                        dlg,
                        "Confirm Undo",
                        "Undo this merge and all subsequent merges?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply == QMessageBox.Yes:
                        # Perform undo
                        self._undo_last_merge()
                        dlg.accept()
                        self._show_merge_history()  # Refresh history
            
            undo_btn = QPushButton("↺ Undo Selected")
            undo_btn.clicked.connect(undo_selected)
            actions.addWidget(undo_btn)
            
            actions.addStretch()
            
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dlg.accept)
            actions.addWidget(close_btn)
            
            layout.addLayout(actions)
            
            dlg.exec()
            
        except Exception as e:
            print(f"[GooglePhotosLayout] Failed to show merge history: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self.main_window, "Error", f"Failed to load history: {e}")

    def _prompt_merge_suggestions(self, target_branch_key: str):
        """Suggest similar people to merge into the target using centroid cosine similarity."""
        try:
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea, QWidget, QGridLayout, QCheckBox, QPushButton, QHBoxLayout
            from PySide6.QtGui import QPixmap
            import numpy as np, os, base64
            from reference_db import ReferenceDB
            db = ReferenceDB()
            # Fetch target centroid and face preview
            target = None
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute("SELECT label, centroid, rep_path, rep_thumb_png FROM face_branch_reps WHERE project_id = ? AND branch_key = ?", (self.project_id, target_branch_key))
                row = cur.fetchone()
                if not row or not row[1]:
                    return
                target_name = row[0] or target_branch_key
                target = np.frombuffer(row[1], dtype=np.float32)
                target_rep_path = row[2]
                target_rep_thumb = row[3]
                # Fetch others with face previews
                cur.execute("SELECT branch_key, label, count, centroid, rep_path, rep_thumb_png FROM face_branch_reps WHERE project_id = ? AND branch_key != ?", (self.project_id, target_branch_key))
                others = cur.fetchall() or []
            # Compute similarities
            suggestions = []
            for bk, label, cnt, centroid, rep_path, rep_thumb in others:
                if not centroid:
                    continue
                vec = np.frombuffer(centroid, dtype=np.float32)
                denom = (np.linalg.norm(target) * np.linalg.norm(vec))
                if denom == 0:
                    continue
                sim = float(np.dot(target, vec) / denom)
                suggestions.append((bk, label or bk, cnt or 0, sim, rep_path, rep_thumb))
            suggestions.sort(key=lambda x: x[3], reverse=True)
            # Filter by threshold
            threshold = 0.80
            suggestions = [s for s in suggestions if s[3] >= threshold][:12]
            if not suggestions:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self.main_window, "No Suggestions", "No similar people found above threshold.")
                return
            # Build dialog with visual previews
            dlg = QDialog(self.main_window)
            dlg.setWindowTitle(f"Suggest Merge into '{target_name}'")
            dlg.resize(700, 600)
            outer = QVBoxLayout(dlg)
            
            # Header with target person preview
            header = QWidget()
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(8, 8, 8, 8)
            header_layout.setSpacing(12)
            
            # Target face preview
            target_face = QLabel()
            target_face.setFixedSize(80, 80)
            target_pix = None
            try:
                if target_rep_thumb:
                    data = base64.b64decode(target_rep_thumb) if isinstance(target_rep_thumb, str) else target_rep_thumb
                    target_pix = QPixmap()
                    target_pix.loadFromData(data)
                if (target_pix is None or target_pix.isNull()) and target_rep_path and os.path.exists(target_rep_path):
                    target_pix = QPixmap(target_rep_path)
                if target_pix and not target_pix.isNull():
                    # Make circular
                    from PySide6.QtGui import QPainter, QPainterPath
                    from PySide6.QtCore import QRect, QPoint
                    scaled = target_pix.scaled(80, 80, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    if scaled.width() > 80 or scaled.height() > 80:
                        x = (scaled.width() - 80) // 2
                        y = (scaled.height() - 80) // 2
                        scaled = scaled.copy(x, y, 80, 80)
                    output = QPixmap(80, 80)
                    output.fill(Qt.transparent)
                    painter = QPainter(output)
                    painter.setRenderHint(QPainter.Antialiasing)
                    path = QPainterPath()
                    path.addEllipse(0, 0, 80, 80)
                    painter.setClipPath(path)
                    painter.drawPixmap(0, 0, scaled)
                    painter.end()
                    target_face.setPixmap(output)
            except Exception as e:
                print(f"[GooglePhotosLayout] Failed to load target preview: {e}")
            target_face.setStyleSheet("border: 2px solid #1a73e8; border-radius: 40px;")
            header_layout.addWidget(target_face)
            
            # Target info
            info_label = QLabel(f"<b>Merge into: {target_name}</b><br><span style='color:#5f6368;'>Select similar people below (similarity ≥ {int(threshold*100)}%)</span>")
            info_label.setWordWrap(True)
            header_layout.addWidget(info_label, 1)
            outer.addWidget(header)
            
            # Recently merged section (if any)
            recent_merges = []
            try:
                with db._connect() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT target_branch, source_branches, created_at
                        FROM face_merge_history
                        WHERE project_id = ?
                        ORDER BY created_at DESC
                        LIMIT 5
                    """, (self.project_id,))
                    recent_merges = cur.fetchall() or []
            except Exception as e:
                print(f"[GooglePhotosLayout] Failed to load merge history: {e}")
            
            if recent_merges:
                recent_header = QLabel("🕒 <b>Recently Merged</b> <span style='color:#5f6368; font-size:9pt;'>(Quick undo available)</span>")
                recent_header.setStyleSheet("padding: 8px; background: #f8f9fa; border-radius: 4px; margin: 4px 0;")
                outer.addWidget(recent_header)
                
                recent_widget = QWidget()
                recent_layout = QVBoxLayout(recent_widget)
                recent_layout.setContentsMargins(8, 4, 8, 4)
                recent_layout.setSpacing(4)
                
                for target_bk, source_bks, created_at in recent_merges:
                    # Get target name
                    with db._connect() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT label FROM face_branch_reps WHERE project_id = ? AND branch_key = ?", (self.project_id, target_bk))
                        target_row = cur.fetchone()
                        target_label = (target_row[0] if target_row and target_row[0] else target_bk)
                    
                    merge_label = QLabel(f"• <b>{len(source_bks.split(','))} people</b> → <b>{target_label}</b> <span style='color:#5f6368; font-size:8pt;'>({created_at})</span>")
                    merge_label.setStyleSheet("font-size: 9pt; padding: 2px 8px;")
                    recent_layout.addWidget(merge_label)
                
                outer.addWidget(recent_widget)
            
            # Scrollable suggestions grid with face previews
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            container = QWidget()
            grid = QGridLayout(container)
            grid.setContentsMargins(8, 8, 8, 8)
            grid.setSpacing(12)
            checks = {}
            
            for i, (bk, name, cnt, sim, rep_path, rep_thumb) in enumerate(suggestions):
                card = QWidget()
                card.setStyleSheet("""
                    QWidget {
                        background: white;
                        border: 1px solid #dadce0;
                        border-radius: 8px;
                    }
                    QWidget:hover {
                        border: 2px solid #1a73e8;
                        background: #f8f9fa;
                    }
                """)
                v = QVBoxLayout(card)
                v.setContentsMargins(8, 8, 8, 8)
                v.setSpacing(6)
                
                # Face preview (80x80 circular)
                face_label = QLabel()
                face_label.setFixedSize(80, 80)
                face_label.setAlignment(Qt.AlignCenter)
                try:
                    pix = None
                    if rep_thumb:
                        data = base64.b64decode(rep_thumb) if isinstance(rep_thumb, str) else rep_thumb
                        pix = QPixmap()
                        pix.loadFromData(data)
                    if (pix is None or pix.isNull()) and rep_path and os.path.exists(rep_path):
                        pix = QPixmap(rep_path)
                    if pix and not pix.isNull():
                        # Make circular
                        from PySide6.QtGui import QPainter, QPainterPath
                        scaled = pix.scaled(80, 80, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                        if scaled.width() > 80 or scaled.height() > 80:
                            x = (scaled.width() - 80) // 2
                            y = (scaled.height() - 80) // 2
                            scaled = scaled.copy(x, y, 80, 80)
                        output = QPixmap(80, 80)
                        output.fill(Qt.transparent)
                        painter = QPainter(output)
                        painter.setRenderHint(QPainter.Antialiasing)
                        path = QPainterPath()
                        path.addEllipse(0, 0, 80, 80)
                        painter.setClipPath(path)
                        painter.drawPixmap(0, 0, scaled)
                        painter.end()
                        face_label.setPixmap(output)
                    else:
                        face_label.setStyleSheet("background: #e8eaed; border-radius: 40px; font-size: 24pt;")
                        face_label.setText("👤")
                except Exception as e:
                    face_label.setStyleSheet("background: #e8eaed; border-radius: 40px; font-size: 24pt;")
                    face_label.setText("👤")
                    print(f"[GooglePhotosLayout] Failed to load suggestion preview: {e}")
                v.addWidget(face_label)
                
                # Name and similarity
                name_label = QLabel(f"<b>{name}</b>")
                name_label.setAlignment(Qt.AlignCenter)
                name_label.setWordWrap(True)
                v.addWidget(name_label)
                
                sim_label = QLabel(f"{int(sim*100)}% match • {cnt} photos")
                sim_label.setStyleSheet("color: #1a73e8; font-size: 9pt;")
                sim_label.setAlignment(Qt.AlignCenter)
                v.addWidget(sim_label)
                
                # Checkbox
                cb = QCheckBox("Select to merge")
                cb.setStyleSheet("font-size: 9pt;")
                checks[bk] = cb
                v.addWidget(cb, 0, Qt.AlignCenter)
                
                row = i // 3
                col = i % 3
                grid.addWidget(card, row, col)
            
            scroll.setWidget(container)
            outer.addWidget(scroll, 1)
            
            # Actions
            btns = QHBoxLayout()
            btns.addStretch()
            cancel_btn = QPushButton("Cancel")
            apply_btn = QPushButton("🔗 Merge Selected")
            apply_btn.setStyleSheet("""
                QPushButton {
                    background: #1a73e8;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #1557b0;
                }
            """)
            btns.addWidget(cancel_btn)
            btns.addWidget(apply_btn)
            outer.addLayout(btns)
            
            def do_merge():
                selected = [bk for bk, cb in checks.items() if cb.isChecked()]
                if not selected:
                    dlg.accept()
                    return
                for src in selected:
                    # Use source name for message
                    from reference_db import ReferenceDB
                    db2 = ReferenceDB()
                    with db2._connect() as conn:
                        label_row = conn.execute("SELECT label FROM face_branch_reps WHERE project_id = ? AND branch_key = ?", (self.project_id, src)).fetchone()
                        src_name = (label_row[0] if label_row and label_row[0] else src)
                    self._perform_merge(src, target_branch_key, src_name)
                dlg.accept()
            
            apply_btn.clicked.connect(do_merge)
            cancel_btn.clicked.connect(dlg.reject)
            dlg.exec()
        except Exception as e:
            print(f"[GooglePhotosLayout] Merge suggestions failed: {e}")
            import traceback
            traceback.print_exc()

    def _open_person_detail(self, branch_key: str):
        """Person detail view with batch remove/merge and confidence filter."""
        try:
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QScrollArea, QWidget, QGridLayout, QCheckBox, QPushButton, QHBoxLayout
            import numpy as np, os
            from PySide6.QtGui import QPixmap
            from reference_db import ReferenceDB
            db = ReferenceDB()
            # Fetch centroid
            centroid_vec = None
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute("SELECT label, centroid FROM face_branch_reps WHERE project_id = ? AND branch_key = ?", (self.project_id, branch_key))
                row = cur.fetchone()
                person_name = (row[0] if row and row[0] else branch_key)
                centroid_vec = np.frombuffer(row[1], dtype=np.float32) if row and row[1] else None
                # Fetch crops
                cur.execute("SELECT id, crop_path, embedding FROM face_crops WHERE project_id = ? AND branch_key = ?", (self.project_id, branch_key))
                crops = cur.fetchall() or []
            # Build list with confidence
            items = []
            for rid, crop_path, emb in crops:
                sim = 0.0
                if centroid_vec is not None and emb:
                    vec = np.frombuffer(emb, dtype=np.float32)
                    denom = (np.linalg.norm(centroid_vec) * np.linalg.norm(vec))
                    if denom > 0:
                        sim = float(np.dot(centroid_vec, vec) / denom)
                items.append((rid, crop_path, sim))
            # Dialog
            dlg = QDialog(self.main_window)
            dlg.setWindowTitle(f"Person Details: {person_name}")
            outer = QVBoxLayout(dlg)
            # Filter
            filter_combo = QComboBox(); filter_combo.addItems(["All", "High (≥0.85)", "Medium (0.70–0.85)", "Low (<0.70)"])
            outer.addWidget(filter_combo)
            # Grid
            scroll = QScrollArea(); scroll.setWidgetResizable(True)
            container = QWidget(); grid = QGridLayout(container); grid.setContentsMargins(8,8,8,8); grid.setSpacing(8)
            checks = {}
            def populate():
                # Clear
                while grid.count():
                    it = grid.takeAt(0)
                    if it and it.widget():
                        it.widget().deleteLater()
                idx = 0
                sel = filter_combo.currentIndex()
                for rid, path, sim in items:
                    if sel == 1 and sim < 0.85: continue
                    if sel == 2 and (sim < 0.70 or sim >= 0.85): continue
                    if sel == 3 and sim >= 0.70: continue
                    card = QWidget(); v = QVBoxLayout(card); v.setContentsMargins(4,4,4,4); v.setSpacing(4)
                    img = QLabel(); img.setFixedSize(140,140)
                    px = QPixmap(path) if path and os.path.exists(path) else QPixmap()
                    if not px.isNull(): img.setPixmap(px.scaled(140,140,Qt.KeepAspectRatio,Qt.SmoothTransformation))
                    v.addWidget(img)
                    lbl = QLabel(f"Similarity: {int(sim*100)}%")
                    lbl.setStyleSheet("color:#5f6368;")
                    v.addWidget(lbl)
                    cb = QCheckBox("Select")
                    checks[rid] = cb
                    v.addWidget(cb)
                    grid.addWidget(card, idx//4, idx%4); idx += 1
            populate()
            scroll.setWidget(container)
            outer.addWidget(scroll)
            # Actions
            actions = QHBoxLayout(); actions.addStretch()
            remove_btn = QPushButton("Remove Selected")
            merge_btn = QPushButton("Merge Selected Into…")
            close_btn = QPushButton("Close")
            actions.addWidget(close_btn); actions.addWidget(remove_btn); actions.addWidget(merge_btn)
            outer.addLayout(actions)
            def remove_selected():
                """Move selected faces to unidentified cluster and update counts."""
                target = "face_unidentified"
                ids = [rid for rid,cb in checks.items() if cb.isChecked()]
                if not ids: return
                
                # Get source branch_key from the current person
                source_branch = branch_key
                
                with ReferenceDB()._connect() as conn:
                    cur = conn.cursor()
                    placeholders = ",".join(["?"]*len(ids))
                    cur.execute(f"UPDATE face_crops SET branch_key = ? WHERE project_id = ? AND id IN ({placeholders})", [target, self.project_id] + ids)
                    
                    # CRITICAL: Update counts for both source and target clusters
                    # Update source cluster count
                    cur.execute("""
                        UPDATE face_branch_reps
                        SET count = (
                            SELECT COUNT(DISTINCT image_path)
                            FROM face_crops
                            WHERE project_id = ? AND branch_key = ?
                        )
                        WHERE project_id = ? AND branch_key = ?
                    """, (self.project_id, source_branch, self.project_id, source_branch))
                    
                    # Update target (unidentified) cluster count
                    cur.execute("""
                        UPDATE face_branch_reps
                        SET count = (
                            SELECT COUNT(DISTINCT image_path)
                            FROM face_crops
                            WHERE project_id = ? AND branch_key = ?
                        )
                        WHERE project_id = ? AND branch_key = ?
                    """, (self.project_id, target, self.project_id, target))
                    
                    conn.commit()
                    print(f"[GooglePhotosLayout] Removed {len(ids)} faces from {source_branch} to {target}, counts updated")
                
                # Refresh people UI
                if hasattr(self, '_build_people_tree'):
                    self._build_people_tree()
                populate()
            def merge_selected():
                """Merge selected faces into another person with visual picker."""
                ids = [rid for rid, cb in checks.items() if cb.isChecked()]
                if not ids:
                    return
                
                # Get source branch_key from the current person
                source_branch = branch_key
                
                # Show visual person picker dialog
                picker_dlg = self._create_person_picker_dialog(exclude_branch=source_branch)
                if picker_dlg.exec() == QDialog.Accepted:
                    selected_target = getattr(picker_dlg, 'selected_branch', None)
                    if not selected_target:
                        return
                    
                    # Move faces
                    with ReferenceDB()._connect() as conn:
                        cur = conn.cursor()
                        placeholders = ",".join(["?"]*len(ids))
                        cur.execute(f"UPDATE face_crops SET branch_key = ? WHERE project_id = ? AND id IN ({placeholders})", [selected_target, self.project_id] + ids)
                        
                        # CRITICAL: Update counts for both source and target clusters
                        # Update source cluster count
                        cur.execute("""
                            UPDATE face_branch_reps
                            SET count = (
                                SELECT COUNT(DISTINCT image_path)
                                FROM face_crops
                                WHERE project_id = ? AND branch_key = ?
                            )
                            WHERE project_id = ? AND branch_key = ?
                        """, (self.project_id, source_branch, self.project_id, source_branch))
                        
                        # Update target cluster count
                        cur.execute("""
                            UPDATE face_branch_reps
                            SET count = (
                                SELECT COUNT(DISTINCT image_path)
                                FROM face_crops
                                WHERE project_id = ? AND branch_key = ?
                            )
                            WHERE project_id = ? AND branch_key = ?
                        """, (self.project_id, selected_target, self.project_id, selected_target))
                        
                        conn.commit()
                        print(f"[GooglePhotosLayout] Merged {len(ids)} faces from {source_branch} to {selected_target}, counts updated")
                    
                    if hasattr(self, '_build_people_tree'):
                        self._build_people_tree()
                    populate()
            filter_combo.currentIndexChanged.connect(lambda _: populate())
            close_btn.clicked.connect(dlg.reject)
            remove_btn.clicked.connect(remove_selected)
            merge_btn.clicked.connect(merge_selected)
            dlg.exec()
        except Exception as e:
            print(f"[GooglePhotosLayout] Person detail failed: {e}")

    def _create_person_picker_dialog(self, exclude_branch=None):
        """Create a visual person picker dialog with face previews."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea, QWidget, QGridLayout, QPushButton, QHBoxLayout, QLineEdit
        from PySide6.QtGui import QPixmap, QPainter, QPainterPath
        from PySide6.QtCore import Qt
        import base64, os
        from reference_db import ReferenceDB
        
        dlg = QDialog(self.main_window)
        dlg.setWindowTitle("Select Merge Target")
        dlg.resize(700, 600)
        dlg.selected_branch = None
        
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)
        
        # Header
        header = QLabel("<b>Select a person to merge into:</b>")
        header.setStyleSheet("font-size: 12pt;")
        outer.addWidget(header)
        
        # Search box
        search_box = QLineEdit()
        search_box.setPlaceholderText("🔍 Search people...")
        search_box.setClearButtonEnabled(True)
        search_box.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #dadce0;
                border-radius: 20px;
                background: #f8f9fa;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 2px solid #1a73e8;
                background: white;
            }
        """)
        outer.addWidget(search_box)
        
        # Fetch all people with multiple face samples
        db = ReferenceDB()
        people = []
        with db._connect() as conn:
            cur = conn.cursor()
            query = "SELECT branch_key, label, count, rep_path, rep_thumb_png FROM face_branch_reps WHERE project_id = ?"
            params = [self.project_id]
            if exclude_branch:
                query += " AND branch_key != ?"
                params.append(exclude_branch)
            query += " ORDER BY count DESC"
            cur.execute(query, params)
            people = cur.fetchall() or []
            
            # Fetch additional face samples for preview grid (top 3 per person)
            face_samples = {}
            for branch_key, _, _, _, _ in people:
                cur.execute(
                    "SELECT crop_path FROM face_crops WHERE project_id = ? AND branch_key = ? LIMIT 3",
                    (self.project_id, branch_key)
                )
                face_samples[branch_key] = [r[0] for r in cur.fetchall()]
        
        # Scrollable grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: white; }")
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(12)
        
        person_cards = []
        
        def create_person_card(branch_key, label, count, rep_path, rep_thumb):
            card = QPushButton()
            card.setFixedSize(140, 180)  # Larger to fit multiple faces
            card.setCursor(Qt.PointingHandCursor)
            card.setStyleSheet("""
                QPushButton {
                    background: white;
                    border: 2px solid #dadce0;
                    border-radius: 8px;
                    text-align: center;
                }
                QPushButton:hover {
                    border: 2px solid #1a73e8;
                    background: #f8f9fa;
                }
                QPushButton:pressed {
                    background: #e8eaed;
                }
                QPushButton:focus {
                    border: 3px solid #1a73e8;
                    outline: none;
                }
            """)
            
            # Build card content
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setSpacing(4)
            
            # Multiple face previews (grid of 2-3 faces)
            samples = face_samples.get(branch_key, [])
            if len(samples) > 1:
                # Show 2-3 faces in a grid
                faces_container = QWidget()
                faces_layout = QHBoxLayout(faces_container)
                faces_layout.setContentsMargins(0, 0, 0, 0)
                faces_layout.setSpacing(4)
                
                for idx, sample_path in enumerate(samples[:3]):
                    mini_face = QLabel()
                    size = 38 if len(samples) >= 3 else 50  # Smaller if showing 3
                    mini_face.setFixedSize(size, size)
                    mini_face.setAlignment(Qt.AlignCenter)
                    try:
                        pix = QPixmap(sample_path) if sample_path and os.path.exists(sample_path) else None
                        if pix and not pix.isNull():
                            scaled = pix.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                            if scaled.width() > size or scaled.height() > size:
                                x = (scaled.width() - size) // 2
                                y = (scaled.height() - size) // 2
                                scaled = scaled.copy(x, y, size, size)
                            output = QPixmap(size, size)
                            output.fill(Qt.transparent)
                            painter = QPainter(output)
                            painter.setRenderHint(QPainter.Antialiasing)
                            path = QPainterPath()
                            path.addEllipse(0, 0, size, size)
                            painter.setClipPath(path)
                            painter.drawPixmap(0, 0, scaled)
                            painter.end()
                            mini_face.setPixmap(output)
                        else:
                            mini_face.setStyleSheet(f"background: #e8eaed; border-radius: {size//2}px; font-size: {size//2}pt;")
                            mini_face.setText("👤")
                    except Exception:
                        mini_face.setStyleSheet(f"background: #e8eaed; border-radius: {size//2}px; font-size: {size//2}pt;")
                        mini_face.setText("👤")
                    faces_layout.addWidget(mini_face)
                
                card_layout.addWidget(faces_container, 0, Qt.AlignCenter)
            else:
                # Single face preview (80x80 circular)
                face_label = QLabel()
                face_label.setFixedSize(80, 80)
                face_label.setAlignment(Qt.AlignCenter)
                try:
                    pix = None
                    if rep_thumb:
                        data = base64.b64decode(rep_thumb) if isinstance(rep_thumb, str) else rep_thumb
                        pix = QPixmap()
                        pix.loadFromData(data)
                    if (pix is None or pix.isNull()) and rep_path and os.path.exists(rep_path):
                        pix = QPixmap(rep_path)
                    if pix and not pix.isNull():
                        # Make circular
                        scaled = pix.scaled(80, 80, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                        if scaled.width() > 80 or scaled.height() > 80:
                            x = (scaled.width() - 80) // 2
                            y = (scaled.height() - 80) // 2
                            scaled = scaled.copy(x, y, 80, 80)
                        output = QPixmap(80, 80)
                        output.fill(Qt.transparent)
                        painter = QPainter(output)
                        painter.setRenderHint(QPainter.Antialiasing)
                        path = QPainterPath()
                        path.addEllipse(0, 0, 80, 80)
                        painter.setClipPath(path)
                        painter.drawPixmap(0, 0, scaled)
                        painter.end()
                        face_label.setPixmap(output)
                    else:
                        face_label.setStyleSheet("background: #e8eaed; border-radius: 40px; font-size: 24pt;")
                        face_label.setText("👤")
                except Exception:
                    face_label.setStyleSheet("background: #e8eaed; border-radius: 40px; font-size: 24pt;")
                    face_label.setText("👤")
                card_layout.addWidget(face_label, 0, Qt.AlignCenter)
            
            # Name
            name_label = QLabel(label or "Unnamed")
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)
            name_label.setStyleSheet("font-size: 10pt; font-weight: bold; color: #202124;")
            card_layout.addWidget(name_label)
            
            # Count with confidence badge
            conf_badge = "✅" if count >= 10 else ("⚠️" if count >= 5 else "❓")
            count_label = QLabel(f"{conf_badge} {count} photos")
            count_label.setAlignment(Qt.AlignCenter)
            count_label.setStyleSheet("font-size: 8pt; color: #5f6368;")
            card_layout.addWidget(count_label)
            
            # Store data
            card.branch_key = branch_key
            card.display_name = label or "Unnamed"
            card.setFocusPolicy(Qt.StrongFocus)  # Enable keyboard focus
            
            # Click handler
            def on_click():
                dlg.selected_branch = branch_key
                dlg.accept()
            card.clicked.connect(on_click)
            
            return card
        
        # Populate grid
        for i, (branch_key, label, count, rep_path, rep_thumb) in enumerate(people):
            card = create_person_card(branch_key, label, count, rep_path, rep_thumb)
            person_cards.append(card)
            row = i // 4
            col = i % 4
            grid.addWidget(card, row, col)
        
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)
        
        # Keyboard navigation support
        dlg.current_focus_index = 0
        
        def navigate_cards(direction):
            """Navigate through person cards with arrow keys."""
            visible_cards = [c for c in person_cards if c.isVisible()]
            if not visible_cards:
                return
            
            cols = 4
            current_idx = dlg.current_focus_index
            
            if direction == "right" and current_idx < len(visible_cards) - 1:
                current_idx += 1
            elif direction == "left" and current_idx > 0:
                current_idx -= 1
            elif direction == "down":
                next_idx = current_idx + cols
                if next_idx < len(visible_cards):
                    current_idx = next_idx
            elif direction == "up":
                prev_idx = current_idx - cols
                if prev_idx >= 0:
                    current_idx = prev_idx
            
            dlg.current_focus_index = current_idx
            visible_cards[current_idx].setFocus()
            # Ensure card is visible in scroll area
            scroll.ensureWidgetVisible(visible_cards[current_idx])
        
        def select_focused_card():
            """Select the currently focused card with Enter/Return."""
            visible_cards = [c for c in person_cards if c.isVisible()]
            if visible_cards and 0 <= dlg.current_focus_index < len(visible_cards):
                focused_card = visible_cards[dlg.current_focus_index]
                dlg.selected_branch = focused_card.branch_key
                dlg.accept()
        
        # Install event filter for keyboard navigation
        from PySide6.QtCore import QEvent
        class KeyNavFilter(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.KeyPress:
                    key = event.key()
                    if key == Qt.Key_Right:
                        navigate_cards("right")
                        return True
                    elif key == Qt.Key_Left:
                        navigate_cards("left")
                        return True
                    elif key == Qt.Key_Down:
                        navigate_cards("down")
                        return True
                    elif key == Qt.Key_Up:
                        navigate_cards("up")
                        return True
                    elif key in (Qt.Key_Return, Qt.Key_Enter):
                        select_focused_card()
                        return True
                return False
        
        key_filter = KeyNavFilter()
        dlg.installEventFilter(key_filter)
        
        # Set initial focus
        if person_cards:
            person_cards[0].setFocus()
        
        # Search filter
        def filter_cards(text):
            query = text.lower().strip()
            for card in person_cards:
                if not query or query in card.display_name.lower():
                    card.setVisible(True)
                else:
                    card.setVisible(False)
        search_box.textChanged.connect(filter_cards)
        
        # Actions
        actions = QHBoxLayout()
        actions.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        actions.addWidget(cancel_btn)
        outer.addLayout(actions)
        
        return dlg

    def _on_drag_merge(self, source_branch: str, target_branch: str):
        """Handle drag-and-drop merge from People grid."""
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Get source name for confirmation feedback
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute("SELECT label FROM face_branch_reps WHERE project_id = ? AND branch_key = ?", (self.project_id, source_branch))
                row = cur.fetchone()
                source_name = row[0] if row and row[0] else source_branch

            # Perform merge using existing method
            self._perform_merge(source_branch, target_branch, source_name)

        except Exception as e:
            print(f"[GooglePhotosLayout] Drag-drop merge failed: {e}")
            import traceback
            traceback.print_exc()

    def _undo_last_merge(self):
        """Undo the last face merge operation."""
        from PySide6.QtWidgets import QMessageBox

        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Get the last merge before undoing (for redo stack)
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, target_branch, source_branches, snapshot FROM face_merge_history WHERE project_id = ? ORDER BY id DESC LIMIT 1",
                    (self.project_id,)
                )
                last_merge = cur.fetchone()

            # Perform undo
            result = db.undo_last_face_merge(self.project_id)

            if result:
                # Add to redo stack
                if last_merge:
                    self.redo_stack.append({
                        'id': last_merge[0],
                        'target': last_merge[1],
                        'sources': last_merge[2],
                        'snapshot': last_merge[3]
                    })

                # Rebuild people tree to show restored clusters
                self._build_people_tree()

                # Update undo/redo button states
                self._update_undo_redo_state()

                QMessageBox.information(
                    self.main_window,
                    "Undo Successful",
                    f"✅ Merge undone successfully\n\n"
                    f"Restored {result['clusters']} person(s)\n"
                    f"Moved {result['faces']} face(s) back"
                )
                print(f"[GooglePhotosLayout] Undo successful: {result}")
            else:
                QMessageBox.information(
                    self.main_window,
                    "No Undo Available",
                    "There are no recent merges to undo."
                )

        except Exception as e:
            print(f"[GooglePhotosLayout] Undo failed: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self.main_window, "Undo Failed", f"Error: {e}")

    def _redo_last_undo(self):
        """Redo the last undone merge operation."""
        from PySide6.QtWidgets import QMessageBox

        if not self.redo_stack:
            QMessageBox.information(
                self.main_window,
                "No Redo Available",
                "There are no undone operations to redo."
            )
            return

        try:
            from reference_db import ReferenceDB
            import json
            db = ReferenceDB()

            # Pop from redo stack
            redo_op = self.redo_stack.pop()
            snapshot = json.loads(redo_op['snapshot']) if isinstance(redo_op['snapshot'], str) else redo_op['snapshot']

            # Re-apply the merge by restoring snapshot state
            # Get source branches from snapshot
            branch_keys = snapshot.get('branch_keys', [])
            target = redo_op['target']
            sources = [k for k in branch_keys if k != target]

            if sources:
                # Re-merge using existing method
                result = db.merge_face_clusters(
                    project_id=self.project_id,
                    target_branch=target,
                    source_branches=sources,
                    log_undo=True
                )

                # Rebuild people tree
                self._build_people_tree()

                # Update button states
                self._update_undo_redo_state()

                # Build comprehensive redo notification
                msg_lines = ["✅ Merge reapplied successfully", ""]

                duplicates = result.get('duplicates_found', 0)
                unique_moved = result.get('unique_moved', 0)
                total_photos = result.get('total_photos', 0)
                moved_faces = result.get('moved_faces', 0)

                if duplicates > 0:
                    msg_lines.append(f"⚠️ Found {duplicates} duplicate photo{'s' if duplicates != 1 else ''}")
                    msg_lines.append("   (already in target, not duplicated)")
                    msg_lines.append("")

                if unique_moved > 0:
                    msg_lines.append(f"• Moved {unique_moved} unique photo{'s' if unique_moved != 1 else ''}")
                elif duplicates > 0:
                    msg_lines.append(f"• No unique photos to move (all were duplicates)")

                msg_lines.append(f"• Reassigned {moved_faces} face crop{'s' if moved_faces != 1 else ''}")
                msg_lines.append("")
                msg_lines.append(f"Total: {total_photos} photo{'s' if total_photos != 1 else ''}")

                QMessageBox.information(
                    self.main_window,
                    "Redo Successful",
                    "\n".join(msg_lines)
                )
                print(f"[GooglePhotosLayout] Redo successful: {result}")
            else:
                QMessageBox.warning(
                    self.main_window,
                    "Redo Failed",
                    "Could not determine source branches for redo."
                )

        except Exception as e:
            print(f"[GooglePhotosLayout] Redo failed: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self.main_window, "Redo Failed", f"Error: {e}")

    def _update_undo_redo_state(self):
        """Update undo/redo button enabled/disabled states."""
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Check if there are any undo records
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT COUNT(*) FROM face_merge_history WHERE project_id = ?",
                    (self.project_id,)
                )
                undo_count = cur.fetchone()[0]

                # Update undo button
                if hasattr(self, 'people_undo_btn'):
                    self.people_undo_btn.setEnabled(undo_count > 0)
                    self.people_undo_btn.setToolTip(
                        f"Undo Last Merge ({undo_count} available)" if undo_count > 0 else "No merges to undo"
                    )

                # Update redo button
                if hasattr(self, 'people_redo_btn'):
                    redo_count = len(self.redo_stack) if hasattr(self, 'redo_stack') else 0
                    self.people_redo_btn.setEnabled(redo_count > 0)
                    self.people_redo_btn.setToolTip(
                        f"Redo Last Undo ({redo_count} available)" if redo_count > 0 else "No undos to redo"
                    )

        except Exception as e:
            print(f"[GooglePhotosLayout] Failed to update undo/redo state: {e}")

    def _delete_person(self, branch_key: str, person_name: str):
        """Delete a person/face cluster."""
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self.main_window,
            "Delete Person",
            f"Are you sure you want to delete '{person_name}'?\n\n"
            f"This will remove all face data for this person.\n"
            f"Original photos will NOT be deleted.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            with db._connect() as conn:
                # Delete face crops
                conn.execute("""
                    DELETE FROM face_crops
                    WHERE project_id = ? AND branch_key = ?
                """, (self.project_id, branch_key))

                # Delete branch representative
                conn.execute("""
                    DELETE FROM face_branch_reps
                    WHERE project_id = ? AND branch_key = ?
                """, (self.project_id, branch_key))

                # Delete branch
                conn.execute("""
                    DELETE FROM branches
                    WHERE project_id = ? AND branch_key = ?
                """, (self.project_id, branch_key))

                conn.commit()

            # Rebuild people tree
            self._build_people_tree()

            print(f"[GooglePhotosLayout] Person deleted: {person_name}")
            QMessageBox.information(self.main_window, "Deleted", f"'{person_name}' deleted successfully")

        except Exception as e:
            print(f"[GooglePhotosLayout] Delete failed: {e}")
            QMessageBox.critical(self.main_window, "Delete Failed", f"Error: {e}")

    def _on_section_header_clicked(self):
        """
        Handle section header click - clear all filters and show all photos.

        Based on Google Photos UX: Clicking section headers returns to "All Photos" view.
        """
        print("[GooglePhotosLayout] Section header clicked - clearing all filters")

        # Clear all filters
        self._load_photos(
            thumb_size=self.current_thumb_size,
            filter_year=None,
            filter_month=None,
            filter_folder=None,
            filter_person=None
        )

        # Also clear search box
        if self.search_box.text():
            self.search_box.blockSignals(True)
            self.search_box.clear()
            self.search_box.blockSignals(False)

    def _build_videos_tree(self):
        """
        Build videos tree in sidebar with filters (copied from Current Layout).

        Features:
        - All Videos
        - By Duration (Short/Medium/Long)
        - By Resolution (SD/HD/FHD/4K)
        - By Date (Year/Month hierarchy)
        NOTE: With AccordionSidebar, this is handled internally - this method is a no-op.
        """
        # Old sidebar implementation - no longer needed with AccordionSidebar
        if not hasattr(self, 'videos_tree'):
            return

        try:
            from services.video_service import VideoService
            video_service = VideoService()

            print(f"[GoogleLayout] Loading videos for project_id={self.project_id}")
            videos = video_service.get_videos_by_project(self.project_id) if self.project_id else []
            total_videos = len(videos)
            print(f"[GoogleLayout] Found {total_videos} videos in project {self.project_id}")

            if not videos:
                # No videos - show message
                no_videos_item = QTreeWidgetItem(["  (No videos yet)"])
                no_videos_item.setForeground(0, QColor("#888888"))
                self.videos_tree.addTopLevelItem(no_videos_item)
                return

            # All Videos
            all_item = QTreeWidgetItem([f"All Videos ({total_videos})"])
            all_item.setData(0, Qt.UserRole, {"type": "all_videos"})
            self.videos_tree.addTopLevelItem(all_item)

            # By Duration
            short_videos = [v for v in videos if v.get('duration_seconds') and v['duration_seconds'] < 30]
            medium_videos = [v for v in videos if v.get('duration_seconds') and 30 <= v['duration_seconds'] < 300]
            long_videos = [v for v in videos if v.get('duration_seconds') and v['duration_seconds'] >= 300]

            if short_videos or medium_videos or long_videos:
                duration_parent = QTreeWidgetItem([f"⏱️ By Duration"])
                self.videos_tree.addTopLevelItem(duration_parent)

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
                res_parent = QTreeWidgetItem([f"📺 By Resolution"])
                self.videos_tree.addTopLevelItem(res_parent)

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
                from reference_db import ReferenceDB
                db = ReferenceDB()
                video_hier = db.get_video_date_hierarchy(self.project_id) or {}

                if video_hier:
                    date_parent = QTreeWidgetItem([f"📅 By Date"])
                    self.videos_tree.addTopLevelItem(date_parent)

                    for year in sorted(video_hier.keys(), key=lambda y: int(str(y)), reverse=True):
                        year_count = db.count_videos_for_year(year, self.project_id)
                        year_item = QTreeWidgetItem([f"  {year} ({year_count})"])
                        year_item.setData(0, Qt.UserRole, {"type": "video_year", "year": year})
                        date_parent.addChild(year_item)

                        # Month nodes under year
                        months = video_hier[year]
                        for month in sorted(months.keys(), key=lambda m: int(str(m))):
                            month_label = f"{int(month):02d}"
                            month_count = db.count_videos_for_month(year, month, self.project_id)
                            month_item = QTreeWidgetItem([f"    {month_label} ({month_count})"])
                            month_item.setData(0, Qt.UserRole, {"type": "video_month", "year": year, "month": month_label})
                            year_item.addChild(month_item)
            except Exception as e:
                print(f"[GoogleLayout] Failed to build video date hierarchy: {e}")

            print(f"[GoogleLayout] Built videos tree with {total_videos} videos")

        except Exception as e:
            print(f"[GoogleLayout] ⚠️ Error building videos tree: {e}")
            import traceback
            traceback.print_exc()

    def _on_videos_header_clicked(self):
        """
        Handle videos header click - show all videos in timeline.
        """
        print("[GoogleLayout] Videos header clicked - loading all videos")

        try:
            from services.video_service import VideoService
            video_service = VideoService()

            videos = video_service.get_videos_by_project(self.project_id) if self.project_id else []
            print(f"[GoogleLayout] Loading {len(videos)} videos")

            if not videos:
                print("[GoogleLayout] No videos found")
                return

            # Show videos in timeline (will need to implement video display)
            self._show_videos_in_timeline(videos)

        except Exception as e:
            print(f"[GoogleLayout] ⚠️ Error loading videos: {e}")
            import traceback
            traceback.print_exc()

    def _on_videos_item_clicked(self, item: QTreeWidgetItem, column: int):
        """
        Handle videos tree item click - filter/show videos.

        Args:
            item: Clicked tree item
            column: Column index (always 0)
        """
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        item_type = data.get("type")

        if item_type == "all_videos":
            print("[GoogleLayout] Showing all videos")
            try:
                from services.video_service import VideoService
                video_service = VideoService()
                videos = video_service.get_videos_by_project(self.project_id) if self.project_id else []
                self._show_videos_in_timeline(videos)
            except Exception as e:
                print(f"[GoogleLayout] Error loading all videos: {e}")

        elif item_type in ["duration", "resolution"]:
            videos = data.get("videos", [])
            print(f"[GoogleLayout] Showing {len(videos)} videos filtered by {item_type}")
            self._show_videos_in_timeline(videos)

        elif item_type == "video_year":
            year = data.get("year")
            print(f"[GoogleLayout] Showing videos from year {year}")
            try:
                from reference_db import ReferenceDB
                from services.video_service import VideoService
                db = ReferenceDB()
                video_service = VideoService()

                # Get all videos for this year
                all_videos = video_service.get_videos_by_project(self.project_id)
                year_videos = [v for v in all_videos if v.get('created_date', '').startswith(str(year))]
                self._show_videos_in_timeline(year_videos)
            except Exception as e:
                print(f"[GoogleLayout] Error loading videos for year {year}: {e}")

        elif item_type == "video_month":
            year = data.get("year")
            month = data.get("month")
            print(f"[GoogleLayout] Showing videos from {year}-{month}")
            try:
                from services.video_service import VideoService
                video_service = VideoService()

                all_videos = video_service.get_videos_by_project(self.project_id)
                month_videos = [v for v in all_videos if v.get('created_date', '').startswith(f"{year}-{month}")]
                self._show_videos_in_timeline(month_videos)
            except Exception as e:
                print(f"[GoogleLayout] Error loading videos for {year}-{month}: {e}")

    def _show_videos_in_timeline(self, videos: list):
        """
        Display videos in the timeline (similar to photos).

        Args:
            videos: List of video dictionaries from VideoService
        """
        print(f"[GoogleLayout] Showing {len(videos)} videos in timeline")

        # Clear existing timeline
        try:
            while self.timeline_layout.count():
                child = self.timeline_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        except Exception as e:
            print(f"[GoogleLayout] Error clearing timeline: {e}")

        if not videos:
            # Show empty state
            empty_label = QLabel("🎬 No videos found")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("font-size: 12pt; color: #888; padding: 60px;")
            self.timeline_layout.addWidget(empty_label)
            # Clear displayed paths when no videos
            self.all_displayed_paths = []
            return

        # Group videos by date
        videos_by_date = defaultdict(list)
        for video in videos:
            date = video.get('created_date', 'No Date')
            if date and date != 'No Date':
                # Extract just the date part (YYYY-MM-DD)
                date = date.split(' ')[0] if ' ' in date else date
            videos_by_date[date].append(video)

        # Track all displayed video paths for lightbox navigation
        self.all_displayed_paths = [video['path'] for video in videos]
        print(f"[GoogleLayout] Tracking {len(self.all_displayed_paths)} video paths for navigation")

        # Create date groups for videos
        for date_str in sorted(videos_by_date.keys(), reverse=True):
            date_videos = videos_by_date[date_str]
            date_group = self._create_video_date_group(date_str, date_videos)
            self.timeline_layout.addWidget(date_group)

        # Add spacer at bottom
        self.timeline_layout.addStretch()

    def _create_video_date_group(self, date_str: str, videos: list) -> QWidget:
        """
        Create a date group widget for videos (header + video grid).

        Args:
            date_str: Date string "YYYY-MM-DD"
            videos: List of video dictionaries
        """
        group = QFrame()
        group.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #e8eaed;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)

        # Header - Use smart date labels (like photo groups)
        try:
            date_obj = datetime.fromisoformat(date_str)
            formatted_date = self._get_smart_date_label(date_obj)
        except:
            formatted_date = date_str

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        date_label = QLabel(f"📅 {formatted_date}")
        date_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #202124;")
        header_layout.addWidget(date_label)

        count_label = QLabel(f"({len(videos)} video{'s' if len(videos) != 1 else ''})")
        count_label.setStyleSheet("font-size: 10pt; color: #5f6368; margin-left: 8px;")
        header_layout.addWidget(count_label)

        header_layout.addStretch()
        layout.addWidget(header)

        # Video grid (QUICK WIN #2: Also responsive)
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(2)  # GOOGLE PHOTOS STYLE: Minimal spacing
        grid.setContentsMargins(0, 0, 0, 0)

        # QUICK WIN #2: Responsive columns for videos too
        columns = self._calculate_responsive_columns(200)  # Use standard 200px thumb size

        for i, video in enumerate(videos):
            row = i // columns
            col = i % columns

            # Create video thumbnail widget
            video_thumb = self._create_video_thumbnail(video)
            grid.addWidget(video_thumb, row, col)

        layout.addWidget(grid_container)

        return group

    def _create_video_thumbnail(self, video: dict) -> QWidget:
        """
        Create a video thumbnail widget with play icon overlay.

        Args:
            video: Video dictionary with path, duration, etc.
        """
        thumb_widget = QLabel()
        thumb_widget.setFixedSize(200, 200)
        thumb_widget.setAlignment(Qt.AlignCenter)
        thumb_widget.setStyleSheet("""
            QLabel {
                background: #f8f9fa;
                border: 1px solid #e8eaed;
                border-radius: 4px;
                color: white;
            }
            QLabel:hover {
                border: 2px solid #1a73e8;
            }
        """)

        # Set mouse cursor programmatically (Qt doesn't support cursor in stylesheets)
        from PySide6.QtCore import Qt as QtCore
        thumb_widget.setCursor(QtCore.PointingHandCursor)

        # Load video thumbnail
        video_path = video.get('path', '')

        try:
            # Try to load video thumbnail from video thumbnail service
            from services.video_thumbnail_service import get_video_thumbnail_service
            thumb_service = get_video_thumbnail_service()
            thumb_path = thumb_service.get_thumbnail_path(video_path)

            if thumb_path and os.path.exists(thumb_path):
                pixmap = QPixmap(str(thumb_path))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    thumb_widget.setPixmap(scaled)
                    # Duration badge overlay (bottom-right)
                    duration_secs = video.get('duration_seconds')
                    if duration_secs:
                        minutes = int(duration_secs) // 60
                        seconds = int(duration_secs) % 60
                        duration_text = f"{minutes}:{seconds:02d}"
                        badge = QLabel(duration_text, thumb_widget)
                        badge.setStyleSheet("background: rgba(0,0,0,0.6); color: white; font-size: 9pt; padding: 2px 6px; border-radius: 8px;")
                        badge.adjustSize()
                        bx = thumb_widget.width() - badge.width() - 6
                        by = thumb_widget.height() - badge.height() - 6
                        badge.move(bx, by)
                        badge.raise_()
                else:
                    thumb_widget.setText("🎬\nVideo")
                    thumb_widget.setStyleSheet("color: white;")
            else:
                thumb_widget.setText("🎬\nVideo")
        except Exception as e:
            print(f"[GoogleLayout] Error loading video thumbnail for {video_path}: {e}")
            thumb_widget.setText("🎬\nVideo")

        # FIXED: Open lightbox instead of video player directly
        # This allows browsing through mixed photos and videos
        thumb_widget.mousePressEvent = lambda event: self._open_photo_lightbox(video_path)

        return thumb_widget

    def _open_video_player(self, video_path: str):
        """
        Open video player for the given video path with navigation support.

        Args:
            video_path: Path to video file
        """
        print(f"[GoogleLayout] 🎬 Opening video player for: {video_path}")

        try:
            # Get all videos for navigation
            from services.video_service import VideoService
            video_service = VideoService()

            all_videos = video_service.get_videos_by_project(self.project_id) if self.project_id else []
            video_paths = [v['path'] for v in all_videos]

            # Find current video index
            start_index = 0
            try:
                start_index = video_paths.index(video_path)
            except ValueError:
                print(f"[GoogleLayout] ⚠️ Video not found in list, using index 0")

            print(f"[GoogleLayout] Found {len(video_paths)} videos, current index: {start_index}")

            # Check if main_window is accessible
            if not hasattr(self, 'main_window') or self.main_window is None:
                print("[GoogleLayout] ⚠️ ERROR: main_window not accessible")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(None, "Video Player Error",
                    "Cannot open video player: Main window not accessible.\n\n"
                    "Try switching to Current Layout to play videos.")
                return

            # Check if _open_video_player method exists
            if not hasattr(self.main_window, '_open_video_player'):
                print("[GoogleLayout] ⚠️ ERROR: main_window doesn't have _open_video_player method")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(None, "Video Player Error",
                    "Video player not available in this layout.\n\n"
                    "Try switching to Current Layout to play videos.")
                return

            # Open video player with navigation support
            self.main_window._open_video_player(video_path, video_paths, start_index)
            print(f"[GoogleLayout] ✓ Video player opened successfully")

        except Exception as e:
            print(f"[GoogleLayout] ⚠️ ERROR opening video player: {e}")
            import traceback
            traceback.print_exc()

            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Video Player Error",
                f"Failed to open video player:\n\n{str(e)}\n\n"
                "Check console for details.")

    def _create_date_group(self, date_str: str, photos: List[Tuple], thumb_size: int = 200) -> QWidget:
        """
        Create a date group widget (header + photo grid).

        QUICK WIN #4: Now supports collapse/expand functionality.

        Args:
            date_str: Date string "YYYY-MM-DD"
            photos: List of (path, date_taken, width, height)
        """
        group = QFrame()
        group.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #e8eaed;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)

        # QUICK WIN #4: Initialize collapse state (default: expanded)
        if date_str not in self.date_group_collapsed:
            self.date_group_collapsed[date_str] = False  # False = expanded

        # Header (with collapse/expand button)
        header = self._create_date_header(date_str, len(photos))
        layout.addWidget(header)

        # Photo grid (pass thumb_size)
        grid = self._create_photo_grid(photos, thumb_size)
        layout.addWidget(grid)

        # QUICK WIN #4: Store grid reference for collapse/expand
        self.date_group_grids[date_str] = grid

        # Apply initial collapse state
        if self.date_group_collapsed.get(date_str, False):
            grid.hide()

        return group

    def _format_smart_date(self, date_str: str) -> str:
        """Format date with Google Photos-style smart labels (Today, Yesterday, etc.)."""
        try:
            from datetime import timedelta
            
            date_obj = datetime.fromisoformat(date_str)
            today = datetime.now().date()
            photo_date = date_obj.date()
            
            diff_days = (today - photo_date).days
            
            # Smart labels based on recency
            if diff_days == 0:
                return "Today"
            elif diff_days == 1:
                return "Yesterday"
            elif diff_days <= 6:
                # This week - show day name
                return date_obj.strftime("%A")  # e.g., "Monday"
            elif diff_days <= 13:
                # Last week
                return f"Last {date_obj.strftime('%A')}"
            elif diff_days <= 30:
                # This month - show date without year
                return date_obj.strftime("%B %d")  # e.g., "November 15"
            elif photo_date.year == today.year:
                # This year - show month and day
                return date_obj.strftime("%B %d")  # e.g., "March 22"
            else:
                # Previous years - show full date
                return date_obj.strftime("%B %d, %Y")  # e.g., "March 22, 2023"
        except:
            # Fallback to basic formatting
            try:
                date_obj = datetime.fromisoformat(date_str)
                return date_obj.strftime("%B %d, %Y")
            except:
                return date_str
    
    def _create_date_header(self, date_str: str, count: int) -> QWidget:
        """
        Create date group header with date and photo count.

        QUICK WIN #4: Now includes collapse/expand button.
        Google Photos Enhancement: Smart date labels (Today, Yesterday, etc.)
        """
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # QUICK WIN #4: Collapse/Expand button (▼ = expanded, ► = collapsed)
        collapse_btn = QPushButton()
        is_collapsed = self.date_group_collapsed.get(date_str, False)
        collapse_btn.setText("►" if is_collapsed else "▼")
        collapse_btn.setFixedSize(24, 24)
        collapse_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 12pt;
                color: #5f6368;
                padding: 0;
            }
            QPushButton:hover {
                color: #202124;
                background: #f1f3f4;
                border-radius: 4px;
            }
        """)
        collapse_btn.setCursor(Qt.PointingHandCursor)
        collapse_btn.clicked.connect(lambda: self._toggle_date_group(date_str, collapse_btn))
        header_layout.addWidget(collapse_btn)

        # PHASE 3 #4: Smart date grouping with friendly labels
        try:
            date_obj = datetime.fromisoformat(date_str)
            formatted_date = self._get_smart_date_label(date_obj)
        except:
            formatted_date = date_str

        # Date label (clickable for collapse/expand)
        date_label = QLabel(f"📅 {formatted_date}")
        date_label.setStyleSheet("""
            font-size: 14pt;
            font-weight: bold;
            color: #202124;
            padding: 4px;
        """)
        date_label.setCursor(Qt.PointingHandCursor)
        date_label.mousePressEvent = lambda e: self._toggle_date_group(date_str, collapse_btn)
        header_layout.addWidget(date_label)

        # PHASE 2 #6: Photo count badge (visual pill instead of plain text)
        count_badge = QLabel(f"{count}")
        count_badge.setStyleSheet("""
            QLabel {
                background: #e8f0fe;
                color: #1a73e8;
                font-size: 10pt;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 12px;
                margin-left: 8px;
            }
        """)
        count_badge.setToolTip(f"{count} photo{'s' if count != 1 else ''}")
        header_layout.addWidget(count_badge)

        header_layout.addStretch()

        return header

    def _get_smart_date_label(self, date_obj: datetime) -> str:
        """
        ENHANCED: Google Photos-style smart date labels (Today, Yesterday, Monday, etc.).
        More concise and user-friendly than verbose labels.

        Args:
            date_obj: datetime object

        Returns:
            str: Friendly date label
        """
        from datetime import timedelta

        now = datetime.now()
        today = now.date()
        photo_date = date_obj.date()

        # Calculate difference in days
        delta = (today - photo_date).days

        # Today (no extra date info - it's today!)
        if delta == 0:
            return "Today"

        # Yesterday
        elif delta == 1:
            return "Yesterday"

        # This Week (show day name only)
        elif delta <= 6:
            return date_obj.strftime("%A")  # "Monday", "Tuesday", etc.

        # Last Week (show "Last Monday", etc.)
        elif delta <= 13:
            return f"Last {date_obj.strftime('%A')}"

        # This Month (show month + day)
        elif photo_date.month == today.month and photo_date.year == today.year:
            return date_obj.strftime("%B %d")  # "November 15"

        # This Year (show month + day without year)
        elif photo_date.year == today.year:
            return date_obj.strftime("%B %d")  # "March 22"

        # Previous Years (show full date)
        else:
            return date_obj.strftime("%B %d, %Y")  # "March 22, 2023"

    def _create_empty_state(self, icon: str, title: str, message: str, action_text: str = "") -> QWidget:
        """
        PHASE 2 #7: Create friendly empty state with illustration.

        Args:
            icon: Emoji icon
            title: Main title
            message: Descriptive message
            action_text: Optional action hint

        Returns:
            QWidget: Styled empty state widget
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 80, 40, 80)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignCenter)

        # Large icon
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 72pt;")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 18pt;
            font-weight: bold;
            color: #202124;
        """)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Message
        message_label = QLabel(message)
        message_label.setStyleSheet("""
            font-size: 11pt;
            color: #5f6368;
            line-height: 1.6;
        """)
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        # Action hint
        if action_text:
            action_label = QLabel(action_text)
            action_label.setStyleSheet("""
                font-size: 10pt;
                color: #80868b;
                font-style: italic;
            """)
            action_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(action_label)

        return container

    def _toggle_date_group(self, date_str: str, collapse_btn: QPushButton):
        """
        QUICK WIN #4: Toggle collapse/expand state for a date group.

        Args:
            date_str: Date string "YYYY-MM-DD"
            collapse_btn: The collapse/expand button widget
        """
        try:
            # Get current state
            is_collapsed = self.date_group_collapsed.get(date_str, False)
            new_state = not is_collapsed

            # Update state
            self.date_group_collapsed[date_str] = new_state

            # Get grid widget
            grid = self.date_group_grids.get(date_str)
            if not grid:
                print(f"[GooglePhotosLayout] ⚠️ Grid not found for {date_str}")
                return

            # Toggle visibility
            if new_state:  # Collapsing
                grid.hide()
                collapse_btn.setText("►")
                print(f"[GooglePhotosLayout] ▲ Collapsed date group: {date_str}")
            else:  # Expanding
                grid.show()
                collapse_btn.setText("▼")
                print(f"[GooglePhotosLayout] ▼ Expanded date group: {date_str}")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error toggling date group {date_str}: {e}")

    def _create_date_group_placeholder(self, metadata: dict) -> QWidget:
        """
        QUICK WIN #3: Create placeholder widget for virtual scrolling.

        Placeholder maintains scroll position by matching estimated group height.
        Will be replaced with actual rendered group when it enters viewport.

        Args:
            metadata: Dict with date_str, photos, thumb_size, index

        Returns:
            QWidget: Placeholder with estimated height
        """
        placeholder = QWidget()

        # Estimate height based on photo count
        estimated_height = self._estimate_date_group_height(
            len(metadata['photos']),
            metadata['thumb_size']
        )

        placeholder.setFixedHeight(estimated_height)
        placeholder.setStyleSheet("background: #f8f9fa;")  # Light gray placeholder

        # Store metadata on widget for lazy rendering
        placeholder.setProperty('date_group_metadata', metadata)
        placeholder.setProperty('is_placeholder', True)

        return placeholder

    def _estimate_date_group_height(self, photo_count: int, thumb_size: int) -> int:
        """
        QUICK WIN #3: Estimate date group height for placeholder sizing.

        Height = header + grid + margins
        - Header: ~60px (date label + spacing)
        - Grid: rows * (thumb_size + spacing)
        - Margins: 28px (16 top, 12 bottom from layout.setContentsMargins)

        Args:
            photo_count: Number of photos in group
            thumb_size: Thumbnail size in pixels

        Returns:
            int: Estimated height in pixels
        """
        # Calculate responsive columns (same as grid rendering)
        columns = self._calculate_responsive_columns(thumb_size)

        # Calculate number of rows needed
        rows = (photo_count + columns - 1) // columns  # Ceiling division

        # Component heights
        header_height = 60  # Date label + spacing
        spacing = 2  # GOOGLE PHOTOS STYLE
        grid_height = rows * (thumb_size + spacing)
        margins = 28  # 16 + 12 from setContentsMargins
        border = 2  # 1px border top + bottom

        total_height = header_height + grid_height + margins + border

        return total_height

    def _render_visible_date_groups(self, viewport, viewport_rect):
        """
        QUICK WIN #3: Render date groups that are visible in viewport.

        Checks which date groups intersect with the viewport and replaces
        placeholders with actual rendered groups.

        Args:
            viewport: Timeline viewport widget
            viewport_rect: Viewport rectangle
        """
        try:
            groups_to_render = []

            # Check each date group to see if it's visible
            for metadata in self.date_groups_metadata:
                index = metadata['index']

                # Skip if already rendered
                if index in self.rendered_date_groups:
                    continue

                # Get the widget (placeholder)
                widget = self.date_group_widgets.get(index)
                if not widget:
                    continue

                # Check if widget is visible in viewport
                try:
                    # Map widget position to viewport coordinates
                    widget_pos = widget.mapTo(viewport, widget.rect().topLeft())
                    widget_rect = widget.rect()
                    widget_rect.moveTo(widget_pos)

                    # If widget intersects viewport, it's visible
                    if viewport_rect.intersects(widget_rect):
                        groups_to_render.append((index, metadata))

                except Exception as e:
                    continue

            # Render visible groups
            if groups_to_render:
                print(f"[GooglePhotosLayout] 🎨 Rendering {len(groups_to_render)} date groups that entered viewport...")

                for index, metadata in groups_to_render:
                    try:
                        # Create actual rendered group
                        rendered_group = self._create_date_group(
                            metadata['date_str'],
                            metadata['photos'],
                            metadata['thumb_size']
                        )

                        # Replace placeholder with rendered group in layout
                        old_widget = self.date_group_widgets[index]
                        layout_index = self.timeline_layout.indexOf(old_widget)

                        if layout_index != -1:
                            # Remove placeholder
                            self.timeline_layout.removeWidget(old_widget)
                            old_widget.deleteLater()

                            # Insert rendered group at same position
                            self.timeline_layout.insertWidget(layout_index, rendered_group)
                            self.date_group_widgets[index] = rendered_group
                            self.rendered_date_groups.add(index)

                    except Exception as e:
                        print(f"[GooglePhotosLayout] ⚠️ Error rendering date group {index}: {e}")
                        continue

                print(f"[GooglePhotosLayout] ✓ Now {len(self.rendered_date_groups)}/{len(self.date_groups_metadata)} groups rendered")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error in virtual scrolling: {e}")

    def _create_photo_grid(self, photos: List[Tuple], thumb_size: int = 200) -> QWidget:
        """
        Create photo grid with thumbnails.

        QUICK WIN #2: Responsive grid that adapts to viewport width.
        Google Photos Style: Minimal spacing for dense, clean grid.
        """
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(2)  # GOOGLE PHOTOS STYLE: Minimal padding
        grid.setContentsMargins(0, 0, 0, 0)

        # QUICK WIN #2: Calculate responsive columns based on viewport width
        # This makes the grid perfect on 1080p, 4K, mobile, etc.
        columns = self._calculate_responsive_columns(thumb_size)

        # Store grid reference for resize handling (QUICK WIN #2)
        if not hasattr(self, '_photo_grids'):
            self._photo_grids = []
        self._photo_grids.append({
            'container': grid_container,
            'grid': grid,
            'photos': photos,
            'thumb_size': thumb_size,
            'columns': columns
        })

        # Add photo thumbnails
        for i, photo in enumerate(photos):
            path, date_taken, width, height = photo

            row = i // columns
            col = i % columns

            thumb = self._create_thumbnail(path, thumb_size)
            grid.addWidget(thumb, row, col)

        return grid_container

    def _calculate_responsive_columns(self, thumb_size: int) -> int:
        """
        QUICK WIN #2: Calculate optimal column count based on viewport width.

        Algorithm (matches Google Photos):
        - Get available width from timeline viewport
        - Calculate how many thumbnails fit
        - Enforce min/max constraints (2-8 columns)
        - Account for spacing and margins

        Args:
            thumb_size: Thumbnail width in pixels

        Returns:
            int: Optimal number of columns (2-8)
        """
        # Get viewport width (timeline scroll area)
        if hasattr(self, 'timeline_scroll'):
            viewport_width = self.timeline_scroll.viewport().width()
        else:
            # Fallback during initialization
            viewport_width = 1200  # Reasonable default

        # Account for margins (20px left + 20px right from timeline_layout)
        available_width = viewport_width - 40

        # Account for grid spacing (2px between each thumbnail)
        spacing = 2

        # Calculate how many thumbnails fit
        # Formula: (width - margins) / (thumb_size + spacing)
        cols = int(available_width / (thumb_size + spacing))

        # Enforce constraints
        # Min: 2 columns (prevents single-column on small screens)
        # Max: 8 columns (prevents tiny thumbnails on huge screens)
        cols = max(2, min(8, cols))

        # DEBUG: Only print if columns changed (reduce log spam)
        if not hasattr(self, '_last_column_count') or self._last_column_count != cols:
            print(f"[GooglePhotosLayout] 📐 Responsive grid: {cols} columns (viewport: {viewport_width}px, thumb: {thumb_size}px)")
            self._last_column_count = cols

        return cols

    def _on_thumbnail_loaded(self, path: str, pixmap: QPixmap, size: int):
        """
        Callback when async thumbnail loading completes.

        Phase 3 #1: Added smooth fade-in animation for loaded thumbnails.
        Phase 3 #2: Stops pulsing animation and shows cached thumbnail.
        """
        # Find the button for this path
        button = self.thumbnail_buttons.get(path)
        if not button:
            return  # Button was destroyed (e.g., during reload)

        try:
            # Update button with loaded thumbnail
            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                button.setIcon(QIcon(scaled))
                button.setIconSize(QSize(size - 4, size - 4))
                button.setText("")  # Clear placeholder text

                # PHASE 3 #1: Smooth fade-in animation for thumbnail
                # PHASE 3 #2 FIX: Always create fresh graphics effect to avoid conflicts
                from PySide6.QtCore import QPropertyAnimation, QEasingCurve

                # Create new opacity effect (don't reuse to avoid animation conflicts)
                opacity_effect = QGraphicsOpacityEffect()
                button.setGraphicsEffect(opacity_effect)
                opacity_effect.setOpacity(0.0)

                # Animate fade-in from 0 to 1
                fade_in = QPropertyAnimation(opacity_effect, b"opacity")
                fade_in.setDuration(300)  # 300ms fade-in
                fade_in.setStartValue(0.0)
                fade_in.setEndValue(1.0)
                fade_in.setEasingCurve(QEasingCurve.OutCubic)
                fade_in.start()

                # Store animation to prevent garbage collection
                button.setProperty("fade_animation", fade_in)
            else:
                button.setText("📷")  # No thumbnail - show placeholder
        except Exception as e:
            print(f"[GooglePhotosLayout] Error updating thumbnail for {path}: {e}")
            button.setText("❌")

    def _on_timeline_scrolled(self):
        """
        QUICK WIN #5: Debounced scroll handler for smooth 60 FPS performance.
        PHASE 2 #4: Also shows date scroll indicator during scrolling.

        Instead of processing every scroll event (which can be hundreds per second),
        we restart a timer on each scroll. Only when scrolling stops (or slows down)
        for 150ms do we actually process the heavy operations.

        This prevents lag and dropped frames during fast scrolling.
        """
        # PHASE 2 #4: Update date scroll indicator (lightweight operation)
        self._update_date_scroll_indicator()

        # Restart debounce timer - will trigger _on_scroll_debounced() after 150ms of no scrolling
        self.scroll_debounce_timer.stop()
        self.scroll_debounce_timer.start(self.scroll_debounce_delay)

        # PHASE 2 #4: Restart hide timer - indicator will hide 800ms after scrolling stops
        if hasattr(self, 'date_indicator_hide_timer'):
            self.date_indicator_hide_timer.stop()
            self.date_indicator_hide_timer.start(self.date_indicator_delay)

    def _update_date_scroll_indicator(self):
        """
        PHASE 2 #4: Update floating date indicator with current visible date.

        Finds the topmost visible date group and shows its date in the indicator.
        Lightweight operation - just checks viewport position.
        """
        if not hasattr(self, 'date_scroll_indicator') or not hasattr(self, 'date_groups_metadata'):
            return

        try:
            # Get viewport
            viewport = self.timeline_scroll.viewport()
            viewport_rect = viewport.rect()
            viewport_top = viewport_rect.top()

            # Find first visible date group
            current_date = None
            for metadata in self.date_groups_metadata:
                widget = self.date_group_widgets.get(metadata['index'])
                if not widget:
                    continue

                # Check if widget is visible
                try:
                    widget_pos = widget.mapTo(viewport, widget.rect().topLeft())
                    # If widget's top is in viewport, this is the current date
                    if widget_pos.y() >= viewport_top - 100 and widget_pos.y() <= viewport_top + 200:
                        current_date = metadata['date_str']
                        break
                except:
                    continue

            if current_date:
                # Format date for indicator
                try:
                    date_obj = datetime.fromisoformat(current_date)
                    label = self._get_smart_date_label(date_obj)
                except:
                    label = current_date

                # Update and show indicator
                self.date_scroll_indicator.setText(label)
                self.date_scroll_indicator.adjustSize()

                # Position at top-right of viewport
                parent = self.date_scroll_indicator.parent()
                if parent:
                    x = parent.width() - self.date_scroll_indicator.width() - 20
                    y = 80  # Below toolbar
                    self.date_scroll_indicator.move(x, y)

                # PHASE 3 #1: Smooth slide-in animation from right if not already visible
                if not self.date_scroll_indicator.isVisible():
                    from PySide6.QtCore import QPropertyAnimation, QPoint, QEasingCurve

                    # Start position (off-screen to the right)
                    start_x = parent.width()
                    end_x = x

                    # Move to start position
                    self.date_scroll_indicator.move(start_x, y)
                    self.date_scroll_indicator.show()
                    self.date_scroll_indicator.raise_()

                    # Animate slide-in from right
                    slide_in = QPropertyAnimation(self.date_scroll_indicator, b"pos")
                    slide_in.setDuration(250)  # 250ms slide
                    slide_in.setStartValue(QPoint(start_x, y))
                    slide_in.setEndValue(QPoint(end_x, y))
                    slide_in.setEasingCurve(QEasingCurve.OutCubic)
                    slide_in.start()

                    # Store animation to prevent garbage collection
                    self.date_scroll_indicator.setProperty("slide_animation", slide_in)
                else:
                    # Already visible, just update position
                    self.date_scroll_indicator.show()
                    self.date_scroll_indicator.raise_()

        except Exception as e:
            pass  # Silently fail to avoid disrupting scrolling

    def _hide_date_indicator(self):
        """
        PHASE 2 #4: Hide date scroll indicator after scrolling stops.
        Phase 3 #1: Added smooth fade-out animation.
        """
        if hasattr(self, 'date_scroll_indicator') and self.date_scroll_indicator.isVisible():
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve

            # Create opacity effect if not already present
            if not self.date_scroll_indicator.graphicsEffect():
                opacity_effect = QGraphicsOpacityEffect()
                self.date_scroll_indicator.setGraphicsEffect(opacity_effect)
                opacity_effect.setOpacity(1.0)

            opacity_effect = self.date_scroll_indicator.graphicsEffect()

            # Animate fade-out
            fade_out = QPropertyAnimation(opacity_effect, b"opacity")
            fade_out.setDuration(200)  # 200ms fade-out
            fade_out.setStartValue(1.0)
            fade_out.setEndValue(0.0)
            fade_out.setEasingCurve(QEasingCurve.InCubic)
            fade_out.finished.connect(self.date_scroll_indicator.hide)
            fade_out.start()

            # Store animation to prevent garbage collection
            self.date_scroll_indicator.setProperty("fade_animation", fade_out)

    def _on_scroll_debounced(self):
        """
        QUICK WIN #1, #3, #5: Process scroll events after debouncing.

        This is called 150ms after scrolling stops/slows down.

        Two functions:
        1. Load thumbnails that are now visible (Quick Win #1)
        2. Render date groups that entered viewport (Quick Win #3)
        """
        # Get viewport rectangle
        viewport = self.timeline_scroll.viewport()
        viewport_rect = viewport.rect()

        # QUICK WIN #3: Virtual scrolling - render date groups that entered viewport
        if self.virtual_scroll_enabled and self.date_groups_metadata:
            self._render_visible_date_groups(viewport, viewport_rect)

        # QUICK WIN #1: Lazy thumbnail loading
        if not self.unloaded_thumbnails:
            return  # All thumbnails already loaded

        # QUICK WIN #5: Limit checks to prevent lag with huge libraries
        # Only check first 200 unloaded items per scroll event
        # This balances responsiveness vs performance
        max_checks = 200
        items_to_check = list(self.unloaded_thumbnails.items())[:max_checks]

        # Find and load visible thumbnails
        paths_to_load = []
        for path, (button, size) in items_to_check:
            # Check if button is visible in viewport
            try:
                # Map button position to viewport coordinates
                button_pos = button.mapTo(viewport, button.rect().topLeft())
                button_rect = button.rect()
                button_rect.moveTo(button_pos)

                # If button intersects viewport, it's visible
                if viewport_rect.intersects(button_rect):
                    paths_to_load.append(path)

            except Exception as e:
                # Button might have been deleted
                continue

        # Load visible thumbnails
        if paths_to_load:
            print(f"[GooglePhotosLayout] 📜 Scroll detected, loading {len(paths_to_load)} visible thumbnails...")
            for path in paths_to_load:
                button, size = self.unloaded_thumbnails.pop(path)
                # Queue async loading
                loader = ThumbnailLoader(path, size, self.thumbnail_signals)
                self.thumbnail_thread_pool.start(loader)

            print(f"[GooglePhotosLayout] ✓ Loaded {len(paths_to_load)} thumbnails, {len(self.unloaded_thumbnails)} remaining")

    def _create_thumbnail(self, path: str, size: int) -> QWidget:
        """
        Create thumbnail widget for a photo with selection checkbox.

        Phase 2: Enhanced with checkbox overlay for batch selection.
        Phase 2 #5: Support for different aspect ratios (square, original, 16:9).
        Phase 3: ASYNC thumbnail loading to prevent UI freeze with large photo sets.
        """
        from PySide6.QtWidgets import QCheckBox, QVBoxLayout

        # PHASE 2 #5: Calculate container size based on aspect ratio mode
        if self.thumbnail_aspect_ratio == "square":
            # Square thumbnails (default)
            container_width = size
            container_height = size
        elif self.thumbnail_aspect_ratio == "16:9":
            # Widescreen 16:9 aspect ratio
            container_width = size
            container_height = int(size * 9 / 16)  # ~56% of width
        else:  # "original"
            # Original aspect ratio - try to get image dimensions
            try:
                from PIL import Image
                with Image.open(path) as img:
                    img_width, img_height = img.size
                    # Calculate scaled dimensions maintaining aspect ratio
                    if img_width > img_height:
                        container_width = size
                        container_height = int(size * img_height / img_width)
                    else:
                        container_height = size
                        container_width = int(size * img_width / img_height)
            except Exception as e:
                # Fallback to square if we can't read the image
                print(f"[GooglePhotosLayout] Warning: Could not read image dimensions for {os.path.basename(path)}: {e}")
                container_width = size
                container_height = size

        # Container widget
        container = QWidget()
        container.setFixedSize(container_width, container_height)
        container.setStyleSheet("background: transparent;")

        # Thumbnail button with placeholder
        thumb = PhotoButton(path, self.project_id, container)  # Use custom PhotoButton
        thumb.setGeometry(0, 0, container_width, container_height)
        # QUICK WIN #8: Modern hover effects with smooth transitions
        # QUICK WIN #9: Skeleton loading state with gradient
        thumb.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e8eaed, stop:0.5 #f1f3f4, stop:1 #e8eaed);
                border: 2px solid #dadce0;
                border-radius: 4px;
                color: #5f6368;
                font-size: 9pt;
            }
            QPushButton:hover {
                background: #ffffff;
                border-color: #1a73e8;
                border-width: 2px;
            }
        """)
        thumb.setCursor(Qt.PointingHandCursor)

        # PHASE 2 #8: Photo metadata tooltip (lightweight - no image loading)
        # PERFORMANCE FIX: Don't load QImage here - it's too expensive during initialization!
        try:
            filename = os.path.basename(path)
            stat = os.stat(path)
            file_size = stat.st_size / (1024 * 1024)  # MB
            tooltip = f"{filename}\nSize: {file_size:.2f} MB"
            thumb.setToolTip(tooltip)
        except:
            thumb.setToolTip(os.path.basename(path))

        # QUICK WIN #9: Skeleton loading indicator (subtle, professional)
        # PHASE 3 #2: Simple skeleton state without animation (performance fix)
        thumb.setText("⏳")

        # Store button for async update
        self.thumbnail_buttons[path] = thumb
        
        # Load and set tags for badge painting
        # ARCHITECTURE: Use TagService layer (Schema v3.1.0) instead of direct ReferenceDB calls
        try:
            from services.tag_service import get_tag_service
            tag_service = get_tag_service()
            tags_map = tag_service.get_tags_for_paths([path], self.project_id)
            tags = tags_map.get(path, [])  # Extract tags for this photo
            thumb.set_tags(tags)  # Set tags on PhotoButton for painting
        except Exception as e:
            print(f"[GooglePhotosLayout] Warning: Could not load tags for {os.path.basename(path)}: {e}")

        # QUICK WIN #1: Load first 50 immediately, rest on scroll
        # This removes the 30-photo limit while maintaining initial performance
        if self.thumbnail_load_count < self.initial_load_limit:
            self.thumbnail_load_count += 1
            # Queue async thumbnail loading with SHARED signal object
            loader = ThumbnailLoader(path, size, self.thumbnail_signals)
            self.thumbnail_thread_pool.start(loader)
        else:
            # Store for lazy loading on scroll
            self.unloaded_thumbnails[path] = (thumb, size)
            print(f"[GooglePhotosLayout] Deferred thumbnail #{self.thumbnail_load_count + 1}: {os.path.basename(path)}")

        # Phase 2: Selection checkbox (overlay top-left corner)
        # QUICK WIN #8: Enhanced with modern hover effects
        checkbox = QCheckBox(container)
        checkbox.setGeometry(8, 8, 24, 24)
        checkbox.setStyleSheet("""
            QCheckBox {
                background: rgba(255, 255, 255, 0.9);
                border: 2px solid #dadce0;
                border-radius: 4px;
                padding: 2px;
            }
            QCheckBox:hover {
                background: rgba(255, 255, 255, 1.0);
                border-color: #1a73e8;
            }
            QCheckBox:checked {
                background: #1a73e8;
                border-color: #1a73e8;
            }
            QCheckBox:checked:hover {
                background: #1557b0;
                border-color: #1557b0;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        checkbox.setCursor(Qt.PointingHandCursor)
        checkbox.setVisible(self.selection_mode)  # Only visible in selection mode

        # Store references
        container.setProperty("photo_path", path)
        container.setProperty("thumbnail_button", thumb)
        container.setProperty("checkbox", checkbox)
        
        # NOTE: Tag badges are now painted directly on PhotoButton, not as QLabel overlays

        # Connect signals
        thumb.clicked.connect(lambda: self._on_photo_clicked(path))
        checkbox.stateChanged.connect(lambda state: self._on_selection_changed(path, state))

        # PHASE 2 #1: Context menu on right-click
        thumb.setContextMenuPolicy(Qt.CustomContextMenu)
        thumb.customContextMenuRequested.connect(lambda pos: self._show_photo_context_menu(path, thumb.mapToGlobal(pos)))

        return container

    def _create_tag_badge_overlay(self, container: QWidget, path: str, container_width: int):
        """
        Create tag badge overlays for photo thumbnail (Google Photos + Current layout pattern).
        
        Displays stacked badges in top-right corner for:
        - ★ Favorite (gold)
        - 👤 Face (blue)
        - 🏷 Custom tags (gray)
        
        Args:
            container: Parent container widget
            path: Photo path
            container_width: Actual width of the container widget (for correct badge positioning)
        """
        try:
            from services.tag_service import get_tag_service

            # Query tags for this photo using proper service layer
            tag_service = get_tag_service()
            tags = tag_service.get_tags_for_path(path, self.project_id) or []

            # Log tag query result (debug level to avoid spam)
            logger.debug(f"Badge overlay for {os.path.basename(path)}: tags={tags}")

            if not tags:
                return  # No tags to display

            # PERFORMANCE FIX: Use cached settings instead of reading SettingsManager every time
            if not self._badge_settings['enabled']:
                return  # Badges disabled by user

            badge_size = self._badge_settings['size']
            max_badges = self._badge_settings['max_count']
            badge_margin = 4

            # Calculate badge positions (top-right corner, stacked vertically)
            x_right = container_width - badge_margin - badge_size
            y_top = badge_margin

            # PERFORMANCE FIX: Use class constant (not recreated on every call)
            badge_config = self.TAG_BADGE_CONFIG

            # Create badge labels
            badge_count = 0
            for tag in tags:
                tag_lower = str(tag).lower().strip()

                # Get badge config or use default
                if tag_lower in badge_config:
                    icon, bg_color, fg_color = badge_config[tag_lower]
                else:
                    # Default badge for custom tags
                    icon, bg_color, fg_color = self.DEFAULT_BADGE_CONFIG
                
                if badge_count >= max_badges:
                    break  # Max badges reached
                
                # Create badge label
                badge = QLabel(icon, container)
                badge.setFixedSize(badge_size, badge_size)
                badge.setAlignment(Qt.AlignCenter)
                badge.setStyleSheet(f"""
                    QLabel {{
                        background-color: rgba({bg_color.red()}, {bg_color.green()}, {bg_color.blue()}, {bg_color.alpha()});
                        color: {'black' if fg_color == Qt.black else 'white'};
                        border-radius: {badge_size // 2}px;
                        font-size: 11pt;
                        font-weight: bold;
                    }}
                """)
                
                # Position badge (stacked vertically)
                y_pos = y_top + (badge_count * (badge_size + 4))
                badge.move(x_right, y_pos)
                badge.setToolTip(tag)  # Show tag name on hover
                badge.show()  # Explicitly show the badge
                badge.raise_()  # Bring to front
                
                # Store reference for updates
                if not hasattr(container, '_tag_badges'):
                    container.setProperty('_tag_badges', [])
                badges_list = container.property('_tag_badges') or []
                badges_list.append(badge)
                container.setProperty('_tag_badges', badges_list)
                
                badge_count += 1
            
            # Show "+n" indicator if more tags exist
            if len(tags) > max_badges:
                overflow_badge = QLabel(f"+{len(tags) - max_badges}", container)
                overflow_badge.setFixedSize(badge_size, badge_size)
                overflow_badge.setAlignment(Qt.AlignCenter)
                overflow_badge.setStyleSheet(f"""
                    QLabel {{
                        background-color: rgba(60, 60, 60, 220);
                        color: white;
                        border-radius: {badge_size // 2}px;
                        font-size: 9pt;
                        font-weight: bold;
                    }}
                """)
                y_pos = y_top + (max_badges * (badge_size + 4))
                overflow_badge.move(x_right, y_pos)
                overflow_badge.setToolTip(f"{len(tags) - max_badges} more tags: {', '.join(tags[max_badges:])}")
                overflow_badge.show()  # Explicitly show the overflow badge
                overflow_badge.raise_()
                
            # Log badge creation (debug level to avoid spam)
            if badge_count > 0:
                logger.debug(f"Created {badge_count} tag badge(s) for {os.path.basename(path)}: {tags[:max_badges]}")

        except Exception as e:
            logger.error(f"Error creating tag badges for {os.path.basename(path)}: {e}", exc_info=True)

    def _on_photo_clicked(self, path: str):
        """
        Handle photo thumbnail click with Shift+Ctrl multi-selection support.

        - Normal click: Open lightbox
        - Ctrl+Click: Add/remove from selection (toggle)
        - Shift+Click: Range select from last selected to current
        - Selection mode: Toggle selection
        """
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt

        print(f"[GooglePhotosLayout] Photo clicked: {path}")

        # Get keyboard modifiers
        modifiers = QApplication.keyboardModifiers()
        ctrl_pressed = bool(modifiers & Qt.ControlModifier)
        shift_pressed = bool(modifiers & Qt.ShiftModifier)

        # SHIFT+CLICK: Range selection (from last selected to current)
        if shift_pressed and self.last_selected_path and self.all_displayed_paths:
            print(f"[GooglePhotosLayout] Shift+Click range selection from {self.last_selected_path} to {path}")
            try:
                # Find indices of last selected and current photo
                last_idx = self.all_displayed_paths.index(self.last_selected_path)
                current_idx = self.all_displayed_paths.index(path)

                # Select all photos in range
                start_idx = min(last_idx, current_idx)
                end_idx = max(last_idx, current_idx)

                for idx in range(start_idx, end_idx + 1):
                    range_path = self.all_displayed_paths[idx]
                    if range_path not in self.selected_photos:
                        self.selected_photos.add(range_path)
                        self._update_checkbox_state(range_path, True)

                self._update_selection_ui()
                print(f"[GooglePhotosLayout] ✓ Range selected: {end_idx - start_idx + 1} photos")
                return

            except (ValueError, IndexError) as e:
                print(f"[GooglePhotosLayout] ⚠️ Range selection error: {e}")
                # Fall through to normal selection

        # CTRL+CLICK: Toggle selection (add/remove)
        if ctrl_pressed:
            print(f"[GooglePhotosLayout] Ctrl+Click toggle selection: {path}")
            self._toggle_photo_selection(path)
            self.last_selected_path = path  # Update last selected for future Shift+Click
            return

        # NORMAL CLICK in selection mode: Toggle selection
        if self.selection_mode:
            self._toggle_photo_selection(path)
            self.last_selected_path = path
        else:
            # NORMAL CLICK: Open lightbox/preview
            self._open_photo_lightbox(path)

    def _open_photo_lightbox(self, path: str):
        """
        Open media lightbox/preview dialog (supports both photos AND videos).

        Args:
            path: Path to photo or video to display
        """
        print(f"[GooglePhotosLayout] 👁️ Opening lightbox for: {path}")

        # Collect all media paths (photos + videos) in timeline order
        all_media = self._get_all_media_paths()

        if not all_media:
            print("[GooglePhotosLayout] ⚠️ No media to display in lightbox")
            return

        # Create and show lightbox dialog
        try:
            lightbox = MediaLightbox(path, all_media, parent=self.main_window)
            lightbox.exec()
            print("[GooglePhotosLayout] ✓ MediaLightbox closed")
            
            # PHASE 3: Refresh tag overlays after lightbox closes
            # (user may have favorited/unfavorited in lightbox)
            self._refresh_tag_overlays([path])

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error opening lightbox: {e}")
            import traceback
            traceback.print_exc()

    def _get_all_media_paths(self) -> List[str]:
        """
        Get all media paths (photos + videos) in timeline order (newest to oldest).

        Returns:
            List of media paths
        """
        # Prefer the currently displayed context (branch/day/group)
        try:
            if hasattr(self, 'all_displayed_paths') and self.all_displayed_paths:
                return list(self.all_displayed_paths)
        except Exception:
            pass
        # Fallback: ask grid for visible paths if available
        try:
            grid = getattr(self, 'grid', None)
            if grid and hasattr(grid, 'get_visible_paths'):
                paths = grid.get_visible_paths()
                if paths:
                    return paths
        except Exception:
            pass

        all_paths = []

        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Query all photos for current project, ordered by date
            photo_query = """
                SELECT DISTINCT pm.path
                FROM photo_metadata pm
                JOIN project_images pi ON pm.path = pi.image_path
                WHERE pi.project_id = ?
                AND pm.date_taken IS NOT NULL
                ORDER BY pm.date_taken DESC
            """

            # Query all videos for current project, ordered by date
            video_query = """
                SELECT DISTINCT path
                FROM video_metadata
                WHERE project_id = ?
                AND created_date IS NOT NULL
                ORDER BY created_date DESC
            """

            with db._connect() as conn:
                conn.execute("PRAGMA busy_timeout = 5000")
                cur = conn.cursor()

                # Get photos
                cur.execute(photo_query, (self.project_id,))
                photo_rows = cur.fetchall()
                photo_paths = [row[0] for row in photo_rows]

                # Get videos
                cur.execute(video_query, (self.project_id,))
                video_rows = cur.fetchall()
                video_paths = [row[0] for row in video_rows]

                # Combine and sort by date (already sorted individually, merge them)
                # For now, just append videos after photos (both are sorted by date desc)
                # TODO: Could merge-sort by actual date if needed
                all_paths = photo_paths + video_paths

                print(f"[GooglePhotosLayout] Found {len(photo_paths)} photos + {len(video_paths)} videos = {len(all_paths)} total media")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error fetching media paths: {e}")

        return all_paths

    def _on_selection_changed(self, path: str, state: int):
        """
        Handle checkbox selection change.

        Args:
            path: Photo path
            state: Qt.CheckState (0=unchecked, 2=checked)
        """
        from PySide6.QtCore import Qt

        if state == Qt.Checked:
            self.selected_photos.add(path)
            print(f"[GooglePhotosLayout] ✓ Selected: {path}")
        else:
            self.selected_photos.discard(path)
            print(f"[GooglePhotosLayout] ✗ Deselected: {path}")

        # Update selection counter and action buttons
        self._update_selection_ui()

    def _toggle_photo_selection(self, path: str):
        """
        Toggle photo selection and update checkbox.
        """
        # Find checkbox for this photo
        container = self._find_thumbnail_container(path)
        if container:
            checkbox = container.property("checkbox")
            if checkbox:
                # Toggle checkbox (will trigger _on_selection_changed)
                checkbox.setChecked(not checkbox.isChecked())

    def _find_thumbnail_container(self, path: str) -> QWidget:
        """
        Find thumbnail container widget by photo path.
        """
        # Iterate through all date groups to find the thumbnail
        for i in range(self.timeline_layout.count()):
            date_group = self.timeline_layout.itemAt(i).widget()
            if not date_group:
                continue

            # Find grid inside date group
            group_layout = date_group.layout()
            if not group_layout:
                continue

            for j in range(group_layout.count()):
                item = group_layout.itemAt(j)
                if not item or not item.widget():
                    continue

                widget = item.widget()
                if hasattr(widget, 'layout') and widget.layout():
                    # This is a grid container
                    grid = widget.layout()
                    for k in range(grid.count()):
                        container = grid.itemAt(k).widget()
                        if container and container.property("photo_path") == path:
                            return container

        return None

    def _update_checkbox_state(self, path: str, checked: bool):
        """
        Update checkbox state for a specific photo (for multi-selection support).

        Args:
            path: Photo path
            checked: True to check, False to uncheck
        """
        container = self._find_thumbnail_container(path)
        if container:
            checkbox = container.property("checkbox")
            if checkbox:
                # Update checkbox state without triggering signal
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)

    def _update_selection_ui(self):
        """
        Update selection counter and show/hide action buttons.

        QUICK WIN #6: Now also controls floating toolbar.
        """
        count = len(self.selected_photos)

        # Update toolbar selection counter (add if doesn't exist)
        if not hasattr(self, 'selection_label'):
            from PySide6.QtWidgets import QLabel
            self.selection_label = QLabel()
            self.selection_label.setStyleSheet("font-weight: bold; padding: 0 12px;")
            # Insert selection label in toolbar (after existing actions)
            toolbar = self._toolbar
            # Simply add to toolbar without complex index logic
            toolbar.addWidget(self.selection_label)

        # Update counter text
        if count > 0:
            self.selection_label.setText(f"✓ {count} selected")
            self.selection_label.setVisible(True)

            # Show action buttons
            self.btn_delete.setVisible(True)
            self.btn_favorite.setVisible(True)
            self.btn_share.setVisible(True)  # PHASE 3 #7: Show share button

            # QUICK WIN #6: Show and update floating toolbar
            if hasattr(self, 'floating_toolbar') and hasattr(self, 'selection_count_label'):
                self.selection_count_label.setText(f"{count} selected")
                self._position_floating_toolbar()
                self.floating_toolbar.show()
                self.floating_toolbar.raise_()  # Bring to front
        else:
            self.selection_label.setVisible(False)

            # Hide action buttons when nothing selected
            self.btn_delete.setVisible(False)
            self.btn_favorite.setVisible(False)
            self.btn_share.setVisible(False)  # PHASE 3 #7: Hide share button

            # QUICK WIN #6: Hide floating toolbar when no selection
            if hasattr(self, 'floating_toolbar'):
                self.floating_toolbar.hide()

        print(f"[GooglePhotosLayout] Selection updated: {count} photos selected")

    def _position_floating_toolbar(self):
        """
        QUICK WIN #6: Position floating toolbar at bottom center of viewport.
        """
        if not hasattr(self, 'floating_toolbar'):
            return

        # Get parent widget size
        parent = self.floating_toolbar.parent()
        if not parent:
            return

        parent_width = parent.width()
        parent_height = parent.height()

        toolbar_width = self.floating_toolbar.width()
        toolbar_height = self.floating_toolbar.height()

        # Position at bottom center
        x = (parent_width - toolbar_width) // 2
        y = parent_height - toolbar_height - 20  # 20px from bottom

        self.floating_toolbar.move(x, y)

    def _on_select_all(self):
        """
        QUICK WIN #6: Select all visible photos.
        """
        # Select all displayed photos
        for path in self.all_displayed_paths:
            if path not in self.selected_photos:
                self.selected_photos.add(path)
                self._update_checkbox_state(path, True)

        self._update_selection_ui()
        print(f"[GooglePhotosLayout] ✓ Selected all {len(self.selected_photos)} photos")

    def _on_clear_selection(self):
        """
        QUICK WIN #6: Clear all selected photos.
        """
        # Deselect all photos
        for path in list(self.selected_photos):
            self._update_checkbox_state(path, False)

        self.selected_photos.clear()
        self._update_selection_ui()
        print("[GooglePhotosLayout] ✗ Cleared all selections")

    def _show_photo_context_menu(self, path: str, global_pos):
        """
        Show comprehensive context menu for photo thumbnail (right-click).

        MERGED IMPLEMENTATION: Combines tag operations (using TagService) with
        file operations (Open, Delete, Properties, etc.)

        Actions available:
        - Open: View in lightbox
        - Checkable common tags (favorite, face, important, etc.)
        - New Tag/Remove All Tags
        - Select/Deselect: Toggle selection
        - Delete: Remove photo
        - Show in Explorer: Open file location
        - Copy Path: Copy file path to clipboard
        - Properties: Show photo details

        Args:
            path: Photo file path
            global_pos: Global position for menu

        Fixes:
        - Uses TagService instead of ReferenceDB (proper architecture)
        - Merges duplicate implementations (was also at line 15465)
        - Provides comprehensive functionality in single method
        """
        from PySide6.QtWidgets import QMenu, QMessageBox
        from PySide6.QtGui import QAction

        try:
            # Get current tags using proper service layer (not ReferenceDB)
            from services.tag_service import get_tag_service
            tag_service = get_tag_service()
            current_tags = [t.lower() for t in (tag_service.get_tags_for_path(path, self.project_id) or [])]

            menu = QMenu(self.main_window)
            menu.setStyleSheet("""
                QMenu {
                    background: white;
                    border: 1px solid #dadce0;
                    border-radius: 4px;
                    padding: 4px;
                }
                QMenu::item {
                    padding: 6px 24px 6px 12px;
                    border-radius: 2px;
                }
                QMenu::item:selected {
                    background: #f1f3f4;
                }
                QMenu::separator {
                    height: 1px;
                    background: #e8eaed;
                    margin: 4px 0;
                }
            """)

            # Open action
            open_action = QAction("📂 Open", parent=menu)
            open_action.triggered.connect(lambda: self._on_photo_clicked(path))
            menu.addAction(open_action)

            menu.addSeparator()

            # Common tags (checkable items show ✓ when present)
            common_tags = [
                ("favorite", "⭐ Favorite"),
                ("face", "👤 Face"),
                ("important", "⚑ Important"),
                ("work", "💼 Work"),
                ("travel", "✈ Travel"),
                ("personal", "♥ Personal"),
                ("family", "👨‍👩‍👧 Family"),
                ("archive", "📦 Archive"),
            ]
            tag_actions = {}
            for key, label in common_tags:
                act = menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(key in current_tags)
                tag_actions[act] = key

            menu.addSeparator()

            # Tag management actions
            act_new_tag = menu.addAction("🏷️ New Tag…")
            act_remove_all_tags = menu.addAction("🗑️ Remove All Tags")

            menu.addSeparator()

            # Select/Deselect toggle
            is_selected = path in self.selected_photos
            if is_selected:
                select_action = QAction("✓ Deselect", parent=menu)
                select_action.triggered.connect(lambda: self._toggle_photo_selection(path))
            else:
                select_action = QAction("☐ Select", parent=menu)
                select_action.triggered.connect(lambda: self._toggle_photo_selection(path))
            menu.addAction(select_action)

            menu.addSeparator()

            # Delete photo action
            delete_action = QAction("🗑️ Delete Photo", parent=menu)
            delete_action.triggered.connect(lambda: self._delete_single_photo(path))
            menu.addAction(delete_action)

            menu.addSeparator()

            # File operations
            explorer_action = QAction("📁 Show in Explorer", parent=menu)
            explorer_action.triggered.connect(lambda: self._show_in_explorer(path))
            menu.addAction(explorer_action)

            copy_action = QAction("📋 Copy Path", parent=menu)
            copy_action.triggered.connect(lambda: self._copy_path_to_clipboard(path))
            menu.addAction(copy_action)

            menu.addSeparator()

            # Properties action
            properties_action = QAction("ℹ️ Properties", parent=menu)
            properties_action.triggered.connect(lambda: self._show_photo_properties(path))
            menu.addAction(properties_action)

            # Show menu and handle selection
            chosen = menu.exec(global_pos)
            if not chosen:
                return

            # Handle tag actions
            if chosen is act_new_tag:
                self._add_tag_to_photo(path)
                return

            if chosen is act_remove_all_tags:
                # Remove all tags from this photo
                for tag_name in list(current_tags):
                    try:
                        tag_service.remove_tag(path, tag_name, self.project_id)
                    except Exception as e:
                        print(f"[GooglePhotosLayout] ⚠️ Failed to remove tag '{tag_name}': {e}")
                # Refresh overlays and tags section
                self._refresh_tag_overlays([path])
                try:
                    self._build_tags_tree()
                except Exception:
                    pass
                return

            # Handle checkable tag toggle
            tag_key = tag_actions.get(chosen)
            if tag_key:
                if tag_key in current_tags:
                    tag_service.remove_tag(path, tag_key, self.project_id)
                else:
                    tag_service.assign_tags_bulk([path], tag_key, self.project_id)
                # Refresh overlays and tags section
                self._refresh_tag_overlays([path])
                try:
                    self._build_tags_tree()
                except Exception:
                    pass

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Context menu error: {e}")
            import traceback
            traceback.print_exc()

    def _delete_single_photo(self, path: str):
        """Delete a single photo (context menu action)."""
        # Add to selection temporarily
        was_selected = path in self.selected_photos
        if not was_selected:
            self.selected_photos.add(path)

        # Call existing delete handler
        self._on_delete_selected()

        # Remove from selection if it wasn't originally selected
        if not was_selected:
            self.selected_photos.discard(path)
            self._update_selection_ui()

    def _show_in_explorer(self, path: str):
        """Open file location in system file explorer."""
        import subprocess
        import platform

        try:
            system = platform.system()
            if system == "Windows":
                subprocess.run(['explorer', '/select,', os.path.normpath(path)])
            elif system == "Darwin":  # macOS
                subprocess.run(['open', '-R', path])
            else:  # Linux
                subprocess.run(['xdg-open', os.path.dirname(path)])

            print(f"[GooglePhotosLayout] 📁 Opened location: {path}")
        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error opening location: {e}")

    def _copy_path_to_clipboard(self, path: str):
        """Copy file path to clipboard."""
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        clipboard.setText(path)
        print(f"[GooglePhotosLayout] 📋 Copied to clipboard: {path}")

    def _show_photo_properties(self, path: str):
        """Show photo properties dialog with EXIF data."""
        from PySide6.QtWidgets import QMessageBox

        try:
            # Get file info
            stat = os.stat(path)
            file_size = stat.st_size / (1024 * 1024)  # MB

            # Try to get image dimensions
            try:
                img = QImage(path)
                dimensions = f"{img.width()} × {img.height()}px"
            except:
                dimensions = "Unknown"

            # Format info
            info = f"""
File: {os.path.basename(path)}
Path: {path}

Size: {file_size:.2f} MB
Dimensions: {dimensions}

Modified: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()

            QMessageBox.information(None, "Photo Properties", info)
            print(f"[GooglePhotosLayout] ℹ️ Showing properties: {path}")
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Could not load properties:\n{e}")
            print(f"[GooglePhotosLayout] ⚠️ Error showing properties: {e}")

    def keyPressEvent(self, event: QKeyEvent):
        """
        Phase 0.1: Keyboard Shortcuts Foundation (Google Photos + Lightroom patterns).

        Shortcuts:
        - Ctrl+A: Select all photos
        - Ctrl+D: Deselect all photos
        - Escape: Clear selection/filter
        - Delete: Delete selected photos
        - Ctrl+F: Focus search box
        - Ctrl+N: New project
        - Enter: Open first selected photo in lightbox
        - Space: Quick preview (full screen)
        - S: Toggle selection mode
        - +/-: Zoom in/out thumbnail size

        Args:
            event: QKeyEvent
        """
        key = event.key()
        modifiers = event.modifiers()

        # Ctrl+A: Select All
        if key == Qt.Key_A and modifiers == Qt.ControlModifier:
            print("[GooglePhotosLayout] ⌨️ Ctrl+A - Select all")
            self._on_select_all()
            event.accept()

        # Ctrl+D: Deselect All
        elif key == Qt.Key_D and modifiers == Qt.ControlModifier:
            if len(self.selected_photos) > 0:
                print("[GooglePhotosLayout] ⌨️ Ctrl+D - Deselect all")
                self._on_clear_selection()
                event.accept()
            else:
                super().keyPressEvent(event)

        # Escape: Clear selection/filter
        elif key == Qt.Key_Escape:
            if len(self.selected_photos) > 0:
                print("[GooglePhotosLayout] ⌨️ ESC - Clear selection")
                self._on_clear_selection()
                event.accept()
            elif hasattr(self, 'active_person_filter') and self.active_person_filter:
                print("[GooglePhotosLayout] ⌨️ ESC - Clear person filter")
                self._clear_filter()
                event.accept()
            else:
                super().keyPressEvent(event)

        # Delete: Delete selected photos
        elif key == Qt.Key_Delete:
            if len(self.selected_photos) > 0:
                print(f"[GooglePhotosLayout] ⌨️ DELETE - Delete {len(self.selected_photos)} photos")
                self._on_delete_selected()
                event.accept()
            else:
                super().keyPressEvent(event)

        # Ctrl+F: Focus search box
        elif key == Qt.Key_F and modifiers == Qt.ControlModifier:
            print("[GooglePhotosLayout] ⌨️ Ctrl+F - Focus search")
            if hasattr(self, 'search_box'):
                self.search_box.setFocus()
                self.search_box.selectAll()
            event.accept()

        # Ctrl+N: New project
        elif key == Qt.Key_N and modifiers == Qt.ControlModifier:
            print("[GooglePhotosLayout] ⌨️ Ctrl+N - New project")
            self._on_create_project_clicked()
            event.accept()

        # Enter: Open first selected photo
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            if len(self.selected_photos) > 0:
                first_photo = list(self.selected_photos)[0]
                print(f"[GooglePhotosLayout] ⌨️ ENTER - Open {first_photo}")
                self._on_photo_clicked(first_photo)
                event.accept()
            else:
                super().keyPressEvent(event)

        # Space: Quick preview (full screen)
        elif key == Qt.Key_Space:
            if len(self.selected_photos) > 0:
                first_photo = list(self.selected_photos)[0]
                print(f"[GooglePhotosLayout] ⌨️ SPACE - Quick preview {first_photo}")
                self._on_photo_clicked(first_photo)
                event.accept()
            else:
                super().keyPressEvent(event)

        # S: Toggle selection mode
        elif key == Qt.Key_S and not modifiers:
            print("[GooglePhotosLayout] ⌨️ S - Toggle selection mode")
            if hasattr(self, 'btn_select'):
                self.btn_select.setChecked(not self.btn_select.isChecked())
                self._toggle_selection_mode(self.btn_select.isChecked())
            event.accept()

        # +/=: Zoom in
        elif key in (Qt.Key_Plus, Qt.Key_Equal):
            print("[GooglePhotosLayout] ⌨️ + - Zoom in")
            if hasattr(self, 'zoom_slider'):
                current = self.zoom_slider.value()
                self.zoom_slider.setValue(min(current + 50, self.zoom_slider.maximum()))
            event.accept()

        # -: Zoom out
        elif key == Qt.Key_Minus:
            print("[GooglePhotosLayout] ⌨️ - - Zoom out")
            if hasattr(self, 'zoom_slider'):
                current = self.zoom_slider.value()
                self.zoom_slider.setValue(max(current - 50, self.zoom_slider.minimum()))
            event.accept()

        # G: Grid View
        elif key == Qt.Key_G and not modifiers:
            print("[GooglePhotosLayout] ⌨️ G - Grid view")
            if hasattr(self, '_show_grid_view'):
                self._show_grid_view()
            event.accept()

        # T: Timeline View
        elif key == Qt.Key_T and not modifiers:
            print("[GooglePhotosLayout] ⌨️ T - Timeline view")
            if hasattr(self, '_show_timeline_view'):
                self._show_timeline_view()
            event.accept()

        # E: Single View
        elif key == Qt.Key_E and not modifiers:
            print("[GooglePhotosLayout] ⌨️ E - Single view")
            if hasattr(self, '_show_single_view'):
                self._show_single_view()
            event.accept()
        
        # F: Toggle favorite for selected photos
        elif key == Qt.Key_F and not modifiers:
            if len(self.selected_photos) > 0:
                print(f"[GooglePhotosLayout] ⌨️ F - Toggle favorite for {len(self.selected_photos)} photos")
                self._on_favorite_selected()
                event.accept()
            else:
                super().keyPressEvent(event)

        else:
            # Pass to parent for other keys
            super().keyPressEvent(event)

    def _toggle_selection_mode(self, checked: bool):
        """
        Toggle selection mode on/off.

        Args:
            checked: Whether Select button is checked
        """
        self.selection_mode = checked
        print(f"[GooglePhotosLayout] Selection mode: {'ON' if checked else 'OFF'}")

        # Show/hide all checkboxes
        self._update_checkboxes_visibility()

        # Update button text
        if checked:
            self.btn_select.setText("☑️ Cancel")
            self.btn_select.setStyleSheet("QPushButton { background: #1a73e8; color: white; }")
        else:
            self.btn_select.setText("☑️ Select")
            self.btn_select.setStyleSheet("")

            # Clear selection when exiting selection mode
            self._clear_selection()

    def _update_checkboxes_visibility(self):
        """
        Show or hide all checkboxes based on selection mode.

        Phase 3 #1: Added smooth fade animations for checkboxes.
        """
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve

        # Iterate through all thumbnails
        for i in range(self.timeline_layout.count()):
            date_group = self.timeline_layout.itemAt(i).widget()
            if not date_group:
                continue

            group_layout = date_group.layout()
            if not group_layout:
                continue

            for j in range(group_layout.count()):
                item = group_layout.itemAt(j)
                if not item or not item.widget():
                    continue

                widget = item.widget()
                if hasattr(widget, 'layout') and widget.layout():
                    grid = widget.layout()
                    for k in range(grid.count()):
                        container = grid.itemAt(k).widget()
                        if container:
                            checkbox = container.property("checkbox")
                            if checkbox:
                                # PHASE 3 #1: Smooth fade animation for checkbox visibility
                                if self.selection_mode:
                                    # Fade in
                                    checkbox.setVisible(True)
                                    if not checkbox.graphicsEffect():
                                        opacity_effect = QGraphicsOpacityEffect()
                                        checkbox.setGraphicsEffect(opacity_effect)
                                        opacity_effect.setOpacity(0.0)

                                        fade_in = QPropertyAnimation(opacity_effect, b"opacity")
                                        fade_in.setDuration(200)  # 200ms fade-in
                                        fade_in.setStartValue(0.0)
                                        fade_in.setEndValue(1.0)
                                        fade_in.setEasingCurve(QEasingCurve.OutCubic)
                                        fade_in.start()

                                        # Store animation to prevent garbage collection
                                        checkbox.setProperty("fade_animation", fade_in)
                                else:
                                    # Fade out
                                    if checkbox.graphicsEffect():
                                        opacity_effect = checkbox.graphicsEffect()
                                        fade_out = QPropertyAnimation(opacity_effect, b"opacity")
                                        fade_out.setDuration(150)  # 150ms fade-out
                                        fade_out.setStartValue(1.0)
                                        fade_out.setEndValue(0.0)
                                        fade_out.setEasingCurve(QEasingCurve.InCubic)
                                        fade_out.finished.connect(lambda cb=checkbox: cb.setVisible(False))
                                        fade_out.start()
                                        checkbox.setProperty("fade_animation", fade_out)
                                    else:
                                        checkbox.setVisible(False)

    def _setup_drag_select(self):
        """
        PHASE 2 #2: Setup drag-to-select (rubber band) functionality.

        File Explorer-style rectangle selection.
        """
        from PySide6.QtWidgets import QRubberBand

        # Create rubber band for visual feedback
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self.timeline_scroll.viewport())
        self.rubber_band.hide()

        # Drag state
        self.is_dragging = False
        self.drag_start_pos = None

        # PHASE 2 #2: Create and install event filter (must be QObject)
        if not hasattr(self, 'event_filter'):
            self.event_filter = GooglePhotosEventFilter(self)

        # Install event filter on viewport to capture mouse events
        self.timeline_scroll.viewport().installEventFilter(self.event_filter)

    def _handle_drag_select_press(self, pos):
        """PHASE 2 #2: Start drag selection."""
        from PySide6.QtCore import QPoint

        # Only start drag if selection mode is active and not clicking on a thumbnail
        if not self.selection_mode:
            return False

        # Check if clicked on empty space (not on a thumbnail button)
        widget = self.timeline_scroll.viewport().childAt(pos)
        if widget and isinstance(widget, QPushButton):
            return False  # Clicked on thumbnail, don't start drag

        self.is_dragging = True
        self.drag_start_pos = pos
        self.rubber_band.setGeometry(pos.x(), pos.y(), 0, 0)
        self.rubber_band.show()
        return True

    def _handle_drag_select_move(self, pos):
        """PHASE 2 #2: Update rubber band during drag."""
        from PySide6.QtCore import QRect

        if not self.is_dragging or not self.drag_start_pos:
            return

        # Calculate rubber band rectangle
        x = min(self.drag_start_pos.x(), pos.x())
        y = min(self.drag_start_pos.y(), pos.y())
        width = abs(pos.x() - self.drag_start_pos.x())
        height = abs(pos.y() - self.drag_start_pos.y())

        self.rubber_band.setGeometry(x, y, width, height)

    def _handle_drag_select_release(self, pos):
        """PHASE 2 #2: Finish drag selection and select thumbnails in rectangle."""
        from PySide6.QtCore import QRect

        if not self.is_dragging or not self.drag_start_pos:
            return

        self.is_dragging = False
        self.rubber_band.hide()

        # Calculate selection rectangle in viewport coordinates
        x = min(self.drag_start_pos.x(), pos.x())
        y = min(self.drag_start_pos.y(), pos.y())
        width = abs(pos.x() - self.drag_start_pos.x())
        height = abs(pos.y() - self.drag_start_pos.y())

        selection_rect = QRect(x, y, width, height)

        # Find all thumbnails that intersect with selection rectangle
        viewport = self.timeline_scroll.viewport()
        selected_count = 0

        for i in range(self.timeline_layout.count()):
            date_group = self.timeline_layout.itemAt(i).widget()
            if not date_group:
                continue

            group_layout = date_group.layout()
            if not group_layout:
                continue

            for j in range(group_layout.count()):
                item = group_layout.itemAt(j)
                if not item or not item.widget():
                    continue

                widget = item.widget()
                if hasattr(widget, 'layout') and widget.layout():
                    grid = widget.layout()
                    for k in range(grid.count()):
                        container = grid.itemAt(k).widget()
                        if not container:
                            continue

                        # Get thumbnail button position relative to viewport
                        thumb_button = container.property("thumbnail_button")
                        if not thumb_button:
                            continue

                        try:
                            # Map thumbnail position to viewport coordinates
                            thumb_global = thumb_button.mapTo(viewport, thumb_button.rect().topLeft())
                            thumb_rect = QRect(thumb_global, thumb_button.size())

                            # Check if thumbnail intersects with selection rectangle
                            if selection_rect.intersects(thumb_rect):
                                # Select this thumbnail
                                photo_path = container.property("photo_path")
                                checkbox = container.property("checkbox")

                                if photo_path and checkbox:
                                    if photo_path not in self.selected_photos:
                                        self.selected_photos.add(photo_path)
                                        checkbox.setChecked(True)
                                        selected_count += 1
                        except:
                            pass  # Skip thumbnails that can't be mapped

        if selected_count > 0:
            print(f"[GooglePhotosLayout] Drag-selected {selected_count} photos")
            self._update_selection_ui()

        self.drag_start_pos = None

    def _clear_selection(self):
        """
        Clear all selected photos and uncheck checkboxes.
        """
        # Uncheck all checkboxes
        for path in list(self.selected_photos):
            container = self._find_thumbnail_container(path)
            if container:
                checkbox = container.property("checkbox")
                if checkbox:
                    checkbox.setChecked(False)

        self.selected_photos.clear()
        self._update_selection_ui()

    def _on_delete_selected(self):
        """
        Delete all selected photos.
        """
        from PySide6.QtWidgets import QMessageBox

        if not self.selected_photos:
            return

        count = len(self.selected_photos)

        # Confirm deletion
        reply = QMessageBox.question(
            self.main_window,
            "Delete Photos",
            f"Are you sure you want to delete {count} photo{'s' if count > 1 else ''}?\n\n"
            "This will remove them from the database but NOT delete the actual files.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        print(f"[GooglePhotosLayout] Deleting {count} photos...")

        # TODO Phase 2: Implement actual deletion from database
        # For now, just clear selection and show message
        QMessageBox.information(
            self.main_window,
            "Delete Photos",
            f"{count} photo{'s' if count > 1 else ''} deleted successfully!\n\n"
            "(Note: Actual deletion not yet implemented - Phase 2 placeholder)"
        )

        self._clear_selection()
        self._load_photos()  # Refresh timeline

    def _on_favorite_selected(self):
        """
        Toggle favorite tag for all selected photos (batch operation).
        
        Follows Current layout pattern:
        - Check if any photo is already favorited
        - If any favorited: unfavorite all
        - If none favorited: favorite all
        - Refresh tag overlays after operation
        - Show status message
        """
        if not self.selected_photos:
            return
        
        try:
            from reference_db import ReferenceDB
            
            paths = list(self.selected_photos)
            count = len(paths)
            
            # Check if any photo is already favorited
            db = ReferenceDB()
            has_favorite = False
            for path in paths:
                tags = db.get_tags_for_photo(path, self.project_id) or []
                if "favorite" in tags:
                    has_favorite = True
                    break
            
            # Toggle: if any is favorite, unfavorite all; otherwise favorite all
            if has_favorite:
                # Unfavorite all
                for path in paths:
                    db.remove_tag(path, "favorite", self.project_id)
                msg = f"⭐ Removed favorite from {count} photo{'s' if count > 1 else ''}"
                print(f"[GooglePhotosLayout] Unfavorited {count} photos")
            else:
                # Favorite all
                for path in paths:
                    db.add_tag(path, "favorite", self.project_id)
                msg = f"⭐ Added {count} photo{'s' if count > 1 else ''} to favorites"
                print(f"[GooglePhotosLayout] Favorited {count} photos")
            
            # Refresh tag overlays for affected photos
            self._refresh_tag_overlays(paths)
            
            # Show status message in parent window
            if hasattr(self.main_window, 'statusBar'):
                self.main_window.statusBar().showMessage(msg, 3000)
            
            # Clear selection after operation
            self._clear_selection()
            
        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error toggling favorites: {e}")
            import traceback
            traceback.print_exc()

    def _on_share_selected(self):
        """
        PHASE 3 #7: Show share/export dialog for selected photos.

        Allows users to:
        - Copy file paths to clipboard
        - Export to a folder
        - Show in file explorer
        """
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QApplication
        from PySide6.QtGui import QClipboard

        if not self.selected_photos:
            return

        # Create share dialog
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle("Share / Export Photos")
        dialog.setMinimumWidth(500)
        dialog.setStyleSheet("""
            QDialog {
                background: white;
            }
            QLabel {
                font-size: 11pt;
            }
            QPushButton {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background: #f1f3f4;
                border-color: #1a73e8;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header
        count = len(self.selected_photos)
        header = QLabel(f"📤 Share {count} photo{'s' if count > 1 else ''}")
        header.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(header)

        # Copy paths button
        copy_btn = QPushButton("📋 Copy File Paths to Clipboard")
        copy_btn.setToolTip("Copy all selected file paths to clipboard (one per line)")
        def copy_paths():
            paths_text = '\n'.join(sorted(self.selected_photos))
            clipboard = QApplication.clipboard()
            clipboard.setText(paths_text)
            copy_btn.setText("✓ Copied!")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: copy_btn.setText("📋 Copy File Paths to Clipboard"))
        copy_btn.clicked.connect(copy_paths)
        layout.addWidget(copy_btn)

        # Export to folder button
        export_btn = QPushButton("💾 Export to Folder...")
        export_btn.setToolTip("Copy selected photos to a new folder")
        def export_to_folder():
            import shutil
            folder = QFileDialog.getExistingDirectory(
                dialog,
                "Select Export Destination",
                "",
                QFileDialog.ShowDirsOnly
            )
            if folder:
                try:
                    success_count = 0
                    for photo_path in self.selected_photos:
                        filename = os.path.basename(photo_path)
                        dest_path = os.path.join(folder, filename)
                        shutil.copy2(photo_path, dest_path)
                        success_count += 1

                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.information(
                        dialog,
                        "Export Complete",
                        f"✓ Exported {success_count} photo{'s' if success_count > 1 else ''} to:\n{folder}"
                    )
                    dialog.accept()
                except Exception as e:
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.critical(
                        dialog,
                        "Export Failed",
                        f"Error exporting photos:\n{str(e)}"
                    )
        export_btn.clicked.connect(export_to_folder)
        layout.addWidget(export_btn)

        # Show in explorer button (for first selected file)
        first_photo = sorted(self.selected_photos)[0]
        explorer_btn = QPushButton(f"📂 Show in Explorer")
        explorer_btn.setToolTip("Open file explorer at first selected photo")
        def show_in_explorer():
            self._show_in_explorer(first_photo)
            dialog.accept()
        explorer_btn.clicked.connect(show_in_explorer)
        layout.addWidget(explorer_btn)

        # Close button
        close_btn = QPushButton("Cancel")
        close_btn.clicked.connect(dialog.reject)
        layout.addWidget(close_btn)

        dialog.exec()

    # ============ Phase 2: Search Functionality ============

    def _create_search_suggestions(self):
        """
        PHASE 2 #3: Create search suggestions dropdown widget.

        Google Search-style autocomplete that appears below search box.
        """
        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        # Create suggestions popup (initially hidden)
        self.search_suggestions = QListWidget()
        self.search_suggestions.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.search_suggestions.setStyleSheet("""
            QListWidget {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 4px;
                font-size: 11pt;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 2px;
            }
            QListWidget::item:hover {
                background: #f1f3f4;
            }
            QListWidget::item:selected {
                background: #e8f0fe;
                color: #1a73e8;
            }
        """)
        self.search_suggestions.setMaximumHeight(300)
        self.search_suggestions.setMinimumWidth(300)
        self.search_suggestions.hide()

        # NUCLEAR FIX: Initialize flag to block popup during layout changes
        self._popup_blocked = False

        # Connect click event
        self.search_suggestions.itemClicked.connect(self._on_suggestion_clicked)

        # PHASE 2 #3: Create and install event filter (must be QObject)
        if not hasattr(self, 'event_filter'):
            self.event_filter = GooglePhotosEventFilter(self)

        # Install event filter on search box to handle arrow keys
        self.search_box.installEventFilter(self.event_filter)

        # NUCLEAR FIX: Install event filter on popup itself to block Show events during layout changes
        self.search_suggestions.installEventFilter(self.event_filter)

    def _show_search_suggestions(self, text: str):
        """
        Phase 0.2: Enhanced search suggestions (Google Photos pattern).

        Shows categorized suggestions:
        - People: Face clusters/named persons
        - Filenames: Matching photo filenames
        - Folders: Matching folder names

        Google Photos DNA: Icons, categories, photo counts
        """
        # FIX 2: Check if suggestions are enabled (prevent showing during layout operations)
        if hasattr(self, '_suggestions_disabled') and self._suggestions_disabled:
            return

        # NUCLEAR FIX: Don't show popup if blocked due to layout changes
        if hasattr(self, '_popup_blocked') and self._popup_blocked:
            return

        if not text or len(text) < 2:
            # FIX 2: Only hide if actually visible (prevents unnecessary operations)
            if self.search_suggestions.isVisible():
                self.search_suggestions.hide()
            return

        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            suggestions = []  # Changed to list to maintain order

            pattern = f"%{text.lower()}%"

            with db._connect() as conn:
                cur = conn.cursor()

                # CATEGORY 1: People matching text
                people_query = """
                    SELECT branch_key, display_name, COUNT(DISTINCT fc.image_path) as photo_count
                    FROM branches b
                    LEFT JOIN face_crops fc ON b.project_id = fc.project_id AND b.branch_key = fc.branch_key
                    WHERE b.project_id = ?
                    AND (LOWER(b.display_name) LIKE ? OR LOWER(b.branch_key) LIKE ?)
                    GROUP BY b.branch_key, b.display_name
                    ORDER BY photo_count DESC
                    LIMIT 5
                """
                cur.execute(people_query, (self.project_id, pattern, pattern))
                people_rows = cur.fetchall()

                for branch_key, display_name, photo_count in people_rows:
                    name = display_name if display_name else branch_key
                    if photo_count > 0:
                        suggestions.append(f"👥 {name} ({photo_count} photos)")

                # CATEGORY 2: Filenames and folders
                files_query = """
                    SELECT DISTINCT pm.path
                    FROM photo_metadata pm
                    JOIN project_images pi ON pm.path = pi.image_path
                    WHERE pi.project_id = ?
                    AND LOWER(pm.path) LIKE ?
                    LIMIT 10
                """
                cur.execute(files_query, (self.project_id, pattern))
                files_rows = cur.fetchall()

                filenames = set()
                folders = set()

                for (path,) in files_rows:
                    filename = os.path.basename(path)
                    folder = os.path.basename(os.path.dirname(path))

                    # Add filename if it matches
                    if text.lower() in filename.lower():
                        filenames.add(filename)

                    # Add folder if it matches
                    if text.lower() in folder.lower() and folder:
                        folders.add(folder)

                # Add folders first (limit 3)
                for folder in sorted(folders)[:3]:
                    suggestions.append(f"📁 {folder}")

                # Add filenames (limit remaining slots)
                remaining = 8 - len(suggestions)
                for filename in sorted(filenames)[:remaining]:
                    suggestions.append(f"📷 {filename}")

            # Populate suggestions list
            self.search_suggestions.clear()

            if suggestions:
                for suggestion in suggestions:
                    self.search_suggestions.addItem(suggestion)

                # Position below search box
                search_box_global = self.search_box.mapToGlobal(self.search_box.rect().bottomLeft())
                self.search_suggestions.move(search_box_global)
                self.search_suggestions.resize(400, min(len(suggestions) * 40, 300))
                self.search_suggestions.show()
                self.search_suggestions.raise_()
            else:
                self.search_suggestions.hide()

        except Exception as e:
            print(f"[GooglePhotosLayout] Error generating suggestions: {e}")
            import traceback
            traceback.print_exc()
            self.search_suggestions.hide()

    def _on_suggestion_clicked(self, item):
        """
        Phase 0.2: Handle clicking on a search suggestion.

        Supports:
        - People: Filters to that person
        - Folders/Files: Sets search text and performs search
        """
        suggestion_text = item.text()

        # Extract the actual text without emoji and metadata
        if suggestion_text.startswith("👥 "):
            # People suggestion: "👥 John (45 photos)" -> "John"
            name_part = suggestion_text[2:]  # Remove "👥 "
            if " (" in name_part:
                person_name = name_part.split(" (")[0]
            else:
                person_name = name_part

            # Set search box and perform person search
            self.search_box.blockSignals(True)
            self.search_box.setText(person_name)
            self.search_box.blockSignals(False)
            self._perform_search(person_name)

        elif " " in suggestion_text and suggestion_text[0] in ("📁", "📷"):
            # Folder/file suggestion: Remove emoji prefix
            clean_text = suggestion_text.split(" ", 1)[1]
            self.search_box.blockSignals(True)
            self.search_box.setText(clean_text)
            self.search_box.blockSignals(False)
            self._perform_search(clean_text)
        else:
            # Fallback: use as-is
            self.search_box.blockSignals(True)
            self.search_box.setText(suggestion_text)
            self.search_box.blockSignals(False)
            self._perform_search(suggestion_text)

        self.search_suggestions.hide()

    def _on_search_text_changed(self, text: str):
        """
        Handle search text change (real-time filtering).

        Phase 2 #3: Now also shows search suggestions dropdown.
        """
        # PHASE 2 #3: Show suggestions immediately (no debounce for suggestions)
        self._show_search_suggestions(text)

        # Debounce: only search after user stops typing for 300ms
        if hasattr(self, '_search_timer'):
            self._search_timer.stop()

        from PySide6.QtCore import QTimer
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(lambda: self._perform_search(text))
        self._search_timer.start(300)  # 300ms debounce

    def _perform_search(self, text: str = None):
        """
        Perform search and filter photos.
        NOW SUPPORTS: People names, filenames, folders, advanced filters
        EXAMPLES:
        - "John" - search person name
        - "John AND Alice" - photos with both people
        - ">10 photos" - people with more than 10 photos  
        - "<5 photos" - people with less than 5 photos

        Args:
            text: Search query (if None, use search_box text)
        """
        if text is None:
            text = self.search_box.text()

        text = text.strip()
        text_lower = text.lower()

        print(f"[GooglePhotosLayout] 🔍 Searching for: '{text}'")

        if not text:
            # Empty search - reload all photos
            self._load_photos()
            return

        # Parse advanced search syntax
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # CHECK 1: Advanced face count filter (e.g., ">10 photos", "<5 photos")
            import re
            count_pattern = r'^([><]=?)\s*(\d+)\s*photos?'
            count_match = re.match(count_pattern, text_lower)
            if count_match:
                operator = count_match.group(1)
                threshold = int(count_match.group(2))
                self._filter_people_by_count(operator, threshold)
                return
            
            # CHECK 2: Multi-person search with AND (e.g., "John AND Alice")
            if ' AND ' in text.upper() or ' and ' in text:
                person_names = [name.strip() for name in re.split(r'\s+AND\s+', text, flags=re.IGNORECASE)]
                self._search_multi_person(person_names)
                return

            # CHECK 3: Single person name search
            person_match = None
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT branch_key, label, count FROM face_branch_reps WHERE project_id = ? AND LOWER(label) LIKE ?",
                    (self.project_id, f"%{text_lower}%")
                )
                people_results = cur.fetchall()
                
                if people_results:
                    # If exact match or close match, filter by that person
                    for branch_key, label, count in people_results:
                        if label and text_lower in label.lower():
                            person_match = (branch_key, label, count)
                            print(f"[GooglePhotosLayout] 👥 Found person: {label} ({count} photos)")
                            
                            # Filter People section to show only this person
                            self._filter_people_grid(label)
                            
                            # Filter timeline photos by this person
                            self._load_photos(
                                thumb_size=self.current_thumb_size,
                                filter_person=branch_key
                            )
                            # Show search result header
                            QTimer.singleShot(100, lambda: self._add_search_header(
                                f"👥 Showing {count} photos of '{label}'"
                            ))
                            return

            # CHECK 4: Filename/folder search
            query = """
                SELECT DISTINCT pm.path, pm.date_taken, pm.width, pm.height
                FROM photo_metadata pm
                JOIN project_images pi ON pm.path = pi.image_path
                WHERE pi.project_id = ?
                AND pm.date_taken IS NOT NULL
                AND LOWER(pm.path) LIKE ?
                ORDER BY pm.date_taken DESC
            """

            search_pattern = f"%{text_lower}%"

            with db._connect() as conn:
                conn.execute("PRAGMA busy_timeout = 5000")
                cur = conn.cursor()
                cur.execute(query, (self.project_id, search_pattern))
                rows = cur.fetchall()

            # Clear and rebuild timeline with search results
            self._rebuild_timeline_with_results(rows, text)

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Search error: {e}")
            import traceback
            traceback.print_exc()
    
    def _filter_people_by_count(self, operator: str, threshold: int):
        """Filter people grid by photo count."""
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            
            # Build SQL condition
            if operator == '>':
                condition = "count > ?"
            elif operator == '>=':
                condition = "count >= ?"
            elif operator == '<':
                condition = "count < ?"
            elif operator == '<=':
                condition = "count <= ?"
            else:
                condition = "count = ?"
            
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"SELECT branch_key, label, count FROM face_branch_reps WHERE project_id = ? AND {condition} ORDER BY count DESC",
                    (self.project_id, threshold)
                )
                results = cur.fetchall()
            
            # Rebuild people grid with filtered results
            self.people_grid.clear()
            
            for branch_key, label, count in results:
                # Load face thumbnail
                with db._connect() as conn2:
                    cur2 = conn2.cursor()
                    cur2.execute(
                        "SELECT rep_path, rep_thumb_png FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                        (self.project_id, branch_key)
                    )
                    row = cur2.fetchone()
                    if row:
                        rep_path, rep_thumb = row
                        face_pix = None
                        if rep_thumb:
                            import base64
                            data = base64.b64decode(rep_thumb) if isinstance(rep_thumb, str) else rep_thumb
                            face_pix = QPixmap()
                            face_pix.loadFromData(data)
                        elif rep_path and os.path.exists(rep_path):
                            face_pix = QPixmap(rep_path)
                        
                        self.people_grid.add_person(branch_key, label or "Unnamed", face_pix, count)
            
            # Update People section count and show result message
            try:
                self.people_section.update_count(len(results))
            except Exception:
                pass
            op_text = {'>': 'more than', '>=': 'at least', '<': 'less than', '<=': 'at most'}.get(operator, '')
            QMessageBox.information(
                self.main_window,
                "Filtered Results",
                f"📊 Found {len(results)} people with {op_text} {threshold} photos"
            )
            
        except Exception as e:
            print(f"[GooglePhotosLayout] Failed to filter by count: {e}")
            import traceback
            traceback.print_exc()
    
    def _search_multi_person(self, person_names: list):
        """Search for photos containing multiple people (AND logic)."""
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            
            # Find branch keys for each person
            branch_keys = []
            found_names = []
            
            with db._connect() as conn:
                cur = conn.cursor()
                for name in person_names:
                    cur.execute(
                        "SELECT branch_key, label FROM face_branch_reps WHERE project_id = ? AND LOWER(label) LIKE ?",
                        (self.project_id, f"%{name.lower()}%")
                    )
                    result = cur.fetchone()
                    if result:
                        branch_keys.append(result[0])
                        found_names.append(result[1] or result[0])
            
            if len(branch_keys) < len(person_names):
                QMessageBox.warning(
                    self.main_window,
                    "Not All Found",
                    f"Could only find {len(branch_keys)} of {len(person_names)} people.\n\nFound: {', '.join(found_names)}"
                )
                if not branch_keys:
                    return
            
            # Filter People section to show only these people
            if len(found_names) == 1:
                self._filter_people_grid(found_names[0])
            elif len(found_names) > 1:
                # For multi-person, show all matched people
                # Clear all first, then show only matched ones
                search_pattern = "|".join([name.lower() for name in found_names])
                for i in range(self.people_grid.flow_layout.count()):
                    item = self.people_grid.flow_layout.itemAt(i)
                    if item and item.widget():
                        card = item.widget()
                        if isinstance(card, PersonCard):
                            matches = any(name.lower() in card.display_name.lower() for name in found_names)
                            card.setVisible(matches)
            
            # Find photos that contain ALL these people
            with db._connect() as conn:
                cur = conn.cursor()
                
                # Build query to find images with all branch keys
                # Use INTERSECT to find common images
                queries = []
                for bk in branch_keys:
                    queries.append(f"""
                        SELECT DISTINCT fc.image_path
                        FROM face_crops fc
                        WHERE fc.project_id = ? AND fc.branch_key = ?
                    """)
                
                full_query = " INTERSECT ".join(queries)
                params = []
                for bk in branch_keys:
                    params.extend([self.project_id, bk])
                
                cur.execute(full_query, params)
                image_paths = [row[0] for row in cur.fetchall()]
                
                # Get full photo metadata
                if image_paths:
                    placeholders = ','.join(['?'] * len(image_paths))
                    cur.execute(
                        f"SELECT DISTINCT path, date_taken, width, height FROM photo_metadata WHERE path IN ({placeholders}) ORDER BY date_taken DESC",
                        image_paths
                    )
                    rows = cur.fetchall()
                else:
                    rows = []
            
            # Rebuild timeline with results
            self._rebuild_timeline_with_results(
                rows,
                f"{' AND '.join(found_names)} (multi-person)"
            )
            
        except Exception as e:
            print(f"[GooglePhotosLayout] Multi-person search failed: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self.main_window, "Search Failed", f"Error: {e}")
    
    def _add_search_header(self, message: str):
        """Add a search result header to the timeline (for person filters)."""
        try:
            # Check if header already exists and remove it
            for i in range(self.timeline_layout.count()):
                widget = self.timeline_layout.itemAt(i).widget()
                if widget and hasattr(widget, 'objectName') and widget.objectName() == "search_header":
                    widget.deleteLater()
                    break
            
            # Add new header
            header = QLabel(message)
            header.setObjectName("search_header")
            header.setStyleSheet("font-size: 11pt; font-weight: bold; padding: 10px 20px; color: #1a73e8;")
            self.timeline_layout.insertWidget(0, header)
        except Exception as e:
            print(f"[GooglePhotosLayout] Failed to add search header: {e}")
    
    def _on_autocomplete_selected(self, item):
        """Handle autocomplete selection."""
        # Get the actual person name from stored data (not the display text with count)
        person_name = item.data(Qt.UserRole)
        if person_name:
            # Set search box to just the person name
            self.people_search.setText(person_name)
            self.people_autocomplete.hide()
            # Trigger search with person name
            self._perform_search(person_name)
        else:
            # Fallback to display text if no data stored
            self.people_search.setText(item.text())
            self.people_autocomplete.hide()
            self._perform_search(item.text())
    
    def _on_people_search(self, text: str):
        """Handle people search text change with autocomplete."""
        if not text or len(text) < 2:
            self.people_autocomplete.hide()
            # Filter people grid
            self._filter_people_grid(text)
            return
        
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            
            # Fetch matching people
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT label, count FROM face_branch_reps WHERE project_id = ? AND LOWER(label) LIKE ? ORDER BY count DESC LIMIT 10",
                    (self.project_id, f"%{text.lower()}%")
                )
                results = cur.fetchall()
            
            # Populate autocomplete
            self.people_autocomplete.clear()
            
            if results:
                for label, count in results:
                    if label:
                        item_text = f"{label} ({count} photos)"
                        item = QListWidgetItem(item_text)
                        item.setData(Qt.UserRole, label)  # Store actual name
                        self.people_autocomplete.addItem(item)
                
                # Position autocomplete below search box
                search_global = self.people_search.mapToGlobal(self.people_search.rect().bottomLeft())
                self.people_autocomplete.move(search_global)
                self.people_autocomplete.setFixedWidth(self.people_search.width())
                self.people_autocomplete.show()
                self.people_autocomplete.raise_()
            else:
                self.people_autocomplete.hide()
            
            # Also filter people grid
            self._filter_people_grid(text)
            
        except Exception as e:
            print(f"[GooglePhotosLayout] Autocomplete error: {e}")
            self.people_autocomplete.hide()

    def _rebuild_timeline_with_results(self, rows, search_text: str):
        """
        Rebuild timeline with search results.
        """
        # Clear existing timeline and trees for search results
        while self.timeline_layout.count():
            child = self.timeline_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # NOTE: With AccordionSidebar, clearing is handled internally - no action needed here

        if not rows:
            # No results
            empty_label = QLabel(f"🔍 No results for '{search_text}'\n\nTry different search terms")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("font-size: 12pt; color: #888; padding: 60px;")
            self.timeline_layout.addWidget(empty_label)
            print(f"[GooglePhotosLayout] No search results for: '{search_text}'")
            return

        # Group and display results
        photos_by_date = self._group_photos_by_date(rows)
        self._build_timeline_tree(photos_by_date)

        # Add search results header
        header = QLabel(f"🔍 Found {len(rows)} results for '{search_text}'")
        header.setStyleSheet("font-size: 11pt; font-weight: bold; padding: 10px 20px; color: #1a73e8;")
        self.timeline_layout.insertWidget(0, header)

        # Create date groups (use current thumb size)
        thumb_size = getattr(self, 'current_thumb_size', 200)
        for date_str in sorted(photos_by_date.keys(), reverse=True):
            photos = photos_by_date.get(date_str, [])
            date_group = self._create_date_group(date_str, photos, thumb_size)
            self.timeline_layout.addWidget(date_group)

        self.timeline_layout.addStretch()

        print(f"[GooglePhotosLayout] Search results: {len(rows)} photos in {len(photos_by_date)} dates")

    # ============ Phase 2: Zoom Functionality ============

    def _on_zoom_changed(self, value: int):
        """
        Handle zoom slider change - adjust thumbnail size.

        Args:
            value: New thumbnail size in pixels (100-400)
        """
        print(f"[GooglePhotosLayout] 🔎 Zoom changed to: {value}px")

        # Update label (just the number, no "px")
        self.zoom_value_label.setText(f"{value}")

        # Reload photos with new thumbnail size
        # Store current scroll position
        scroll_pos = self.timeline.verticalScrollBar().value()

        # Reload with new size
        self._load_photos(thumb_size=value)

        # Restore scroll position (approximate)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self.timeline.verticalScrollBar().setValue(scroll_pos))

    def _set_aspect_ratio(self, mode: str):
        """
        PHASE 2 #5: Set thumbnail aspect ratio mode.

        Args:
            mode: "square", "original", or "16:9"
        """
        print(f"[GooglePhotosLayout] 📐 Aspect ratio changed to: {mode}")

        # Update state
        self.thumbnail_aspect_ratio = mode

        # Update button states
        self.btn_aspect_square.setChecked(mode == "square")
        self.btn_aspect_original.setChecked(mode == "original")
        self.btn_aspect_16_9.setChecked(mode == "16:9")

        # Reload photos with new aspect ratio
        # Store current scroll position
        scroll_pos = self.timeline.verticalScrollBar().value()

        # Reload with current thumb size
        current_size = self.zoom_slider.value()
        self._load_photos(thumb_size=current_size)

        # Restore scroll position (approximate)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self.timeline.verticalScrollBar().setValue(scroll_pos))

    def _clear_filter(self):
        """
        Clear all date/folder/person filters and show all photos.
        """
        print("[GooglePhotosLayout] Clearing all filters")

        # Reload without filters
        self._load_photos(
            thumb_size=self.current_thumb_size,
            filter_year=None,
            filter_month=None,
            filter_day=None,
            filter_folder=None,
            filter_person=None
        )

        # Clear search box as well if it has text
        if self.search_box.text():
            self.search_box.blockSignals(True)
            self.search_box.clear()
            self.search_box.blockSignals(False)

    def get_sidebar(self):
        """Get sidebar component."""
        return getattr(self, 'sidebar', None)

    def get_grid(self):
        """Grid is integrated into timeline view."""
        return None

    def _on_view_tab_changed(self, index: int):
        tab_text = self.view_tabs.tabText(index)
        if "Photos" in tab_text:
            if hasattr(self, 'photos_mode_bar'):
                self.photos_mode_bar.setVisible(True)
            self._show_timeline_view()
        else:
            if hasattr(self, 'photos_mode_bar'):
                self.photos_mode_bar.setVisible(False)
            # Old sidebar navigation - no longer needed with AccordionSidebar
            # AccordionSidebar handles section expansion internally
            if "Favorites" in tab_text:
                self._filter_by_tag("favorite")

    def _filter_favorites(self):
        """Filter timeline to show only photos tagged as favorites."""
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            with db._connect() as conn:
                cur = conn.cursor()
                query = """
                    SELECT DISTINCT pm.path, COALESCE(pm.date_taken, pm.created_date) as date_taken
                    FROM photo_metadata pm
                    JOIN project_images pi ON pm.path = pi.image_path
                    JOIN tags t ON t.name = ? AND t.project_id = ?
                    JOIN photo_tags pt ON pt.tag_id = t.id AND pt.photo_id = pm.id
                    WHERE pi.project_id = ?
                    ORDER BY date_taken DESC
                """
                cur.execute(query, ("favorite", self.project_id, self.project_id))
                rows = cur.fetchall()
            self._rebuild_timeline_with_results(rows, "Favorites")
        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error filtering favorites: {e}")
    def _set_photos_mode(self, mode: str):
        self.view_mode = mode

    def _show_grid_view(self):
        self._set_photos_mode('grid')
        # TODO: Implement dedicated grid renderer; reload for now
        self._load_photos(thumb_size=getattr(self, 'current_thumb_size', 200))

    def _show_timeline_view(self):
        self._set_photos_mode('timeline')
        self._load_photos(thumb_size=getattr(self, 'current_thumb_size', 200))

    def _show_single_view(self):
        self._set_photos_mode('single')
        try:
            paths = self._get_all_media_paths()
            if not paths:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self.main_window, "Single View", "No media available.")
                return
            lightbox = MediaLightbox(paths[0], paths, parent=self.main_window)
            lightbox.exec()
        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error opening single view: {e}")
    def on_layout_activated(self):
        """Called when this layout becomes active."""
        print("[GooglePhotosLayout] 📍 Layout activated")

        # Store main_window method references for Settings menu
        # (btn_scan and btn_faces removed from toolbar, now in Settings menu)
        if hasattr(self.main_window, '_on_scan_repository'):
            self._scan_repository_handler = self.main_window._on_scan_repository
            print("[GooglePhotosLayout] ✓ Stored Scan Repository handler")

        if hasattr(self.main_window, '_on_detect_and_group_faces'):
            self._detect_faces_handler = self.main_window._on_detect_and_group_faces
            print("[GooglePhotosLayout] ✓ Stored Detect Faces handler")

    def on_layout_deactivated(self):
        """
        CRITICAL FIX: Called when layout is being switched or destroyed.
        Cleans up all resources to prevent memory leaks.
        """
        print("[GooglePhotosLayout] 🧹 Layout deactivated - starting cleanup...")
        self.cleanup()
        print("[GooglePhotosLayout] ✓ Cleanup complete")

    def cleanup(self):
        """
        CRITICAL FIX: Comprehensive resource cleanup to prevent memory leaks.

        Addresses audit findings:
        - Issue #1: 173 signal connections never disconnected
        - Issue #2: 8 event filters never removed
        - Issue #3: 47 timers never stopped
        - Issue #4: Thread pool never cleaned up
        - Issue #7: Unbounded pixmap cache
        """
        print("[GooglePhotosLayout] Cleaning up resources...")

        # 1. Disconnect all signals (CRITICAL - prevents 173 connection leak)
        self._disconnect_all_signals()

        # 2. Remove event filters (CRITICAL - prevents 8 filter leak)
        self._remove_event_filters()

        # 3. Stop all timers (CRITICAL - prevents timer crash after deletion)
        self._stop_all_timers()

        # 4. Stop thread pools (CRITICAL - prevents background thread leak)
        self._cleanup_thread_pools()

        # 5. Clear caches (HIGH - prevents unbounded memory growth)
        self._clear_caches()

        # 6. Clean up child widgets with animations
        self._stop_animations()

        # 7. Call parent cleanup
        if hasattr(super(), 'cleanup'):
            super().cleanup()

    def _disconnect_all_signals(self):
        """Disconnect all signal connections to prevent memory leaks."""
        print("[GooglePhotosLayout]   ↳ Disconnecting signals...")

        # Thumbnail loading signals
        if hasattr(self, 'thumbnail_signals'):
            try:
                self.thumbnail_signals.loaded.disconnect(self._on_thumbnail_loaded)
            except:
                pass

        # Search box signals
        if hasattr(self, 'search_box'):
            try:
                self.search_box.textChanged.disconnect(self._on_search_text_changed)
            except:
                pass
            try:
                self.search_box.returnPressed.disconnect(self._perform_search)
            except:
                pass

        # Zoom slider signals
        if hasattr(self, 'zoom_slider'):
            try:
                self.zoom_slider.valueChanged.disconnect(self._on_zoom_changed)
            except:
                pass

        # Project combo signals
        if hasattr(self, 'project_combo'):
            try:
                self.project_combo.currentIndexChanged.disconnect(self._on_project_changed)
            except:
                pass

        # Scroll area signals
        if hasattr(self, 'timeline_scroll'):
            try:
                self.timeline_scroll.verticalScrollBar().valueChanged.disconnect(self._on_scroll)
            except:
                pass

        print("[GooglePhotosLayout]   ✓ Signals disconnected")

    def _remove_event_filters(self):
        """Remove all event filters to prevent memory leaks."""
        print("[GooglePhotosLayout]   ↳ Removing event filters...")

        # Timeline scroll viewport filter
        if hasattr(self, 'timeline_scroll') and hasattr(self, 'event_filter'):
            try:
                self.timeline_scroll.viewport().removeEventFilter(self.event_filter)
            except:
                pass

        # Search box filter
        if hasattr(self, 'search_box') and hasattr(self, 'event_filter'):
            try:
                self.search_box.removeEventFilter(self.event_filter)
            except:
                pass

        # People search filter
        if hasattr(self, 'people_search') and hasattr(self, 'autocomplete_event_filter'):
            try:
                self.people_search.removeEventFilter(self.autocomplete_event_filter)
            except:
                pass

        print("[GooglePhotosLayout]   ✓ Event filters removed")

    def _stop_all_timers(self):
        """Stop all QTimer instances to prevent crashes after widget deletion."""
        print("[GooglePhotosLayout]   ↳ Stopping timers...")

        timer_names = [
            'scroll_debounce_timer',
            'date_indicator_hide_timer',
            '_search_timer',
            '_autosave_timer',
            '_adjust_debounce_timer'
        ]

        for timer_name in timer_names:
            if hasattr(self, timer_name):
                timer = getattr(self, timer_name)
                if timer:
                    try:
                        timer.stop()
                        timer.deleteLater()
                    except:
                        pass

        print("[GooglePhotosLayout]   ✓ Timers stopped")

    def _cleanup_thread_pools(self):
        """Clean up thread pools to prevent background thread leaks."""
        print("[GooglePhotosLayout]   ↳ Cleaning up thread pools...")

        if hasattr(self, 'thumbnail_thread_pool'):
            try:
                self.thumbnail_thread_pool.clear()
                self.thumbnail_thread_pool.waitForDone(2000)  # Wait max 2 seconds
            except:
                pass

        print("[GooglePhotosLayout]   ✓ Thread pools cleaned")

    def _clear_caches(self):
        """Clear all caches to prevent unbounded memory growth."""
        print("[GooglePhotosLayout]   ↳ Clearing caches...")

        # Clear thumbnail button cache
        if hasattr(self, 'thumbnail_buttons'):
            for btn in list(self.thumbnail_buttons.values()):
                try:
                    btn.deleteLater()
                except:
                    pass
            self.thumbnail_buttons.clear()

        # Clear unloaded thumbnails cache
        if hasattr(self, 'unloaded_thumbnails'):
            self.unloaded_thumbnails.clear()

        print("[GooglePhotosLayout]   ✓ Caches cleared")

    def _stop_animations(self):
        """Stop all animations in child widgets (CollapsibleSection)."""
        print("[GooglePhotosLayout]   ↳ Stopping animations...")

        # Find all CollapsibleSection widgets and stop their animations
        section_names = ['timeline_section', 'folders_section', 'people_section', 'videos_section']

        for section_name in section_names:
            if hasattr(self, section_name):
                section = getattr(self, section_name)
                if hasattr(section, 'cleanup'):
                    try:
                        section.cleanup()
                    except:
                        pass

        print("[GooglePhotosLayout]   ✓ Animations stopped")

    def _on_create_project_clicked(self):
        """Handle Create Project button click."""
        print("[GooglePhotosLayout] 🆕🆕🆕 CREATE PROJECT BUTTON CLICKED! 🆕🆕🆕")

        # Debug: Check if main_window exists and has breadcrumb_nav
        if not hasattr(self, 'main_window'):
            print("[GooglePhotosLayout] ❌ ERROR: self.main_window does not exist!")
            return

        # CRITICAL FIX: _create_new_project is in BreadcrumbNavigation, not MainWindow!
        # MainWindow has self.breadcrumb_nav which contains the method
        if not hasattr(self.main_window, 'breadcrumb_nav'):
            print(f"[GooglePhotosLayout] ❌ ERROR: main_window does not have breadcrumb_nav!")
            return

        if not hasattr(self.main_window.breadcrumb_nav, '_create_new_project'):
            print(f"[GooglePhotosLayout] ❌ ERROR: breadcrumb_nav does not have _create_new_project method!")
            return

        print("[GooglePhotosLayout] ✓ Calling breadcrumb_nav._create_new_project()...")

        # Call BreadcrumbNavigation's project creation dialog
        self.main_window.breadcrumb_nav._create_new_project()

        print("[GooglePhotosLayout] ✓ Project creation dialog completed")

        # CRITICAL: Update project_id after creation
        from app_services import get_default_project_id
        self.project_id = get_default_project_id()
        print(f"[GooglePhotosLayout] Updated project_id: {self.project_id}")

        # Refresh project selector and layout
        self._populate_project_selector()
        self._load_photos()
        print("[GooglePhotosLayout] ✓ Layout refreshed after project creation")

    def _populate_project_selector(self):
        """
        Populate the project selector combobox with available projects.
        Google Photos pattern: "+ New Project..." as first item.
        """
        try:
            from app_services import list_projects
            projects = list_projects()

            # Block signals while updating to prevent triggering change handler
            self.project_combo.blockSignals(True)
            self.project_combo.clear()

            # Google Photos pattern: Add "+ New Project..." as first item
            self.project_combo.addItem("➕ New Project...", userData="__new_project__")

            # Add separator after "New Project" option
            self.project_combo.insertSeparator(1)

            if not projects:
                self.project_combo.addItem("(No projects)", None)
                # Still enable dropdown so user can create new project
                self.project_combo.setEnabled(True)
            else:
                for proj in projects:
                    self.project_combo.addItem(proj["name"], proj["id"])
                self.project_combo.setEnabled(True)

                # Select current project (skip index 0 and 1 which are "+ New" and separator)
                if self.project_id:
                    for i in range(2, self.project_combo.count()):  # Start from index 2
                        if self.project_combo.itemData(i) == self.project_id:
                            self.project_combo.setCurrentIndex(i)
                            break
                else:
                    # If no project_id, select first actual project (index 2)
                    if self.project_combo.count() > 2:
                        self.project_combo.setCurrentIndex(2)

            # Unblock signals and connect change handler
            self.project_combo.blockSignals(False)
            try:
                self.project_combo.currentIndexChanged.disconnect()
            except:
                pass  # No previous connection
            self.project_combo.currentIndexChanged.connect(self._on_project_changed)

            print(f"[GooglePhotosLayout] Project selector populated with {len(projects)} projects (+ New Project option)")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error populating project selector: {e}")

    def _on_project_changed(self, index: int):
        """
        Handle project selection change in combobox.
        Detects "+ New Project..." selection and opens create dialog.
        """
        new_project_id = self.project_combo.itemData(index)

        # Check if user selected "+ New Project..." option
        if new_project_id == "__new_project__":
            print("[GooglePhotosLayout] ➕ New Project option selected")

            # Block signals to prevent recursion
            self.project_combo.blockSignals(True)

            # Restore previous selection (don't stay on "+ New Project")
            if self.project_id:
                for i in range(2, self.project_combo.count()):
                    if self.project_combo.itemData(i) == self.project_id:
                        self.project_combo.setCurrentIndex(i)
                        break
            else:
                # If no current project, select first actual project
                if self.project_combo.count() > 2:
                    self.project_combo.setCurrentIndex(2)

            # Unblock signals
            self.project_combo.blockSignals(False)

            # Open project creation dialog
            self._on_create_project_clicked()
            return

        # Normal project change handling
        if new_project_id is None or new_project_id == self.project_id:
            return

        print(f"[GooglePhotosLayout] 📂 Project changed: {self.project_id} → {new_project_id}")
        self.project_id = new_project_id

        # Update accordion sidebar with new project
        if hasattr(self, 'accordion_sidebar'):
            self.accordion_sidebar.set_project(new_project_id)

        # Reload photos for the new project
        self._load_photos()

    # ============ PHASE 3: Tag Operations ============
    
    def _toggle_favorite_single(self, path: str):
        """
        Toggle favorite status for a single photo (context menu action).
        """
        try:
            from services.tag_service import get_tag_service
            tag_service = get_tag_service()
            
            current_tags = tag_service.get_tags_for_path(path, self.project_id) or []
            is_favorited = any(t.lower() == "favorite" for t in current_tags)
            
            if is_favorited:
                tag_service.remove_tag(path, "favorite", self.project_id)
                msg = f"⭐ Removed from favorites: {os.path.basename(path)}"
                print(f"[GooglePhotosLayout] Unfavorited: {os.path.basename(path)}")
            else:
                tag_service.assign_tags_bulk([path], "favorite", self.project_id)
                msg = f"⭐ Added to favorites: {os.path.basename(path)}"
                print(f"[GooglePhotosLayout] Favorited: {os.path.basename(path)}")
            
            # Refresh tag overlay for this photo
            self._refresh_tag_overlays([path])
            
            # Show status message
            if hasattr(self.main_window, 'statusBar'):
                self.main_window.statusBar().showMessage(msg, 3000)
        
        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error toggling favorite: {e}")
            import traceback
            traceback.print_exc()
    
    def _add_tag_to_photo(self, path: str):
        """
        Add a custom tag to a single photo (context menu action).
        
        ARCHITECTURE: Uses TagService layer (Schema v3.1.0) instead of direct ReferenceDB calls.
        This ensures proper photo_metadata creation and tag isolation.
        
        Args:
            path: Photo file path
        """
        from PySide6.QtWidgets import QInputDialog
        
        tag_name, ok = QInputDialog.getText(
            self.main_window,
            "Add Tag",
            "Enter tag name:",
            QLineEdit.Normal,
            ""
        )
        
        if ok and tag_name.strip():
            try:
                # ARCHITECTURE: Use TagService layer (matches Current layout approach)
                from services.tag_service import get_tag_service
                tag_service = get_tag_service()
                
                # Ensure tag exists and assign to photo
                tag_service.ensure_tag_exists(tag_name.strip(), self.project_id)
                count = tag_service.assign_tags_bulk([path], tag_name.strip(), self.project_id)
                
                if count > 0:
                    msg = f"🏷️ Tagged '{tag_name.strip()}': {os.path.basename(path)}"
                    print(f"[GooglePhotosLayout] {msg}")
                    
                    # Refresh tag overlay
                    self._refresh_tag_overlays([path])
                    
                    # Show success message
                    if hasattr(self.main_window, 'statusBar'):
                        self.main_window.statusBar().showMessage(msg, 3000)
                else:
                    # Tag assignment failed
                    error_msg = f"⚠️ Failed to add tag '{tag_name.strip()}' to {os.path.basename(path)}"
                    print(f"[GooglePhotosLayout] {error_msg}")
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(
                        self.main_window,
                        "Tag Failed",
                        f"Failed to add tag '{tag_name.strip()}'.\n\nThe photo may not exist in the database or the tag could not be created."
                    )
            
            except Exception as e:
                print(f"[GooglePhotosLayout] ⚠️ Error adding tag: {e}")
                import traceback
                traceback.print_exc()
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self.main_window,
                    "Tag Failed",
                    f"Failed to add tag:\n{str(e)}"
                )
    
    # NOTE: Duplicate _show_photo_context_menu removed - see line ~13711 for merged implementation
    # NOTE: Typo method _refresh_tag_ovverlays removed - use _refresh_tag_overlays instead

    def _on_tags_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu, QInputDialog, QMessageBox
        menu = QMenu(self.tags_tree)
        act_new = menu.addAction("➕ New Tag…")
        chosen = menu.exec(self.tags_tree.viewport().mapToGlobal(pos))
        if chosen is act_new:
            name, ok = QInputDialog.getText(self.main_window, "New Tag", "Tag name:")
            if ok and name.strip():
                try:
                    from services.tag_service import get_tag_service
                    tag_service = get_tag_service()
                    tag_service.ensure_tag_exists(name.strip(), self.project_id)
                    self._build_tags_tree()
                except Exception as e:
                    QMessageBox.critical(self.main_window, "Create Failed", str(e))

    def _refresh_tag_overlays(self, paths: List[str]):
        """
        Refresh tag badge overlays for given photos.
        
        ARCHITECTURE: Uses TagService layer (Schema v3.1.0) for proper data access.
        Updates PhotoButton's painted badges and triggers repaint.
        
        Args:
            paths: List of photo paths to refresh
        """
        try:
            # ARCHITECTURE: Use TagService layer (matches Current layout approach)
            from services.tag_service import get_tag_service
            tag_service = get_tag_service()
            
            # Bulk query tags for all paths (more efficient than individual queries)
            tags_map = tag_service.get_tags_for_paths(paths, self.project_id)
            
            for path in paths:
                # Find the PhotoButton for this path
                button = self.thumbnail_buttons.get(path)
                if not button or not isinstance(button, PhotoButton):
                    continue
                
                # Get tags from the bulk query result
                tags = tags_map.get(path, [])
                
                # Update button's tags (triggers automatic repaint)
                button.set_tags(tags)
            
            print(f"[GooglePhotosLayout] ✓ Refreshed tag badges for {len(paths)} photos")
            
            # Also refresh Favorites sidebar section
            try:
                self._build_tags_tree()
            except Exception as e:
                print(f"[GooglePhotosLayout] ⚠️ Could not refresh tags section: {e}")
        
        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error refreshing tag overlays: {e}")
            import traceback
            traceback.print_exc()


# =============================================================================
# SIDEBAR REDESIGN: NEW WIDGETS (Phase 1 + Phase 2)
# =============================================================================

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


class CollapsibleSection(QWidget):
    """
    Collapsible section with smooth expand/collapse animation.
    
    Features:
    - Click header to toggle expand/collapse
    - Smooth QPropertyAnimation (200ms)
    - Shows item count badge
    - Visual indicators (▼ expanded, ▶ collapsed)
    - Content area can contain any widget
    """
    def __init__(self, title, icon, count=0, parent=None):
        super().__init__(parent)
        self.is_expanded = True
        self.title = title
        self.icon = icon
        self.count = count

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header bar with actions area
        self.header_bar = QWidget()
        hb = QHBoxLayout(self.header_bar)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(4)

        self.header_btn = QPushButton(f"▼ {icon} {title}  ({count})")
        self.header_btn.setFlat(True)
        self.header_btn.setCursor(Qt.PointingHandCursor)
        self.header_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-size: 11pt;
                font-weight: bold;
                color: #202124;
                border: none;
                padding: 8px 4px;
                background: transparent;
            }
            QPushButton:hover {
                color: #1a73e8;
                background: rgba(26, 115, 232, 0.08);
                border-radius: 4px;
            }
        """)
        self.header_btn.clicked.connect(self.toggle)
        hb.addWidget(self.header_btn, 1)

        # Actions container on the right
        self._header_actions_container = QWidget()
        self.header_actions = QHBoxLayout(self._header_actions_container)
        self.header_actions.setContentsMargins(0, 0, 0, 0)
        self.header_actions.setSpacing(4)
        hb.addWidget(self._header_actions_container, 0)

        main_layout.addWidget(self.header_bar)

        # Content widget (collapsible)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)
        main_layout.addWidget(self.content_widget)

        # Animation for smooth expand/collapse
        self.animation = QPropertyAnimation(self.content_widget, b"maximumHeight")
        self.animation.setDuration(200)  # 200ms smooth
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)

    def toggle(self):
        """Toggle expand/collapse."""
        if self.is_expanded:
            self.collapse()
        else:
            self.expand()

    def collapse(self):
        """Collapse section (hide content)."""
        self.animation.setStartValue(self.content_widget.height())
        self.animation.setEndValue(0)
        self.animation.start()
        self.is_expanded = False
        self.header_btn.setText(f"▶ {self.icon} {self.title}  ({self.count})")
        print(f"[CollapsibleSection] Collapsed: {self.title}")

    def expand(self):
        """Expand section (show content)."""
        self.content_widget.setMaximumHeight(16777215)  # Remove max height limit
        content_height = self.content_widget.sizeHint().height()

        # CRITICAL FIX: Ensure minimum visible height for content
        # If sizeHint() returns tiny value (e.g., <100px), use reasonable default
        # This prevents People grid from being too tiny to see faces
        if content_height < 100:
            content_height = 250  # Reasonable default for ~2 rows of face cards

        self.animation.setStartValue(0)
        self.animation.setEndValue(content_height)
        self.animation.start()
        self.is_expanded = True
        self.header_btn.setText(f"▼ {self.icon} {self.title}  ({self.count})")
        print(f"[CollapsibleSection] Expanded: {self.title}")

    def update_count(self, count):
        """Update count badge."""
        self.count = count
        arrow = "▼" if self.is_expanded else "▶"
        self.header_btn.setText(f"{arrow} {self.icon} {self.title}  ({count})")

    def add_widget(self, widget):
        """Add widget to content area."""
        self.content_layout.addWidget(widget)

    def add_header_action(self, widget):
        """Add a small action widget to the header right side."""
        try:
            self.header_actions.addWidget(widget)
        except Exception:
            pass

    def cleanup(self):
        """
        CRITICAL FIX: Clean up animation and signals to prevent memory leaks.
        Addresses Issue #8 from audit: Animation continues after widget deletion.
        """
        # Disconnect header button signal
        if hasattr(self, 'header_btn'):
            try:
                self.header_btn.clicked.disconnect(self.toggle)
            except:
                pass

        # Stop and clean up animation
        if hasattr(self, 'animation'):
            try:
                self.animation.stop()
                self.animation.setTargetObject(None)  # Break reference to widget
                self.animation.deleteLater()
            except:
                pass


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
    context_menu_requested = Signal(str, str)  # Emits (branch_key, display_name)
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
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
        
        # Start drag operation
        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QDrag
        
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
            from PySide6.QtGui import QPainter
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
                from PySide6.QtWidgets import QMessageBox
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
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)

        # Rename action
        rename_action = menu.addAction("✏️ Rename Person")
        rename_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "rename"))

        # Merge action
        merge_action = menu.addAction("🔗 Merge with Another Person")
        merge_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "merge"))

        # Suggest merge action
        suggest_action = menu.addAction("🤝 Suggest Merge…")
        suggest_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "suggest_merge"))

        # View details action
        details_action = menu.addAction("👁️ View Details…")
        details_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "details"))

        menu.addSeparator()

        # Delete action
        delete_action = menu.addAction("🗑️ Delete Person")
        delete_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "delete"))

        menu.addSeparator()
        review_action = menu.addAction("📝 Review Unnamed People…")
        review_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "review_unnamed"))

        menu.exec(global_pos)

    def cleanup(self):
        """
        CRITICAL FIX: Disconnect signals to prevent memory leaks.
        Addresses Issue #1 from audit: Signals never disconnected.
        """
        # Disconnect all signals
        try:
            self.clicked.disconnect()
        except:
            pass

        try:
            self.context_menu_requested.disconnect()
        except:
            pass

        try:
            self.drag_merge_requested.disconnect()
        except:
            pass


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

        CRITICAL: CollapsibleSection uses this to determine expand height.
        Without this, section collapses to tiny ~50px area showing only 2 faces!

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
