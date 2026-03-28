# Changelog

All notable changes to the MemoryMate PhotoFlow search pipeline are documented here.

## [Unreleased] - 2026-03-28

### UX-9 Review: Implementation Gap Audit & Fixes

Comprehensive audit of UX-9 spec against codebase, fixing 11 implementation gaps
identified by the review document.

#### Merge Engine
- Score threshold corrected: 0.62 → 0.60 (matches spec)

#### Facet Quality (UX-9D)
- `_normalize_result_facets()` upgraded: handles all facet types (people, locations, years,
  types), filters dead items (count<=0), caps to 12 per category (was 8 for people only)
- `filter_section.py`: facet items now sorted by count desc before rendering

#### Merge Suggestions Panel
- QSplitter left/right layout with separate QTextEdit previews for each cluster
  (replaces single details pane); dialog widened to 760x520

#### Unnamed Cluster Review
- Added `markDistinctRequested` signal to UnnamedClusterReviewDialog (UX-9 compat alias)
- `_keep_separate` now emits both `keepSeparateRequested` and `markDistinctRequested`

#### People Section Adapters
- Added `get_unnamed_cluster_items()` — simple dict adapter for UX-9C workflow
- Added `mark_unnamed_cluster_distinct()` — persists "distinct" decision to DB
- Added `assign_unnamed_cluster_to_person()` — delegates to existing merge logic

#### State & Controller
- Added `unnamed_cluster_items` field to SearchState
- Added `set_unnamed_cluster_items()` to SearchController
- `_refresh_people_quick_section()` now also extracts unnamed_cluster_items

#### MainWindow Routing
- Added `_mark_unnamed_cluster_distinct()` handler with sidebar/layout fallback
- `_handle_search_sidebar_branch_request()` now routes "people_unnamed" directly
  to `_open_unnamed_cluster_review()` (was routing through intermediate wrapper)

#### App Log Audit (clean run)
- Reviewed 943-line app_log.txt: zero errors, zero exceptions, zero crashes
- Boot → scan → embed → cluster → navigate → shutdown all clean (exit code 0)

#### Files Changed
- `services/people_merge_engine.py`
- `ui/search/search_state_store.py`
- `ui/search/search_controller.py`
- `ui/search/people_merge_suggestions_panel.py`
- `ui/search/unnamed_cluster_review_dialog.py`
- `ui/search/sections/filter_section.py`
- `ui/accordion_sidebar/people_section.py`
- `main_window_qt.py`
- `CHANGELOG.md`

---

## [Unreleased] - 2026-03-27

### UX-11: Interaction Polish & UX-9A Post-Implementation

Smoother typing experience, cursor affordance, browse mode clarity, and a complementary
DB-native merge engine with persistent candidate caching.

#### UX-11: Interaction Polish
- **TopSearchBar**: 250ms debounce timer on `queryChanged` emission — prevents rapid-fire
  search requests while typing; direct emit moved behind `_emit_debounced_query`
- **SearchController**: `_mark_interaction(action)` records `last_interaction_ts` and
  `last_action` on every user-initiated state change (query, submit, preset, filter, browse)
- **SearchState**: Added `last_interaction_ts` (float), `last_action` (str),
  `is_user_typing` (bool) fields for debounce and flicker prevention
- **ActiveChipsBar**: `Qt.PointingHandCursor` on chip buttons and Clear button
- **BrowseSection**: Section title updates to show active browse mode
  (e.g. "Browse — Favorites") for mode-lock clarity

#### UX-9A Post-Implementation: DB-Native Merge Engine
- **New**: `services/people_merge_engine.py` — complementary merge engine with
  78% embedding / 17% size-balance / 5% unnamed-bonus scoring, MIN_SCORE 0.62
- Persistent merge decisions: `people_merge_decisions` table with accept/reject + score/reason
- Candidate caching: `people_merge_candidates` table for fast re-retrieval
- Cluster summaries: `people_cluster_summary` table materialized from face_branch_reps
- `_normalize_result_facets()` in SearchController — sorts people facets by count desc,
  limits to top 8 for cleaner filter display

#### Files Changed
- `ui/search/top_search_bar.py` (UX-11)
- `ui/search/active_chips_bar.py` (UX-11)
- `ui/search/sections/browse_section.py` (UX-11)
- `ui/search/search_state_store.py` (UX-11)
- `ui/search/search_controller.py` (UX-11 + UX-9A Post-Impl)
- `services/people_merge_engine.py` (new — UX-9A Post-Impl)
- `reference_db.py` (UX-9A Post-Impl — 3 new tables)
- `CHANGELOG.md`

---

### UX-10 (A-F): Result Pane Polish, Review Workflows, Stable Transitions

Makes the result experience feel product-grade with stable transitions, richer review
workflows, and clearer "why these results" explanations aligned with Google Photos / Lightroom.

#### UX-10A: Result Pane Structure Polish
- **New**: `ui/search/result_context_bar.py` — explanation + scope labels between header and grid
- Upgraded `search_results_header.py`: warning badge, selection indicator label,
  explanation line, isValid guard, cleaner layout (QVBoxLayout top/bottom rows)
- Upgraded `empty_state_view.py`: stable loading state keeps previous results described,
  cleaner "indexing" alias, richer no-results hint mentioning People merges
- `google_layout.py`: during search_in_progress, keeps existing results visible instead of
  flashing empty state (stable transitions via `_last_displayed_paths` tracking)

#### UX-10B: Side-by-Side People Comparison (text-based companion)
- **New**: `ui/search/people_comparison_dialog.py` — lightweight text-list comparison dialog
  for cluster sample review (complements UX-9B's thumbnail-based PersonComparisonDialog)

#### UX-10C: Unnamed Cluster Review Workflow
- **New**: `ui/search/unnamed_cluster_review_dialog.py` — assign to existing person,
  keep as separate person, or ignore for now (fixed magic number 256 → Qt.UserRole)
- `get_unnamed_cluster_payloads()` in people_section.py — builds structured payloads
  with candidate named people for assignment
- `assign_unnamed_cluster()` executes `merge_face_clusters()` to merge into named person
- `keep_unnamed_cluster_separate()` + `ignore_unnamed_cluster()` persist decisions to DB
- `_open_unnamed_cluster_review()` in main_window_qt.py launches the dialog
- `_assign_unnamed_cluster()`, `_keep_unnamed_cluster_separate()`,
  `_ignore_unnamed_cluster()` — MainWindow bridge handlers

#### UX-10D/E/F: State, Controller, and Refresh Enhancements
- SearchState: added `selected_result_ids`, `merge_review_payloads`, `unnamed_cluster_payloads`
  (selected_result_ids clears on clear_search; review payloads persist)
- SearchController: `set_merge_review_payloads()`, `set_unnamed_cluster_payloads()`,
  `set_selected_result_ids()`, `refresh_status()` for review-state-safe refreshes
- `_refresh_people_quick_section()` upgraded to extract and populate all review payloads

#### Design Decisions (UX-9 preserved, not downgraded)
- Kept UX-9A centroid-based `get_merge_suggestions()` (spec wanted weaker heuristic)
- Kept UX-9A DB-persisting accept/reject (spec wanted print stubs)
- Kept UX-9B PersonComparisonDialog queue-based review (spec wanted text-only)
- Added UX-10 features additively on top of UX-9 foundation

#### Files Changed
- `ui/search/result_context_bar.py` (new — UX-10A)
- `ui/search/people_comparison_dialog.py` (new — UX-10B)
- `ui/search/unnamed_cluster_review_dialog.py` (new — UX-10C)
- `ui/search/search_state_store.py` (UX-10D)
- `ui/search/search_controller.py` (UX-10D)
- `ui/search/search_results_header.py` (UX-10A)
- `ui/search/empty_state_view.py` (UX-10A)
- `ui/accordion_sidebar/people_section.py` (UX-10C)
- `main_window_qt.py` (UX-10C/F)
- `layouts/google_layout.py` (UX-10A)
- `CHANGELOG.md`

---

### UX-9 (A+B+C+D): People Merge Intelligence, Side-by-Side Review, Unnamed Clusters, Facet Quality

Complete UX-9 patch pack implementing real merge intelligence, side-by-side person comparison,
unnamed-cluster review workflow, audit trail for decisions, and people-aware facet prioritization.

#### UX-9A: Merge Intelligence Engine
- **New**: `services/people_merge_intelligence.py` — weighted scoring engine
  (55% embedding, 15% size, 15% temporal, 15% camera) with MIN_SCORE 0.45
- **New**: `people_merge_review` table in `reference_db.py` with UPSERT semantics
- `get_merge_suggestions()` builds ClusterSummary from face_branch_reps centroids,
  filters prior decisions, delegates to PeopleMergeIntelligence
- Upgraded `people_merge_suggestions_panel.py` with QTextEdit details pane

#### UX-9B: Side-by-Side Person Comparison Dialog
- **New**: `ui/search/person_comparison_dialog.py` — 900x620 dialog with left/right
  QGroupBox clusters, scrollable 96px preview thumbnails, similarity score + reasons
- Queue-based review: accept/reject advances to next candidate automatically
- `_open_people_merge_review()` now uses PersonComparisonDialog instead of list panel
- `_show_next_merge_review_dialog()` steps through ranked suggestions sequentially

#### UX-9B (cont): Merge Review Payload
- `get_merge_review_payload()` in people_section.py — cosine similarity on centroids,
  0.72 threshold, preview paths/thumbs, ranked top-20 with confidence-band reasons
- `merge_review_payload` field added to SearchState (not cleared by clear_search)
- `set_merge_review_payload()` added to SearchController
- `_refresh_people_quick_section()` upgraded to populate merge + unnamed payloads

#### UX-9C: Unnamed Cluster Review
- `get_unnamed_review_payload()` identifies face_-prefixed and "unnamed" clusters
- `unnamed_review_payload` field added to SearchState (not cleared by clear_search)
- `_open_unnamed_people_review()` dialog shows unnamed clusters with counts
- `people_unnamed` branch request now routes to review dialog instead of sidebar emit
- Button label changed: "Review Unnamed Clusters" (clearer action verb)

#### UX-9C (cont): Audit Trail
- `face_merge_review_log` table with project_id, branch IDs, decision, timestamp
- `accept_merge_suggestion()` and `reject_merge_suggestion()` write audit entries
  alongside the existing people_merge_review persistence

#### UX-9D: Facet Quality Engine
- `_compute_visible_facet_keys()` in SearchController — context-aware facet ordering
- People family: ["people", "year", "location", "type"]
- Scenic family: ["location", "year", "type"]
- Type family: ["type", "year", "location"]
- Browse modes: favorites/videos/with_location get tailored facet sets
- `_infer_family()` helper detects search family from state + query keywords

#### Files Changed
- `services/people_merge_intelligence.py` (new — UX-9A)
- `ui/search/person_comparison_dialog.py` (new — UX-9B)
- `reference_db.py` (UX-9A)
- `ui/accordion_sidebar/people_section.py` (UX-9A/B/C)
- `ui/search/people_merge_suggestions_panel.py` (UX-9A)
- `ui/search/search_state_store.py` (UX-9B/C)
- `ui/search/search_controller.py` (UX-9B/C/D)
- `ui/search/sections/people_quick_section.py` (UX-9C)
- `main_window_qt.py` (UX-9B/C)
- `CHANGELOG.md`

---

### UX-8 Audit: Bug Fixes, Design Compliance, and Missing Features

Comprehensive audit of the UX-1 through UX-8 implementation against the design specification,
app_log.txt test-run analysis, and Google Photos / Lightroom / Excire UX best practices.

#### Critical Bug Fixes (from app_log.txt analysis)

- **Duplicate Viewer Crash**: `AssetRepository.list_duplicate_assets()` now accepts `limit` and `offset`
  parameters, fixing the `TypeError` that completely broke the duplicate photo viewer.
- **Similar Photo Dialog Crash**: Fixed `sqlite3.OperationalError: no such table: photo_embedding` by
  updating `similar_photo_dialog.py` to query the canonical `semantic_embeddings` table (v7+) instead
  of the legacy `photo_embedding` table (v6).
- **Thumbnail Cache False Purges**: `ThumbCacheDB.purge_stale()` was comparing file modification times
  against a 30-day cutoff, causing freshly-cached thumbnails of older photos to be immediately purged.
  Added `cached_at` column and use insertion time for staleness decisions.

#### UX Signal Wiring Fixes

- **SearchSidebar Disconnected Signals**: `SearchSidebar.selectBranch` and
  `openActivityCenterRequested` signals were never connected in `MainWindow`, making People merge
  review, unnamed clusters, and Activity Center sidebar buttons completely non-functional. Now wired
  to `_handle_search_sidebar_branch_request` and `_open_activity_center_from_sidebar`.
- **ActiveChipsBar ScrollBarPolicy**: Fixed `AttributeError` caused by calling
  `.ScrollBarAlwaysOff` on an enum return value instead of using `Qt.ScrollBarAlwaysOff` directly.

#### UX Rule 3 Compliance: Contextual Filter Visibility

- **FilterSection** now starts hidden and only appears when a search query, preset, browse mode,
  or active filters exist. This follows the design principle "do not show every filter all the time"
  and matches Google Photos / Lightroom behavior where refinements appear contextually.

#### SearchHubSection: Emoji Prefix Leak Fix

- Recent search and suggestion items stored clean text in `Qt.UserRole` but click handlers
  extracted the display text (with emoji prefix like "🕒 beach"). Fixed to use `UserRole` data,
  preventing corrupted search queries.

#### Missing Features Implemented

- **Sort Selector**: `SearchResultsHeader` now includes a sort dropdown (Relevance, Date Newest/Oldest,
  Name) with full state store integration via `SearchController.apply_sort()`. Matches the design spec
  and aligns with Lightroom/Excire sort-in-header pattern.
- **EmptyStateView Complete States**: Expanded from 3 states to 6 per the design specification:
  - `no_project` - with action button to select project
  - `no_results` - with hint to try different keywords
  - `loading` - searching indicator
  - `indexing_in_progress` - scan progress messaging
  - `embeddings_missing` - with action button to extract embeddings
  - `face_clustering_incomplete` - clustering progress messaging
- **Search Payload Completeness**: `SearchController.run_search()` payload now includes `sort_mode`,
  `browse_mode`, and `search_mode` for downstream consumers.

#### UX-8 Design Audit Findings

The following design aspects from the UX spec are verified as correctly implemented:
- SearchStateStore canonical state with 48 fields covering all search dimensions
- SearchController as sole state mutator with debounced search
- TopSearchBar with popup for recent/suggestions, project-aware enable/disable
- DiscoverSection with SmartFindCard visual cards, active state, counts, previews
- PeopleQuickSection with merge review, unnamed clusters, show-all buttons
- BrowseSection with active mode highlighting
- ActivityMiniSection with progress bar and Activity Center link
- ActiveChipsBar with removable chips and clear-all
- PeopleMergeSuggestionsPanel and Dialog for merge workflow

#### Architecture Pattern Fixes (from UX-8 document audit)

- **State Mutation Violation in `remove_chip`**: The `browse` chip removal path directly mutated
  `state.active_filters` via `.pop()` instead of going through `store.update()`, violating the
  controller-only-mutates-state rule. Fixed to create a new dict and use `store.update()`.
- **Magic Number in `PeopleMergeSuggestionsPanel`**: Replaced raw `256` with `Qt.UserRole` for
  list item data storage/retrieval.

#### Files Changed
- `main_window_qt.py`
- `ui/search/active_chips_bar.py`
- `ui/search/search_results_header.py`
- `ui/search/search_controller.py`
- `ui/search/search_sidebar.py`
- `ui/search/sections/search_hub_section.py`
- `ui/search/sections/filter_section.py`
- `ui/search/empty_state_view.py`
- `ui/search/people_merge_suggestions_panel.py`
- `repository/asset_repository.py`
- `ui/similar_photo_dialog.py`
- `thumb_cache_db.py`

---

## [Unreleased] - 2026-03-22

### Industrial-Grade Face Pipeline & Bootstrap Policy

Final comprehensive overhaul of the face processing stack, eliminating filtering bottlenecks and ensuring maximum recall for screenshots and group photos.

#### Face Detection
- **FaceDetectionWorker**:
  - **Zero Truncation**: Eliminated the per-screenshot face cap for `include_cluster` mode (previously 14-18), allowing all detected faces (e.g., 20+ in dense collages) to reach the database.
  - **Always-on Classification**: Mandatory screenshot classification regardless of policy ensures consistent behavior across all modes.
  - **Policy-aware Caps**: Retained tiered limits for standard modes: `exclude` (0), `detect_only` (4).

#### Face Clustering
- **FaceClusterWorker**:
  - **Zero-drop Small Face Policy**: Fully disabled small-face dropping in `include_cluster` mode. Faces are no longer filtered by area ratio, ensuring small background faces in screenshots are clustered.
  - **Very Aggressive Merge Bias**: Increased DBSCAN epsilon to 0.70 for screenshot-inclusive runs to combat over-fragmentation and ensure noisy social media faces are grouped effectively.
  - **Lexicon Expansion**: Added international markers (bildschirmfoto, 스크린샷, etc.) to the clustering-side screenshot detector for localized OS support.
  - **Accounting Granularity**: Implemented class-level `_skip_stats` to track specific attrition reasons (bad_dim, low_conf, small_face_screenshot).

#### Face Pipeline
- **FacePipelineWorker**:
  - **Enhanced Accounting**: Final `FACE_ACCOUNTING` summary now exposes full attrition (detected -> DB -> loaded -> dropped) including screenshot-specific skip statistics.
  - **Policy Consistency**: Guaranteed that interim clustering passes strictly adhere to the user's active screenshot policy.

#### Project Management & Reliability
- **Bootstrap Policy**: Implemented canonical startup selection (Last-used -> Single existing -> Onboarding/Selection state) in `main_window_qt.py` to ensure valid application state on startup.
- **Model Intelligence**: `ProjectRepository` now automatically selects the highest-tier CLIP model available (Large > B16 > B32) for new projects by searching multiple common model directory patterns.
- **UI Feedback**: Added "Model Upgrade Assistant" tooltip and a clearer explanation of screenshot clustering behavior in the scope dialog.
- **Database Stability**: Increased `busy_timeout` to 30,000ms across `DatabaseConnection` and `ReferenceDB` to mitigate locking issues during concurrent background tasks.
- **Concurrency Fix**: Implemented chunked commits (every 50 clusters) in `FaceClusterWorker` to prevent long-held write locks during massive re-clustering operations.
- **Signal Integrity**: Fixed signature mismatches in `MainWindow` and `PeopleManagerDialog` signal handlers to correctly propagate the new 3-mode screenshot policy.

### Files Changed
- `workers/face_detection_worker.py`
- `workers/face_cluster_worker.py`
- `workers/face_pipeline_worker.py`
- `main_window_qt.py`
- `repository/project_repository.py`
- `repository/base_repository.py`
- `reference_db.py`
- `ui/face_detection_scope_dialog.py`
- `ui/people_manager_dialog.py`

### Test Updates
- Verified with 279 tests (100% pass rate).

## [Unreleased] - 2026-03-23

### Search Shell Centralization (UX-1 Completion)

Completed the transition of search ownership to `MainWindow`, establishing a centralized search shell that maintains consistent state across layout switches and handles onboarding mode gracefully.

#### Search Shell Architecture
- **Centralized Ownership**: `MainWindow` is now the sole owner of `SearchStateStore`, `SearchController`, `TopSearchBar`, `SearchResultsHeader`, `ActiveChipsBar`, and `SearchSidebar`.
- **Search Bridge**: Implemented a robust `_on_ux1_search_requested` bridge in `MainWindow` that routes centralized search requests to existing search pipelines, ensuring a low-risk integration.
- **Legacy Cleanup**: Removed redundant search widgets (`SearchBarWidget`, `SemanticSearchWidget`) from `MainWindow` and `GooglePhotosLayout` toolbars to eliminate UI confusion.
- **Cross-Layout Sync**: Updated `LayoutManager` to ensure the centralized search shell remains visible and consistent across all UI layouts (Current, Google, Apple, Lightroom).

#### UI & Onboarding Improvements
- **Onboarding Awareness**: `SearchResultsHeader` now explicitly displays "No active project" during onboarding.
- **Project-Bound Logic**: `SearchSidebar` now disables project-specific sections (Discover, People, Filters) when no project is active, providing a clearer onboarding path.
- **Startup Suppression**: Enhanced startup logic in `MainWindow` to suppress project-bound layout loading when starting in an unbound onboarding state.
- **Navigation Parity**: Updated the `Ctrl+F` shortcut to focus the new centralized `TopSearchBar` across all layouts.

#### Files Changed
- `main_window_qt.py`
- `layouts/google_layout.py`
- `layouts/layout_manager.py`
- `ui/search/search_sidebar.py`
- `ui/search/search_results_header.py`
- `ui/search/active_chips_bar.py`
- `ui/search/empty_state_view.py`
