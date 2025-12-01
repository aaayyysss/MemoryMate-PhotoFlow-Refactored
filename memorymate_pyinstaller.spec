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
insightface_models_dir = os.path.expanduser('~/.insightface/models/buffalo_l')

# Collect all model files
model_datas = []
if os.path.exists(insightface_models_dir):
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
	'layout_manager',
	'layouts.lightroom_layout',
	
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
    'ui.device_import_dialog',
    'ui.face_settings_dialog',
    'ui.mtp_deep_scan_dialog',
    'ui.mtp_import_dialog',
    'ui.people_list_view',
    'ui.people_manager_dialog',
	'ui.ui_builder',
	
	'ui.panels',
	'ui.panels.backfill_status_panel',
	'ui.panels.details_panel',
	
	'ui.widgets',
	'ui.widgets.backfill_indicator',
	'ui.widgets.breadcrumb_navigation',
	'ui.widgets.selection_toolbar',

    'utils',
	'utils.diagnose_insightface',
	'utils.dpi_helper',  # CRITICAL: DPI/resolution adaptive scaling helper
	'utils.ffmpeg_check',
	'utils.insightface_check',
	'utils.test_insightface_models',
    'utils.translation_manager',

    # Core app modules
    'config.face_detection_config',
    'logging_config',
    'db_config',
    'db_writer',
    'settings_manager_qt',
    'app_services',

    # Root-level UI modules (CRITICAL - often missed in PyInstaller specs)
    'main_window_qt',
    'sidebar_qt',
    'search_widget_qt',
    'thumbnail_grid_qt',
    'preview_panel_qt',
    'video_player_qt',
    'splash_qt',
    'preferences_dialog',
    'video_backfill_dialog',
    'reference_db',
    'thumb_cache_db',
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
    # SECURITY: ONE-FILE MODE - Everything packed in single encrypted .exe
    a.binaries,
    a.zipfiles,
    a.datas,
    
    name='MemoryMate-PhotoFlow-v3.0.2',  # Updated version with face detection fix
    debug=False,
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