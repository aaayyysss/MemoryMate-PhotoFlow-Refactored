
import sys

filepath = 'ui/face_detection_scope_dialog.py'
with open(filepath, 'rb') as f:
    content = f.read()

# Using bytes to handle CRLF correctly
search_text_1 = b'    # Signal emitted when user clicks "Start Detection"\r\n    # Emits list of photo paths to process and the chosen screenshot policy\r\n    scopeSelected = Signal(list, str)  # List[str], str policy\r\n\r\n    def __init__(self, project_id: int, parent=None):\r\n        super().__init__(parent)\r\n        self.project_id = project_id\r\n        self.db = ReferenceDB()'

replacement_text_1 = b'''    # Signal emitted when user clicks "Start Detection"
    # Emits list of photo paths to process, chosen screenshot policy, and include-all flag
    scopeSelected = Signal(list, str, bool)  # List[str], str policy, bool include_all

    def __init__(self, project_id: int, parent=None):
        super().__init__(parent)
        from settings_manager_qt import SettingsManager
        self.settings = SettingsManager()
        self.project_id = project_id
        self.db = ReferenceDB()'''.replace(b'\n', b'\r\n')

if search_text_1 in content:
    content = content.replace(search_text_1, replacement_text_1)
    print("Patch 3.1a applied")
else:
    print("Search text 1 not found")

# Patch 3.2 (UI controls)
search_text_2 = b'        self.cmb_screenshot_policy.setCurrentIndex(1)\r\n        policy_layout.addWidget(self.lbl_screenshot_policy)\r\n        policy_layout.addWidget(self.cmb_screenshot_policy, 1)\r\n        layout.addLayout(policy_layout)\r\n\r\n        self.lbl_screenshot_note = QLabel(\r\n            "Note: \'Detect and cluster screenshots\' makes screenshot faces eligible for People clustering, "\r\n            "but crowded screenshots may still be capped or filtered for quality."\r\n        )'

replacement_text_2 = b'''        default_policy = "detect_only"
        try:
            default_policy = self.settings.get("screenshot_face_policy", "detect_only")
        except Exception:
            pass

        idx = self.cmb_screenshot_policy.findData(default_policy)
        if idx >= 0:
            self.cmb_screenshot_policy.setCurrentIndex(idx)
        else:
            self.cmb_screenshot_policy.setCurrentIndex(1)

        policy_layout.addWidget(self.lbl_screenshot_policy)
        policy_layout.addWidget(self.cmb_screenshot_policy, 1)
        layout.addLayout(policy_layout)

        self.chk_include_all_screenshot_faces = QCheckBox(
            "Keep all detected screenshot faces"
        )
        self.chk_include_all_screenshot_faces.setToolTip(
            "If enabled, screenshot-origin detections will not be capped before clustering.\\n"
            "Warning: this may increase noise and singleton clusters."
        )

        try:
            self.chk_include_all_screenshot_faces.setChecked(
                self.settings.get("include_all_screenshot_faces", False)
            )
        except Exception:
            self.chk_include_all_screenshot_faces.setChecked(False)

        layout.addWidget(self.chk_include_all_screenshot_faces)

        self.lbl_screenshot_note = QLabel(
            "Note: \'Detect and cluster screenshots\' makes screenshot faces eligible for People clustering, "
            "but crowded screenshots may still be capped or filtered for quality."
        )'''.replace(b'\n', b'\r\n')

if search_text_2 in content:
    content = content.replace(search_text_2, replacement_text_2)
    print("Patch 3.2 applied")
else:
    print("Search text 2 not found")

# Patch 3.3 (Getter)
search_text_3 = b'    def get_screenshot_policy(self) -> str:\r\n        """Return the selected screenshot policy."""\r\n        return self.cmb_screenshot_policy.currentData() or "detect_only"\r\n\r\n    def _on_folder_selection_changed(self, item: QTreeWidgetItem, column: int):'

replacement_text_3 = b'''    def get_screenshot_policy(self) -> str:
        """Return the selected screenshot policy."""
        return self.cmb_screenshot_policy.currentData() or "detect_only"

    def get_include_all_screenshot_faces(self) -> bool:
        """Return the state of the include-all checkbox."""
        return bool(self.chk_include_all_screenshot_faces.isChecked())

    def _on_folder_selection_changed(self, item: QTreeWidgetItem, column: int):'''.replace(b'\n', b'\r\n')

if search_text_3 in content:
    content = content.replace(search_text_3, replacement_text_3)
    print("Patch 3.3 applied")
else:
    print("Search text 3 not found")

# Patch 3.4 (Emit)
search_text_4 = b'        # Emit signal with paths and policy\r\n        self.scopeSelected.emit(paths_to_process, self.get_screenshot_policy())\r\n        self.accept()'

replacement_text_4 = b'''        # Emit signal with paths, policy and include-all flag
        self.scopeSelected.emit(
            paths_to_process,
            self.get_screenshot_policy(),
            self.get_include_all_screenshot_faces(),
        )
        self.accept()'''.replace(b'\n', b'\r\n')

if search_text_4 in content:
    content = content.replace(search_text_4, replacement_text_4)
    print("Patch 3.4 applied")
else:
    print("Search text 4 not found")

with open(filepath, 'wb') as f:
    f.write(content)
