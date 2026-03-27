from PySide6.QtCore import Qt, Signal, QPoint, QTimer
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton, QToolButton,
    QFrame, QVBoxLayout, QListWidget, QListWidgetItem, QLabel
)


class TopSearchBar(QWidget):
    querySubmitted = Signal(str)
    queryChanged = Signal(str)
    searchCleared = Signal()
    recentQueryClicked = Signal(str)
    suggestionClicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._recent_queries = []
        self._suggestions = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search photos, people, places, screenshots...")

        self.btn_recent = QToolButton()
        self.btn_recent.setText("▾")
        self.btn_recent.setToolTip("Recent searches")

        self.btn_clear = QPushButton("✕")
        self.btn_clear.setFixedWidth(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.search_input, 1)
        layout.addWidget(self.btn_recent)
        layout.addWidget(self.btn_clear)

        self.popup = QFrame(None, Qt.Popup)
        self.popup.setFrameShape(QFrame.StyledPanel)
        self.popup.setMinimumWidth(360)

        popup_layout = QVBoxLayout(self.popup)
        popup_layout.setContentsMargins(6, 6, 6, 6)
        popup_layout.setSpacing(4)

        self.lbl_recent = QLabel("Recent")
        self.list_recent = QListWidget()
        self.list_recent.setMaximumHeight(120)

        self.lbl_suggestions = QLabel("Suggestions")
        self.list_suggestions = QListWidget()
        self.list_suggestions.setMaximumHeight(160)

        popup_layout.addWidget(self.lbl_recent)
        popup_layout.addWidget(self.list_recent)
        popup_layout.addWidget(self.lbl_suggestions)
        popup_layout.addWidget(self.list_suggestions)

        # UX-11: debounce timer for smoother typing experience
        self._query_debounce = QTimer(self)
        self._query_debounce.setInterval(250)
        self._query_debounce.setSingleShot(True)
        self._query_debounce.timeout.connect(self._emit_debounced_query)

        self.search_input.returnPressed.connect(self._emit_submit)
        self.search_input.textChanged.connect(self._on_text_changed)
        self.btn_clear.clicked.connect(self._clear)
        self.btn_recent.clicked.connect(self._toggle_popup)

        self.list_recent.itemClicked.connect(self._on_recent_clicked)
        self.list_suggestions.itemClicked.connect(self._on_suggestion_clicked)

    def _on_text_changed(self, text: str):
        self._query_debounce.start()
        self._refresh_popup_visibility()

    def _emit_debounced_query(self):
        text = self.search_input.text()
        self.queryChanged.emit(text)

    def _emit_submit(self):
        text = self.search_input.text().strip()
        if text:
            self.querySubmitted.emit(text)

    def _clear(self):
        self.search_input.clear()
        self.popup.hide()
        self.searchCleared.emit()

    def _toggle_popup(self):
        if self.popup.isVisible():
            self.popup.hide()
            return

        self._refresh_popup_contents()
        self._show_popup()

    def _show_popup(self):
        pos = self.search_input.mapToGlobal(QPoint(0, self.search_input.height() + 2))
        self.popup.move(pos)
        self.popup.resize(max(self.search_input.width() + self.btn_recent.width() + self.btn_clear.width() + 6, 360), self.popup.sizeHint().height())
        self.popup.show()
        self.popup.raise_()

    def _refresh_popup_visibility(self):
        text = self.search_input.text().strip().lower()

        if not text and not self._recent_queries:
            self.popup.hide()
            return

        self._refresh_popup_contents(text)

        if self.search_input.hasFocus():
            self._show_popup()

    def _refresh_popup_contents(self, text: str = ""):
        self.list_recent.clear()
        self.list_suggestions.clear()

        filtered_recent = self._recent_queries
        if text:
            filtered_recent = [q for q in self._recent_queries if text in q.lower()]

        for q in filtered_recent[:8]:
            self.list_recent.addItem(QListWidgetItem(q))

        filtered_suggestions = self._suggestions
        if text:
            filtered_suggestions = [s for s in self._suggestions if text in s.lower()]

        for s in filtered_suggestions[:10]:
            self.list_suggestions.addItem(QListWidgetItem(s))

        self.lbl_recent.setVisible(self.list_recent.count() > 0)
        self.list_recent.setVisible(self.list_recent.count() > 0)
        self.lbl_suggestions.setVisible(self.list_suggestions.count() > 0)
        self.list_suggestions.setVisible(self.list_suggestions.count() > 0)

    def _on_recent_clicked(self, item):
        text = item.text().strip()
        self.search_input.setText(text)
        self.popup.hide()
        self.recentQueryClicked.emit(text)
        self.querySubmitted.emit(text)

    def _on_suggestion_clicked(self, item):
        text = item.text().strip()
        self.search_input.setText(text)
        self.popup.hide()
        self.suggestionClicked.emit(text)
        self.querySubmitted.emit(text)

    def set_query_text(self, text: str):
        if self.search_input.text() != text:
            self.search_input.setText(text)

    def set_recent_queries(self, queries):
        self._recent_queries = list(queries or [])

    def set_suggestions(self, suggestions):
        self._suggestions = list(suggestions or [])

    def set_enabled_for_project(self, enabled: bool):
        self.search_input.setEnabled(enabled)
        self.btn_recent.setEnabled(enabled)
        self.btn_clear.setEnabled(enabled)
        if not enabled:
            self.popup.hide()
