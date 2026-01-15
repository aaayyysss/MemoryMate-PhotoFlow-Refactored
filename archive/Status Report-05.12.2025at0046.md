Status Report — 05.12.2025 @ 00:46
Executive Summary
Badges and tag UX are implemented and stable in the Google layout.
Sidebar sections (Timeline, Folders, Tags, People, Videos) now show meaningful counts and render consistently during filters/search.
Date branches visibility issue addressed: date groups are created in sorted order and the sidebar tree keeps its branches intact when filtering.
Completed Work
Photo badges rendering
Implemented PhotoButton overlay painting via paintEvent with icons for common tags and fallback icon for custom tags.
Fixed QFont import error inside paintEvent.
Tag service alignment
Migrated tag operations to TagService (ensure_tag_exists, assign_tags_bulk, remove_tag, bulk get_tags_for_paths).
Verified project scoping and metadata reading consistency.
Tags section
Added tags_section and tags_tree with counts via TagService.get_all_tags_with_counts.
Clicking a tag filters the timeline with proper row format (path, date_taken, width, height).
Context menu enhancements
Added “➕ New Tag…” and “🗑️ Remove All Tags” to the thumbnail context menu.
Common tags show a checkmark (✓) when present; single-click toggles add/remove the tag.
Ensured overlays and tags section rebuild after any tag change.
Method alias
Restored _refresh_tag_overlays(...); added alias _refresh_tag_ovverlays(...) for backward compatibility.
Timeline & Sidebar
Only timeline elements are cleared during search/filter rebuilds; other sections remain visible.
Date groups render in sorted descending order to ensure “rest of the dates” are visible.
Virtual scrolling and lazy thumbnail loading active for performance.
Repository fix
Implemented PhotoRepository.get_by_id(...) to resolve path resolution errors in filtering flows.
Section Counts Behavior
Timeline: Count reflects the total number of photos currently loaded (project-scoped and filter-aware).
Folders: Count reflects the sum of photos across all folders built from current rows (top folders displayed; header shows the sum of all folder photo counts).
Tags: Count reflects the sum of per-tag counts returned by TagService.get_all_tags_with_counts.
People: Count reflects the sum of photo counts across face clusters (face_branch_reps), not just the number of clusters.
Videos: Count reflects the total number of video files in the project (based on extension filtering).
Note: For Tags and Folders, counts are summed per branch which can double-count photos that appear in multiple tags/folders. If you prefer unique totals (deduplicated), we can adjust those sections to compute distinct photo counts.
Notable Fixes Since Last Session
Sorted date group iteration to render all date branches in order.
Updated People header count after filters and reconstructions.
Updated Timeline and Videos header counts after row loads.
Updated Folders header count to the sum of all photos across folders.
Current UX/Behavior Highlights
Single-click tag toggling: Immediate apply/remove, checkmark state updates, badges refresh.
Remove All Tags: Bulk clear on a single photo; overlays and Tags section rebuild immediately.
Search & Filters:
Search suggestions (people, folders, filenames) and advanced filters (multi-person, count thresholds).
Person filters rebuild timeline while preserving sidebar context.
Tag filters return correctly formatted rows; date grouping, grid rendering, and lazy loading apply.
Known Issues / Watchouts
Deduplication of counts: Tags/Folders totals can double-count photos when a photo belongs to multiple branches. If unique totals are preferred, we need to change aggregation logic.
Large tag lists: If the tag list grows, the tags tree may benefit from pagination or search in the section.
People grid vs tree: The grid is primary; the old tree remains hidden for backward compatibility. Ensure newer flows don’t depend on the old tree.
Suggested Next Steps for Tomorrow
Counts preference: Decide whether section header counts should be deduplicated across branches (Tags, Folders). I can implement unique-count logic per your preference.
Tags context menu in sidebar: Optionally add “Remove All Tags” scoped to selected photo(s) or selected tag group (needs clear UX).
Favorites quick branch: If desired, add a dedicated quick filter under Tags to match your Favorites workflow, though the current route via Tags → favorite already works.
Performance pass: Verify lazy rendering thresholds and tuning for large libraries; adjust initial_render_count if needed.
i18n review: Ensure new labels/tooltips are localized via translation_manager.tr.
Quick Validation Checklist
Apply/remove a common tag via thumbnail context menu; check the ✓ state and badges refresh.
Use “🗑️ Remove All Tags” on a photo; confirm badges disappear and Tags section counts update.
Click a tag in the Tags section; confirm timeline rebuilds with date groups and sidebar branches stay visible.
Change zoom/aspect ratio; ensure timeline reloads and scroll position restores.
Switch to People tab; confirm the count reflects the sum of photo counts and grid shows expected faces.
Key Files touched
layouts/google_layout.py:
Context menu toggles with checkmarks, “➕ New Tag…”, “🗑️ Remove All Tags”.
_refresh_tag_overlays(...) and alias _refresh_tag_ovverlays(...).
Tags section build (_build_tags_tree).
People grid build (_build_people_tree), header count logic.
Folders tree build (_build_folders_tree), header count logic.
Timeline rebuild (_rebuild_timeline_with_results), sorted date iteration.
Photo loading (_load_photos), Timeline/Videos header count updates.
repository/photo_repository.py: Implemented get_by_id(...).
Impact
Badge overlays reflect current tags reliably.
Sidebar sections show meaningful counts and remain visible during filters.
Tag UX is consistent with single-click toggle behavior and checkmarks.
Filtering (tags, people, folders, favorites) produces stable, correctly grouped timeline output.