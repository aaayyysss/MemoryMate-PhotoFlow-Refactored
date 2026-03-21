# Changelog

All notable changes to the MemoryMate PhotoFlow search pipeline are documented here.

## [Unreleased] - 2026-03-22

### Industrial-Grade Face Pipeline & Bootstrap Policy

Comprehensive overhaul of the face clustering pipeline and application startup flow to reach industrial-grade reliability and quality.

#### Face Detection
- **FaceDetectionWorker**:
  - **Increased Throughput**: Set per-screenshot face cap to 18 in `include_cluster` mode to support high-density collages and social media screenshots.
  - **Always-on Classification**: Mandatory screenshot classification regardless of policy ensures consistent behavior across all modes.
  - **Policy-aware Caps**: Applied tiered limits: `exclude` (0), `detect_only` (4), and `include_cluster` (18).

#### Face Clustering
- **FaceClusterWorker**:
  - **Relaxed Small-Face Filtering**: Implemented a conditional 0.008 ratio threshold for screenshots in `include_cluster` mode, significantly increasing recall for crowded group photos.
  - **Aggressive Merge Bias**: Increased DBSCAN epsilon to 0.60 for screenshot-inclusive runs to combat over-fragmentation caused by low-resolution face crops.
  - **Lexicon Expansion**: Added international markers (bildschirmfoto, 스크린샷, etc.) to the clustering-side screenshot detector for localized OS support.
  - **Accounting Granularity**: Implemented class-level `_skip_stats` to track specific attrition reasons (bad_dim, low_conf, small_face_screenshot).

#### Project Management & Reliability
- **Bootstrap Policy**: Implemented canonical startup selection (Last-used -> Single existing -> Onboarding/Selection state) in `main_window_qt.py`.
- **Model Intelligence**: `ProjectRepository` now automatically selects the highest-tier CLIP model available (Large > B16 > B32) for new projects.
- **UI Feedback**: Added "Model Upgrade Assistant" tooltip and a clearer explanation of screenshot clustering behavior in the scope dialog.

### Files Changed
- `workers/face_detection_worker.py`
- `workers/face_cluster_worker.py`
- `workers/face_pipeline_worker.py`
- `main_window_qt.py`
- `repository/project_repository.py`
- `ui/face_detection_scope_dialog.py`

### Test Updates
- Verified with 279 tests (100% pass rate).

---

## [Unreleased] - 2026-03-14

### Screenshot Builder, Candidate Fusion & Builder Diagnostics

New dedicated screenshot retrieval pipeline, multi-builder fusion support,
and diagnostic instrumentation across all candidate builders.

#### ScreenshotCandidateBuilder
- **New `ScreenshotCandidateBuilder`** (`services/candidate_builders/screenshot_candidate_builder.py`)
  — Dedicated multi-signal screenshot detection with composite scoring:
  - `is_screenshot` metadata flag (0.40)
  - Filename markers: screenshot, bildschirmfoto, captura, etc. (0.25)
  - UI-text OCR patterns: battery, wifi, settings, etc. — 2+ terms required (0.20)
  - Screen-like aspect ratio (1.5–2.3) + OCR text density (0.15)
  - Query text term match in OCR content (0.05)
- Each candidate receives a `screenshot_score` [0..1] for ranking

#### Preset-Level Builder Dispatch
- **`PRESET_BUILDERS`** map in `services/candidate_builders/__init__.py` — Preset-specific
  builder overrides that take priority over family-level `CANDIDATE_BUILDERS` dispatch
- `"screenshots"` preset now routes to `ScreenshotCandidateBuilder` instead of
  falling through to `DocumentCandidateBuilder`

#### Candidate Set Fusion
- **`_fuse_candidate_sets()`** in `search_orchestrator.py` — Google-style fusion
  that merges multiple `CandidateSet` results by path with evidence accumulation
- When the same path appears in multiple builders, evidence dicts are merged
- Inherits family from the first non-empty set; takes max confidence

#### Builder Diagnostics
- **`CandidateSet.diagnostics`** — New `Dict[str, Any]` field on `CandidateSet`
  for rejection tracking and debug metadata
- **`DocumentCandidateBuilder`** now tracks rejection counts by reason
  (insufficient_evidence, etc.) and logs rejection histograms
- **`PeopleCandidateBuilder`** diagnostics include named_hits, cluster_hits,
  cooccurrence_hits, face_presence_hits, and top event_score samples
- **`SearchConfidencePolicy`** enriches low-confidence warnings with top rejection
  reasons (document family) and face presence breakdown (people family)
- **`get_last_candidate_diagnostics()`** on orchestrator for external access

#### Ranker: w_screenshot Weight
- **`ScoringWeights.w_screenshot`** — New reserved weight channel (default 0.00)
  for screenshot-specific evidence scoring

### Files Changed
- `services/candidate_builders/__init__.py`
- `services/candidate_builders/base_candidate_builder.py`
- `services/candidate_builders/screenshot_candidate_builder.py` *(new)*
- `services/candidate_builders/document_candidate_builder.py`
- `services/candidate_builders/people_candidate_builder.py`
- `services/ranker.py`
- `services/search_confidence_policy.py`
- `services/search_orchestrator.py`
- `tests/test_search_quality.py`

### Test Updates
- Updated weight-sum-to-one tests to include `w_event` + `w_screenshot` in the
  total (was summing 8 weights, now correctly sums all 9)
- All 306 relevant tests pass

---

## [Unreleased] - 2026-03-13

### Bug Fix: people_event NoneType crash (PR #718 CI fix)

Fixed `TypeError: object of type 'NoneType' has no len()` that crashed
all people_event searches (Wedding, Party, Baby, Portraits).

**Root cause**: When `people_event_candidates` triggered `skip_clip_for_type`,
the CLIP-skip log line at the `elif` branch called `len(type_structural_candidates)`
— but `type_structural_candidates` was `None` for people_event queries (only
`people_event_candidates` was populated). The f-string `len()` call on `None`
raised `TypeError`, which propagated to `[FindSection] Async search failed`.

**Fix**: Replaced the unsafe `len(type_structural_candidates)` with a
None-guarded expression that logs the correct pool name and size for
whichever candidate pool (type or people_event) caused CLIP to be skipped.

**Audit**: Verified all other `len()` calls on potentially-None variables
(`metadata_candidate_paths`, `people_event_candidates`,
`type_structural_candidates`) are safe — either guarded by `is not None`
checks or inside branches where assignment is guaranteed.

### Search Pipeline Architecture Fixes (Steps 1-5)

Five surgical fixes addressing confirmed architectural issues in the search
ranking and candidate retrieval pipeline.

#### Step 1: Wire event_score through the ranking pipeline
- **ranker.py**: Added `event_score` field to `ScoredResult` dataclass
- **ranker.py**: Added `w_event` weight to `ScoringWeights` with canonical
  mapping, validation, and normalization
- **ranker.py**: Added `event_score` parameter to `Ranker.score()` — enters
  the weighted formula as `w_event * event_score`
- **ranker.py**: `FAMILY_WEIGHTS["people_event"]` now allocates `w_event=0.25`
  (taken from `w_clip`, reduced from 0.58 to 0.33)
- **ranker.py**: `score_many()` accepts `event_scores` dict and passes per-path
  values through to `score()`
- **ranking_config.py**: Added `w_event` to `FAMILY_DEFAULTS` for all families
  and to `_WEIGHT_KEYS` tuple for preference reading

**Why**: The PeopleCandidateBuilder computed `event_score` per candidate but
the ranker never saw it. The feature was decorative — face_match (binary 0/1)
was the only people signal in final ranking.

#### Step 2: Give people_event its own execution branch
- **search_orchestrator.py**: `people_event_candidates` is now a separate set,
  never reusing the `type_structural_candidates` variable
- **search_orchestrator.py**: `people_event_evidence` dict extracted from
  `builder_candidate_set.evidence_by_path`
- **search_orchestrator.py**: Dedicated scoring loop at Step 5 passes
  `event_score` from evidence to `_score_result()` per candidate
- **search_orchestrator.py**: Own `[PeopleEvent]` logging prefix for
  diagnostics

**Why**: People_event candidates were shoved into `type_structural_candidates`
and followed the type-family scoring path, where `structural_scores={}` and
`ocr_scores={}` meant only CLIP + binary face_match survived.

#### Step 3: Kill the legacy `_build_type_candidates()` split-brain
- **search_orchestrator.py**: Deleted `_build_type_candidates()` method entirely
  (was ~85 lines of inline structural candidate logic duplicating
  `DocumentCandidateBuilder` / `DocumentEvidenceEvaluator`)
- **search_orchestrator.py**: Legacy fallback at the "builder inactive" branch
  now returns empty with a `BUILDER_UNAVAILABLE` warning instead of silently
  switching to a parallel evidence contract
- Forces all type-family candidate generation through the canonical
  `DocumentCandidateBuilder`

**Why**: Two candidate generation paths with different constants, different
extension sets, and different GateEngine calls produced inconsistent results.
The legacy path could return candidates the builder would have rejected and
vice versa.

#### Step 4: Add family-path consistency assertions
- **search_orchestrator.py**: After `_resolve_family()`, logs
  `FAMILY_MISMATCH` warning if builder's `family_hint` disagrees with
  `PRESET_FAMILIES` mapping
- **search_orchestrator.py**: Post-scoring `SCORING_ANOMALY` warning when:
  - All type-family results have `structural=0` AND `ocr=0`
  - All people_event results have `event_score=0`
- **search_orchestrator.py**: Debug log line now includes `event=` field
  alongside clip/struct/ocr/face

**Why**: Silent family/evidence mismatches are hard to debug. These assertions
surface wiring bugs at runtime without crashing production.

#### Step 5: Pass evidence bundle forward (lightweight)
- **search_orchestrator.py**: Type-family branch now captures
  `type_evidence = builder_candidate_set.evidence_by_path` when builder is
  active
- **search_orchestrator.py**: Builder boolean evidence signals (`ocr_fts_hit`,
  `ocr_lexicon_hit`, `structural_hit`) boost structural scores for candidates
  the metadata scan scored conservatively
- No new classes — dict pass-through from builder to scoring, ~20 lines

**Why**: The orchestrator was recomputing evidence from metadata that the
builder had already evaluated. Builder evidence now supplements (not replaces)
the structural scoring pass.

### Files Changed
- `services/ranker.py`
- `config/ranking_config.py`
- `services/search_orchestrator.py`
- `tests/test_search_orchestrator.py`
- `CHANGELOG.md` (this file)

### Test Updates
- Updated weight-sum-to-one tests for all families to include `w_event` in
  the total (was summing 7 weights, now correctly sums all 8)
- Renamed `test_all_families_have_seven_weight_components` to
  `test_all_families_have_eight_weight_components` and added `w_event` check
- Renamed `test_validate_normalizes_seven_weights` to
  `test_validate_normalizes_eight_weights` with `w_event` in constructor
- Added assertion that `people_event` family has positive `w_event`
- All 207 tests pass
