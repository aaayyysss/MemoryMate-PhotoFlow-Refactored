# Geocoding Service Documentation

## Overview

The Geocoding Service (Phase 4) provides automatic reverse geocoding functionality to convert GPS coordinates from photo EXIF data into human-readable location names.

**Example:** `(37.7749, -122.4194)` → `"San Francisco, California, United States"`

## Architecture

### Components

1. **GeocodingService** (`services/geocoding_service.py`)
   - Core reverse geocoding service
   - Nominatim API integration
   - Rate limiting (1 req/sec)
   - Caching integration

2. **ReferenceDB Integration** (`reference_db.py`)
   - `geocode_photos_missing_location_names()` - Geocode individual photos
   - `batch_geocode_unique_coordinates()` - Efficient batch geocoding
   - `cache_location_name()` - Cache location names
   - `get_cached_location_name()` - Retrieve cached locations

3. **Database Cache** (`gps_location_cache` table)
   - Stores geocoded location names
   - Reduces API calls
   - Tolerance-based lookup (nearby coordinates)

## Usage

### 1. Simple Reverse Geocoding

```python
from services.geocoding_service import reverse_geocode

# Single location
location = reverse_geocode(37.7749, -122.4194)
# Returns: "San Francisco, California, United States"
```

### 2. Using the Service Class

```python
from services.geocoding_service import GeocodingService

service = GeocodingService()

# Reverse geocode with custom cache tolerance
location = service.reverse_geocode(
    latitude=37.7749,
    longitude=-122.4194,
    cache_tolerance=0.01  # ~1km
)
```

### 3. Batch Geocoding Photos (Recommended)

**Most Efficient:** Geocode unique coordinates, then update all photos

```python
from reference_db import ReferenceDB

db = ReferenceDB()

# Geocode up to 50 unique locations in project 1
stats = db.batch_geocode_unique_coordinates(
    project_id=1,
    max_locations=50,
    progress_callback=lambda curr, total, loc: print(f"{curr}/{total}: {loc}")
)

print(stats)
# {'locations_geocoded': 15, 'photos_updated': 245, 'cached': 8, 'failed': 0}
```

### 4. Geocode Individual Photos

```python
from reference_db import ReferenceDB

db = ReferenceDB()

# Geocode up to 100 photos missing location names
stats = db.geocode_photos_missing_location_names(
    project_id=1,
    max_requests=100,
    progress_callback=lambda curr, total, path, name: print(f"{curr}/{total}: {name}")
)

print(stats)
# {'processed': 87, 'geocoded': 45, 'cached': 42, 'failed': 0}
```

### 5. Manual Caching

```python
from reference_db import ReferenceDB

db = ReferenceDB()

# Cache a location
db.cache_location_name(
    latitude=37.7749,
    longitude=-122.4194,
    location_name="San Francisco, California, United States"
)

# Retrieve from cache
cached = db.get_cached_location_name(
    latitude=37.7749,
    longitude=-122.4194,
    tolerance=0.01  # Match within ~1km
)
```

## API Details

### Nominatim API (OpenStreetMap)

- **Endpoint:** `https://nominatim.openstreetmap.org/reverse`
- **Rate Limit:** 1 request per second (strictly enforced)
- **User-Agent:** Required by usage policy
- **Cost:** Free for reasonable usage
- **Documentation:** https://nominatim.org/release-docs/develop/api/Reverse/

### Request Format

```
GET /reverse?lat=37.7749&lon=-122.4194&format=json&addressdetails=1&zoom=10
User-Agent: MemoryMate-PhotoFlow/1.0 (Photo Management Application)
```

### Response Format

The service formats responses as:
- **Primary:** `City, State/Region, Country`
- **Fallback:** Most specific available components
- **Error:** `"Unknown Location"`

## Rate Limiting

The service implements strict rate limiting to respect Nominatim's usage policy:

```python
# Automatic rate limiting (thread-safe)
service = GeocodingService()

# These calls will be automatically spaced 1 second apart
location1 = service.reverse_geocode(37.7749, -122.4194)  # Immediate
location2 = service.reverse_geocode(40.7128, -74.0060)   # Waits 1s
location3 = service.reverse_geocode(51.5074, -0.1278)    # Waits 1s
```

**Implementation:**
- Thread-safe lock mechanism
- Measures time since last request
- Automatically sleeps if needed
- Minimum 1 second between requests

## Caching Strategy

### Cache Table Schema

```sql
CREATE TABLE gps_location_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    location_name TEXT NOT NULL,
    cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(latitude, longitude)
);
```

### Cache Lookup with Tolerance

The cache supports tolerance-based lookups to match nearby coordinates:

```python
# Photo 1: (37.7749, -122.4194)
db.cache_location_name(37.7749, -122.4194, "San Francisco, CA, USA")

# Photo 2: (37.7755, -122.4200) - Only ~70 meters away
# This will hit the cache instead of making a new API request
cached = db.get_cached_location_name(37.7755, -122.4200, tolerance=0.01)
# Returns: "San Francisco, CA, USA"
```

**Tolerance Values:**
- `0.001` ≈ 100 meters (default for cache lookups)
- `0.01` ≈ 1 kilometer (recommended for batch geocoding)
- `0.1` ≈ 10 kilometers (very loose matching)

## Error Handling

The service handles all common errors gracefully:

```python
service = GeocodingService()

# Invalid coordinates
location = service.reverse_geocode(999, 999)  # Returns None

# Network error
location = service.reverse_geocode(37.7749, -122.4194)  # Returns None on failure

# API error (404, 500, etc.)
# Returns None, logs error

# All methods return None on error instead of raising exceptions
```

## Performance Considerations

### Batch vs. Individual Geocoding

| Method | API Calls | Time (50 locations) | Recommended For |
|--------|-----------|---------------------|-----------------|
| `batch_geocode_unique_coordinates()` | 1 per unique location | ~50 seconds | Initial setup, bulk updates |
| `geocode_photos_missing_location_names()` | 1 per photo | Variable | Individual photos, testing |

### Best Practices

1. **Use batch geocoding for initial setup**
   ```python
   # Geocode all photos in project efficiently
   db.batch_geocode_unique_coordinates(project_id=1, max_locations=100)
   ```

2. **Enable caching (default)**
   ```python
   service = GeocodingService(use_cache=True)  # Default
   ```

3. **Set appropriate limits**
   ```python
   # Don't geocode thousands of locations at once
   stats = db.batch_geocode_unique_coordinates(
       project_id=1,
       max_locations=50  # Reasonable limit
   )
   ```

4. **Use progress callbacks for long operations**
   ```python
   def progress(curr, total, loc):
       print(f"Progress: {curr}/{total} ({curr*100//total}%)")

   db.batch_geocode_unique_coordinates(
       project_id=1,
       progress_callback=progress
   )
   ```

## Integration with Locations Section

The geocoding service integrates seamlessly with the Locations section:

1. **Photos are scanned** for GPS EXIF data
2. **Location names are geocoded** (if missing)
3. **Locations section displays** human-readable names
4. **Users click locations** to filter photos

```python
# Automatic workflow
1. EXIF parser extracts GPS coordinates
2. Coordinates saved to photo_metadata (gps_latitude, gps_longitude)
3. Geocoding service converts to location name
4. Location name saved to photo_metadata (location_name)
5. LocationsSection displays locations with counts
6. User clicks location → filters photos
```

## Configuration

### Settings Manager Integration

```python
from settings_manager_qt import SettingsManager

sm = SettingsManager()

# Clustering radius for location grouping
radius_km = float(sm.get("gps_clustering_radius_km", 5.0))

# Cache tolerance for geocoding
cache_tolerance = float(sm.get("geocoding_cache_tolerance", 0.01))
```

### Environment Variables (Optional)

```bash
# Override Nominatim endpoint (for self-hosted instances)
export NOMINATIM_URL="https://your-nominatim-instance.com/reverse"

# Adjust rate limit (only for self-hosted instances)
export NOMINATIM_RATE_LIMIT=2.0  # Seconds between requests
```

## Testing

### Unit Tests

```bash
# Run geocoding service tests
python3 test_geocoding_service.py
```

### Manual Testing

```bash
# Test geocoding directly
python3 services/geocoding_service.py
```

### Integration Testing

```python
from reference_db import ReferenceDB

db = ReferenceDB()

# Test cache
db.cache_location_name(37.7749, -122.4194, "Test Location")
cached = db.get_cached_location_name(37.7749, -122.4194)
assert cached == "Test Location"

# Test geocoding (requires internet)
stats = db.batch_geocode_unique_coordinates(project_id=1, max_locations=1)
print(stats)
```

## Troubleshooting

### Issue: "Rate limit exceeded"

**Cause:** Making too many requests to Nominatim API

**Solution:** The service automatically enforces rate limiting. If you see this error, it means the external API is rejecting requests. Wait 1 minute and try again.

### Issue: "No location name returned"

**Possible causes:**
1. Invalid coordinates
2. Network connectivity issue
3. Nominatim API down
4. Coordinates in ocean/uninhabited area

**Solution:**
```python
# Check coordinates are valid
from services.geocoding_service import GeocodingService
if GeocodingService._validate_coordinates(lat, lon):
    print("Coordinates valid")
else:
    print("Coordinates invalid")
```

### Issue: "Cache not working"

**Check:**
1. Database has `gps_location_cache` table
2. Caching is enabled: `GeocodingService(use_cache=True)`
3. Tolerance is appropriate for your use case

**Solution:**
```python
from reference_db import ReferenceDB

db = ReferenceDB()

# Verify cache table exists
with db._connect() as conn:
    cur = conn.cursor()
    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='gps_location_cache'
    """)
    print("Cache table exists:", cur.fetchone() is not None)
```

## API Usage Policy Compliance

This implementation follows Nominatim's usage policy:

✅ **User-Agent header:** Included in all requests
✅ **Rate limiting:** 1 request per second (strictly enforced)
✅ **Caching:** Enabled by default to reduce API load
✅ **Batch operations:** Minimizes redundant requests
✅ **Error handling:** Graceful handling of API errors

**Do NOT:**
- Remove or bypass rate limiting
- Make mass requests without caching
- Use for high-volume commercial applications without self-hosting

**For high-volume usage:**
Consider self-hosting Nominatim: https://nominatim.org/release-docs/develop/admin/Installation/

## Examples

### Example 1: Geocode New Project

```python
from reference_db import ReferenceDB

db = ReferenceDB()

# Batch geocode all unique locations (most efficient)
print("Starting batch geocoding...")
stats = db.batch_geocode_unique_coordinates(
    project_id=1,
    max_locations=100
)

print(f"✓ Geocoded {stats['locations_geocoded']} unique locations")
print(f"✓ Updated {stats['photos_updated']} photos")
print(f"✓ Used cache for {stats['cached']} locations")
print(f"✗ Failed {stats['failed']} locations")
```

### Example 2: Background Geocoding Worker

```python
import threading
from reference_db import ReferenceDB

def geocode_worker(project_id, progress_callback=None):
    """Background worker for geocoding photos."""
    db = ReferenceDB()

    try:
        stats = db.batch_geocode_unique_coordinates(
            project_id=project_id,
            max_locations=50,
            progress_callback=progress_callback
        )
        return stats
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None

# Run in background
thread = threading.Thread(
    target=geocode_worker,
    args=(1,),
    daemon=True
)
thread.start()
```

### Example 3: On-Demand Geocoding

```python
from services.geocoding_service import get_geocoding_service

# Get singleton service instance
service = get_geocoding_service()

# Geocode single location on demand
location = service.reverse_geocode(35.6762, 139.6503)
print(f"Location: {location}")
# Output: "Tokyo, Kantō region, Japan"
```

## See Also

- [Locations Section Documentation](LOCATIONS_SECTION.md)
- [GPS/EXIF Data Extraction](../services/exif_parser.py)
- [Nominatim API Documentation](https://nominatim.org/release-docs/develop/api/Reverse/)
- [OpenStreetMap Usage Policy](https://operations.osmfoundation.org/policies/nominatim/)
