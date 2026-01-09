#!/usr/bin/env python3
"""Geocoding Service - Reverse geocoding GPS coordinates to location names

This service provides reverse geocoding functionality using OpenStreetMap's
Nominatim API. It includes:
- Rate limiting (1 req/sec as per Nominatim usage policy)
- Automatic caching to minimize API calls
- Graceful error handling
- Human-readable location name formatting

Usage:
    from services.geocoding_service import GeocodingService

    service = GeocodingService()
    location = service.reverse_geocode(37.7749, -122.4194)
    # Returns: "San Francisco, California, United States"
"""

import time
import logging
import urllib.request
import urllib.parse
import json
from typing import Optional
from threading import Lock

logger = logging.getLogger(__name__)


class GeocodingService:
    """
    Reverse geocoding service using OpenStreetMap Nominatim API.

    Features:
    - Automatic rate limiting (1 request per second)
    - Cache integration to minimize API calls
    - Formatted location names (City, State/Region, Country)
    - Error handling with fallback to coordinates

    Usage Policy:
    - Respects Nominatim usage policy (max 1 req/sec)
    - Includes User-Agent header
    - Uses caching to be a good API citizen
    """

    # Nominatim API endpoint
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

    # Rate limiting: minimum seconds between requests
    MIN_REQUEST_INTERVAL = 1.0

    # Request timeout in seconds
    REQUEST_TIMEOUT = 10.0

    # User-Agent for API requests (required by Nominatim)
    USER_AGENT = "MemoryMate-PhotoFlow/1.0 (Photo Management Application)"

    def __init__(self, use_cache: bool = True):
        """
        Initialize geocoding service.

        Args:
            use_cache: Whether to use database cache (default: True)
        """
        self.use_cache = use_cache
        self._last_request_time = 0.0
        self._rate_limit_lock = Lock()

        logger.info("[GeocodingService] Initialized with cache=%s", use_cache)

    def reverse_geocode(self, latitude: float, longitude: float,
                       cache_tolerance: float = 0.01, language: str = None) -> Optional[str]:
        """
        Convert GPS coordinates to human-readable location name.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            cache_tolerance: Cache lookup tolerance in degrees (default: 0.01 ≈ 1km)
            language: Language code for location names (e.g., 'en', 'ar', 'de')
                     If None, uses app's current language from translation manager

        Returns:
            Formatted location name in requested language or None if geocoding fails

        Example:
            >>> service.reverse_geocode(37.7749, -122.4194, language='en')
            "San Francisco, California, United States"
            >>> service.reverse_geocode(37.7749, -122.4194, language='ar')
            "سان فرانسيسكو، كاليفورنيا، الولايات المتحدة"
        """
        # Input validation
        if not self._validate_coordinates(latitude, longitude):
            logger.warning(f"[GeocodingService] Invalid coordinates: ({latitude}, {longitude})")
            return None

        # Auto-detect language from app settings if not specified
        if language is None:
            try:
                from translation_manager import TranslationManager
                tm = TranslationManager.get_instance()
                language = tm.current_language  # e.g., 'en', 'ar'
                logger.debug(f"[GeocodingService] Auto-detected language: {language}")
            except Exception as e:
                logger.warning(f"[GeocodingService] Could not detect app language: {e}")
                language = 'en'  # Fallback to English

        # Check cache first
        if self.use_cache:
            cached = self._get_cached_location(latitude, longitude, cache_tolerance)
            if cached:
                logger.debug(f"[GeocodingService] Cache hit: ({latitude:.4f}, {longitude:.4f}) → {cached}")
                return cached

        # Make API request
        try:
            location_name = self._fetch_from_api(latitude, longitude, language)

            # Cache the result
            if location_name and self.use_cache:
                self._cache_location(latitude, longitude, location_name)

            return location_name

        except Exception as e:
            logger.error(f"[GeocodingService] Geocoding failed for ({latitude}, {longitude}): {e}")
            return None

    def batch_reverse_geocode(self, coordinates: list[tuple[float, float]],
                             progress_callback=None) -> dict[tuple[float, float], str]:
        """
        Reverse geocode multiple coordinates with rate limiting.

        Args:
            coordinates: List of (latitude, longitude) tuples
            progress_callback: Optional callback(current, total, location_name)

        Returns:
            Dict mapping (lat, lon) to location name
        """
        results = {}
        total = len(coordinates)

        logger.info(f"[GeocodingService] Batch geocoding {total} locations...")

        for i, (lat, lon) in enumerate(coordinates, 1):
            location = self.reverse_geocode(lat, lon)
            results[(lat, lon)] = location

            if progress_callback:
                progress_callback(i, total, location)

            # Log progress every 10 items
            if i % 10 == 0 or i == total:
                logger.info(f"[GeocodingService] Progress: {i}/{total} ({i*100//total}%)")

        logger.info(f"[GeocodingService] Batch complete: {len(results)} locations geocoded")
        return results

    def _fetch_from_api(self, latitude: float, longitude: float, language: str = 'en') -> Optional[str]:
        """
        Fetch location name from Nominatim API with rate limiting.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            language: Language code for results (e.g., 'en', 'ar', 'de')

        Returns:
            Formatted location name in requested language or None if request fails
        """
        # Rate limiting
        self._wait_for_rate_limit()

        # Build request URL with language preference
        params = {
            'lat': f"{latitude:.6f}",
            'lon': f"{longitude:.6f}",
            'format': 'json',
            'addressdetails': '1',
            'zoom': '10',  # City-level detail
            'accept-language': language,  # Request localized location names
        }
        url = f"{self.NOMINATIM_URL}?{urllib.parse.urlencode(params)}"

        # Create request with proper User-Agent
        request = urllib.request.Request(url)
        request.add_header('User-Agent', self.USER_AGENT)

        logger.debug(f"[GeocodingService] API request: ({latitude:.4f}, {longitude:.4f})")

        try:
            with urllib.request.urlopen(request, timeout=self.REQUEST_TIMEOUT) as response:
                data = json.loads(response.read().decode('utf-8'))
                location_name = self._format_location_name(data)

                logger.info(f"[GeocodingService] API response: ({latitude:.4f}, {longitude:.4f}) → {location_name}")
                return location_name

        except urllib.error.HTTPError as e:
            logger.error(f"[GeocodingService] HTTP error {e.code}: {e.reason}")
            return None
        except urllib.error.URLError as e:
            logger.error(f"[GeocodingService] URL error: {e.reason}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"[GeocodingService] JSON decode error: {e}")
            return None
        except Exception as e:
            logger.exception(f"[GeocodingService] Unexpected error: {e}")
            return None

    def _format_location_name(self, data: dict) -> str:
        """
        Format API response into human-readable location name.

        Strategy:
        - Try: City, State/Region, Country
        - Fallback: Most specific available info

        Args:
            data: Nominatim API response JSON

        Returns:
            Formatted location name
        """
        if 'error' in data:
            return "Unknown Location"

        address = data.get('address', {})
        parts = []

        # City/Town/Village
        city = (address.get('city') or
                address.get('town') or
                address.get('village') or
                address.get('municipality') or
                address.get('hamlet'))
        if city:
            parts.append(city)

        # State/Region/Province
        state = (address.get('state') or
                 address.get('region') or
                 address.get('province') or
                 address.get('county'))
        if state and state != city:  # Avoid duplication
            parts.append(state)

        # Country
        country = address.get('country')
        if country:
            parts.append(country)

        # Fallback to display name if no structured address
        if not parts:
            display_name = data.get('display_name', 'Unknown Location')
            # Simplify display name (take first 3 components)
            parts = display_name.split(', ')[:3]

        location_name = ', '.join(parts)
        return location_name if location_name else "Unknown Location"

    def _wait_for_rate_limit(self):
        """
        Enforce rate limiting (1 request per second).

        Thread-safe implementation using lock.
        """
        with self._rate_limit_lock:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.MIN_REQUEST_INTERVAL:
                sleep_time = self.MIN_REQUEST_INTERVAL - elapsed
                logger.debug(f"[GeocodingService] Rate limit: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
            self._last_request_time = time.time()

    def _get_cached_location(self, latitude: float, longitude: float,
                            tolerance: float) -> Optional[str]:
        """
        Retrieve cached location name from database.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            tolerance: Search tolerance in degrees

        Returns:
            Cached location name or None
        """
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            cached = db.get_cached_location_name(latitude, longitude, tolerance)
            return cached
        except Exception as e:
            logger.warning(f"[GeocodingService] Cache lookup failed: {e}")
            return None

    def _cache_location(self, latitude: float, longitude: float, location_name: str):
        """
        Cache location name in database.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            location_name: Location name to cache
        """
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            db.cache_location_name(latitude, longitude, location_name)
            logger.debug(f"[GeocodingService] Cached: ({latitude:.4f}, {longitude:.4f}) → {location_name}")
        except Exception as e:
            logger.warning(f"[GeocodingService] Cache write failed: {e}")

    @staticmethod
    def _validate_coordinates(latitude: float, longitude: float) -> bool:
        """
        Validate GPS coordinates are within valid ranges.

        Args:
            latitude: Latitude (-90 to 90)
            longitude: Longitude (-180 to 180)

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            return False

        return -90 <= latitude <= 90 and -180 <= longitude <= 180


# Singleton instance for convenience
_geocoding_service = None


def get_geocoding_service() -> GeocodingService:
    """
    Get singleton GeocodingService instance.

    Returns:
        Shared GeocodingService instance
    """
    global _geocoding_service
    if _geocoding_service is None:
        _geocoding_service = GeocodingService()
    return _geocoding_service


def reverse_geocode(latitude: float, longitude: float, language: str = None) -> Optional[str]:
    """
    Convenience function for reverse geocoding.

    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees
        language: Language code (e.g., 'en', 'ar') - auto-detected if None

    Returns:
        Location name in requested language or None
    """
    service = get_geocoding_service()
    return service.reverse_geocode(latitude, longitude, language=language)


if __name__ == '__main__':
    # Test the geocoding service
    import sys

    print("=" * 70)
    print("Geocoding Service Test")
    print("=" * 70)

    service = GeocodingService()

    # Test coordinates
    test_locations = [
        (37.7749, -122.4194, "San Francisco, California"),
        (40.7128, -74.0060, "New York City, New York"),
        (51.5074, -0.1278, "London, England"),
        (35.6762, 139.6503, "Tokyo, Japan"),
        (48.8566, 2.3522, "Paris, France"),
    ]

    print("\nTesting reverse geocoding:\n")

    for lat, lon, expected in test_locations:
        print(f"Coordinates: ({lat:.4f}, {lon:.4f})")
        print(f"Expected: {expected}")

        result = service.reverse_geocode(lat, lon)
        print(f"Result: {result}")
        print(f"Status: {'✓ PASS' if result else '✗ FAIL'}")
        print("-" * 70)

        # Respect rate limit between tests
        time.sleep(1.1)

    print("\n" + "=" * 70)
    print("Test complete")
    print("=" * 70)
