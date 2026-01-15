Here’s what I did: I inspected

accordion_sidebar.py (your Accordion sidebar)

layouts/google_layout.py (your Google Photos-style layout)

sidebar_controller.py

photo_operations_controller.py

project_controller.py

scan_controller.py

video_service.py

main_window_qt.py

and focused on how they interact around:

Sidebar behavior (old SidebarQt vs AccordionSidebar)

Google layout switching & refresh

Scanning, backfill, face detection, videos

The files are huge, so instead of line-by-line, this is a concrete bug / risk list + improvement & refactor plan, with explicit places to touch and how.

1. High-level architecture / coupling issues
1.1. Two worlds: “Current” layout vs “Google” layout

Current layout uses:

MainWindow.grid (a ThumbnailGridQt)

MainWindow.sidebar (legacy sidebar)

SidebarController, PhotoOperationsController, ProjectController expect to talk to main.grid and main.sidebar directly.

Google layout (GooglePhotosLayout in layouts/google_layout.py) uses:

Its own internal AccordionSidebar instance (self.accordion_sidebar)

Its own central widgets & timeline

Scan / face detection / refresh hooks via LayoutManager and ScanController.

This is mostly wired correctly via layout_manager._current_layout_id == "google" checks in scan_controller.py and main_window_qt.py, but there are some sharp edges.

Risks / bugs

Project switching doesn’t know about Google layout

ProjectController.on_project_changed does:

pid = self.main.project_combo.itemData(idx)
...
if self.main.thumbnails:
    self.main.thumbnails.clear()
self.main.sidebar.set_project(pid)
self.main.grid.set_project(pid)


This updates only the legacy sidebar/grid, not the Google layout.

If the user is on the Google layout and changes the project via the combo, there’s no explicit call to something like layout_manager.set_project(pid) or current_layout.set_project(pid).

Depending on how LayoutManager is implemented, Google layout may continue to show old project data until a layout switch or a manual refresh method is called.

Plan to fix:

Introduce a small abstraction in MainWindow and centralize project switching:

def set_project_for_current_layout(self, project_id: int):
    # Legacy layout
    if self.layout_manager._current_layout_id == "current":
        self.sidebar.set_project(project_id)
        self.grid.set_project(project_id)
    # Google layout
    elif self.layout_manager._current_layout_id == "google":
        layout = self.layout_manager._current_layout
        if layout and hasattr(layout, "set_project"):
            layout.set_project(project_id)
        # also keep any shared state, e.g. self.grid.project_id, in sync if needed


Change ProjectController.on_project_changed to call that instead of poking at sidebar / grid directly.

Controllers are tied to MainWindow.grid

SidebarController, PhotoOperationsController assume a self.main.grid with set_branch, set_folder, get_selected_paths, apply_tag_filter, etc.

These are correct for the “Current” layout but not for GooglePhotosLayout, which has its own photo selection / navigation.

Plan to fix/improve:

Decide explicitly: Are controllers meant only for the “Current” layout?

If yes: enforce that – e.g. disable their actions in Google layout, or route their calls through LayoutManager and no-op when current_layout_id == "google".

If no: then define a layout interface (e.g. ILayout protocol) that exposes:

def get_selected_paths(self) -> list[str]: ...
def set_project(self, pid: int) -> None: ...
def set_branch(self, key: str) -> None: ...
def set_folder(self, folder_id: int) -> None: ...
...


Then have both ThumbnailGridQt and GooglePhotosLayout implement this, and have controllers call self.main.layout_manager.current_layout instead of self.main.grid.

2. accordion_sidebar.py audit
2.1. Threading & DB access

You use Python threads like:

def _load_people_section(self):
    ...
    def work():
        rows = self.db.get_face_clusters(self.project_id)
        return rows

    def on_complete():
        try:
            rows = work()
            self._peopleLoaded.emit(rows)
        except Exception as e:
            self._dbg(f"⚠️ Error in people thread: {e}")
            traceback.print_exc()

    threading.Thread(target=on_complete, daemon=True).start()


and connect signals with Qt.QueuedConnection:

self._peopleLoaded.connect(self._build_people_grid, Qt.QueuedConnection)


Good:

UI updates (_build_people_grid, _build_dates_tree, etc.) run in the main thread via signals.

DB reads happen in worker threads.

Risks:

self.db = ReferenceDB() is created in the UI thread and re-used from background threads.

Depending on the implementation of ReferenceDB / SQLite, this can be unsafe if check_same_thread=True or if the connection is not fully threadsafe.

Threads are spawned “fire-and-forget” with no ability to cancel / throttle. Rapid spam of reloads (e.g. fast project switching) can cause overlapping DB queries.

Fix / improvement plan:

Make DB usage explicitly thread-safe

In the worker, instantiate a local ReferenceDB:

def work():
    try:
        db = ReferenceDB()           # local instance in this thread
        rows = db.get_face_clusters(self.project_id)
        ...
        return rows
    except Exception as e:
        ...


Do this for all _load_*_section methods (dates, folders, tags, branches, quick, people, videos).

Add a simple reload token / generation guard

Store self._reload_generation and increment it on each reload.

Worker captures the generation and, when emitting results, drops them if they’re stale:

gen = self._reload_generation

def on_complete():
    ...
    if gen != self._reload_generation:
        return  # stale result; ignore
    self._peopleLoaded.emit(rows)


This prevents older threads from overwriting the UI after a newer reload.

Optional: move to QThreadPool

Replace raw threading.Thread with QRunnable / QThreadPool.globalInstance().

This gives you better control over concurrency and plays nicer with Qt.

2.2. reload_all_sections safety
def reload_all_sections(self):
    self._dbg("Reloading all sections...")
    for section_id in self.sections.keys():
        self._load_section_content(section_id)


Potential issue:

If _load_section_content ever modifies self.sections (e.g. adds/removes sections), iterating over .keys() directly could become unsafe.

Safer version:

for section_id in list(self.sections.keys()):
    self._load_section_content(section_id)


Also consider debouncing this method (e.g. don’t allow it to run more than once every X ms) if you call it aggressively after scans or project switches.

2.3. Video duration / categorization

You classify videos:

short_videos = [v for v in videos if v.get("duration_seconds") and v["duration_seconds"] < 30]
medium_videos = [v for v in videos if v.get("duration_seconds") and 30 <= v["duration_seconds"] < 300]
long_videos = [v for v in videos if v.get("duration_seconds") and v["duration_seconds"] >= 300]


In video_service.py, filter_by_duration_key explicitly comments that these ranges must match sidebar logic and uses the same duration_seconds field and ranges – you’re correctly aligned. 👍

Improvement:

Centralize this classification in VideoService and call it from the sidebar, rather than duplicating the ranges. That keeps future changes consistent.

2.4. UX / i18n / accessibility

Some strings in accordion_sidebar.py appear to be hard-coded text (English) instead of going through translation_manager.tr.

Navigation buttons / headers should set accessibleName / accessibleDescription for screen readers.

Tooltips are present, but you can standardize them via translation keys.

Plan:

Make a pass and wrap user-visible strings with tr('sidebar.xxx').

Add nav_btn.setAccessibleName(title) and similar properties for important widgets.

2.5. Code size & maintainability

accordion_sidebar.py is ~94k characters. It contains:

Flow layout implementation

People grid

Tags, folders, branches, dates, quick sections

Video section

Navigation bar, badges, etc.

Refactor plan:

Break it into modules under e.g. ui/accordion_sidebar/:

base.py – AccordionSidebar, common interfaces

sections/people.py – people grid logic

sections/dates.py

sections/folders.py

sections/tags.py

sections/quick.py

sections/videos.py

widgets/section.py – AccordionSection, SectionHeader, etc.

layouts/flow_layout.py – the reusable FlowLayout widget

This makes testing and future bugfixes much easier.

3. layouts/google_layout.py (GooglePhotosLayout) audit

Key parts:

class GooglePhotosLayout(BaseLayout)

_create_sidebar() → creates AccordionSidebar and wires its signals

_load_photos(...) and _load_videos(...) → timeline loading

_build_people_tree() → legacy people support

Mode switching (grid vs timeline), responsive column calculation, etc.

3.1. Sidebar integration

_create_sidebar:

from accordion_sidebar import AccordionSidebar

sidebar = AccordionSidebar(project_id=self.project_id, parent=None)
...
sidebar.selectBranch.connect(self._on_accordion_branch_clicked)
sidebar.selectFolder.connect(self._on_accordion_folder_clicked)
sidebar.selectDate.connect(self._on_accordion_date_clicked)
sidebar.selectTag.connect(self._on_accordion_tag_clicked)
sidebar.selectVideo.connect(self._on_accordion_video_clicked)  # NEW: Video filtering

self.accordion_sidebar = sidebar


Good:

Uses the new accordion sidebar.

Wires the correct selectVideo signal (singular) for videos.

Risks / improvements:

Parenting / lifetime

You create AccordionSidebar(..., parent=None) and then presumably insert it into your layout.

The visual parent is the layout’s container widget; but the QObject parent for lifetime management is still None unless you reparent it.

Safer:

Make the layout’s container widget the parent:

sidebar = AccordionSidebar(project_id=self.project_id, parent=self._sidebar_container)


or at least call sidebar.setParent(self._sidebar_container) right after creation.

Project changes

When project changes (see §1.1), you should propagate this to self.accordion_sidebar.project_id and reload its sections.

Plan:

Add a set_project(project_id:int) method on GooglePhotosLayout:

def set_project(self, project_id: int):
    self.project_id = project_id
    if hasattr(self, 'accordion_sidebar') and self.accordion_sidebar:
        self.accordion_sidebar.project_id = project_id
        self.accordion_sidebar.reload_all_sections()
    # also trigger a timeline reload
    self._load_photos()


Call this from ProjectController via MainWindow.set_project_for_current_layout() as discussed.

3.2. _load_photos / _load_videos DB logic

You’re doing fairly complex queries with dynamic WHERE clauses and combining photo and video timelines. I saw:

Month and day filters with “BUG FIX” comments adding strftime('%m', pm.created_date) and strftime('%d', ...).

Separate photo and video queries that are merged later.

Potential issues:

If created_date is NULL or missing for some rows, strftime will return NULL and the record is skipped. After a fresh scan but before backfill, this may make items invisible.

These queries appear to be synchronous and can be heavy on big DBs; they run in the GUI thread.

Plan:

Guarantee created_date before usage

You’re already backfilling created_date in scan_controller._cleanup_impl via:

backfilled = db.single_pass_backfill_created_fields()
video_backfilled = db.single_pass_backfill_created_fields_videos()


Ensure _load_photos is not called before that backfill finishes after a scan.

If there’s a chance that can happen, add a fallback inside _load_photos:

if not self._has_date_index_ready():
    # either trigger backfill or show a friendly "still processing" message


Move heavy DB work off the GUI thread

Similar to AccordionSidebar, create a worker (thread or QThreadPool) to run the timeline query, emit a signal with the grouped data, and then populate the UI in the main thread.

This is especially important given the Google layout’s goal of handling huge libraries.

Centralize timeline grouping

A lot of the date/bin grouping logic duplicates what the DB already does with build_date_branches.

Consider a service function like TimelineService.get_timeline(project_id, filters) and call it from _load_photos, rather than embedding raw SQL here.

3.3. _build_people_tree and AccordionSidebar overlap
def _build_people_tree(self):
    """
    ...
    NOTE: With AccordionSidebar, this is handled internally - this method is a no-op.
    """
    # Old sidebar implementation - no longer needed with AccordionSidebar
    if not hasattr(self, 'people_grid') and not hasattr(self, 'people_tree'):
        return

    print("[GooglePhotosLayout] 🔍 _build_people_tree() called")
    ...


The docstring claims it’s a no-op; the body is not a no-op – it still attempts to query the DB and build UI widgets if people_grid / people_tree exist.

scan_controller and main_window_qt still call _build_people_tree() in some face detection flows, and also refresh the AccordionSidebar/People section.

Plan:

Decide the source of truth for “People”:

If AccordionSidebar should own People 100%:

Either:

Completely stub _build_people_tree:

def _build_people_tree(self):
    # Kept for backwards compatibility – People UI is now in AccordionSidebar
    if hasattr(self, 'accordion_sidebar'):
        self.accordion_sidebar.reload_all_sections()  # or a targeted people reload


Or remove the old tree/grid widgets and all DB logic from this method.

If you still want a separate people pane in the Google layout content area:

Make sure _build_people_tree and AccordionSidebar don’t both load people data independently (wasted queries).

Factor the “get face clusters for project” logic into a service and share it.

4. Controllers & services
4.1. sidebar_controller.py

Behavior:

on_folder_selected → self.main.grid.set_folder(...), re-applies tag filter if active, reloads thumbnails.

on_branch_selected → self.main.grid.set_branch(...), scroll to top, reload thumbnails.

on_videos_selected → self.main.grid.set_videos(), reapply tag filter, reload thumbs.

Issues / improvements:

These controllers are properly isolated to self.main.grid; as noted, they don’t know about Google layout.

The get_visible_paths → ThumbnailManager.load_thumbnails(...) pattern is duplicated several times.

Plan:

Extract “apply tag filter + refresh thumbnails + scroll to top” into a helper method on MainWindow or ThumbnailGridQt.

Route these methods through LayoutManager if you later want them to work across layouts.

4.2. photo_operations_controller.py

Key operations:

Toggle favorite via tags (favorite)

Add tag via tag_service.assign_tags_bulk(...)

Export / move selection

Delete with PhotoDeletionService

Notes / improvements:

Strong coupling to self.main.grid selection.

Deletion UI:

msg = QMessageBox(self.main)
...
db_only_btn = msg.addButton("Database Only", ...)
db_and_files_btn = msg.addButton("Database && Files", ...)


Strings are hard-coded, not translated.

The “&& Files” label is slightly odd for non-technical users.

After deletion, you show a summary using numbers from result, which is good, but I’d also trigger a targeted refresh on the visible grid.

Plan:

Internationalize dialog text via translations.

Consider moving this logic into a reusable PhotoDeletionDialog widget.

Expose a layout-level method like current_layout.delete_photos(paths, delete_files) so the Google layout can unify the behavior.

4.3. project_controller.py

Already covered in §1.1.

4.4. scan_controller.py

This is central to how Google layout and AccordionSidebar get refreshed.

Key things it does after scan:

Shows a completion QMessageBox (now stored as self.main._scan_complete_msgbox).

Builds photo and video date branches:

branch_count = db.build_date_branches(current_project_id)
video_branch_count = db.build_video_date_branches(current_project_id)


Backfills created_date for photos and videos.

Optionally runs face detection & clustering with progress UI.

Refreshes:

Legacy sidebar (self.main.sidebar.reload() or reload_date_tree())

Google layout via:

if current_layout_id == "google":
    current_layout = self.main.layout_manager._current_layout
    if current_layout and hasattr(current_layout, '_load_photos'):
        QTimer.singleShot(500, current_layout._load_photos)


Refreshing Google people grid after face clustering:

if current_layout_id == "google" and hasattr(current_layout, '_build_people_tree'):
    current_layout._build_people_tree()


This is reasonably robust, but can be improved:

_current_layout is assumed truthy when _current_layout_id == "google". A race condition or a failed layout load could leave _current_layout as None.

Fix:

Guard all layout accesses carefully and log when _current_layout is missing.

The refresh logic for current layout after scan is scattered:

Date branches, backfill, sidebar reload, grid reload, Google layout reload, face detection, people grid refresh, etc.

Plan:

Define a layout callback API in LayoutManager:

class LayoutManager:
    def on_scan_completed(self, project_id: int): ...
    def on_face_clustering_completed(self, project_id: int): ...


Have each layout (Current & Google) implement these hooks, instead of having ScanController reach into their internals (_load_photos, _build_people_tree, accordion_sidebar.reload_all_sections()).

4.5. video_service.py

This looks pretty solid and well-documented:

Filtering by duration, resolution, codec, file size, date, combined criteria.

Duration ranges are explicitly synchronized with sidebar logic.

Lots of defensive guards for None / invalid values.

Singleton getter get_video_service().

Improvements:

Extract constant definitions (duration ranges, resolution presets, size presets) into a single place and reuse in both UI code and service.

Add small unit tests around filter_by_duration_key and filter_combined to ensure UI & service remain in sync.

4.6. main_window_qt.py

You already have:

Layout switching via _switch_layout(layout_id) and LayoutManager.

Menu wiring for layout actions, including the "Layout" menu and layout_action_group.

Scan, DB backfill, face grouping, etc., heavily refactored out to controllers and panels.

Important bits for this audit:

In __init__, after building toolbar and sidebar, you create controllers:

self.scan_controller = ScanController(self)
self.sidebar_controller = SidebarController(self)
self.project_controller = ProjectController(self)
self.photo_ops_controller = PhotoOperationsController(self)


Sidebar signals wired to SidebarController, and sidebar is added to self.splitter.

_switch_layout uses self.layout_manager.switch_layout(layout_id) and shows error message if it fails.

Plan:

Add a concept of “current layout object” at the MainWindow level:

@property
def current_layout(self):
    return getattr(self.layout_manager, "_current_layout", None)


Use that in controllers where appropriate (instead of accessing self.grid directly), once you define a common interface.

5. Suggested implementation roadmap

To make this manageable, I’d do it in phases.

Phase 1 – Safety & correctness

Thread-safe DB usage in AccordionSidebar:

Use per-thread ReferenceDB instances in all background workers.

Add reload generation tokens to prevent stale data overwriting the UI.

Guard all Google layout interactions in ScanController and MainWindow:

Check for _current_layout being non-None before calling _load_photos, _build_people_tree, or accordion_sidebar.reload_all_sections().

When layout switching fails, ensure you don’t keep stale pointers around.

Project switching integration across layouts:

Implement MainWindow.set_project_for_current_layout(project_id) and call it from ProjectController.

Add set_project to GooglePhotosLayout to sync project_id, AccordionSidebar.project_id, and reload data.

Clarify _build_people_tree semantics:

Decide: either fully delegate to AccordionSidebar or fully own a separate People UI.

Make the code match the docstring (if it’s supposed to be a no-op, make it one).

Phase 2 – Performance & UX

Move heavy timeline queries in GooglePhotosLayout off the GUI thread.

Debounce / throttle reload_all_sections and layout refreshes after scan.

Improve i18n & accessibility:

Replace hardcoded English strings with tr(...) in sidebar, Google layout, and controllers.

Add accessibility names/roles to key widgets in the AccordionSidebar and Google layout.

Phase 3 – Architecture & refactor

Define a layout interface / abstraction:

Formalize what Current layout and GooglePhotosLayout both need to support (e.g. set_project, get_selected_paths, refresh_after_scan, etc.).

Have LayoutManager hand out current_layout that conforms to that interface.

Split large modules:

Break accordion_sidebar.py into smaller submodules (sections, widgets, layout).

Split google_layout.py similarly (e.g. timeline, toolbar, media viewer).

Add tests for key behaviors:

Video duration classification vs sidebar buckets.

Timeline filters by date/year/month/day.

Project switching across layouts.

Scan completion hooks calling the right layout refresh methods.
