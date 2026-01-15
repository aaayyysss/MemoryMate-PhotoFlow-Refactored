# Embedding & Semantic Search - Implementation Plan

**Date:** 2026-01-04
**Reference:** EMBEDDING_SEARCH_IMPROVEMENT_AUDIT.md
**Status:** 📋 READY FOR IMPLEMENTATION
**Estimated Total Effort:** 25-36 hours (3-5 days)

---

## OVERVIEW

This document provides a detailed, step-by-step implementation plan for improving the embedding extraction and semantic search functionality based on the audit findings and industry best practices.

---

## PHASE 1: HIGH-PRIORITY IMPROVEMENTS

**Timeline:** 1-2 days
**Effort:** 10-15 hours
**Impact:** HIGH
**Risk:** LOW

### 1.1 Result Caching for Search ⭐⭐⭐

**Priority:** CRITICAL
**Effort:** 2-3 hours
**Files:** `ui/semantic_search_widget.py`

#### Current Issue
```python
# Every search call recomputes similarities from scratch
def _on_search(self):
    results = self.embedding_service.search_similar(query_embedding, ...)
    # ❌ No caching - wastes CPU for repeated queries
```

#### Proposed Solution
```python
from cachetools import TTLCache
from hashlib import md5

class SemanticSearchWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Add result cache (100 queries, 5 minute TTL)
        self._result_cache = TTLCache(maxsize=100, ttl=300)
        self._cache_hits = 0
        self._cache_misses = 0

    def _get_cache_key(self, query: str, threshold: float, model_id: int) -> str:
        """Generate cache key from search parameters."""
        cache_str = f"{query}|{threshold:.3f}|{model_id}"
        return md5(cache_str.encode()).hexdigest()

    def _on_search(self):
        # Get query embedding (this is cached in embedding_service)
        query_embedding = self.embedding_service.extract_text_embedding(query_text)

        # Generate cache key
        cache_key = self._get_cache_key(query_text, self._min_similarity, model_id)

        # Check cache
        if cache_key in self._result_cache:
            results = self._result_cache[cache_key]
            self._cache_hits += 1
            logger.info(f"[SemanticSearch] Cache HIT for '{query_text}' (hits={self._cache_hits}, misses={self._cache_misses})")
        else:
            # Cache miss - perform search
            results = self.embedding_service.search_similar(
                query_embedding,
                top_k=100,
                min_similarity=self._min_similarity
            )
            self._result_cache[cache_key] = results
            self._cache_misses += 1
            logger.info(f"[SemanticSearch] Cache MISS for '{query_text}' (hits={self._cache_hits}, misses={self._cache_misses})")

        # Update UI with results
        self._display_results(results)

    def clear_cache(self):
        """Clear result cache (call when embeddings are re-extracted)."""
        self._result_cache.clear()
        logger.info("[SemanticSearch] Result cache cleared")
```

#### Implementation Steps
1. Add `cachetools` dependency (already lightweight, no new deps needed)
2. Add `_result_cache` instance variable in `__init__`
3. Implement `_get_cache_key()` method
4. Modify `_on_search()` to check cache before searching
5. Add `clear_cache()` method for cache invalidation
6. Add cache statistics logging

#### Testing
- Test repeated searches return instantly
- Test different thresholds create different cache entries
- Test cache expiration after 5 minutes
- Test cache clearing on embedding re-extraction

#### Dependencies
```python
# Already available in standard library / likely installed
from cachetools import TTLCache
from hashlib import md5
```

---

### 1.2 Batch Processing for Search ⭐⭐⭐

**Priority:** HIGH
**Effort:** 4-6 hours
**Files:** `services/embedding_service.py`

#### Current Issue
```python
def search_similar(self, query_embedding, top_k=10, ...):
    # ❌ Loads ALL embeddings into memory at once
    cursor = conn.execute("SELECT photo_id, embedding FROM photo_embedding WHERE model_id = ?")
    rows = cursor.fetchall()  # ← 40MB for 10k photos, 400MB for 100k photos

    results = []
    for row in rows:  # ← Sequential processing
        embedding = np.frombuffer(row["embedding"], dtype=np.float32)
        similarity = float(np.dot(query_norm, embedding_norm))
        results.append((photo_id, similarity))
```

#### Proposed Solution
```python
def search_similar(self,
                  query_embedding: np.ndarray,
                  top_k: int = 10,
                  model_id: Optional[int] = None,
                  photo_ids: Optional[List[int]] = None,
                  min_similarity: float = 0.20,
                  batch_size: int = 1000,
                  progress_callback: Optional[callable] = None) -> List[Tuple[int, float]]:
    """
    Search for similar images using batched processing.

    Args:
        batch_size: Number of embeddings to process per batch (default: 1000)
        progress_callback: Optional callback(current, total) for progress updates

    Performance:
        - batch_size=1000: ~40MB peak memory per batch (512-D embeddings)
        - batch_size=100: ~4MB peak memory per batch
        - Recommended: 500-1000 for desktop, 100-500 for mobile
    """
    if model_id is None:
        model_id = self._clip_model_id

    with self.db.get_connection() as conn:
        # Get total count first
        count_query = "SELECT COUNT(*) as count FROM photo_embedding WHERE model_id = ?"
        total_count = conn.execute(count_query, [model_id]).fetchone()["count"]

        if total_count == 0:
            logger.warning("[EmbeddingService] No embeddings found")
            return []

        logger.info(f"[EmbeddingService] Searching {total_count} embeddings with batch_size={batch_size}")

        # Build query for batch processing
        query = "SELECT photo_id, embedding FROM photo_embedding WHERE model_id = ?"
        params = [model_id]

        if photo_ids:
            placeholders = ','.join('?' * len(photo_ids))
            query += f" AND photo_id IN ({placeholders})"
            params.extend(photo_ids)

        query += " LIMIT ? OFFSET ?"

        # Process in batches
        all_results = []
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        offset = 0
        batch_num = 1
        total_batches = (total_count + batch_size - 1) // batch_size

        while offset < total_count:
            # Fetch batch
            cursor = conn.execute(query, params + [batch_size, offset])
            rows = cursor.fetchall()

            if not rows:
                break

            # Process batch
            batch_results = self._process_batch(rows, query_norm, min_similarity)
            all_results.extend(batch_results)

            # Progress callback
            if progress_callback:
                progress_callback(offset + len(rows), total_count)

            # Log progress
            logger.debug(f"[EmbeddingService] Batch {batch_num}/{total_batches}: processed {len(rows)} embeddings, found {len(batch_results)} above threshold")

            offset += batch_size
            batch_num += 1

        # Sort all results by similarity
        all_results.sort(key=lambda x: x[1], reverse=True)

        # Return top K
        top_results = all_results[:top_k]

        logger.info(
            f"[EmbeddingService] Search complete: {total_count} embeddings, "
            f"{len(all_results)} above threshold, returning top {len(top_results)}"
        )

        return top_results

def _process_batch(self,
                  rows: List,
                  query_norm: np.ndarray,
                  min_similarity: float) -> List[Tuple[int, float]]:
    """
    Process a batch of embeddings and compute similarities.

    Args:
        rows: List of (photo_id, embedding_blob) tuples
        query_norm: Normalized query embedding
        min_similarity: Minimum similarity threshold

    Returns:
        List of (photo_id, similarity) tuples above threshold
    """
    batch_results = []
    skipped = 0

    for row in rows:
        photo_id = row["photo_id"]
        embedding_blob = row["embedding"]

        try:
            # Deserialize
            if isinstance(embedding_blob, str):
                try:
                    embedding_blob = bytes.fromhex(embedding_blob)
                except (ValueError, TypeError):
                    embedding_blob = embedding_blob.encode('latin1')

            # Validate dimension
            expected_size = len(query_norm) * 4
            if len(embedding_blob) != expected_size:
                skipped += 1
                continue

            # Compute similarity
            embedding = np.frombuffer(embedding_blob, dtype=np.float32)
            embedding_norm = embedding / np.linalg.norm(embedding)
            similarity = float(np.dot(query_norm, embedding_norm))

            # Filter by threshold
            if similarity >= min_similarity:
                batch_results.append((photo_id, similarity))

        except Exception as e:
            logger.warning(f"[EmbeddingService] Failed to process photo {photo_id}: {e}")
            skipped += 1
            continue

    if skipped > 0:
        logger.debug(f"[EmbeddingService] Batch: skipped {skipped} embeddings")

    return batch_results
```

#### Implementation Steps
1. Add `batch_size` parameter to `search_similar()` with default 1000
2. Add `progress_callback` parameter for UI updates
3. Refactor main loop to fetch embeddings in batches (LIMIT/OFFSET)
4. Extract batch processing logic into `_process_batch()` helper
5. Accumulate results across batches, sort at end
6. Add logging for batch progress
7. Update configuration to add `batch_search_size` option

#### Configuration Changes
```python
# config/embedding_config.py

@dataclass
class SemanticSearchConfig:
    # ... existing fields ...

    # Batch processing for search
    batch_search_size: int = 1000  # Embeddings per batch
    max_search_memory_mb: int = 500  # Max memory for search
```

#### Testing
- Test with small dataset (100 photos)
- Test with medium dataset (10k photos)
- Test with large dataset (100k photos) if available
- Verify memory usage stays under limit
- Verify results identical to current implementation

---

### 1.3 Progress Reporting for Search ⭐⭐

**Priority:** MEDIUM
**Effort:** 2-3 hours
**Files:** `services/embedding_service.py`, `ui/semantic_search_widget.py`

#### Current Issue
```python
# Search blocks UI with no feedback
results = self.embedding_service.search_similar(query_embedding, ...)
# ❌ User has no idea if search is running or frozen
```

#### Proposed Solution

**Part A: Add Progress Callback to Service**
```python
# services/embedding_service.py

def search_similar(self,
                  query_embedding: np.ndarray,
                  progress_callback: Optional[callable] = None,
                  ...):
    """
    Args:
        progress_callback: Optional callback(current, total, message)
    """
    # ... existing code ...

    while offset < total_count:
        # Fetch batch
        cursor = conn.execute(query, params + [batch_size, offset])
        rows = cursor.fetchall()

        # Process batch
        batch_results = self._process_batch(rows, query_norm, min_similarity)
        all_results.extend(batch_results)

        # Progress callback with throttling (every 1000 items or 0.5 seconds)
        now = time.time()
        if progress_callback and (offset % 1000 == 0 or (now - last_progress_time) > 0.5):
            progress_callback(
                offset + len(rows),
                total_count,
                f"Searching... {offset + len(rows)}/{total_count} embeddings"
            )
            last_progress_time = now

        offset += batch_size
```

**Part B: Add Progress Dialog in UI**
```python
# ui/semantic_search_widget.py

from PySide6.QtWidgets import QProgressDialog

def _on_search(self):
    # ... existing code ...

    # Show progress dialog for large collections
    total_embeddings = self._get_embedding_count()

    if total_embeddings > 5000:  # Only show for large collections
        progress_dialog = QProgressDialog(
            "Searching...",
            "Cancel",
            0, total_embeddings,
            self
        )
        progress_dialog.setWindowTitle("Semantic Search")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.show()

        def on_progress(current, total, message):
            progress_dialog.setValue(current)
            progress_dialog.setLabelText(message)

            # Check for cancellation
            if progress_dialog.wasCanceled():
                # TODO: Implement cancellation support
                return

        # Perform search with progress callback
        results = self.embedding_service.search_similar(
            query_embedding,
            progress_callback=on_progress,
            ...
        )

        progress_dialog.close()
    else:
        # Small collection - no progress dialog needed
        results = self.embedding_service.search_similar(query_embedding, ...)
```

#### Implementation Steps
1. Add `progress_callback` parameter to `search_similar()`
2. Call callback with throttling (every 1000 items or 0.5 seconds)
3. Add progress dialog in search widget for large collections (>5000)
4. Add cancellation button (prepare for Phase 2 cancellation support)
5. Add logging for search duration

#### Testing
- Test with small collection (<5000) - no progress dialog
- Test with large collection (>5000) - shows progress dialog
- Verify progress updates smoothly
- Verify search completes successfully

---

### 1.4 Performance Metrics ⭐⭐

**Priority:** MEDIUM
**Effort:** 2-3 hours
**Files:** `services/embedding_service.py`

#### Current Issue
```python
# Basic logging, no structured metrics
logger.info(f"Search complete: {len(results)} results")
# ❌ No timing, no performance tracking, no slow query detection
```

#### Proposed Solution
```python
# services/embedding_service.py

import time
from dataclasses import dataclass, field
from typing import List

@dataclass
class SearchMetrics:
    """Metrics for a semantic search operation."""
    query_text: str
    start_time: float
    end_time: float
    duration_ms: float
    embedding_count: int
    result_count: int
    top_score: float
    avg_score: float
    min_similarity_threshold: float
    cache_hit: bool = False
    batch_count: int = 0
    skipped_embeddings: int = 0
    model_id: int = 0

    def to_dict(self) -> dict:
        return {
            'query': self.query_text,
            'duration_ms': self.duration_ms,
            'embeddings_searched': self.embedding_count,
            'results_found': self.result_count,
            'top_score': self.top_score,
            'avg_score': self.avg_score,
            'threshold': self.min_similarity_threshold,
            'cache_hit': self.cache_hit,
            'batches': self.batch_count,
            'skipped': self.skipped_embeddings,
        }

class EmbeddingService:
    def __init__(self, ...):
        # ... existing code ...
        self._search_metrics: List[SearchMetrics] = []

    def search_similar(self, query_embedding, query_text="", ...):
        """
        Args:
            query_text: Optional query text for metrics logging
        """
        start_time = time.time()

        # ... existing search code ...

        # Compute metrics
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        metrics = SearchMetrics(
            query_text=query_text,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            embedding_count=total_count,
            result_count=len(all_results),
            top_score=all_results[0][1] if all_results else 0.0,
            avg_score=sum(s for _, s in all_results) / len(all_results) if all_results else 0.0,
            min_similarity_threshold=min_similarity,
            cache_hit=False,  # Set by caller if cached
            batch_count=batch_num,
            skipped_embeddings=skipped_count,
            model_id=model_id
        )

        # Log metrics
        self._log_search_metrics(metrics)

        # Store for analysis
        self._search_metrics.append(metrics)

        # Keep only last 100 searches
        if len(self._search_metrics) > 100:
            self._search_metrics.pop(0)

        return top_results

    def _log_search_metrics(self, metrics: SearchMetrics):
        """Log search performance metrics."""
        # Always log duration
        logger.info(
            f"[EmbeddingService] Search completed in {metrics.duration_ms:.0f}ms: "
            f"'{metrics.query_text}' - {metrics.result_count} results, "
            f"top score={metrics.top_score:.3f}"
        )

        # Warn about slow searches (>1 second)
        if metrics.duration_ms > 1000:
            logger.warning(
                f"[EmbeddingService] SLOW SEARCH detected: {metrics.duration_ms:.0f}ms for "
                f"{metrics.embedding_count} embeddings. Consider batch_size tuning."
            )

        # Warn about low match quality
        if metrics.result_count > 0 and metrics.top_score < 0.25:
            logger.warning(
                f"[EmbeddingService] LOW QUALITY results: top score={metrics.top_score:.3f}. "
                f"Consider refining query or checking embeddings."
            )

        # Log detailed metrics at debug level
        logger.debug(f"[EmbeddingService] Search metrics: {metrics.to_dict()}")

    def get_search_statistics(self) -> dict:
        """Get aggregate search statistics."""
        if not self._search_metrics:
            return {}

        return {
            'total_searches': len(self._search_metrics),
            'avg_duration_ms': sum(m.duration_ms for m in self._search_metrics) / len(self._search_metrics),
            'max_duration_ms': max(m.duration_ms for m in self._search_metrics),
            'slow_searches': sum(1 for m in self._search_metrics if m.duration_ms > 1000),
            'avg_results': sum(m.result_count for m in self._search_metrics) / len(self._search_metrics),
            'cache_hit_rate': sum(1 for m in self._search_metrics if m.cache_hit) / len(self._search_metrics),
        }
```

#### Implementation Steps
1. Create `SearchMetrics` dataclass
2. Add metrics collection in `search_similar()`
3. Add `_log_search_metrics()` method with thresholds
4. Add `get_search_statistics()` method for aggregate stats
5. Store last 100 search metrics for analysis
6. Add slow search warning (>1000ms)
7. Add low quality warning (top score <0.25)

#### Testing
- Verify metrics logged for each search
- Verify slow search warning triggers
- Verify statistics calculation correct

---

## PHASE 2: MEDIUM-PRIORITY IMPROVEMENTS

**Timeline:** 3-5 days
**Effort:** 15-21 hours
**Impact:** MEDIUM-HIGH
**Risk:** MEDIUM

### 2.1 Memory Optimization ⭐⭐⭐

**Priority:** HIGH
**Effort:** 6-8 hours
**Files:** `services/embedding_service.py`, `config/embedding_config.py`

#### Current Issue
```python
# No memory limits - can cause OOM for very large collections
# No streaming, no garbage collection hints
```

#### Proposed Solution
```python
# config/embedding_config.py

@dataclass
class PerformanceConfig:
    """Performance optimization settings."""
    # Memory management
    max_search_memory_mb: int = 500  # Maximum memory for search operations
    enable_gc_hints: bool = True  # Enable garbage collection hints

    # Batch sizing
    auto_batch_size: bool = True  # Automatically calculate batch size based on memory
    manual_batch_size: int = 1000  # Manual batch size if auto disabled

# services/embedding_service.py

import gc
import psutil

class EmbeddingService:
    def _calculate_optimal_batch_size(self, total_embeddings: int, embedding_dim: int) -> int:
        """
        Calculate optimal batch size based on available memory.

        Args:
            total_embeddings: Total number of embeddings to search
            embedding_dim: Embedding dimension (512 or 768)

        Returns:
            Optimal batch size
        """
        from config.embedding_config import get_embedding_config
        config = get_embedding_config()

        if not config.performance.auto_batch_size:
            return config.performance.manual_batch_size

        # Get available memory
        available_mb = psutil.virtual_memory().available / (1024 * 1024)
        max_memory_mb = config.performance.max_search_memory_mb

        # Use min of available and configured max
        usable_memory_mb = min(available_mb * 0.5, max_memory_mb)  # Use 50% of available

        # Calculate batch size
        # embedding_dim * 4 bytes (float32) * batch_size = memory in bytes
        bytes_per_embedding = embedding_dim * 4
        batch_size = int((usable_memory_mb * 1024 * 1024) / bytes_per_embedding)

        # Clamp to reasonable range
        batch_size = max(100, min(batch_size, 10000))

        logger.info(
            f"[EmbeddingService] Auto-calculated batch size: {batch_size} "
            f"(available={available_mb:.0f}MB, max={max_memory_mb}MB, dim={embedding_dim})"
        )

        return batch_size

    def search_similar(self, ...):
        """Search with memory optimization."""
        # Auto-calculate batch size
        batch_size = self._calculate_optimal_batch_size(total_count, len(query_embedding))

        # ... existing search code with batching ...

        # Garbage collection hint after search
        if get_embedding_config().performance.enable_gc_hints:
            gc.collect()

        return top_results
```

#### Implementation Steps
1. Add `PerformanceConfig` to `embedding_config.py`
2. Add `psutil` dependency for memory monitoring
3. Implement `_calculate_optimal_batch_size()` method
4. Integrate auto batch sizing into `search_similar()`
5. Add garbage collection hints after large operations
6. Add memory usage logging

#### Dependencies
```bash
pip install psutil  # For memory monitoring
```

#### Testing
- Test with varying available memory
- Verify batch size adjusts automatically
- Verify memory stays under limit
- Test with manual batch size override

---

### 2.2 Search Cancellation ⭐⭐

**Priority:** MEDIUM
**Effort:** 4-6 hours
**Files:** `services/embedding_service.py`, `ui/semantic_search_widget.py`

#### Current Issue
```python
# Search is synchronous and cannot be cancelled
# Long searches block UI with no escape
```

#### Proposed Solution

**Part A: Add Cancellation Flag to Service**
```python
# services/embedding_service.py

class SearchCancelledException(Exception):
    """Raised when search is cancelled."""
    pass

class EmbeddingService:
    def __init__(self, ...):
        # ... existing code ...
        self._cancel_search = False

    def search_similar(self,
                      query_embedding: np.ndarray,
                      cancellation_token: Optional[callable] = None,
                      ...):
        """
        Args:
            cancellation_token: Optional callable that returns True if search should be cancelled
        """
        # ... existing code ...

        while offset < total_count:
            # Check for cancellation
            if cancellation_token and cancellation_token():
                logger.info("[EmbeddingService] Search cancelled by user")
                raise SearchCancelledException("Search cancelled by user")

            # Fetch and process batch
            # ... existing code ...

    def cancel_current_search(self):
        """Cancel currently running search."""
        self._cancel_search = True
```

**Part B: Add Cancellation Support in UI**
```python
# ui/semantic_search_widget.py

class SemanticSearchWidget(QWidget):
    def __init__(self, parent=None):
        # ... existing code ...
        self._search_cancelled = False

    def _on_search(self):
        self._search_cancelled = False

        # Show progress dialog with cancel button
        if total_embeddings > 5000:
            progress_dialog = QProgressDialog(
                "Searching...",
                "Cancel",  # ← Cancel button enabled
                0, total_embeddings,
                self
            )
            progress_dialog.show()

            def cancellation_token():
                """Check if user cancelled."""
                return progress_dialog.wasCanceled() or self._search_cancelled

            try:
                results = self.embedding_service.search_similar(
                    query_embedding,
                    cancellation_token=cancellation_token,
                    ...
                )

                progress_dialog.close()
                self._display_results(results)

            except SearchCancelledException:
                progress_dialog.close()
                self.status_label.setText("Search cancelled")
                logger.info("[SemanticSearch] Search cancelled by user")
            except Exception as e:
                progress_dialog.close()
                self.errorOccurred.emit(str(e))

    def cancel_search(self):
        """Cancel ongoing search (can be called from external button)."""
        self._search_cancelled = True
        logger.info("[SemanticSearch] Cancellation requested")
```

#### Implementation Steps
1. Add `SearchCancelledException` to embedding_service.py
2. Add `cancellation_token` parameter to `search_similar()`
3. Check cancellation token in batch processing loop
4. Update UI to pass cancellation token
5. Handle cancellation exception in UI
6. Add cancel button to progress dialog
7. Test cancellation at various points

#### Testing
- Test cancellation at start of search
- Test cancellation mid-search
- Test cancellation near end of search
- Verify UI responds immediately
- Verify no resource leaks after cancellation

---

### 2.3 Enhanced Query Expansion ⭐⭐

**Priority:** MEDIUM
**Effort:** 3-4 hours
**Files:** `ui/semantic_search_widget.py`

#### Current Status
```python
# 44 hardcoded expansion patterns (lines 76-118)
# Good but could be more comprehensive
```

#### Proposed Enhancements

**Add More Patterns:**
```python
# ui/semantic_search_widget.py

QUERY_EXPANSIONS = {
    # ... existing patterns ...

    # Emotions (new)
    r'\b(happy|happiness)\b': 'person looking happy',
    r'\b(sad|sadness)\b': 'person looking sad',
    r'\b(angry|anger)\b': 'person looking angry',
    r'\b(surprised|surprise)\b': 'person looking surprised',

    # Locations (new)
    r'\b(beach|beaches)\b': 'photo at beach',
    r'\b(mountain|mountains)\b': 'photo of mountains',
    r'\b(city|cities)\b': 'photo in city',
    r'\b(park|parks)\b': 'photo in park',
    r'\b(indoor|indoors)\b': 'photo taken indoors',
    r'\b(outdoor|outdoors)\b': 'photo taken outdoors',

    # Time of day (new)
    r'\b(sunrise)\b': 'sunrise sky',
    r'\b(sunset)\b': 'sunset sky',
    r'\b(night|nighttime)\b': 'night scene',
    r'\b(day|daytime)\b': 'daytime scene',

    # Weather (new)
    r'\b(rain|rainy|raining)\b': 'rainy weather',
    r'\b(snow|snowy|snowing)\b': 'snowy weather',
    r'\b(sun|sunny)\b': 'sunny weather',
    r'\b(cloud|cloudy)\b': 'cloudy sky',

    # Groups (new)
    r'\b(group|groups)\b': 'group of people',
    r'\b(crowd|crowds)\b': 'crowd of people',
    r'\b(family)\b': 'family together',
    r'\b(friends)\b': 'friends together',
    r'\b(couple)\b': 'couple together',

    # Animals (new)
    r'\b(dog|dogs|puppy|puppies)\b': 'dog animal',
    r'\b(cat|cats|kitten|kittens)\b': 'cat animal',
    r'\b(bird|birds)\b': 'bird flying',
    r'\b(fish)\b': 'fish swimming',

    # Food (new)
    r'\b(food|meal)\b': 'food plate',
    r'\b(drink|drinks|beverage)\b': 'drink glass',
    r'\b(cake|cakes)\b': 'cake dessert',
    r'\b(pizza)\b': 'pizza food',
}
```

**Add Spell Checking (Optional):**
```python
from spellchecker import SpellChecker

def expand_query_with_spell_check(query: str) -> str:
    """
    Expand query with spell checking.

    Args:
        query: Original user query

    Returns:
        Spell-checked and expanded query
    """
    spell = SpellChecker()
    words = query.lower().split()

    # Correct misspellings
    corrected_words = []
    for word in words:
        corrected = spell.correction(word)
        if corrected != word:
            logger.info(f"[SemanticSearch] Spell correction: '{word}' → '{corrected}'")
        corrected_words.append(corrected)

    corrected_query = ' '.join(corrected_words)

    # Apply expansion
    expanded = expand_query(corrected_query)

    return expanded
```

#### Implementation Steps
1. Add ~30 new expansion patterns (emotions, locations, time, weather, groups, animals, food)
2. Reorganize patterns by category with comments
3. (Optional) Add spell checking with pyspellchecker
4. Add logging for expansions
5. Test new patterns

#### Dependencies (Optional)
```bash
pip install pyspellchecker  # For spell checking
```

#### Testing
- Test new patterns expand correctly
- Test spell checking corrects typos
- Test expansion doesn't break existing queries

---

### 2.4 Configuration Enhancements ⭐

**Priority:** LOW
**Effort:** 2-3 hours
**Files:** `config/embedding_config.py`

#### Additions
```python
# config/embedding_config.py

@dataclass
class PerformanceConfig:
    """Performance optimization settings."""
    # Memory management
    max_search_memory_mb: int = 500
    enable_gc_hints: bool = True

    # Batch sizing
    auto_batch_size: bool = True
    manual_batch_size: int = 1000

    # Caching
    enable_result_cache: bool = True
    cache_size_entries: int = 100
    cache_ttl_seconds: int = 300  # 5 minutes

    # Progress reporting
    show_progress_threshold: int = 5000  # Show progress for >5000 embeddings
    progress_update_interval_ms: int = 500

@dataclass
class MonitoringConfig:
    """Monitoring and metrics settings."""
    track_search_metrics: bool = True
    log_slow_searches: bool = True
    slow_search_threshold_ms: int = 1000
    log_low_quality_results: bool = True
    low_quality_threshold: float = 0.25

# Add to EmbeddingConfig
class EmbeddingConfig:
    def __init__(self, config_path: Optional[str] = None):
        # ... existing code ...
        self.performance = PerformanceConfig()
        self.monitoring = MonitoringConfig()
```

#### Implementation Steps
1. Add `PerformanceConfig` and `MonitoringConfig` dataclasses
2. Update `EmbeddingConfig.__init__()` to initialize new configs
3. Update `load()` and `save()` methods
4. Update services to use new config options
5. Add validation for config values

---

## PHASE 3: ADVANCED FEATURES (FUTURE)

**Timeline:** 1-2 weeks
**Effort:** 30-44 hours
**Impact:** HIGH (for large collections)
**Risk:** HIGH

### 3.1 FAISS Vector Database Integration ⭐⭐⭐

**Priority:** LOW (until collection >50k photos)
**Effort:** 16-24 hours
**Files:** `services/embedding_service.py`, new: `services/vector_db.py`

#### Overview
FAISS (Facebook AI Similarity Search) provides 10-100x speedup for large collections using approximate nearest neighbor (ANN) algorithms.

#### Implementation Plan

**Part A: Create Vector Database Abstraction**
```python
# services/vector_db.py (NEW FILE)

from abc import ABC, abstractmethod
import numpy as np
from typing import List, Tuple, Optional

class VectorDB(ABC):
    """Abstract base class for vector databases."""

    @abstractmethod
    def add_vectors(self, ids: List[int], vectors: np.ndarray):
        """Add vectors to the index."""
        pass

    @abstractmethod
    def search(self, query_vector: np.ndarray, top_k: int = 10) -> List[Tuple[int, float]]:
        """Search for similar vectors."""
        pass

    @abstractmethod
    def remove_vectors(self, ids: List[int]):
        """Remove vectors from index."""
        pass

    @abstractmethod
    def save(self, path: str):
        """Save index to disk."""
        pass

    @abstractmethod
    def load(self, path: str):
        """Load index from disk."""
        pass

class FAISSVectorDB(VectorDB):
    """FAISS-based vector database."""

    def __init__(self, dimension: int, metric: str = 'cosine'):
        """
        Initialize FAISS index.

        Args:
            dimension: Embedding dimension (512 or 768)
            metric: Distance metric ('cosine', 'euclidean', 'dot')
        """
        try:
            import faiss
            self.faiss = faiss
        except ImportError:
            raise ImportError(
                "FAISS not installed. Install with:\n"
                "pip install faiss-cpu  # For CPU\n"
                "pip install faiss-gpu  # For GPU"
            )

        self.dimension = dimension
        self.metric = metric

        # Create index
        if metric == 'cosine':
            # Use inner product for cosine similarity (vectors must be normalized)
            self.index = faiss.IndexFlatIP(dimension)
        elif metric == 'euclidean':
            self.index = faiss.IndexFlatL2(dimension)
        else:
            raise ValueError(f"Unsupported metric: {metric}")

        # ID mapping (FAISS uses sequential IDs, we need photo IDs)
        self.id_map = []  # List of photo IDs

    def add_vectors(self, ids: List[int], vectors: np.ndarray):
        """Add vectors to FAISS index."""
        # Ensure float32 and contiguous
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)

        # Normalize for cosine similarity
        if self.metric == 'cosine':
            faiss.normalize_L2(vectors)

        # Add to index
        self.index.add(vectors)

        # Update ID map
        self.id_map.extend(ids)

    def search(self, query_vector: np.ndarray, top_k: int = 10) -> List[Tuple[int, float]]:
        """Search FAISS index."""
        # Ensure float32 and 2D
        query_vector = np.ascontiguousarray(query_vector.reshape(1, -1), dtype=np.float32)

        # Normalize for cosine similarity
        if self.metric == 'cosine':
            self.faiss.normalize_L2(query_vector)

        # Search
        distances, indices = self.index.search(query_vector, top_k)

        # Convert to photo IDs and scores
        results = []
        for idx, dist in zip(indices[0], distances[0]):
            if idx < len(self.id_map):
                photo_id = self.id_map[idx]
                score = float(dist)  # For cosine, this is already similarity
                results.append((photo_id, score))

        return results

    def save(self, path: str):
        """Save FAISS index to disk."""
        self.faiss.write_index(self.index, path)
        # Save ID map separately
        import json
        with open(f"{path}.ids.json", 'w') as f:
            json.dump(self.id_map, f)

    def load(self, path: str):
        """Load FAISS index from disk."""
        self.index = self.faiss.read_index(path)
        # Load ID map
        import json
        with open(f"{path}.ids.json", 'r') as f:
            self.id_map = json.load(f)

class SQLiteVectorDB(VectorDB):
    """SQLite-based vector database (fallback)."""
    # Current implementation wrapped in VectorDB interface

# Factory function
def create_vector_db(dimension: int, use_faiss: bool = False) -> VectorDB:
    """
    Create vector database.

    Args:
        dimension: Embedding dimension
        use_faiss: Whether to use FAISS (requires faiss-cpu/faiss-gpu installed)

    Returns:
        VectorDB instance
    """
    if use_faiss:
        try:
            return FAISSVectorDB(dimension)
        except ImportError:
            logger.warning("[VectorDB] FAISS not available, falling back to SQLite")
            return SQLiteVectorDB(dimension)
    else:
        return SQLiteVectorDB(dimension)
```

**Part B: Integrate with EmbeddingService**
```python
# services/embedding_service.py

class EmbeddingService:
    def __init__(self, ...):
        # ... existing code ...
        self._vector_db = None  # Lazy-loaded FAISS index

    def _get_vector_db(self) -> VectorDB:
        """Get or create vector database."""
        if self._vector_db is None:
            from config.embedding_config import get_embedding_config
            config = get_embedding_config()

            # Check if FAISS enabled in config
            use_faiss = config.performance.use_vector_db

            # Create vector DB
            dimension = self._clip_model.config.projection_dim if self._clip_model else 512
            self._vector_db = create_vector_db(dimension, use_faiss=use_faiss)

            # Load existing index if available
            index_path = self._get_index_path()
            if Path(index_path).exists():
                logger.info(f"[EmbeddingService] Loading FAISS index from {index_path}")
                self._vector_db.load(index_path)

        return self._vector_db

    def search_similar_fast(self, query_embedding: np.ndarray, top_k: int = 10):
        """Fast search using FAISS."""
        vector_db = self._get_vector_db()
        return vector_db.search(query_embedding, top_k)

    def rebuild_index(self):
        """Rebuild FAISS index from database."""
        logger.info("[EmbeddingService] Rebuilding FAISS index...")

        # Load all embeddings
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT photo_id, embedding FROM photo_embedding WHERE model_id = ?",
                (self._clip_model_id,)
            )

            photo_ids = []
            embeddings = []

            for row in cursor:
                photo_id = row["photo_id"]
                embedding_blob = row["embedding"]
                embedding = np.frombuffer(embedding_blob, dtype=np.float32)

                photo_ids.append(photo_id)
                embeddings.append(embedding)

        # Build index
        embeddings = np.array(embeddings, dtype=np.float32)
        vector_db = self._get_vector_db()
        vector_db.add_vectors(photo_ids, embeddings)

        # Save index
        index_path = self._get_index_path()
        vector_db.save(index_path)

        logger.info(f"[EmbeddingService] FAISS index built with {len(photo_ids)} vectors")
```

#### Dependencies
```bash
# CPU version
pip install faiss-cpu

# GPU version (if CUDA available)
pip install faiss-gpu
```

#### Implementation Steps
1. Create `services/vector_db.py` with abstract base class
2. Implement `FAISSVectorDB` with basic FLAT index
3. Implement `SQLiteVectorDB` wrapper (current implementation)
4. Add factory function for DB selection
5. Integrate with `EmbeddingService`
6. Add index building/rebuilding functionality
7. Add index persistence (save/load)
8. Add configuration option `use_vector_db`
9. Add UI command to rebuild index (Tools → Rebuild Search Index)
10. Test with large collection (>50k photos)

#### Advanced FAISS Optimizations (Future)
```python
# Use IVF (Inverted File) index for even faster search
# Good for >100k vectors
index = faiss.IndexIVFFlat(quantizer, dimension, nlist=100)

# Use HNSW (Hierarchical Navigable Small World) for best quality/speed
# Good for >1M vectors
index = faiss.IndexHNSWFlat(dimension, M=32)
```

#### Testing
- Test with FAISS installed
- Test without FAISS (fallback to SQLite)
- Benchmark search speed (FAISS vs SQLite)
- Verify results are identical (or very close with ANN)
- Test index persistence (save/load)

---

### 3.2 GPU Batch Optimization ⭐⭐

**Priority:** LOW
**Effort:** 8-12 hours
**Files:** `workers/embedding_worker.py`, `services/embedding_service.py`

#### Overview
Process multiple images simultaneously on GPU for 5x speedup.

#### Implementation
```python
# services/embedding_service.py

def extract_batch_embeddings(self, image_paths: List[str]) -> List[np.ndarray]:
    """
    Extract embeddings for multiple images in one batch (GPU-optimized).

    Args:
        image_paths: List of image file paths

    Returns:
        List of embedding vectors
    """
    # Load images
    images = []
    for path in image_paths:
        try:
            img = Image.open(path).convert('RGB')
            images.append(img)
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")
            images.append(None)

    # Filter out failed images
    valid_indices = [i for i, img in enumerate(images) if img is not None]
    valid_images = [images[i] for i in valid_indices]

    if not valid_images:
        return []

    # Process batch
    inputs = self._clip_processor(
        images=valid_images,
        return_tensors="pt",
        padding=True
    )
    inputs = {k: v.to(self.device) for k, v in inputs.items()}

    # Extract embeddings
    with self._torch.no_grad():
        image_features = self._clip_model.get_image_features(**inputs)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

    # Convert to numpy
    embeddings = image_features.cpu().numpy()

    # Create result list with None for failed images
    result = [None] * len(image_paths)
    for i, emb in zip(valid_indices, embeddings):
        result[i] = emb

    return result

# workers/embedding_worker.py

def run(self):
    # ... existing code ...

    # Process photos in batches
    batch_size = 8  # Process 8 images at once on GPU

    for batch_start in range(0, len(self.photo_ids), batch_size):
        batch_end = min(batch_start + batch_size, len(self.photo_ids))
        batch_ids = self.photo_ids[batch_start:batch_end]

        # Get paths
        batch_paths = [self._get_photo_path(pid) for pid in batch_ids]

        # Extract batch
        batch_embeddings = self.embedding_service.extract_batch_embeddings(batch_paths)

        # Store
        for photo_id, embedding in zip(batch_ids, batch_embeddings):
            if embedding is not None:
                self.embedding_service.store_embedding(photo_id, embedding, model_id)
                self.success_count += 1
            else:
                self.failed_count += 1
```

---

### 3.3 Advanced Caching ⭐⭐

**Priority:** LOW
**Effort:** 6-8 hours
**Files:** New: `services/search_cache.py`

#### Overview
Sophisticated multi-level caching with LRU, TTL, and smart invalidation.

#### Implementation
```python
# services/search_cache.py (NEW FILE)

from cachetools import LRUCache, TTLCache
from typing import Dict, List, Tuple, Optional
import hashlib

class SearchCache:
    """
    Multi-level cache for semantic search.

    Levels:
    1. Query cache: (query_text, threshold) → results (TTL-based)
    2. Embedding cache: photo_id → embedding (LRU)
    3. Similarity cache: (query_hash, photo_id) → similarity (LRU)
    """

    def __init__(self,
                 query_cache_size: int = 100,
                 query_cache_ttl: int = 300,
                 embedding_cache_size: int = 10000,
                 similarity_cache_size: int = 100000):
        """
        Initialize multi-level cache.

        Args:
            query_cache_size: Max query results to cache
            query_cache_ttl: Query cache TTL in seconds
            embedding_cache_size: Max embeddings to cache in memory
            similarity_cache_size: Max similarity scores to cache
        """
        # Level 1: Query results (TTL cache)
        self.query_cache = TTLCache(maxsize=query_cache_size, ttl=query_cache_ttl)

        # Level 2: Embeddings (LRU cache)
        self.embedding_cache = LRUCache(maxsize=embedding_cache_size)

        # Level 3: Similarity scores (LRU cache)
        self.similarity_cache = LRUCache(maxsize=similarity_cache_size)

        # Statistics
        self.stats = {
            'query_hits': 0,
            'query_misses': 0,
            'embedding_hits': 0,
            'embedding_misses': 0,
            'similarity_hits': 0,
            'similarity_misses': 0,
        }

    def get_query_key(self, query: str, threshold: float, model_id: int) -> str:
        """Generate cache key for query."""
        key_str = f"{query}|{threshold:.3f}|{model_id}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get_query_results(self, query: str, threshold: float, model_id: int) -> Optional[List]:
        """Get cached query results."""
        key = self.get_query_key(query, threshold, model_id)
        if key in self.query_cache:
            self.stats['query_hits'] += 1
            return self.query_cache[key]
        self.stats['query_misses'] += 1
        return None

    def set_query_results(self, query: str, threshold: float, model_id: int, results: List):
        """Cache query results."""
        key = self.get_query_key(query, threshold, model_id)
        self.query_cache[key] = results

    def invalidate_all(self):
        """Clear all caches."""
        self.query_cache.clear()
        self.embedding_cache.clear()
        self.similarity_cache.clear()

    def get_statistics(self) -> Dict:
        """Get cache statistics."""
        total_query = self.stats['query_hits'] + self.stats['query_misses']
        total_embedding = self.stats['embedding_hits'] + self.stats['embedding_misses']

        return {
            'query_hit_rate': self.stats['query_hits'] / total_query if total_query > 0 else 0,
            'embedding_hit_rate': self.stats['embedding_hits'] / total_embedding if total_embedding > 0 else 0,
            'query_cache_size': len(self.query_cache),
            'embedding_cache_size': len(self.embedding_cache),
            **self.stats
        }
```

---

## TESTING STRATEGY

### Unit Tests

**Priority Files:**
1. `services/embedding_service.py` - search_similar, batch processing
2. `services/search_cache.py` - caching logic
3. `config/embedding_config.py` - configuration loading/saving

**Test Coverage:**
```python
# tests/test_embedding_search.py (NEW FILE)

import pytest
import numpy as np
from services.embedding_service import EmbeddingService

class TestEmbeddingSearch:
    def test_batch_processing(self):
        """Test batch processing produces same results as sequential."""
        service = EmbeddingService()
        query_embedding = np.random.rand(512).astype(np.float32)

        # Sequential
        results_seq = service.search_similar(query_embedding, batch_size=1)

        # Batched
        results_batch = service.search_similar(query_embedding, batch_size=1000)

        # Should be identical
        assert results_seq == results_batch

    def test_search_cancellation(self):
        """Test search can be cancelled."""
        service = EmbeddingService()
        query_embedding = np.random.rand(512).astype(np.float32)

        cancelled = False
        def cancel_token():
            nonlocal cancelled
            return cancelled

        # Start search then cancel
        import threading
        def cancel_after_delay():
            time.sleep(0.1)
            nonlocal cancelled
            cancelled = True

        threading.Thread(target=cancel_after_delay).start()

        with pytest.raises(SearchCancelledException):
            service.search_similar(query_embedding, cancellation_token=cancel_token)

    def test_memory_limit(self):
        """Test memory stays under limit."""
        service = EmbeddingService()
        # ... test memory usage ...
```

### Integration Tests

**Test Scenarios:**
1. Search with 100 photos
2. Search with 10,000 photos
3. Search with cache enabled/disabled
4. Search with cancellation
5. Search with different batch sizes

### Performance Benchmarks

```python
# benchmarks/benchmark_search.py (NEW FILE)

import time
import numpy as np

def benchmark_search(num_embeddings: int, batch_sizes: List[int]):
    """Benchmark search with different batch sizes."""
    for batch_size in batch_sizes:
        start = time.time()
        results = service.search_similar(query, batch_size=batch_size)
        duration = time.time() - start

        print(f"Batch size {batch_size}: {duration:.2f}s ({num_embeddings/duration:.0f} embeddings/s)")
```

---

## DEPLOYMENT PLAN

### Phase 1 Deployment (Week 1)

1. **Day 1-2:** Implement caching and batch processing
2. **Day 2:** Testing and bug fixes
3. **Day 3:** Code review and documentation
4. **Day 3:** Deploy to main branch

### Phase 2 Deployment (Week 2-3)

1. **Week 2:** Implement memory optimization and cancellation
2. **Week 2:** Testing and performance benchmarks
3. **Week 3:** Code review and deploy

### Phase 3 Deployment (Future)

1. **When needed:** Implement FAISS integration
2. **Test extensively:** Benchmark with large collections
3. **Deploy as optional feature**

---

## ROLLBACK PLAN

### If Issues Arise

1. **Caching Issues:**
   - Disable caching via config: `enable_result_cache = False`
   - Clear cache: Delete TTLCache entries

2. **Batch Processing Issues:**
   - Set `batch_size = 1` for sequential processing
   - Fall back to current implementation

3. **Memory Issues:**
   - Reduce `batch_size`
   - Disable auto batch sizing: `auto_batch_size = False`

4. **FAISS Issues:**
   - Set `use_vector_db = False` in config
   - Falls back to SQLite automatically

---

## SUCCESS METRICS

### Performance Metrics

**Phase 1:**
- ✅ Search speed: 50% faster for repeated queries (caching)
- ✅ Memory usage: 30-50% reduction for large datasets (batching)
- ✅ User feedback: Progress shown for large collections

**Phase 2:**
- ✅ Memory stability: No OOM for collections up to 100k photos
- ✅ Cancellation: Search stops within 1 second of cancel request
- ✅ Slow queries: <5% of searches take >1 second

**Phase 3:**
- ✅ FAISS speedup: 10-100x faster for large collections (>50k)
- ✅ GPU batching: 5x faster embedding extraction

### Quality Metrics

- ✅ No regression in search quality
- ✅ Same or better results compared to current implementation
- ✅ Cache hit rate: >30% for typical usage

### User Experience

- ✅ No user-facing breaking changes
- ✅ Seamless upgrade (no manual steps required)
- ✅ Better feedback during long operations

---

## CONCLUSION

This implementation plan provides a **comprehensive, phased approach** to improving embedding extraction and semantic search functionality. All proposed improvements are:

✅ **Implementable** - Based on proven technologies and best practices
✅ **Low-risk** - Incremental changes with fallbacks
✅ **High-impact** - Significant performance and UX improvements
✅ **Well-tested** - Comprehensive testing strategy
✅ **Backward-compatible** - No breaking changes

**Recommendation:** Proceed with **Phase 1 implementation** immediately.

---

**Document Status:** ✅ COMPLETE & READY FOR IMPLEMENTATION
**Next Action:** Begin Phase 1 implementation
**Estimated Completion:** 3-5 days for Phases 1-2
