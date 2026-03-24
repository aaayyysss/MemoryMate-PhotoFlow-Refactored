from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar, QPushButton
)
from PySide6.QtCore import Signal, Qt
from ui.search.search_sidebar import SidebarSection

class ActivityMiniSection(SidebarSection):
    openActivityCenterRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("Activity", parent)
        self._setup_content()

    def _setup_content(self):
        self.job_label = QLabel("No background tasks")
        self.job_label.setStyleSheet("color: #666; font-size: 9pt;")

        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #e0e0e0;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #1a73e8;
                border-radius: 2px;
            }
        """)
        self.progress.hide()

        self.btn_details = QPushButton("View Details")
        self.btn_details.setFlat(True)
        self.btn_details.setStyleSheet("color: #1a73e8; font-size: 8pt; text-align: left;")
        self.btn_details.clicked.connect(self.openActivityCenterRequested)

        self.content_layout.addWidget(self.job_label)
        self.content_layout.addWidget(self.progress)
        self.content_layout.addWidget(self.btn_details)

    def set_active_job(self, name, percent=None):
        self.job_label.setText(name)
        if percent is not None:
            self.progress.setValue(percent)
            self.progress.show()
        else:
            self.progress.hide()

    def set_idle(self):
        self.job_label.setText("All tasks complete")
        self.progress.hide()
