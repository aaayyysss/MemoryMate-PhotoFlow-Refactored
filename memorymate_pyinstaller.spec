# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for MemoryMate-PhotoFlow
Includes proper packaging of InsightFace models and dependencies
"""

import os
import sys
from pathlib import Path

# SECURITY NOTE: PyInstaller 6.0+ removed AES bytecode encryption
# Alternative protections still active:
# - One-file mode (harder to extract)
# - UPX compression (obfuscates structure)
# - Bytecode-only distribution (no .py source files)
# For maximum protection, consider using PyArmor or Nuitka separately

# Get the InsightFace models directory


# PyInstaller executes spec via exec(); __file__ may be undefined.
# SPECPATH is provided by PyInstaller and points to the spec directory.
project_root = Path(SPECPATH).resolve()
insightface_models_dir = project_root / 'models' / 'buffalo_l'

# Collect all model files
model_datas = []
#if os.path.exists(insightface_models_dir):
#if os.path.exists(str(insightface_models_dir)):
if insightface_models_dir.exists():
    for root, dirs, files in os.walk(insightface_models_dir):
        for file in files:
            src = os.path.join(root, file)
            # Map to insightface/models/buffalo_l in the bundle
            rel_path = os.path.relpath(src, os.path.dirname(insightface_models_dir))
            dst = os.path.join('insightface', 'models', os.path.dirname(rel_path))
            model_datas.append((src, dst))
    print(f"Found {len(model_datas)} model files in {insightface_models_dir}")
else:
    print(f"WARNING: InsightFace models not found at {insightface_models_dir}")
    print("Please run face detection once to download models before packaging")

# Additional data files
datas = [
    # Language files (both directories)
    ('lang', 'lang'),
    ('locales', 'locales'),

    # Configuration files
    ('config', 'config'),

	# Layout files
	('layouts', 'layouts'),

    # SQL migration files
    ('migrations', 'migrations'),

    # Python package directories (required for imports)
	('controllers', 'controllers'),
    ('repository', 'repository'),
    ('services', 'services'),
    ('workers', 'workers'),
    ('ui', 'ui'),
    ('utils', 'utils'),

    # CRITICAL: Google Photos components (PhotoButton, MediaLightbox, etc.)
    ('google_components', 'google_components'),

    # Note: Databases are excluded as requested (reference_data.db, thumb_cache_db, etc.)
    # Users will create fresh databases on first run
]

# Add model files
datas.extend(model_datas)

# CRITICAL: Bundle FFmpeg binaries for video support
import shutil
ffmpeg_exe = shutil.which('ffmpeg')
ffprobe_exe = shutil.which('ffprobe')

if ffmpeg_exe and ffprobe_exe:
    datas.append((ffmpeg_exe, '.'))
    datas.append((ffprobe_exe, '.'))
    print(f"✓ Bundled ffmpeg: {ffmpeg_exe}")
    print(f"✓ Bundled ffprobe: {ffprobe_exe}")
else:
    print("⚠ WARNING: FFmpeg not found on PATH")
    print("   Video thumbnails and metadata will not work!")
    print("   Install FFmpeg and add to PATH, then re-run PyInstaller")

# Hidden imports for ML libraries and project modules
hiddenimports = [
    # ML/AI libraries
    'insightface',
    'insightface.app',
    'insightface.model_zoo',
    'onnxruntime',
    'onnxruntime.capi',
    'onnxruntime.capi.onnxruntime_pybind11_state',
    'numpy',
    'numpy.core',  # CRITICAL: Required for np.array() in PyInstaller
    'numpy.core._methods',  # CRITICAL: Required for array operations
    'numpy.lib',  # Required for numpy utilities
    'numpy.lib.format',  # Required for array serialization
    'cv2',
    'cv2.cv2',  # CRITICAL: Explicit cv2 binary module for PyInstaller
    'PIL',
    'PIL.Image',
    'PIL.ImageOps',
    'PIL.ImageQt',
    'sklearn',
    'sklearn.cluster',
    'sklearn.preprocessing',
    'sklearn.__check_build',  # CRITICAL: Required for sklearn in PyInstaller
    'sklearn.__check_build._check_build',  # C extension for sklearn
    'sklearn.utils',
    'sklearn.utils._cython_blas',  # Required for DBSCAN clustering
    'sklearn.neighbors',  # Required for clustering algorithms
    'sklearn.neighbors._partition_nodes',  # C extension

    # RAW image support (DSLR cameras: CR2, NEF, ARW, DNG, etc.)
    'rawpy',

    # Qt framework
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtWebEngineWidgets',  # CRITICAL: Embedded map view in GPS location editor
    'PySide6.QtWebEngineCore',     # CRITICAL: WebEngine core for map rendering
    'PySide6.QtWebChannel',        # CRITICAL: JavaScript ↔ Python communication for map

    # Windows COM support (pywin32)
    'win32com',
    'win32com.client',
    'win32com.shell',
    'win32api',
    'win32con',
    'pythoncom',
    'pywintypes',
    'ctypes',
    'ctypes.wintypes',  # Required by device_monitor.py for WM_DEVICECHANGE

    # HEIF/HEIC image support (iPhone photos)
    'pillow_heif',
    'pillow_heif.heif',

    # Matplotlib (required by InsightFace for visualization/plotting)
    'matplotlib',
    'matplotlib.pyplot',
    'matplotlib.backends',
    'matplotlib.backends.backend_agg',

    # Project modules
	'controllers',
	'controllers.photo_operations_controller',
	'controllers.project_controller',
	'controllers.scan_controller',
	'controllers.sidebar_controller',
	
	'layouts',
	'layouts.apple_layout',
	'layouts.base_layout',
	'layouts.current_layout',
	'layouts.google_layout',
	'layouts.lightroom_layout',
	'layouts.layout_manager',
	'layouts.layout_protocol',  # Layout protocol interface
	'layouts.video_editor_mixin',  # Video editing mixin for layouts
	
    'repository',
    'repository.base_repository',
    'repository.folder_repository',
    'repository.photo_repository',
    'repository.project_repository',
    'repository.tag_repository',
    'repository.video_repository',
    'repository.migrations',
    'repository.schema',

    'services',
    'services.device_id_extractor',
    'services.device_import_service',
    'services.device_sources',
    'services.device_monitor',  # CRITICAL: Added in Phase 2 (Windows device detection)
    'services.exif_parser',
	'services.face_detection_benchmark',
	'services.face_detection_service',
    'services.geocoding_service',  # CRITICAL: GPS location geocoding (forward/reverse)
    'services.metadata_service',
    'services.mtp_import_adapter',
    'services.photo_deletion_service',
    'services.photo_scan_service',
    'services.scan_worker_adapter',  # Scan worker compatibility layer
    'services.search_service',
    'services.tag_service',
	'services.thumbnail_manager',
    'services.thumbnail_service',
    'services.video_metadata_service',
    'services.video_service',
    'services.video_thumbnail_service',

    'workers',
    'workers.face_cluster_worker',
    'workers.face_detection_worker',
    'workers.meta_backfill_pool',
    'workers.meta_backfill_single',
    'workers.mtp_copy_worker',
    'workers.progress_writer',
    'workers.video_metadata_worker',
    'workers.video_thumbnail_worker',

    'ui',
    'ui.advanced_filters_widget',  # Advanced search filters widget
    'ui.cluster_face_selector',  # Face clustering selector
    'ui.device_import_dialog',
    'ui.embedding_progress_dialog',  # Embedding generation progress dialog
    'ui.face_crop_editor',  # CRITICAL: Face crop editor (manual face cropping)
    'ui.face_detection_config_dialog',  # Face detection configuration
    'ui.face_detection_progress_dialog',  # Face detection progress tracking
    'ui.face_naming_dialog',  # Face naming dialog
    'ui.face_quality_dashboard',  # Face quality scoring dashboard
    'ui.face_quality_scorer',  # Face quality scoring utility
    'ui.face_settings_dialog',
    'ui.location_editor_dialog',  # CRITICAL: GPS location editor with embedded map
    'ui.location_editor_integration',  # CRITICAL: GPS location save integration layer
    'ui.mtp_deep_scan_dialog',
    'ui.mtp_import_dialog',
    'ui.people_list_view',
    'ui.people_manager_dialog',
    'ui.performance_analytics_dialog',  # Performance analytics and metrics
    'ui.semantic_search_dialog',  # Semantic search dialog
    'ui.semantic_search_widget',  # CRITICAL: Semantic search widget (Google Layout)
    'ui.similar_photos_dialog',  # Similar photos finder
    'ui.ui_builder',
    'ui.visual_photo_browser',  # Visual photo browser

	'ui.panels',
	'ui.panels.backfill_status_panel',
	'ui.panels.details_panel',

	'ui.widgets',
	'ui.widgets.backfill_indicator',
	'ui.widgets.breadcrumb_navigation',
	'ui.widgets.selection_toolbar',

	# CRITICAL: Accordion sidebar package (Phase 2 sidebar refactor)
	'ui.accordion_sidebar',
	'ui.accordion_sidebar.base_section',
	'ui.accordion_sidebar.dates_section',
	'ui.accordion_sidebar.devices_section',
	'ui.accordion_sidebar.folders_section',
	'ui.accordion_sidebar.locations_section',  # CRITICAL: GPS locations sidebar section
	'ui.accordion_sidebar.people_section',
	'ui.accordion_sidebar.quick_section',
	'ui.accordion_sidebar.section_widgets',
	'ui.accordion_sidebar.videos_section',

    'utils',
	'utils.diagnose_insightface',
	'utils.dpi_helper',  # CRITICAL: DPI/resolution adaptive scaling helper
	'utils.ffmpeg_check',
	'utils.insightface_check',
	'utils.test_insightface_models',
    'utils.translation_manager',

    # Google Photos components (PhotoButton, MediaLightbox, etc.)
    'google_components',
    'google_components.photo_helpers',  # CRITICAL: PhotoButton with tag badges
    'google_components.widgets',  # Google Photos UI widgets
    'google_components.dialogs',  # Google Photos dialogs
    'google_components.media_lightbox',  # Media lightbox viewer

    # Core app modules
    'config.face_detection_config',
    'logging_config',
    'db_config',
    'db_performance_optimizations',
    'db_writer',
    'settings_manager_qt',
    'app_services',

    # Database modules (CRITICAL - required for photo management)
    'reference_db',  # Main photo database
    'thumb_cache_db',  # Thumbnail cache database

    # Root-level UI modules (CRITICAL - often missed in PyInstaller specs)
    'main_window_qt',
    'sidebar_qt',
    'accordion_sidebar',  # CRITICAL: Root-level accordion sidebar controller
    'search_widget_qt',
    'thumbnail_grid_qt',
    'preview_panel_qt',
    'video_player_qt',
    'splash_qt',
    'preferences_dialog',
    'video_backfill_dialog',
    'translation_manager',  # Root-level translation manager
]

a = Analysis(
    ['main_qt.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_insightface.py'],  # Hook to set InsightFace model paths
    excludes=[
        'tkinter',     # Exclude if not needed (not used by app)
        'pytest',      # Test framework not needed in production
        'tests',       # Test files not needed
		

        # ------------------------------------------------------------------
        # CRITICAL: Prevent PyInstaller from collecting multiple Qt bindings.
        # Your environment has PySide6 (needed) AND PyQt5 (extraneous).
        # PyInstaller aborts when both are detected.
        # ------------------------------------------------------------------
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PyQt5.sip',
        'sip',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PySide2',
		
		
        'utils.test_insightface_models',
        'utils.diagnose_insightface',
        'utils.insightface_check',
        'utils.ffmpeg_check',
        'IPython',
        'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    # cipher parameter removed in PyInstaller 6.0+
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    # cipher parameter removed in PyInstaller 6.0+
    # Bytecode is still compiled (.pyc) but not AES encrypted
)

exe = EXE(
    pyz,
    a.scripts,
#    # SECURITY: ONE-FILE MODE - Everything packed in single encrypted .exe
#    a.binaries,
#    a.zipfiles,
#    a.datas,

    # NOTE: Use ONEDIR for ML apps (faster startup, fewer temp-extract issues,
    # better with large models + native deps like onnxruntime/cv2).
    [],
    exclude_binaries=True,
    
    name='MemoryMate-PhotoFlow-v3.1.0',  # Updated: GPS location features + scrollable thumbnails
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # SECURITY: Compress executable to obfuscate structure
    upx_exclude=[],
    runtime_tmpdir=None,  # Extract to temp on each run
    console=True,  # No console window
    disable_windowing_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)

# COLLECT is not needed for one-file mode - comment out or delete
# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,  # SECURITY: Compress all DLLs and binaries
#     upx_exclude=[],
#     name='MemoryMate-PhotoFlow'
# )

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,  # Optional: if runtime issues, set upx=False first
    upx_exclude=[],
    name='MemoryMate-PhotoFlow-v3.1.0'
)
