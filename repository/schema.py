# repository/schema.py
# Version 2.0.0 dated 20251103
# Centralized database schema definition for repository layer
#
# This module provides the complete database schema for MemoryMate-PhotoFlow.
# It is the single source of truth for schema creation and versioning.

"""
Centralized database schema definition for repository layer.

This schema is extracted from the legacy reference_db.py and serves as
the canonical definition for all database tables, indexes, and constraints.

Schema Version: 2.0.0
- Includes all 13 tables from production
- Includes all foreign key constraints
- Includes all performance indexes
- Includes created_ts/created_date/created_year columns (previously migrations)
- Adds schema_version tracking table
"""

SCHEMA_VERSION = "9.3.0"

# Complete schema SQL - executed as a script for new databases
SCHEMA_SQL = """
-- ============================================================================
-- SCHEMA VERSION TRACKING
-- ============================================================================
CREATE TABLE IF NOT EXISTS schema_version (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- Insert initial version marker
INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('3.0.0', 'Added project_id to photo_folders and photo_metadata for clean project isolation');

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('3.1.0', 'Added project_id to tags table for proper tag isolation between projects');

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('3.2.0', 'Added complete video infrastructure (video_metadata, project_videos, video_tags)');

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('3.3.0', 'Added compound indexes for query optimization (project_id + folder/date patterns)');

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('5.0.0', 'Added mobile device tracking: devices, import sessions, and file provenance');

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('7.0.0', 'Semantic embeddings separation: semantic_embeddings, semantic_index_meta');

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('8.0.0', 'Asset-centric duplicates model + stacks: media_asset, media_instance, media_stack');

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('9.1.0', 'Project canonical semantic model: projects.semantic_model for embedding consistency');

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('9.2.0', 'Add GPS columns to photo_metadata for location-based browsing');

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('9.3.0', 'Add image_content_hash for pixel-based embedding staleness detection');

-- ============================================================================
-- FACE RECOGNITION TABLES
-- ============================================================================

-- Reference images for face recognition
CREATE TABLE IF NOT EXISTS reference_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL
);

-- Match audit logging for face recognition
CREATE TABLE IF NOT EXISTS match_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    matched_label TEXT,
    confidence REAL,
    match_mode TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Label thresholds for face recognition
CREATE TABLE IF NOT EXISTS reference_labels (
    label TEXT PRIMARY KEY,
    folder_path TEXT NOT NULL,
    threshold REAL DEFAULT 0.3
);

-- ============================================================================
-- PROJECT ORGANIZATION TABLES
-- ============================================================================

-- Projects (top-level organizational unit)
-- v9.1.0: Added semantic_model for canonical embedding model per project
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    folder TEXT NOT NULL,
    mode TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    semantic_model TEXT DEFAULT 'clip-vit-b32'  -- Canonical embedding model for this project
);

-- Branches (sub-groups within projects)
CREATE TABLE IF NOT EXISTS branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    branch_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, branch_key)
);

-- Project images (many-to-many: projects/branches to images)
CREATE TABLE IF NOT EXISTS project_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    branch_key TEXT,
    image_path TEXT NOT NULL,
    label TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, branch_key, image_path)
);

-- Face crops (face thumbnails for each branch)
-- Phase 5: Added embedding column for face recognition clustering
CREATE TABLE IF NOT EXISTS face_crops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    branch_key TEXT,
    image_path TEXT NOT NULL,
    crop_path TEXT NOT NULL,
    embedding BLOB,
    bbox_x INTEGER,
    bbox_y INTEGER,
    bbox_w INTEGER,
    bbox_h INTEGER,
    confidence REAL,
    is_representative INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, image_path, bbox_x, bbox_y, bbox_w, bbox_h)
);

-- Face branch representatives (cluster centroids and representative images)
CREATE TABLE IF NOT EXISTS face_branch_reps (
    project_id INTEGER NOT NULL,
    branch_key TEXT NOT NULL,
    label TEXT,
    count INTEGER DEFAULT 0,
    centroid BLOB,
    rep_path TEXT,
    rep_thumb_png BLOB,
    PRIMARY KEY (project_id, branch_key),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Face merge history (for undo functionality)
CREATE TABLE IF NOT EXISTS face_merge_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    target_branch TEXT NOT NULL,
    source_branches TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Export history (tracks photo export operations)
CREATE TABLE IF NOT EXISTS export_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    branch_key TEXT,
    photo_count INTEGER,
    source_paths TEXT,
    dest_paths TEXT,
    dest_folder TEXT,
    timestamp TEXT
);

-- ============================================================================
-- PHOTO LIBRARY TABLES (Core photo management)
-- ============================================================================

-- Photo folders (hierarchical folder structure with project ownership)
CREATE TABLE IF NOT EXISTS photo_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    parent_id INTEGER NULL,
    project_id INTEGER NOT NULL,
    photo_count INTEGER DEFAULT 0,
    FOREIGN KEY(parent_id) REFERENCES photo_folders(id),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(path, project_id)
);

-- Photo metadata (main photo index with all metadata and project ownership)
CREATE TABLE IF NOT EXISTS photo_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    folder_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    size_kb REAL,
    modified TEXT,
    width INTEGER,
    height INTEGER,
    embedding BLOB,
    date_taken TEXT,
    tags TEXT,
    updated_at TEXT,
    metadata_status TEXT DEFAULT 'pending',
    metadata_fail_count INTEGER DEFAULT 0,
    created_ts INTEGER,
    created_date TEXT,
    created_year INTEGER,
    file_hash TEXT,
    -- GPS coordinates for location-based browsing (v9.2.0)
    gps_latitude REAL,
    gps_longitude REAL,
    location_name TEXT,  -- Reverse-geocoded location name
    -- Perceptual hash for pixel-based embedding staleness detection (v9.3.0)
    -- Uses dHash (difference hash) which is resilient to metadata-only changes
    image_content_hash TEXT,
    FOREIGN KEY(folder_id) REFERENCES photo_folders(id),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(path, project_id)
);

-- ============================================================================
-- TAGGING TABLES (Normalized tag structure)
-- ============================================================================

-- Tags (tag definitions)
-- Schema v3.1.0: Added project_id for proper tag isolation between projects
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE,
    project_id INTEGER NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(name, project_id)
);

-- Photo tags (many-to-many: photos to tags)
CREATE TABLE IF NOT EXISTS photo_tags (
    photo_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (photo_id, tag_id),
    FOREIGN KEY (photo_id) REFERENCES photo_metadata(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- ============================================================================
-- VIDEO TABLES (Schema v3.2.0: Complete video infrastructure)
-- ============================================================================

-- Video metadata (mirrors photo_metadata structure for videos)
CREATE TABLE IF NOT EXISTS video_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    folder_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,

    -- File metadata
    size_kb REAL,
    modified TEXT,

    -- Video-specific metadata
    duration_seconds REAL,
    width INTEGER,
    height INTEGER,
    fps REAL,
    codec TEXT,
    bitrate INTEGER,

    -- Timestamps (for date-based browsing)
    date_taken TEXT,
    created_ts INTEGER,
    created_date TEXT,
    created_year INTEGER,
    updated_at TEXT,

    -- Processing status
    metadata_status TEXT DEFAULT 'pending',
    metadata_fail_count INTEGER DEFAULT 0,
    thumbnail_status TEXT DEFAULT 'pending',

    FOREIGN KEY (folder_id) REFERENCES photo_folders(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(path, project_id)
);

-- Project videos (mirrors project_images for videos)
CREATE TABLE IF NOT EXISTS project_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    branch_key TEXT,
    video_path TEXT NOT NULL,
    label TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, branch_key, video_path)
);

-- Video tags (many-to-many: videos to tags)
CREATE TABLE IF NOT EXISTS video_tags (
    video_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (video_id, tag_id),
    FOREIGN KEY (video_id) REFERENCES video_metadata(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- ============================================================================
-- MOBILE DEVICE TRACKING TABLES (Schema v5.0.0)
-- ============================================================================

-- Mobile devices registry (tracks all connected devices)
CREATE TABLE IF NOT EXISTS mobile_devices (
    device_id TEXT PRIMARY KEY,           -- Unique device identifier (MTP serial, iOS UUID, Volume GUID)
    device_name TEXT NOT NULL,            -- User-friendly name ("Samsung Galaxy S22", "John's iPhone")
    device_type TEXT NOT NULL,            -- Device type: "android", "ios", "camera", "usb", "sd_card"
    serial_number TEXT,                   -- Physical serial number (if available)
    volume_guid TEXT,                     -- Volume GUID for removable storage (Windows)
    mount_point TEXT,                     -- Last known mount path ("/media/user/phone")
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- When device first connected
    last_seen TIMESTAMP,                  -- Last time device was detected
    last_import_session INTEGER,          -- ID of most recent import session
    total_imports INTEGER DEFAULT 0,      -- Total number of import sessions
    total_photos_imported INTEGER DEFAULT 0,  -- Cumulative photo count
    total_videos_imported INTEGER DEFAULT 0,  -- Cumulative video count
    notes TEXT,                           -- User notes about device
    -- Phase 4: Auto-import preferences
    auto_import BOOLEAN DEFAULT 0,        -- Enable auto-import for this device
    auto_import_folder TEXT DEFAULT NULL, -- Which folder to auto-import from (e.g., "Camera")
    last_auto_import TIMESTAMP DEFAULT NULL,  -- Last time auto-import ran
    auto_import_enabled_date TIMESTAMP DEFAULT NULL  -- When auto-import was enabled
);

-- Import sessions (tracks each import operation)
CREATE TABLE IF NOT EXISTS import_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,              -- Which device was imported from
    project_id INTEGER NOT NULL,          -- Target project
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    import_type TEXT DEFAULT 'manual',    -- "manual", "auto", "incremental"
    photos_imported INTEGER DEFAULT 0,
    videos_imported INTEGER DEFAULT 0,
    duplicates_skipped INTEGER DEFAULT 0,
    bytes_imported INTEGER DEFAULT 0,
    duration_seconds INTEGER,
    status TEXT DEFAULT 'completed',      -- "in_progress", "completed", "partial", "failed"
    error_message TEXT,
    FOREIGN KEY (device_id) REFERENCES mobile_devices(device_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Device files (tracks all files ever seen on devices)
CREATE TABLE IF NOT EXISTS device_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,              -- Which device this file is on
    device_path TEXT NOT NULL,            -- Original path on device (e.g., "/DCIM/Camera/IMG_001.jpg")
    device_folder TEXT,                   -- Folder name on device ("Camera", "Screenshots", "WhatsApp")
    file_hash TEXT NOT NULL,              -- SHA256 hash for duplicate detection
    file_size INTEGER,                    -- File size in bytes
    file_mtime TIMESTAMP,                 -- File modification time on device
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- When first detected
    last_seen TIMESTAMP,                  -- Last time seen on device
    import_status TEXT DEFAULT 'new',     -- "new", "imported", "skipped", "deleted"
    local_photo_id INTEGER,               -- Link to photo_metadata.id (if imported)
    local_video_id INTEGER,               -- Link to video_metadata.id (if imported)
    import_session_id INTEGER,            -- Which session imported this file
    FOREIGN KEY (device_id) REFERENCES mobile_devices(device_id) ON DELETE CASCADE,
    FOREIGN KEY (import_session_id) REFERENCES import_sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (local_photo_id) REFERENCES photo_metadata(id) ON DELETE SET NULL,
    FOREIGN KEY (local_video_id) REFERENCES video_metadata(id) ON DELETE SET NULL,
    UNIQUE(device_id, device_path)
);

-- ============================================================================
-- SEMANTIC EMBEDDINGS (v7.0.0)
-- ============================================================================
CREATE TABLE IF NOT EXISTS semantic_embeddings (
    photo_id INTEGER PRIMARY KEY,
    model TEXT NOT NULL,               -- 'clip-vit-b32', 'clip-vit-l14', 'siglip-base'
    embedding BLOB NOT NULL,           -- float32 bytes (normalized)
    dim INTEGER NOT NULL,              -- 512, 768, etc.
    norm REAL NOT NULL,                -- Precomputed L2 norm (should be 1.0 for normalized)

    -- Freshness tracking
    source_photo_hash TEXT,            -- SHA256 of source image
    source_photo_mtime TEXT,           -- mtime at computation time
    artifact_version TEXT DEFAULT '1.0',  -- Recompute trigger

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(photo_id) REFERENCES photo_metadata(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS semantic_index_meta (
    model TEXT PRIMARY KEY,
    dim INTEGER NOT NULL,
    total_vectors INTEGER NOT NULL,
    last_rebuild TIMESTAMP,
    notes TEXT
);

-- ============================================================================
-- MEDIA ASSET MODEL (v8.0.0)
-- ============================================================================
CREATE TABLE IF NOT EXISTS media_asset (
    asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,

    -- Cryptographic identity (SHA256 or equivalent)
    content_hash TEXT NOT NULL,

    -- Optional perceptual hash for near-duplicate detection
    perceptual_hash TEXT,

    -- Chosen representative photo for previews and UI
    representative_photo_id INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ensure one asset per content_hash per project
    UNIQUE(project_id, content_hash),

    FOREIGN KEY (representative_photo_id) REFERENCES photo_metadata(id) ON DELETE SET NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS media_instance (
    instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,

    -- Link to asset (many instances can share one asset)
    asset_id INTEGER NOT NULL,

    -- Link to existing photo_metadata row (one-to-one mapping)
    photo_id INTEGER NOT NULL,

    -- Traceability: where did this file come from
    source_device_id TEXT,
    source_path TEXT,
    import_session_id TEXT,

    -- File metadata (denormalized for performance)
    file_size INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ensure one instance per photo per project
    UNIQUE(project_id, photo_id),

    FOREIGN KEY (asset_id) REFERENCES media_asset(asset_id) ON DELETE CASCADE,
    FOREIGN KEY (photo_id) REFERENCES photo_metadata(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS media_stack (
    stack_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,

    -- Stack type: duplicate, near_duplicate, similar, burst
    stack_type TEXT NOT NULL CHECK(stack_type IN ('duplicate', 'near_duplicate', 'similar', 'burst')),

    -- Representative photo for preview (shown in timeline)
    representative_photo_id INTEGER,

    -- Rule version allows algorithm evolution and regeneration
    rule_version TEXT NOT NULL DEFAULT '1',

    -- Optional: track who/what created this stack (system, user, ml)
    created_by TEXT DEFAULT 'system',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (representative_photo_id) REFERENCES photo_metadata(id) ON DELETE SET NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS media_stack_member (
    stack_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,

    photo_id INTEGER NOT NULL,

    -- Similarity score (meaning depends on stack_type)
    similarity_score REAL,

    -- Rank for stable ordering (lower = better/more representative)
    rank INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (stack_id, photo_id),

    FOREIGN KEY (stack_id) REFERENCES media_stack(stack_id) ON DELETE CASCADE,
    FOREIGN KEY (photo_id) REFERENCES photo_metadata(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS media_stack_meta (
    stack_id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,

    -- JSON string with parameters used to build this stack
    params_json TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (stack_id) REFERENCES media_stack(stack_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Face crops indexes
CREATE INDEX IF NOT EXISTS idx_face_crops_proj ON face_crops(project_id);
CREATE INDEX IF NOT EXISTS idx_face_crops_proj_branch ON face_crops(project_id, branch_key);
CREATE INDEX IF NOT EXISTS idx_face_crops_proj_rep ON face_crops(project_id, is_representative);

-- Face branch reps indexes
CREATE INDEX IF NOT EXISTS idx_fbreps_proj ON face_branch_reps(project_id);
CREATE INDEX IF NOT EXISTS idx_fbreps_proj_branch ON face_branch_reps(project_id, branch_key);

-- Branches indexes
CREATE INDEX IF NOT EXISTS idx_branches_project ON branches(project_id);
CREATE INDEX IF NOT EXISTS idx_branches_key ON branches(project_id, branch_key);

-- Project images indexes
CREATE INDEX IF NOT EXISTS idx_projimgs_project ON project_images(project_id);
CREATE INDEX IF NOT EXISTS idx_projimgs_branch ON project_images(project_id, branch_key);
CREATE INDEX IF NOT EXISTS idx_projimgs_path ON project_images(image_path);

-- Photo folders indexes
CREATE INDEX IF NOT EXISTS idx_photo_folders_project ON photo_folders(project_id);
CREATE INDEX IF NOT EXISTS idx_photo_folders_parent ON photo_folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_photo_folders_path ON photo_folders(path);

-- Photo metadata indexes (project_id for fast filtering)
CREATE INDEX IF NOT EXISTS idx_photo_metadata_project ON photo_metadata(project_id);

-- Photo metadata indexes (date and metadata)
CREATE INDEX IF NOT EXISTS idx_meta_date ON photo_metadata(date_taken);
CREATE INDEX IF NOT EXISTS idx_meta_modified ON photo_metadata(modified);
CREATE INDEX IF NOT EXISTS idx_meta_updated ON photo_metadata(updated_at);
CREATE INDEX IF NOT EXISTS idx_meta_folder ON photo_metadata(folder_id);
CREATE INDEX IF NOT EXISTS idx_meta_status ON photo_metadata(metadata_status);

-- Photo metadata indexes (created_* columns for date-based browsing)
CREATE INDEX IF NOT EXISTS idx_photo_created_year ON photo_metadata(created_year);
CREATE INDEX IF NOT EXISTS idx_photo_created_date ON photo_metadata(created_date);
CREATE INDEX IF NOT EXISTS idx_photo_created_ts ON photo_metadata(created_ts);

-- Photo metadata indexes (file_hash for duplicate detection during imports)
CREATE INDEX IF NOT EXISTS idx_photo_metadata_hash ON photo_metadata(file_hash);

-- Photo metadata indexes (GPS for location-based browsing v9.2.0)
CREATE INDEX IF NOT EXISTS idx_photo_metadata_gps ON photo_metadata(project_id, gps_latitude, gps_longitude)
    WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL;

-- Tag indexes (v3.1.0: Added project_id indexes)
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_tags_project ON tags(project_id);
CREATE INDEX IF NOT EXISTS idx_tags_project_name ON tags(project_id, name);
CREATE INDEX IF NOT EXISTS idx_photo_tags_photo ON photo_tags(photo_id);
CREATE INDEX IF NOT EXISTS idx_photo_tags_tag ON photo_tags(tag_id);

-- Video indexes (v3.2.0: Video infrastructure)
CREATE INDEX IF NOT EXISTS idx_video_metadata_project ON video_metadata(project_id);
CREATE INDEX IF NOT EXISTS idx_video_metadata_folder ON video_metadata(folder_id);
CREATE INDEX IF NOT EXISTS idx_video_metadata_date ON video_metadata(date_taken);
CREATE INDEX IF NOT EXISTS idx_video_metadata_year ON video_metadata(created_year);
CREATE INDEX IF NOT EXISTS idx_video_metadata_status ON video_metadata(metadata_status);
CREATE INDEX IF NOT EXISTS idx_video_thumbnail_status ON video_metadata(thumbnail_status);

CREATE INDEX IF NOT EXISTS idx_project_videos_project ON project_videos(project_id);
CREATE INDEX IF NOT EXISTS idx_project_videos_branch ON project_videos(project_id, branch_key);
CREATE INDEX IF NOT EXISTS idx_project_videos_path ON project_videos(video_path);

CREATE INDEX IF NOT EXISTS idx_video_tags_video ON video_tags(video_id);
CREATE INDEX IF NOT EXISTS idx_video_tags_tag ON video_tags(tag_id);

-- Compound indexes for performance (v3.3.0: Query optimization)
-- These indexes optimize common filtering patterns by project + another column
CREATE INDEX IF NOT EXISTS idx_photo_metadata_project_folder ON photo_metadata(project_id, folder_id);
CREATE INDEX IF NOT EXISTS idx_photo_metadata_project_date ON photo_metadata(project_id, created_year, created_date);
CREATE INDEX IF NOT EXISTS idx_video_metadata_project_folder ON video_metadata(project_id, folder_id);
CREATE INDEX IF NOT EXISTS idx_video_metadata_project_date ON video_metadata(project_id, created_year, created_date);
CREATE INDEX IF NOT EXISTS idx_video_metadata_project_thumb_status ON video_metadata(project_id, thumbnail_status);
CREATE INDEX IF NOT EXISTS idx_video_metadata_project_meta_status ON video_metadata(project_id, metadata_status);
CREATE INDEX IF NOT EXISTS idx_project_images_project_branch ON project_images(project_id, branch_key, image_path);
CREATE INDEX IF NOT EXISTS idx_photo_folders_project_parent ON photo_folders(project_id, parent_id);

-- Mobile device tracking indexes (v5.0.0: Device import tracking)
CREATE INDEX IF NOT EXISTS idx_mobile_devices_type ON mobile_devices(device_type);
CREATE INDEX IF NOT EXISTS idx_mobile_devices_last_seen ON mobile_devices(last_seen);
CREATE INDEX IF NOT EXISTS idx_mobile_devices_auto_import ON mobile_devices(auto_import) WHERE auto_import = 1;

CREATE INDEX IF NOT EXISTS idx_import_sessions_device ON import_sessions(device_id);
CREATE INDEX IF NOT EXISTS idx_import_sessions_project ON import_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_import_sessions_date ON import_sessions(import_date);
CREATE INDEX IF NOT EXISTS idx_import_sessions_status ON import_sessions(status);

CREATE INDEX IF NOT EXISTS idx_device_files_device ON device_files(device_id);
CREATE INDEX IF NOT EXISTS idx_device_files_hash ON device_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_device_files_status ON device_files(device_id, import_status);
CREATE INDEX IF NOT EXISTS idx_device_files_photo ON device_files(local_photo_id);
CREATE INDEX IF NOT EXISTS idx_device_files_video ON device_files(local_video_id);
CREATE INDEX IF NOT EXISTS idx_device_files_session ON device_files(import_session_id);
CREATE INDEX IF NOT EXISTS idx_device_files_last_seen ON device_files(device_id, last_seen);

-- Semantic embeddings indexes (v7.0.0)
CREATE INDEX IF NOT EXISTS idx_semantic_model ON semantic_embeddings(model);
CREATE INDEX IF NOT EXISTS idx_semantic_hash ON semantic_embeddings(source_photo_hash);
CREATE INDEX IF NOT EXISTS idx_semantic_computed ON semantic_embeddings(computed_at);

-- Media asset indexes (v8.0.0)
CREATE INDEX IF NOT EXISTS idx_media_asset_project_hash ON media_asset(project_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_media_asset_representative ON media_asset(project_id, representative_photo_id);
CREATE INDEX IF NOT EXISTS idx_media_asset_project_id ON media_asset(project_id);

CREATE INDEX IF NOT EXISTS idx_media_instance_project_asset ON media_instance(project_id, asset_id);
CREATE INDEX IF NOT EXISTS idx_media_instance_project_photo ON media_instance(project_id, photo_id);
CREATE INDEX IF NOT EXISTS idx_media_instance_project_device ON media_instance(project_id, source_device_id);
CREATE INDEX IF NOT EXISTS idx_media_instance_asset_id ON media_instance(asset_id);

CREATE INDEX IF NOT EXISTS idx_media_stack_project_type ON media_stack(project_id, stack_type);
CREATE INDEX IF NOT EXISTS idx_media_stack_project_representative ON media_stack(project_id, representative_photo_id);
CREATE INDEX IF NOT EXISTS idx_media_stack_project_id ON media_stack(project_id);
CREATE INDEX IF NOT EXISTS idx_media_stack_type_version ON media_stack(stack_type, rule_version);

CREATE INDEX IF NOT EXISTS idx_media_stack_member_project_stack ON media_stack_member(project_id, stack_id);
CREATE INDEX IF NOT EXISTS idx_media_stack_member_project_photo ON media_stack_member(project_id, photo_id);
CREATE INDEX IF NOT EXISTS idx_media_stack_member_stack_id ON media_stack_member(stack_id);
CREATE INDEX IF NOT EXISTS idx_media_stack_member_photo_id ON media_stack_member(photo_id);

CREATE INDEX IF NOT EXISTS idx_media_stack_meta_project_id ON media_stack_meta(project_id);
"""


def get_schema_sql() -> str:
    """
    Return the complete schema SQL for database initialization.

    Returns:
        str: SQL script containing all CREATE TABLE and CREATE INDEX statements
    """
    return SCHEMA_SQL


def get_schema_version() -> str:
    """
    Return the current schema version.

    Returns:
        str: Schema version string (e.g., "2.0.0")
    """
    return SCHEMA_VERSION


def get_expected_tables() -> list[str]:
    """
    Return list of expected table names in the schema.

    Returns:
        list[str]: List of table names that should exist
    """
    return [
        "schema_version",
        "reference_entries",
        "match_audit",
        "reference_labels",
        "projects",
        "branches",
        "project_images",
        "face_crops",
        "face_branch_reps",
        "export_history",
        "photo_folders",
        "photo_metadata",
        "tags",
        "photo_tags",
        # Video tables (v3.2.0)
        "video_metadata",
        "project_videos",
        "video_tags",
        # Mobile device tracking tables (v5.0.0)
        "mobile_devices",
        "import_sessions",
        "device_files",
        # Semantic embeddings tables (v7.0.0)
        "semantic_embeddings",
        "semantic_index_meta",
        # Media asset model tables (v8.0.0)
        "media_asset",
        "media_instance",
        "media_stack",
        "media_stack_member",
        "media_stack_meta",
        # Face merge history (should have been included earlier)
        "face_merge_history",
    ]


def get_expected_indexes() -> list[str]:
    """
    Return list of expected index names in the schema.

    Returns:
        list[str]: List of index names that should exist
    """
    return [
        "idx_face_crops_proj",
        "idx_face_crops_proj_branch",
        "idx_face_crops_proj_rep",
        "idx_fbreps_proj",
        "idx_fbreps_proj_branch",
        "idx_branches_project",
        "idx_branches_key",
        "idx_projimgs_project",
        "idx_projimgs_branch",
        "idx_projimgs_path",
        "idx_photo_folders_project",
        "idx_photo_folders_parent",
        "idx_photo_folders_path",
        "idx_photo_metadata_project",
        "idx_meta_date",
        "idx_meta_modified",
        "idx_meta_updated",
        "idx_meta_folder",
        "idx_meta_status",
        "idx_photo_created_year",
        "idx_photo_created_date",
        "idx_photo_created_ts",
        "idx_tags_name",
        "idx_tags_project",
        "idx_tags_project_name",
        "idx_photo_tags_photo",
        "idx_photo_tags_tag",
        # Video indexes (v3.2.0)
        "idx_video_metadata_project",
        "idx_video_metadata_folder",
        "idx_video_metadata_date",
        "idx_video_metadata_year",
        "idx_video_metadata_status",
        "idx_project_videos_project",
        "idx_project_videos_branch",
        "idx_project_videos_path",
        "idx_video_tags_video",
        "idx_video_tags_tag",
        # Compound indexes (v3.3.0)
        "idx_photo_metadata_project_folder",
        "idx_photo_metadata_project_date",
        "idx_photo_metadata_gps",
        "idx_video_metadata_project_folder",
        "idx_video_metadata_project_date",
        "idx_project_images_project_branch",
        "idx_photo_folders_project_parent",
        # Mobile device tracking indexes (v5.0.0)
        "idx_mobile_devices_type",
        "idx_mobile_devices_last_seen",
        "idx_mobile_devices_auto_import",
        "idx_import_sessions_device",
        "idx_import_sessions_project",
        "idx_import_sessions_date",
        "idx_import_sessions_status",
        "idx_device_files_device",
        "idx_device_files_hash",
        "idx_device_files_status",
        "idx_device_files_photo",
        "idx_device_files_video",
        "idx_device_files_session",
        "idx_device_files_last_seen",
        # Semantic embeddings indexes (v7.0.0)
        "idx_semantic_model",
        "idx_semantic_hash",
        "idx_semantic_computed",
        # Media asset indexes (v8.0.0)
        "idx_media_asset_project_hash",
        "idx_media_asset_representative",
        "idx_media_asset_project_id",
        "idx_media_instance_project_asset",
        "idx_media_instance_project_photo",
        "idx_media_instance_project_device",
        "idx_media_instance_asset_id",
        "idx_media_stack_project_type",
        "idx_media_stack_project_representative",
        "idx_media_stack_project_id",
        "idx_media_stack_type_version",
        "idx_media_stack_member_project_stack",
        "idx_media_stack_member_project_photo",
        "idx_media_stack_member_stack_id",
        "idx_media_stack_member_photo_id",
        "idx_media_stack_meta_project_id",
    ]


# Schema migration support (for future use)
MIGRATIONS = {
    "1.0.0": {
        "description": "Legacy schema from reference_db.py",
        "sql": "-- Legacy schema, no migration needed"
    },
    "2.0.0": {
        "description": "Repository layer schema with all tables and indexes",
        "sql": "-- Superseded by 3.0.0"
    },
    "3.0.0": {
        "description": "Added project_id to photo_folders and photo_metadata for clean project isolation",
        "sql": SCHEMA_SQL
    },
    "9.2.0": {
        "description": "Add GPS columns to photo_metadata for location-based browsing",
        "sql": """
-- v9.2.0: Add GPS columns if they don't exist
-- SQLite requires checking column existence before ALTER TABLE
-- This is idempotent - safe to run multiple times

-- Add gps_latitude column if it doesn't exist
-- (SQLite doesn't support ADD COLUMN IF NOT EXISTS, so we use a try-ignore pattern)

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('9.2.0', 'Add GPS columns to photo_metadata for location-based browsing');

-- Create partial index for GPS queries (fast location lookups)
CREATE INDEX IF NOT EXISTS idx_photo_metadata_gps ON photo_metadata(project_id, gps_latitude, gps_longitude)
    WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL;
"""
    },
    "9.3.0": {
        "description": "Add image_content_hash for pixel-based embedding staleness detection",
        "sql": """
-- v9.3.0: Add image_content_hash column for pixel-based staleness detection
-- This uses perceptual hash (dHash) which is resilient to metadata-only changes like GPS edits
-- Replaces mtime-based staleness detection that caused unnecessary re-embedding on EXIF edits

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('9.3.0', 'Add image_content_hash for pixel-based embedding staleness detection');
"""
    }
}

# GPS column migration SQL (run separately since ALTER TABLE can't be conditional)
GPS_MIGRATION_SQL = """
ALTER TABLE photo_metadata ADD COLUMN gps_latitude REAL;
ALTER TABLE photo_metadata ADD COLUMN gps_longitude REAL;
"""


def get_migration(from_version: str, to_version: str) -> str | None:
    """
    Get migration SQL for upgrading from one version to another.

    Args:
        from_version: Starting schema version
        to_version: Target schema version

    Returns:
        str: Migration SQL, or None if no migration exists
    """
    # For now, we only support creating new databases with 2.0.0
    # Future: Add incremental migration support
    if to_version in MIGRATIONS:
        return MIGRATIONS[to_version]["sql"]
    return None


def ensure_gps_columns(conn) -> bool:
    """
    Ensure GPS columns exist in photo_metadata table.

    This is called at app startup to migrate existing databases.
    Safe to call multiple times (idempotent).

    Args:
        conn: SQLite connection object

    Returns:
        bool: True if columns were added, False if already existed
    """
    import logging
    logger = logging.getLogger(__name__)

    cur = conn.cursor()

    # Check existing columns
    existing_cols = {r[1] for r in cur.execute("PRAGMA table_info(photo_metadata)")}

    columns_added = False

    if 'gps_latitude' not in existing_cols:
        logger.info("[Schema] Adding gps_latitude column to photo_metadata")
        cur.execute("ALTER TABLE photo_metadata ADD COLUMN gps_latitude REAL")
        columns_added = True

    if 'gps_longitude' not in existing_cols:
        logger.info("[Schema] Adding gps_longitude column to photo_metadata")
        cur.execute("ALTER TABLE photo_metadata ADD COLUMN gps_longitude REAL")
        columns_added = True

    # Create GPS index if needed
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_photo_metadata_gps
        ON photo_metadata(project_id, gps_latitude, gps_longitude)
        WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL
    """)

    # Update schema version
    cur.execute("""
        INSERT OR IGNORE INTO schema_version (version, description)
        VALUES ('9.2.0', 'Add GPS columns to photo_metadata for location-based browsing')
    """)

    conn.commit()

    if columns_added:
        logger.info("[Schema] GPS columns migration complete")

    return columns_added
