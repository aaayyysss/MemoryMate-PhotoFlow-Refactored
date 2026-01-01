r"""
Offline CLIP Model Downloader
===============================

This script downloads the CLIP model with SSL verification disabled,
for use in portable Python environments without proper SSL certificates.

Usage:
    python download_clip_model_offline.py

The model will be downloaded to the HuggingFace cache directory:
Windows: C:/Users/<username>/.cache/huggingface/hub/models--openai--clip-vit-base-patch32/
Linux:   ~/.cache/huggingface/hub/models--openai--clip-vit-base-patch32/
"""

import os
import sys
import urllib.request
import ssl
import json
from pathlib import Path

# Disable SSL verification
ssl._create_default_https_context = ssl._create_unverified_context

# Model files to download
MODEL_NAME = "openai/clip-vit-base-patch32"
BASE_URL = "https://huggingface.co/openai/clip-vit-base-patch32/resolve/main/"

FILES_TO_DOWNLOAD = [
    "config.json",
    "preprocessor_config.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "tokenizer.json",
    "special_tokens_map.json",
    "pytorch_model.bin"  # Large file ~600MB
]

def get_cache_dir():
    """Get the HuggingFace cache directory."""
    if os.name == 'nt':  # Windows
        cache_dir = Path(os.environ.get('USERPROFILE', 'C:\\')) / '.cache' / 'huggingface' / 'hub'
    else:  # Linux/Mac
        cache_dir = Path(os.environ.get('HOME', '/tmp')) / '.cache' / 'huggingface' / 'hub'

    # Model-specific directory
    model_dir = cache_dir / 'models--openai--clip-vit-base-patch32' / 'snapshots' / 'main'
    return model_dir

def download_file(url, dest_path, filename):
    """Download a file with SSL verification disabled."""
    print(f"\n📥 Downloading: {filename}")
    print(f"   URL: {url}")
    print(f"   Destination: {dest_path}")

    try:
        # Download with progress
        def progress_callback(block_num, block_size, total_size):
            if total_size > 0:
                downloaded = block_num * block_size
                percent = min(100, (downloaded * 100) // total_size)
                mb_downloaded = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r   Progress: {percent}% ({mb_downloaded:.1f}MB / {mb_total:.1f}MB)", end='')

        urllib.request.urlretrieve(url, dest_path, reporthook=progress_callback)
        print()  # New line after progress
        print(f"   ✅ Downloaded successfully!")
        return True

    except Exception as e:
        print(f"\n   ❌ Error downloading {filename}: {e}")
        return False

def main():
    """Main download function."""
    print("=" * 70)
    print("CLIP Model Offline Downloader (SSL Verification Disabled)")
    print("=" * 70)

    # Get cache directory
    cache_dir = get_cache_dir()
    print(f"\n📁 Cache directory: {cache_dir}")

    # Create directory if it doesn't exist
    cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"✅ Cache directory created/verified")

    # Download each file
    print(f"\n📦 Downloading {len(FILES_TO_DOWNLOAD)} files...")

    success_count = 0
    failed_files = []

    for filename in FILES_TO_DOWNLOAD:
        url = BASE_URL + filename
        dest_path = cache_dir / filename

        # Skip if already exists
        if dest_path.exists():
            file_size_mb = dest_path.stat().st_size / (1024 * 1024)
            print(f"\n⏭️  Skipping {filename} (already exists, {file_size_mb:.1f}MB)")
            success_count += 1
            continue

        # Download
        if download_file(url, dest_path, filename):
            success_count += 1
        else:
            failed_files.append(filename)

    # Summary
    print("\n" + "=" * 70)
    print("DOWNLOAD SUMMARY")
    print("=" * 70)
    print(f"✅ Successfully downloaded: {success_count}/{len(FILES_TO_DOWNLOAD)} files")

    if failed_files:
        print(f"❌ Failed to download: {len(failed_files)} files")
        for f in failed_files:
            print(f"   - {f}")
        print("\n⚠️  Please try running this script again or download manually from:")
        print(f"   https://huggingface.co/{MODEL_NAME}/tree/main")
        return 1
    else:
        print("\n🎉 All files downloaded successfully!")
        print("\n📝 Next steps:")
        print("   1. Close and restart your application")
        print("   2. Try the embedding extraction feature again")
        print("   3. The model should now load from the local cache")
        return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n❌ Download cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
