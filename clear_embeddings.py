"""
Clear Existing Embeddings

This script clears all existing photo embeddings from the database,
forcing re-extraction with the new large CLIP model.

Run this AFTER downloading the large model with download_large_clip_model.py

Usage:
    python clear_embeddings.py

What it does:
    1. Backs up current embeddings (optional)
    2. Deletes all embeddings from photo_embeddings table
    3. Resets embedding_models table
    4. Next extraction will use the new large model

IMPORTANT: This will delete all existing embeddings!
You'll need to re-extract embeddings for all photos.
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime


def find_database():
    """Find the reference database file."""
    # Common locations
    possible_paths = [
        Path.cwd() / 'data' / 'reference.db',
        Path.cwd() / 'reference.db',
        Path.home() / '.memorymate' / 'reference.db',
    ]

    for path in possible_paths:
        if path.exists():
            return path

    return None


def backup_embeddings(db_path: Path):
    """Create a backup of current embeddings."""
    backup_file = db_path.parent / f"embeddings_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get count
        cursor.execute("SELECT COUNT(*) FROM photo_embeddings")
        count = cursor.fetchone()[0]

        if count == 0:
            print("  No embeddings to backup (table is empty)")
            conn.close()
            return None

        # Export to SQL
        with open(backup_file, 'w') as f:
            for line in conn.iterdump():
                if 'photo_embeddings' in line or 'embedding_models' in line:
                    f.write(f"{line}\n")

        conn.close()

        print(f"  ✓ Backup created: {backup_file}")
        print(f"  ✓ Backed up {count} embeddings")
        return backup_file

    except Exception as e:
        print(f"  ⚠ Backup failed: {e}")
        return None


def clear_embeddings():
    """Clear all embeddings from database."""

    print("=" * 70)
    print("Clear Embeddings for CLIP Model Upgrade")
    print("=" * 70)
    print()

    # Find database
    print("[Step 1/3] Locating database...")
    db_path = find_database()

    if not db_path:
        print("  ✗ Database not found!")
        print()
        print("Please specify the database path:")
        db_input = input("  Path to reference.db: ").strip()
        db_path = Path(db_input)

        if not db_path.exists():
            print(f"  ✗ File not found: {db_path}")
            sys.exit(1)

    print(f"  ✓ Found database: {db_path}")
    print()

    # Connect and check
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if tables exist
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN ('photo_embeddings', 'embedding_models')
        """)
        tables = [row[0] for row in cursor.fetchall()]

        if 'photo_embeddings' not in tables:
            print("  ⚠ photo_embeddings table doesn't exist (nothing to clear)")
            conn.close()
            return

        # Get current count
        cursor.execute("SELECT COUNT(*) FROM photo_embeddings")
        count = cursor.fetchone()[0]

        print(f"  ✓ Found {count} embeddings to clear")
        print()

    except Exception as e:
        print(f"  ✗ Database error: {e}")
        sys.exit(1)

    # Backup
    print("[Step 2/3] Creating backup...")
    backup_file = backup_embeddings(db_path)
    print()

    # Confirm
    print("[Step 3/3] Ready to clear embeddings")
    print()
    print(f"  Database: {db_path}")
    print(f"  Embeddings to delete: {count}")
    if backup_file:
        print(f"  Backup: {backup_file}")
    print()

    confirm = input("  Continue? [y/N]: ").strip().lower()
    if confirm != 'y':
        print("\n  Cancelled by user")
        conn.close()
        return

    print()
    print("  Clearing embeddings...")

    try:
        # Delete embeddings
        cursor.execute("DELETE FROM photo_embeddings")
        deleted_embeddings = cursor.rowcount

        # Reset models table
        if 'embedding_models' in tables:
            cursor.execute("DELETE FROM embedding_models")
            deleted_models = cursor.rowcount
        else:
            deleted_models = 0

        # Commit
        conn.commit()
        conn.close()

        print(f"  ✓ Deleted {deleted_embeddings} embeddings")
        if deleted_models > 0:
            print(f"  ✓ Deleted {deleted_models} model entries")

    except Exception as e:
        print(f"  ✗ Delete failed: {e}")
        conn.rollback()
        conn.close()
        sys.exit(1)

    print()
    print("=" * 70)
    print("SUCCESS! Embeddings cleared")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Open MemoryMate-PhotoFlow app")
    print("  2. Go to Tools menu")
    print("  3. Click 'Extract Embeddings'")
    print("  4. Wait for extraction to complete (uses new large model)")
    print("  5. Try semantic search with better results!")
    print()
    print("Expected timeline:")
    print(f"  - Extracting {count} photos: ~{count * 0.2:.0f} seconds ({count * 0.2 / 60:.1f} minutes)")
    print("  - First search will load model: +5-10 seconds")
    print("  - Subsequent searches: instant")
    print()


if __name__ == '__main__':
    try:
        clear_embeddings()
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
