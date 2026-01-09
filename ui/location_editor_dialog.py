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
                               QMessageBox, QGroupBox, QListWidget, QListWidgetItem, QComboBox)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QDoubleValidator, QPixmap
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
                 parent=None, batch_mode=False, batch_count=1, photo_paths=None):
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
            photo_paths: Optional list of photo paths for batch mode (enables thumbnail preview)
        """
        super().__init__(parent)

        self.photo_path = photo_path
        self.current_lat = current_lat
        self.current_lon = current_lon
        self.current_name = current_name
        self.batch_mode = batch_mode
        self.batch_count = batch_count
        self.photo_paths = photo_paths  # SPRINT 2: For batch thumbnail preview

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

        # SPRINT 2 ENHANCEMENT: Photo Preview (150x150px thumbnails)
        self._init_photo_preview(layout)

        # SPRINT 2 ENHANCEMENT: Recent Locations dropdown (quick reuse)
        recent_group = QGroupBox("⏱️ Recent Locations")
        recent_layout = QVBoxLayout()

        # Recent locations dropdown
        self.recent_combo = QComboBox()
        self.recent_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #dadce0;
                border-radius: 4px;
                background: white;
                min-height: 24px;
            }
            QComboBox:hover {
                border: 1px solid #1a73e8;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #5f6368;
                margin-right: 10px;
            }
        """)
        self.recent_combo.currentIndexChanged.connect(self._on_recent_location_selected)

        # Load recent locations
        self._load_recent_locations()

        recent_layout.addWidget(self.recent_combo)

        # Help text
        recent_help = QLabel("💡 Select a recently used location to auto-fill coordinates and name")
        recent_help.setStyleSheet("font-size: 10pt; color: #666; font-style: italic;")
        recent_layout.addWidget(recent_help)

        recent_group.setLayout(recent_layout)
        layout.addWidget(recent_group)

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

    def _init_photo_preview(self, layout: QVBoxLayout):
        """
        SPRINT 2 ENHANCEMENT: Initialize photo preview section.

        Shows 150x150px thumbnails of photos being edited:
        - Single mode: One thumbnail
        - Batch mode: 3-5 thumbnails + "... and N more"

        Loads asynchronously to avoid blocking the UI.
        """
        if not self.photo_path:
            return

        # Create preview group
        preview_group = QGroupBox("📸 Photo Preview")
        preview_layout = QHBoxLayout()
        preview_layout.setSpacing(8)

        # Storage for thumbnail labels
        self.thumbnail_labels = []

        if self.batch_mode:
            # Batch mode: Show message that thumbnails will load
            loading_label = QLabel("Loading thumbnails...")
            loading_label.setStyleSheet("color: #666; font-style: italic; padding: 8px;")
            loading_label.setAlignment(Qt.AlignCenter)
            preview_layout.addWidget(loading_label)
            self.thumbnail_labels.append(loading_label)
        else:
            # Single mode: Show one thumbnail placeholder
            thumbnail_label = QLabel()
            thumbnail_label.setFixedSize(150, 150)
            thumbnail_label.setAlignment(Qt.AlignCenter)
            thumbnail_label.setStyleSheet("""
                QLabel {
                    border: 2px solid #dadce0;
                    border-radius: 8px;
                    background: #f8f9fa;
                    color: #666;
                }
            """)
            thumbnail_label.setText("Loading...")
            preview_layout.addWidget(thumbnail_label)
            self.thumbnail_labels.append(thumbnail_label)

        preview_layout.addStretch()
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # Load thumbnails asynchronously (non-blocking)
        # Use QTimer.singleShot to defer loading until after dialog is shown
        QTimer.singleShot(50, self._load_photo_thumbnails)

    def _load_photo_thumbnails(self):
        """
        Load photo thumbnails asynchronously.

        For single mode: Load one thumbnail
        For batch mode: Load up to 5 thumbnails + count indicator
        """
        try:
            from services.thumbnail_service import get_thumbnail_service
            from pathlib import Path

            thumb_service = get_thumbnail_service()

            if self.batch_mode:
                # Clear loading message
                for label in self.thumbnail_labels:
                    label.deleteLater()
                self.thumbnail_labels.clear()

                # Get the preview group layout
                preview_group = self.findChild(QGroupBox, "")
                if not preview_group:
                    return

                preview_layout = preview_group.layout()
                if not preview_layout:
                    return

                # If we have photo_paths, show up to 5 thumbnails
                if self.photo_paths and len(self.photo_paths) > 0:
                    max_thumbnails = min(5, len(self.photo_paths))

                    for i in range(max_thumbnails):
                        photo_path = self.photo_paths[i]
                        pixmap = thumb_service.get_thumbnail(photo_path, height=120)

                        thumbnail_label = QLabel()
                        thumbnail_label.setFixedSize(120, 120)
                        thumbnail_label.setAlignment(Qt.AlignCenter)
                        thumbnail_label.setStyleSheet("""
                            QLabel {
                                border: 2px solid #dadce0;
                                border-radius: 8px;
                                background: #f8f9fa;
                            }
                        """)

                        if pixmap and not pixmap.isNull():
                            scaled_pixmap = pixmap.scaled(
                                120, 120,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation
                            )
                            thumbnail_label.setPixmap(scaled_pixmap)
                        else:
                            thumbnail_label.setText("⚠️")

                        preview_layout.addWidget(thumbnail_label)

                    # Show "... and N more" if there are more photos
                    if len(self.photo_paths) > max_thumbnails:
                        more_count = len(self.photo_paths) - max_thumbnails
                        more_label = QLabel(f"... and\n{more_count} more")
                        more_label.setStyleSheet("color: #666; font-weight: bold; padding: 8px;")
                        more_label.setAlignment(Qt.AlignCenter)
                        preview_layout.addWidget(more_label)
                else:
                    # No photo_paths provided - show fallback message
                    msg_label = QLabel(f"📸 Editing {self.batch_count} photos")
                    msg_label.setStyleSheet("color: #666; padding: 8px; font-weight: bold;")
                    msg_label.setAlignment(Qt.AlignCenter)
                    preview_layout.addWidget(msg_label)

            else:
                # Single mode: Load one thumbnail
                pixmap = thumb_service.get_thumbnail(self.photo_path, height=150)

                if pixmap and not pixmap.isNull():
                    # Scale to fit 150x150 while preserving aspect ratio
                    scaled_pixmap = pixmap.scaled(
                        150, 150,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.thumbnail_labels[0].setPixmap(scaled_pixmap)
                    self.thumbnail_labels[0].setText("")  # Clear "Loading..."
                else:
                    # Failed to load
                    self.thumbnail_labels[0].setText("⚠️\nPreview\nUnavailable")
                    self.thumbnail_labels[0].setStyleSheet("""
                        QLabel {
                            border: 2px solid #dadce0;
                            border-radius: 8px;
                            background: #fff3cd;
                            color: #856404;
                            font-size: 9pt;
                        }
                    """)

        except Exception as e:
            logger.warning(f"[LocationEditor] Failed to load thumbnail: {e}")
            # Show error in thumbnail placeholder
            if self.thumbnail_labels:
                self.thumbnail_labels[0].setText("⚠️\nPreview\nError")

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

    def _load_recent_locations(self):
        """
        Load recent locations from settings and populate dropdown.

        Shows most recently used locations at the top for quick selection.
        """
        try:
            from settings_manager_qt import SettingsManager

            sm = SettingsManager()
            recents = sm.get_recent_locations(limit=10)

            # Clear existing items
            self.recent_combo.clear()

            # Add placeholder item
            self.recent_combo.addItem("-- Select Recent Location --", None)

            if not recents:
                # No recent locations
                self.recent_combo.addItem("(No recent locations yet)", None)
                self.recent_combo.setEnabled(False)
                return

            # Add recent locations
            for loc in recents:
                name = loc.get('name', 'Unknown')
                lat = loc.get('lat', 0)
                lon = loc.get('lon', 0)
                use_count = loc.get('use_count', 1)

                # Format display text
                if use_count > 1:
                    display_text = f"{name} (used {use_count}x)"
                else:
                    display_text = name

                # Store full location data
                self.recent_combo.addItem(display_text, loc)

            logger.info(f"[LocationEditor] Loaded {len(recents)} recent locations")

        except Exception as e:
            logger.error(f"[LocationEditor] Failed to load recent locations: {e}")
            # Don't crash, just disable the dropdown
            self.recent_combo.addItem("(Error loading recents)", None)
            self.recent_combo.setEnabled(False)

    def _on_recent_location_selected(self, index: int):
        """
        Handle selection of a recent location from dropdown.

        Auto-fills coordinates and location name when user selects a recent location.
        """
        if index <= 0:  # Placeholder or "no recents" item
            return

        location_data = self.recent_combo.itemData(index)
        if not location_data:
            return

        # Auto-fill coordinates
        lat = location_data.get('lat')
        lon = location_data.get('lon')
        name = location_data.get('name', '')

        if lat is not None and lon is not None:
            self.lat_input.setText(str(lat))
            self.lon_input.setText(str(lon))

        if name:
            self.name_input.setText(name)

        logger.info(f"[LocationEditor] Selected recent location: {name} ({lat}, {lon})")

        # Show brief confirmation (non-blocking)
        # User can immediately click Save without dismissing dialog
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: None)  # Process events

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
