# ui/accordion_sidebar/people_section.py
# People section - face clusters with Groups tab
# Version: 2.0.0

"""
People Section with Individuals / Groups Tab Toggle

Structure (following Google Photos / Apple Photos / Lightroom pattern):
- People (accordion section header)
  - [Individuals] [Groups]  ← tab toggle (QStackedWidget)
  - Page 0: Individuals — existing face cluster grid
  - Page 1: Groups — reuses GroupsSection for content + signals
"""

import io
import logging
import os
import threading
import traceback
from typing import Optional, List, Dict

from PySide6.QtCore import Signal, Qt, QObject, QSize, QRect, QPoint, QEvent
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QWidget,
    QVBoxLayout,
    QLayout,
    QGridLayout,
    QSizePolicy,
    QToolButton,
    QLineEdit,
)
from shiboken6 import isValid

from reference_db import ReferenceDB
from translation_manager import tr
from services.people_merge_engine import PeopleMergeEngine
from repository.people_merge_review_repository import PeopleMergeReviewRepository
from .base_section import BaseSection

logger = logging.getLogger(__name__)


class PeopleSectionSignals(QObject):
    """Signals for async people loading."""

    loaded = Signal(int, list)  # (generation, face_rows)
    error = Signal(int, str)    # (generation, error_message)


class PeopleSection(BaseSection):
    """
    People section with Individuals / Groups tab toggle.

    Individuals tab: existing face cluster grid
    Groups tab: reuses GroupsSection content embedded via QStackedWidget
    """

    # Face cluster signals
    personSelected = Signal(str)  # person_branch_key
    contextMenuRequested = Signal(str, str)  # (branch_key, action)
    dragMergeRequested = Signal(str, str)  # (source_branch, target_branch)
    mergeHistoryRequested = Signal()
    undoMergeRequested = Signal()
    redoMergeRequested = Signal()
    peopleToolsRequested = Signal()

    # Groups tab signals (forwarded from embedded GroupsSection)
    groupSelected = Signal(int, str)       # (group_id, match_mode)
    newGroupRequested = Signal()
    editGroupRequested = Signal(int)       # group_id
    deleteGroupRequested = Signal(int)     # group_id
    recomputeGroupRequested = Signal(int, str)  # (group_id, match_mode)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = PeopleSectionSignals()
        self.signals.loaded.connect(self._on_data_loaded)
        self.signals.error.connect(self._on_error)

        # Keep a reference to rendered cards so selection state can be updated externally
        self._cards: Dict[str, "PersonCard"] = {}
        self._header_widget: Optional[QWidget] = None

        # Search/filter state
        self._all_data: List[Dict] = []  # Full list of people data
        self._search_text: str = ""
        self._count_label: Optional[QLabel] = None

        # Groups tab state
        self._groups_section = None      # GroupsSection instance (lazy)
        self._stack: Optional[QStackedWidget] = None
        self._btn_individuals = None
        self._btn_groups = None
        self._groups_loaded_once = False  # lazy-load on first tab switch

    def get_section_id(self) -> str:
        return "people"

    def get_title(self) -> str:
        return tr("sidebar.header_people") if callable(tr) else "People"

    def get_icon(self) -> str:
        return "👥"

    def get_header_widget(self) -> Optional[QWidget]:
        """Provide compact post-detection controls beside the section title."""
        if self._header_widget:
            return self._header_widget

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        def build_btn(emoji: str, tooltip_key: str, fallback: str, callback):
            btn = QToolButton()
            btn.setText(emoji)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setAutoRaise(True)
            btn.setFixedSize(26, 26)
            btn.setToolTip(tr(tooltip_key) if callable(tr) else fallback)
            btn.clicked.connect(callback)
            btn.setStyleSheet(
                """
                QToolButton {
                    border: 1px solid #dadce0;
                    border-radius: 6px;
                    background: #fff;
                }
                QToolButton:hover { background: #f1f3f4; }
                QToolButton:pressed { background: #e8f0fe; }
                """
            )
            layout.addWidget(btn)

        build_btn("🕑", "sidebar.people_actions.merge_history", "View Merge History", self.mergeHistoryRequested.emit)
        build_btn("↩️", "sidebar.people_actions.undo_last_merge", "Undo Last Merge", self.undoMergeRequested.emit)
        build_btn("↪️", "sidebar.people_actions.redo_last_undo", "Redo Last Undo", self.redoMergeRequested.emit)
        build_btn("🧰", "sidebar.people_actions.people_tools", "Open People Tools", self.peopleToolsRequested.emit)

        # FEATURE #2: Expand button to open full-screen people manager
        build_btn("⛶", "sidebar.people_actions.expand_view", "Expand to Full View", self._on_expand_clicked)

        self._header_widget = container
        return self._header_widget

    def _on_expand_clicked(self):
        """
        FEATURE #2: Open PeopleManagerDialog in maximized state for better face browsing.

        This provides a full-screen view of all detected faces, making it easier to:
        - Browse large numbers of faces
        - Perform multi-face merging
        - Name and organize people
        """
        try:
            from ui.people_manager_dialog import PeopleManagerDialog

            logger.info("[PeopleSection] Opening full-screen people manager")

            dialog = PeopleManagerDialog(self.project_id, parent=self.parent())
            dialog.showMaximized()  # Open in maximized state
            dialog.exec()

            # Refresh sidebar after dialog closes (in case faces were merged/renamed)
            logger.info("[PeopleSection] People manager closed, refreshing section")
            self.load_section()  # FIXED: Method is called load_section(), not load_data()

        except Exception as e:
            logger.error(f"[PeopleSection] Failed to open people manager: {e}")
            import traceback
            traceback.print_exc()

    def set_project(self, project_id: int) -> None:
        """Override to reset groups tab when project changes."""
        super().set_project(project_id)
        # Reset groups lazy-load flag so it reloads for new project
        self._groups_loaded_once = False
        if self._groups_section:
            self._groups_section.set_project(project_id)

    def load_section(self) -> None:
        """Load people section data in a background thread."""
        if not self.project_id:
            logger.warning("[PeopleSection] No project_id set")
            return

        self._generation += 1
        current_gen = self._generation
        self._loading = True

        logger.info(f"[PeopleSection] Loading face clusters (generation {current_gen})…")

        def work():
            db: Optional[ReferenceDB] = None
            try:
                db = ReferenceDB()
                rows = db.get_face_clusters(self.project_id) or []
                logger.info(f"[PeopleSection] Loaded {len(rows)} clusters (gen {current_gen})")
                return rows
            except Exception as e:
                logger.error(f"[PeopleSection] Error loading face clusters: {e}")
                traceback.print_exc()
                return []
            finally:
                if db:
                    try:
                        db.close()
                    except Exception:
                        pass

        def on_complete():
            try:
                rows = work()
                self.signals.loaded.emit(current_gen, rows)
            except Exception as e:
                logger.error(f"[PeopleSection] Error in worker thread: {e}")
                traceback.print_exc()
                self.signals.error.emit(current_gen, str(e))

        threading.Thread(target=on_complete, daemon=True).start()

    def create_content_widget(self, data):
        """Create tabbed layout: [Individuals] [Groups] with QStackedWidget."""
        rows: List[Dict] = data or []
        self._all_data = rows

        # Reset groups state so it reloads when tab is clicked after rebuild
        self._groups_loaded_once = False
        self._groups_section = None

        # ── Outer container ──
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ── Tab bar: [Individuals] [Groups] ──
        tab_bar = QWidget()
        tab_bar.setFixedHeight(36)
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(8, 4, 8, 0)
        tab_layout.setSpacing(0)

        _TAB_ACTIVE = (
            "QPushButton { border: none; border-bottom: 2px solid #1a73e8;"
            " color: #1a73e8; font-weight: 600; font-size: 10pt;"
            " padding: 4px 12px; background: transparent; }"
        )
        _TAB_INACTIVE = (
            "QPushButton { border: none; border-bottom: 2px solid transparent;"
            " color: #5f6368; font-size: 10pt;"
            " padding: 4px 12px; background: transparent; }"
            "QPushButton:hover { color: #202124; background: #f1f3f4;"
            " border-radius: 4px 4px 0 0; }"
        )

        btn_individuals = QPushButton("Individuals")
        btn_individuals.setCursor(Qt.PointingHandCursor)
        btn_individuals.setStyleSheet(_TAB_ACTIVE)

        btn_groups = QPushButton("Groups")
        btn_groups.setCursor(Qt.PointingHandCursor)
        btn_groups.setStyleSheet(_TAB_INACTIVE)

        tab_layout.addWidget(btn_individuals)
        tab_layout.addWidget(btn_groups)
        tab_layout.addStretch()
        outer_layout.addWidget(tab_bar)

        # ── Stacked content area ──
        stack = QStackedWidget()
        outer_layout.addWidget(stack, 1)

        # === Page 0: Individuals (face cluster grid) ===
        individuals_page = self._build_individuals_page(rows)
        stack.addWidget(individuals_page)  # index 0

        # === Page 1: Groups (lazy-loaded from GroupsSection) ===
        groups_placeholder = QWidget()  # will be replaced on first switch
        stack.addWidget(groups_placeholder)  # index 1

        # ── Tab switching logic ──
        def _switch_to_individuals():
            stack.setCurrentIndex(0)
            btn_individuals.setStyleSheet(_TAB_ACTIVE)
            btn_groups.setStyleSheet(_TAB_INACTIVE)

        def _switch_to_groups():
            stack.setCurrentIndex(1)
            btn_groups.setStyleSheet(_TAB_ACTIVE)
            btn_individuals.setStyleSheet(_TAB_INACTIVE)
            # Lazy-load groups on first switch
            self._ensure_groups_tab(stack)

        btn_individuals.clicked.connect(_switch_to_individuals)
        btn_groups.clicked.connect(_switch_to_groups)

        # Store references
        self._stack = stack
        self._btn_individuals = btn_individuals
        self._btn_groups = btn_groups
        # Keep strong refs to prevent GC of closures
        self._tab_switch_individuals = _switch_to_individuals
        self._tab_switch_groups = _switch_to_groups

        logger.info(f"[PeopleSection] Grid built with {len(self._cards)} people + Groups tab")
        return outer

    def _build_individuals_page(self, rows: List[Dict]) -> QWidget:
        """Build the Individuals page (existing face grid)."""
        # Always reset cache to prevent stale card references
        self._cards.clear()

        if not rows:
            placeholder = QLabel(
                tr("sidebar.people.empty") if callable(tr)
                else "No people detected yet"
            )
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("padding: 16px; color: #666;")
            return placeholder

        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Search bar with count
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)

        search_input = QLineEdit()
        search_input.setPlaceholderText("Search people...")
        search_input.setClearButtonEnabled(True)
        search_input.setStyleSheet("""
            QLineEdit {
                padding: 6px 10px;
                border: 1px solid #dadce0;
                border-radius: 6px;
                background: #fff;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 1px solid #1a73e8;
            }
        """)
        search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(search_input, 1)

        self._count_label = QLabel(f"{len(rows)} people")
        self._count_label.setStyleSheet("color: #5f6368; font-size: 9pt; padding: 4px;")
        search_layout.addWidget(self._count_label)

        main_layout.addWidget(search_container)

        # Scroll area for people grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        cards: List[PersonCard] = []

        for idx, row in enumerate(rows):
            try:
                branch_key = row.get("branch_key") or f"cluster_{idx}"
                display_name = row.get("display_name") or f"Person {idx + 1}"
                member_count = int(row.get("member_count") or 0)
                rep_path = row.get("rep_path")
                rep_thumb = row.get("rep_thumb_png")

                pixmap = self._load_face_thumbnail(rep_path, rep_thumb)
                card = PersonCard(branch_key, display_name, member_count, pixmap)

                card.clicked.connect(self.personSelected.emit)
                card.context_menu_requested.connect(self.contextMenuRequested.emit)
                card.drag_merge_requested.connect(self.dragMergeRequested.emit)

                cards.append(card)
                self._cards[branch_key] = card
            except Exception as card_err:
                logger.error(
                    f"[PeopleSection] Failed to create card {idx+1}: {card_err}",
                    exc_info=True,
                )

        container = PeopleGrid(cards)
        container.attach_viewport(scroll.viewport())
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        return main_container

    def _ensure_groups_tab(self, stack: QStackedWidget):
        """Lazy-create and load the Groups tab content on first switch.

        Also detects stale groups (e.g. after face merge cleared their
        matches) and emits recomputeGroupRequested so the AccordionSidebar
        auto-recomputes them in the background — following the Apple Photos
        / Lightroom pattern where opening an album triggers a background
        refresh if the cache is outdated.
        """
        if self._groups_loaded_once:
            return

        self._groups_loaded_once = True

        try:
            from .groups_section import GroupsSection

            gs = GroupsSection(self.parent())
            gs.set_project(self.project_id)
            if hasattr(gs, 'set_db') and hasattr(self, '_parent_db'):
                gs.set_db(self._parent_db)

            # Forward GroupsSection signals through PeopleSection
            gs.groupSelected.connect(self.groupSelected.emit)
            gs.newGroupRequested.connect(self.newGroupRequested.emit)
            gs.editGroupRequested.connect(self.editGroupRequested.emit)
            gs.deleteGroupRequested.connect(self.deleteGroupRequested.emit)
            gs.recomputeRequested.connect(self.recomputeGroupRequested.emit)

            self._groups_section = gs

            # Trigger data load; when loaded, build content and swap into stack
            def on_groups_loaded(gen, data):
                try:
                    # Discard stale results (e.g. rapid project switches)
                    if gen != gs._generation:
                        return
                    content = gs.create_content_widget(data)
                    if content:
                        old = stack.widget(1)
                        stack.removeWidget(old)
                        old.deleteLater()
                        stack.insertWidget(1, content)
                        stack.setCurrentIndex(1)

                    # Auto-recompute stale groups in background, but only once
                    # per group per session.  Without the _recomputed set guard,
                    # a group with legitimately 0 matches would stay "stale" and
                    # trigger an infinite loop: compute → 0 → reload → stale →
                    # compute → 0 → ...
                    if data:
                        if not hasattr(self, '_recomputed_group_ids'):
                            self._recomputed_group_ids = set()
                        stale_ids = [
                            g['id'] for g in data
                            if g.get('is_stale') and g.get('member_count', 0) >= 2
                            and g['id'] not in self._recomputed_group_ids
                        ]
                        if stale_ids:
                            logger.info(
                                f"[PeopleSection] Auto-recomputing {len(stale_ids)} "
                                f"stale group(s): {stale_ids}"
                            )
                            for gid in stale_ids:
                                self._recomputed_group_ids.add(gid)
                                self.recomputeGroupRequested.emit(gid, "together")
                except Exception as e:
                    logger.error(f"[PeopleSection] Failed to build groups content: {e}", exc_info=True)

            gs.signals.loaded.connect(on_groups_loaded)
            gs.load_section()

            logger.info("[PeopleSection] Groups tab lazy-loaded")
        except Exception as e:
            logger.error(f"[PeopleSection] Failed to create groups tab: {e}", exc_info=True)

    def reload_groups(self):
        """Public method to reload Groups tab content.

        Reuses the existing GroupsSection instance to avoid duplicate
        signal connections and memory leaks.  Only falls back to full
        lazy-init if no GroupsSection has been created yet.
        """
        if self._groups_section and self._stack:
            # Reuse existing GroupsSection – just re-trigger its data load.
            # The on_groups_loaded closure from _ensure_groups_tab still holds
            # the correct stack/gs references, so new data will replace the
            # widget at index 1 automatically.
            self._groups_section.load_section()
        elif self._stack:
            # Groups tab was never opened; do the full lazy-init.
            # Reset recompute tracking so stale groups are recomputed.
            self._groups_loaded_once = False
            if hasattr(self, '_recomputed_group_ids'):
                self._recomputed_group_ids.clear()
            self._ensure_groups_tab(self._stack)

    def _get_merge_review_repo(self):
        """UX-9A: get persistent merge review repository."""
        try:
            db = getattr(self, "_parent_db", None)
            if db is None:
                return None
            with db._connect() as conn:
                return PeopleMergeReviewRepository(conn)
        except Exception:
            return None

    def get_people_quick_payload(self):
        """
        UX-8A adapter for the centralized search shell.
        Returns:
        - top identities
        - suspicious merge-review count
        - unnamed cluster count
        """
        try:
            payload = {
                "top_people": [],
                "merge_candidates": 0,
                "unnamed_count": 0,
            }

            source = getattr(self, "_all_data", None) or getattr(self, "people_data", None) or getattr(self, "clusters", None) or []

            unnamed_count = 0
            top_people = []

            for item in list(source):
                if not isinstance(item, dict):
                    continue

                pid = item.get("branch_key") or item.get("id") or item.get("person_id") or item.get("label")
                label = item.get("display_name") or item.get("label") or item.get("name") or str(pid)
                count = int(item.get("member_count", 0) or item.get("count", 0))

                if label.lower().startswith("face_") or "unnamed" in label.lower():
                    unnamed_count += 1

                if pid is not None:
                    top_people.append({
                        "id": str(pid),
                        "label": str(label),
                        "count": count,
                    })

            top_people = sorted(top_people, key=lambda x: x.get("count", 0), reverse=True)
            payload["top_people"] = top_people[:8]
            payload["unnamed_count"] = unnamed_count

            # Lightweight merge candidate heuristic
            merge_candidates = 0
            counts = [x.get("count", 0) for x in top_people[:20]]
            if len(counts) >= 2:
                merge_candidates = len([c for c in counts if c <= 3])

            payload["merge_candidates"] = merge_candidates
            return payload

        except Exception:
            return {
                "top_people": [],
                "merge_candidates": 0,
                "unnamed_count": 0,
            }

    def get_merge_suggestions(self):
        """
        UX-9A merge suggestions backed by PeopleMergeEngine
        and persistent accept/reject review state.
        """
        try:
            import numpy as np

            db = getattr(self, "_parent_db", None)
            pid = getattr(self, "project_id", None)
            if not db or not pid:
                return []

            reps = db.get_face_branch_reps(pid)
            if not reps or len(reps) < 2:
                return []

            clusters = []
            for r in reps:
                centroid = None
                centroid_bytes = r.get("centroid_bytes")
                if centroid_bytes:
                    try:
                        centroid = np.frombuffer(centroid_bytes, dtype=np.float32).tolist()
                    except Exception:
                        pass

                cid = str(r.get("id", r.get("branch_key", "")))
                label = str(r.get("name", r.get("label", cid)))
                count = int(r.get("count", 0))

                clusters.append({
                    "id": cid,
                    "label": label,
                    "count": count,
                    "centroid": centroid,
                    "unnamed": bool(
                        label.lower().startswith("face_")
                        or "unnamed" in label.lower()
                    ),
                })

            repo = self._get_merge_review_repo()
            accepted_pairs = repo.get_pairs_by_decision("accepted") if repo else set()
            rejected_pairs = repo.get_pairs_by_decision("rejected") if repo else set()

            engine = PeopleMergeEngine()
            return engine.build_merge_suggestions(
                clusters=clusters,
                accepted_pairs=accepted_pairs,
                rejected_pairs=rejected_pairs,
            )

        except Exception:
            logger.debug("[PeopleSection] get_merge_suggestions error", exc_info=True)
            return []

    def get_merge_review_payload(self):
        """
        UX-9B merge intelligence payload with previews and reasons
        for the PersonComparisonDialog side-by-side review.
        """
        try:
            import numpy as np

            db = getattr(self, "_parent_db", None)
            pid = getattr(self, "project_id", None)
            if not db or not pid:
                return {"suggestions": []}

            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT branch_key, label, count, centroid, rep_path, rep_thumb_png
                    FROM face_branch_reps
                    WHERE project_id = ?
                      AND centroid IS NOT NULL
                """, (pid,))
                rows = cur.fetchall() or []

            clusters = []
            for row in rows:
                branch_key, label, count, centroid_blob, rep_path, rep_thumb = row
                try:
                    centroid = np.frombuffer(centroid_blob, dtype=np.float32)
                    clusters.append({
                        "id": str(branch_key),
                        "label": str(label or branch_key),
                        "count": int(count or 0),
                        "centroid": centroid,
                        "rep_path": rep_path,
                        "rep_thumb": rep_thumb,
                    })
                except Exception:
                    continue

            # Load prior decisions to filter already-reviewed pairs
            prior = set()
            try:
                reviews = db.get_people_merge_reviews()
                prior = set(reviews.keys())
            except Exception:
                pass

            suggestions = []
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    left = clusters[i]
                    right = clusters[j]

                    if left["id"] == right["id"]:
                        continue

                    pair_key = tuple(sorted((left["id"], right["id"])))
                    if pair_key in prior:
                        continue

                    if left["count"] > 80 and right["count"] > 80:
                        continue

                    denom = np.linalg.norm(left["centroid"]) * np.linalg.norm(right["centroid"])
                    if denom == 0:
                        continue

                    sim = float(np.dot(left["centroid"], right["centroid"]) / denom)
                    if sim < 0.72:
                        continue

                    reason = []
                    if sim >= 0.90:
                        reason.append("very high centroid similarity")
                    elif sim >= 0.82:
                        reason.append("high centroid similarity")
                    else:
                        reason.append("moderate centroid similarity")

                    if left["count"] <= 3 or right["count"] <= 3:
                        reason.append("one cluster is very small")

                    suggestions.append({
                        "left_id": left["id"],
                        "right_id": right["id"],
                        "left_label": left["label"],
                        "right_label": right["label"],
                        "left_count": left["count"],
                        "right_count": right["count"],
                        "left_preview_paths": [left["rep_path"]] if left["rep_path"] else [],
                        "right_preview_paths": [right["rep_path"]] if right["rep_path"] else [],
                        "left_preview_thumbs": [left["rep_thumb"]] if left["rep_thumb"] else [],
                        "right_preview_thumbs": [right["rep_thumb"]] if right["rep_thumb"] else [],
                        "score": sim,
                        "reason": ", ".join(reason),
                    })

            suggestions.sort(key=lambda x: x["score"], reverse=True)
            return {"suggestions": suggestions[:20]}

        except Exception:
            logger.debug("[PeopleSection] get_merge_review_payload error", exc_info=True)
            return {"suggestions": []}

    def get_unnamed_review_payload(self):
        """
        UX-9C: Returns unnamed / generic clusters for review.
        """
        try:
            db = getattr(self, "_parent_db", None)
            pid = getattr(self, "project_id", None)
            if not db or not pid:
                return {"unnamed_items": []}

            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT branch_key, label, count, rep_path, rep_thumb_png
                    FROM face_branch_reps
                    WHERE project_id = ?
                    ORDER BY count DESC
                """, (pid,))
                rows = cur.fetchall() or []

            items = []
            for row in rows:
                branch_key, label, count, rep_path, rep_thumb = row
                label_str = str(label or branch_key)
                if label_str.lower().startswith("face_") or "unnamed" in label_str.lower():
                    items.append({
                        "id": str(branch_key),
                        "label": label_str,
                        "count": int(count or 0),
                        "rep_path": rep_path,
                        "rep_thumb": rep_thumb,
                    })

            return {"unnamed_items": items[:30]}

        except Exception:
            logger.debug("[PeopleSection] get_unnamed_review_payload error", exc_info=True)
            return {"unnamed_items": []}

    def _ensure_audit_table(self, conn):
        """Ensure the face_merge_review_log audit table exists."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS face_merge_review_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                left_branch TEXT,
                right_branch TEXT,
                decision TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def accept_merge_suggestion(self, left_id: str, right_id: str):
        """UX-9A: accept merge — persist decision, write audit trail, execute cluster merge."""
        db = getattr(self, "_parent_db", None)
        pid = getattr(self, "project_id", None)
        logger.info("[PeopleSection] Accept merge: %s + %s", left_id, right_id)

        try:
            repo = self._get_merge_review_repo()
            if repo:
                repo.accept(left_id, right_id)
        except Exception:
            logger.warning("[PeopleSection] Failed to persist merge acceptance", exc_info=True)

        # Legacy audit trail
        if db:
            try:
                with db._connect() as conn:
                    self._ensure_audit_table(conn)
                    conn.execute("""
                        INSERT INTO face_merge_review_log (project_id, left_branch, right_branch, decision)
                        VALUES (?, ?, ?, ?)
                    """, (pid, left_id, right_id, "accepted"))
            except Exception:
                logger.debug("[PeopleSection] Audit trail write failed", exc_info=True)

            if pid:
                try:
                    db.merge_face_clusters(pid, target_branch=left_id, source_branches=[right_id])
                    logger.info("[PeopleSection] Clusters merged: %s <- %s", left_id, right_id)
                except Exception:
                    logger.warning("[PeopleSection] merge_face_clusters failed", exc_info=True)

    def reject_merge_suggestion(self, left_id: str, right_id: str):
        """UX-9A: reject merge — persist rejection so pair is excluded from future suggestions."""
        db = getattr(self, "_parent_db", None)
        pid = getattr(self, "project_id", None)
        logger.info("[PeopleSection] Reject merge: %s / %s", left_id, right_id)

        try:
            repo = self._get_merge_review_repo()
            if repo:
                repo.reject(left_id, right_id)
        except Exception:
            logger.warning("[PeopleSection] Failed to persist merge rejection", exc_info=True)

        # Legacy audit trail
        if db:
            try:
                with db._connect() as conn:
                    self._ensure_audit_table(conn)
                    conn.execute("""
                        INSERT INTO face_merge_review_log (project_id, left_branch, right_branch, decision)
                        VALUES (?, ?, ?, ?)
                    """, (pid, left_id, right_id, "rejected"))
            except Exception:
                logger.debug("[PeopleSection] Audit trail write failed", exc_info=True)

    def get_unnamed_cluster_payloads(self):
        """
        UX-10C: build structured payloads for unnamed-cluster review dialog,
        including candidate named people for assignment.
        """
        try:
            db = getattr(self, "_parent_db", None)
            pid = getattr(self, "project_id", None)
            if not db or not pid:
                return []

            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT branch_key, label, count, rep_path, rep_thumb_png
                    FROM face_branch_reps
                    WHERE project_id = ?
                    ORDER BY count DESC
                """, (pid,))
                rows = cur.fetchall() or []

            named_candidates = []
            unnamed_clusters = []

            for row in rows:
                branch_key, label, count, rep_path, rep_thumb = row
                label_str = str(label or branch_key)
                entry = {
                    "id": str(branch_key),
                    "label": label_str,
                    "count": int(count or 0),
                    "rep_path": rep_path,
                }
                if label_str.lower().startswith("face_") or "unnamed" in label_str.lower():
                    unnamed_clusters.append(entry)
                else:
                    named_candidates.append(entry)

            named_candidates = sorted(named_candidates, key=lambda x: x["count"], reverse=True)[:10]

            payloads = []
            for cluster in unnamed_clusters[:12]:
                payloads.append({
                    "cluster_id": cluster["id"],
                    "label": f"Unnamed Cluster {cluster['id']}",
                    "samples": [cluster.get("rep_path", cluster["id"])],
                    "candidate_people": named_candidates,
                })

            return payloads

        except Exception:
            logger.debug("[PeopleSection] get_unnamed_cluster_payloads error", exc_info=True)
            return []

    def assign_unnamed_cluster(self, cluster_id: str, target_person_id: str):
        """UX-10C: merge unnamed cluster into a named person via face_clusters merge."""
        db = getattr(self, "_parent_db", None)
        pid = getattr(self, "project_id", None)
        logger.info("[PeopleSection] Assign unnamed %s -> %s", cluster_id, target_person_id)

        if db and pid:
            try:
                db.merge_face_clusters(pid, target_branch=target_person_id, source_branches=[cluster_id])
                logger.info("[PeopleSection] Unnamed cluster assigned: %s -> %s", cluster_id, target_person_id)
            except Exception:
                logger.warning("[PeopleSection] assign_unnamed_cluster failed", exc_info=True)

            try:
                db.save_people_merge_review(cluster_id, target_person_id, "assigned")
            except Exception:
                pass

    def keep_unnamed_cluster_separate(self, cluster_id: str):
        """UX-10C: mark unnamed cluster as intentionally separate."""
        db = getattr(self, "_parent_db", None)
        logger.info("[PeopleSection] Keep unnamed separate: %s", cluster_id)

        if db:
            try:
                db.save_people_merge_review(cluster_id, "__separate__", "keep_separate")
            except Exception:
                pass

    def ignore_unnamed_cluster(self, cluster_id: str):
        """UX-10C: ignore unnamed cluster for now (skip in future reviews)."""
        db = getattr(self, "_parent_db", None)
        logger.info("[PeopleSection] Ignore unnamed: %s", cluster_id)

        if db:
            try:
                db.save_people_merge_review(cluster_id, "__ignored__", "ignored")
            except Exception:
                pass

    def get_unnamed_cluster_items(self):
        """UX-9C adapter: return unnamed cluster items as simple dicts."""
        try:
            source = getattr(self, "people_data", None) or getattr(self, "clusters", None) or []
            items = []
            for item in list(source):
                if not isinstance(item, dict):
                    continue
                pid = item.get("id") or item.get("person_id") or item.get("label")
                label = item.get("label") or item.get("name") or str(pid)
                count = int(item.get("count", 0))
                if label.lower().startswith("face_") or "unnamed" in label.lower():
                    items.append({"id": str(pid), "label": str(label), "count": count})
            return sorted(items, key=lambda x: x["count"], reverse=True)[:20]
        except Exception:
            return []

    def get_unnamed_clusters(self):
        """UX-9A: return unnamed/generic clusters for review."""
        try:
            source = (
                getattr(self, "_all_data", None)
                or getattr(self, "people_data", None)
                or getattr(self, "clusters", None)
                or []
            )
            unnamed = []

            for item in list(source):
                if not isinstance(item, dict):
                    continue

                cid = (
                    item.get("branch_key")
                    or item.get("id")
                    or item.get("person_id")
                    or item.get("label")
                )
                label = (
                    item.get("display_name")
                    or item.get("label")
                    or item.get("name")
                    or str(cid)
                )
                count = int(item.get("member_count", 0) or item.get("count", 0))

                if str(label).lower().startswith("face_") or "unnamed" in str(label).lower():
                    unnamed.append({
                        "id": str(cid),
                        "label": str(label),
                        "count": count,
                    })

            unnamed.sort(key=lambda x: x["count"], reverse=True)
            return unnamed

        except Exception:
            return []

    def mark_unnamed_cluster_distinct(self, cluster_id: str):
        """UX-9C stub: mark unnamed cluster as a distinct person."""
        logger.info("[PeopleSection] Mark unnamed cluster distinct: %s", cluster_id)
        db = getattr(self, "_parent_db", None)
        if db:
            try:
                db.save_people_merge_review(cluster_id, "__distinct__", "distinct")
            except Exception:
                pass

    def assign_unnamed_cluster_to_person(self, cluster_id: str, target_person_id: str):
        """UX-9C stub: assign unnamed cluster to a named person."""
        logger.info("[PeopleSection] Assign unnamed cluster %s -> %s", cluster_id, target_person_id)
        self.assign_unnamed_cluster(cluster_id, target_person_id)

    def set_db(self, db):
        """Store DB reference for passing to GroupsSection."""
        self._parent_db = db

    # --- Search/Filter helpers ---
    def _on_search_changed(self, text: str):
        """Filter people cards based on search text."""
        self._search_text = text.strip().lower()
        visible_count = 0

        # Filter cards by display name
        for branch_key, card in self._cards.items():
            display_name = card.display_name.lower()
            is_match = self._search_text in display_name if self._search_text else True

            # Show/hide card based on match
            if isValid(card):
                card.setVisible(is_match)
                if is_match:
                    visible_count += 1

        # Update count label
        if self._count_label and isValid(self._count_label):
            total_count = len(self._cards)
            if self._search_text:
                self._count_label.setText(f"{visible_count} of {total_count} people")
            else:
                self._count_label.setText(f"{total_count} people")

        logger.debug(f"[PeopleSection] Search: '{text}' → {visible_count}/{len(self._cards)} visible")

    # --- Selection helpers ---
    def set_active_branch(self, branch_key: Optional[str]) -> None:
        """Highlight the active person card for visual feedback in the sidebar."""
        try:
            for key, card in self._cards.items():
                is_active = branch_key is not None and key == branch_key
                card.setProperty("selected", is_active)
                card.style().unpolish(card)
                card.style().polish(card)
        except Exception:
            logger.debug("[PeopleSection] Failed to update active state", exc_info=True)

    def _load_face_thumbnail(self, rep_path: Optional[str], rep_thumb_png: Optional[bytes]) -> Optional[QPixmap]:
        """Load a face thumbnail from BLOB or file path with robust error handling."""
        try:
            FACE_ICON_SIZE = 48

            # Try BLOB first (faster)
            if rep_thumb_png:
                try:
                    logger.debug(f"[PeopleSection] Loading thumbnail from BLOB ({len(rep_thumb_png)} bytes)")
                    image_data = io.BytesIO(rep_thumb_png)
                    from PIL import Image

                    with Image.open(image_data) as img:
                        # CRITICAL: Ensure RGB mode before Qt conversion (prevents crashes)
                        img_rgb = img.convert("RGB")

                        # Validate image dimensions
                        if img_rgb.width <= 0 or img_rgb.height <= 0:
                            logger.warning(f"[PeopleSection] Invalid BLOB image dimensions: {img_rgb.width}x{img_rgb.height}")
                            raise ValueError("Invalid image dimensions")

                        # Convert to bytes
                        data = img_rgb.tobytes("raw", "RGB")

                        # DEFENSIVE: Create QImage with explicit format
                        # .copy() ensures pixel data is owned by QImage (data buffer may be GC'd)
                        qimg = QImage(data, img_rgb.width, img_rgb.height, img_rgb.width * 3, QImage.Format_RGB888).copy()

                        if qimg.isNull():
                            logger.warning(f"[PeopleSection] QImage.isNull() == True for BLOB thumbnail")
                            raise ValueError("QImage is null")

                        # Create QPixmap and scale
                        pixmap = QPixmap.fromImage(qimg)
                        if pixmap.isNull():
                            logger.warning(f"[PeopleSection] QPixmap.isNull() == True for BLOB thumbnail")
                            raise ValueError("QPixmap is null")

                        return pixmap.scaled(
                            FACE_ICON_SIZE, FACE_ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                except Exception as blob_error:
                    logger.warning(f"[PeopleSection] Failed to load thumbnail from BLOB: {blob_error}", exc_info=True)

            # Try file path
            if rep_path and os.path.exists(rep_path):
                try:
                    logger.debug(f"[PeopleSection] Loading thumbnail from file: {os.path.basename(rep_path)}")
                    from PIL import Image

                    with Image.open(rep_path) as img:
                        # CRITICAL: Ensure RGB mode before Qt conversion (prevents crashes from DNG/RAW files)
                        img_rgb = img.convert("RGB")

                        # Validate image dimensions
                        if img_rgb.width <= 0 or img_rgb.height <= 0:
                            logger.warning(f"[PeopleSection] Invalid file image dimensions: {img_rgb.width}x{img_rgb.height} for {rep_path}")
                            raise ValueError("Invalid image dimensions")

                        # DEFENSIVE: Validate image size isn't too large (prevent memory issues)
                        max_pixels = 10000 * 10000  # 10k x 10k max
                        if img_rgb.width * img_rgb.height > max_pixels:
                            logger.warning(f"[PeopleSection] Image too large: {img_rgb.width}x{img_rgb.height} for {rep_path}")
                            # Resize before converting to bytes
                            img_rgb.thumbnail((2000, 2000), Image.Resampling.LANCZOS)

                        # Convert to bytes
                        data = img_rgb.tobytes("raw", "RGB")

                        # DEFENSIVE: Create QImage with explicit stride
                        # .copy() ensures pixel data is owned by QImage (data buffer may be GC'd)
                        stride = img_rgb.width * 3
                        qimg = QImage(data, img_rgb.width, img_rgb.height, stride, QImage.Format_RGB888).copy()

                        if qimg.isNull():
                            logger.warning(f"[PeopleSection] QImage.isNull() == True for {rep_path}")
                            raise ValueError("QImage is null")

                        # Create QPixmap and scale
                        pixmap = QPixmap.fromImage(qimg)
                        if pixmap.isNull():
                            logger.warning(f"[PeopleSection] QPixmap.isNull() == True for {rep_path}")
                            raise ValueError("QPixmap is null")

                        logger.debug(f"[PeopleSection] ✓ Successfully loaded thumbnail from {os.path.basename(rep_path)}")
                        return pixmap.scaled(
                            FACE_ICON_SIZE, FACE_ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                except Exception as file_error:
                    logger.error(f"[PeopleSection] Failed to load thumbnail from {rep_path}: {file_error}", exc_info=True)

            # Fallback: No thumbnail available
            logger.debug(f"[PeopleSection] No thumbnail available (rep_path={rep_path}, has_blob={bool(rep_thumb_png)})")
            return None

        except Exception as e:
            logger.error(f"[PeopleSection] Unexpected error in _load_face_thumbnail: {e}", exc_info=True)
            return None

    def _on_data_loaded(self, generation: int, data: list):
        """Internal callback when face cluster data is loaded."""
        self._loading = False

        if generation != self._generation:
            logger.debug(f"[PeopleSection] Discarding stale data (gen {generation} vs {self._generation})")
            return

        # Patch D: Strengthen UI consistency by ensuring freshly loaded data is stored and audited.
        # This replaces any stale/partial results from earlier runs.
        self._all_data = list(data or [])

        logger.info(
            "[PEOPLE_UI] loaded=%d clusters (gen %d)",
            len(self._all_data), generation
        )

        # Mismatch guard: if the rendered cards don't match the new data, log a warning.
        # This helps detect cases where create_content_widget wasn't called after load.
        if hasattr(self, "_cards") and len(self._cards) > 0 and len(self._cards) != len(self._all_data):
             # Only log if we have data (empty grid -> empty data is normal)
             if len(self._all_data) > 0:
                 logger.warning("[PEOPLE_UI_MISMATCH] cards=%d data=%d", len(self._cards), len(self._all_data))

        # Note: AccordionSidebar._on_section_loaded also listens to this signal
        # to trigger the UI rebuild. This override is for logging and state reset.
        logger.info(f"[PeopleSection] Data load confirmed: {len(data)} clusters at generation {generation}")

    def _on_error(self, generation: int, message: str):
        """Handle loading errors."""
        self._loading = False
        if generation != self._generation:
            return
        logger.error(f"[PeopleSection] Load error: {message}")

class FlowLayout(QLayout):
    """Simple flow layout for wrapping person cards across rows."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = -1):
        super().__init__(parent)
        self.itemList = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing if spacing >= 0 else 6)

    def addItem(self, item):
        self.itemList.append(item)

    def addWidget(self, widget):
        super().addWidget(widget)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x, y = rect.x(), rect.y()
        line_height = 0
        spacing = self.spacing()
        for item in self.itemList:
            widget = item.widget()
            if not widget:
                continue

            next_x = x + item.sizeHint().width() + spacing
            if next_x - spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + spacing
                next_x = x + item.sizeHint().width() + spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()


class PeopleGrid(QWidget):
    """Grid that automatically recalculates columns based on available width."""

    def __init__(self, cards: List["PersonCard"], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.cards = cards
        self._card_width = cards[0].sizeHint().width() if cards else 96
        self._columns = 0
        self._viewport = None
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setHorizontalSpacing(10)
        self._layout.setVerticalSpacing(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._relayout(force=True)

    def attach_viewport(self, viewport: QWidget) -> None:
        """Track the scroll viewport so column count follows sidebar width."""
        if not viewport:
            return
        self._viewport = viewport
        viewport.installEventFilter(self)
        self._relayout(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def eventFilter(self, obj, event):
        if obj is self._viewport and event.type() == QEvent.Resize:
            self._relayout(force=True)
        return super().eventFilter(obj, event)

    def _relayout(self, force: bool = False):
        margins = self._layout.contentsMargins()
        base_width = self._viewport.width() if self._viewport else self.width()
        available_width = max(base_width - margins.left() - margins.right(), 0)
        spacing = self._layout.horizontalSpacing() or 0
        columns = max(1, int(available_width / (self._card_width + spacing)) if (self._card_width + spacing) > 0 else 1)

        if not force and columns == self._columns:
            return

        self._columns = columns

        # Clear existing layout positions without deleting widgets
        while self._layout.count():
            self._layout.takeAt(0)

        for idx, card in enumerate(self.cards):
            row = idx // columns
            col = idx % columns
            self._layout.addWidget(card, row, col)


class PersonCard(QWidget):
    """Compact face card with circular thumbnail and counts."""

    clicked = Signal(str)
    context_menu_requested = Signal(str, str)  # (branch_key, action)
    drag_merge_requested = Signal(str, str)  # (source_branch, target_branch)

    def __init__(self, branch_key: str, display_name: str, member_count: int, face_pixmap: Optional[QPixmap], parent=None):
        super().__init__(parent)
        self.branch_key = branch_key
        self.display_name = display_name
        self.setFixedSize(88, 112)
        self.setCursor(Qt.PointingHandCursor)

        self._press_pos: Optional[QPoint] = None
        self._drag_active = False

        # Enable drag-and-drop for face merging
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        avatar = QLabel()
        avatar.setFixedSize(64, 64)
        avatar.setAlignment(Qt.AlignCenter)
        if face_pixmap and not face_pixmap.isNull():
            avatar.setPixmap(self._make_circular(face_pixmap, 64))
        else:
            avatar.setText("👤")
            avatar.setStyleSheet("background:#e8eaed;border-radius:32px;font-size:24px;")
        layout.addWidget(avatar)

        name_label = QLabel(display_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-weight:600;font-size:11px;color:#202124;")
        layout.addWidget(name_label)

        count_label = QLabel(f"{member_count} photos")
        count_label.setAlignment(Qt.AlignCenter)
        count_label.setStyleSheet("color:#5f6368;font-size:10px;")
        layout.addWidget(count_label)

        self.setStyleSheet(
            """
            PersonCard { background: transparent; border-radius: 8px; }
            PersonCard:hover { background: rgba(26,115,232,0.08); }
            PersonCard[selected="true"] { background: rgba(26,115,232,0.12); border: 1px solid #1a73e8; }
            PersonCard[dragging="true"] { background: rgba(26,115,232,0.12); border: 1px dashed #1a73e8; }
            PersonCard[dragTarget="true"] { background: rgba(26,115,232,0.08); border: 1px dashed #1a73e8; }
            """
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            self._drag_active = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._press_pos:
            distance = (event.position().toPoint() - self._press_pos).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._begin_drag()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._drag_active:
            self.clicked.emit(self.branch_key)
        self._press_pos = None
        self._drag_active = False
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Show context menu for rename/merge/delete actions."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        menu = QMenu(self)

        rename_action = QAction("✏️ " + (tr("sidebar.people_actions.rename") if callable(tr) else "Rename"), self)
        rename_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "rename"))
        menu.addAction(rename_action)

        merge_action = QAction(
            "🔗 " + (tr("sidebar.people_actions.merge_hint") if callable(tr) else "Merge (use drag-drop)"), self
        )
        merge_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "merge"))
        menu.addAction(merge_action)

        menu.addSeparator()

        details_action = QAction("ℹ️ " + (tr("sidebar.people_actions.details") if callable(tr) else "Details"), self)
        details_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "details"))
        menu.addAction(details_action)

        delete_action = QAction("🗑️ " + (tr("sidebar.people_actions.delete") if callable(tr) else "Delete"), self)
        delete_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "delete"))
        menu.addAction(delete_action)

        tools_menu = menu.addMenu(
            "🧰 " + (tr("sidebar.people_actions.post_detection") if callable(tr) else "Post-Face Detection")
        )

        history_action = QAction(
            "🕑 " + (tr("sidebar.people_actions.merge_history") if callable(tr) else "View Merge History"), self
        )
        history_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "merge_history"))
        tools_menu.addAction(history_action)

        undo_action = QAction(
            "↩️ " + (tr("sidebar.people_actions.undo_last_merge") if callable(tr) else "Undo Last Merge"), self
        )
        undo_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "undo_merge"))
        tools_menu.addAction(undo_action)

        redo_action = QAction(
            "↪️ " + (tr("sidebar.people_actions.redo_last_undo") if callable(tr) else "Redo Last Undo"), self
        )
        redo_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "redo_merge"))
        tools_menu.addAction(redo_action)

        people_tools_action = QAction(
            "🧭 " + (tr("sidebar.people_actions.people_tools") if callable(tr) else "Open People Tools"), self
        )
        people_tools_action.triggered.connect(lambda: self.context_menu_requested.emit(self.branch_key, "people_tools"))
        tools_menu.addAction(people_tools_action)

        menu.exec_(event.globalPos())

    def dragEnterEvent(self, event):
        """Accept drag events from other PersonCards."""
        if event.mimeData().hasText() and event.mimeData().text().startswith("person:"):
            self._set_drag_target_highlight(True)
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle drop event - merge source person into this person."""
        if event.mimeData().hasText():
            source_data = event.mimeData().text()
            if source_data.startswith("person:"):
                source_branch = source_data.split(":", 1)[1]
                if source_branch != self.branch_key:
                    self.drag_merge_requested.emit(source_branch, self.branch_key)
                    event.acceptProposedAction()
        if isValid(self):
            self._set_drag_target_highlight(False)

    def dragLeaveEvent(self, event):
        self._set_drag_target_highlight(False)
        super().dragLeaveEvent(event)

    def _make_circular(self, pixmap: QPixmap, size: int) -> QPixmap:
        scaled = pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        mask = QPixmap(size, size)
        mask.fill(Qt.transparent)
        from PySide6.QtGui import QPainter, QPainterPath

        painter = QPainter(mask)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return mask

    # === Drag helpers ===
    def _begin_drag(self):
        """Start a drag with a visual pixmap and safe state handling."""
        from PySide6.QtGui import QDrag
        from PySide6.QtCore import QMimeData

        self._drag_active = True
        self.setProperty("dragging", True)
        self.style().unpolish(self)
        self.style().polish(self)

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"person:{self.branch_key}")
        drag.setMimeData(mime_data)

        drag_pixmap = self.grab()
        if not drag_pixmap.isNull():
            drag.setPixmap(drag_pixmap)
            drag.setHotSpot(drag_pixmap.rect().center())

        drag.exec_(Qt.MoveAction)

        self._drag_active = False
        self._press_pos = None

        if isValid(self):
            # Restore visual state only if the widget still exists
            self.setProperty("dragging", False)
            self.style().unpolish(self)
            self.style().polish(self)

    def _set_drag_target_highlight(self, enabled: bool):
        if not isValid(self):
            return

        self.setProperty("dragTarget", enabled)
        self.style().unpolish(self)
        self.style().polish(self)

