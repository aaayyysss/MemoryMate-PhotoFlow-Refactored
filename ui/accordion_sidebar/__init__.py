# ui/accordion_sidebar/__init__.py
# Main orchestrator for modularized accordion sidebar

"""
Modularized Accordion Sidebar

This module provides a refactored version of the accordion sidebar,
broken down into manageable, testable components.

Structure:
- section_widgets.py: SectionHeader and AccordionSection UI components
- base_section.py: BaseSection abstract interface
- folders_section.py: Folders hierarchy implementation
- dates_section.py: Date hierarchy implementation
- videos_section.py: Videos filtering (stub)
- people_section.py: People/faces section (stub)
- quick_section.py: Quick dates section (stub)
- __init__.py: Main AccordionSidebar orchestrator (this file)

Phase 3 Task 3.2: Modularize AccordionSidebar (94KB → modules)
"""

import logging
from typing import Optional, Dict
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QScrollArea, QSizePolicy)
from PySide6.QtCore import Signal, Qt, QTimer
from shiboken6 import isValid
from reference_db import ReferenceDB

from .section_widgets import AccordionSection
from .folders_section import FoldersSection
from .dates_section import DatesSection
from .videos_section import VideosSection
from .people_section import PeopleSection
from .devices_section import DevicesSection
from .quick_section import QuickSection
from .locations_section import LocationsSection

logger = logging.getLogger(__name__)


class AccordionSidebar(QWidget):
    """
    Main accordion sidebar widget (modularized version).

    Manages multiple collapsible sections with:
    - Vertical navigation bar (left side)
    - Expandable sections (right side)
    - One section expanded at a time
    - Thread-safe data loading
    - Generation tokens to prevent stale data

    This is a simplified orchestrator that delegates section logic
    to individual modules.
    """

    # Signals to parent (MainWindow/GooglePhotosLayout) for grid filtering
    selectBranch = Signal(str)     # branch_key (e.g., "all" or "face_john")
    selectFolder = Signal(int)     # folder_id
    selectDate   = Signal(str)     # date string (e.g., "2025", "2025-10")
    selectTag    = Signal(str)     # tag name
    selectPerson = Signal(str)     # person branch_key
    selectVideo  = Signal(str)     # video filter type
    selectDevice = Signal(str)     # device root path
    selectLocation = Signal(object)  # location data dict {name, lat, lon, count, paths}
    personMerged = Signal(str, str)  # source_branch, target_branch
    personDeleted = Signal(str)      # branch_key
    mergeHistoryRequested = Signal()
    undoLastMergeRequested = Signal()
    redoLastUndoRequested = Signal()
    peopleToolsRequested = Signal()

    # Section expansion signal
    sectionExpanding = Signal(str)  # section_id

    def __init__(self, project_id: Optional[int], parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.db = ReferenceDB()
        self.expanded_section_id: Optional[str] = None
        self._active_person_branch: Optional[str] = None

        # Section instances (logic modules)
        self.section_logic: Dict[str, any] = {}

        # Section UI widgets (containers)
        self.section_widgets: Dict[str, AccordionSection] = {}

        # Navigation buttons
        self.nav_buttons: Dict[str, QPushButton] = {}

        logger.info(f"[AccordionSidebar] Initializing with project_id={project_id}")

        # Build UI
        self._init_ui()
        self._create_sections()
        self._connect_signals()

        # Expand first section by default
        if self.section_widgets:
            first_section_id = list(self.section_widgets.keys())[0]
            self._expand_section(first_section_id)

    def _init_ui(self):
        """Initialize main UI layout."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === LEFT: Vertical Navigation Bar ===
        nav_bar = QWidget()
        nav_bar.setFixedWidth(52)
        nav_bar.setStyleSheet("""
            QWidget {
                background: #ffffff;
                border-right: 1px solid #dadce0;
            }
        """)
        self.nav_layout = QVBoxLayout(nav_bar)
        self.nav_layout.setContentsMargins(6, 12, 6, 4)
        self.nav_layout.setSpacing(4)

        main_layout.addWidget(nav_bar)

        # === RIGHT: Sections Container ===
        self.sections_container = QWidget()
        self.sections_container.setStyleSheet("""
            QWidget {
                background: #f8f9fa;
            }
        """)
        self.sections_layout = QVBoxLayout(self.sections_container)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(2)

        # Scroll area for sections
        scroll = QScrollArea()
        scroll.setWidget(self.sections_container)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # BUGFIX: Use QFrame.NoFrame enum instead of integer
        from PySide6.QtWidgets import QFrame
        scroll.setFrameShape(QFrame.NoFrame)  # No frame

        main_layout.addWidget(scroll)

    def _create_sections(self):
        """Create all section instances."""

        # Create section logic modules
        self.section_logic = {
            "folders": FoldersSection(self),
            "dates": DatesSection(self),
            "videos": VideosSection(self),
            "people": PeopleSection(self),
            "devices": DevicesSection(self),
            "locations": LocationsSection(self),
            "quick": QuickSection(self)
        }

        # Set project ID and DB reference for all sections
        for section_id, section in self.section_logic.items():
            section.set_project(self.project_id)
            if hasattr(section, 'set_db'):
                section.set_db(self.db)

        # Create UI widgets for each section
        for section_id, section_logic in self.section_logic.items():
            self._ensure_loaded_connection(section_id, section_logic)

            # Create AccordionSection UI container
            section_widget = AccordionSection(
                section_id=section_id,
                title=section_logic.get_title(),
                icon=section_logic.get_icon()
            )
            if hasattr(section_logic, "get_header_widget"):
                try:
                    header_widget = section_logic.get_header_widget()
                    if header_widget:
                        section_widget.set_header_extra(header_widget)
                except Exception:
                    logger.debug("[AccordionSidebar] Failed attaching header widget for %s", section_id, exc_info=True)
            section_widget.expandRequested.connect(self._on_section_expand_requested)

            # Store references
            self.section_widgets[section_id] = section_widget

            # Add to layout
            self.sections_layout.addWidget(section_widget)

            # Create navigation button
            nav_btn = QPushButton(section_logic.get_icon())
            nav_btn.setFixedSize(40, 40)
            nav_btn.setToolTip(section_logic.get_title())
            nav_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    font-size: 18px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background: #f1f3f4;
                }
                QPushButton:pressed {
                    background: #e8f0fe;
                }
            """)
            nav_btn.clicked.connect(lambda checked, sid=section_id: self._expand_section(sid))
            self.nav_buttons[section_id] = nav_btn
            self.nav_layout.addWidget(nav_btn)

        # Add spacer at bottom of nav bar
        self.nav_layout.addStretch()

        logger.info(f"[AccordionSidebar] Created {len(self.section_logic)} sections")

    def _connect_signals(self):
        """Connect section signals to accordion signals."""

        # Folders section
        folders = self.section_logic.get("folders")
        if folders and hasattr(folders, 'folderSelected'):
            folders.folderSelected.connect(self._on_folder_selected)

        # Dates section
        dates = self.section_logic.get("dates")
        if dates and hasattr(dates, 'dateSelected'):
            dates.dateSelected.connect(self._on_date_selected)

        # People section
        people = self.section_logic.get("people")
        if people and hasattr(people, 'personSelected'):
            people.personSelected.connect(self._on_person_selected)
        if people and hasattr(people, 'contextMenuRequested'):
            people.contextMenuRequested.connect(self._on_person_context_menu)
        if people and hasattr(people, 'dragMergeRequested'):
            people.dragMergeRequested.connect(self._on_person_drag_merge)
        if people and hasattr(people, 'mergeHistoryRequested'):
            people.mergeHistoryRequested.connect(self.mergeHistoryRequested.emit)
        if people and hasattr(people, 'undoMergeRequested'):
            people.undoMergeRequested.connect(self.undoLastMergeRequested.emit)
        if people and hasattr(people, 'redoMergeRequested'):
            people.redoMergeRequested.connect(self.redoLastUndoRequested.emit)
        if people and hasattr(people, 'peopleToolsRequested'):
            people.peopleToolsRequested.connect(self.peopleToolsRequested.emit)

        # Videos section
        videos = self.section_logic.get("videos")
        if videos and hasattr(videos, 'videoFilterSelected'):
            videos.videoFilterSelected.connect(self._on_video_selected)

        # Devices section
        devices = self.section_logic.get("devices")
        if devices and hasattr(devices, 'deviceSelected'):
            devices.deviceSelected.connect(self.selectDevice.emit)

        # Locations section
        locations = self.section_logic.get("locations")
        if locations and hasattr(locations, 'locationSelected'):
            locations.locationSelected.connect(self.selectLocation.emit)

        # Quick section
        quick = self.section_logic.get("quick")
        if quick and hasattr(quick, 'quickDateSelected'):
            quick.quickDateSelected.connect(self.selectDate.emit)

    def _on_section_expand_requested(self, section_id: str):
        """Handle section expand request."""
        self._expand_section(section_id)

    # --- PHASE 3: Selection handlers with session state persistence ---
    def _on_folder_selected(self, folder_id: int):
        """Handle folder selection and save to session state."""
        # PHASE 3: Save folder selection to session state
        try:
            from session_state_manager import get_session_state
            # Get folder name for display
            folder_name = f"Folder #{folder_id}"
            try:
                from reference_db import ReferenceDB
                db = ReferenceDB()
                row = db._connect().execute("SELECT name FROM photo_folders WHERE id = ?", (folder_id,)).fetchone()
                if row:
                    folder_name = row[0]
            except:
                pass

            get_session_state().set_selection("folder", folder_id, folder_name)
            logger.debug(f"[AccordionSidebar] PHASE 3: Saved folder selection: {folder_name} (ID={folder_id})")
        except Exception as e:
            logger.warning(f"[AccordionSidebar] PHASE 3: Failed to save folder selection: {e}")

        # Emit signal for grid update
        self.selectFolder.emit(folder_id)

    def _on_date_selected(self, date_key: str):
        """Handle date selection and save to session state."""
        # PHASE 3: Save date selection to session state
        try:
            from session_state_manager import get_session_state
            get_session_state().set_selection("date", date_key, date_key)
            logger.debug(f"[AccordionSidebar] PHASE 3: Saved date selection: {date_key}")
        except Exception as e:
            logger.warning(f"[AccordionSidebar] PHASE 3: Failed to save date selection: {e}")

        # Emit signal for grid update
        self.selectDate.emit(date_key)

    def _on_person_selected(self, branch_key: str):
        """Track active person selection, support toggling, and emit filter signal."""
        people_logic = self.section_logic.get("people")

        # Toggle selection when clicking the same person again
        if self._active_person_branch and branch_key == self._active_person_branch:
            self._active_person_branch = None
            if hasattr(people_logic, "set_active_branch"):
                people_logic.set_active_branch(None)
            self.selectPerson.emit("")
            # PHASE 3: Clear person selection from session state
            try:
                from session_state_manager import get_session_state
                get_session_state().set_selection(None, None, None)
            except:
                pass
            return

        self._active_person_branch = branch_key

        if hasattr(people_logic, "set_active_branch"):
            people_logic.set_active_branch(branch_key)

        # PHASE 3: Save person selection to session state
        try:
            from session_state_manager import get_session_state
            # Get person name from branch_key
            person_name = branch_key.replace("person_", "Person ")
            get_session_state().set_selection("person", branch_key, person_name)
            logger.debug(f"[AccordionSidebar] PHASE 3: Saved person selection: {person_name}")
        except Exception as e:
            logger.warning(f"[AccordionSidebar] PHASE 3: Failed to save person selection: {e}")

        self.selectPerson.emit(branch_key)

    def _on_video_selected(self, filter_key: str):
        """Handle video filter selection and save to session state."""
        # PHASE 3: Save video selection to session state
        try:
            from session_state_manager import get_session_state
            # filter_key could be: "all", "date:2024", "date:2024-07", etc.
            display_name = filter_key
            if filter_key.startswith("date:"):
                display_name = filter_key.replace("date:", "Videos ")
            elif filter_key == "all":
                display_name = "All Videos"

            get_session_state().set_selection("video", filter_key, display_name)
            logger.debug(f"[AccordionSidebar] PHASE 3: Saved video selection: {display_name}")
        except Exception as e:
            logger.warning(f"[AccordionSidebar] PHASE 3: Failed to save video selection: {e}")

        # Emit signal for grid update
        self.selectVideo.emit(filter_key)

    def _expand_section(self, section_id: str):
        """Expand specified section and collapse others."""
        if section_id not in self.section_widgets:
            logger.warning(f"[AccordionSidebar] Unknown section: {section_id}")
            return

        logger.info(f"[AccordionSidebar] Expanding section: {section_id}")

        # PHASE 2: Save expanded section to session state
        try:
            from session_state_manager import get_session_state
            get_session_state().set_section(section_id)
            logger.debug(f"[AccordionSidebar] PHASE 2: Saved section={section_id} to session state")
        except Exception as e:
            logger.warning(f"[AccordionSidebar] PHASE 2: Failed to save section state: {e}")

        # Emit expansion signal
        self.sectionExpanding.emit(section_id)

        # Collapse all sections
        for sid, widget in self.section_widgets.items():
            widget.set_expanded(sid == section_id)

        # Update expanded section ID
        self.expanded_section_id = section_id

        # Load section data if not already loaded
        self._trigger_section_load(section_id)

    def _trigger_section_load(self, section_id: str):
        """Ensure signals are wired and start loading the given section."""
        section_logic = self.section_logic.get(section_id)
        if not section_logic or section_logic.is_loading():
            return

        self._ensure_loaded_connection(section_id, section_logic)

        result = section_logic.load_section()

        # Fallback: some stub sections complete synchronously without emitting
        if not section_logic.is_loading():
            generation = getattr(section_logic, '_generation', 0)
            self._on_section_loaded(section_id, generation, result)

    def _ensure_loaded_connection(self, section_id: str, section_logic):
        """Connect loaded signal to accordion handler exactly once."""
        signals = getattr(section_logic, 'signals', None)
        loaded_signal = getattr(signals, 'loaded', None)

        # Connect before triggering load to avoid missing fast emissions
        if loaded_signal and not getattr(section_logic, '_loaded_connected', False):
            loaded_signal.connect(
                lambda gen, data, sid=section_id: self._on_section_loaded(sid, gen, data)
            )
            section_logic._loaded_connected = True

    def _on_section_loaded(self, section_id: str, generation: int, data):
        """Handle section data loaded."""
        section_logic = self.section_logic.get(section_id)
        section_widget = self.section_widgets.get(section_id)

        if not section_logic or not section_widget or not isValid(section_widget):
            return

        # Check generation (staleness)
        if generation != section_logic._generation:
            logger.debug(f"[AccordionSidebar] Discarding stale data for {section_id}")
            return

        # Normalize missing data so section builders never crash on None
        normalized_data = data
        if normalized_data is None:
            if section_id in {"folders", "videos", "people"}:
                normalized_data = []
            elif section_id == "dates":
                normalized_data = {}
            else:
                normalized_data = {}

        try:
            content_widget = section_logic.create_content_widget(normalized_data)
            if content_widget:
                section_widget.set_content_widget(content_widget)

                # Update count if available
                if section_id == "dates" and isinstance(normalized_data, dict):
                    year_counts = normalized_data.get("year_counts", {}) or {}
                    section_widget.set_count(sum(year_counts.values()))
                elif hasattr(normalized_data, '__len__'):
                    section_widget.set_count(len(normalized_data))
        except Exception:
            logger.exception(f"[AccordionSidebar] Failed to build content for {section_id}")
            return

        logger.info(f"[AccordionSidebar] Section {section_id} loaded and displayed")

    # === Public API ===

    def set_project(self, project_id: int):
        """Update all sections for new project."""
        logger.info(f"[AccordionSidebar] Switching project: {self.project_id} → {project_id}")

        self.project_id = project_id

        # Update all sections
        for section in self.section_logic.values():
            section.set_project(project_id)

        # Reload expanded section
        if self.expanded_section_id:
            section = self.section_logic.get(self.expanded_section_id)
            if section:
                self._trigger_section_load(self.expanded_section_id)

    def reload_all_sections(self):
        """Reload all sections from database."""
        logger.info("[AccordionSidebar] Reloading all sections")

        for section_id, section in self.section_logic.items():
            self._trigger_section_load(section_id)

    def reload_people_section(self):
        """Public helper to refresh the people section content."""
        self._trigger_section_load("people")

    def reload_section(self, section_id: str):
        """
        Public method to reload a specific section's content.

        This is useful for refreshing the sidebar after:
        - Photo scanning completes
        - Face detection finishes
        - Tags are added/modified
        - GPS locations are updated
        - Folders are reorganized

        Args:
            section_id: Section to reload ("people", "dates", "folders", "tags",
                       "branches", "quick", "locations", "devices", "videos")
        """
        logger.info(f"[AccordionSidebar] Reloading section: {section_id}")
        if section_id in self.section_logic:
            self._trigger_section_load(section_id)
        else:
            logger.warning(f"[AccordionSidebar] Section '{section_id}' not found")

    def _on_person_context_menu(self, branch_key: str, action: str):
        """Handle person context menu actions."""
        logger.info(f"[AccordionSidebar] Context menu action: {action} for {branch_key}")

        if action == "rename":
            self._handle_rename_person(branch_key)
        elif action == "merge":
            self._handle_merge_person(branch_key)
        elif action == "details":
            self._handle_person_details(branch_key)
        elif action == "delete":
            self._handle_delete_person(branch_key)
        elif action == "merge_history":
            self.mergeHistoryRequested.emit()
        elif action == "undo_merge":
            self.undoLastMergeRequested.emit()
        elif action == "redo_merge":
            self.redoLastUndoRequested.emit()
        elif action == "people_tools":
            self.peopleToolsRequested.emit()

    def _on_person_drag_merge(self, source_branch: str, target_branch: str):
        """Handle drag-and-drop merge from People grid."""
        from PySide6.QtWidgets import QMessageBox

        try:
            # Get source and target names for confirmation feedback
            with self.db._connect() as conn:
                cur = conn.cursor()

                # Get source name
                cur.execute(
                    "SELECT label, count FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                    (self.project_id, source_branch)
                )
                source_row = cur.fetchone()
                source_name = source_row[0] if source_row and source_row[0] else source_branch
                source_count = source_row[1] if source_row else 0

                # Get target name
                cur.execute(
                    "SELECT label, count FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                    (self.project_id, target_branch)
                )
                target_row = cur.fetchone()
                target_name = target_row[0] if target_row and target_row[0] else target_branch
                target_count = target_row[1] if target_row else 0

            logger.info(f"[AccordionSidebar] Drag-drop merge: '{source_name}' ({source_count} photos) -> '{target_name}' ({target_count} photos)")

            # Use ReferenceDB.merge_face_clusters (the proper method)
            result = self.db.merge_face_clusters(
                project_id=self.project_id,
                target_branch=target_branch,
                source_branches=[source_branch],
                log_undo=True
            )

            # Reload people section to reflect changes
            people = self.section_logic.get("people")
            if people:
                # Delay reload until drag/drop events fully unwind to avoid stale widget crashes
                QTimer.singleShot(0, lambda: self._trigger_section_load("people"))

            # Build comprehensive merge notification following Google Photos pattern
            msg_lines = [f"✓ '{source_name}' merged successfully", ""]

            duplicates = result.get('duplicates_found', 0)
            unique_moved = result.get('unique_moved', 0)
            total_photos = result.get('total_photos', 0)
            moved_faces = result.get('moved_faces', 0)

            if duplicates > 0:
                msg_lines.append(f"⚠️ Found {duplicates} duplicate photo{'s' if duplicates != 1 else ''}")
                msg_lines.append("   (already in target, not duplicated)")
                msg_lines.append("")

            if unique_moved > 0:
                msg_lines.append(f"• Moved {unique_moved} unique photo{'s' if unique_moved != 1 else ''}")
            elif duplicates > 0:
                msg_lines.append(f"• No unique photos to move (all were duplicates)")

            msg_lines.append(f"• Reassigned {moved_faces} face crop{'s' if moved_faces != 1 else ''}")
            msg_lines.append("")
            msg_lines.append(f"Total: {total_photos} photo{'s' if total_photos != 1 else ''}")

            QMessageBox.information(
                None,
                "Merged",
                "\n".join(msg_lines)
            )

            # Notify listeners (e.g., Google layout) so active person filters stay in sync
            self.personMerged.emit(source_branch, target_branch)

            # Keep sidebar highlight aligned with the surviving target after reload
            self._active_person_branch = target_branch
            if hasattr(people, "set_active_branch"):
                QTimer.singleShot(0, lambda: people.set_active_branch(target_branch))

            logger.info(f"[AccordionSidebar] Merge successful: {result}")

        except Exception as e:
            logger.exception(f"[AccordionSidebar] Drag-drop merge failed: {e}")
            QMessageBox.critical(
                None,
                "Merge Failed",
                f"❌ Error merging face clusters:\n\n{str(e)}\n\n"
                f"Please check the logs for details."
            )

    def _handle_rename_person(self, branch_key: str):
        """Handle rename person action."""
        from PySide6.QtWidgets import QInputDialog, QMessageBox

        # Get current name
        with self.db._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT label FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                (self.project_id, branch_key)
            )
            row = cur.fetchone()
            current_name = row[0] if row and row[0] else branch_key

        # Show input dialog
        new_name, ok = QInputDialog.getText(
            None,
            "Rename Person",
            f"Enter new name for '{current_name}':",
            text=current_name
        )

        if ok and new_name and new_name != current_name:
            try:
                # Update in database
                with self.db._connect() as conn:
                    conn.execute(
                        "UPDATE face_branch_reps SET label = ? WHERE project_id = ? AND branch_key = ?",
                        (new_name, self.project_id, branch_key)
                    )
                    conn.commit()

                logger.info(f"[AccordionSidebar] Renamed {current_name} to {new_name}")

                # Reload people section
                self._trigger_section_load("people")

                QMessageBox.information(
                    None,
                    "Rename Successful",
                    f"✅ Renamed '{current_name}' to '{new_name}'"
                )

            except Exception as e:
                logger.exception(f"[AccordionSidebar] Rename failed: {e}")
                QMessageBox.critical(None, "Rename Failed", f"Error: {e}")

    def _handle_merge_person(self, branch_key: str):
        """Handle merge person action."""
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(
            None,
            "Merge Person",
            f"Merge functionality for {branch_key}\n\n"
            f"Use drag-and-drop to merge: drag one person card onto another."
        )

    def _handle_person_details(self, branch_key: str):
        """Handle person details action."""
        from PySide6.QtWidgets import QMessageBox

        # Get person details from database
        with self.db._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT label, count, rep_path FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                (self.project_id, branch_key)
            )
            row = cur.fetchone()

        if row:
            name = row[0] or "Unnamed"
            count = row[1] or 0
            rep_path = row[2] or "None"

            QMessageBox.information(
                None,
                "Person Details",
                f"👤 {name}\n\n"
                f"Branch Key: {branch_key}\n"
                f"Photo Count: {count}\n"
                f"Representative Path: {rep_path}"
            )

    def _handle_delete_person(self, branch_key: str):
        """Handle delete person action."""
        from PySide6.QtWidgets import QMessageBox

        # Get person name
        with self.db._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT label FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                (self.project_id, branch_key)
            )
            row = cur.fetchone()
            person_name = row[0] if row and row[0] else branch_key

        # Confirm deletion
        reply = QMessageBox.question(
            None,
            "Confirm Delete",
            f"🗑️ Delete '{person_name}'?\n\n"
            f"This will remove this person and all associated face data.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # Delete from database
                with self.db._connect() as conn:
                    conn.execute(
                        "DELETE FROM face_branch_reps WHERE project_id = ? AND branch_key = ?",
                        (self.project_id, branch_key)
                    )
                    conn.commit()

                logger.info(f"[AccordionSidebar] Deleted person: {person_name}")

                # Reload people section
                self._trigger_section_load("people")

                if self._active_person_branch == branch_key:
                    self._active_person_branch = None
                    people_logic = self.section_logic.get("people")
                    if hasattr(people_logic, "set_active_branch"):
                        people_logic.set_active_branch(None)

                # Notify parent layouts so active filters can be cleared if necessary
                self.personDeleted.emit(branch_key)

                QMessageBox.information(
                    None,
                    "Delete Successful",
                    f"✅ Deleted '{person_name}'"
                )

            except Exception as e:
                logger.exception(f"[AccordionSidebar] Delete failed: {e}")
                QMessageBox.critical(None, "Delete Failed", f"Error: {e}")

    def cleanup(self):
        """Clean up resources before destruction."""
        logger.info("[AccordionSidebar] Cleanup")

        # Cleanup all sections
        for section in self.section_logic.values():
            if hasattr(section, 'cleanup'):
                section.cleanup()

        # Close database
        if hasattr(self, 'db') and self.db:
            try:
                self.db.close()
            except Exception as e:
                logger.error(f"[AccordionSidebar] Error closing database: {e}")

    def _dbg(self, msg: str):
        """Debug logging helper."""
        logger.debug(f"[AccordionSidebar] {msg}")


# Export main class
__all__ = ['AccordionSidebar']
