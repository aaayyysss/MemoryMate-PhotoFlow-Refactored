from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame


class SmartFindCard(QFrame):
    clicked = Signal(str)

    def __init__(self, preset_id: str, title: str, icon_text: str = "", parent=None):
        super().__init__(parent)
        self.preset_id = preset_id
        self._active = False
        self._count = None

        self.setObjectName("SmartFindCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)

        self.lbl_icon = QLabel(icon_text)
        self.lbl_icon.setObjectName("SmartFindCardIcon")

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("SmartFindCardTitle")

        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("SmartFindCardCount")
        self.lbl_count.setVisible(False)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)
        header_row.addWidget(self.lbl_icon)
        header_row.addWidget(self.lbl_title, 1)
        header_row.addWidget(self.lbl_count)

        self.preview_row = QHBoxLayout()
        self.preview_row.setContentsMargins(0, 0, 0, 0)
        self.preview_row.setSpacing(4)

        self.preview_host = QWidget()
        self.preview_host.setLayout(self.preview_row)
        self.preview_host.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        layout.addLayout(header_row)
        layout.addWidget(self.preview_host)

        self._apply_style()

    def set_count(self, count: int | None):
        self._count = count
        if count is None:
            self.lbl_count.setVisible(False)
            self.lbl_count.setText("")
        else:
            self.lbl_count.setVisible(True)
            self.lbl_count.setText(str(count))

    def set_active(self, active: bool):
        self._active = bool(active)
        self._apply_style()

    def set_preview_labels(self, labels: list[str] | None):
        while self.preview_row.count():
            item = self.preview_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        labels = list(labels or [])[:3]
        self.preview_host.setVisible(bool(labels))

        for text in labels:
            lbl = QLabel(text)
            lbl.setObjectName("SmartFindCardPreview")
            self.preview_row.addWidget(lbl)

        self.preview_row.addStretch(1)

    def _apply_style(self):
        if self._active:
            self.setStyleSheet("""
                QFrame#SmartFindCard {
                    background: #d2e3fc;
                    border: 1px solid #8ab4f8;
                    border-radius: 8px;
                }
                QLabel#SmartFindCardTitle {
                    font-weight: 600;
                }
                QLabel#SmartFindCardCount {
                    color: #174ea6;
                    font-weight: 600;
                }
                QLabel#SmartFindCardPreview {
                    background: #ffffff;
                    border: 1px solid #c6dafc;
                    border-radius: 6px;
                    padding: 2px 6px;
                    font-size: 9pt;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#SmartFindCard {
                    background: #ffffff;
                    border: 1px solid #dadce0;
                    border-radius: 8px;
                }
                QFrame#SmartFindCard:hover {
                    background: #f8f9fa;
                    border: 1px solid #c6c6c6;
                }
                QLabel#SmartFindCardTitle {
                    font-weight: 500;
                }
                QLabel#SmartFindCardCount {
                    color: #5f6368;
                    font-weight: 600;
                }
                QLabel#SmartFindCardPreview {
                    background: #f1f3f4;
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    padding: 2px 6px;
                    font-size: 9pt;
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.preset_id)
        super().mousePressEvent(event)
