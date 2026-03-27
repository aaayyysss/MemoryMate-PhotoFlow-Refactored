from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QDialog, QDialogButtonBox
)


class PeopleMergeSuggestionsPanel(QWidget):
    mergeAccepted = Signal(str, str)
    mergeRejected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.lbl_title = QLabel("Possible People Merges")
        self.list_widget = QListWidget()

        self.btn_accept = QPushButton("Merge Selected")
        self.btn_reject = QPushButton("Reject Selected")

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_accept)
        btn_row.addWidget(self.btn_reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.list_widget)
        layout.addLayout(btn_row)

        self._items = []

        self.btn_accept.clicked.connect(self._accept_selected)
        self.btn_reject.clicked.connect(self._reject_selected)

    def set_suggestions(self, suggestions):
        self._items = list(suggestions or [])
        self.list_widget.clear()

        for item in self._items:
            left_id = str(item.get("left_id", ""))
            right_id = str(item.get("right_id", ""))
            score = item.get("score")
            score_txt = f"{score:.2f}" if isinstance(score, (float, int)) else "?"
            title = item.get("label") or f"{left_id} ↔ {right_id}  (score={score_txt})"

            list_item = QListWidgetItem(title)
            list_item.setData(256, (left_id, right_id))
            self.list_widget.addItem(list_item)

    def _accept_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        left_id, right_id = item.data(256)
        self.mergeAccepted.emit(left_id, right_id)

    def _reject_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        left_id, right_id = item.data(256)
        self.mergeRejected.emit(left_id, right_id)


class PeopleMergeSuggestionsDialog(QDialog):
    mergeAccepted = Signal(str, str)
    mergeRejected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("People Merge Review")
        self.resize(540, 420)

        self.panel = PeopleMergeSuggestionsPanel(self)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.panel)
        layout.addWidget(buttons)

        self.panel.mergeAccepted.connect(self.mergeAccepted.emit)
        self.panel.mergeRejected.connect(self.mergeRejected.emit)

    def set_suggestions(self, suggestions):
        self.panel.set_suggestions(suggestions)
