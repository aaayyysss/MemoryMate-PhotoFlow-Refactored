"""
Pre-Scan Options Dialog
Phase 3B: Scan Integration

Shows options before starting a repository scan:
- Scan type (incremental vs full)
- Duplicate detection toggle
- Similar shot detection settings
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QGroupBox, QSpinBox, QDoubleSpinBox, QRadioButton,
    QButtonGroup, QFrame
)
from PySide6.QtCore import Qt, Signal
from typing import Optional


class PreScanOptions:
    """Data class for pre-scan options."""
    def __init__(self):
        self.incremental = True
        self.detect_duplicates = True
        self.detect_exact = True
        self.detect_similar = True
        self.generate_embeddings = True  # New: Auto-generate embeddings for similar detection
        self.time_window_seconds = 10
        self.similarity_threshold = 0.92
        self.min_stack_size = 3


class PreScanOptionsDialog(QDialog):
    """
    Pre-scan options dialog.

    Allows user to configure:
    - Scan mode (incremental vs full)
    - Duplicate detection settings
    - Similar shot detection parameters
    """

    def __init__(self, parent=None, default_incremental: bool = True):
        super().__init__(parent)
        self.options = PreScanOptions()
        self.options.incremental = default_incremental

        self.setWindowTitle("Scan Options")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._build_ui()
        self._apply_styles()
        self._connect_signals()

    def _build_ui(self):
        """Build dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel("<h2>📸 Scan Repository</h2>")
        layout.addWidget(header)

        info = QLabel("Configure scanning options before starting the scan.")
        info.setStyleSheet("color: #666; margin-bottom: 8px;")
        layout.addWidget(info)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep1)

        # Scan Mode Section
        scan_mode_group = QGroupBox("Scan Mode")
        scan_mode_layout = QVBoxLayout(scan_mode_group)
        scan_mode_layout.setSpacing(8)

        self.radio_incremental = QRadioButton("Incremental (recommended)")
        self.radio_incremental.setToolTip("Only scan new or modified files")
        self.radio_incremental.setChecked(self.options.incremental)

        incremental_desc = QLabel("    Skip unchanged files (faster)")
        incremental_desc.setStyleSheet("color: #666; font-size: 9pt;")

        self.radio_full = QRadioButton("Full rescan")
        self.radio_full.setToolTip("Scan all files, even if unchanged")
        self.radio_full.setChecked(not self.options.incremental)

        full_desc = QLabel("    Re-index all files from scratch")
        full_desc.setStyleSheet("color: #666; font-size: 9pt;")

        scan_mode_layout.addWidget(self.radio_incremental)
        scan_mode_layout.addWidget(incremental_desc)
        scan_mode_layout.addWidget(self.radio_full)
        scan_mode_layout.addWidget(full_desc)

        layout.addWidget(scan_mode_group)

        # Duplicate Detection Section
        dup_group = QGroupBox("Duplicate Detection")
        dup_layout = QVBoxLayout(dup_group)
        dup_layout.setSpacing(12)

        self.chk_detect_duplicates = QCheckBox("Enable duplicate detection")
        self.chk_detect_duplicates.setToolTip("Detect duplicate photos during scan")
        self.chk_detect_duplicates.setChecked(self.options.detect_duplicates)
        dup_layout.addWidget(self.chk_detect_duplicates)

        # Duplicate types container (indented)
        dup_types_widget = QFrame()
        dup_types_layout = QVBoxLayout(dup_types_widget)
        dup_types_layout.setContentsMargins(24, 8, 0, 0)
        dup_types_layout.setSpacing(8)

        self.chk_exact = QCheckBox("🔍 Exact duplicates (identical content)")
        self.chk_exact.setToolTip("Detect photos with identical file content (SHA256)")
        self.chk_exact.setChecked(self.options.detect_exact)
        dup_types_layout.addWidget(self.chk_exact)

        self.chk_similar = QCheckBox("📸 Similar shots (burst photos, series)")
        self.chk_similar.setToolTip("Detect visually similar photos using AI")
        self.chk_similar.setChecked(self.options.detect_similar)
        dup_types_layout.addWidget(self.chk_similar)

        # Embedding generation option (indented)
        self.chk_generate_embeddings = QCheckBox("🤖 Generate AI embeddings (required for similar detection)")
        self.chk_generate_embeddings.setToolTip(
            "Extract visual embeddings using CLIP model.\n"
            "Required for similar shot detection.\n"
            "May add 2-5 seconds per photo depending on hardware."
        )
        self.chk_generate_embeddings.setChecked(self.options.generate_embeddings)
        dup_types_layout.addWidget(self.chk_generate_embeddings)

        # Similar shot settings (indented further)
        similar_settings_widget = QFrame()
        similar_settings_layout = QVBoxLayout(similar_settings_widget)
        similar_settings_layout.setContentsMargins(24, 8, 0, 0)
        similar_settings_layout.setSpacing(8)

        # Time window
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Time window:"))
        self.spin_time_window = QSpinBox()
        self.spin_time_window.setRange(1, 60)
        self.spin_time_window.setValue(self.options.time_window_seconds)
        self.spin_time_window.setSuffix(" seconds")
        self.spin_time_window.setToolTip("Only compare photos within this time range")
        time_row.addWidget(self.spin_time_window)
        time_row.addStretch(1)
        similar_settings_layout.addLayout(time_row)

        # Similarity threshold
        sim_row = QHBoxLayout()
        sim_row.addWidget(QLabel("Similarity:"))
        self.spin_similarity = QDoubleSpinBox()
        self.spin_similarity.setRange(0.80, 0.99)
        self.spin_similarity.setSingleStep(0.01)
        self.spin_similarity.setValue(self.options.similarity_threshold)
        self.spin_similarity.setToolTip("Minimum visual similarity (0.80-0.99)")
        sim_row.addWidget(self.spin_similarity)
        sim_row.addStretch(1)
        similar_settings_layout.addLayout(sim_row)

        # Min stack size
        stack_row = QHBoxLayout()
        stack_row.addWidget(QLabel("Min stack size:"))
        self.spin_stack_size = QSpinBox()
        self.spin_stack_size.setRange(2, 10)
        self.spin_stack_size.setValue(self.options.min_stack_size)
        self.spin_stack_size.setSuffix(" photos")
        self.spin_stack_size.setToolTip("Minimum photos to create a stack")
        stack_row.addWidget(self.spin_stack_size)
        stack_row.addStretch(1)
        similar_settings_layout.addLayout(stack_row)

        similar_settings_widget.setLayout(similar_settings_layout)
        dup_types_layout.addWidget(similar_settings_widget)
        self.similar_settings_widget = similar_settings_widget

        dup_types_widget.setLayout(dup_types_layout)
        dup_layout.addWidget(dup_types_widget)
        self.dup_types_widget = dup_types_widget

        layout.addWidget(dup_group)

        # Info message
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #e8f4f8;
                border: 1px solid #b3d9e6;
                border-radius: 4px;
                padding: 12px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(4)

        info_title = QLabel("💡 Note:")
        info_title.setStyleSheet("font-weight: bold; color: #1a73e8;")
        info_layout.addWidget(info_title)

        info_text = QLabel(
            "Duplicate detection will run automatically after the scan completes. "
            "Exact duplicate detection is fast, but embedding generation and similar "
            "shot detection may take 2-5 seconds per photo depending on hardware (GPU vs CPU)."
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet("color: #444;")
        info_layout.addWidget(info_text)

        layout.addWidget(info_frame)

        # Buttons
        layout.addStretch(1)
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)

        self.btn_start = QPushButton("Start Scan")
        self.btn_start.setDefault(True)
        self.btn_start.clicked.connect(self._on_start_clicked)
        button_layout.addWidget(self.btn_start)

        layout.addLayout(button_layout)

    def _apply_styles(self):
        """Apply custom styles."""
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ddd;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background-color: white;
            }
            QPushButton#btn_start {
                background-color: #1a73e8;
                color: white;
                border: none;
                padding: 8px 24px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton#btn_start:hover {
                background-color: #1557b0;
            }
            QPushButton#btn_start:pressed {
                background-color: #0d47a1;
            }
        """)
        self.btn_start.setObjectName("btn_start")

    def _connect_signals(self):
        """Connect signals."""
        # Enable/disable duplicate types based on main checkbox
        self.chk_detect_duplicates.toggled.connect(self._on_duplicates_toggled)

        # Enable/disable similar settings based on similar checkbox
        self.chk_similar.toggled.connect(self._on_similar_toggled)

        # Initial state
        self._on_duplicates_toggled(self.chk_detect_duplicates.isChecked())
        self._on_similar_toggled(self.chk_similar.isChecked())

    def _on_duplicates_toggled(self, checked: bool):
        """Handle duplicate detection toggle."""
        self.dup_types_widget.setEnabled(checked)

    def _on_similar_toggled(self, checked: bool):
        """Handle similar shots toggle."""
        self.similar_settings_widget.setEnabled(checked)

    def _on_start_clicked(self):
        """Handle start button click."""
        # Save options
        self.options.incremental = self.radio_incremental.isChecked()
        self.options.detect_duplicates = self.chk_detect_duplicates.isChecked()
        self.options.detect_exact = self.chk_exact.isChecked()
        self.options.detect_similar = self.chk_similar.isChecked()
        self.options.generate_embeddings = self.chk_generate_embeddings.isChecked()
        self.options.time_window_seconds = self.spin_time_window.value()
        self.options.similarity_threshold = self.spin_similarity.value()
        self.options.min_stack_size = self.spin_stack_size.value()

        self.accept()

    def get_options(self) -> PreScanOptions:
        """Get the configured options."""
        return self.options
