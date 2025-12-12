"""
ProjectController - Project Switching Logic

Extracted from main_window_qt.py (Phase 1, Step 1.3)

Responsibilities:
- Project combo box change handling
- Project switching coordination
- Thumbnail cache clearing
- Sidebar/grid project updates

Version: 09.20.00.00
"""


class ProjectController:
    """Owns project switching & persistence logic."""
    def __init__(self, main):
        self.main = main

    def on_project_changed(self, idx: int):
        pid = self.main.project_combo.itemData(idx)
        if pid is None:
            return
        if self.main.thumbnails:
            self.main.thumbnails.clear()

        # Update legacy sidebar and grid
        self.main.sidebar.set_project(pid)
        self.main.grid.set_project(pid)

        # PHASE 1 Task 1.3: Also update Google Layout if active
        if hasattr(self.main, 'layout_manager') and self.main.layout_manager:
            current_layout = self.main.layout_manager._current_layout
            if current_layout and hasattr(current_layout, 'set_project'):
                current_layout.set_project(pid)
                print(f"[ProjectController] Updated Google Layout to project {pid}")
