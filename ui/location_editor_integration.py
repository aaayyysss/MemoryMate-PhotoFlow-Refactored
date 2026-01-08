#!/usr/bin/env python3
"""Location Editor Integration

Helper functions for integrating location editing into photo context menus
and other UI components.

Usage:
    from ui.location_editor_integration import edit_photo_location

    # In your context menu handler:
    def on_edit_location():
        edit_photo_location(photo_path, parent_widget)
"""

import logging
from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import QWidget, QMessageBox

logger = logging.getLogger(__name__)


def get_photo_location(photo_path: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Get current GPS location for a photo from database.

    Args:
        photo_path: Path to photo file

    Returns:
        Tuple of (latitude, longitude, location_name) or (None, None, None)
    """
    try:
        from reference_db import ReferenceDB

        db = ReferenceDB()

        with db._connect() as conn:
            cur = conn.cursor()

            # Check if GPS columns exist (Row objects use dict-like access)
            existing_cols = [r['name'] for r in cur.execute("PRAGMA table_info(photo_metadata)")]
            if 'gps_latitude' not in existing_cols or 'gps_longitude' not in existing_cols:
                return (None, None, None)

            # Get GPS data for photo
            cur.execute("""
                SELECT gps_latitude, gps_longitude, location_name
                FROM photo_metadata
                WHERE path = ?
            """, (photo_path,))

            row = cur.fetchone()
            if row:
                return (row['gps_latitude'], row['gps_longitude'], row['location_name'])

            return (None, None, None)

    except Exception as e:
        logger.error(f"[LocationEditor] Failed to get photo location: {e}")
        return (None, None, None)


def save_photo_location(photo_path: str, latitude: Optional[float],
                       longitude: Optional[float], location_name: Optional[str]) -> bool:
    """
    Save GPS location for a photo to database.

    Args:
        photo_path: Path to photo file
        latitude: GPS latitude or None to clear
        longitude: GPS longitude or None to clear
        location_name: Location name or None

    Returns:
        True if successful, False otherwise
    """
    try:
        from reference_db import ReferenceDB

        db = ReferenceDB()
        db.update_photo_gps(photo_path, latitude, longitude, location_name)

        logger.info(f"[LocationEditor] Saved location for {Path(photo_path).name}: ({latitude}, {longitude}) - {location_name}")
        return True

    except Exception as e:
        logger.error(f"[LocationEditor] Failed to save photo location: {e}")
        return False


def edit_photo_location(photo_path: str, parent: Optional[QWidget] = None) -> bool:
    """
    Show location editor dialog for a photo.

    This is the main entry point for editing photo locations from context menus.

    Args:
        photo_path: Path to photo file
        parent: Parent widget for dialog

    Returns:
        True if location was changed, False if cancelled or error
    """
    try:
        from ui.location_editor_dialog import LocationEditorDialog

        # Get current location
        current_lat, current_lon, current_name = get_photo_location(photo_path)

        # Show editor dialog
        dialog = LocationEditorDialog(
            photo_path=photo_path,
            current_lat=current_lat,
            current_lon=current_lon,
            current_name=current_name,
            parent=parent
        )

        # Connect save signal
        location_saved = [False]  # Use list for closure

        def on_location_saved(lat, lon, name):
            success = save_photo_location(photo_path, lat, lon, name)
            if success:
                location_saved[0] = True

                if lat is not None and lon is not None:
                    QMessageBox.information(
                        parent,
                        "Location Saved",
                        f"✓ Location updated successfully!\n\n"
                        f"Coordinates: ({lat:.6f}, {lon:.6f})\n"
                        f"Location: {name if name else 'Not specified'}\n\n"
                        f"The photo will now appear in the Locations section."
                    )
                else:
                    QMessageBox.information(
                        parent,
                        "Location Cleared",
                        "✓ Location data removed from photo."
                    )
            else:
                QMessageBox.critical(
                    parent,
                    "Error",
                    "Failed to save location data.\nPlease check the logs for details."
                )

        dialog.locationSaved.connect(on_location_saved)

        # Show dialog
        result = dialog.exec()

        return location_saved[0]

    except Exception as e:
        logger.error(f"[LocationEditor] Failed to show dialog: {e}")
        QMessageBox.critical(
            parent,
            "Error",
            f"Failed to open location editor:\n{e}"
        )
        return False


# Example: Adding to photo context menu
def create_location_menu_action(photo_path: str, parent: QWidget):
    """
    Create a QAction for "Edit Location" context menu item.

    Example usage:
        from ui.location_editor_integration import create_location_menu_action

        # In your photo grid/list widget:
        def create_context_menu(photo_path):
            menu = QMenu()

            # ... other actions ...

            location_action = create_location_menu_action(photo_path, self)
            menu.addAction(location_action)

            return menu

    Args:
        photo_path: Path to photo file
        parent: Parent widget

    Returns:
        QAction configured for location editing
    """
    from PySide6.QtGui import QAction

    action = QAction("📍 Edit Location...", parent)
    action.setToolTip("Add or edit GPS location for this photo")
    action.triggered.connect(lambda: edit_photo_location(photo_path, parent))

    return action


if __name__ == '__main__':
    # Test the integration
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Test with a sample photo path
    test_photo = "/path/to/test/photo.jpg"
    print(f"Testing location editor for: {test_photo}")

    # Get current location
    lat, lon, name = get_photo_location(test_photo)
    print(f"Current location: ({lat}, {lon}) - {name}")

    # Show editor
    result = edit_photo_location(test_photo)
    print(f"Edit result: {result}")

    sys.exit(0)
