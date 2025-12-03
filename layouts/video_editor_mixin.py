# layouts/video_editor_mixin.py
# Video editing functionality mixin for MediaLightbox
# Phase 1: EDITOR-ONLY features (Trim, Rotate, Export)
# REUSES existing viewer video controls (no duplicates)

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QFileDialog, QMessageBox, QProgressDialog, QApplication
)
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QPixmap, QImage
import os


class VideoEditorMixin:
    """
    Mixin class providing video EDITING capabilities for MediaLightbox.
    
    EDITOR-ONLY Features (does NOT duplicate viewer controls):
    - Trim controls (set start/end points)
    - Rotate 90° buttons
    - Export pipeline with moviepy
    - Extended speed range (upgrade 4→8 speeds)
    
    REUSES from MediaLightbox:
    - self.video_player (QMediaPlayer) - Already initialized in viewer
    - self.video_widget (QVideoWidget) - Already created
    - self.audio_output (QAudioOutput) - Already exists
    - Existing playback controls (play/pause, seek, volume)
    """
    
    # ========== TRIM CONTROLS (Editor-Only) ==========
    
    def _create_video_trim_controls(self) -> QWidget:
        """Create trim controls (Set Start/End buttons). Reuses existing seek_slider from viewer."""
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background: rgba(0, 0, 0, 0.85);
                border-radius: 8px;
            }
        """)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)
        
        # Trim label
        trim_label = QLabel("✂️ Trim:")
        trim_label.setStyleSheet("color: white; font-weight: bold; font-size: 10pt;")
        layout.addWidget(trim_label)

        # Frame navigation buttons (Phase 2 Feature 6)
        prev_frame_btn = QPushButton("◀")
        prev_frame_btn.setToolTip("Previous frame (or use ← key)")
        prev_frame_btn.clicked.connect(self._previous_frame)
        prev_frame_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        layout.addWidget(prev_frame_btn)

        next_frame_btn = QPushButton("▶")
        next_frame_btn.setToolTip("Next frame (or use → key)")
        next_frame_btn.clicked.connect(self._next_frame)
        next_frame_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        layout.addWidget(next_frame_btn)
        
        # Set Start button
        self.trim_start_btn = QPushButton("[ Set Start")
        self.trim_start_btn.clicked.connect(self._set_trim_start)
        self.trim_start_btn.setStyleSheet("""
            QPushButton {
                background: rgba(76, 175, 80, 0.8);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(76, 175, 80, 1.0);
            }
        """)
        layout.addWidget(self.trim_start_btn)
        
        # Start time label
        self.trim_start_label = QLabel("00:00")
        self.trim_start_label.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 10pt;")
        layout.addWidget(self.trim_start_label)
        
        layout.addStretch()
        
        # End time label
        self.trim_end_label = QLabel("00:00")
        self.trim_end_label.setStyleSheet("color: #F44336; font-weight: bold; font-size: 10pt;")
        layout.addWidget(self.trim_end_label)
        
        # Set End button
        self.trim_end_btn = QPushButton("Set End ]")
        self.trim_end_btn.clicked.connect(self._set_trim_end)
        self.trim_end_btn.setStyleSheet("""
            QPushButton {
                background: rgba(244, 67, 54, 0.8);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(244, 67, 54, 1.0);
            }
        """)
        layout.addWidget(self.trim_end_btn)
        
        # Reset trim button
        reset_trim_btn = QPushButton("↺ Reset")
        reset_trim_btn.clicked.connect(self._reset_trim)
        reset_trim_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        layout.addWidget(reset_trim_btn)

        # Preview Trim button (Phase 2 Feature 5)
        preview_trim_btn = QPushButton("▶ Preview Trim")
        preview_trim_btn.setToolTip("Play only the trimmed region")
        preview_trim_btn.clicked.connect(self._preview_trim)
        preview_trim_btn.setStyleSheet("""
            QPushButton {
                background: rgba(66, 133, 244, 0.8);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(66, 133, 244, 1.0);
            }
        """)
        layout.addWidget(preview_trim_btn)

        return container
    
    # ========== ROTATE CONTROLS (Editor-Only) ==========
    
    def _create_video_rotate_controls(self) -> QWidget:
        """Create rotate buttons for video with status label."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        rotate_left_btn = QPushButton("↶ 90°")
        rotate_left_btn.setToolTip("Rotate 90° Left (Counterclockwise)")
        rotate_left_btn.clicked.connect(lambda: self._rotate_video(-90))
        rotate_left_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        layout.addWidget(rotate_left_btn)

        # Rotation status label
        self.rotation_status_label = QLabel("Original")
        self.rotation_status_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 10pt;
                font-weight: bold;
                background: rgba(66, 133, 244, 0.8);
                border-radius: 4px;
                padding: 8px 16px;
            }
        """)
        layout.addWidget(self.rotation_status_label)

        rotate_right_btn = QPushButton("↷ 90°")
        rotate_right_btn.setToolTip("Rotate 90° Right (Clockwise)")
        rotate_right_btn.clicked.connect(lambda: self._rotate_video(90))
        rotate_right_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        layout.addWidget(rotate_right_btn)

        # Export quality preset selector (Phase 2 Feature 7)
        layout.addSpacing(20)
        quality_label = QLabel("Quality:")
        quality_label.setStyleSheet("color: white; font-size: 10pt; font-weight: bold;")
        layout.addWidget(quality_label)

        self.export_quality_combo = QComboBox()
        self.export_quality_combo.addItems(["High (Original)", "Medium (Balanced)", "Low (Small File)"])
        self.export_quality_combo.setCurrentIndex(0)  # Default to High
        self.export_quality_combo.setToolTip("Select export quality/file size")
        self.export_quality_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 10pt;
            }
            QComboBox:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background: rgba(40, 40, 40, 0.95);
                color: white;
                selection-background-color: rgba(66, 133, 244, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.3);
            }
        """)
        layout.addWidget(self.export_quality_combo)

        return container
    
    # ========== TRIM/ROTATE/EXPORT METHODS (Editor-Only) ==========
    
    def _set_trim_start(self):
        """Set trim start point to current position. REUSES existing video_player."""
        if not hasattr(self, 'video_player') or not self.video_player:
            return

        self.video_trim_start = self.video_player.position()
        self.trim_start_label.setText(self._format_time(self.video_trim_start))
        print(f"[VideoEditor] Trim start: {self._format_time(self.video_trim_start)}")

        # Update visual trim markers on seek slider
        if hasattr(self, 'seek_slider') and hasattr(self.seek_slider, 'set_trim_markers'):
            duration = getattr(self, '_video_duration', 0)
            self.seek_slider.set_trim_markers(self.video_trim_start, self.video_trim_end, duration)
    
    def _set_trim_end(self):
        """Set trim end point to current position. REUSES existing video_player."""
        if not hasattr(self, 'video_player') or not self.video_player:
            return

        self.video_trim_end = self.video_player.position()
        self.trim_end_label.setText(self._format_time(self.video_trim_end))
        print(f"[VideoEditor] Trim end: {self._format_time(self.video_trim_end)}")

        # Update visual trim markers on seek slider
        if hasattr(self, 'seek_slider') and hasattr(self.seek_slider, 'set_trim_markers'):
            duration = getattr(self, '_video_duration', 0)
            self.seek_slider.set_trim_markers(self.video_trim_start, self.video_trim_end, duration)
    
    def _reset_trim(self):
        """Reset trim points to full video duration."""
        if not hasattr(self, 'video_player') or not self.video_player:
            return

        self.video_trim_start = 0
        # Get duration from existing player (stored in MediaLightbox as _video_duration)
        duration = getattr(self, '_video_duration', 0)
        self.video_trim_end = duration

        self.trim_start_label.setText("00:00")
        self.trim_end_label.setText(self._format_time(duration))
        print(f"[VideoEditor] Trim reset to full duration: {self._format_time(duration)}")

        # Clear visual trim markers (or set to full range)
        if hasattr(self, 'seek_slider') and hasattr(self.seek_slider, 'clear_trim_markers'):
            self.seek_slider.clear_trim_markers()

    def _preview_trim(self):
        """Preview only the trimmed region (Phase 2 Feature 5)."""
        if not hasattr(self, 'video_player') or not self.video_player:
            return

        # Validate trim points
        if self.video_trim_start >= self.video_trim_end:
            print("[VideoEditor] Cannot preview: trim start >= trim end")
            return

        # Seek to trim start
        self.video_player.setPosition(self.video_trim_start)

        # Start playback
        self.video_player.play()
        print(f"[VideoEditor] Previewing trim: {self._format_time(self.video_trim_start)} - {self._format_time(self.video_trim_end)}")

        # Create monitor timer if not exists
        if not hasattr(self, '_trim_preview_timer'):
            self._trim_preview_timer = QTimer(self)
            self._trim_preview_timer.timeout.connect(self._check_trim_preview_position)

        # Start monitoring (check every 100ms)
        self._trim_preview_timer.start(100)

    def _check_trim_preview_position(self):
        """Monitor video position during trim preview and stop at trim end."""
        if not hasattr(self, 'video_player') or not self.video_player:
            if hasattr(self, '_trim_preview_timer'):
                self._trim_preview_timer.stop()
            return

        current_pos = self.video_player.position()

        # Stop if reached trim end (with 100ms tolerance)
        if current_pos >= self.video_trim_end - 100:
            self.video_player.pause()
            # Seek back to trim start for easy replay
            self.video_player.setPosition(self.video_trim_start)
            if hasattr(self, '_trim_preview_timer'):
                self._trim_preview_timer.stop()
            print(f"[VideoEditor] Trim preview complete")

    def _previous_frame(self):
        """Go to previous frame (Phase 2 Feature 6)."""
        if not hasattr(self, 'video_player') or not self.video_player:
            return

        current_pos = self.video_player.position()
        frame_ms = 1000 / 30  # Assume 30 fps (~33ms per frame)
        new_pos = max(0, current_pos - frame_ms)
        self.video_player.setPosition(int(new_pos))
        print(f"[VideoEditor] Previous frame: {self._format_time(int(new_pos))}")

    def _next_frame(self):
        """Go to next frame (Phase 2 Feature 6)."""
        if not hasattr(self, 'video_player') or not self.video_player:
            return

        current_pos = self.video_player.position()
        duration = getattr(self, '_video_duration', 0)
        frame_ms = 1000 / 30  # Assume 30 fps (~33ms per frame)
        new_pos = min(duration, current_pos + frame_ms)
        self.video_player.setPosition(int(new_pos))
        print(f"[VideoEditor] Next frame: {self._format_time(int(new_pos))}")

    def _rotate_video(self, degrees):
        """Rotate video by degrees (90, -90). Visual rotation applied during export."""
        self.video_rotation_angle = (self.video_rotation_angle + degrees) % 360
        print(f"[VideoEditor] Rotation: {self.video_rotation_angle}°")

        # Update rotation status label
        if hasattr(self, 'rotation_status_label'):
            if self.video_rotation_angle == 0:
                label_text = "Original"
            elif self.video_rotation_angle == 90:
                label_text = "↷ 90° (Clockwise)"
            elif self.video_rotation_angle == 180:
                label_text = "↕ 180° (Upside Down)"
            elif self.video_rotation_angle == 270:
                label_text = "↶ 90° (Counterclockwise)"
            else:
                label_text = f"{self.video_rotation_angle}°"

            self.rotation_status_label.setText(label_text)
            print(f"[VideoEditor] Rotation status: {label_text}")

        # Note: QVideoWidget doesn't support rotation - applied during export
    
    def _format_time(self, milliseconds):
        """Format time from milliseconds to MM:SS."""
        if milliseconds <= 0:
            return "00:00"
        seconds = milliseconds // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
    
    # ========== EXPORT PIPELINE (Editor-Only) ==========
    
    def _export_edited_video(self):
        """Show export dialog and export video with all edits (trim, rotate, speed)."""
        try:
            # Get output path from user
            default_name = os.path.splitext(os.path.basename(self.media_path))[0] + "_edited.mp4"
            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Edited Video",
                default_name,
                "MP4 Video (*.mp4);;All Files (*)"
            )
            
            if not output_path:
                return  # User cancelled
            
            # Perform export
            success = self._export_video_with_edits(output_path)
            
            if success:
                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Video exported successfully to:\n{output_path}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Export Failed",
                    "Failed to export video. Check console for errors."
                )
        
        except Exception as e:
            import traceback
            print(f"[VideoEditor] Error in export dialog: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Export error: {e}")
    
    def _export_video_with_edits(self, output_path):
        """Export video with all edits applied (trim, rotate). REUSES existing video state."""
        progress_dialog = None
        try:
            print(f"[VideoEditor] Exporting video to: {output_path}")

            # Check if moviepy is available
            try:
                from moviepy.editor import VideoFileClip
            except ImportError:
                print("[VideoEditor] moviepy not available - install with: pip install moviepy")
                QMessageBox.warning(
                    self,
                    "Missing Dependency",
                    "moviepy library not installed.\n\nInstall with: pip install moviepy"
                )
                return False

            # Use self.media_path (existing video file)
            if not hasattr(self, 'media_path') or not self.media_path:
                print("[VideoEditor] No video loaded")
                return False

            # Load video with moviepy
            clip = VideoFileClip(self.media_path)

            # Apply trim (if set)
            duration_ms = getattr(self, '_video_duration', clip.duration * 1000)
            if self.video_trim_start > 0 or self.video_trim_end < duration_ms:
                start_sec = self.video_trim_start / 1000.0
                end_sec = self.video_trim_end / 1000.0 if self.video_trim_end > 0 else clip.duration
                clip = clip.subclip(start_sec, end_sec)
                print(f"[VideoEditor] Trimmed: {start_sec:.2f}s - {end_sec:.2f}s")

            # Apply rotation
            if self.video_rotation_angle != 0:
                if self.video_rotation_angle == 90:
                    clip = clip.rotate(90)
                elif self.video_rotation_angle == 180:
                    clip = clip.rotate(180)
                elif self.video_rotation_angle == 270:
                    clip = clip.rotate(270)
                print(f"[VideoEditor] Rotated: {self.video_rotation_angle}°")

            # Note: Speed change done in viewer playback only (not exported)
            # Note: Mute done in viewer playback only (not exported)
            # Phase 2: Can add speed/mute to export if needed

            # Create progress dialog
            progress_dialog = QProgressDialog("Initializing export...", "Cancel", 0, 100, self)
            progress_dialog.setWindowTitle("Exporting Video")
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setMinimumDuration(0)  # Show immediately
            progress_dialog.setValue(0)
            progress_dialog.show()
            QApplication.processEvents()

            # Track if user cancelled
            export_cancelled = False

            # Custom progress logger for moviepy
            class QtProgressLogger:
                def __init__(self, progress_dialog, duration):
                    self.progress_dialog = progress_dialog
                    self.duration = duration
                    self.last_progress = 0

                def __call__(self, message):
                    """Called by moviepy with progress messages."""
                    # Check if user cancelled
                    if self.progress_dialog.wasCanceled():
                        nonlocal export_cancelled
                        export_cancelled = True
                        raise Exception("Export cancelled by user")

                    # Parse moviepy progress message (format: "t: 1.23s")
                    if message.startswith('t:'):
                        try:
                            # Extract time value
                            time_str = message.split(':')[1].strip().rstrip('s')
                            current_time = float(time_str)

                            # Calculate percentage
                            progress = int((current_time / self.duration) * 100)
                            progress = min(progress, 100)  # Cap at 100%

                            # Update dialog only if progress changed significantly
                            if progress > self.last_progress:
                                self.last_progress = progress
                                self.progress_dialog.setValue(progress)

                                # Calculate time remaining (rough estimate)
                                if progress > 0:
                                    elapsed_per_percent = current_time / progress
                                    remaining_time = elapsed_per_percent * (100 - progress)
                                    remaining_mins = int(remaining_time // 60)
                                    remaining_secs = int(remaining_time % 60)

                                    self.progress_dialog.setLabelText(
                                        f"Exporting video: {progress}%\n"
                                        f"Time remaining: {remaining_mins:02d}:{remaining_secs:02d}"
                                    )
                                else:
                                    self.progress_dialog.setLabelText(f"Exporting video: {progress}%")

                                QApplication.processEvents()
                        except (ValueError, IndexError):
                            # Ignore malformed messages
                            pass

            # Create progress logger
            logger = QtProgressLogger(progress_dialog, clip.duration)

            # Get quality preset settings (Phase 2 Feature 7)
            quality_index = 0  # Default to High
            if hasattr(self, 'export_quality_combo'):
                quality_index = self.export_quality_combo.currentIndex()

            # Quality presets: [bitrate, preset, fps]
            quality_presets = {
                0: {'bitrate': None, 'preset': 'medium', 'fps': None},  # High: Original quality
                1: {'bitrate': '2000k', 'preset': 'fast', 'fps': None},  # Medium: 2 Mbps, faster encode
                2: {'bitrate': '500k', 'preset': 'faster', 'fps': 24}   # Low: 500 Kbps, reduce fps
            }

            preset = quality_presets.get(quality_index, quality_presets[0])
            print(f"[VideoEditor] Export quality: {['High', 'Medium', 'Low'][quality_index]} (bitrate={preset['bitrate']}, preset={preset['preset']})")

            # Build write_videofile parameters
            write_params = {
                'filename': output_path,
                'codec': 'libx264',
                'audio_codec': 'aac',
                'temp_audiofile': 'temp-audio.m4a',
                'remove_temp': True,
                'verbose': True,
                'logger': logger,
                'preset': preset['preset']
            }

            # Add optional parameters
            if preset['bitrate']:
                write_params['bitrate'] = preset['bitrate']
            if preset['fps']:
                write_params['fps'] = preset['fps']

            # Export video with progress tracking and quality preset
            clip.write_videofile(**write_params)

            # Close progress dialog
            if progress_dialog:
                progress_dialog.setValue(100)
                progress_dialog.close()

            # Cleanup
            clip.close()

            print(f"[VideoEditor] ✓ Video exported successfully!")
            return True

        except Exception as e:
            # Close progress dialog on error
            if progress_dialog:
                progress_dialog.close()

            # Don't show error if user cancelled
            if export_cancelled:
                print(f"[VideoEditor] Export cancelled by user")
                return False

            import traceback
            print(f"[VideoEditor] Error exporting video: {e}")
            traceback.print_exc()
            return False
