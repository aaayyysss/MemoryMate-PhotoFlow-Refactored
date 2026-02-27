# ui/accordion_sidebar/find_section.py
# Smart Find Section - Intelligent photo discovery
# iPhone/Google Photos/Lightroom/Excire inspired three-layer UX

"""
Find Section for AccordionSidebar

Three-layer discovery pattern (Apple/Google/Lightroom best practice):

Layer 1 - Quick Finds: Preset category chips (Beach, Mountains, Wedding, etc.)
    One click → instant results in the grid. No thinking required.

Layer 2 - Refine: Metadata facets (date, people, location, media type, rating)
    Additive filters applied ON TOP of the concept search.

Layer 3 - Custom Search: Free-text CLIP search field
    User types their own query (e.g., "dog playing on grass").

Signals:
    smartFindTriggered(list, str): Emitted with (paths, query_label) for grid filtering
    smartFindCleared(): Emitted when Find filter is cleared
"""

import logging
from typing import Optional, Dict, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QLineEdit, QComboBox, QCheckBox,
    QGridLayout, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QTimer
from .base_section import BaseSection

logger = logging.getLogger(__name__)


# Category display order and labels
CATEGORY_ORDER = [
    ("places", "Places & Scenes"),
    ("events", "Events & Activities"),
    ("subjects", "Subjects & Things"),
    ("media", "Media Types"),
    ("quality", "Quality & Flags"),
]


class FindSection(BaseSection):
    """
    Smart Find section for the AccordionSidebar.

    Provides intelligent photo discovery with preset categories,
    refinement facets, and free-text CLIP search.
    """

    # Emitted when a Smart Find query produces results
    # Args: (list_of_paths, query_label_string)
    smartFindTriggered = Signal(list, str)

    # Emitted when the user clears the Find filter
    smartFindCleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._smart_find_service = None
        self._active_preset_id = None
        self._active_query_label = None
        self._search_debounce = QTimer()
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(500)
        self._search_debounce.timeout.connect(self._execute_text_search)
        self._pending_text_query = ""
        self._recent_searches: List[Dict] = []  # [{label, preset_id_or_query, count}]
        self._preset_buttons: Dict[str, QPushButton] = {}
        self._refine_filters: Dict[str, any] = {}

    def get_section_id(self) -> str:
        return "find"

    def get_title(self) -> str:
        return "Find"

    def get_icon(self) -> str:
        return "🔍"

    def set_project(self, project_id: int) -> None:
        """Override to reinitialize service on project switch."""
        super().set_project(project_id)
        self._smart_find_service = None
        self._active_preset_id = None

    def _get_service(self):
        """Get or create SmartFindService for current project."""
        if self._smart_find_service is None and self.project_id:
            from services.smart_find_service import get_smart_find_service
            self._smart_find_service = get_smart_find_service(self.project_id)
        return self._smart_find_service

    def load_section(self):
        """Load section (synchronous - no DB needed for presets)."""
        self._loading = False
        service = self._get_service()
        if service:
            return service.get_presets_by_category()
        return {}

    def create_content_widget(self, data) -> Optional[QWidget]:
        """
        Create the three-layer Find UI.

        Layer 1: Quick Find preset chips (categorized)
        Layer 2: Refine facets
        Layer 3: Custom text search + recent searches
        """
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(8, 6, 8, 8)
        main_layout.setSpacing(8)

        # ── Active Query Indicator (shown when a find is active) ──
        self._active_indicator = QWidget()
        indicator_layout = QHBoxLayout(self._active_indicator)
        indicator_layout.setContentsMargins(8, 6, 8, 6)
        indicator_layout.setSpacing(6)

        self._active_label = QLabel("")
        self._active_label.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #1a73e8;"
        )
        indicator_layout.addWidget(self._active_label, 1)

        clear_btn = QPushButton("✕ Clear")
        clear_btn.setFixedHeight(26)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: #fce8e6; color: #c5221f; border: none;
                border-radius: 4px; padding: 2px 10px; font-size: 11px;
            }
            QPushButton:hover { background: #f8d7da; }
        """)
        clear_btn.clicked.connect(self._clear_find)
        indicator_layout.addWidget(clear_btn)

        self._active_indicator.setStyleSheet(
            "background: #e8f0fe; border-radius: 6px;"
        )
        self._active_indicator.hide()
        main_layout.addWidget(self._active_indicator)

        # ── Layer 3: Custom Text Search (at top for quick access) ──
        search_frame = QFrame()
        search_frame.setStyleSheet(
            "QFrame { background: white; border: 1px solid #dadce0; border-radius: 8px; }"
        )
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(10, 4, 10, 4)
        search_layout.setSpacing(6)

        search_icon = QLabel("🔍")
        search_icon.setFixedWidth(20)
        search_layout.addWidget(search_icon)

        self._search_field = QLineEdit()
        self._search_field.setPlaceholderText("Describe what you're looking for...")
        self._search_field.setStyleSheet("""
            QLineEdit {
                border: none; background: transparent;
                font-size: 13px; color: #202124; padding: 6px 0;
            }
        """)
        self._search_field.textChanged.connect(self._on_search_text_changed)
        self._search_field.returnPressed.connect(self._execute_text_search)
        search_layout.addWidget(self._search_field, 1)

        main_layout.addWidget(search_frame)

        # ── CLIP availability indicator ──
        service = self._get_service()
        if service and not service.clip_available:
            no_clip = QLabel(
                "⚠ AI Search unavailable — CLIP model not loaded.\n"
                "Metadata-only presets still work."
            )
            no_clip.setWordWrap(True)
            no_clip.setStyleSheet(
                "color: #e67c00; font-size: 11px; padding: 4px 8px; "
                "background: #fff3e0; border-radius: 4px;"
            )
            main_layout.addWidget(no_clip)

        # ── Layer 1: Quick Find Preset Chips (categorized) ──
        presets_by_cat = data if isinstance(data, dict) else {}
        self._preset_buttons = {}

        for cat_id, cat_label in CATEGORY_ORDER:
            presets = presets_by_cat.get(cat_id, [])
            if not presets:
                continue

            # Category header
            cat_header = QLabel(cat_label)
            cat_header.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #5f6368; "
                "padding: 4px 0 2px 2px;"
            )
            main_layout.addWidget(cat_header)

            # Preset chips in a flow grid
            chip_widget = QWidget()
            chip_layout = self._create_flow_layout(chip_widget)

            for preset in presets:
                chip = self._create_preset_chip(preset)
                chip_layout.addWidget(chip)
                self._preset_buttons[preset["id"]] = chip

            main_layout.addWidget(chip_widget)

        # ── Layer 2: Refine Facets ──
        refine_header = QLabel("Refine Results")
        refine_header.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #5f6368; "
            "padding: 6px 0 2px 2px;"
        )
        main_layout.addWidget(refine_header)

        refine_widget = self._create_refine_panel()
        main_layout.addWidget(refine_widget)

        # ── Recent Searches ──
        self._recent_container = QWidget()
        self._recent_layout = QVBoxLayout(self._recent_container)
        self._recent_layout.setContentsMargins(0, 4, 0, 0)
        self._recent_layout.setSpacing(2)
        self._update_recent_ui()
        main_layout.addWidget(self._recent_container)

        # Stretch at bottom
        main_layout.addStretch()

        return container

    def _create_flow_layout(self, parent: QWidget) -> QGridLayout:
        """Create a grid layout that simulates a chip flow (3 columns)."""
        layout = QGridLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        return layout

    def _create_preset_chip(self, preset: Dict) -> QPushButton:
        """
        Create a Google Photos-style preset chip button.

        Design: icon + name, rounded corners, subtle background,
        hover highlight, active state.
        """
        icon = preset.get("icon", "🔍")
        name = preset.get("name", "Unknown")
        preset_id = preset.get("id", "")

        btn = QPushButton(f" {icon}  {name}")
        btn.setMinimumHeight(34)
        btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: #f1f3f4;
                border: 1px solid #e0e0e0;
                border-radius: 17px;
                padding: 5px 14px;
                font-size: 12px;
                color: #202124;
                text-align: left;
            }
            QPushButton:hover {
                background: #e8f0fe;
                border-color: #1a73e8;
                color: #1a73e8;
            }
            QPushButton:pressed {
                background: #d2e3fc;
            }
        """)
        btn.setProperty("preset_id", preset_id)
        btn.clicked.connect(lambda _, pid=preset_id: self._on_preset_clicked(pid))
        return btn

    def _set_chip_active(self, preset_id: str):
        """Highlight the active preset chip, reset others."""
        for pid, btn in self._preset_buttons.items():
            if pid == preset_id:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #1a73e8;
                        border: 1px solid #1a73e8;
                        border-radius: 17px;
                        padding: 5px 14px;
                        font-size: 12px;
                        color: white;
                        text-align: left;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background: #1765cc;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #f1f3f4;
                        border: 1px solid #e0e0e0;
                        border-radius: 17px;
                        padding: 5px 14px;
                        font-size: 12px;
                        color: #202124;
                        text-align: left;
                    }
                    QPushButton:hover {
                        background: #e8f0fe;
                        border-color: #1a73e8;
                        color: #1a73e8;
                    }
                    QPushButton:pressed {
                        background: #d2e3fc;
                    }
                """)

    def _create_refine_panel(self) -> QWidget:
        """Create Layer 2: Metadata refinement facets."""
        panel = QWidget()
        layout = QGridLayout(panel)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        combo_style = """
            QComboBox {
                background: white; border: 1px solid #dadce0;
                border-radius: 4px; padding: 4px 8px;
                font-size: 12px; color: #202124;
            }
            QComboBox:hover { border-color: #1a73e8; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background: white; selection-background-color: #e8f0fe;
                color: #202124;
            }
        """

        # Date filter
        layout.addWidget(QLabel("Date:"), 0, 0)
        self._date_combo = QComboBox()
        self._date_combo.addItem("Any time", None)
        self._date_combo.addItem("Today", "today")
        self._date_combo.addItem("This week", "week")
        self._date_combo.addItem("This month", "month")
        self._date_combo.addItem("This year", "year")
        self._date_combo.addItem("Last year", "last_year")
        self._date_combo.setStyleSheet(combo_style)
        self._date_combo.currentIndexChanged.connect(self._on_refine_changed)
        layout.addWidget(self._date_combo, 0, 1)

        # Media type
        layout.addWidget(QLabel("Type:"), 1, 0)
        self._type_combo = QComboBox()
        self._type_combo.addItem("All types", None)
        self._type_combo.addItem("Photos only", "photo")
        self._type_combo.addItem("Videos only", "video")
        self._type_combo.setStyleSheet(combo_style)
        self._type_combo.currentIndexChanged.connect(self._on_refine_changed)
        layout.addWidget(self._type_combo, 1, 1)

        # Location checkbox
        self._gps_check = QCheckBox("Has location (GPS)")
        self._gps_check.setStyleSheet("QCheckBox { font-size: 12px; color: #202124; }")
        self._gps_check.stateChanged.connect(self._on_refine_changed)
        layout.addWidget(self._gps_check, 2, 0, 1, 2)

        # Rating
        layout.addWidget(QLabel("Rating:"), 3, 0)
        self._rating_combo = QComboBox()
        self._rating_combo.addItem("Any rating", None)
        self._rating_combo.addItem("★ and above", "1")
        self._rating_combo.addItem("★★ and above", "2")
        self._rating_combo.addItem("★★★ and above", "3")
        self._rating_combo.addItem("★★★★ and above", "4")
        self._rating_combo.addItem("★★★★★ only", "5")
        self._rating_combo.setStyleSheet(combo_style)
        self._rating_combo.currentIndexChanged.connect(self._on_refine_changed)
        layout.addWidget(self._rating_combo, 3, 1)

        # Style labels
        for label in panel.findChildren(QLabel):
            label.setStyleSheet("font-size: 12px; color: #5f6368;")

        return panel

    def _get_refine_filters(self) -> Dict:
        """Collect current refine facet values into a filters dict."""
        filters = {}

        # Date
        from datetime import datetime, timedelta
        date_val = self._date_combo.currentData()
        if date_val:
            today = datetime.now().date()
            if date_val == "today":
                filters["date_from"] = today.strftime("%Y-%m-%d")
                filters["date_to"] = today.strftime("%Y-%m-%d")
            elif date_val == "week":
                start = today - timedelta(days=6)
                filters["date_from"] = start.strftime("%Y-%m-%d")
                filters["date_to"] = today.strftime("%Y-%m-%d")
            elif date_val == "month":
                start = today.replace(day=1)
                filters["date_from"] = start.strftime("%Y-%m-%d")
                filters["date_to"] = today.strftime("%Y-%m-%d")
            elif date_val == "year":
                filters["date_from"] = f"{today.year}-01-01"
                filters["date_to"] = today.strftime("%Y-%m-%d")
            elif date_val == "last_year":
                filters["date_from"] = f"{today.year - 1}-01-01"
                filters["date_to"] = f"{today.year - 1}-12-31"

        # Media type
        type_val = self._type_combo.currentData()
        if type_val:
            filters["media_type"] = type_val

        # GPS
        if self._gps_check.isChecked():
            filters["has_gps"] = True

        # Rating
        rating_val = self._rating_combo.currentData()
        if rating_val:
            filters["rating_min"] = int(rating_val)

        return filters

    # ── Event Handlers ──

    def _on_preset_clicked(self, preset_id: str):
        """Handle preset chip click — run Smart Find."""
        # Toggle: clicking active preset clears it
        if self._active_preset_id == preset_id:
            self._clear_find()
            return

        self._active_preset_id = preset_id
        self._set_chip_active(preset_id)

        service = self._get_service()
        if not service:
            logger.warning("[FindSection] SmartFindService not available")
            return

        extra_filters = self._get_refine_filters()

        # Run in background to avoid freezing UI
        QTimer.singleShot(0, lambda: self._run_preset_find(preset_id, extra_filters))

    def _run_preset_find(self, preset_id: str, extra_filters: Dict):
        """Execute preset find and emit results."""
        service = self._get_service()
        if not service:
            return

        result = service.find_by_preset(preset_id, extra_filters=extra_filters or None)

        if result.paths:
            self._active_query_label = result.query_label
            self._show_active_indicator(result.query_label, result.total_matches)
            self._add_recent(result.query_label, preset_id, result.total_matches)
            self.smartFindTriggered.emit(result.paths, result.query_label)
        else:
            self._show_active_indicator(result.query_label, 0)
            self.smartFindTriggered.emit([], result.query_label)

    def _on_search_text_changed(self, text: str):
        """Debounced text input handler."""
        self._pending_text_query = text.strip()
        if len(self._pending_text_query) >= 3:
            self._search_debounce.start()
        elif not self._pending_text_query:
            self._search_debounce.stop()

    def _execute_text_search(self):
        """Execute free-text CLIP search."""
        query = self._pending_text_query
        if not query or len(query) < 3:
            return

        service = self._get_service()
        if not service or not service.clip_available:
            logger.warning("[FindSection] CLIP not available for text search")
            return

        # Clear preset selection
        self._active_preset_id = None
        self._set_chip_active("")

        extra_filters = self._get_refine_filters()
        result = service.find_by_text(query)

        # Apply refine filters if any
        if extra_filters and result.paths:
            from services.smart_find_service import SmartFindService
            filtered = service.find_by_preset.__func__  # noqa - not needed
            # Simple path-based filtering for extra criteria
            result_paths = result.paths
            if "media_type" in extra_filters:
                mt = extra_filters["media_type"]
                if mt == "video":
                    video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.webm'}
                    result_paths = [p for p in result_paths
                                    if any(p.lower().endswith(e) for e in video_exts)]
                elif mt == "photo":
                    video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.webm'}
                    result_paths = [p for p in result_paths
                                    if not any(p.lower().endswith(e) for e in video_exts)]
            result.paths = result_paths

        self._active_query_label = result.query_label
        self._show_active_indicator(result.query_label, result.total_matches)
        self._add_recent(result.query_label, query, result.total_matches)
        self.smartFindTriggered.emit(result.paths, result.query_label)

    def _on_refine_changed(self, _=None):
        """Re-run current find with updated refine filters."""
        if self._active_preset_id:
            extra_filters = self._get_refine_filters()
            QTimer.singleShot(0, lambda: self._run_preset_find(
                self._active_preset_id, extra_filters))
        elif self._pending_text_query and len(self._pending_text_query) >= 3:
            self._execute_text_search()

    def _clear_find(self):
        """Clear all Smart Find state and restore full photo grid."""
        self._active_preset_id = None
        self._active_query_label = None
        self._set_chip_active("")

        if hasattr(self, '_active_indicator'):
            self._active_indicator.hide()

        # Reset refine facets
        if hasattr(self, '_date_combo'):
            self._date_combo.setCurrentIndex(0)
        if hasattr(self, '_type_combo'):
            self._type_combo.setCurrentIndex(0)
        if hasattr(self, '_gps_check'):
            self._gps_check.setChecked(False)
        if hasattr(self, '_rating_combo'):
            self._rating_combo.setCurrentIndex(0)

        # Clear search field
        if hasattr(self, '_search_field'):
            self._search_field.clear()

        self.smartFindCleared.emit()

    def _show_active_indicator(self, label: str, count: int):
        """Show the active query indicator at top of section."""
        if hasattr(self, '_active_indicator') and hasattr(self, '_active_label'):
            if count > 0:
                self._active_label.setText(f"{label}  —  {count} photos found")
            else:
                self._active_label.setText(f"{label}  —  No matches")
            self._active_indicator.show()

    # ── Recent Searches ──

    def _add_recent(self, label: str, query_or_id: str, count: int):
        """Add a search to recent history (max 8)."""
        # Remove duplicate
        self._recent_searches = [
            r for r in self._recent_searches if r["query"] != query_or_id
        ]
        self._recent_searches.insert(0, {
            "label": label, "query": query_or_id, "count": count
        })
        self._recent_searches = self._recent_searches[:8]
        self._update_recent_ui()

    def _update_recent_ui(self):
        """Refresh the recent searches UI."""
        if not hasattr(self, '_recent_layout'):
            return

        # Clear
        while self._recent_layout.count():
            child = self._recent_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self._recent_searches:
            return

        header = QLabel("Recent")
        header.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #5f6368; "
            "padding: 4px 0 2px 2px;"
        )
        self._recent_layout.addWidget(header)

        for item in self._recent_searches:
            btn = QPushButton(f"  {item['label']}  ({item['count']})")
            btn.setMinimumHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent; border: none;
                    text-align: left; font-size: 12px;
                    color: #202124; padding: 4px 8px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: #f1f3f4;
                }
            """)
            query = item["query"]
            btn.clicked.connect(lambda _, q=query: self._on_recent_clicked(q))
            self._recent_layout.addWidget(btn)

    def _on_recent_clicked(self, query_or_id: str):
        """Re-run a recent search."""
        # Check if it's a preset ID
        from services.smart_find_service import BUILTIN_PRESETS
        for p in BUILTIN_PRESETS:
            if p["id"] == query_or_id:
                self._on_preset_clicked(query_or_id)
                return

        # Otherwise treat as text query
        self._search_field.setText(query_or_id)
        self._pending_text_query = query_or_id
        self._execute_text_search()

    def cleanup(self):
        """Clean up resources."""
        self._search_debounce.stop()
        logger.debug("[FindSection] Cleanup")
