
import sys
import os
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from main_window_qt import MainWindow
from ui.embedding_stats_dashboard import EmbeddingStatsDashboard
from repository.project_repository import ProjectRepository
from repository.base_repository import DatabaseConnection

def capture_ui():
    print("Starting UI Capture...")
    app = QApplication.instance() or QApplication(sys.argv)

    # Setup: Create a project if none exists
    db_conn = DatabaseConnection()
    repo = ProjectRepository(db_conn)
    projects = repo.get_all_with_details()

    if not projects:
        repo.create("Test Project", "/tmp", "scan")
        projects = repo.get_all_with_details()

    pid = projects[0]['id']

    # Create Main Window
    mw = MainWindow()
    mw.show()

    # Take screenshot of MainWindow
    print("Capturing MainWindow...")
    QApplication.processEvents()
    time.sleep(1) # Wait for layout
    QApplication.processEvents()
    pix = mw.grab()
    pix.save("/home/jules/verification/mainwindow.png")
    print("MainWindow saved.")

    # Create a project with a legacy model to force the upgrade section
    # We'll mock the check in the dashboard or actually install a fake better model
    # For verification, we just want to see the UI.

    print("Capturing EmbeddingStatsDashboard (Legacy)...")
    legacy_pid = repo.create("Legacy Project", "/tmp", "scan", semantic_model="openai/clip-vit-base-patch32")

    # Mock best available model to be something else to force upgrade section
    old_best = repo._get_best_available_model
    repo._get_best_available_model = lambda: "openai/clip-vit-large-patch14"

    dashboard = EmbeddingStatsDashboard(legacy_pid, parent=mw)
    dashboard.show()
    QApplication.processEvents()
    time.sleep(1)
    QApplication.processEvents()

    pix = dashboard.grab()
    pix.save("/home/jules/verification/dashboard_upgrade.png")
    print("Dashboard with upgrade saved.")

    dashboard.close()
    mw.close()
    print("UI Capture Finished.")

if __name__ == "__main__":
    if not os.path.exists("/home/jules/verification"):
        os.makedirs("/home/jules/verification")

    try:
        capture_ui()
    except Exception as e:
        print(f"UI Capture failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
