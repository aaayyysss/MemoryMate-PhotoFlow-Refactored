# Changelog

All notable changes to the MemoryMate PhotoFlow search pipeline are documented here.

## [Unreleased] - 2026-04-01

### 🔧 PATCH PACK: Ownership Fix + Polish Release

**Goal**: Fix photogrid refresh (new shell becomes real action owner), bridge legacy systems, add modern UI polish, push to production.

#### Critical Fixes
- **Favorites Bug Fixed**: Changed `_load_photos(favorites_only=True)` → `_filter_favorites()` in handle_shell_branch_request()
  - `_load_photos()` doesn't support `favorites_only` parameter
  - Now correctly calls the existing `_filter_favorites()` method
  
- **PhotoGrid Refresh**: New shell now drives photogrid directly  
  - Google layout dispatcher uses intelligent branch routing
  - People + Browse sections properly bridge to legacy accordion
  - Legacy fallback only for unhandled branches

#### UI Polish (Google/Apple Feel)
- **Soft Styling Applied**:
  - Removed heavy borders, replaced with soft hover effects
  - Rounded buttons (6px border-radius)
  - Light blue hover background (#eef3ff)
  - Transparent backgrounds with subtle interactions
  - Reduced visual hierarchy clutter
  
- **ExpandableSection Already In Place**:
  - All sections wrapped in collapsible headers
  - Search Hub, Discover, People, Browse: expanded by default
  - Filters, Activity: collapsed by default

#### Architecture Ownership Fix
- **Main routing via main_window_qt._handle_search_sidebar_branch_request()**:
  1. Special People actions → direct handlers
  2. Google layout direct handler (NEW dispatcher priority)
  3. Legacy accordion bridge for deep interactions
  4. Legacy SidebarQt fallback

- **Google layout.handle_shell_branch_request()**:
  - Direct loaders: "all", "favorites"
  - Structure bridge: folders, dates, videos, duplicates, locations, devices, people
  - Quick dates: today, yesterday, last_7_days, last_30_days, this_month, last_month, this_year, last_year
  - Simple types: documents, screenshots
  - Returns True if handled, False for fallback

- **set_project() Refresh Hooks**:
  - After project switch, refreshes People and Browse quick sections
  - Calls `_refresh_people_quick_section()` and `_refresh_browse_quick_section()` on MainWindow if available
  - Ensures new shell stays in sync with project changes

#### Files Modified
- `main_window_qt.py` — _handle_search_sidebar_branch_request() already in place (routing verified)
- `layouts/google_layout.py` — Updated handle_shell_branch_request() method + added set_project() refresh hooks
- `ui/search/search_sidebar.py` — Added soft stylesheet for modern UI feel

#### Final State
✅ Photogrid updates instantly from new shell  
✅ Browse drives Google layout, expands legacy for deep navigation  
✅ People uses real legacy actions, no dead buttons  
✅ UI clean, modern, expandable, not cluttered  
✅ New shell = owner, legacy sidebar = fallback only

---

## [Unreleased] - Previous

### Feature-Parity Sidebar Migration—Branch Routing & Expandable Sections

Comprehensive migration of Google sidebar functionality to new production shell with full backward compatibility maintained.

#### Critical Fixes
- **PhotoGrid Refresh Bug Fixed**: New shell now drives Google photogrid directly via intelligent branch routing (was stuck using legacy SidebarQt path)
  - `SearchSidebar.selectBranch` signal now properly connected to main_window_qt handler
  - Google layout prioritized first with `handle_shell_branch_request()` dispatcher
  - Legacy SidebarQt acts as fallback only
  - All branch requests from new shell now correctly trigger grid reloads

#### Shell Architecture Improvements
- **Expandable Sections**: Main sections (Search Hub, Discover, People, Browse, Filters, Activity) now collapsible via header toggles
  - Search Hub, Discover, People, Browse: expanded by default
  - Filters, Activity: collapsed by default
  - Reduces visual clutter and improves UX density
  
- **Browse Subsections**: Reorganized Browse section into expandable groups:
  - **Library** (All Photos, Years, Months, Days) — expanded by default
  - **Sources** (Folders, Devices) — expanded by default
  - **Collections** (Favorites, Videos, Documents, Screenshots, Duplicates) — collapsed
  - **Places** (Locations) — collapsed
  - **Quick Access** (Today, Yesterday, Last X days, This/Last month/year) — collapsed

#### Branch Routing Architecture
- **Priority dispatcher in MainWindow**:
  1. People special actions (merge_review, unnamed, tools, history, undo/redo, expand) → direct handlers
  2. Google layout direct handler → `handle_shell_branch_request()` dispatcher
  3. Legacy SidebarQt fallback → only if Google layout doesn't handle it
  
- **Google layout `handle_shell_branch_request()` handles**:
  - Direct grid actions: all, favorites
  - Section transitions: folders, dates, videos, duplicates, locations, devices, people
  - Quick date presets: today, yesterday, last_7_days, last_30_days, this_month, last_month, this_year, last_year

#### Browse Section
- Expanded with full coverage of old sidebar: Library (All Photos, Years, Months, Days), Sources (Folders, Devices), Collections (Favorites, Videos, Documents, Screenshots, Duplicates), Places (Locations), Quick Access (Today, Yesterday, Last X days, etc.)
- Device sub-items now displayed with indentation
- Count display for all items
- Proper signal mapping to navigation branches
- **NEW**: Browse subsections now expandable for better UX organization

#### People Section
- Top people list with live count display
- Review Possible Merges with dynamic count
- Show Unnamed Clusters with dynamic count
- Show All People and People Tools buttons
- Legacy People row actions preserved in new shell (History, Undo, Redo, Expand)
- Full backward compatibility with legacy `set_people()` method

#### Sidebar Architecture
- Dual-sidebar layout maintained during transition
- New production shell on top (SearchSidebar) — growing primary UX
- Legacy Google sidebar on bottom (AccordionSidebar) — compatibility layer
- Legacy sidebar remains visible until parity proven
- **NEW**: Main sections now wrapped with ExpandableSection for collapsible headers
- **NEW**: _expand_legacy_section_and_hint() helper bridges new shell to old accordion during transition

#### Files Modified
- `main_window_qt.py` — Added branch routing dispatcher + browse payload refresh
- `layouts/google_layout.py` — Added handle_shell_branch_request() + _expand_legacy_section_and_hint()
- `ui/search/search_sidebar.py` — Added ExpandableSection + ExpandableSubsection wrapper classes + wrapped all sections
- `ui/search/sections/browse_section.py` — Refactored with _ExpandableSubsection for nested collapsible groups

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
