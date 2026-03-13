# Changelog

All notable changes to the MemoryMate PhotoFlow search pipeline are documented here.

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
