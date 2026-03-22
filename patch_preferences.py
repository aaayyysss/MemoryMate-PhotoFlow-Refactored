
import sys

filepath = 'preferences_dialog.py'
with open(filepath, 'rb') as f:
    content = f.read()

# Using bytes to handle CRLF correctly
search_text = b'        self.chk_auto_cluster = QCheckBox("Auto-cluster after face detection scan")\r\n        self.chk_auto_cluster.setToolTip("Automatically group faces after detection completes")\r\n        cluster_layout.addRow("", self.chk_auto_cluster)\r\n\r\n        layout.addWidget(cluster_group)'

replacement_text = b'''        self.chk_auto_cluster = QCheckBox("Auto-cluster after face detection scan")
        self.chk_auto_cluster.setToolTip("Automatically group faces after detection completes")
        cluster_layout.addRow("", self.chk_auto_cluster)

        layout.addWidget(cluster_group)

        # Screenshot Face Handling
        screenshot_group = QGroupBox("Screenshot Face Handling")
        screenshot_layout = QFormLayout(screenshot_group)
        screenshot_layout.setSpacing(10)

        self.cmb_screenshot_face_policy = QComboBox()
        self.cmb_screenshot_face_policy.addItem("Exclude screenshots", "exclude")
        self.cmb_screenshot_face_policy.addItem("Detect only, exclude from clustering", "detect_only")
        self.cmb_screenshot_face_policy.addItem("Detect and cluster screenshots", "include_cluster")
        self.cmb_screenshot_face_policy.setToolTip(
            "Default screenshot handling policy for face detection and clustering.\\n"
            "This can still be overridden in the Face Detection dialog for a specific run."
        )
        screenshot_layout.addRow("Default Screenshot Policy:", self.cmb_screenshot_face_policy)

        self.chk_include_all_screenshot_faces = QCheckBox(
            "When clustering screenshots, keep all detected screenshot faces"
        )
        self.chk_include_all_screenshot_faces.setToolTip(
            "If enabled, screenshot-origin faces will not be capped before clustering.\\n"
            "Warning: this may increase noise and singleton clusters."
        )
        screenshot_layout.addRow("", self.chk_include_all_screenshot_faces)

        layout.addWidget(screenshot_group)'''.replace(b'\n', b'\r\n')

if search_text in content:
    new_content = content.replace(search_text, replacement_text)
    with open(filepath, 'wb') as f:
        f.write(new_content)
    print("Patch 2.1 applied successfully")
else:
    print("Search text not found for Patch 2.1")

# Patch 2.2
search_text_2 = b'        self.chk_show_low_conf.setChecked(self.face_config.get("show_low_confidence", False))'
replacement_text_2 = b'''        self.chk_show_low_conf.setChecked(self.face_config.get("show_low_confidence", False))

        # Screenshot policy
        policy = self.settings.get("screenshot_face_policy", "detect_only")
        idx = self.cmb_screenshot_face_policy.findData(policy)
        if idx >= 0:
            self.cmb_screenshot_face_policy.setCurrentIndex(idx)

        self.chk_include_all_screenshot_faces.setChecked(
            self.settings.get("include_all_screenshot_faces", False)
        )'''.replace(b'\n', b'\r\n')

with open(filepath, 'rb') as f:
    content = f.read()

if search_text_2 in content:
    new_content = content.replace(search_text_2, replacement_text_2)
    with open(filepath, 'wb') as f:
        f.write(new_content)
    print("Patch 2.2 applied successfully")
else:
    print("Search text not found for Patch 2.2")

# Patch 2.3
search_text_3 = b'        # UI low-confidence toggle\r\n        self.face_config.set("show_low_confidence", self.chk_show_low_conf.isChecked(), save_now=False)'
replacement_text_3 = b'''        # UI low-confidence toggle
        self.face_config.set("show_low_confidence", self.chk_show_low_conf.isChecked(), save_now=False)

        # Screenshot policy defaults
        self.settings.set("screenshot_face_policy", self.cmb_screenshot_face_policy.currentData())
        self.settings.set("include_all_screenshot_faces", self.chk_include_all_screenshot_faces.isChecked())'''.replace(b'\n', b'\r\n')

with open(filepath, 'rb') as f:
    content = f.read()

if search_text_3 in content:
    new_content = content.replace(search_text_3, replacement_text_3)
    with open(filepath, 'wb') as f:
        f.write(new_content)
    print("Patch 2.3 applied successfully")
else:
    print("Search text not found for Patch 2.3")
