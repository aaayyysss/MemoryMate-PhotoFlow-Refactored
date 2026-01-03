"""
Semantic Search Widget - Natural Language Photo Search

Version: 1.0.0
Date: 2026-01-01

Widget for searching photos by natural language descriptions using
CLIP/SigLIP visual embeddings.

Features:
- Text input for natural language queries
- Real-time search as user types
- Display results in main grid
- Integration with EmbeddingService

Usage:
    widget = SemanticSearchWidget(parent)
    widget.searchTriggered.connect(on_semantic_search)
    toolbar.addWidget(widget)
"""

from PySide6.QtWidgets import (
    QWidget, QLineEdit, QPushButton, QHBoxLayout, QLabel,
    QMessageBox, QProgressDialog, QFileDialog, QSlider, QVBoxLayout
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon, QPixmap

from typing import Optional, List, Tuple
import numpy as np
import time
from pathlib import Path
import re

from services.embedding_service import get_embedding_service
from services.search_history_service import get_search_history_service
from repository.photo_repository import PhotoRepository
from logging_config import get_logger
from translation_manager import tr

logger = get_logger(__name__)


def expand_query(query: str) -> str:
    """
    Expand simple queries into more descriptive phrases for better CLIP matching.

    CLIP models are trained on image captions, so 'eyes' → 'close-up photo of
    person's eyes' produces much better results.

    Args:
        query: Original user query

    Returns:
        Expanded query if pattern matches, otherwise original query
    """
    query_lower = query.lower().strip()

    # Skip expansion if query is already descriptive (3+ words)
    if len(query_lower.split()) >= 3:
        return query

    # Try to match and expand single-word or 2-word queries
    for pattern, expansion in QUERY_EXPANSIONS.items():
        if re.search(pattern, query_lower, re.IGNORECASE):
            expanded = re.sub(pattern, expansion, query_lower, count=1, flags=re.IGNORECASE)
            logger.info(f"[SemanticSearch] Query expansion: '{query}' → '{expanded}'")
            return expanded

    # No expansion matched, return original
    return query


# Query expansion mapping for common terms
QUERY_EXPANSIONS = {
    # Body parts - expand to contextualized descriptions
    r'\b(eye|eyes)\b': 'close-up photo of person\'s eyes',
    r'\b(mouth|lips)\b': 'close-up photo of person\'s mouth',
    r'\b(nose)\b': 'close-up photo of person\'s nose',
    r'\b(face|faces)\b': 'portrait photo of person\'s face',
    r'\b(hand|hands)\b': 'photo of person\'s hands',
    r'\b(finger|fingers)\b': 'photo of person\'s fingers',
    r'\b(head|heads)\b': 'photo of person\'s head',
    r'\b(hair)\b': 'photo showing person\'s hair',
    r'\b(ear|ears)\b': 'photo of person\'s ears',

    # Colors - add context
    r'\b(blue)\b': 'photo with blue color',
    r'\b(red)\b': 'photo with red color',
    r'\b(green)\b': 'photo with green color',
    r'\b(yellow)\b': 'photo with yellow color',
    r'\b(black)\b': 'photo with black color',
    r'\b(white)\b': 'photo with white color',

    # Common objects
    r'\b(window|windows)\b': 'photo of building with windows',
    r'\b(door|doors)\b': 'photo of door or entrance',
    r'\b(car|cars)\b': 'photo of car or vehicle',
    r'\b(tree|trees)\b': 'photo of trees in nature',
    r'\b(sky)\b': 'photo with visible sky',
    r'\b(cloud|clouds)\b': 'photo of clouds in the sky',

    # Activities
    r'\b(smile|smiling)\b': 'photo of person smiling',
    r'\b(laugh|laughing)\b': 'photo of person laughing',
    r'\b(walk|walking)\b': 'photo of person walking',
    r'\b(run|running)\b': 'photo of person running',
}


class SemanticSearchWidget(QWidget):
    """
    Semantic search bar for natural language photo search.

    Emits signals when search is triggered with results.
    """

    # Signal: (photo_ids, query_text, scores)
    # scores is a list of (photo_id, similarity_score) tuples
    searchTriggered = Signal(list, str, list)

    # Signal: () - emitted when search is cleared
    searchCleared = Signal()

    # Signal: (error_message)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.embedding_service = None
        self.photo_repo = PhotoRepository()
        self.search_history_service = get_search_history_service()
        self._last_query = ""
        self._query_image_path = None  # Path to uploaded query image
        self._query_image_embedding = None  # Cached image embedding
        self._search_start_time = None  # For timing searches
        self._min_similarity = 0.25  # Default similarity threshold (configurable via slider)
        self._slider_debounce_timer = None  # Timer for debouncing slider changes
        self._setup_ui()

    def _setup_ui(self):
        """Setup the semantic search UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Semantic search icon/label
        search_label = QLabel("🔍✨")  # Magic search icon
        search_label.setToolTip("Semantic Search - Describe what you're looking for")
        layout.addWidget(search_label)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Describe the photo (e.g., 'sunset beach', 'dog playing in park')..."
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(300)
        self.search_input.returnPressed.connect(self._on_search)
        self.search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.search_input, 1)

        # Image query button (multi-modal search)
        self.image_btn = QPushButton("📷 +Image")
        self.image_btn.setToolTip("Add an image to your search query (multi-modal search)")
        self.image_btn.clicked.connect(self._on_upload_image)
        layout.addWidget(self.image_btn)

        # Search button
        self.search_btn = QPushButton("Semantic Search")
        self.search_btn.setToolTip("Search photos by description using AI")
        self.search_btn.clicked.connect(self._on_search)
        layout.addWidget(self.search_btn)

        # History button
        self.history_btn = QPushButton("📜 History")
        self.history_btn.setToolTip("View recent searches")
        self.history_btn.clicked.connect(self._on_show_history)
        layout.addWidget(self.history_btn)

        # Similarity threshold slider
        threshold_layout = QVBoxLayout()
        threshold_layout.setSpacing(2)

        self.threshold_label = QLabel(f"Min: {int(self._min_similarity * 100)}%")
        self.threshold_label.setToolTip("Minimum similarity threshold - higher = stricter matching")
        self.threshold_label.setStyleSheet("font-size: 9pt; color: #666;")
        threshold_layout.addWidget(self.threshold_label)

        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setMinimum(10)  # 10% = 0.10
        self.threshold_slider.setMaximum(50)  # 50% = 0.50
        self.threshold_slider.setValue(int(self._min_similarity * 100))  # Default 25%
        self.threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_slider.setTickInterval(10)
        self.threshold_slider.setMaximumWidth(120)
        self.threshold_slider.setToolTip(
            "Adjust similarity threshold:\n"
            "• 10-20%: Very permissive (may include unrelated photos)\n"
            "• 25-30%: Balanced (recommended)\n"
            "• 35-50%: Strict (only close matches)"
        )
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        threshold_layout.addWidget(self.threshold_slider)

        layout.addLayout(threshold_layout)

        # Preset buttons for quick threshold selection
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(4)

        self.lenient_btn = QPushButton("Lenient")
        self.lenient_btn.setToolTip("Show more results (15% threshold)")
        self.lenient_btn.setMaximumWidth(70)
        self.lenient_btn.clicked.connect(lambda: self._set_preset_threshold(15))
        preset_layout.addWidget(self.lenient_btn)

        self.balanced_btn = QPushButton("Balanced")
        self.balanced_btn.setToolTip("Recommended setting (25% threshold)")
        self.balanced_btn.setMaximumWidth(75)
        self.balanced_btn.setStyleSheet("font-weight: bold;")  # Default preset
        self.balanced_btn.clicked.connect(lambda: self._set_preset_threshold(25))
        preset_layout.addWidget(self.balanced_btn)

        self.strict_btn = QPushButton("Strict")
        self.strict_btn.setToolTip("Only close matches (35% threshold)")
        self.strict_btn.setMaximumWidth(70)
        self.strict_btn.clicked.connect(lambda: self._set_preset_threshold(35))
        preset_layout.addWidget(self.strict_btn)

        layout.addLayout(preset_layout)

        # Clear button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setToolTip("Show all photos")
        self.clear_btn.clicked.connect(self._on_clear)
        self.clear_btn.setVisible(False)  # Hidden until search is active
        layout.addWidget(self.clear_btn)

        # Status label (shows result count)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # Debounce timer for live search (optional)
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._on_search)

        # Debounce timer for slider changes
        self._slider_debounce_timer = QTimer()
        self._slider_debounce_timer.setSingleShot(True)
        self._slider_debounce_timer.setInterval(500)  # 500ms delay

        # Initialize preset button highlighting (Balanced is default)
        self._update_preset_buttons(25)

    def _on_text_changed(self, text: str):
        """Handle text change - can enable live search if desired."""
        # Disable live search for now (too expensive with embeddings)
        # User must press Enter or click Search button
        pass

    def _on_threshold_changed(self, value: int):
        """Handle similarity threshold slider change with debouncing."""
        self._min_similarity = value / 100.0
        self.threshold_label.setText(f"Min: {value}%")

        # Update preset button highlighting
        self._update_preset_buttons(value)

        # Debounce: only log after user stops dragging for 500ms
        if self._slider_debounce_timer.isActive():
            self._slider_debounce_timer.stop()

        self._slider_debounce_timer.timeout.disconnect()
        self._slider_debounce_timer.timeout.connect(
            lambda: logger.info(f"[SemanticSearch] Threshold set to {self._min_similarity:.0%}")
        )
        self._slider_debounce_timer.start()

    def _set_preset_threshold(self, value: int):
        """Set threshold to preset value (Lenient=15%, Balanced=25%, Strict=35%)."""
        self.threshold_slider.setValue(value)
        logger.info(f"[SemanticSearch] Preset threshold applied: {value}%")

    def _update_preset_buttons(self, value: int):
        """Update visual highlighting of preset buttons based on current threshold."""
        # Clear all button highlighting
        self.lenient_btn.setStyleSheet("")
        self.balanced_btn.setStyleSheet("")
        self.strict_btn.setStyleSheet("")

        # Highlight the active preset (with tolerance of ±2%)
        if abs(value - 15) <= 2:
            self.lenient_btn.setStyleSheet("font-weight: bold; background-color: #4CAF50; color: white;")
        elif abs(value - 25) <= 2:
            self.balanced_btn.setStyleSheet("font-weight: bold; background-color: #2196F3; color: white;")
        elif abs(value - 35) <= 2:
            self.strict_btn.setStyleSheet("font-weight: bold; background-color: #FF9800; color: white;")

    def _suggest_threshold(self, scores: List[float]) -> Optional[str]:
        """
        Analyze score distribution and suggest optimal threshold.

        Args:
            scores: List of similarity scores from search results

        Returns:
            Suggestion message or None if current threshold is optimal
        """
        if not scores:
            return None

        top_score = scores[0]
        avg_score = sum(scores) / len(scores)
        current_threshold = self._min_similarity

        # Case 1: Very low scores (< 0.25) - might need query expansion or different search terms
        if top_score < 0.25:
            return (
                f"💡 Suggestion: Low match scores detected (top: {top_score:.1%}). "
                "Try more descriptive search terms or check if embeddings are extracted."
            )

        # Case 2: Top score is good but current threshold too strict
        if top_score > 0.35 and current_threshold > 0.30 and len(scores) < 5:
            return (
                f"💡 Suggestion: Good matches found (top: {top_score:.1%}), but only {len(scores)} results. "
                f"Try lowering threshold to ~{int(avg_score * 100 - 5)}% to see more relevant photos."
            )

        # Case 3: Many results with low average - threshold too lenient
        if len(scores) > 50 and avg_score < current_threshold + 0.05:
            return (
                f"💡 Suggestion: Many results ({len(scores)}) with low average similarity ({avg_score:.1%}). "
                f"Try raising threshold to ~{int(avg_score * 100 + 10)}% for better quality."
            )

        # Case 4: Perfect range - no suggestion needed
        if 10 <= len(scores) <= 30 and avg_score > current_threshold + 0.05:
            return None  # Good results, no suggestion

        return None

    def _show_suggestion_toast(self, message: str):
        """Show threshold suggestion as a non-blocking message."""
        # Use status label for now (could be upgraded to toast notification)
        original_text = self.status_label.text()
        self.status_label.setText(f"{original_text} | {message}")
        self.status_label.setStyleSheet("color: #FF9800; font-style: italic; font-weight: bold;")

        # Reset style after 5 seconds
        QTimer.singleShot(5000, lambda: self.status_label.setStyleSheet("color: #666; font-style: italic;"))

    def _on_upload_image(self):
        """Handle image upload for multi-modal search."""
        # Open file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Query Image",
            "",
            "Images (*.jpg *.jpeg *.png *.heic *.bmp);;All Files (*)"
        )

        if not file_path:
            return

        try:
            logger.info(f"[SemanticSearch] Loading query image: {file_path}")

            # Check if embedding service is available
            if self.embedding_service is None:
                self.embedding_service = get_embedding_service()

            if not self.embedding_service.available:
                QMessageBox.warning(
                    self,
                    "Feature Unavailable",
                    "Multi-modal search requires PyTorch and Transformers.\n\n"
                    "Install dependencies:\n"
                    "pip install torch transformers pillow"
                )
                return

            # Load model if needed
            if self.embedding_service._clip_model is None:
                # Auto-select best available CLIP model variant
                from utils.clip_check import get_recommended_variant, MODEL_CONFIGS
                variant = get_recommended_variant()
                config = MODEL_CONFIGS.get(variant, {})

                progress = QProgressDialog(
                    f"Loading {config.get('description', 'CLIP model')}...",
                    None,
                    0, 0,
                    self
                )
                progress.setWindowTitle("Loading AI Model")
                progress.setWindowModality(Qt.WindowModal)
                progress.show()

                try:
                    self.embedding_service.load_clip_model(variant)
                    progress.close()
                except Exception as e:
                    progress.close()
                    QMessageBox.critical(
                        self,
                        "Model Loading Failed",
                        f"Failed to load CLIP model ({variant}):\n{e}"
                    )
                    return

            # Extract embedding from image
            self._query_image_embedding = self.embedding_service.extract_image_embedding(
                file_path
            )
            self._query_image_path = file_path

            # Update UI to show image is loaded
            image_name = Path(file_path).name
            self.image_btn.setText(f"📷 {image_name[:15]}...")
            self.image_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                }
            """)

            logger.info(f"[SemanticSearch] Query image loaded: {image_name}")

            # Show info
            QMessageBox.information(
                self,
                "Image Loaded",
                f"Query image loaded: {image_name}\n\n"
                "You can now:\n"
                "• Search with just the image (leave text empty)\n"
                "• Combine image + text for multi-modal search\n"
                "• Click 'Clear' to remove the image"
            )

        except Exception as e:
            logger.error(f"[SemanticSearch] Failed to load query image: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Image Load Failed",
                f"Failed to load query image:\n{e}"
            )

    def _on_search(self):
        """Trigger semantic search (supports multi-modal: text + image)."""
        query = self.search_input.text().strip()
        has_text = bool(query)
        has_image = self._query_image_embedding is not None

        # Must have at least one query type
        if not has_text and not has_image:
            self._on_clear()
            return

        # Skip if same text query and no image
        if has_text and query == self._last_query and not has_image:
            logger.info(f"[SemanticSearch] Same query, skipping: {query}")
            return

        query_desc = []
        if has_text:
            query_desc.append(f"text: '{query}'")
        if has_image:
            query_desc.append(f"image: {Path(self._query_image_path).name}")
        logger.info(f"[SemanticSearch] Searching for: {', '.join(query_desc)}")
        self._last_query = query

        # Start timing
        self._search_start_time = time.time()

        try:
            # Check if embedding service is available
            if self.embedding_service is None:
                self.embedding_service = get_embedding_service()

            if not self.embedding_service.available:
                QMessageBox.warning(
                    self,
                    "Semantic Search Unavailable",
                    "Semantic search requires PyTorch and Transformers.\n\n"
                    "Install dependencies:\n"
                    "pip install torch transformers pillow"
                )
                self.errorOccurred.emit("Dependencies not available")
                return

            # Check if model is loaded
            if self.embedding_service._clip_model is None:
                # Auto-select best available CLIP model variant
                from utils.clip_check import get_recommended_variant, MODEL_CONFIGS
                variant = get_recommended_variant()
                config = MODEL_CONFIGS.get(variant, {})

                logger.info(
                    f"[SemanticSearch] Auto-selected CLIP variant: {variant} "
                    f"({config.get('description', 'unknown')})"
                )

                # Show loading dialog
                progress = QProgressDialog(
                    f"Loading {config.get('description', 'CLIP model')} for first-time search...\n"
                    f"({config.get('dimension', '???')}-D embeddings, {config.get('size_mb', '???')}MB)",
                    None,  # No cancel button
                    0, 0,  # Indeterminate
                    self
                )
                progress.setWindowTitle("Loading AI Model")
                progress.setWindowModality(Qt.WindowModal)
                progress.show()

                try:
                    self.embedding_service.load_clip_model(variant)
                    progress.close()
                except Exception as e:
                    progress.close()
                    QMessageBox.critical(
                        self,
                        "Model Loading Failed",
                        f"Failed to load CLIP model ({variant}):\n{e}\n\n"
                        "Check console for details."
                    )
                    self.errorOccurred.emit(str(e))
                    return

            # Apply query expansion for better CLIP matching
            expanded_query = query
            if has_text:
                expanded_query = expand_query(query)

            # Extract query embedding (multi-modal support)
            query_embedding = None

            if has_text and has_image:
                # Multi-modal: combine text + image embeddings
                logger.info("[SemanticSearch] Extracting multi-modal query embedding (text + image)...")
                text_embedding = self.embedding_service.extract_text_embedding(expanded_query)
                image_embedding = self._query_image_embedding

                # Weighted average (50/50 by default)
                # Can be adjusted: 0.7 text + 0.3 image, etc.
                text_weight = 0.5
                image_weight = 0.5

                query_embedding = (text_weight * text_embedding + image_weight * image_embedding)

                # Normalize the combined embedding
                query_embedding = query_embedding / np.linalg.norm(query_embedding)

                logger.info(f"[SemanticSearch] Combined embeddings: {text_weight}*text + {image_weight}*image")

            elif has_text:
                # Text-only search
                logger.info("[SemanticSearch] Extracting text query embedding...")
                query_embedding = self.embedding_service.extract_text_embedding(expanded_query)

            elif has_image:
                # Image-only search
                logger.info("[SemanticSearch] Using image query embedding...")
                query_embedding = self._query_image_embedding

            else:
                raise ValueError("No query provided (neither text nor image)")

            # Search for similar images
            logger.info(f"[SemanticSearch] Searching database (min_similarity={self._min_similarity:.2f})...")
            results = self.embedding_service.search_similar(
                query_embedding,
                top_k=100,  # Get top 100 results
                model_id=self.embedding_service._clip_model_id,
                min_similarity=self._min_similarity
            )

            if not results:
                # Build context-aware no-results message
                suggestions = []

                # Check if query was expanded
                if expanded_query != query:
                    suggestions.append(
                        f"✓ Query expanded: '{query}' → '{expanded_query}'\n"
                        "  (Still no matches - try different terms)"
                    )

                # Check threshold
                if self._min_similarity >= 0.30:
                    suggestions.append(
                        f"• Lower threshold: Currently {self._min_similarity:.0%} (Strict)\n"
                        "  Try clicking 'Balanced' (25%) or 'Lenient' (15%)"
                    )
                else:
                    suggestions.append(
                        f"• Try different search terms\n"
                        "  Current threshold ({self._min_similarity:.0%}) is already lenient"
                    )

                # Check embedding count
                try:
                    embedding_count = self.embedding_service.get_embedding_count()
                    if embedding_count == 0:
                        suggestions.append(
                            "⚠ No embeddings found in database!\n"
                            "  Run: Scan → Extract Embeddings first"
                        )
                    else:
                        suggestions.append(
                            f"✓ {embedding_count} embeddings in database\n"
                            "  Try more descriptive queries (e.g., 'sunset beach' instead of 'sunset')"
                        )
                except Exception:
                    suggestions.append(
                        "• Make sure embeddings have been extracted\n"
                        "  (Scan → Extract Embeddings)"
                    )

                QMessageBox.information(
                    self,
                    "No Search Results",
                    f"No photos found matching '{query}' (similarity ≥ {self._min_similarity:.0%}).\n\n"
                    + "\n".join(suggestions)
                )
                self.status_label.setText(f"No results ≥{self._min_similarity:.0%}")
                self.status_label.setVisible(True)
                return

            # Extract photo IDs and analyze score distribution
            photo_ids = [photo_id for photo_id, score in results]
            scores = [score for _, score in results]

            # Calculate score statistics for smart suggestions
            top_score = scores[0]
            avg_score = sum(scores) / len(scores)
            min_score = scores[-1]

            logger.info(
                f"[SemanticSearch] Found {len(results)} results, "
                f"top score: {top_score:.3f}, avg: {avg_score:.3f}, min: {min_score:.3f}"
            )

            # Smart threshold suggestion based on score distribution
            threshold_suggestion = self._suggest_threshold(scores)
            if threshold_suggestion:
                logger.info(f"[SemanticSearch] {threshold_suggestion}")

            # Update UI state with score distribution
            self.clear_btn.setVisible(True)

            # Create detailed status message with score distribution
            status_parts = [
                f"Found {len(results)} matches ≥{self._min_similarity:.0%}",
                f"Top: {top_score:.1%}",
                f"Avg: {avg_score:.1%}"
            ]

            # Add quality indicator
            if top_score >= 0.40:
                status_parts.append("🟢 Excellent")
            elif top_score >= 0.30:
                status_parts.append("🟡 Good")
            elif top_score >= 0.20:
                status_parts.append("🟠 Fair")
            else:
                status_parts.append("🔴 Weak")

            self.status_label.setText(" | ".join(status_parts))
            self.status_label.setVisible(True)

            # Show suggestion if available
            if threshold_suggestion:
                QTimer.singleShot(1000, lambda: self._show_suggestion_toast(threshold_suggestion))

            # Calculate execution time
            execution_time_ms = (time.time() - self._search_start_time) * 1000

            # Record search in history
            query_type = 'semantic_text' if (has_text and not has_image) else \
                        'semantic_image' if (has_image and not has_text) else \
                        'semantic_multi'

            self.search_history_service.record_search(
                query_type=query_type,
                query_text=query if has_text else None,
                query_image_path=self._query_image_path if has_image else None,
                result_count=len(results),
                top_photo_ids=photo_ids[:10],  # Store top 10
                execution_time_ms=execution_time_ms,
                model_id=self.embedding_service._clip_model_id
            )

            # Emit signal with results and scores
            # results is already a list of (photo_id, score) tuples
            self.searchTriggered.emit(photo_ids, query, results)

        except Exception as e:
            logger.error(f"[SemanticSearch] Search failed: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Search Failed",
                f"Semantic search failed:\n{e}\n\n"
                "Check console for details."
            )
            self.errorOccurred.emit(str(e))

    def _on_clear(self):
        """Clear search and show all photos."""
        self.search_input.clear()
        self._last_query = ""
        self._query_image_path = None
        self._query_image_embedding = None

        # Reset image button
        self.image_btn.setText("📷 +Image")
        self.image_btn.setStyleSheet("")

        self.clear_btn.setVisible(False)
        self.status_label.setVisible(False)
        self.searchCleared.emit()
        logger.info("[SemanticSearch] Search cleared")

    def get_query(self) -> str:
        """Get current query text."""
        return self.search_input.text().strip()

    def set_enabled(self, enabled: bool):
        """Enable/disable the search widget."""
        self.search_input.setEnabled(enabled)
        self.search_btn.setEnabled(enabled)

    def _on_show_history(self):
        """Show search history dialog."""
        from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QVBoxLayout, QDialogButtonBox

        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Search History")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(400)

        layout = QVBoxLayout(dialog)

        # Info label
        info = QLabel("Click on a search to re-run it")
        info.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(info)

        # List widget
        list_widget = QListWidget()
        list_widget.setAlternatingRowColors(True)

        # Load recent searches
        recent_searches = self.search_history_service.get_recent_searches(limit=50)

        if not recent_searches:
            no_results = QLabel("No search history yet.\n\nYour searches will appear here.")
            no_results.setAlignment(Qt.AlignCenter)
            no_results.setStyleSheet("color: #999; padding: 40px;")
            layout.addWidget(no_results)
        else:
            for search in recent_searches:
                # Format display text
                if search.query_type == 'semantic_text':
                    text = f"🔍 Text: \"{search.query_text}\""
                elif search.query_type == 'semantic_image':
                    image_name = Path(search.query_image_path).name if search.query_image_path else "Unknown"
                    text = f"📷 Image: {image_name}"
                elif search.query_type == 'semantic_multi':
                    image_name = Path(search.query_image_path).name if search.query_image_path else "Unknown"
                    text = f"✨ Multi: \"{search.query_text}\" + {image_name}"
                else:
                    text = f"❓ {search.query_type}"

                # Add metadata
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(search.created_at)
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    time_str = search.created_at

                text += f"\n   {time_str} • {search.result_count} results • {search.execution_time_ms:.0f}ms"

                # Create item
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, search)  # Store search record
                list_widget.addItem(item)

            # Handle item click
            def on_item_clicked(item):
                search = item.data(Qt.UserRole)

                # Restore search state
                if search.query_text:
                    self.search_input.setText(search.query_text)

                # TODO: Handle image query restoration
                # Would need to check if image still exists

                # Re-run search
                dialog.accept()
                self._on_search()

            list_widget.itemClicked.connect(on_item_clicked)
            layout.addWidget(list_widget)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.exec()
