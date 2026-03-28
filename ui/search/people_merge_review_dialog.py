"""
UX-9B: Side-by-side person comparison dialog for merge review.

Shows left vs right cluster cards with representative faces, counts,
time hints, and merge / reject / postpone actions.
"""

import base64
import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QDialog, QDialogButtonBox, QFrame
)


class ClusterCompareCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-weight: 600;")

        self.lbl_face = QLabel()
        self.lbl_face.setFixedSize(220, 220)
        self.lbl_face.setAlignment(Qt.AlignCenter)
        self.lbl_face.setStyleSheet("border: 1px solid #ccc; background: #fafafa;")

        self.lbl_count = QLabel("")
        self.lbl_time = QLabel("")
        self.lbl_label = QLabel("")
        self.lbl_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_face)
        layout.addWidget(self.lbl_label)
        layout.addWidget(self.lbl_count)
        layout.addWidget(self.lbl_time)

    def set_cluster_data(self, payload: dict):
        label = payload.get("label") or payload.get("id") or "Unknown"
        count = payload.get("count", 0)
        time_hint = payload.get("time_hint", "Time hint unavailable")

        self.lbl_label.setText(f"Identity: {label}")
        self.lbl_count.setText(f"Photos: {count}")
        self.lbl_time.setText(f"Time hint: {time_hint}")

        pix = self._load_pixmap(payload)
        if pix and not pix.isNull():
            self.lbl_face.setPixmap(pix.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.lbl_face.setText("No preview")

    def _load_pixmap(self, payload: dict):
        rep_thumb = payload.get("rep_thumb_png")
        rep_path = payload.get("rep_path")

        try:
            if rep_thumb:
                data = base64.b64decode(rep_thumb) if isinstance(rep_thumb, str) else rep_thumb
                pix = QPixmap()
                pix.loadFromData(data)
                if not pix.isNull():
                    return pix
        except Exception:
            pass

        try:
            if rep_path and os.path.exists(rep_path):
                pix = QPixmap(rep_path)
                if not pix.isNull():
                    return pix
        except Exception:
            pass

        return None


class PeopleMergeReviewDialog(QDialog):
    reviewRequested = Signal(str, str)
    mergeAccepted = Signal(str, str)
    mergeRejected = Signal(str, str)
    mergePostponed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("People Merge Review")
        self.resize(980, 620)

        self._current_pair = None

        self.lbl_title = QLabel("Possible People Merges")
        self.lbl_title.setStyleSheet("font-size: 12pt; font-weight: 600;")

        self.list_widget = QListWidget()
        self.list_widget.setMaximumWidth(280)

        self.left_card = ClusterCompareCard("Left Cluster")
        self.right_card = ClusterCompareCard("Right Cluster")

        compare_row = QHBoxLayout()
        compare_row.addWidget(self.left_card, 1)
        compare_row.addWidget(self.right_card, 1)

        self.btn_merge = QPushButton("Merge")
        self.btn_reject = QPushButton("Reject")
        self.btn_postpone = QPushButton("Postpone")

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.btn_merge)
        actions.addWidget(self.btn_reject)
        actions.addWidget(self.btn_postpone)

        main_row = QHBoxLayout()
        main_row.addWidget(self.list_widget, 0)
        main_row.addLayout(compare_row, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.close)

        outer = QVBoxLayout(self)
        outer.addWidget(self.lbl_title)
        outer.addLayout(main_row, 1)
        outer.addLayout(actions)
        outer.addWidget(buttons)

        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.btn_merge.clicked.connect(self._emit_merge)
        self.btn_reject.clicked.connect(self._emit_reject)
        self.btn_postpone.clicked.connect(self._emit_postpone)

    def set_suggestions(self, suggestions):
        self.list_widget.clear()
        for item in list(suggestions or []):
            left_id = str(item.get("left_id", ""))
            right_id = str(item.get("right_id", ""))
            label = item.get("label") or f"{left_id} \u2194 {right_id}"
            list_item = QListWidgetItem(label)
            list_item.setData(256, (left_id, right_id))
            self.list_widget.addItem(list_item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def set_comparison_payload(self, payload: dict):
        left = payload.get("left", {})
        right = payload.get("right", {})
        self.left_card.set_cluster_data(left)
        self.right_card.set_cluster_data(right)

    def _on_selection_changed(self, current, previous):
        if not current:
            self._current_pair = None
            return
        left_id, right_id = current.data(256)
        self._current_pair = (left_id, right_id)
        self.reviewRequested.emit(left_id, right_id)

    def _emit_merge(self):
        if self._current_pair:
            self.mergeAccepted.emit(*self._current_pair)

    def _emit_reject(self):
        if self._current_pair:
            self.mergeRejected.emit(*self._current_pair)

    def _emit_postpone(self):
        if self._current_pair:
            self.mergePostponed.emit(*self._current_pair)
