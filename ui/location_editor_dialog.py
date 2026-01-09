#!/usr/bin/env python3
"""Location Editor Dialog

Allows users to manually add or edit GPS location for photos.
Similar to Google Photos' "Add location" / "Edit location" feature.

Features:
- View current location (if available)
- Enter coordinates manually (latitude, longitude)
- Enter location name manually
- Optional: Geocode coordinates to get location name
- Validate coordinates (-90 to 90 lat, -180 to 180 lon)
- Preview location on map (opens in browser)
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLabel, QLineEdit, QPushButton, QTextEdit,
                               QMessageBox, QGroupBox, QListWidget, QListWidgetItem)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
import logging

logger = logging.getLogger(__name__)


class LocationEditorDialog(QDialog):
    """
    Dialog for editing photo GPS location.

    Allows manual entry of:
    - Latitude (-90 to 90)
    - Longitude (-180 to 180)
    - Location name (city, country, etc.)

    Optional features:
    - Geocode coordinates → location name
    - Open location in browser map (OpenStreetMap)
    """

    # Signal emitted when location is saved
    locationSaved = Signal(float, float, str)  # lat, lon, location_name

    def __init__(self, photo_path=None, current_lat=None, current_lon=None, current_name=None,
                 parent=None, batch_mode=False, batch_count=1):
        """
        Initialize location editor dialog.

        Args:
            photo_path: Path to photo being edited (or count string for batch mode)
            current_lat: Current latitude (if any)
            current_lon: Current longitude (if any)
            current_name: Current location name (if any)
            parent: Parent widget
            batch_mode: If True, editing multiple photos at once
            batch_count: Number of photos being edited in batch mode
        """
        super().__init__(parent)

        self.photo_path = photo_path
        self.current_lat = current_lat
        self.current_lon = current_lon
        self.current_name = current_name
        self.batch_mode = batch_mode
        self.batch_count = batch_count

        if batch_mode:
            self.setWindowTitle(f"Edit Location - {batch_count} Photos")
        else:
            self.setWindowTitle("Edit Location")

        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self._init_ui()
        self._load_current_location()

    def _init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Photo info
        if self.photo_path:
            from pathlib import Path
            photo_label = QLabel(f"📷 {Path(self.photo_path).name}")
            photo_label.setStyleSheet("font-weight: bold; padding: 8px; background: #f0f0f0; border-radius: 4px;")
            layout.addWidget(photo_label)

        # CRITICAL FIX: Location search by name (forward geocoding)
        search_group = QGroupBox("🔍 Search for Location")
        search_layout = QVBoxLayout()

        # Search input row
        search_input_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("e.g., Golden Gate Bridge, San Francisco, Paris...")
        self.search_input.returnPressed.connect(self._search_location)  # Search on Enter
        search_input_layout.addWidget(self.search_input)

        self.search_btn = QPushButton("🔍 Search")
        self.search_btn.clicked.connect(self._search_location)
        self.search_btn.setStyleSheet("background: #1a73e8; color: white; padding: 6px 16px; font-weight: bold;")
        search_input_layout.addWidget(self.search_btn)

        search_layout.addLayout(search_input_layout)

        # Search results list
        self.search_results = QListWidget()
        self.search_results.setMaximumHeight(120)
        self.search_results.setStyleSheet("""
            QListWidget {
                border: 1px solid #dadce0;
                border-radius: 4px;
                background: #f8f9fa;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #e8eaed;
            }
            QListWidget::item:hover {
                background: #e8f0fe;
            }
            QListWidget::item:selected {
                background: #1a73e8;
                color: white;
            }
        """)
        self.search_results.itemDoubleClicked.connect(self._on_search_result_selected)
        self.search_results.hide()  # Hidden initially
        search_layout.addWidget(self.search_results)

        # Help text
        search_help = QLabel("💡 Type a place name and click Search, or press Enter")
        search_help.setStyleSheet("font-size: 10pt; color: #666; font-style: italic;")
        search_layout.addWidget(search_help)

        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # Current location display
        current_group = QGroupBox("Current Location")
        current_layout = QVBoxLayout()

        self.current_display = QLabel()
        self.current_display.setWordWrap(True)
        self.current_display.setStyleSheet("padding: 8px; color: #666;")
        current_layout.addWidget(self.current_display)

        current_group.setLayout(current_layout)
        layout.addWidget(current_group)

        # Coordinate input
        coord_group = QGroupBox("GPS Coordinates")
        coord_layout = QFormLayout()

        # Latitude input
        self.lat_input = QLineEdit()
        self.lat_input.setPlaceholderText("e.g., 37.7749")
        lat_validator = QDoubleValidator(-90.0, 90.0, 6)
        lat_validator.setNotation(QDoubleValidator.StandardNotation)
        self.lat_input.setValidator(lat_validator)
        coord_layout.addRow("Latitude (-90 to 90):", self.lat_input)

        # Longitude input
        self.lon_input = QLineEdit()
        self.lon_input.setPlaceholderText("e.g., -122.4194")
        lon_validator = QDoubleValidator(-180.0, 180.0, 6)
        lon_validator.setNotation(QDoubleValidator.StandardNotation)
        self.lon_input.setValidator(lon_validator)
        coord_layout.addRow("Longitude (-180 to 180):", self.lon_input)

        # Map preview button
        map_btn_layout = QHBoxLayout()
        self.map_preview_btn = QPushButton("🗺️ Preview on Map")
        self.map_preview_btn.clicked.connect(self._preview_on_map)
        map_btn_layout.addWidget(self.map_preview_btn)
        map_btn_layout.addStretch()
        coord_layout.addRow("", map_btn_layout)

        coord_group.setLayout(coord_layout)
        layout.addWidget(coord_group)

        # Location name input
        name_group = QGroupBox("Location Name")
        name_layout = QVBoxLayout()

        name_input_layout = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., San Francisco, California, USA")
        name_input_layout.addRow("Name:", self.name_input)

        name_layout.addLayout(name_input_layout)

        # Geocode button
        geocode_layout = QHBoxLayout()
        self.geocode_btn = QPushButton("🌍 Get Location Name from Coordinates")
        self.geocode_btn.clicked.connect(self._geocode_coordinates)
        geocode_layout.addWidget(self.geocode_btn)
        geocode_layout.addStretch()
        name_layout.addLayout(geocode_layout)

        name_group.setLayout(name_layout)
        layout.addWidget(name_group)

        # Help text
        help_text = QLabel(
            "💡 Tips:\n"
            "• Get coordinates from Google Maps: Right-click → Copy coordinates\n"
            "• Click 'Get Location Name' to automatically find location name\n"
            "• Preview shows location on OpenStreetMap"
        )
        help_text.setStyleSheet("padding: 12px; background: #f8f9fa; border-radius: 4px; color: #666;")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()

        clear_btn = QPushButton("Clear Location")
        clear_btn.clicked.connect(self._clear_location)
        button_layout.addWidget(clear_btn)

        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_location)
        save_btn.setStyleSheet("background: #1a73e8; color: white; padding: 6px 20px; font-weight: bold;")
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _load_current_location(self):
        """Load and display current location data."""
        if self.batch_mode:
            # Batch mode display
            if self.current_lat is not None and self.current_lon is not None:
                # All photos have same location
                name_str = f" - {self.current_name}" if self.current_name else ""
                self.current_display.setText(
                    f"✓ All {self.batch_count} photos have the same location:\n"
                    f"({self.current_lat:.6f}, {self.current_lon:.6f}){name_str}"
                )
                # Pre-fill inputs
                self.lat_input.setText(str(self.current_lat))
                self.lon_input.setText(str(self.current_lon))
                if self.current_name:
                    self.name_input.setText(self.current_name)
            else:
                # Photos have different locations or no locations
                self.current_display.setText(
                    f"✏️ Editing location for {self.batch_count} photos.\n"
                    f"Enter coordinates to apply the same location to all photos."
                )
        else:
            # Single photo mode display
            if self.current_lat is not None and self.current_lon is not None:
                # Display current location
                name_str = f" - {self.current_name}" if self.current_name else ""
                self.current_display.setText(
                    f"✓ Location set: ({self.current_lat:.6f}, {self.current_lon:.6f}){name_str}"
                )

                # Pre-fill inputs
                self.lat_input.setText(str(self.current_lat))
                self.lon_input.setText(str(self.current_lon))
                if self.current_name:
                    self.name_input.setText(self.current_name)
            else:
                self.current_display.setText("⚠ No location data. Enter coordinates manually or paste from Google Maps.")

    def _preview_on_map(self):
        """Open location preview in browser (OpenStreetMap)."""
        try:
            lat_text = self.lat_input.text().strip()
            lon_text = self.lon_input.text().strip()

            if not lat_text or not lon_text:
                QMessageBox.warning(self, "Missing Coordinates", "Please enter latitude and longitude first.")
                return

            lat = float(lat_text)
            lon = float(lon_text)

            # Validate coordinates
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                QMessageBox.warning(self, "Invalid Coordinates",
                                  f"Coordinates out of range:\n"
                                  f"Latitude must be between -90 and 90\n"
                                  f"Longitude must be between -180 and 180")
                return

            # Open OpenStreetMap in browser
            import webbrowser
            map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}"
            webbrowser.open(map_url)

            logger.info(f"[LocationEditor] Opened map preview: ({lat}, {lon})")

        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric coordinates.")
        except Exception as e:
            logger.error(f"[LocationEditor] Map preview failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to open map:\n{e}")

    def _search_location(self):
        """
        Search for location by name (forward geocoding).

        This allows users to type "San Francisco" instead of manually
        entering coordinates.
        """
        search_text = self.search_input.text().strip()

        if not search_text:
            QMessageBox.warning(self, "Empty Search", "Please enter a location name to search.")
            return

        # Show progress
        self.search_btn.setEnabled(False)
        self.search_btn.setText("🔍 Searching...")
        self.search_results.clear()

        try:
            # Import forward geocoding service
            from services.geocoding_service import forward_geocode

            # Search for locations
            results = forward_geocode(search_text, limit=5)

            if results:
                # Show results in list
                self.search_results.show()
                for result in results:
                    name = result['name']
                    lat = result['lat']
                    lon = result['lon']
                    result_type = result.get('type', 'location')

                    # Create list item with data
                    item_text = f"{name}\n({lat:.6f}, {lon:.6f})"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.UserRole, result)  # Store full result data
                    item.setToolTip(f"Type: {result_type}\nDouble-click to select")

                    self.search_results.addItem(item)

                logger.info(f"[LocationEditor] Search '{search_text}' → {len(results)} result(s)")
            else:
                # No results found
                self.search_results.show()
                no_results = QListWidgetItem("❌ No results found. Try a different search term.")
                no_results.setFlags(Qt.NoItemFlags)  # Not selectable
                no_results.setForeground(Qt.gray)
                self.search_results.addItem(no_results)

                logger.info(f"[LocationEditor] Search '{search_text}' → No results")

        except ImportError as e:
            QMessageBox.critical(self, "Import Error",
                               f"Failed to import geocoding service:\n{e}\n\n"
                               f"Please ensure services/geocoding_service.py is available.")
            logger.error(f"[LocationEditor] Import error: {e}")
        except Exception as e:
            logger.error(f"[LocationEditor] Location search failed: {e}")
            QMessageBox.critical(self, "Search Error",
                               f"Failed to search for location:\n{e}\n\n"
                               f"Please check your internet connection.")
        finally:
            self.search_btn.setEnabled(True)
            self.search_btn.setText("🔍 Search")

    def _on_search_result_selected(self, item: QListWidgetItem):
        """
        Handle selection of a search result.

        Auto-fills coordinates and location name when user double-clicks a result.
        """
        result = item.data(Qt.UserRole)
        if not result:
            return

        # Auto-fill coordinates
        self.lat_input.setText(str(result['lat']))
        self.lon_input.setText(str(result['lon']))

        # Auto-fill location name
        self.name_input.setText(result['name'])

        # Hide search results
        self.search_results.hide()

        # Clear search input
        self.search_input.clear()

        logger.info(f"[LocationEditor] Selected: {result['name']} ({result['lat']}, {result['lon']})")

        # Show confirmation
        QMessageBox.information(
            self,
            "Location Selected",
            f"✓ Coordinates and name auto-filled:\n\n"
            f"Location: {result['name']}\n"
            f"Coordinates: ({result['lat']:.6f}, {result['lon']:.6f})\n\n"
            f"Click 'Save' to apply this location to your photo(s)."
        )

    def _geocode_coordinates(self):
        """Geocode coordinates to get location name."""
        try:
            lat_text = self.lat_input.text().strip()
            lon_text = self.lon_input.text().strip()

            if not lat_text or not lon_text:
                QMessageBox.warning(self, "Missing Coordinates", "Please enter latitude and longitude first.")
                return

            lat = float(lat_text)
            lon = float(lon_text)

            # Validate coordinates
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                QMessageBox.warning(self, "Invalid Coordinates",
                                  "Coordinates out of range.")
                return

            # Show progress
            self.geocode_btn.setEnabled(False)
            self.geocode_btn.setText("🌍 Getting location name...")

            # Import geocoding service
            try:
                from services.geocoding_service import reverse_geocode
            except ImportError as e:
                QMessageBox.critical(self, "Import Error",
                                   f"Failed to import geocoding service:\n{e}")
                return

            # Geocode
            location_name = reverse_geocode(lat, lon)

            if location_name:
                self.name_input.setText(location_name)
                QMessageBox.information(self, "Location Found",
                                      f"✓ Location: {location_name}")
                logger.info(f"[LocationEditor] Geocoded ({lat}, {lon}) → {location_name}")
            else:
                QMessageBox.warning(self, "Geocoding Failed",
                                  "Could not find location name for these coordinates.\n"
                                  "Please enter location name manually.")

        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric coordinates.")
        except Exception as e:
            logger.error(f"[LocationEditor] Geocoding failed: {e}")
            QMessageBox.critical(self, "Error", f"Geocoding failed:\n{e}")
        finally:
            self.geocode_btn.setEnabled(True)
            self.geocode_btn.setText("🌍 Get Location Name from Coordinates")

    def _clear_location(self):
        """Clear location data."""
        reply = QMessageBox.question(
            self,
            "Clear Location",
            "Remove GPS location data from this photo?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.lat_input.clear()
            self.lon_input.clear()
            self.name_input.clear()
            logger.info(f"[LocationEditor] Location data cleared")

    def _save_location(self):
        """Save location data."""
        try:
            lat_text = self.lat_input.text().strip()
            lon_text = self.lon_input.text().strip()
            location_name = self.name_input.text().strip() or None

            # Check if clearing location
            if not lat_text and not lon_text:
                # Saving empty location (clearing)
                self.locationSaved.emit(None, None, None)
                self.accept()
                return

            # Validate inputs
            if not lat_text or not lon_text:
                QMessageBox.warning(self, "Incomplete Data",
                                  "Please enter both latitude and longitude.")
                return

            lat = float(lat_text)
            lon = float(lon_text)

            # Validate range
            if not (-90 <= lat <= 90):
                QMessageBox.warning(self, "Invalid Latitude",
                                  "Latitude must be between -90 and 90.")
                return

            if not (-180 <= lon <= 180):
                QMessageBox.warning(self, "Invalid Longitude",
                                  "Longitude must be between -180 and 180.")
                return

            # Emit signal with location data
            self.locationSaved.emit(lat, lon, location_name)
            logger.info(f"[LocationEditor] Location saved: ({lat}, {lon}) - {location_name}")

            self.accept()

        except ValueError:
            QMessageBox.warning(self, "Invalid Input",
                              "Please enter valid numeric coordinates.")
        except Exception as e:
            logger.error(f"[LocationEditor] Save failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save location:\n{e}")


# Standalone testing
if __name__ == '__main__':
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Test with existing location
    dialog = LocationEditorDialog(
        photo_path="/path/to/photo.jpg",
        current_lat=37.7749,
        current_lon=-122.4194,
        current_name="San Francisco, California, USA"
    )

    dialog.locationSaved.connect(
        lambda lat, lon, name: print(f"Location saved: ({lat}, {lon}) - {name}")
    )

    dialog.show()
    sys.exit(app.exec())
