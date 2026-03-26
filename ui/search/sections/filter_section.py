from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QPushButton, QLabel, QFrame, QHBoxLayout


class FilterSection(QGroupBox):
    filterChanged = Signal(str, str)  # kind, value
    clearAllFiltersRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("Filters", parent)
        self.setObjectName("FilterSection")

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(10)

        self._build_facets()
        self.layout.addStretch(1)

        # Clear button
        self.btn_clear = QPushButton("Clear All Filters")
        self.btn_clear.clicked.connect(self.clearFiltersRequested.emit)
        self.layout.addWidget(self.btn_clear)

    def _build_facets(self):
        self.facets = {}
        facet_configs = [
            ("people", "People", ["Family", "Friends", "Work"]),
            ("location", "Location", ["Home", "Office", "Travel"]),
            ("year", "Year", ["2025", "2024", "2023"]),
            ("type", "Type", ["Photos", "Videos", "Screenshots"]),
        ]

        for kind, title, defaults in facet_configs:
            group = QFrame()
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(4)

            lbl = QLabel(f"<b>{title}</b>")
            group_layout.addWidget(lbl)

            container = QFrame()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(4, 0, 0, 0)
            container_layout.setSpacing(2)

            facet_btns = {}
            for val in defaults:
                btn = QPushButton(val)
                btn.setCheckable(True)
                btn.setStyleSheet("QPushButton { text-align: left; border: none; padding: 2px; } QPushButton:checked { font-weight: bold; color: #1a73e8; }")
                btn.clicked.connect(lambda checked, k=kind, v=val: self.filterChanged.emit(k, v))
                container_layout.addWidget(btn)
                facet_btns[val] = btn

            group_layout.addWidget(container)
            self.layout.addWidget(group)
            self.facets[kind] = {
                "label": lbl,
                "container": container,
                "buttons": facet_btns
            }

    def set_facets(self, result_facets: dict, active_filters: dict):
        """Update facet options and counts based on search results."""
        self.set_active_filters(active_filters)

    def set_active_filters(self, active_filters: dict):
        """Sync button checked states with active filters in store."""
        for kind, info in self.facets.items():
            active_val = active_filters.get(kind)
            for val, btn in info["buttons"].items():
                btn.blockSignals(True)
                btn.setChecked(val == active_val)
                btn.blockSignals(False)

    def set_enabled_for_project(self, enabled: bool):
        self.setEnabled(enabled)
