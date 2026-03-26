from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QPushButton, QLabel, QWidget, QHBoxLayout


class PeopleQuickSection(QGroupBox):
    personSelected = Signal(str)
    showAllPeopleRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("People", parent)

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(8)

        self.lbl_empty = QLabel("People will appear after face clustering.")
        self.layout.addWidget(self.lbl_empty)

        self.people_host = QWidget()
        self.people_layout = QVBoxLayout(self.people_host)
        self.people_layout.setContentsMargins(0, 0, 0, 0)
        self.people_layout.setSpacing(6)
        self.layout.addWidget(self.people_host)

        self.btn_show_all = QPushButton("Show All People")
        self.btn_show_all.clicked.connect(self.showAllPeopleRequested.emit)
        self.layout.addWidget(self.btn_show_all)

        self.setVisible(False)

    def _clear_people(self):
        while self.people_layout.count():
            item = self.people_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_people(self, people_items):
        self._clear_people()

        people_items = list(people_items or [])
        has_any = bool(people_items)

        self.lbl_empty.setVisible(not has_any)
        self.people_host.setVisible(has_any)
        self.btn_show_all.setVisible(has_any)
        self.setVisible(has_any)

        for item in people_items[:8]:
            person_id = item.get("id")
            label = item.get("label", str(person_id))
            count = item.get("count", 0)

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            btn = QPushButton(f"{label} ({count})")
            btn.clicked.connect(lambda checked=False, pid=person_id: self.personSelected.emit(str(pid)))
            row_layout.addWidget(btn)

            self.people_layout.addWidget(row)
