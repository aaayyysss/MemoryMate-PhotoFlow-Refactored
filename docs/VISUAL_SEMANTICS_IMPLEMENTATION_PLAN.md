# Visual Semantics Implementation Plan v6.0.0

**Date**: 2025-12-29
**Status**: APPROVED (Production-Ready)
**Migration**: v5.0.0 → v6.0.0

---

## Executive Summary

This document defines the **production-grade implementation plan** for adding ML-powered visual understanding to MemoryMate/PhotoFlow.

**Scope**:
- ✅ Image embeddings (CLIP/SigLIP) for semantic search
- ✅ Captions (BLIP2) for natural language descriptions
- ✅ ML tag suggestions with user review workflow
- ✅ Object detections (Grounding DINO) for evidence-based search
- ✅ Event clustering (weddings, trips, "days")
- ✅ Job orchestration (crash-safe, persistent background jobs)

**Constraints**:
- **Offline-first**: All ML runs locally on user's PC (CPU/GPU)
- **Privacy-preserving**: No data leaves the machine (optional GPU server in Phase 2+)
- **Backward-compatible**: Existing tags, embeddings (face recognition) untouched
- **Idempotent migrations**: Safe to run multiple times

---

## Table of Contents

1. [Critical Design Decisions](#critical-design-decisions)
2. [Schema Design](#schema-design)
3. [Tag Reconciliation Rules (Authority Policy)](#tag-reconciliation-rules-authority-policy)
4. [Job Orchestration Architecture](#job-orchestration-architecture)
5. [Service Layer Design](#service-layer-design)
6. [Worker Pattern](#worker-pattern)
7. [Embedding Freshness & Recomputation](#embedding-freshness--recomputation)
8. [Migration Strategy](#migration-strategy)
9. [WBS Roadmap (Updated)](#wbs-roadmap-updated)
10. [Testing & Verification](#testing--verification)

---

## Critical Design Decisions

### 1. Embedding Storage: Separate Table vs Column

**Decision**: Use separate `photo_embedding` table (NOT extend `photo_metadata.embedding`)

**Reasoning**:
- `photo_metadata.embedding` already used for **face recognition** (InsightFace 512-D)
- Visual semantic embeddings (CLIP/SigLIP) are different:
  - Different dimensionality (512D, 768D, etc.)
  - Different models
  - Different update cadence
- Future-proof for multiple embedding types: `visual_semantic`, `face`, `object`

**Schema**:
```sql
CREATE TABLE photo_embedding (
  photo_id INTEGER,
  model_id INTEGER,
  embedding_type TEXT,  -- 'visual_semantic', 'face', 'object'
  embedding BLOB,
  PRIMARY KEY(photo_id, model_id, embedding_type)
);
```

---

### 2. Tag Authority: photo_tags vs photo_tag_decision

**Decision**: **Option A** - `photo_tags` remains the authoritative source of truth

**Reasoning**:
- Backward compatible with existing manual tagging
- Clear separation of concerns:
  - `photo_tag_suggestion`: ML outputs (derivations)
  - `photo_tag_decision`: User actions (decisions)
  - `photo_tags`: Confirmed tags (facts)

**Reconciliation Rules** (see detailed section below):
1. User confirms suggestion → Write to **both** `photo_tags` AND `photo_tag_decision(confirm)`
2. User rejects suggestion → Write to `photo_tag_decision(reject)` with suppression timestamp
3. User manually adds tag → Write to `photo_tags` only (no decision entry)
4. Query for "all tags" → Read from `photo_tags` (authoritative)

---

### 3. Job Crash Recovery: Lease + Heartbeat

**Decision**: Add lease/heartbeat mechanism to `ml_job` table

**Reasoning**:
- Without this, app crashes leave jobs in "running" state forever
- Users see zombie jobs that never complete
- Restart doesn't recover work

**Implementation**:
```sql
ALTER TABLE ml_job ADD COLUMN worker_id TEXT;
ALTER TABLE ml_job ADD COLUMN lease_expires_at TEXT;
ALTER TABLE ml_job ADD COLUMN last_heartbeat_at TEXT;
```

**Startup Recovery**:
```python
def recover_zombie_jobs(conn):
    """On app startup: mark expired jobs as 'failed'."""
    current_ts = datetime.now().isoformat()
    conn.execute("""
        UPDATE ml_job
        SET status = 'failed',
            error = 'Crash recovery: job running when app crashed'
        WHERE status = 'running'
          AND (lease_expires_at IS NULL OR lease_expires_at < ?)
    """, (current_ts,))
```

---

### 4. Embedding Freshness: Detect Stale Artifacts

**Decision**: Add `source_photo_hash` + `artifact_version` to all artifact tables

**Reasoning**:
- Photo edited on disk (rotation, crop, etc.) → embeddings become stale
- Model updated (v1.0 → v1.1) → need recomputation trigger
- Without tracking: user sees wrong results

**Implementation**:
```sql
CREATE TABLE photo_embedding (
  -- ... existing columns
  source_photo_hash TEXT,      -- SHA256 at computation time
  source_photo_mtime TEXT,     -- mtime at computation time
  artifact_version TEXT DEFAULT '1.0',
  computed_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**Freshness Check**:
```python
def is_embedding_fresh(photo_path, embedding_row):
    current_hash = compute_sha256(photo_path)
    return current_hash == embedding_row['source_photo_hash']
```

---

### 5. Suppression Mechanism: Stop Annoying Users

**Decision**: Add `suppress_until_ts` to `photo_tag_decision`

**Reasoning**:
- User rejects "wedding" tag → it keeps reappearing on every scan
- Need temporal suppression: "don't suggest this tag for 30 days"

**Implementation**:
```sql
CREATE TABLE photo_tag_decision (
  -- ... existing columns
  suppress_until_ts TEXT,  -- ISO timestamp or NULL
);
```

**Suggestion Filtering**:
```python
def get_active_suggestions(photo_id):
    """Get suggestions not currently suppressed."""
    current_ts = datetime.now().isoformat()
    return db.execute("""
        SELECT * FROM photo_tag_suggestion s
        WHERE s.photo_id = ?
          AND NOT EXISTS (
            SELECT 1 FROM photo_tag_decision d
            WHERE d.photo_id = s.photo_id
              AND d.tag_id = s.tag_id
              AND d.decision = 'reject'
              AND (d.suppress_until_ts IS NULL OR d.suppress_until_ts > ?)
          )
    """, (photo_id, current_ts))
```

---

## Tag Reconciliation Rules (Authority Policy)

### Principle: Facts vs Derivations vs Decisions

| Table | Role | Authority Level |
|-------|------|----------------|
| `photo_tags` | **Facts** - Confirmed tags (manual + accepted ML) | **Authoritative** |
| `photo_tag_suggestion` | **Derivations** - ML outputs | Non-authoritative |
| `photo_tag_decision` | **Decisions** - User actions (confirm/reject) | Audit trail |

---

### Reconciliation Rules

#### Rule 1: User Confirms ML Suggestion

```python
def confirm_suggestion(photo_id, tag_id, source_model_id, source_score):
    """User clicks ✓ on ML suggestion."""
    with db.transaction():
        # 1. Add to authoritative tags (if not already there)
        db.execute("""
            INSERT OR IGNORE INTO photo_tags (photo_id, tag_id)
            VALUES (?, ?)
        """, (photo_id, tag_id))

        # 2. Record decision (audit trail)
        db.execute("""
            INSERT INTO photo_tag_decision
              (photo_id, tag_id, decision, source_model_id, source_score)
            VALUES (?, ?, 'confirm', ?, ?)
        """, (photo_id, tag_id, source_model_id, source_score))

        # 3. Remove suggestion (optional, or keep for history)
        db.execute("""
            DELETE FROM photo_tag_suggestion
            WHERE photo_id = ? AND tag_id = ? AND model_id = ?
        """, (photo_id, tag_id, source_model_id))
```

**Invariant**: After confirm, `photo_tags` MUST contain the tag.

---

#### Rule 2: User Rejects ML Suggestion

```python
def reject_suggestion(photo_id, tag_id, source_model_id, suppress_days=30):
    """User clicks ✗ on ML suggestion."""
    suppress_until = (datetime.now() + timedelta(days=suppress_days)).isoformat()

    with db.transaction():
        # 1. Record rejection with suppression
        db.execute("""
            INSERT INTO photo_tag_decision
              (photo_id, tag_id, decision, source_model_id, suppress_until_ts)
            VALUES (?, ?, 'reject', ?, ?)
        """, (photo_id, tag_id, source_model_id, suppress_until))

        # 2. Remove from suggestions
        db.execute("""
            DELETE FROM photo_tag_suggestion
            WHERE photo_id = ? AND tag_id = ? AND model_id = ?
        """, (photo_id, tag_id, source_model_id))

        # 3. DO NOT touch photo_tags (user might have manually added it)
```

**Invariant**: Rejected suggestions don't reappear until `suppress_until_ts` expires.

---

#### Rule 3: User Manually Adds Tag

```python
def add_manual_tag(photo_id, tag_name, project_id):
    """User types tag manually (not from suggestion)."""
    with db.transaction():
        # 1. Get or create tag
        tag_id = get_or_create_tag(tag_name, project_id, family='user')

        # 2. Add to photo_tags (authoritative)
        db.execute("""
            INSERT OR IGNORE INTO photo_tags (photo_id, tag_id)
            VALUES (?, ?)
        """, (photo_id, tag_id))

        # 3. NO decision entry (user didn't react to ML suggestion)
```

**Invariant**: Manual tags don't require decision entries.

---

#### Rule 4: User Removes Confirmed Tag

```python
def remove_tag(photo_id, tag_id):
    """User removes a tag (manual or confirmed ML)."""
    with db.transaction():
        # 1. Remove from photo_tags
        db.execute("""
            DELETE FROM photo_tags
            WHERE photo_id = ? AND tag_id = ?
        """, (photo_id, tag_id))

        # 2. If this was ML-suggested, record implicit rejection
        existing_decision = db.execute("""
            SELECT decision_id FROM photo_tag_decision
            WHERE photo_id = ? AND tag_id = ? AND decision = 'confirm'
        """, (photo_id, tag_id)).fetchone()

        if existing_decision:
            # User removed a previously confirmed ML tag
            suppress_until = (datetime.now() + timedelta(days=90)).isoformat()
            db.execute("""
                INSERT INTO photo_tag_decision
                  (photo_id, tag_id, decision, suppress_until_ts)
                VALUES (?, ?, 'reject', ?)
            """, (photo_id, tag_id, suppress_until))
```

**Invariant**: Removing a tag should suppress future ML suggestions.

---

#### Rule 5: Query for "All Tags"

```python
def get_tags_for_photo(photo_id):
    """Get all confirmed tags for a photo (authoritative)."""
    return db.execute("""
        SELECT t.name
        FROM photo_tags pt
        JOIN tags t ON pt.tag_id = t.id
        WHERE pt.photo_id = ?
        ORDER BY t.name
    """, (photo_id,)).fetchall()
```

**Invariant**: ALWAYS query `photo_tags`, NEVER query suggestions for confirmed tags.

---

### Suppression Expiry

```python
def expire_suppressions():
    """Periodic task: clean up expired suppressions."""
    current_ts = datetime.now().isoformat()
    count = db.execute("""
        DELETE FROM photo_tag_decision
        WHERE decision = 'reject'
          AND suppress_until_ts IS NOT NULL
          AND suppress_until_ts < ?
    """, (current_ts,)).rowcount

    logger.info(f"Expired {count} tag suppression entries")
```

**Schedule**: Run daily or on app startup.

---

## Job Orchestration Architecture

### Design: Persistent Queue + QRunnable Workers

**Hybrid approach**:
1. `ml_job` table = **persistent queue** (survives crashes)
2. `QRunnable` workers = **execution engine** (existing pattern)
3. `JobService` = **bridge** between DB and workers

---

### Job Lifecycle

```
┌─────────────────┐
│  UI clicks      │
│  "Index Photos" │
└────────┬────────┘
         │
         ▼
   ┌─────────────┐
   │ JobService  │
   │ .enqueue()  │
   └──────┬──────┘
          │
          ▼
   ┌─────────────────────────┐
   │ INSERT INTO ml_job      │
   │ status='queued'         │
   └──────┬──────────────────┘
          │
          ▼
   ┌─────────────────────────┐
   │ Create QRunnable Worker │
   │ QThreadPool.start()     │
   └──────┬──────────────────┘
          │
          ▼
   ┌─────────────────────────┐
   │ Worker.run():           │
   │ 1. Claim lease          │
   │ 2. UPDATE status=run    │
   │ 3. Heartbeat loop       │
   │ 4. Process photos       │
   │ 5. UPDATE progress      │
   │ 6. UPDATE status=done   │
   └──────┬──────────────────┘
          │
          ▼
   ┌─────────────┐
   │ Signal UI   │
   │ .finished() │
   └─────────────┘
```

---

### JobService Interface

```python
class JobService:
    """Bridge between persistent ml_job table and QRunnable workers."""

    def enqueue_job(self, kind: str, payload: dict, backend: str = 'cpu') -> int:
        """
        Enqueue a new job.

        Args:
            kind: Job type ('embed', 'caption', 'tag_suggest', etc.)
            payload: Job parameters (photo_ids, model_id, etc.)
            backend: 'cpu' | 'gpu_local' | 'gpu_remote'

        Returns:
            job_id: Primary key of created job
        """
        job_id = self.db.execute("""
            INSERT INTO ml_job (kind, status, backend, payload_json, created_at)
            VALUES (?, 'queued', ?, ?, ?)
        """, (kind, backend, json.dumps(payload), datetime.now().isoformat()))

        # Create worker and start
        worker = self._create_worker(job_id, kind, payload, backend)
        QThreadPool.globalInstance().start(worker)

        return job_id

    def claim_job(self, job_id: int, worker_id: str, lease_seconds: int = 300):
        """Worker claims a job before starting work."""
        lease_expires = (datetime.now() + timedelta(seconds=lease_seconds)).isoformat()

        self.db.execute("""
            UPDATE ml_job
            SET status = 'running',
                worker_id = ?,
                lease_expires_at = ?,
                last_heartbeat_at = ?,
                updated_at = ?
            WHERE job_id = ? AND status = 'queued'
        """, (worker_id, lease_expires, datetime.now().isoformat(),
              datetime.now().isoformat(), job_id))

    def heartbeat(self, job_id: int, progress: float):
        """Worker sends heartbeat to keep lease alive."""
        lease_expires = (datetime.now() + timedelta(seconds=300)).isoformat()

        self.db.execute("""
            UPDATE ml_job
            SET last_heartbeat_at = ?,
                lease_expires_at = ?,
                progress = ?,
                updated_at = ?
            WHERE job_id = ?
        """, (datetime.now().isoformat(), lease_expires, progress,
              datetime.now().isoformat(), job_id))

    def complete_job(self, job_id: int, success: bool, error: str = None):
        """Worker marks job as done or failed."""
        status = 'done' if success else 'failed'

        self.db.execute("""
            UPDATE ml_job
            SET status = ?,
                error = ?,
                progress = 1.0,
                updated_at = ?
            WHERE job_id = ?
        """, (status, error, datetime.now().isoformat(), job_id))
```

---

### Worker Pattern (Embedding Example)

```python
class EmbeddingWorker(QRunnable):
    """Extract visual embeddings for photos."""

    def __init__(self, job_id: int, photo_ids: List[int], model_id: int):
        super().__init__()
        self.job_id = job_id
        self.photo_ids = photo_ids
        self.model_id = model_id
        self.worker_id = f"embedding-{os.getpid()}-{id(self)}"
        self.signals = WorkerSignals()
        self.job_service = JobService()

    @Slot()
    def run(self):
        try:
            # Claim job
            self.job_service.claim_job(self.job_id, self.worker_id)

            # Load model
            model = load_clip_model(self.model_id)

            # Process photos
            for i, photo_id in enumerate(self.photo_ids):
                # Heartbeat every photo
                progress = i / len(self.photo_ids)
                self.job_service.heartbeat(self.job_id, progress)

                # Extract embedding
                embedding = model.encode_image(photo_id)

                # Save to DB
                save_embedding(photo_id, self.model_id, embedding)

                # Signal progress
                self.signals.progress.emit(i+1, len(self.photo_ids))

            # Mark done
            self.job_service.complete_job(self.job_id, success=True)
            self.signals.finished.emit(len(self.photo_ids))

        except Exception as e:
            logger.error(f"Embedding job {self.job_id} failed: {e}")
            self.job_service.complete_job(self.job_id, success=False, error=str(e))
            self.signals.error.emit(str(e))
```

---

## WBS Roadmap (Updated with Critical Changes)

### Phase 0: Foundation (1-3 days)

| WBS | Task | Output |
|-----|------|--------|
| P0.1 | Define semantics scope | Allowed tag families, forbidden categories list |
| P0.2 | Define authority policy | ✅ **Reconciliation rules documented above** |
| P0.3 | Define privacy + compute policy | Offline-first; GPU server opt-in with audit |
| P0.4 | Define query UX targets | Example queries + filters |
| **P0.5** | **Audit existing embedding usage** | ✅ **Confirmed: photo_metadata.embedding = face** |
| **P0.6** | **Design job persistence bridge** | ✅ **JobService spec documented above** |
| **P0.7** | **Define reconciliation rules** | ✅ **Completed above** |
| **P0.8** | **Define suppression policy** | ✅ **30-day default, configurable** |
| **P0.9** | **Define job crash recovery** | ✅ **Lease/heartbeat documented above** |

---

### Phase 1: Core Visual Embeddings (1-2 weeks)

| WBS | Task | Dependencies | Output |
|-----|------|--------------|--------|
| P1.1 | Run migration v6.0.0 | P0.* | Schema upgraded, tables created |
| P1.2 | Implement EmbeddingService | P1.1 | CLIP/SigLIP model loader |
| P1.3 | Implement EmbeddingWorker | P1.2 | Background embedding extraction |
| P1.4 | Implement JobService | P1.1 | Job queue + crash recovery |
| P1.5 | Implement semantic search | P1.3 | Text → embedding → cosine similarity |
| P1.6 | Add Preferences UI | P0.3 | Compute backend selector (CPU/GPU) |
| P1.7 | Incremental updates | P1.3 | Skip photos with fresh embeddings |

---

### Phase 2: Captions & Tags (1-2 weeks)

| WBS | Task | Dependencies | Output |
|-----|------|--------------|--------|
| P2.1 | Implement CaptionService | P1.1 | BLIP2 model loader |
| P2.2 | Implement CaptionWorker | P2.1 | Background caption generation |
| P2.3 | Implement TagSuggestionService | P1.1, P1.5 | Extract tags from captions + embeddings |
| P2.4 | Implement review queue UI | P2.3 | Accordion section with confirm/reject |
| P2.5 | Extend SearchService | P1.5, P2.1 | Hybrid search (SQL + semantic) |
| P2.6 | Implement suppression expiry task | P2.4 | Daily cleanup of expired suppressions |

---

### Phase 3: Evidence Extraction (2-4 weeks)

| WBS | Task | Dependencies | Output |
|-----|------|--------------|--------|
| P3.1 | Implement DetectionService | P1.1 | Grounding DINO model loader |
| P3.2 | Implement on-demand detection | P3.1 | "Find river" → bbox evidence |
| P3.3 | Evidence-aware reranking | P3.2 | Boost results with detection evidence |
| P3.4 | "Explain why" UI | P3.3 | Show caption + bbox overlay |

---

### Phase 4: Event Layer (3-6 weeks)

| WBS | Task | Dependencies | Output |
|-----|------|--------------|--------|
| P4.1 | Implement event proposal | P1.1, P1.5 | Time + semantic + faces → events |
| P4.2 | Implement event merge/split | P4.1 | User actions logged as decisions |
| P4.3 | Event search UI | P4.2 | "Wedding 2019" view |

---

### Phase 5: Hardening (Ongoing)

| WBS | Task | Dependencies | Output |
|-----|------|--------------|--------|
| P5.1 | Artifact dependency graph | P1.1 | Targeted reprocessing |
| P5.2 | Drift evaluation | P1.5 | Periodic model eval dataset |
| P5.3 | Export/delete coverage | P2.1+ | Cascading delete for ML artifacts |
| **P5.4** | **FK enforcement test** | P1.1 | ✅ **Verify PRAGMA foreign_keys ON** |
| **P5.5** | **Job recovery test** | P1.4 | ✅ **Simulate crash, verify recovery** |

---

## Testing & Verification

### Critical Tests

#### Test 1: Foreign Key Enforcement

```python
def test_foreign_keys_enabled():
    """Verify ON DELETE CASCADE works."""
    conn = get_db_connection()

    # Check PRAGMA
    result = conn.execute("PRAGMA foreign_keys").fetchone()
    assert result[0] == 1, "Foreign keys NOT enabled!"

    # Test cascade delete
    photo_id = create_test_photo()
    add_embedding(photo_id)

    # Delete photo
    delete_photo(photo_id)

    # Verify embedding deleted
    embedding = get_embedding(photo_id)
    assert embedding is None, "CASCADE delete failed!"
```

#### Test 2: Job Crash Recovery

```python
def test_job_crash_recovery():
    """Simulate app crash, verify job recovery."""
    # Create running job
    job_id = enqueue_job('embed', {...})
    claim_job(job_id, worker_id='test-worker')

    # Simulate crash (don't complete job)
    # Restart app
    recover_zombie_jobs()

    # Verify job marked failed
    job = get_job(job_id)
    assert job['status'] == 'failed'
    assert 'crash recovery' in job['error'].lower()
```

#### Test 3: Tag Reconciliation

```python
def test_tag_reconciliation():
    """Verify confirm/reject workflow."""
    photo_id = create_test_photo()
    tag_id = create_test_tag('wedding')

    # ML suggests tag
    suggest_tag(photo_id, tag_id, score=0.9)

    # User confirms
    confirm_suggestion(photo_id, tag_id)

    # Verify in photo_tags
    tags = get_tags_for_photo(photo_id)
    assert 'wedding' in tags

    # User removes tag
    remove_tag(photo_id, tag_id)

    # Verify suppressed
    suggestions = get_active_suggestions(photo_id)
    assert tag_id not in [s['tag_id'] for s in suggestions]
```

---

## Next Steps

**Ready to implement**:

1. ✅ **Sprint 1 (Week 1)**: Run migration v6.0.0, implement JobService
2. ✅ **Sprint 2 (Week 2-3)**: Implement embedding extraction + semantic search
3. ✅ **Sprint 3 (Week 4-5)**: Implement captions + tag suggestions + review UI
4. ⏳ **Sprint 4+**: Detections, events, hardening

**Migration Command**:
```bash
cd /home/user/MemoryMate-PhotoFlow-Refactored
python migrations/migration_v6_visual_semantics.py
```

**Verification**:
```python
from repository.base_repository import DatabaseConnection
from migrations.migration_v6_visual_semantics import verify_migration

conn = DatabaseConnection().get_connection()
success, errors = verify_migration(conn)
if success:
    print("✓ Migration verified successfully")
else:
    print("✗ Migration verification failed:")
    for error in errors:
        print(f"  - {error}")
```

---

## Appendix: Repository Layer Invariants

### CRITICAL: Every DB Connection MUST Enable Foreign Keys

```python
# repository/base_repository.py

@contextmanager
def get_connection(self, read_only: bool = False):
    conn = sqlite3.connect(self._db_path, ...)

    # CRITICAL: Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    # Verify
    result = conn.execute("PRAGMA foreign_keys").fetchone()
    if not result or result[0] != 1:
        raise RuntimeError("CRITICAL: Failed to enable foreign keys!")

    # Set busy timeout (avoid "database is locked")
    conn.execute("PRAGMA busy_timeout = 5000")  # 5 seconds

    yield conn
```

**Testing**: Add to `repository/base_repository.py` test suite.

---

**END OF IMPLEMENTATION PLAN**
