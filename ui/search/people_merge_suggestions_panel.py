from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QDialog, QDialogButtonBox,
    QTextEdit, QSplitter,
)


class PeopleMergeSuggestionsPanel(QWidget):
    mergeAccepted = Signal(str, str)
    mergeRejected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.lbl_title = QLabel("Possible People Merges")
        self.list_widget = QListWidget()

        self.left_preview = QTextEdit()
        self.left_preview.setReadOnly(True)
        self.left_preview.setPlaceholderText("Left cluster details")
        self.right_preview = QTextEdit()
        self.right_preview.setReadOnly(True)
        self.right_preview.setPlaceholderText("Right cluster details")

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.left_preview)
        splitter.addWidget(self.right_preview)
        splitter.setSizes([240, 240])

        self.btn_accept = QPushButton("Merge Selected")
        self.btn_reject = QPushButton("Reject Selected")

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_accept)
        btn_row.addWidget(self.btn_reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(splitter)
        layout.addLayout(btn_row)

        self._items = []

        self.btn_accept.clicked.connect(self._accept_selected)
        self.btn_reject.clicked.connect(self._reject_selected)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)

    def set_suggestions(self, suggestions):
        self._items = list(suggestions or [])
        self.list_widget.clear()
        self.left_preview.clear()
        self.right_preview.clear()

        for item in self._items:
            left_id = str(item.get("left_id", ""))
            right_id = str(item.get("right_id", ""))
            score = item.get("score")
            score_txt = f"{score:.2f}" if isinstance(score, (float, int)) else "?"
            title = item.get("label") or f"{left_id} \u2194 {right_id}  (score={score_txt})"

            list_item = QListWidgetItem(title)
            list_item.setData(Qt.UserRole, (left_id, right_id))
            list_item.setData(Qt.UserRole + 1, item)
            self.list_widget.addItem(list_item)

    def _on_selection_changed(self, current, _previous):
        if not current:
            self.left_preview.clear()
            self.right_preview.clear()
            return
        item_data = current.data(Qt.UserRole + 1)
        if not isinstance(item_data, dict):
            self.left_preview.clear()
            self.right_preview.clear()
            return

        score = item_data.get("score")
        score_txt = f"{score:.2f}" if isinstance(score, (float, int)) else "?"
        reasons = item_data.get("reasons", [])
        reason_txt = ", ".join(reasons) if reasons else item_data.get("reason", "review candidate")
        left_id = item_data.get("left_id", "")
        right_id = item_data.get("right_id", "")

        self.left_preview.setHtml(
            f"<b>Cluster:</b> {left_id}<br>"
            f"<b>Count:</b> {item_data.get('left_count', '?')}<br>"
            f"<b>Score:</b> {score_txt}<br>"
            f"<b>Reason:</b> {reason_txt}"
        )
        self.right_preview.setHtml(
            f"<b>Cluster:</b> {right_id}<br>"
            f"<b>Count:</b> {item_data.get('right_count', '?')}<br>"
            f"<b>Score:</b> {score_txt}<br>"
            f"<b>Reason:</b> {reason_txt}"
        )

    def _accept_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        left_id, right_id = item.data(Qt.UserRole)
        row = self.list_widget.row(item)
        self.list_widget.takeItem(row)
        self.left_preview.clear()
        self.right_preview.clear()
        self.mergeAccepted.emit(left_id, right_id)

    def _reject_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        left_id, right_id = item.data(Qt.UserRole)
        row = self.list_widget.row(item)
        self.list_widget.takeItem(row)
        self.left_preview.clear()
        self.right_preview.clear()
        self.mergeRejected.emit(left_id, right_id)


class PeopleMergeSuggestionsDialog(QDialog):
    mergeAccepted = Signal(str, str)
    mergeRejected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("People Merge Review")
        self.resize(760, 520)

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
