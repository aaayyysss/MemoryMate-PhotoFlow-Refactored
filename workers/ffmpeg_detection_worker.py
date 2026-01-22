# ffmpeg_detection_worker.py
# version 01.00.00.00 dated 20260122

"""
Async FFmpeg/FFprobe Detection Worker

Implements background detection of FFmpeg/FFprobe to prevent UI freezing
during application startup, following the same pattern as other async workers.
"""

from typing import Optional, Tuple
from PySide6.QtCore import QRunnable, QObject, Signal
import subprocess
import time
import json
from pathlib import Path

from logging_config import get_logger

logger = get_logger(__name__)

# Cache file for storing detection results
device_cache_file = Path(__file__).parent.parent / ".ffmpeg_cache.json"
CACHE_EXPIRY_SECONDS = 3600  # 1 hour cache


class FFmpegDetectionSignals(QObject):
    """Signals for FFmpeg detection worker."""
    detection_complete = Signal(bool, bool, str)  # (ffmpeg_available, ffprobe_available, message)
    error = Signal(str)  # error message


class FFmpegDetectionWorker(QRunnable):
    """
    Worker for asynchronous FFmpeg/FFprobe detection.
    
    Properties:
    - ✔ Background detection (doesn't block UI)
    - ✔ Timeout protection (5 second limit)
    - ✔ Error handling with descriptive messages
    - ✔ Signal-based communication
    """

    def __init__(self):
        super().__init__()
        self.signals = FFmpegDetectionSignals()

    def run(self):
        """Execute FFmpeg/FFprobe detection asynchronously."""
        logger.info("[FFmpegDetectionWorker] Starting async FFmpeg detection...")
        
        try:
            start_time = time.time()
            
            # Check cache first
            cached_result = self._get_cached_result()
            if cached_result:
                logger.info("[FFmpegDetectionWorker] Using cached FFmpeg detection result")
                ffmpeg_available, ffprobe_available, message = cached_result
                self.signals.detection_complete.emit(ffmpeg_available, ffprobe_available, message)
                return
            
            # Perform fresh detection (same logic as sync version but with timeout)
            ffmpeg_available, ffprobe_available, message = self._detect_ffmpeg_ffprobe()
            
            # Cache the result
            self._cache_result(ffmpeg_available, ffprobe_available, message)
            
            duration = time.time() - start_time
            logger.info(f"[FFmpegDetectionWorker] Fresh detection completed in {duration:.2f}s")
            
            # Emit results via signal
            self.signals.detection_complete.emit(ffmpeg_available, ffprobe_available, message)
            
        except Exception as e:
            logger.error(f"[FFmpegDetectionWorker] Detection failed: {e}")
            self.signals.error.emit(str(e))

    def _detect_ffmpeg_ffprobe(self) -> Tuple[bool, bool, str]:
        """
        Detect FFmpeg and FFprobe availability.
        
        Returns:
            Tuple of (ffmpeg_available, ffprobe_available, status_message)
        """
        # Check ffprobe first (critical for metadata)
        ffprobe_available = self._check_command('ffprobe')
        ffprobe_message = ""
        
        if ffprobe_available:
            ffprobe_message = "✅ FFprobe detected - video metadata extraction enabled"
        else:
            ffprobe_message = "⚠️ FFprobe not found - video metadata extraction limited"
        
        # Check ffmpeg (for thumbnails)
        ffmpeg_available = self._check_command('ffmpeg')
        ffmpeg_message = ""
        
        if ffmpeg_available:
            ffmpeg_message = "✅ FFmpeg detected - video thumbnail generation enabled"
        else:
            ffmpeg_message = "⚠️ FFmpeg not found - video thumbnail generation disabled"
        
        # Combine messages
        if ffprobe_available and ffmpeg_available:
            message = "✅ FFmpeg and FFprobe detected (system PATH) - full video support enabled"
        elif ffprobe_available and not ffmpeg_available:
            message = f"{ffprobe_message}\n{ffmpeg_message}"
        elif not ffprobe_available and ffmpeg_available:
            message = f"{ffprobe_message}\n{ffmpeg_message}"
        else:
            message = "⚠️ Neither FFmpeg nor FFprobe found - video features limited"
            message += "\n\nInstall FFmpeg to enable video metadata extraction and thumbnails:"
            message += "\n• Windows: choco install ffmpeg (or manual install)"
            message += "\n• macOS: brew install ffmpeg"
            message += "\n• Linux: sudo apt install ffmpeg"
        
        return ffmpeg_available, ffprobe_available, message

    def _check_command(self, command: str) -> bool:
        """
        Check if a command is available in the system PATH.
        
        Args:
            command: Command name to check (e.g., 'ffmpeg', 'ffprobe')
            
        Returns:
            True if command is available, False otherwise
        """
        try:
            result = subprocess.run(
                [command, '-version'],
                capture_output=True,
                text=True,
                timeout=5  # 5 second timeout to prevent hanging
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.debug(f"[FFmpegDetectionWorker] Command '{command}' check failed: {e}")
            return False
        except Exception as e:
            logger.warning(f"[FFmpegDetectionWorker] Unexpected error checking '{command}': {e}")
            return False

    def _get_cached_result(self) -> Optional[Tuple[bool, bool, str]]:
        """
        Get cached FFmpeg detection result if still valid.
        
        Returns:
            Cached result tuple or None if cache invalid/expired
        """
        try:
            if not device_cache_file.exists():
                return None
            
            with open(device_cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Check if cache is expired
            import time
            current_time = time.time()
            if current_time - cache_data.get('timestamp', 0) > CACHE_EXPIRY_SECONDS:
                logger.debug("[FFmpegDetectionWorker] Cache expired, performing fresh detection")
                return None
            
            # Return cached result
            ffmpeg_available = cache_data.get('ffmpeg_available', False)
            ffprobe_available = cache_data.get('ffprobe_available', False)
            message = cache_data.get('message', '')
            
            logger.debug(f"[FFmpegDetectionWorker] Loaded cached result: ffmpeg={ffmpeg_available}, ffprobe={ffprobe_available}")
            return (ffmpeg_available, ffprobe_available, message)
            
        except Exception as e:
            logger.debug(f"[FFmpegDetectionWorker] Failed to read cache: {e}")
            return None

    def _cache_result(self, ffmpeg_available: bool, ffprobe_available: bool, message: str):
        """
        Cache FFmpeg detection result.
        
        Args:
            ffmpeg_available: Whether ffmpeg is available
            ffprobe_available: Whether ffprobe is available
            message: Status message
        """
        try:
            import time
            cache_data = {
                'ffmpeg_available': ffmpeg_available,
                'ffprobe_available': ffprobe_available,
                'message': message,
                'timestamp': time.time()
            }
            
            with open(device_cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            logger.debug(f"[FFmpegDetectionWorker] Cached result: ffmpeg={ffmpeg_available}, ffprobe={ffprobe_available}")
            
        except Exception as e:
            logger.debug(f"[FFmpegDetectionWorker] Failed to cache result: {e}")