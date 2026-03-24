from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
)
from PySide6.QtCore import Signal, Qt
from ui.search.search_sidebar import SidebarSection

class QuickPersonChip(QPushButton):
    def __init__(self, person_id, label, icon=None, parent=None):
        super().__init__(parent)
        self.person_id = person_id
        self.setFlat(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 4px 8px;
                border-radius: 4px;
                background-color: #f8f9fa;
                border: 1px solid #e0e0e0;
                color: #3c4043;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #f1f3f4;
            }
        """)
        icon_str = "👤" if not icon else icon
        self.setText(f"{icon_str} {label}")

class PeopleQuickSection(SidebarSection):
    personSelected = Signal(str)
    reviewMergesRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("People", parent)
        self._setup_content()

    def _setup_content(self):
        self.chips_layout = QVBoxLayout()
        self.chips_layout.setSpacing(4)

        # Placeholder for dynamic chips
        self.content_layout.addLayout(self.chips_layout)

        self.btn_all = QPushButton("Show all people")
        self.btn_all.setFlat(True)
        self.btn_all.setStyleSheet("color: #1a73e8; font-size: 9pt; text-align: left; margin-top: 4px;")

        self.btn_merge = QPushButton("Review suggested merges")
        self.btn_merge.setFlat(True)
        self.btn_merge.setStyleSheet("color: #1a73e8; font-size: 9pt; text-align: left;")
        self.btn_merge.clicked.connect(self.reviewMergesRequested)

        self.content_layout.addWidget(self.btn_all)
        self.content_layout.addWidget(self.btn_merge)

    def set_people(self, people_list):
        # Clear existing
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for p in people_list:
            chip = QuickPersonChip(p["id"], p["label"])
            chip.clicked.connect(lambda _, pid=p["id"]: self.personSelected.emit(pid))
            self.chips_layout.addWidget(chip)
