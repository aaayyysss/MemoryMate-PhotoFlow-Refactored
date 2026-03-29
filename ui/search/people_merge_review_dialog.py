"""
UX-9B/UX-10: Side-by-side person comparison dialog for merge review.

Shows left vs right cluster cards with representative faces, counts,
time hints, confidence scoring, and merge / reject / skip actions.
Includes auto-advance and decision log.
"""

import base64
import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QDialog, QDialogButtonBox, QFrame
)


class ClusterCompareCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
        """)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-weight: 600; font-size: 14px;")

        self.lbl_face = QLabel()
        self.lbl_face.setFixedSize(220, 220)
        self.lbl_face.setAlignment(Qt.AlignCenter)
        self.lbl_face.setStyleSheet(
            "border: 1px solid #e0e0e0; background: #fafafa; border-radius: 6px;"
        )

        self.lbl_label = QLabel("")
        self.lbl_label.setWordWrap(True)
        self.lbl_label.setStyleSheet("color: #202124;")

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #5f6368;")

        self.lbl_time = QLabel("")
        self.lbl_time.setStyleSheet("color: #5f6368; font-size: 11px;")

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #9aa0a6; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_face, 0, Qt.AlignCenter)
        layout.addWidget(self.lbl_label)
        layout.addWidget(self.lbl_count)
        layout.addWidget(self.lbl_time)
        layout.addWidget(self.lbl_status)

    def set_cluster_data(self, payload: dict):
        label = payload.get("label") or payload.get("id") or "Unknown"
        count = payload.get("count", 0)
        time_hint = payload.get("time_hint", "")

        is_unnamed = str(label).startswith("face_") or str(label).startswith("unnamed")
        self.lbl_label.setText(f"Identity: {label}")
        self.lbl_count.setText(f"Photos: {count}")
        self.lbl_time.setText(f"Last seen: {time_hint}" if time_hint else "")
        self.lbl_status.setText("Unnamed cluster" if is_unnamed else "Named identity")

        pix = self._load_pixmap(payload)
        if pix and not pix.isNull():
            self.lbl_face.setPixmap(
                pix.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
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


def _confidence_color(score):
    """Return (bg_color, text_color) based on merge confidence score."""
    if score is None:
        return "#f1f3f4", "#5f6368"
    if score >= 0.85:
        return "#e6f4ea", "#188038"  # green — high confidence
    if score >= 0.70:
        return "#e8f0fe", "#1a73e8"  # blue — moderate
    return "#fef7e0", "#f9ab00"       # amber — review carefully


class PeopleMergeReviewDialog(QDialog):
    reviewRequested = Signal(str, str)
    mergeAccepted = Signal(str, str)
    mergeRejected = Signal(str, str)
    mergePostponed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("People Merge Review")
        self.resize(1020, 660)

        self._current_pair = None
        self._decision_counts = {"merged": 0, "rejected": 0, "skipped": 0}

        # Title row
        self.lbl_title = QLabel("People Merge Review")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #202124;")

        self.lbl_subtitle = QLabel("")
        self.lbl_subtitle.setStyleSheet("color: #5f6368; font-size: 12px;")

        # Candidate list (left pane)
        self.list_widget = QListWidget()
        self.list_widget.setMaximumWidth(300)
        self.list_widget.setStyleSheet("""
            QListWidget::item {
                padding: 8px 6px;
                border-bottom: 1px solid #f1f3f4;
            }
            QListWidget::item:selected {
                background: #e8f0fe;
            }
        """)

        # Confidence + rationale labels
        self.lbl_confidence = QLabel("")
        self.lbl_confidence.setAlignment(Qt.AlignCenter)
        self.lbl_confidence.setStyleSheet("font-size: 13px; padding: 4px;")

        self.lbl_rationale = QLabel("")
        self.lbl_rationale.setAlignment(Qt.AlignCenter)
        self.lbl_rationale.setWordWrap(True)
        self.lbl_rationale.setStyleSheet("color: #5f6368; font-size: 11px; padding: 4px;")

        # Comparison cards (right pane)
        self.left_card = ClusterCompareCard("Left Cluster")
        self.right_card = ClusterCompareCard("Right Cluster")

        compare_row = QHBoxLayout()
        compare_row.addWidget(self.left_card, 1)
        compare_row.addWidget(self.right_card, 1)

        # Action buttons — Merge (primary), Not Same (warning), Skip (neutral)
        self.btn_merge = QPushButton("Merge")
        self.btn_merge.setStyleSheet("""
            QPushButton {
                background: #1a73e8; color: white;
                border: none; border-radius: 6px;
                padding: 8px 20px; font-weight: 600;
            }
            QPushButton:hover { background: #1967d2; }
        """)

        self.btn_reject = QPushButton("Not Same")
        self.btn_reject.setStyleSheet("""
            QPushButton {
                background: #fff3e0; color: #e65100;
                border: 1px solid #f9ab00; border-radius: 6px;
                padding: 8px 20px;
            }
            QPushButton:hover { background: #fce8e6; }
        """)

        self.btn_skip = QPushButton("Skip")
        self.btn_skip.setStyleSheet("""
            QPushButton {
                background: #f1f3f4; color: #5f6368;
                border: none; border-radius: 6px;
                padding: 8px 20px;
            }
            QPushButton:hover { background: #e0e0e0; }
        """)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.btn_merge)
        actions.addWidget(self.btn_reject)
        actions.addWidget(self.btn_skip)

        # Decision log
        self.lbl_decisions = QLabel("")
        self.lbl_decisions.setStyleSheet("color: #5f6368; font-size: 11px; padding: 4px 0;")
        self._update_decision_log()

        # Layout assembly
        right_pane = QVBoxLayout()
        right_pane.addWidget(self.lbl_confidence)
        right_pane.addLayout(compare_row, 1)
        right_pane.addWidget(self.lbl_rationale)
        right_pane.addLayout(actions)

        main_row = QHBoxLayout()
        main_row.addWidget(self.list_widget, 0)
        main_row.addLayout(right_pane, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.close)

        header = QHBoxLayout()
        header.addWidget(self.lbl_title)
        header.addStretch()
        header.addWidget(self.lbl_subtitle)

        outer = QVBoxLayout(self)
        outer.addLayout(header)
        outer.addLayout(main_row, 1)
        outer.addWidget(self.lbl_decisions)
        outer.addWidget(buttons)

        # Signal wiring
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.btn_merge.clicked.connect(self._emit_merge)
        self.btn_reject.clicked.connect(self._emit_reject)
        self.btn_skip.clicked.connect(self._emit_skip)

    def set_suggestions(self, suggestions):
        self.list_widget.clear()
        suggestions = list(suggestions or [])

        self.lbl_subtitle.setText(f"Possible merges: {len(suggestions)}")

        for item in suggestions:
            left_id = str(item.get("left_id", ""))
            right_id = str(item.get("right_id", ""))
            score = item.get("score")
            left_count = item.get("left_count", "?")
            right_count = item.get("right_count", "?")

            score_txt = f"{score:.2f}" if isinstance(score, (float, int)) else "?"
            label = f"{left_id} \u2194 {right_id}\nscore {score_txt}  |  {left_count} vs {right_count}"

            list_item = QListWidgetItem(label)
            list_item.setData(256, (left_id, right_id))
            list_item.setData(257, item)  # store full suggestion data

            # Confidence color coding
            bg_color, text_color = _confidence_color(score)
            list_item.setBackground(QColor(bg_color))
            list_item.setForeground(QColor(text_color))

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

        # Show confidence info from stored suggestion data
        suggestion = current.data(257)
        if isinstance(suggestion, dict):
            score = suggestion.get("score")
            if isinstance(score, (float, int)):
                _, text_color = _confidence_color(score)
                confidence_text = f"Merge confidence: {score:.2f}"
                if score >= 0.85:
                    confidence_text += " (high)"
                elif score >= 0.70:
                    confidence_text += " (moderate)"
                else:
                    confidence_text += " (review carefully)"
                self.lbl_confidence.setText(confidence_text)
                self.lbl_confidence.setStyleSheet(
                    f"font-size: 13px; padding: 4px; color: {text_color}; font-weight: 600;"
                )
            else:
                self.lbl_confidence.setText("")

            rationale = suggestion.get("rationale", {})
            if isinstance(rationale, dict) and rationale:
                parts = [f"{k}: {v}" for k, v in rationale.items()]
                self.lbl_rationale.setText(" | ".join(parts))
            else:
                self.lbl_rationale.setText("")
        else:
            self.lbl_confidence.setText("")
            self.lbl_rationale.setText("")

        self.reviewRequested.emit(left_id, right_id)

    def _advance_to_next(self):
        """Auto-advance to next pair after action."""
        row = self.list_widget.currentRow()
        self.list_widget.takeItem(row)
        self.lbl_subtitle.setText(f"Possible merges: {self.list_widget.count()}")
        if self.list_widget.count() > 0:
            next_row = min(row, self.list_widget.count() - 1)
            self.list_widget.setCurrentRow(next_row)
        else:
            self._current_pair = None
            self.lbl_confidence.setText("All pairs reviewed!")
            self.lbl_rationale.setText("")

    def _update_decision_log(self):
        c = self._decision_counts
        self.lbl_decisions.setText(
            f"Decisions: merged {c['merged']}, rejected {c['rejected']}, "
            f"skipped {c['skipped']}"
        )

    def _emit_merge(self):
        if self._current_pair:
            self._decision_counts["merged"] += 1
            self._update_decision_log()
            self.mergeAccepted.emit(*self._current_pair)
            self._advance_to_next()

    def _emit_reject(self):
        if self._current_pair:
            self._decision_counts["rejected"] += 1
            self._update_decision_log()
            self.mergeRejected.emit(*self._current_pair)
            self._advance_to_next()

    def _emit_skip(self):
        if self._current_pair:
            self._decision_counts["skipped"] += 1
            self._update_decision_log()
            self.mergePostponed.emit(*self._current_pair)
            self._advance_to_next()
