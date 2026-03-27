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

        self.details_pane = QTextEdit()
        self.details_pane.setReadOnly(True)
        self.details_pane.setPlaceholderText("Select a suggestion to see details")
        self.details_pane.setMaximumHeight(120)

        self.btn_accept = QPushButton("Merge Selected")
        self.btn_reject = QPushButton("Reject Selected")

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_accept)
        btn_row.addWidget(self.btn_reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.details_pane)
        layout.addLayout(btn_row)

        self._items = []

        self.btn_accept.clicked.connect(self._accept_selected)
        self.btn_reject.clicked.connect(self._reject_selected)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)

    def set_suggestions(self, suggestions):
        self._items = list(suggestions or [])
        self.list_widget.clear()
        self.details_pane.clear()

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
            self.details_pane.clear()
            return
        item_data = current.data(Qt.UserRole + 1)
        if not isinstance(item_data, dict):
            self.details_pane.clear()
            return

        score = item_data.get("score")
        score_txt = f"{score:.2f}" if isinstance(score, (float, int)) else "?"
        reasons = item_data.get("reasons", [])
        left_id = item_data.get("left_id", "")
        right_id = item_data.get("right_id", "")

        lines = [
            f"<b>Score:</b> {score_txt}",
            f"<b>Left:</b> {left_id}",
            f"<b>Right:</b> {right_id}",
        ]
        if reasons:
            lines.append(f"<b>Reasons:</b> {', '.join(reasons)}")
        else:
            lines.append("<b>Reasons:</b> <i>none reported</i>")

        self.details_pane.setHtml("<br>".join(lines))

    def _accept_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        left_id, right_id = item.data(Qt.UserRole)
        row = self.list_widget.row(item)
        self.list_widget.takeItem(row)
        self.details_pane.clear()
        self.mergeAccepted.emit(left_id, right_id)

    def _reject_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        left_id, right_id = item.data(Qt.UserRole)
        row = self.list_widget.row(item)
        self.list_widget.takeItem(row)
        self.details_pane.clear()
        self.mergeRejected.emit(left_id, right_id)


class PeopleMergeSuggestionsDialog(QDialog):
    mergeAccepted = Signal(str, str)
    mergeRejected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("People Merge Review")
        self.resize(540, 480)

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
