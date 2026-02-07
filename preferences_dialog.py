# preferences_dialog.py
# Version 10.01.01.03 dated 20260115

"""
Modern Preferences Dialog with Left Sidebar Navigation

Features:
- Apple/VS Code style left sidebar navigation
- 6 organized sections (General, Appearance, Scanning, Face Detection, Video, Advanced)
- Full i18n translation support
- Responsive layout with minimum 900x600 size
- Top-right Save/Cancel buttons
- Dark mode adaptive styling
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QStackedWidget, QWidget, QLabel, QCheckBox, QComboBox, QLineEdit,
    QTextEdit, QPushButton, QSpinBox, QFormLayout, QGroupBox, QMessageBox,
    QDialogButtonBox, QScrollArea, QFileDialog, QFrame
)
from PySide6.QtCore import Qt, QSize, QProcess, QRect
from PySide6.QtGui import QGuiApplication, QPainter, QColor, QPen, QFont
import sys
from pathlib import Path

from translation_manager import get_translation_manager, tr
from utils.qt_guards import connect_guarded
from config.face_detection_config import get_face_config


class BadgePreviewWidget(QWidget):
    """Live preview widget showing badge samples with current settings."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 120)
        self.setMaximumHeight(120)
        self.badge_size = 22
        self.badge_shape = "circle"
        self.badge_max = 4
        self.badge_shadow = True
        self.badge_enabled = True
    
    def update_settings(self, size, shape, max_count, shadow, enabled):
        """Update preview with new settings."""
        self.badge_size = size
        self.badge_shape = shape
        self.badge_max = max_count
        self.badge_shadow = shadow
        self.badge_enabled = enabled
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        
        # Background
        painter.fillRect(self.rect(), QColor(240, 240, 245))
        
        if not self.badge_enabled:
            painter.setPen(QColor(150, 150, 150))
            font = QFont()
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, "Badge overlays disabled")
            return
        
        # Draw sample thumbnail background
        thumb_rect = QRect(10, 10, 100, 100)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(200, 200, 200))
        painter.drawRoundedRect(thumb_rect, 4, 4)
        
        # Sample badges (favorite, face, tag)
        sample_badges = [
            ('★', QColor(255, 215, 0, 230), Qt.black),
            ('👤', QColor(70, 130, 180, 220), Qt.white),
            ('🏷', QColor(150, 150, 150, 230), Qt.white),
            ('⚑', QColor(255, 69, 0, 220), Qt.white),
            ('💼', QColor(0, 128, 255, 220), Qt.white)
        ]
        
        margin = 4
        x_right = thumb_rect.right() - margin - self.badge_size
        y_top = thumb_rect.top() + margin
        
        max_display = min(len(sample_badges), self.badge_max)
        
        for i in range(max_display):
            by = y_top + i * (self.badge_size + 4)
            badge_rect = QRect(x_right, by, self.badge_size, self.badge_size)
            
            # Shadow
            if self.badge_shadow:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, 100))
                shadow_rect = badge_rect.adjusted(2, 2, 2, 2)
                if self.badge_shape == 'square':
                    painter.drawRect(shadow_rect)
                elif self.badge_shape == 'rounded':
                    painter.drawRoundedRect(shadow_rect, 4, 4)
                else:
                    painter.drawEllipse(shadow_rect)
            
            # Badge
            ch, bg, fg = sample_badges[i]
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            if self.badge_shape == 'square':
                painter.drawRect(badge_rect)
            elif self.badge_shape == 'rounded':
                painter.drawRoundedRect(badge_rect, 4, 4)
            else:
                painter.drawEllipse(badge_rect)
            
            # Icon
            painter.setPen(QPen(fg))
            font = QFont()
            font.setPointSize(max(8, int(self.badge_size * 0.5)))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(badge_rect, Qt.AlignCenter, ch)
        
        # Overflow indicator
        if len(sample_badges) > self.badge_max:
            by = y_top + max_display * (self.badge_size + 4)
            more_rect = QRect(x_right, by, self.badge_size, self.badge_size)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(60, 60, 60, 220))
            if self.badge_shape == 'square':
                painter.drawRect(more_rect)
            elif self.badge_shape == 'rounded':
                painter.drawRoundedRect(more_rect, 4, 4)
            else:
                painter.drawEllipse(more_rect)
            painter.setPen(QPen(Qt.white))
            font2 = QFont()
            font2.setPointSize(max(7, int(self.badge_size * 0.45)))
            font2.setBold(True)
            painter.setFont(font2)
            painter.drawText(more_rect, Qt.AlignCenter, f"+{len(sample_badges) - self.badge_max}")
        
        # Info text
        painter.setPen(QColor(100, 100, 100))
        info_font = QFont()
        info_font.setPointSize(9)
        painter.setFont(info_font)
        info_text = f"Preview: {self.badge_shape} • {self.badge_size}px • max {self.badge_max}"
        painter.drawText(QRect(120, 10, 160, 100), Qt.AlignLeft | Qt.AlignVCenter, info_text)


class PreferencesDialog(QDialog):
    """Modern preferences dialog with sidebar navigation and i18n support."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.face_config = get_face_config()
        self.tm = get_translation_manager()

        # Load current language from settings
        current_lang = self.settings.get("language", "en")
        self.tm.set_language(current_lang)

        self.setWindowTitle(tr("preferences.title"))
        self.setMinimumSize(900, 600)

        # Track original settings for change detection
        self.original_settings = self._capture_settings()

        self._setup_ui()
        self._load_settings()
        self._apply_styling()

        # Check InsightFace model status after UI is ready
        self._check_model_status()

        # Check hash backfill status
        self._update_backfill_status()

        # Check similar shot status
        self._update_similar_shot_status()

    def _setup_ui(self):
        """Create the main UI layout with sidebar navigation."""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Left sidebar navigation
        self.sidebar = QListWidget()
        self.sidebar.setMaximumWidth(180)
        self.sidebar.setSpacing(2)
        self.sidebar.setFocusPolicy(Qt.NoFocus)
        # NOTE: Signal connection moved after content_stack creation to prevent AttributeError

        # Add navigation items
        nav_items = [
            ("preferences.nav.general", "⚙️"),
            ("preferences.nav.appearance", "🎨"),
            ("preferences.nav.scanning", "📁"),
            ("preferences.nav.gps_location", "🗺️"),
            ("preferences.nav.face_detection", "👤"),
            ("preferences.nav.visual_embeddings", "🔍"),
            ("preferences.nav.video", "🎬"),
            ("preferences.nav.advanced", "🔧")
        ]

        for key, icon in nav_items:
            item = QListWidgetItem(f"{icon}  {tr(key)}")
            item.setSizeHint(QSize(160, 40))
            self.sidebar.addItem(item)

        self.sidebar.setCurrentRow(0)

        main_layout.addWidget(self.sidebar)

        # Right side: content area with top button bar
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(20, 10, 20, 10)
        right_layout.setSpacing(10)

        # Top button bar (Save/Cancel)
        button_bar = QHBoxLayout()
        button_bar.addStretch()

        self.btn_cancel = QPushButton(tr("common.cancel"))
        self.btn_cancel.clicked.connect(self._on_cancel)

        self.btn_save = QPushButton(tr("common.save"))
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._on_save)

        button_bar.addWidget(self.btn_cancel)
        button_bar.addWidget(self.btn_save)

        right_layout.addLayout(button_bar)

        # Stacked widget for content panels
        self.content_stack = QStackedWidget()

        # Create all content panels
        self.content_stack.addWidget(self._create_general_panel())
        self.content_stack.addWidget(self._create_appearance_panel())
        self.content_stack.addWidget(self._create_scanning_panel())
        self.content_stack.addWidget(self._create_gps_location_panel())
        self.content_stack.addWidget(self._create_face_detection_panel())
        self.content_stack.addWidget(self._create_visual_embeddings_panel())
        self.content_stack.addWidget(self._create_video_panel())
        self.content_stack.addWidget(self._create_advanced_panel())

        right_layout.addWidget(self.content_stack)

        main_layout.addWidget(right_widget, 1)

        # Connect sidebar signal AFTER content_stack is created (prevents AttributeError)
        self.sidebar.currentRowChanged.connect(self._on_sidebar_changed)

    def _create_scrollable_panel(self, content_widget: QWidget) -> QScrollArea:
        """Wrap content in a scrollable area."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(content_widget)
        return scroll

    def _create_general_panel(self) -> QWidget:
        """Create General Settings panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        # Title
        title = QLabel(tr("preferences.general.title"))
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        layout.addWidget(title)

        # Skip unchanged photos
        self.chk_skip = QCheckBox(tr("preferences.general.skip_unchanged"))
        self.chk_skip.setToolTip(tr("preferences.general.skip_unchanged_hint"))
        layout.addWidget(self.chk_skip)

        # Use EXIF dates
        self.chk_exif = QCheckBox(tr("preferences.general.use_exif_dates"))
        self.chk_exif.setToolTip(tr("preferences.general.use_exif_dates_hint"))
        layout.addWidget(self.chk_exif)

        layout.addStretch()

        return self._create_scrollable_panel(widget)

    def _create_appearance_panel(self) -> QWidget:
        """Create Appearance panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        # Title
        title = QLabel(tr("preferences.appearance.title"))
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        layout.addWidget(title)

        # Dark mode
        self.chk_dark = QCheckBox(tr("preferences.appearance.dark_mode"))
        self.chk_dark.setToolTip(tr("preferences.appearance.dark_mode_hint"))
        layout.addWidget(self.chk_dark)

        # Language selector
        lang_group = QGroupBox()
        lang_layout = QFormLayout(lang_group)
        lang_layout.setSpacing(10)

        self.cmb_language = QComboBox()
        self.cmb_language.setToolTip(tr("preferences.appearance.language_hint"))

        # Populate available languages
        for lang_code, lang_name in self.tm.get_available_languages():
            self.cmb_language.addItem(lang_name, lang_code)

        # Set current language
        current_index = self.cmb_language.findData(self.tm.current_language)
        if current_index >= 0:
            self.cmb_language.setCurrentIndex(current_index)

        lang_layout.addRow(tr("preferences.appearance.language") + ":", self.cmb_language)
        layout.addWidget(lang_group)

        # Badge overlays
        badge_group = QGroupBox(tr("preferences.appearance.badge_overlays"))
        badge_form = QFormLayout(badge_group)
        badge_form.setSpacing(10)

        self.chk_badge_overlays = QCheckBox(tr("preferences.appearance.badge_enable"))
        badge_form.addRow(self.chk_badge_overlays)

        self.spin_badge_size = QSpinBox()
        self.spin_badge_size.setRange(12, 64)
        self.spin_badge_size.setSuffix(" px")
        badge_form.addRow(tr("preferences.appearance.badge_size") + ":", self.spin_badge_size)

        self.cmb_badge_shape = QComboBox()
        self.cmb_badge_shape.addItems(["circle", "rounded", "square"])
        badge_form.addRow(tr("preferences.appearance.badge_shape") + ":", self.cmb_badge_shape)

        self.spin_badge_max = QSpinBox()
        self.spin_badge_max.setRange(1, 9)
        badge_form.addRow(tr("preferences.appearance.badge_max_count") + ":", self.spin_badge_max)

        self.chk_badge_shadow = QCheckBox(tr("preferences.appearance.badge_shadow"))
        badge_form.addRow(self.chk_badge_shadow)

        # Live preview widget
        self.badge_preview = BadgePreviewWidget()
        badge_form.addRow("", self.badge_preview)
        
        # Wire live updates
        self.chk_badge_overlays.toggled.connect(self._update_badge_preview)
        self.spin_badge_size.valueChanged.connect(self._update_badge_preview)
        self.cmb_badge_shape.currentIndexChanged.connect(self._update_badge_preview)
        self.spin_badge_max.valueChanged.connect(self._update_badge_preview)
        self.chk_badge_shadow.toggled.connect(self._update_badge_preview)

        layout.addWidget(badge_group)
        # Cache settings group
        cache_group = QGroupBox(tr("preferences.cache.title"))
        cache_layout = QVBoxLayout(cache_group)
        cache_layout.setSpacing(10)

        self.chk_cache = QCheckBox(tr("preferences.cache.enabled"))
        self.chk_cache.setToolTip(tr("preferences.cache.enabled_hint"))
        cache_layout.addWidget(self.chk_cache)

        cache_size_layout = QFormLayout()
        self.cmb_cache_size = QComboBox()
        self.cmb_cache_size.setEditable(True)
        self.cmb_cache_size.setToolTip(tr("preferences.cache.size_mb_hint"))
        for size in ["100", "250", "500", "1000", "2000"]:
            self.cmb_cache_size.addItem(size)

        cache_size_layout.addRow(tr("preferences.cache.size_mb") + ":", self.cmb_cache_size)
        cache_layout.addLayout(cache_size_layout)

        self.chk_cache_cleanup = QCheckBox(tr("preferences.cache.auto_cleanup"))
        self.chk_cache_cleanup.setToolTip(tr("preferences.cache.auto_cleanup_hint"))
        cache_layout.addWidget(self.chk_cache_cleanup)

        # Cache management buttons
        cache_btn_row = QWidget()
        cache_btn_layout = QHBoxLayout(cache_btn_row)
        cache_btn_layout.setContentsMargins(0, 8, 0, 0)

        btn_cache_stats = QPushButton("📊 Show Cache Stats")
        btn_cache_stats.setToolTip("View detailed thumbnail cache statistics")
        btn_cache_stats.setMaximumWidth(150)
        btn_cache_stats.clicked.connect(self._show_cache_stats)

        btn_purge_cache = QPushButton("🗑️ Purge Old Entries")
        btn_purge_cache.setToolTip("Remove thumbnails older than 7 days")
        btn_purge_cache.setMaximumWidth(150)
        btn_purge_cache.clicked.connect(self._purge_cache)

        cache_btn_layout.addWidget(btn_cache_stats)
        cache_btn_layout.addWidget(btn_purge_cache)
        cache_btn_layout.addStretch()

        cache_layout.addWidget(cache_btn_row)

        layout.addWidget(cache_group)

        layout.addStretch()

        return self._create_scrollable_panel(widget)

    def _create_scanning_panel(self) -> QWidget:
        """Create Scanning Settings panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        # Title
        title = QLabel(tr("preferences.scanning.title"))
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        layout.addWidget(title)

        # Ignore folders
        ignore_group = QGroupBox(tr("preferences.scanning.ignore_folders"))
        ignore_layout = QVBoxLayout(ignore_group)

        hint_label = QLabel(tr("preferences.scanning.ignore_folders_hint"))
        hint_label.setStyleSheet("color: gray; font-size: 9pt;")
        ignore_layout.addWidget(hint_label)

        self.txt_ignore_folders = QTextEdit()
        self.txt_ignore_folders.setPlaceholderText(tr("preferences.scanning.ignore_folders_placeholder"))
        self.txt_ignore_folders.setMaximumHeight(150)
        ignore_layout.addWidget(self.txt_ignore_folders)

        layout.addWidget(ignore_group)

        # Devices
        devices_group = QGroupBox("Devices")
        devices_layout = QVBoxLayout(devices_group)
        self.chk_device_auto_refresh = QCheckBox("Auto-detect device connections")
        self.chk_device_auto_refresh.setToolTip(
            "Automatically detect when mobile devices are connected/disconnected.\n\n"
            "• Windows: Instant detection via system events + 30s polling backup\n"
            "• Other platforms: 30s polling only\n"
            "• Disabled: Manual refresh only (click refresh button)"
        )
        devices_layout.addWidget(self.chk_device_auto_refresh)
        layout.addWidget(devices_group)

        layout.addStretch()

        return self._create_scrollable_panel(widget)

    def _create_gps_location_panel(self) -> QWidget:
        """Create GPS & Location Settings panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        # Title
        title = QLabel("GPS & Location Settings")
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        layout.addWidget(title)

        # Location Clustering
        cluster_group = QGroupBox("🗺️ Location Clustering")
        cluster_layout = QFormLayout(cluster_group)
        cluster_layout.setSpacing(10)

        self.spin_cluster_radius = QSpinBox()
        self.spin_cluster_radius.setRange(1, 50)
        self.spin_cluster_radius.setSuffix(" km")
        self.spin_cluster_radius.setToolTip(
            "Photos within this radius will be grouped together.\n"
            "Smaller values = more precise grouping\n"
            "Larger values = fewer, broader location groups"
        )
        cluster_layout.addRow("Clustering Radius:", self.spin_cluster_radius)

        layout.addWidget(cluster_group)

        # Reverse Geocoding
        geocoding_group = QGroupBox("🌍 Reverse Geocoding")
        geocoding_layout = QVBoxLayout(geocoding_group)
        geocoding_layout.setSpacing(10)

        self.chk_reverse_geocoding = QCheckBox("Enable automatic location name lookup")
        self.chk_reverse_geocoding.setToolTip(
            "When enabled, GPS coordinates will be converted to location names\n"
            "(e.g., 'San Francisco, California, USA')\n"
            "Uses OpenStreetMap Nominatim API (free, no key required)"
        )
        geocoding_layout.addWidget(self.chk_reverse_geocoding)

        timeout_row = QWidget()
        timeout_layout = QHBoxLayout(timeout_row)
        timeout_layout.setContentsMargins(0, 0, 0, 0)
        
        timeout_label = QLabel("API Timeout:")
        self.spin_geocoding_timeout = QSpinBox()
        self.spin_geocoding_timeout.setRange(1, 10)
        self.spin_geocoding_timeout.setSuffix(" seconds")
        self.spin_geocoding_timeout.setToolTip(
            "Maximum time to wait for location name lookup.\n"
            "Lower = faster but may fail on slow connections\n"
            "Higher = more reliable but may slow down metadata display"
        )
        timeout_layout.addWidget(timeout_label)
        timeout_layout.addWidget(self.spin_geocoding_timeout)
        timeout_layout.addStretch()
        geocoding_layout.addWidget(timeout_row)

        self.chk_cache_location_names = QCheckBox("Cache location names (reduces API calls)")
        self.chk_cache_location_names.setToolTip(
            "Store location names in database to avoid repeated API lookups.\n"
            "Recommended for better performance and to respect API rate limits."
        )
        geocoding_layout.addWidget(self.chk_cache_location_names)

        layout.addWidget(geocoding_group)

        # Info box
        info_label = QLabel(
            "💡 <b>How it works:</b><br>"
            "• Photos with GPS EXIF data are automatically detected<br>"
            "• Locations are grouped by proximity using the clustering radius<br>"
            "• Click GPS coordinates in photo metadata to view on OpenStreetMap<br>"
            "• Location names are fetched using free Nominatim API (no key needed)"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            "QLabel { font-size: 10pt; color: #666; padding: 8px; "
            "background: #f0f0f0; border-radius: 4px; border-left: 4px solid #0078d4; }"
        )
        layout.addWidget(info_label)

        layout.addStretch()

        return self._create_scrollable_panel(widget)

    def _create_face_detection_panel(self) -> QWidget:
        """Create Face Detection panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        # Title
        title = QLabel(tr("preferences.face_detection.title"))
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        layout.addWidget(title)

        # InsightFace Model Selection
        model_group = QGroupBox("InsightFace Model")
        model_layout = QFormLayout(model_group)
        model_layout.setSpacing(10)

        self.cmb_insightface_model = QComboBox()
        self.cmb_insightface_model.addItem("buffalo_s (Fast, smaller memory)", "buffalo_s")
        self.cmb_insightface_model.addItem("buffalo_l (Balanced, recommended)", "buffalo_l")
        self.cmb_insightface_model.addItem("antelopev2 (Most accurate)", "antelopev2")
        self.cmb_insightface_model.setToolTip(
            "Choose the face detection model:\n"
            "• buffalo_s: Faster, uses less memory\n"
            "• buffalo_l: Best balance (recommended)\n"
            "• antelopev2: Most accurate but slower"
        )
        model_layout.addRow("Model:", self.cmb_insightface_model)

        layout.addWidget(model_group)

        # InsightFace Model Path Configuration
        model_path_group = QGroupBox("Model Installation")
        model_path_layout = QVBoxLayout(model_path_group)
        model_path_layout.setSpacing(8)

        # Custom model path row
        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)

        path_label = QLabel("Custom Models Path:")
        path_label.setToolTip(
            "Path to buffalo_l model directory (offline use).\n"
            "Leave empty to use default locations:\n"
            "  1. ./models/buffalo_l/\n"
            "  2. ~/.insightface/models/buffalo_l/\n\n"
            "For offline use, point to a folder containing buffalo_l models."
        )

        self.txt_model_path = QLineEdit()
        self.txt_model_path.setPlaceholderText("Leave empty to use default locations")

        btn_browse_models = QPushButton("Browse...")
        btn_browse_models.setMaximumWidth(80)
        btn_browse_models.clicked.connect(self._browse_models)

        btn_test_models = QPushButton("Test")
        btn_test_models.setMaximumWidth(60)
        btn_test_models.clicked.connect(self._test_model_path)

        path_layout.addWidget(path_label)
        path_layout.addWidget(self.txt_model_path, 1)
        path_layout.addWidget(btn_browse_models)
        path_layout.addWidget(btn_test_models)

        model_path_layout.addWidget(path_row)

        # Model status display
        self.lbl_model_status = QLabel("Checking model status...")
        self.lbl_model_status.setWordWrap(True)
        self.lbl_model_status.setStyleSheet("QLabel { padding: 6px; background-color: #f0f0f0; border-radius: 4px; }")
        model_path_layout.addWidget(self.lbl_model_status)

        # Model management buttons
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_download_models = QPushButton("📥 Download Models")
        self.btn_download_models.setToolTip("Download buffalo_l face detection models (~200MB)")
        self.btn_download_models.setMaximumWidth(150)
        self.btn_download_models.clicked.connect(self._download_models)

        self.btn_check_models = QPushButton("🔍 Check Status")
        self.btn_check_models.setToolTip("Check if models are properly installed")
        self.btn_check_models.setMaximumWidth(120)
        self.btn_check_models.clicked.connect(self._check_model_status)

        btn_layout.addWidget(self.btn_download_models)
        btn_layout.addWidget(self.btn_check_models)
        btn_layout.addStretch()

        model_path_layout.addWidget(btn_row)

        # Help text
        help_label = QLabel(
            "💡 <b>Note:</b> Face detection requires InsightFace library and buffalo_l models.<br>"
            "<b>Option 1 (Online):</b> Click 'Download Models' to download ~200MB to ./models/buffalo_l/<br>"
            "<b>Option 2 (Offline):</b> Use 'Browse' to select a folder containing pre-downloaded models"
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("QLabel { font-size: 10pt; color: #666; padding: 4px; }")
        model_path_layout.addWidget(help_label)

        layout.addWidget(model_path_group)

        # Detection Settings
        detection_group = QGroupBox("Detection Settings")
        detection_layout = QFormLayout(detection_group)
        detection_layout.setSpacing(10)

        self.spin_min_face_size = QSpinBox()
        self.spin_min_face_size.setRange(10, 100)
        self.spin_min_face_size.setSuffix(" px")
        self.spin_min_face_size.setToolTip("Minimum face size in pixels (smaller = detect smaller/distant faces)")
        detection_layout.addRow("Min Face Size:", self.spin_min_face_size)

        self.spin_confidence = QSpinBox()
        self.spin_confidence.setRange(30, 95)
        self.spin_confidence.setSuffix(" %")
        self.spin_confidence.setToolTip("Minimum confidence threshold (higher = fewer false positives)")
        detection_layout.addRow("Confidence:", self.spin_confidence)

        # Quality Filtering (ENHANCEMENT 2026-01-07)
        self.spin_min_quality = QSpinBox()
        self.spin_min_quality.setRange(0, 100)
        self.spin_min_quality.setSuffix(" /100")
        self.spin_min_quality.setToolTip(
            "Minimum quality score for faces (0 = disabled)\n"
            "0 = All faces (default)\n"
            "40 = Fair quality and above\n"
            "60 = Good quality (recommended for cleaner clusters)\n"
            "80 = Excellent quality only\n\n"
            "Quality based on: blur, lighting, size, aspect ratio, confidence"
        )
        detection_layout.addRow("Min Quality:", self.spin_min_quality)

        layout.addWidget(detection_group)

        # Clustering Settings
        cluster_group = QGroupBox("Face Clustering")
        cluster_layout = QFormLayout(cluster_group)
        cluster_layout.setSpacing(10)

        self.spin_cluster_eps = QSpinBox()
        self.spin_cluster_eps.setRange(20, 60)
        self.spin_cluster_eps.setSuffix(" %")
        self.spin_cluster_eps.setToolTip(
            "Clustering threshold (lower = stricter grouping):\n"
            "• 30-35%: Recommended (prevents grouping different people)\n"
            "• <30%: Very strict (may split same person)\n"
            "• >40%: Loose (may group different people)"
        )
        cluster_layout.addRow("Threshold (eps):", self.spin_cluster_eps)

        self.spin_min_samples = QSpinBox()
        self.spin_min_samples.setRange(1, 10)
        self.spin_min_samples.setToolTip("Minimum faces needed to form a cluster")
        cluster_layout.addRow("Min Samples:", self.spin_min_samples)

        self.chk_auto_cluster = QCheckBox("Auto-cluster after face detection scan")
        self.chk_auto_cluster.setToolTip("Automatically group faces after detection completes")
        cluster_layout.addRow("", self.chk_auto_cluster)

        layout.addWidget(cluster_group)

        # Per-Project Overrides
        project_group = QGroupBox("Per-Project Overrides")
        project_form = QFormLayout(project_group)
        project_form.setSpacing(10)

        from app_services import get_default_project_id
        self.current_project_id = get_default_project_id() or 1
        self.lbl_project_info = QLabel(f"Current project ID: {self.current_project_id}")
        project_form.addRow(self.lbl_project_info)

        self.chk_project_overrides = QCheckBox("Enable per-project overrides for this project")
        project_form.addRow("", self.chk_project_overrides)

        self.spin_proj_min_face = QSpinBox()
        self.spin_proj_min_face.setRange(10, 100)
        self.spin_proj_min_face.setSuffix(" px")
        project_form.addRow("Min Face Size (project):", self.spin_proj_min_face)

        self.spin_proj_confidence = QSpinBox()
        self.spin_proj_confidence.setRange(10, 95)
        self.spin_proj_confidence.setSuffix(" %")
        project_form.addRow("Confidence (project):", self.spin_proj_confidence)

        self.spin_proj_eps = QSpinBox()
        self.spin_proj_eps.setRange(20, 60)
        self.spin_proj_eps.setSuffix(" %")
        project_form.addRow("Threshold eps (project):", self.spin_proj_eps)

        self.spin_proj_min_samples = QSpinBox()
        self.spin_proj_min_samples.setRange(1, 10)
        project_form.addRow("Min Samples (project):", self.spin_proj_min_samples)

        self.chk_show_low_conf = QCheckBox("Show low-confidence detections in UI")
        project_form.addRow("", self.chk_show_low_conf)

        layout.addWidget(project_group)

        # Performance Settings
        perf_group = QGroupBox("Performance")
        perf_layout = QFormLayout(perf_group)
        perf_layout.setSpacing(10)

        self.spin_max_workers = QSpinBox()
        self.spin_max_workers.setRange(1, 16)
        self.spin_max_workers.setToolTip("Number of parallel face detection workers")
        perf_layout.addRow("Max Workers:", self.spin_max_workers)

        self.spin_batch_size = QSpinBox()
        self.spin_batch_size.setRange(10, 200)
        self.spin_batch_size.setToolTip("Number of images to process before saving to database")
        perf_layout.addRow("Batch Size:", self.spin_batch_size)

        # GPU Batch Processing (ENHANCEMENT 2026-01-07)
        self.chk_gpu_batch = QCheckBox("Enable GPU batch processing (2-5x speedup)")
        self.chk_gpu_batch.setToolTip("Process multiple images in parallel on GPU (requires CUDA)")
        perf_layout.addRow("", self.chk_gpu_batch)

        self.spin_gpu_batch_size = QSpinBox()
        self.spin_gpu_batch_size.setRange(1, 16)
        self.spin_gpu_batch_size.setToolTip("Number of images to process in single GPU call (4 optimal for 6-8GB VRAM)")
        perf_layout.addRow("GPU Batch Size:", self.spin_gpu_batch_size)

        self.spin_gpu_batch_min = QSpinBox()
        self.spin_gpu_batch_min.setRange(1, 100)
        self.spin_gpu_batch_min.setToolTip("Minimum photos to enable batch processing (overhead not worth it for small jobs)")
        perf_layout.addRow("GPU Batch Threshold:", self.spin_gpu_batch_min)

        layout.addWidget(perf_group)

        layout.addStretch()

        return self._create_scrollable_panel(widget)

    def _create_visual_embeddings_panel(self) -> QWidget:
        """Create Visual Embeddings / CLIP Model panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        # Title
        title = QLabel("🔍 Visual Embeddings")
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Visual embeddings enable semantic image search using AI vision models. "
            "Search photos by describing what you're looking for (e.g., 'sunset at beach', 'cat on sofa')."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-size: 10pt; padding: 4px;")
        layout.addWidget(desc)

        # CLIP Model Installation
        model_group = QGroupBox("CLIP Model Installation")
        model_layout = QVBoxLayout(model_group)
        model_layout.setSpacing(8)

        # Model location row
        location_row = QWidget()
        location_layout = QHBoxLayout(location_row)
        location_layout.setContentsMargins(0, 0, 0, 0)

        location_label = QLabel("Model Location:")
        location_label.setToolTip(
            "Path to CLIP model directory.\n"
            "Default: ./models/clip-vit-base-patch32/\n\n"
            "This is where CLIP model files are stored (~600MB)."
        )

        self.txt_clip_model_path = QLineEdit()
        self.txt_clip_model_path.setPlaceholderText("Default: ./models/clip-vit-base-patch32/")
        self.txt_clip_model_path.setReadOnly(True)  # Set by system

        btn_browse_clip = QPushButton("Browse...")
        btn_browse_clip.setMaximumWidth(80)
        btn_browse_clip.clicked.connect(self._browse_clip_models)

        btn_open_folder = QPushButton("Open Folder")
        btn_open_folder.setMaximumWidth(100)
        btn_open_folder.clicked.connect(self._open_clip_model_folder)

        location_layout.addWidget(location_label)
        location_layout.addWidget(self.txt_clip_model_path, 1)
        location_layout.addWidget(btn_browse_clip)
        location_layout.addWidget(btn_open_folder)

        model_layout.addWidget(location_row)

        # Model status display
        self.lbl_clip_status = QLabel("Checking CLIP model status...")
        self.lbl_clip_status.setWordWrap(True)
        self.lbl_clip_status.setStyleSheet("QLabel { padding: 8px; background-color: #f0f0f0; border-radius: 4px; }")
        model_layout.addWidget(self.lbl_clip_status)

        # Model management buttons
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_download_clip = QPushButton("📥 Download CLIP Model")
        self.btn_download_clip.setToolTip("Run download script to get CLIP model files (~600MB)")
        self.btn_download_clip.setMaximumWidth(180)
        self.btn_download_clip.clicked.connect(self._download_clip_model)

        self.btn_check_clip = QPushButton("🔍 Check Status")
        self.btn_check_clip.setToolTip("Check if CLIP model is properly installed")
        self.btn_check_clip.setMaximumWidth(120)
        self.btn_check_clip.clicked.connect(self._check_clip_status)

        btn_layout.addWidget(self.btn_download_clip)
        btn_layout.addWidget(self.btn_check_clip)
        btn_layout.addStretch()

        model_layout.addWidget(btn_row)

        # Help text
        help_label = QLabel(
            "💡 <b>Getting Started:</b><br>"
            "1. Click 'Download CLIP Model' to download OpenAI CLIP ViT-B/32 (~600MB)<br>"
            "2. Files will be saved to <code>./models/clip-vit-base-patch32/</code> (next to face detection models)<br>"
            "3. After download, restart the app or retry embedding extraction<br>"
            "4. Use 'Extract Embeddings' in the main window to process your photos"
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("QLabel { font-size: 10pt; color: #666; padding: 6px; background-color: #f9f9f9; border-radius: 4px; }")
        model_layout.addWidget(help_label)

        layout.addWidget(model_group)

        # Model Configuration
        config_group = QGroupBox("Model Configuration")
        config_layout = QFormLayout(config_group)
        config_layout.setSpacing(10)

        self.cmb_clip_variant = QComboBox()
        self.cmb_clip_variant.addItem("CLIP ViT-B/32 (512-D, Fast, Recommended)", "openai/clip-vit-base-patch32")
        self.cmb_clip_variant.addItem("CLIP ViT-B/16 (512-D, Better Quality)", "openai/clip-vit-base-patch16")
        self.cmb_clip_variant.addItem("CLIP ViT-L/14 (768-D, Best Quality)", "openai/clip-vit-large-patch14")
        self.cmb_clip_variant.setToolTip(
            "Choose CLIP model variant:\n"
            "• ViT-B/32: Fastest, balanced quality (recommended)\n"
            "• ViT-B/16: Slower, better image understanding\n"
            "• ViT-L/14: Slowest, best quality (requires more memory)"
        )
        self.cmb_clip_variant.setEnabled(False)  # Only ViT-B/32 supported for now
        config_layout.addRow("Model Variant:", self.cmb_clip_variant)

        self.cmb_clip_device = QComboBox()
        self.cmb_clip_device.addItem("Auto (Use GPU if available)", "auto")
        self.cmb_clip_device.addItem("CPU Only", "cpu")
        self.cmb_clip_device.addItem("CUDA GPU", "cuda")
        self.cmb_clip_device.addItem("Apple Metal (MPS)", "mps")
        self.cmb_clip_device.setToolTip(
            "Select compute device:\n"
            "• Auto: Automatically use GPU if available, else CPU\n"
            "• CPU: Always use CPU (slower but works everywhere)\n"
            "• CUDA: Use NVIDIA GPU (requires CUDA toolkit)\n"
            "• MPS: Use Apple Silicon GPU (M1/M2 Macs)"
        )
        config_layout.addRow("Compute Device:", self.cmb_clip_device)

        layout.addWidget(config_group)

        # Extraction Settings
        extraction_group = QGroupBox("Extraction Settings")
        extraction_layout = QFormLayout(extraction_group)
        extraction_layout.setSpacing(10)

        self.chk_auto_extract = QCheckBox("Automatically extract embeddings after photo scan")
        self.chk_auto_extract.setToolTip("Auto-extract visual embeddings when new photos are imported")
        extraction_layout.addRow("", self.chk_auto_extract)

        self.spin_extraction_batch = QSpinBox()
        self.spin_extraction_batch.setRange(10, 500)
        self.spin_extraction_batch.setValue(50)
        self.spin_extraction_batch.setSuffix(" photos")
        self.spin_extraction_batch.setToolTip("Number of photos to process in each batch")
        extraction_layout.addRow("Batch Size:", self.spin_extraction_batch)

        layout.addWidget(extraction_group)

        # GPU & Performance Section
        gpu_group = QGroupBox("GPU & Performance")
        gpu_layout = QFormLayout(gpu_group)
        gpu_layout.setSpacing(10)

        # GPU Device Status
        self.lbl_gpu_device = QLabel("Detecting...")
        self.lbl_gpu_device.setStyleSheet("font-weight: bold;")
        gpu_layout.addRow("GPU Device:", self.lbl_gpu_device)

        # GPU Memory
        self.lbl_gpu_memory = QLabel("—")
        gpu_layout.addRow("Available Memory:", self.lbl_gpu_memory)

        # Optimal Batch Size
        self.lbl_optimal_batch = QLabel("—")
        self.lbl_optimal_batch.setToolTip("Auto-tuned batch size based on GPU memory")
        gpu_layout.addRow("Optimal Batch Size:", self.lbl_optimal_batch)

        # FAISS Status
        self.lbl_faiss_status = QLabel("Checking...")
        self.lbl_faiss_status.setToolTip("FAISS enables fast approximate nearest neighbor search")
        gpu_layout.addRow("FAISS (Fast Search):", self.lbl_faiss_status)

        # Refresh GPU info button
        btn_refresh_gpu = QPushButton("🔄 Refresh")
        btn_refresh_gpu.setMaximumWidth(100)
        btn_refresh_gpu.clicked.connect(self._refresh_gpu_info)
        gpu_layout.addRow("", btn_refresh_gpu)

        layout.addWidget(gpu_group)

        # Statistics & Storage Section
        stats_group = QGroupBox("Statistics & Storage")
        stats_layout = QVBoxLayout(stats_group)
        stats_layout.setSpacing(10)

        # Quick coverage summary
        self.lbl_embedding_coverage = QLabel("Loading statistics...")
        self.lbl_embedding_coverage.setStyleSheet("font-size: 11pt;")
        stats_layout.addWidget(self.lbl_embedding_coverage)

        # Storage format info
        self.lbl_storage_format = QLabel("")
        self.lbl_storage_format.setStyleSheet("color: #666;")
        stats_layout.addWidget(self.lbl_storage_format)

        # Action buttons row
        stats_btn_row = QWidget()
        stats_btn_layout = QHBoxLayout(stats_btn_row)
        stats_btn_layout.setContentsMargins(0, 4, 0, 0)

        btn_open_dashboard = QPushButton("📊 Open Statistics Dashboard")
        btn_open_dashboard.setToolTip("View detailed embedding statistics, coverage, and storage info")
        btn_open_dashboard.clicked.connect(self._open_embedding_stats_dashboard)
        stats_btn_layout.addWidget(btn_open_dashboard)

        btn_migrate_float16 = QPushButton("⚡ Migrate to Float16")
        btn_migrate_float16.setToolTip("Convert legacy float32 embeddings to float16 (50% space savings)")
        btn_migrate_float16.clicked.connect(self._migrate_embeddings_to_float16)
        self.btn_migrate_float16 = btn_migrate_float16
        stats_btn_layout.addWidget(btn_migrate_float16)

        stats_btn_layout.addStretch()
        stats_layout.addWidget(stats_btn_row)

        layout.addWidget(stats_group)

        layout.addStretch()

        # Check CLIP status after UI is ready
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self._check_clip_status)
        QTimer.singleShot(200, self._refresh_gpu_info)
        QTimer.singleShot(300, self._refresh_embedding_stats)

        return self._create_scrollable_panel(widget)

    def _create_video_panel(self) -> QWidget:
        """Create Video Settings panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        # Title
        title = QLabel(tr("preferences.video.title"))
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        layout.addWidget(title)

        # FFprobe path
        ffprobe_group = QGroupBox(tr("preferences.video.ffprobe_path"))
        ffprobe_layout = QVBoxLayout(ffprobe_group)

        hint_label = QLabel(tr("preferences.video.ffprobe_path_hint"))
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: gray; font-size: 9pt; padding-bottom: 5px;")
        ffprobe_layout.addWidget(hint_label)

        path_layout = QHBoxLayout()
        self.txt_ffprobe_path = QLineEdit()
        self.txt_ffprobe_path.setPlaceholderText(tr("preferences.video.ffprobe_path_placeholder"))
        path_layout.addWidget(self.txt_ffprobe_path, 1)

        btn_browse = QPushButton(tr("common.browse"))
        btn_browse.clicked.connect(self._browse_ffprobe)
        path_layout.addWidget(btn_browse)

        btn_test = QPushButton(tr("common.test"))
        btn_test.clicked.connect(self._test_ffprobe)
        path_layout.addWidget(btn_test)

        ffprobe_layout.addLayout(path_layout)

        # Help note
        note_label = QLabel(tr("preferences.video.ffmpeg_note"))
        note_label.setWordWrap(True)
        note_label.setStyleSheet("font-size: 10pt; color: #666; padding: 8px; background: #f0f0f0; border-radius: 4px;")
        ffprobe_layout.addWidget(note_label)

        layout.addWidget(ffprobe_group)

        layout.addStretch()

        return self._create_scrollable_panel(widget)

    def _create_advanced_panel(self) -> QWidget:
        """Create Advanced Settings panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        # Title
        title = QLabel(tr("preferences.developer.title"))
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        layout.addWidget(title)

        # Diagnostics
        diag_group = QGroupBox(tr("preferences.diagnostics.title"))
        diag_layout = QVBoxLayout(diag_group)

        self.chk_decoder_warnings = QCheckBox(tr("preferences.diagnostics.decoder_warnings"))
        self.chk_decoder_warnings.setToolTip(tr("preferences.diagnostics.decoder_warnings_hint"))
        diag_layout.addWidget(self.chk_decoder_warnings)

        layout.addWidget(diag_group)

        # Developer tools
        dev_group = QGroupBox(tr("preferences.developer.title"))
        dev_layout = QVBoxLayout(dev_group)

        self.chk_db_debug = QCheckBox(tr("preferences.developer.db_debug"))
        self.chk_db_debug.setToolTip(tr("preferences.developer.db_debug_hint"))
        dev_layout.addWidget(self.chk_db_debug)

        self.chk_sql_echo = QCheckBox(tr("preferences.developer.sql_queries"))
        self.chk_sql_echo.setToolTip(tr("preferences.developer.sql_queries_hint"))
        dev_layout.addWidget(self.chk_sql_echo)

        layout.addWidget(dev_group)

        # Metadata extraction
        meta_group = QGroupBox(tr("preferences.metadata.title"))
        meta_layout = QFormLayout(meta_group)
        meta_layout.setSpacing(10)

        self.spin_workers = QComboBox()
        self.spin_workers.setEditable(True)
        self.spin_workers.setToolTip(tr("preferences.metadata.workers_hint"))
        for workers in ["2", "4", "6", "8", "12"]:
            self.spin_workers.addItem(workers)
        meta_layout.addRow(tr("preferences.metadata.workers") + ":", self.spin_workers)

        self.txt_meta_timeout = QComboBox()
        self.txt_meta_timeout.setEditable(True)
        self.txt_meta_timeout.setToolTip(tr("preferences.metadata.timeout_hint"))
        for timeout in ["4.0", "6.0", "8.0", "12.0"]:
            self.txt_meta_timeout.addItem(timeout)
        meta_layout.addRow(tr("preferences.metadata.timeout") + ":", self.txt_meta_timeout)

        self.txt_meta_batch = QComboBox()
        self.txt_meta_batch.setEditable(True)
        self.txt_meta_batch.setToolTip(tr("preferences.metadata.batch_size_hint"))
        for batch in ["50", "100", "200", "500"]:
            self.txt_meta_batch.addItem(batch)
        meta_layout.addRow(tr("preferences.metadata.batch_size") + ":", self.txt_meta_batch)

        self.chk_meta_auto = QCheckBox(tr("preferences.metadata.auto_run"))
        self.chk_meta_auto.setToolTip(tr("preferences.metadata.auto_run_hint"))
        meta_layout.addRow("", self.chk_meta_auto)

        layout.addWidget(meta_group)

        # Duplicate Management
        dup_group = QGroupBox(tr("preferences.duplicate.title"))
        dup_layout = QVBoxLayout(dup_group)
        dup_layout.setSpacing(10)

        # Description
        dup_desc = QLabel(tr("preferences.duplicate.description"))
        dup_desc.setWordWrap(True)
        dup_desc.setStyleSheet("color: #666; font-size: 11px;")
        dup_layout.addWidget(dup_desc)

        # Backfill status
        self.lbl_backfill_status = QLabel(tr("preferences.duplicate.status_checking"))
        self.lbl_backfill_status.setStyleSheet("color: #666; font-size: 11px;")
        dup_layout.addWidget(self.lbl_backfill_status)

        # Backfill button
        self.btn_run_backfill = QPushButton(tr("preferences.duplicate.run_backfill"))
        self.btn_run_backfill.setToolTip(tr("preferences.duplicate.run_backfill_hint"))
        self.btn_run_backfill.clicked.connect(self._on_run_hash_backfill)
        self.btn_run_backfill.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #666;
            }
        """)
        dup_layout.addWidget(self.btn_run_backfill)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #ddd;")
        dup_layout.addWidget(separator)

        # Similar Shot Stacks section
        similar_title = QLabel("<b>Similar Shot Detection</b>")
        similar_title.setStyleSheet("font-size: 12px; margin-top: 10px;")
        dup_layout.addWidget(similar_title)

        similar_desc = QLabel(
            "Groups burst photos, photo series, and similar poses using AI.\n"
            "Requires semantic embeddings to be generated first."
        )
        similar_desc.setWordWrap(True)
        similar_desc.setStyleSheet("color: #666; font-size: 11px;")
        dup_layout.addWidget(similar_desc)

        # Similar shot status
        self.lbl_similar_shot_status = QLabel("Checking status...")
        self.lbl_similar_shot_status.setStyleSheet("color: #666; font-size: 11px;")
        dup_layout.addWidget(self.lbl_similar_shot_status)

        # Similar shot button
        self.btn_run_similar_shots = QPushButton("🔍 Generate Similar Shot Stacks")
        self.btn_run_similar_shots.setToolTip(
            "Generate stacks for burst photos and similar shots using time proximity + visual similarity"
        )
        self.btn_run_similar_shots.clicked.connect(self._on_run_similar_shot_stacks)
        self.btn_run_similar_shots.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #666;
            }
        """)
        dup_layout.addWidget(self.btn_run_similar_shots)

        layout.addWidget(dup_group)

        layout.addStretch()

        return self._create_scrollable_panel(widget)

    def _apply_styling(self):
        """Apply dark/light mode adaptive styling."""
        is_dark = self.settings.get("dark_mode", False)

        if is_dark:
            sidebar_bg = "#2b2b2b"
            sidebar_item_bg = "#3c3c3c"
            sidebar_selected = "#4a90e2"
            content_bg = "#1e1e1e"
            text_color = "#e0e0e0"
        else:
            sidebar_bg = "#f5f5f5"
            sidebar_item_bg = "#ffffff"
            sidebar_selected = "#0078d4"
            content_bg = "#ffffff"
            text_color = "#000000"

        self.sidebar.setStyleSheet(f"""
            QListWidget {{
                background: {sidebar_bg};
                border: none;
                border-right: 1px solid #ccc;
                outline: none;
            }}
            QListWidget::item {{
                background: {sidebar_item_bg};
                color: {text_color};
                padding: 8px;
                margin: 2px 4px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background: {sidebar_selected};
                color: white;
            }}
            QListWidget::item:hover:!selected {{
                background: {sidebar_item_bg if is_dark else '#e8e8e8'};
            }}
        """)

        self.setStyleSheet(f"""
            QDialog {{
                background: {content_bg};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
        """)

    def _on_sidebar_changed(self, index: int):
        """Handle sidebar navigation changes."""
        self.content_stack.setCurrentIndex(index)

    def _load_settings(self):
        """Load current settings into UI controls."""
        # General
        self.chk_skip.setChecked(self.settings.get("skip_unchanged_photos", False))
        self.chk_exif.setChecked(self.settings.get("use_exif_for_date", True))

        # Appearance
        self.chk_dark.setChecked(self.settings.get("dark_mode", False))
        self.chk_cache.setChecked(self.settings.get("thumbnail_cache_enabled", True))
        self.cmb_cache_size.setCurrentText(str(self.settings.get("cache_size_mb", 500)))
        self.chk_cache_cleanup.setChecked(self.settings.get("cache_auto_cleanup", True))

        # Scanning
        ignore_folders = self.settings.get("ignore_folders", [])
        self.txt_ignore_folders.setPlainText("\n".join(ignore_folders))
        self.chk_device_auto_refresh.setChecked(self.settings.get("device_auto_refresh", True))

        # Face Detection
        model = self.face_config.get("insightface_model", "buffalo_l")
        index = self.cmb_insightface_model.findData(model)
        if index >= 0:
            self.cmb_insightface_model.setCurrentIndex(index)

        self.spin_min_face_size.setValue(self.face_config.get("min_face_size", 20))
        self.spin_confidence.setValue(int(self.face_config.get("confidence_threshold", 0.6) * 100))
        self.spin_min_quality.setValue(int(self.face_config.get("min_quality_score", 0.0)))
        self.spin_cluster_eps.setValue(int(self.face_config.get("clustering_eps", 0.35) * 100))
        self.spin_min_samples.setValue(self.face_config.get("clustering_min_samples", 2))
        self.chk_auto_cluster.setChecked(self.face_config.get("auto_cluster_after_scan", True))
        self.spin_max_workers.setValue(self.face_config.get("max_workers", 4))
        self.spin_batch_size.setValue(self.face_config.get("batch_size", 50))
        self.chk_gpu_batch.setChecked(self.face_config.get("enable_gpu_batch", True))
        self.spin_gpu_batch_size.setValue(self.face_config.get("gpu_batch_size", 4))
        self.spin_gpu_batch_min.setValue(self.face_config.get("gpu_batch_min_photos", 10))
        po = self.face_config.get("project_overrides", {})
        ov = po.get(str(self.current_project_id), {})
        self.chk_project_overrides.setChecked(bool(ov))
        self.spin_proj_min_face.setValue(int(ov.get("min_face_size", self.face_config.get("min_face_size", 20))))
        self.spin_proj_confidence.setValue(int((ov.get("confidence_threshold", self.face_config.get("confidence_threshold", 0.6))) * 100))
        self.spin_proj_eps.setValue(int(ov.get("clustering_eps", self.face_config.get("clustering_eps", 0.35)) * 100))
        self.spin_proj_min_samples.setValue(int(ov.get("clustering_min_samples", self.face_config.get("clustering_min_samples", 2))))
        self.chk_show_low_conf.setChecked(self.face_config.get("show_low_confidence", False))

        # InsightFace model path
        self.txt_model_path.setText(self.settings.get("insightface_model_path", ""))

        # CLIP / Visual Embeddings
        clip_variant = self.settings.get("clip_model_variant", "openai/clip-vit-base-patch32")
        clip_index = self.cmb_clip_variant.findData(clip_variant)
        if clip_index >= 0:
            self.cmb_clip_variant.setCurrentIndex(clip_index)

        clip_device = self.settings.get("clip_device", "auto")
        device_index = self.cmb_clip_device.findData(clip_device)
        if device_index >= 0:
            self.cmb_clip_device.setCurrentIndex(device_index)

        self.chk_auto_extract.setChecked(self.settings.get("clip_auto_extract", False))
        self.spin_extraction_batch.setValue(self.settings.get("clip_batch_size", 50))
        self.txt_clip_model_path.setText(self.settings.get("clip_model_path", ""))

        # Badge overlay settings
        self.chk_badge_overlays.setChecked(self.settings.get("badge_overlays_enabled", True))
        self.spin_badge_size.setValue(int(self.settings.get("badge_size_px", 22)))
        shape = str(self.settings.get("badge_shape", "circle")).lower()
        idx = self.cmb_badge_shape.findText(shape)
        if idx >= 0:
            self.cmb_badge_shape.setCurrentIndex(idx)
        self.spin_badge_max.setValue(int(self.settings.get("badge_max_count", 4)))
        self.chk_badge_shadow.setChecked(self.settings.get("badge_shadow", True))
        
        # Update preview with initial values
        self._update_badge_preview()
        
        # GPS & Location
        self.spin_cluster_radius.setValue(int(self.settings.get("gps_clustering_radius_km", 5)))
        self.chk_reverse_geocoding.setChecked(self.settings.get("gps_reverse_geocoding_enabled", True))
        self.spin_geocoding_timeout.setValue(int(self.settings.get("gps_geocoding_timeout_sec", 2)))
        self.chk_cache_location_names.setChecked(self.settings.get("gps_cache_location_names", True))

        # Advanced
        self.chk_decoder_warnings.setChecked(self.settings.get("show_decoder_warnings", False))
        self.chk_db_debug.setChecked(self.settings.get("db_debug_logging", False))
        self.chk_sql_echo.setChecked(self.settings.get("show_sql_queries", False))
        self.spin_workers.setCurrentText(str(self.settings.get("meta_workers", 4)))
        self.txt_meta_timeout.setCurrentText(str(self.settings.get("meta_timeout_secs", 8.0)))
        self.txt_meta_batch.setCurrentText(str(self.settings.get("meta_batch", 200)))
        self.chk_meta_auto.setChecked(self.settings.get("auto_run_backfill_after_scan", False))

    def _capture_settings(self) -> dict:
        """Capture current settings for change detection."""
        return {
            "skip_unchanged_photos": self.settings.get("skip_unchanged_photos", False),
            "use_exif_for_date": self.settings.get("use_exif_for_date", True),
            "dark_mode": self.settings.get("dark_mode", False),
            "language": self.settings.get("language", "en"),
            "thumbnail_cache_enabled": self.settings.get("thumbnail_cache_enabled", True),
            "cache_size_mb": self.settings.get("cache_size_mb", 500),
            "cache_auto_cleanup": self.settings.get("cache_auto_cleanup", True),
            "ignore_folders": self.settings.get("ignore_folders", []),
            "device_auto_refresh": self.settings.get("device_auto_refresh", True),
            "insightface_model": self.face_config.get("insightface_model", "buffalo_l"),
            "min_face_size": self.face_config.get("min_face_size", 20),
            "confidence_threshold": self.face_config.get("confidence_threshold", 0.6),
            "clustering_eps": self.face_config.get("clustering_eps", 0.35),
            "clustering_min_samples": self.face_config.get("clustering_min_samples", 2),
            "auto_cluster_after_scan": self.face_config.get("auto_cluster_after_scan", True),
            "face_max_workers": self.face_config.get("max_workers", 4),
            "face_batch_size": self.face_config.get("batch_size", 50),
            "min_quality_score": self.face_config.get("min_quality_score", 0.0),
            "enable_gpu_batch": self.face_config.get("enable_gpu_batch", True),
            "gpu_batch_size": self.face_config.get("gpu_batch_size", 4),
            "gpu_batch_min_photos": self.face_config.get("gpu_batch_min_photos", 10),
            "insightface_model_path": self.settings.get("insightface_model_path", ""),
            "ffprobe_path": self.settings.get("ffprobe_path", ""),
            "show_decoder_warnings": self.settings.get("show_decoder_warnings", False),
            "db_debug_logging": self.settings.get("db_debug_logging", False),
            "show_sql_queries": self.settings.get("show_sql_queries", False),
            "meta_workers": self.settings.get("meta_workers", 4),
            "meta_timeout_secs": self.settings.get("meta_timeout_secs", 8.0),
            "meta_batch": self.settings.get("meta_batch", 200),
            "auto_run_backfill_after_scan": self.settings.get("auto_run_backfill_after_scan", False),
        }

    def _on_run_hash_backfill(self):
        """Handle hash backfill button click."""
        try:
            # Import required modules
            from services.job_service import get_job_service
            from services.asset_service import AssetService
            from repository.photo_repository import PhotoRepository
            from repository.asset_repository import AssetRepository
            from repository.base_repository import DatabaseConnection
            from workers.hash_backfill_worker import create_hash_backfill_worker
            from ui.hash_backfill_progress_dialog import HashBackfillProgressDialog
            from PySide6.QtCore import QThreadPool

            # Get current project_id (try to get from main window)
            project_id = 1  # Default to project 1
            if hasattr(self.parent(), 'sidebar') and hasattr(self.parent().sidebar, 'project_id'):
                project_id = self.parent().sidebar.project_id
            elif hasattr(self.parent(), 'grid') and hasattr(self.parent().grid, 'project_id'):
                project_id = self.parent().grid.project_id

            # Initialize services to check status
            db_conn = DatabaseConnection()
            asset_repo = AssetRepository(db_conn)

            # Check how many photos need backfill
            total_without_instance = asset_repo.count_photos_without_instance(project_id)

            if total_without_instance == 0:
                QMessageBox.information(
                    self,
                    "Duplicate Detection Ready",
                    "All photos are already hashed and linked to assets.\n\n"
                    "Duplicate detection is ready to use!",
                    QMessageBox.Ok
                )
                return

            # Confirm with user
            reply = QMessageBox.question(
                self,
                "Prepare Duplicate Detection",
                f"Found {total_without_instance} photos that need processing.\n\n"
                f"This will compute SHA256 hashes and link photos to assets.\n"
                f"Estimated time: ~{int(total_without_instance / 1000) + 1} minutes\n\n"
                f"Continue?",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

            # Create progress dialog
            progress_dialog = HashBackfillProgressDialog(total_without_instance, self)

            # Enqueue job
            job_service = get_job_service()
            job_id = job_service.enqueue_job(
                kind='hash_backfill',
                payload={
                    'project_id': project_id
                },
                backend='local'
            )

            # Create worker
            worker = create_hash_backfill_worker(
                job_id=job_id,
                project_id=project_id,
                batch_size=500
            )

            # Connect worker signals to progress dialog (guarded against teardown)
            gen = int(getattr(self.parent() or self.window(), "_ui_generation", 0))
            connect_guarded(worker.signals.progress, self.parent() or self.window(), progress_dialog.update_progress, generation=gen, extra_valid=[progress_dialog])
            connect_guarded(worker.signals.finished, self.parent() or self.window(), progress_dialog.on_finished, generation=gen, extra_valid=[progress_dialog])
            connect_guarded(worker.signals.error, self.parent() or self.window(), progress_dialog.on_error, generation=gen, extra_valid=[progress_dialog])

            # Connect dialog cancel to worker (if needed - not implemented in worker yet)
            # progress_dialog.cancelled.connect(worker.cancel)

            # Start worker
            QThreadPool.globalInstance().start(worker)

            # Show progress dialog
            result = progress_dialog.exec()

            # Update status label
            self._update_backfill_status()

            if result == QDialog.Accepted:
                QMessageBox.information(
                    self,
                    "Backfill Complete",
                    f"Successfully processed {total_without_instance} photos!\n\n"
                    f"Duplicate detection is now ready to use.",
                    QMessageBox.Ok
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Backfill Error",
                f"Failed to start hash backfill:\n{str(e)}"
            )
            print(f"✗ Hash backfill error: {e}")
            import traceback
            traceback.print_exc()

    def _on_run_similar_shot_stacks(self):
        """Handle similar shot stack generation button click."""
        try:
            # Import required modules
            from services.job_service import get_job_service
            from services.semantic_embedding_service import get_semantic_embedding_service
            from repository.stack_repository import StackRepository
            from repository.base_repository import DatabaseConnection
            from workers.similar_shot_stack_worker import create_similar_shot_stack_worker
            from ui.similar_shot_progress_dialog import SimilarShotProgressDialog
            from PySide6.QtCore import QThreadPool

            # Get current project_id
            project_id = 1
            if hasattr(self.parent(), 'sidebar') and hasattr(self.parent().sidebar, 'project_id'):
                project_id = self.parent().sidebar.project_id
            elif hasattr(self.parent(), 'grid') and hasattr(self.parent().grid, 'project_id'):
                project_id = self.parent().grid.project_id

            # Check prerequisites - use getter to avoid duplicate instances
            db_conn = DatabaseConnection()
            embedding_service = get_semantic_embedding_service()
            stack_repo = StackRepository(db_conn)

            # Check if embeddings exist
            embedding_count = embedding_service.get_embedding_count()
            if embedding_count == 0:
                QMessageBox.warning(
                    self,
                    "Embeddings Required",
                    "Similar shot detection requires semantic embeddings.\n\n"
                    "Please generate embeddings first:\n"
                    "1. Go to Search → Semantic Search\n"
                    "2. Click 'Generate Embeddings'\n"
                    "3. Wait for completion\n"
                    "4. Return here to generate similar shot stacks",
                    QMessageBox.Ok
                )
                return

            # Check for existing stacks
            existing_stacks = stack_repo.count_stacks(project_id, stack_type="similar")

            # Confirm with user
            if existing_stacks > 0:
                reply = QMessageBox.question(
                    self,
                    "Regenerate Similar Shot Stacks",
                    f"Found {existing_stacks} existing similar shot stacks.\n\n"
                    f"This will clear and regenerate all similar shot stacks.\n"
                    f"Photos with embeddings: {embedding_count}\n"
                    f"Estimated time: ~{int(embedding_count / 500) + 1} minutes\n\n"
                    f"Continue?",
                    QMessageBox.Yes | QMessageBox.No
                )
            else:
                reply = QMessageBox.question(
                    self,
                    "Generate Similar Shot Stacks",
                    f"This will analyze photos and group similar shots.\n\n"
                    f"Photos with embeddings: {embedding_count}\n"
                    f"Time window: ±10 seconds\n"
                    f"Similarity threshold: 92%\n"
                    f"Minimum stack size: 3 photos\n\n"
                    f"Estimated time: ~{int(embedding_count / 500) + 1} minutes\n\n"
                    f"Continue?",
                    QMessageBox.Yes | QMessageBox.No
                )

            if reply != QMessageBox.Yes:
                return

            # Create progress dialog
            progress_dialog = SimilarShotProgressDialog(embedding_count, self)

            # Enqueue job
            job_service = get_job_service()
            job_id = job_service.enqueue_job(
                kind='similar_shot_stacks',
                payload={
                    'project_id': project_id
                },
                backend='cpu'
            )

            # Create worker with default parameters
            worker = create_similar_shot_stack_worker(
                job_id=job_id,
                project_id=project_id,
                time_window_seconds=10,      # ±10 seconds
                similarity_threshold=0.92,    # 92% similarity
                min_stack_size=3,             # At least 3 photos
                rule_version="1"
            )

            # Connect worker signals to progress dialog (guarded against teardown)
            gen = int(getattr(self.parent() or self.window(), "_ui_generation", 0))
            connect_guarded(worker.signals.progress, self.parent() or self.window(), progress_dialog.update_progress, generation=gen, extra_valid=[progress_dialog])
            connect_guarded(worker.signals.finished, self.parent() or self.window(), progress_dialog.on_finished, generation=gen, extra_valid=[progress_dialog])
            connect_guarded(worker.signals.error, self.parent() or self.window(), progress_dialog.on_error, generation=gen, extra_valid=[progress_dialog])

            # Start worker
            QThreadPool.globalInstance().start(worker)

            # Show progress dialog
            result = progress_dialog.exec()

            # Update status label
            self._update_similar_shot_status()

            if result == QDialog.Accepted:
                stats = progress_dialog.get_stats()
                QMessageBox.information(
                    self,
                    "Similar Shot Stacks Generated",
                    f"Successfully processed {stats['photos_considered']} photos!\n\n"
                    f"• {stats['stacks_created']} stacks created\n"
                    f"• {stats['memberships_created']} photo memberships\n"
                    f"• {stats['errors']} errors\n\n"
                    f"View stacks in the Duplicates dialog.",
                    QMessageBox.Ok
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Similar Shot Error",
                f"Failed to start similar shot generation:\n{str(e)}"
            )

    def _update_similar_shot_status(self):
        """Update similar shot status label."""
        try:
            from repository.stack_repository import StackRepository
            from repository.base_repository import DatabaseConnection
            from services.semantic_embedding_service import get_semantic_embedding_service

            # Get current project_id
            project_id = 1
            if hasattr(self.parent(), 'sidebar') and hasattr(self.parent().sidebar, 'project_id'):
                project_id = self.parent().sidebar.project_id
            elif hasattr(self.parent(), 'grid') and hasattr(self.parent().grid, 'project_id'):
                project_id = self.parent().grid.project_id

            # Check status - use getter to avoid duplicate instances
            db_conn = DatabaseConnection()
            stack_repo = StackRepository(db_conn)
            embedding_service = get_semantic_embedding_service()

            embedding_count = embedding_service.get_embedding_count()
            similar_stacks = stack_repo.count_stacks(project_id, stack_type="similar")

            if embedding_count == 0:
                self.lbl_similar_shot_status.setText("⚠ No embeddings - generate embeddings first")
                self.lbl_similar_shot_status.setStyleSheet("color: #ff9800; font-size: 11px;")
                self.btn_run_similar_shots.setEnabled(False)
            elif similar_stacks == 0:
                self.lbl_similar_shot_status.setText(f"Ready - {embedding_count} photos with embeddings")
                self.lbl_similar_shot_status.setStyleSheet("color: #666; font-size: 11px;")
                self.btn_run_similar_shots.setEnabled(True)
            else:
                self.lbl_similar_shot_status.setText(
                    f"✓ {similar_stacks} similar shot stacks generated ({embedding_count} photos analyzed)"
                )
                self.lbl_similar_shot_status.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
                self.btn_run_similar_shots.setEnabled(True)

        except Exception as e:
            self.lbl_similar_shot_status.setText(f"Status unavailable: {str(e)}")
            self.lbl_similar_shot_status.setStyleSheet("color: #f44336; font-size: 11px;")
            print(f"Error checking similar shot status: {e}")

    def _update_backfill_status(self):
        """Update backfill status label."""
        try:
            from repository.asset_repository import AssetRepository
            from repository.photo_repository import PhotoRepository
            from repository.base_repository import DatabaseConnection

            # Get current project_id
            project_id = 1
            if hasattr(self.parent(), 'sidebar') and hasattr(self.parent().sidebar, 'project_id'):
                project_id = self.parent().sidebar.project_id
            elif hasattr(self.parent(), 'grid') and hasattr(self.parent().grid, 'project_id'):
                project_id = self.parent().grid.project_id

            # Check status
            db_conn = DatabaseConnection()
            photo_repo = PhotoRepository(db_conn)
            asset_repo = AssetRepository(db_conn)

            total_photos = photo_repo.count(where_clause="project_id = ?", params=(project_id,))
            photos_without_instance = asset_repo.count_photos_without_instance(project_id)

            if total_photos == 0:
                self.lbl_backfill_status.setText("No photos in project")
                self.lbl_backfill_status.setStyleSheet("color: #666; font-size: 11px;")
                self.btn_run_backfill.setEnabled(False)
            elif photos_without_instance == 0:
                self.lbl_backfill_status.setText("✓ All photos ready for duplicate detection")
                self.lbl_backfill_status.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
                self.btn_run_backfill.setEnabled(False)
            else:
                progress_pct = ((total_photos - photos_without_instance) / total_photos * 100) if total_photos > 0 else 0
                self.lbl_backfill_status.setText(
                    f"{photos_without_instance} photos need processing ({progress_pct:.1f}% complete)"
                )
                self.lbl_backfill_status.setStyleSheet("color: #ff9800; font-size: 11px;")
                self.btn_run_backfill.setEnabled(True)

        except Exception as e:
            self.lbl_backfill_status.setText(f"Status unavailable: {str(e)}")
            self.lbl_backfill_status.setStyleSheet("color: #f44336; font-size: 11px;")
            print(f"Error checking backfill status: {e}")

    def _on_cancel(self):
        """Handle cancel button - check for unsaved changes."""
        if self._has_changes():
            reply = QMessageBox.question(
                self,
                tr("preferences.unsaved_changes"),
                tr("preferences.unsaved_changes_message"),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )

            if reply == QMessageBox.Yes:
                self._on_save()
            elif reply == QMessageBox.No:
                self.reject()
            # Cancel = do nothing
        else:
            self.reject()

    def _on_save(self):
        """Save all settings and close dialog."""
        # General
        self.settings.set("skip_unchanged_photos", self.chk_skip.isChecked())
        self.settings.set("use_exif_for_date", self.chk_exif.isChecked())

        # Appearance
        self.settings.set("dark_mode", self.chk_dark.isChecked())
        self.settings.set("thumbnail_cache_enabled", self.chk_cache.isChecked())

        try:
            cache_size = int(self.cmb_cache_size.currentText())
        except ValueError:
            cache_size = 500
        self.settings.set("cache_size_mb", cache_size)

        self.settings.set("cache_auto_cleanup", self.chk_cache_cleanup.isChecked())

        # Language
        selected_lang = self.cmb_language.currentData()
        old_lang = self.settings.get("language", "en")
        if selected_lang != old_lang:
            self.settings.set("language", selected_lang)
            QMessageBox.information(
                self,
                tr("preferences.appearance.restart_required"),
                tr("preferences.appearance.restart_required_message")
            )

        # Scanning
        ignore_list = [x.strip() for x in self.txt_ignore_folders.toPlainText().splitlines() if x.strip()]
        self.settings.set("ignore_folders", ignore_list)
        self.settings.set("device_auto_refresh", self.chk_device_auto_refresh.isChecked())

        # Face Detection - Batch save to prevent repeated saves
        self.face_config.set("insightface_model", self.cmb_insightface_model.currentData(), save_now=False)
        self.face_config.set("min_face_size", self.spin_min_face_size.value(), save_now=False)
        self.face_config.set("confidence_threshold", self.spin_confidence.value() / 100.0, save_now=False)
        self.face_config.set("clustering_eps", self.spin_cluster_eps.value() / 100.0, save_now=False)
        self.face_config.set("clustering_min_samples", self.spin_min_samples.value(), save_now=False)
        self.face_config.set("auto_cluster_after_scan", self.chk_auto_cluster.isChecked(), save_now=False)
        self.face_config.set("max_workers", self.spin_max_workers.value(), save_now=False)
        self.face_config.set("batch_size", self.spin_batch_size.value(), save_now=False)
        self.face_config.set("min_quality_score", float(self.spin_min_quality.value()), save_now=False)
        self.face_config.set("enable_gpu_batch", self.chk_gpu_batch.isChecked(), save_now=False)
        self.face_config.set("gpu_batch_size", self.spin_gpu_batch_size.value(), save_now=False)
        self.face_config.set("gpu_batch_min_photos", self.spin_gpu_batch_min.value(), save_now=False)
        # Per-project overrides
        if self.chk_project_overrides.isChecked():
            self.face_config.set_project_overrides(self.current_project_id, {
                "min_face_size": self.spin_proj_min_face.value(),
                "confidence_threshold": self.spin_proj_confidence.value() / 100.0,
                "clustering_eps": self.spin_proj_eps.value() / 100.0,
                "clustering_min_samples": self.spin_proj_min_samples.value(),
            })
        else:
            po = self.face_config.get("project_overrides", {})
            if str(self.current_project_id) in po:
                del po[str(self.current_project_id)]
                self.face_config.set("project_overrides", po)
        # UI low-confidence toggle
        self.face_config.set("show_low_confidence", self.chk_show_low_conf.isChecked(), save_now=False)
        
        # Save all face detection settings at once
        self.face_config.save()
        print(f"✅ Face detection settings saved: model={self.cmb_insightface_model.currentData()}, "
              f"eps={self.spin_cluster_eps.value()}%, min_samples={self.spin_min_samples.value()}")

        # InsightFace Model Path
        model_path = self.txt_model_path.text().strip()
        old_model_path = self.settings.get("insightface_model_path", "")
        self.settings.set("insightface_model_path", model_path)

        if model_path != old_model_path:
            # Clear InsightFace check flag
            flag_file = Path('.insightface_check_done')
            if flag_file.exists():
                try:
                    flag_file.unlink()
                    print("🔄 InsightFace check flag cleared - will re-check on next startup")
                except Exception as e:
                    print(f"⚠️ Failed to clear InsightFace check flag: {e}")

            print(f"🧑 InsightFace model path configured: {model_path or '(using default locations)'}")

        # CLIP / Visual Embeddings
        self.settings.set("clip_model_variant", self.cmb_clip_variant.currentData())
        self.settings.set("clip_device", self.cmb_clip_device.currentData())
        self.settings.set("clip_auto_extract", self.chk_auto_extract.isChecked())
        self.settings.set("clip_batch_size", self.spin_extraction_batch.value())
        clip_path = self.txt_clip_model_path.text().strip()
        self.settings.set("clip_model_path", clip_path)
        print(f"🔍 CLIP settings saved: variant={self.cmb_clip_variant.currentData()}, device={self.cmb_clip_device.currentData()}")

        # Badge overlays
        self.settings.set("badge_overlays_enabled", self.chk_badge_overlays.isChecked())
        self.settings.set("badge_size_px", self.spin_badge_size.value())
        self.settings.set("badge_shape", self.cmb_badge_shape.currentText())
        self.settings.set("badge_max_count", self.spin_badge_max.value())
        self.settings.set("badge_shadow", self.chk_badge_shadow.isChecked())
        
        # GPS & Location
        self.settings.set("gps_clustering_radius_km", float(self.spin_cluster_radius.value()))
        self.settings.set("gps_reverse_geocoding_enabled", self.chk_reverse_geocoding.isChecked())
        self.settings.set("gps_geocoding_timeout_sec", float(self.spin_geocoding_timeout.value()))
        self.settings.set("gps_cache_location_names", self.chk_cache_location_names.isChecked())

        # Video FFprobe path
        ffprobe_path = self.txt_ffprobe_path.text().strip()
        old_ffprobe_path = self.settings.get("ffprobe_path", "")
        self.settings.set("ffprobe_path", ffprobe_path)
        if ffprobe_path != old_ffprobe_path:
            # Clear FFmpeg check flag
            flag_file = Path('.ffmpeg_check_done')
            if flag_file.exists():
                try:
                    flag_file.unlink()
                    print(tr("preferences.video.ffmpeg_path_changed"))
                except Exception as e:
                    print(f"⚠️ Failed to clear FFmpeg check flag: {e}")

            path_display = ffprobe_path if ffprobe_path else tr("preferences.video.ffmpeg_path_system")
            print(tr("preferences.video.ffmpeg_path_configured", path=path_display))

            # Offer to restart
            reply = QMessageBox.question(
                self,
                tr("preferences.video.restart_required"),
                tr("preferences.video.restart_required_message"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                self.accept()
                print("🔄 Restarting application...")
                # Use centralized restart with proper shutdown barrier
                try:
                    w = self.window()
                    if hasattr(w, "request_restart"):
                        w.request_restart()
                        return
                except Exception:
                    pass
                # Fallback if MainWindow.request_restart not available
                QProcess.startDetached(sys.executable, sys.argv)
                QGuiApplication.quit()
                return

        # Advanced
        self.settings.set("show_decoder_warnings", self.chk_decoder_warnings.isChecked())

        if self.settings.get("show_decoder_warnings", False):
            QMessageBox.information(
                self,
                tr("preferences.diagnostics.restart_required"),
                tr("preferences.diagnostics.restart_required_message")
            )
        else:
            QMessageBox.information(
                self,
                tr("preferences.diagnostics.restart_recommended"),
                tr("preferences.diagnostics.restart_recommended_message")
            )

        self.settings.set("db_debug_logging", self.chk_db_debug.isChecked())
        self.settings.set("show_sql_queries", self.chk_sql_echo.isChecked())

        if self.chk_db_debug.isChecked():
            print(tr("preferences.developer.developer_mode_enabled"))

        # Metadata
        self.settings.set("meta_workers", int(self.spin_workers.currentText()))
        self.settings.set("meta_timeout_secs", float(self.txt_meta_timeout.currentText()))
        self.settings.set("meta_batch", int(self.txt_meta_batch.currentText()))
        self.settings.set("auto_run_backfill_after_scan", self.chk_meta_auto.isChecked())

        self.accept()

    def _has_changes(self) -> bool:
        """Check if any settings have been modified."""
        current = {
            "skip_unchanged_photos": self.chk_skip.isChecked(),
            "use_exif_for_date": self.chk_exif.isChecked(),
            "dark_mode": self.chk_dark.isChecked(),
            "language": self.cmb_language.currentData(),
            "thumbnail_cache_enabled": self.chk_cache.isChecked(),
            "cache_size_mb": int(self.cmb_cache_size.currentText()) if self.cmb_cache_size.currentText().isdigit() else 500,
            "cache_auto_cleanup": self.chk_cache_cleanup.isChecked(),
            "ignore_folders": [x.strip() for x in self.txt_ignore_folders.toPlainText().splitlines() if x.strip()],
            "device_auto_refresh": self.chk_device_auto_refresh.isChecked(),
            "insightface_model": self.cmb_insightface_model.currentData(),
            "min_face_size": self.spin_min_face_size.value(),
            "confidence_threshold": self.spin_confidence.value() / 100.0,
            "clustering_eps": self.spin_cluster_eps.value() / 100.0,
            "clustering_min_samples": self.spin_min_samples.value(),
            "auto_cluster_after_scan": self.chk_auto_cluster.isChecked(),
            "face_max_workers": self.spin_max_workers.value(),
            "face_batch_size": self.spin_batch_size.value(),
            "insightface_model_path": self.txt_model_path.text().strip(),
            "ffprobe_path": self.txt_ffprobe_path.text().strip(),
            "show_decoder_warnings": self.chk_decoder_warnings.isChecked(),
            "db_debug_logging": self.chk_db_debug.isChecked(),
            "show_sql_queries": self.chk_sql_echo.isChecked(),
            "meta_workers": int(self.spin_workers.currentText()) if self.spin_workers.currentText().isdigit() else 4,
            "meta_timeout_secs": float(self.txt_meta_timeout.currentText()) if self.txt_meta_timeout.currentText().replace('.', '').isdigit() else 8.0,
            "meta_batch": int(self.txt_meta_batch.currentText()) if self.txt_meta_batch.currentText().isdigit() else 200,
            "auto_run_backfill_after_scan": self.chk_meta_auto.isChecked(),
        }

        return current != self.original_settings

    def _browse_ffprobe(self):
        """Browse for ffprobe executable."""
        import platform

        if platform.system() == "Windows":
            filter_str = "Executable Files (*.exe);;All Files (*.*)"
        else:
            filter_str = "All Files (*)"

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select FFprobe Executable",
            "",
            filter_str
        )

        if path:
            self.txt_ffprobe_path.setText(path)

    def _test_ffprobe(self):
        """Test ffprobe executable."""
        import subprocess

        path = self.txt_ffprobe_path.text().strip()
        if not path:
            path = "ffprobe"  # Test system PATH

        try:
            result = subprocess.run(
                [path, '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0] if result.stdout else 'Version info unavailable'
                QMessageBox.information(
                    self,
                    tr("preferences.video.ffprobe_test_success"),
                    tr("preferences.video.ffprobe_test_success_message", version=version_line)
                )
            else:
                QMessageBox.warning(
                    self,
                    tr("preferences.video.ffprobe_test_failed"),
                    tr("preferences.video.ffprobe_test_failed_message",
                       code=result.returncode, error=result.stderr)
                )
        except FileNotFoundError:
            QMessageBox.critical(
                self,
                tr("preferences.video.ffprobe_not_found"),
                tr("preferences.video.ffprobe_not_found_message", path=path)
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("preferences.video.ffprobe_test_error"),
                tr("preferences.video.ffprobe_test_error_message", error=str(e))
            )

    def _browse_models(self):
        """Browse for InsightFace models directory."""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select InsightFace Models Directory (buffalo_l)",
            "",
            QFileDialog.ShowDirsOnly
        )
        if path:
            self.txt_model_path.setText(path)

    def _test_model_path(self):
        """Test InsightFace model path."""
        from PySide6.QtWidgets import QProgressDialog
        from PySide6.QtCore import QThread, Signal

        path = self.txt_model_path.text().strip()

        if not path:
            QMessageBox.information(
                self,
                "Model Path Test",
                "No custom path specified.\n\n"
                "App will use default locations:\n"
                "  1. ./models/buffalo_l/\n"
                "  2. ~/.insightface/models/buffalo_l/"
            )
            return

        # Verify path exists
        if not Path(path).exists():
            QMessageBox.critical(
                self,
                "Model Path Test - Not Found",
                f"✗ Path does not exist:\n{path}\n\n"
                "Please check the path and try again."
            )
            return

        # Run comprehensive test
        class TestThread(QThread):
            finished_signal = Signal(bool, str)

            def __init__(self, test_path):
                super().__init__()
                self.test_path = test_path

            def run(self):
                try:
                    from utils.test_insightface_models import test_model_path
                    success, message = test_model_path(self.test_path)
                    self.finished_signal.emit(success, message)
                except Exception as e:
                    self.finished_signal.emit(False, f"Test error: {str(e)}")

        progress_dlg = QProgressDialog(
            "Testing InsightFace model loading...\nThis may take a moment...",
            None, 0, 0, self
        )
        progress_dlg.setWindowTitle("Model Test")
        progress_dlg.setWindowModality(Qt.WindowModal)
        progress_dlg.setCancelButton(None)
        progress_dlg.setMinimumDuration(0)

        test_thread = TestThread(path)

        def on_test_finished(success, message):
            progress_dlg.close()
            if success:
                QMessageBox.information(
                    self,
                    "Model Test - SUCCESS ✅",
                    message + "\n\n💡 Remember to click Save to save settings, then restart the app."
                )
            else:
                QMessageBox.critical(
                    self,
                    "Model Test - FAILED ❌",
                    message
                )

        test_thread.finished_signal.connect(on_test_finished)
        test_thread.start()
        progress_dlg.exec()

    def _check_model_status(self):
        """Check and display current model status."""
        try:
            from utils.insightface_check import get_model_download_status
            status = get_model_download_status()

            if not status['library_installed']:
                self.lbl_model_status.setText(
                    "❌ InsightFace library not installed\n"
                    "Install with: pip install insightface onnxruntime"
                )
                self.lbl_model_status.setStyleSheet(
                    "QLabel { padding: 6px; background-color: #ffe0e0; border-radius: 4px; color: #d00; }"
                )
                self.btn_download_models.setEnabled(False)
            elif status['models_available']:
                self.lbl_model_status.setText(
                    f"✅ Models installed and ready\n"
                    f"Location: {status['model_path']}"
                )
                self.lbl_model_status.setStyleSheet(
                    "QLabel { padding: 6px; background-color: #e0ffe0; border-radius: 4px; color: #060; }"
                )
                self.btn_download_models.setEnabled(False)
            else:
                self.lbl_model_status.setText(
                    "⚠️ Models not found\n"
                    "Click 'Download Models' to install buffalo_l face detection models"
                )
                self.lbl_model_status.setStyleSheet(
                    "QLabel { padding: 6px; background-color: #fff4e0; border-radius: 4px; color: #840; }"
                )
                self.btn_download_models.setEnabled(True)
        except Exception as e:
            self.lbl_model_status.setText(f"⚠️ Error checking status: {str(e)}")
            self.lbl_model_status.setStyleSheet(
                "QLabel { padding: 6px; background-color: #fff4e0; border-radius: 4px; color: #840; }"
            )

    def _download_models(self):
        """Download InsightFace models with progress dialog."""
        from PySide6.QtWidgets import QProgressDialog
        from PySide6.QtCore import QThread, Signal
        import subprocess

        class DownloadThread(QThread):
            progress = Signal(str)
            finished_signal = Signal(bool, str)

            def run(self):
                try:
                    self.progress.emit("Initializing download...")

                    # Run download_face_models.py script
                    script_path = Path("download_face_models.py")
                    if not script_path.exists():
                        self.finished_signal.emit(False, "download_face_models.py not found")
                        return

                    self.progress.emit("Downloading buffalo_l models (~200MB)...")
                    result = subprocess.run(
                        [sys.executable, str(script_path)],
                        capture_output=True,
                        text=True,
                        timeout=600  # 10 minute timeout
                    )

                    if result.returncode == 0:
                        self.finished_signal.emit(True, "Models downloaded successfully!")
                    else:
                        error_msg = result.stderr or result.stdout or "Unknown error"
                        self.finished_signal.emit(False, f"Download failed:\n{error_msg}")

                except subprocess.TimeoutExpired:
                    self.finished_signal.emit(False, "Download timed out (>10 minutes)")
                except Exception as e:
                    self.finished_signal.emit(False, f"Error: {str(e)}")

        progress_dlg = QProgressDialog("Downloading InsightFace models...", "Cancel", 0, 0, self)
        progress_dlg.setWindowTitle("Model Download")
        progress_dlg.setWindowModality(Qt.WindowModal)
        progress_dlg.setCancelButton(None)  # Disable cancel during download
        progress_dlg.setMinimumDuration(0)

        download_thread = DownloadThread()

        def on_progress(msg):
            progress_dlg.setLabelText(msg)

        def on_finished(success, message):
            progress_dlg.close()
            if success:
                QMessageBox.information(
                    self,
                    "Download Complete",
                    f"✅ {message}\n\n"
                    "Face detection models are now installed.\n"
                    "Restart the application to use face detection."
                )
                self._check_model_status()  # Update status display
            else:
                QMessageBox.critical(
                    self,
                    "Download Failed",
                    f"❌ {message}\n\n"
                    "You can try manually running:\n"
                    "python download_face_models.py"
                )

        download_thread.progress.connect(on_progress)
        download_thread.finished_signal.connect(on_finished)
        download_thread.start()
        progress_dlg.exec()

    def _check_clip_status(self):
        """Check and display CLIP model status."""
        try:
            from utils.clip_check import get_clip_download_status
            status = get_clip_download_status()

            # Update model path display
            app_root = Path(__file__).parent.absolute()
            default_path = app_root / 'models' / 'clip-vit-base-patch32'
            self.txt_clip_model_path.setText(str(default_path))

            if status['models_available']:
                size_mb = status.get('total_size_mb', 0)
                self.lbl_clip_status.setText(
                    f"✅ CLIP model installed and ready ({size_mb} MB)\n"
                    f"Location: {status['model_path']}"
                )
                self.lbl_clip_status.setStyleSheet(
                    "QLabel { padding: 8px; background-color: #e0ffe0; border-radius: 4px; color: #060; }"
                )
                self.btn_download_clip.setEnabled(False)
            elif status['missing_files']:
                missing_count = len(status['missing_files'])
                self.lbl_clip_status.setText(
                    f"⚠️ CLIP model partially installed ({missing_count} files missing)\n"
                    f"Click 'Download CLIP Model' to complete installation"
                )
                self.lbl_clip_status.setStyleSheet(
                    "QLabel { padding: 8px; background-color: #fff4e0; border-radius: 4px; color: #840; }"
                )
                self.btn_download_clip.setEnabled(True)
            else:
                self.lbl_clip_status.setText(
                    "⚠️ CLIP model not installed\n"
                    "Click 'Download CLIP Model' to install OpenAI CLIP ViT-B/32 (~600MB)"
                )
                self.lbl_clip_status.setStyleSheet(
                    "QLabel { padding: 8px; background-color: #fff4e0; border-radius: 4px; color: #840; }"
                )
                self.btn_download_clip.setEnabled(True)
        except Exception as e:
            self.lbl_clip_status.setText(f"⚠️ Error checking CLIP status: {str(e)}")
            self.lbl_clip_status.setStyleSheet(
                "QLabel { padding: 8px; background-color: #fff4e0; border-radius: 4px; color: #840; }"
            )

    def _download_clip_model(self):
        """Download CLIP model with progress dialog."""
        from PySide6.QtWidgets import QProgressDialog
        from PySide6.QtCore import QThread, Signal
        import subprocess

        class CLIPDownloadThread(QThread):
            progress = Signal(str)
            finished_signal = Signal(bool, str)

            def run(self):
                try:
                    self.progress.emit("Initializing CLIP model download...")

                    # Run download_clip_model_offline.py script
                    script_path = Path("download_clip_model_offline.py")
                    if not script_path.exists():
                        self.finished_signal.emit(False, "download_clip_model_offline.py not found")
                        return

                    self.progress.emit("Downloading CLIP ViT-B/32 model (~600MB)...")
                    result = subprocess.run(
                        [sys.executable, str(script_path)],
                        capture_output=True,
                        text=True,
                        timeout=1800  # 30 minute timeout (large download)
                    )

                    if result.returncode == 0:
                        self.finished_signal.emit(True, "CLIP model downloaded successfully!")
                    else:
                        error_msg = result.stderr or result.stdout or "Unknown error"
                        self.finished_signal.emit(False, f"Download failed:\n{error_msg}")

                except subprocess.TimeoutExpired:
                    self.finished_signal.emit(False, "Download timed out (>30 minutes)")
                except Exception as e:
                    self.finished_signal.emit(False, f"Error: {str(e)}")

        progress_dlg = QProgressDialog("Downloading CLIP model...", "Cancel", 0, 0, self)
        progress_dlg.setWindowTitle("CLIP Model Download")
        progress_dlg.setWindowModality(Qt.WindowModal)
        progress_dlg.setCancelButton(None)  # Disable cancel during download
        progress_dlg.setMinimumDuration(0)

        download_thread = CLIPDownloadThread()

        def on_progress(msg):
            progress_dlg.setLabelText(msg)

        def on_finished(success, message):
            progress_dlg.close()
            if success:
                QMessageBox.information(
                    self,
                    "Download Complete",
                    f"✅ {message}\n\n"
                    "CLIP model files are now installed in ./models/clip-vit-base-patch32/\n"
                    "You can now use visual embedding extraction."
                )
                self._check_clip_status()  # Update status display
            else:
                QMessageBox.critical(
                    self,
                    "Download Failed",
                    f"❌ {message}\n\n"
                    "You can try manually running:\n"
                    "python download_clip_model_offline.py"
                )

        download_thread.progress.connect(on_progress)
        download_thread.finished_signal.connect(on_finished)
        download_thread.start()
        progress_dlg.exec()

    def _browse_clip_models(self):
        """Browse for custom CLIP model directory."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select CLIP Model Directory",
            str(Path.home()),
            QFileDialog.ShowDirsOnly
        )
        if folder:
            self.txt_clip_model_path.setText(folder)
            self.settings.set("clip_model_path", folder)
            self._check_clip_status()

    def _open_clip_model_folder(self):
        """Open CLIP model folder in file explorer."""
        try:
            app_root = Path(__file__).parent.absolute()
            model_folder = app_root / 'models' / 'clip-vit-base-patch32'

            if not model_folder.exists():
                model_folder.mkdir(parents=True, exist_ok=True)

            # Open folder in system file explorer
            import platform
            system = platform.system()

            if system == 'Windows':
                os.startfile(str(model_folder))
            elif system == 'Darwin':  # macOS
                subprocess.run(['open', str(model_folder)])
            else:  # Linux and others
                subprocess.run(['xdg-open', str(model_folder)])

        except Exception as e:
            QMessageBox.warning(
                self,
                "Open Folder Failed",
                f"Could not open model folder:\n{str(e)}"
            )

    def _get_current_project_id(self):
        """
        Get the current project ID from the main window.

        Checks multiple sources in order:
        1. Main window's grid.project_id
        2. Main window's sidebar.project_id
        3. Default project from app_services

        Returns:
            Project ID or None if not found
        """
        try:
            parent = self.parent()

            # Try grid.project_id
            if parent and hasattr(parent, 'grid') and hasattr(parent.grid, 'project_id'):
                pid = parent.grid.project_id
                if pid is not None:
                    return pid

            # Try sidebar.project_id
            if parent and hasattr(parent, 'sidebar') and hasattr(parent.sidebar, 'project_id'):
                pid = parent.sidebar.project_id
                if pid is not None:
                    return pid

            # Fallback to default project
            from app_services import get_default_project_id
            return get_default_project_id()

        except Exception as e:
            print(f"[PreferencesDialog] Error getting project_id: {e}")
            return None

    def _refresh_gpu_info(self):
        """Refresh GPU and performance information."""
        try:
            from services.semantic_embedding_service import get_semantic_embedding_service
            service = get_semantic_embedding_service()

            # Get GPU info
            gpu_info = service.get_gpu_memory_info()
            device = gpu_info.get('device', 'cpu')
            total_mb = gpu_info.get('total_mb', 0)
            available_mb = gpu_info.get('available_mb', 0)

            # Update GPU device label
            device_text = device.upper()
            if device == 'cuda':
                device_text = f"CUDA ({gpu_info.get('device_name', 'NVIDIA GPU')})"
            elif device == 'mps':
                device_text = "Apple Metal (MPS)"
            elif device == 'cpu':
                device_text = "CPU (No GPU detected)"
            self.lbl_gpu_device.setText(device_text)

            # Update memory info
            if total_mb > 0:
                self.lbl_gpu_memory.setText(f"{available_mb:.0f} MB / {total_mb:.0f} MB")
            else:
                self.lbl_gpu_memory.setText("N/A (CPU mode)")

            # Get optimal batch size
            try:
                batch_size = service.get_optimal_batch_size()
                self.lbl_optimal_batch.setText(f"{batch_size} photos/batch")
            except Exception:
                self.lbl_optimal_batch.setText("N/A")

            # Check FAISS availability
            try:
                import faiss
                self.lbl_faiss_status.setText("✓ Available")
                self.lbl_faiss_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
            except ImportError:
                self.lbl_faiss_status.setText("Not installed (using numpy)")
                self.lbl_faiss_status.setStyleSheet("color: #666;")

        except Exception as e:
            self.lbl_gpu_device.setText("Error detecting GPU")
            self.lbl_gpu_memory.setText("—")
            self.lbl_optimal_batch.setText("—")
            self.lbl_faiss_status.setText("Unknown")

    def _refresh_embedding_stats(self):
        """Refresh embedding statistics summary."""
        try:
            from services.semantic_embedding_service import get_semantic_embedding_service

            # Get current project ID from main window's grid or sidebar
            project_id = self._get_current_project_id()

            if project_id is None:
                self.lbl_embedding_coverage.setText("No project selected")
                self.lbl_storage_format.setText("")
                self.btn_migrate_float16.setEnabled(False)
                return

            service = get_semantic_embedding_service()
            stats = service.get_project_embedding_stats(project_id)

            # Coverage summary
            total = stats.get('total_photos', 0)
            with_emb = stats.get('photos_with_embeddings', 0)
            coverage = stats.get('coverage_percent', 0)
            self.lbl_embedding_coverage.setText(
                f"📊 Coverage: {with_emb}/{total} photos ({coverage:.1f}%)"
            )

            # Storage format
            float16 = stats.get('float16_count', 0)
            float32 = stats.get('float32_count', 0)
            storage_mb = stats.get('storage_mb', 0)

            if float16 > 0 or float32 > 0:
                self.lbl_storage_format.setText(
                    f"Storage: {storage_mb:.2f} MB ({float16} float16, {float32} float32)"
                )
                self.btn_migrate_float16.setEnabled(float32 > 0)
            else:
                self.lbl_storage_format.setText("No embeddings yet")
                self.btn_migrate_float16.setEnabled(False)

        except Exception as e:
            self.lbl_embedding_coverage.setText("Could not load statistics")
            self.lbl_storage_format.setText(f"Error: {str(e)[:50]}")
            self.btn_migrate_float16.setEnabled(False)

    def _open_embedding_stats_dashboard(self):
        """Open the full embedding statistics dashboard."""
        try:
            from ui.embedding_stats_dashboard import show_embedding_stats_dashboard

            # Get current project ID
            project_id = self._get_current_project_id()

            if project_id is None:
                QMessageBox.warning(
                    self,
                    "No Project Selected",
                    "Please select a project first to view embedding statistics."
                )
                return

            # Show the dashboard (non-modal)
            self._stats_dashboard = show_embedding_stats_dashboard(project_id, self)
            # Connect refresh signal to update our summary
            self._stats_dashboard.refreshRequested.connect(self._refresh_embedding_stats)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Opening Dashboard",
                f"Could not open embedding statistics dashboard:\n{str(e)}"
            )

    def _migrate_embeddings_to_float16(self):
        """Migrate legacy float32 embeddings to float16."""
        try:
            from services.semantic_embedding_service import get_semantic_embedding_service

            reply = QMessageBox.question(
                self,
                "Migrate to Float16",
                "This will convert legacy float32 embeddings to half-precision format, "
                "saving approximately 50% storage space.\n\n"
                "This is safe and reversible (embeddings can be regenerated).\n\n"
                "Proceed?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply != QMessageBox.Yes:
                return

            service = get_semantic_embedding_service()
            migrated = 0

            # Migrate in batches
            while True:
                batch_migrated = service.migrate_to_half_precision(batch_size=500)
                if batch_migrated == 0:
                    break
                migrated += batch_migrated

            QMessageBox.information(
                self,
                "Migration Complete",
                f"Successfully migrated {migrated} embeddings to float16 format."
            )

            # Refresh stats
            self._refresh_embedding_stats()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Migration Failed",
                f"Error during migration:\n{str(e)}"
            )

    def _show_cache_stats(self):
        """Show thumbnail cache statistics."""
        try:
            from thumb_cache_db import get_cache
            cache = get_cache()
            stats = cache.get_stats()

            if "error" in stats:
                QMessageBox.warning(self, "Thumbnail Cache Stats", f"Error: {stats['error']}")
                return

            msg = (
                f"Entries: {stats['entries']}\n"
                f"Size: {stats['size_mb']} MB\n"
                f"Last Updated: {stats['last_updated']}\n"
                f"Path: {stats['path']}"
            )
            QMessageBox.information(self, "Thumbnail Cache Stats", msg)
        except Exception as e:
            QMessageBox.warning(self, "Cache Stats", f"Error retrieving cache stats:\n{str(e)}")

    def _purge_cache(self):
        """Purge old cache entries."""
        try:
            from thumb_cache_db import get_cache
            cache = get_cache()

            reply = QMessageBox.question(
                self,
                "Purge Cache",
                "Remove thumbnails older than 7 days?\n\nThis will free up disk space.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                cache.purge_stale(max_age_days=7)
                QMessageBox.information(
                    self,
                    "Purge Complete",
                    "Old thumbnails (older than 7 days) have been purged."
                )
        except Exception as e:
            QMessageBox.warning(self, "Purge Cache", f"Error purging cache:\n{str(e)}")

    def _update_badge_preview(self):
        """Update the badge preview widget with current settings."""
        try:
            self.badge_preview.update_settings(
                size=self.spin_badge_size.value(),
                shape=self.cmb_badge_shape.currentText(),
                max_count=self.spin_badge_max.value(),
                shadow=self.chk_badge_shadow.isChecked(),
                enabled=self.chk_badge_overlays.isChecked()
            )
        except Exception as e:
            print(f"[PreferencesDialog] Badge preview update error: {e}")
