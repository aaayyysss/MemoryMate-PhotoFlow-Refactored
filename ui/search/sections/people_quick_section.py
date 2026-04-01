from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget, QListWidgetItem


class PeopleQuickSection(QGroupBox):
    reviewMergesRequested = Signal()
    reviewUnnamedRequested = Signal()
    showAllPeopleRequested = Signal()
    peopleToolsRequested = Signal()
    personRequested = Signal(str)

    # legacy row actions, kept during parity migration
    mergeHistoryRequested = Signal()
    undoMergeRequested = Signal()
    redoMergeRequested = Signal()
    expandPeopleRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("People", parent)
        self.setObjectName("PeopleQuickSection")
        self._people_rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        subtitle = QLabel("Top people and review tools")
        subtitle.setStyleSheet("color: #5f6368; font-size: 12px;")
        root.addWidget(subtitle)

        self.top_people_list = QListWidget()
        self.top_people_list.setMaximumHeight(160)
        self.top_people_list.itemClicked.connect(
            lambda item: self.personRequested.emit(item.data(Qt.UserRole) or "")
        )
        root.addWidget(self.top_people_list)

        self.btn_review_merges = QPushButton("Review Possible Merges (0)")
        self.btn_review_unnamed = QPushButton("Show Unnamed Clusters (0)")
        self.btn_show_all = QPushButton("Show All People")
        self.btn_tools = QPushButton("People Tools")

        self.btn_review_merges.clicked.connect(self.reviewMergesRequested.emit)
        self.btn_review_unnamed.clicked.connect(self.reviewUnnamedRequested.emit)
        self.btn_show_all.clicked.connect(self.showAllPeopleRequested.emit)
        self.btn_tools.clicked.connect(self.peopleToolsRequested.emit)

        root.addWidget(self.btn_review_merges)
        root.addWidget(self.btn_review_unnamed)
        root.addWidget(self.btn_show_all)
        root.addWidget(self.btn_tools)

        # ---- Legacy row actions parity strip ----
        legacy_label = QLabel("Legacy People Actions")
        legacy_label.setStyleSheet("font-weight: 600; color: #5f6368; margin-top: 6px;")
        root.addWidget(legacy_label)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)

        self.btn_merge_history = QPushButton("History")
        self.btn_undo_merge = QPushButton("Undo")
        self.btn_redo_merge = QPushButton("Redo")
        self.btn_expand_people = QPushButton("Expand")

        self.btn_merge_history.clicked.connect(self.mergeHistoryRequested.emit)
        self.btn_undo_merge.clicked.connect(self.undoMergeRequested.emit)
        self.btn_redo_merge.clicked.connect(self.redoMergeRequested.emit)
        self.btn_expand_people.clicked.connect(self.expandPeopleRequested.emit)

        actions_row.addWidget(self.btn_merge_history)
        actions_row.addWidget(self.btn_undo_merge)
        actions_row.addWidget(self.btn_redo_merge)
        actions_row.addWidget(self.btn_expand_people)

        root.addLayout(actions_row)
        root.addStretch(1)

    def set_people_rows(self, rows: list[dict]) -> None:
        self._people_rows = list(rows or [])
        self.top_people_list.clear()

        for row in self._people_rows[:10]:
            name = (
                row.get("display_name")
                or row.get("canonical_cluster_id")
                or row.get("identity_id")
                or "Unknown"
            )
            count = row.get("count")
            text = f"{name} ({count})" if count is not None else name

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, row.get("identity_id") or "")
            self.top_people_list.addItem(item)

    def set_counts(self, merge_count: int, unnamed_count: int) -> None:
        self.btn_review_merges.setText(f"Review Possible Merges ({merge_count})")
        self.btn_review_unnamed.setText(f"Show Unnamed Clusters ({unnamed_count})")
        self.btn_review_merges.setEnabled(merge_count > 0)
        self.btn_review_unnamed.setEnabled(unnamed_count > 0)

    def set_legacy_actions_enabled(self, enabled: bool) -> None:
        self.btn_merge_history.setEnabled(enabled)
        self.btn_undo_merge.setEnabled(enabled)
        self.btn_redo_merge.setEnabled(enabled)
        self.btn_expand_people.setEnabled(enabled)

    # Legacy compatibility method
    def set_people(self, payload):
        """Legacy set_people method for backward compatibility."""
        payload = payload or {}
        self.set_people_rows(payload.get("top_people", []))
        self.set_counts(
            int(payload.get("merge_candidates", 0) or 0),
            int(payload.get("unnamed_count", 0) or 0),
        )
        self.set_legacy_actions_enabled(bool(payload.get("people_tools_enabled", True)))

    def set_enabled_for_project(self, enabled: bool):
        self.setEnabled(enabled)
