
import os
import sys

def apply_patch(filepath, search_text, replacement_text):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return False

    with open(filepath, 'rb') as f:
        content = f.read()

    if search_text in content:
        new_content = content.replace(search_text, replacement_text)
        with open(filepath, 'wb') as f:
            f.write(new_content)
        print(f"Patch applied successfully to {filepath}")
        return True
    else:
        print(f"Search text not found in {filepath}")
        # Try to debug why
        print("First 100 bytes of search text (hex):", search_text[:100].hex())
        return False

# ui/face_detection_scope_dialog.py patches
filepath = 'ui/face_detection_scope_dialog.py'

# Patch 3.1: Signal and Init
search_1 = b'    # Signal emitted when user clicks "Start Detection"\r\n    # Emits list of photo paths to process and the chosen screenshot policy\n    scopeSelected = Signal(list, str)  # List[str], str policy\r\n\r\n    def __init__(self, project_id: int, parent=None):\r\n        super().__init__(parent)\r\n        self.project_id = project_id\r\n        self.db = ReferenceDB()'

replacement_1 = b'''    # Signal emitted when user clicks "Start Detection"
    # Emits list of photo paths to process, chosen screenshot policy, and include-all flag
    scopeSelected = Signal(list, str, bool)  # List[str], str policy, bool include_all

    def __init__(self, project_id: int, parent=None):
        super().__init__(parent)
        from settings_manager_qt import SettingsManager
        self.settings = SettingsManager()
        self.project_id = project_id
        self.db = ReferenceDB()'''.replace(b'\n', b'\r\n')

apply_patch(filepath, search_1, replacement_1)

# Patch 3.2: UI controls (Screenshot Policy + Checkbox)
search_2 = b'        self.cmb_screenshot_policy.setCurrentIndex(1)\r\n        policy_layout.addWidget(self.lbl_screenshot_policy)\r\n        policy_layout.addWidget(self.cmb_screenshot_policy, 1)\r\n        layout.addLayout(policy_layout)\r\n\r\n        self.lbl_screenshot_note = QLabel(\r\n            "Note: \'Detect and cluster screenshots\' makes screenshot faces eligible for People clustering, "\r\n            "but crowded screenshots may still be capped or filtered for quality."\r\n        )'

replacement_2 = b'''        default_policy = "detect_only"
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

apply_patch(filepath, search_2, replacement_2)

# Patch 3.3: Getters
search_3 = b'    def get_screenshot_policy(self) -> str:\r\n        """Return the selected screenshot policy."""\r\n        return self.cmb_screenshot_policy.currentData() or "detect_only"\r\n\r\n    def _on_folder_selection_changed(self, item: QTreeWidgetItem, column: int):'

replacement_3 = b'''    def get_screenshot_policy(self) -> str:
        """Return the selected screenshot policy."""
        return self.cmb_screenshot_policy.currentData() or "detect_only"

    def get_include_all_screenshot_faces(self) -> bool:
        """Return the state of the include-all checkbox."""
        return bool(self.chk_include_all_screenshot_faces.isChecked())

    def _on_folder_selection_changed(self, item: QTreeWidgetItem, column: int):'''.replace(b'\n', b'\r\n')

apply_patch(filepath, search_3, replacement_3)

# Patch 3.4: Start Detection Emit
search_4 = b'        # Emit signal with paths and policy\r\n        self.scopeSelected.emit(paths_to_process, self.get_screenshot_policy())\r\n        self.accept()'

replacement_4 = b'''        # Emit signal with paths, policy and include-all flag
        self.scopeSelected.emit(
            paths_to_process,
            self.get_screenshot_policy(),
            self.get_include_all_screenshot_faces(),
        )
        self.accept()'''.replace(b'\n', b'\r\n')

apply_patch(filepath, search_4, replacement_4)
