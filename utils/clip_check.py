"""
CLIP model availability checker with user-friendly notifications.

Provides clear guidance when CLIP embedding models are not installed.
"""

import os
import logging
from pathlib import Path
from typing import Tuple, Dict

logger = logging.getLogger(__name__)

# Known commit hash for CLIP ViT-B/32 model
COMMIT_HASH = "e6a30b603a447e251fdaca1c3056b2a16cdfebeb"

# Required CLIP model files
REQUIRED_FILES = [
    "config.json",
    "preprocessor_config.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "tokenizer.json",
    "special_tokens_map.json",
    "pytorch_model.bin"  # ~600MB
]


def check_clip_availability() -> Tuple[bool, str]:
    """
    Check if CLIP model files are available.

    Returns:
        Tuple[bool, str]: (available, message)
            - available: True if CLIP model files are ready
            - message: Status message for user display
    """
    # Check if models exist in any of the standard locations
    model_locations = _get_model_search_paths()
    models_found = False
    model_path = None

    for location in model_locations:
        # First, check if there's a models/clip-vit-base-patch32 directory
        base_dir = Path(location) / 'models' / 'clip-vit-base-patch32'
        if not base_dir.exists():
            continue

        # Check for snapshots directory
        snapshots_dir = base_dir / 'snapshots'
        if not snapshots_dir.exists():
            continue

        # Look for ANY commit hash directory in snapshots/
        for commit_dir in snapshots_dir.iterdir():
            if commit_dir.is_dir():
                # Check if this directory has all required files
                if _verify_model_files(str(commit_dir)):
                    models_found = True
                    model_path = str(commit_dir)
                    break

        if models_found:
            break

    if models_found:
        message = f"✅ CLIP model detected\n   Location: {model_path}"
        return True, message
    else:
        message = _get_install_message()
        return False, message


def _get_model_search_paths() -> list:
    """
    Get list of paths to search for CLIP models.

    Priority order:
    1. App directory (./models/clip-vit-base-patch32/)
    2. Custom path from settings (for offline use)
    """
    import sys

    paths = []

    # 1. App directory (primary location)
    try:
        app_root = Path(__file__).parent.parent
        paths.append(str(app_root))
    except Exception:
        pass

    # 2. Custom path from settings (optional)
    try:
        from settings_manager_qt import SettingsManager
        settings = SettingsManager()
        custom_path = settings.get_setting('clip_model_path', '')
        if custom_path:
            custom_path = Path(custom_path)
            if custom_path.exists():
                # Check if this is the snapshot directory itself
                if (custom_path / 'pytorch_model.bin').exists():
                    # This is the snapshot dir, use great-grandparent as root
                    paths.append(str(custom_path.parent.parent.parent))
                elif (custom_path / 'models' / 'clip-vit-base-patch32').exists():
                    # This is the app root
                    paths.append(str(custom_path))
                else:
                    # Add it anyway, might have different structure
                    paths.append(str(custom_path))
    except Exception:
        pass

    return paths


def _verify_model_files(snapshot_path: str) -> bool:
    """
    Verify that all essential CLIP model files exist in snapshot directory.

    Args:
        snapshot_path: Path to snapshots/<commit_hash> directory

    Returns:
        True if all essential files are present, False otherwise
    """
    snapshot_path = Path(snapshot_path)

    # Check all required files
    for filename in REQUIRED_FILES:
        file_path = snapshot_path / filename
        if not file_path.exists():
            logger.debug(f"Missing CLIP model file: {filename}")
            return False

    # Also check refs/main file exists (but don't validate hash - accept any version)
    refs_main = snapshot_path.parent.parent / 'refs' / 'main'
    if not refs_main.exists():
        logger.debug("Missing refs/main file")
        return False

    return True


def get_clip_download_status() -> Dict[str, any]:
    """
    Get detailed status of CLIP model installation.

    Returns:
        Dictionary with:
            - 'models_available': bool
            - 'model_path': str or None
            - 'missing_files': list of missing file names
            - 'total_size_mb': float (approximate)
            - 'message': str
    """
    status = {
        'models_available': False,
        'model_path': None,
        'missing_files': [],
        'total_size_mb': 0.0,
        'message': ''
    }

    # Check models
    model_locations = _get_model_search_paths()
    for location in model_locations:
        base_dir = Path(location) / 'models' / 'clip-vit-base-patch32'
        if not base_dir.exists():
            continue

        snapshots_dir = base_dir / 'snapshots'
        if not snapshots_dir.exists():
            continue

        # Look for ANY commit hash directory
        for commit_dir in snapshots_dir.iterdir():
            if not commit_dir.is_dir():
                continue

            # Check which files are missing
            missing = []
            total_size = 0

            for filename in REQUIRED_FILES:
                file_path = commit_dir / filename
                if file_path.exists():
                    total_size += file_path.stat().st_size
                else:
                    missing.append(filename)

            if not missing:
                # All files present
                status['models_available'] = True
                status['model_path'] = str(commit_dir)
                status['total_size_mb'] = round(total_size / (1024 * 1024), 1)
                status['message'] = f"✅ CLIP model installed ({status['total_size_mb']} MB)"
                return status
            elif len(missing) < len(REQUIRED_FILES):
                # Some files present
                status['missing_files'] = missing
                status['model_path'] = str(commit_dir)
                status['message'] = f"⚠️ Incomplete installation - {len(missing)} files missing"
                return status

    # No installation found
    status['message'] = "❌ CLIP model not installed"
    status['missing_files'] = REQUIRED_FILES.copy()
    return status


def _get_install_message() -> str:
    """
    Get user-friendly installation message.

    Returns:
        Formatted message with installation instructions
    """
    return """
═══════════════════════════════════════════════════════════════════
⚠️  CLIP Model Files Not Found
═══════════════════════════════════════════════════════════════════

Visual embedding extraction requires CLIP model files.

⚠️ Impact:
  ✅ Photos can still be viewed and organized
  ✅ Face detection will still work
  ❌ Visual semantic search won't work
  ❌ Embedding extraction will be disabled

📥 Download Models:
  Option 1: Run the download script
    python download_clip_model_offline.py

  Option 2: Use the application preferences
    1. Go to Preferences (Ctrl+,)
    2. Navigate to "🔍 Visual Embeddings" section
    3. Click "Download CLIP Model"

💡 Model Details:
   - Model: OpenAI CLIP ViT-B/32
   - Size: ~600MB
   - Location: ./models/clip-vit-base-patch32/
   - Files: 8 files total

After download:
  1. Restart the application (or retry extraction)
  2. Embedding extraction will be automatically enabled
  3. Visual semantic search will be available

═══════════════════════════════════════════════════════════════════
"""


if __name__ == '__main__':
    # Test the checker
    available, message = check_clip_availability()
    print(message)
    print()

    # Show detailed status
    status = get_clip_download_status()
    print("Detailed Status:")
    for key, value in status.items():
        print(f"  {key}: {value}")
