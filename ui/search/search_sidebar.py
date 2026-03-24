from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QLabel, QHBoxLayout
)
from PySide6.QtCore import Signal, Qt
from ui.search.search_state_store import SearchStateStore, SearchState

class SidebarSection(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 8, 0, 8)
        self.layout.setSpacing(4)

        self.header = QWidget()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(16, 4, 16, 4)

        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setStyleSheet("font-weight: bold; color: #70757a; font-size: 9pt; letter-spacing: 0.5px;")
        header_layout.addWidget(self.lbl_title)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 0, 8, 0)
        self.content_layout.setSpacing(2)

        self.layout.addWidget(self.header)
        self.layout.addWidget(self.content)

class SearchSidebar(QWidget):
    # Parity signals for MainWindow/Controller integration
    folderSelected = Signal(int)
    selectBranch = Signal(str)
    selectDate = Signal(str)
    selectVideos = Signal(str)
    selectGroup = Signal(int)

    def __init__(self, state_store: SearchStateStore, parent=None):
        super().__init__(parent)
        self.store = state_store
        self._setup_ui()
        self.setFixedWidth(260)
        self.setStyleSheet("background-color: white; border-right: 1px solid #e0e0e0;")

    def reload_date_tree(self):
        """Parity method for MainWindow deferred init."""
        logger.debug("[SearchSidebar] reload_date_tree called (parity stub)")
        # In the new architecture, the Browse or Filter sections handle this via state
        pass

    def set_project(self, project_id: int):
        """Update sidebar context for new project."""
        logger.info(f"[SearchSidebar] Switching to project: {project_id}")
        # Trigger section reloads if they have project-bound data

    def toggle_fold(self, folded: bool):
        """Handle sidebar collapse/expand."""
        self.setVisible(not folded)

    def _effective_display_mode(self):
        """Parity method for MainWindow."""
        return "list"

    def switch_display_mode(self, mode: str):
        """Parity method for MainWindow."""
        pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self.sections_layout = QVBoxLayout(container)
        self.sections_layout.setContentsMargins(0, 8, 0, 8)
        self.sections_layout.setSpacing(16)
        self.sections_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll)

    def add_section(self, widget: QWidget):
        # Insert before the stretch
        self.sections_layout.insertWidget(self.sections_layout.count() - 1, widget)
