# Troubleshooting: "no such table: ml_job" Error

## Problem

When trying to extract embeddings, you see this error:

```
sqlite3.OperationalError: no such table: ml_job
```

## Root Cause

Your database is missing the `ml_job` table, which was introduced in migration v6.0.0. This happens when:

1. You're using an older database that hasn't been migrated to the latest schema
2. The application failed to run migrations automatically on startup

## Solution

### Option 1: Run the Fix Script (Recommended)

We've provided a simple script to fix your database:

```bash
python3 fix_database.py
```

This script will:
- Check which tables are missing
- Apply migration v6.0.0 (creates `ml_job` and other ML infrastructure tables)
- Apply migration v7.0.0 (creates `semantic_embeddings` table)
- Verify everything is working

### Option 2: Manual Migration

If the script doesn't work, you can apply the migrations manually:

1. **Open Python in your project directory:**

   ```bash
   python3
   ```

2. **Run these commands:**

   ```python
   import sys
   sys.path.insert(0, '.')

   from repository.base_repository import DatabaseConnection
   from migrations import migration_v6_visual_semantics

   # Connect to database
   db = DatabaseConnection()

   with db.get_connection() as conn:
       # Apply migration v6
       migration_v6_visual_semantics.migrate_up(conn)

       # Verify
       success, errors = migration_v6_visual_semantics.verify_migration(conn)
       if success:
           print("✓ Migration v6.0.0 applied successfully")
       else:
           print("✗ Migration failed:")
           for error in errors:
               print(f"  - {error}")
   ```

3. **Also apply migration v7 (semantic embeddings):**

   ```python
   # Read migration SQL
   with open('migrations/migration_v7_semantic_separation.sql', 'r') as f:
       sql = f.read()

   with db.get_connection() as conn:
       conn.executescript(sql)
       conn.commit()
       print("✓ Migration v7.0.0 applied successfully")
   ```

4. **Exit Python:**

   ```python
   exit()
   ```

### Option 3: Database Reset (Last Resort)

If migrations fail, you can reset your database (⚠️ **WARNING: This will delete all data!**):

1. **Backup your current database** (if you want to keep any data):

   ```bash
   cp reference_data.db reference_data.db.backup
   ```

2. **Delete the database file:**

   ```bash
   rm reference_data.db
   ```

3. **Restart the application** - it will create a fresh database with all tables

## What Gets Fixed

After running the fix, these tables will be created:

### Migration v6.0.0 Tables

- `ml_model` - Registry of ML models (CLIP, BLIP2, etc.)
- `ml_job` - Job queue for background ML tasks
- `photo_embedding` - Visual embeddings for search
- `photo_caption` - AI-generated captions
- `photo_tag_suggestion` - ML-suggested tags
- `photo_tag_decision` - User decisions on tag suggestions
- `photo_detection` - Object detections
- `event` and `event_photo` - Event clustering

### Migration v7.0.0 Tables

- `semantic_embeddings` - Semantic embeddings (separate from face embeddings)
- `semantic_index_meta` - Metadata for semantic search index

## Verification

After applying the fix, verify it worked:

```bash
python3 fix_database.py
```

You should see:

```
✓ Database is already up to date!
```

## Still Having Issues?

If the error persists after running the fix:

1. **Check that migrations were actually applied:**

   ```bash
   sqlite3 reference_data.db "SELECT version, description FROM schema_version ORDER BY applied_at;"
   ```

   You should see versions up to at least 6.0.0 and 7.0.0.

2. **Check that ml_job table exists:**

   ```bash
   sqlite3 reference_data.db ".tables" | grep ml_job
   ```

   If `ml_job` doesn't appear, the migration didn't run successfully.

3. **Check the application logs** for more detailed error messages.

4. **Try Option 3 (Database Reset)** as a last resort.

## Understanding the Architecture

The new system separates different types of AI embeddings:

- **Face Embeddings** (`face_crops.embedding`) - For face recognition
- **Semantic Embeddings** (`semantic_embeddings.embedding`) - For visual similarity and text search

This clean separation was introduced in Phase 1 of the semantic embedding implementation. See `SEMANTIC_EMBEDDING_IMPLEMENTATION_SUMMARY.md` for full details.

## Related Files

- `fix_database.py` - Automated fix script
- `apply_migrations.py` - Alternative migration runner
- `migrations/migration_v6_visual_semantics.py` - Migration v6 code
- `migrations/migration_v6_visual_semantics_create.sql` - Migration v6 SQL
- `migrations/migration_v7_semantic_separation.sql` - Migration v7 SQL

## Support

If none of these solutions work, please:

1. Run `python3 fix_database.py` and save the output
2. Check `app_log.txt` for error messages
3. Report the issue with both outputs attached
