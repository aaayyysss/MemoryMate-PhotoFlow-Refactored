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

from services.embedding_service import get_embedding_service
from services.search_history_service import get_search_history_service
from repository.photo_repository import PhotoRepository
from logging_config import get_logger
from translation_manager import tr

logger = get_logger(__name__)


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

    def _on_text_changed(self, text: str):
        """Handle text change - can enable live search if desired."""
        # Disable live search for now (too expensive with embeddings)
        # User must press Enter or click Search button
        pass

    def _on_threshold_changed(self, value: int):
        """Handle similarity threshold slider change."""
        self._min_similarity = value / 100.0
        self.threshold_label.setText(f"Min: {value}%")
        logger.debug(f"[SemanticSearch] Similarity threshold changed to {self._min_similarity:.2f}")

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
                progress = QProgressDialog(
                    "Loading CLIP model...",
                    None,
                    0, 0,
                    self
                )
                progress.setWindowTitle("Loading AI Model")
                progress.setWindowModality(Qt.WindowModal)
                progress.show()

                try:
                    self.embedding_service.load_clip_model()
                    progress.close()
                except Exception as e:
                    progress.close()
                    QMessageBox.critical(
                        self,
                        "Model Loading Failed",
                        f"Failed to load CLIP model:\n{e}"
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
                # Show loading dialog
                progress = QProgressDialog(
                    "Loading CLIP model for first-time search...",
                    None,  # No cancel button
                    0, 0,  # Indeterminate
                    self
                )
                progress.setWindowTitle("Loading AI Model")
                progress.setWindowModality(Qt.WindowModal)
                progress.show()

                try:
                    self.embedding_service.load_clip_model()
                    progress.close()
                except Exception as e:
                    progress.close()
                    QMessageBox.critical(
                        self,
                        "Model Loading Failed",
                        f"Failed to load CLIP model:\n{e}\n\n"
                        "Check console for details."
                    )
                    self.errorOccurred.emit(str(e))
                    return

            # Extract query embedding (multi-modal support)
            query_embedding = None

            if has_text and has_image:
                # Multi-modal: combine text + image embeddings
                logger.info("[SemanticSearch] Extracting multi-modal query embedding (text + image)...")
                text_embedding = self.embedding_service.extract_text_embedding(query)
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
                query_embedding = self.embedding_service.extract_text_embedding(query)

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
                QMessageBox.information(
                    self,
                    "No Results",
                    f"No photos found matching your description (similarity ≥ {self._min_similarity:.0%}).\n\n"
                    "Try:\n"
                    "• Using different search terms\n"
                    "• Lowering the similarity threshold slider\n"
                    "• Making sure embeddings have been extracted\n"
                    "  (Scan → Extract Embeddings)"
                )
                self.status_label.setText(f"No results ≥{self._min_similarity:.0%}")
                self.status_label.setVisible(True)
                return

            # Extract photo IDs
            photo_ids = [photo_id for photo_id, score in results]

            logger.info(
                f"[SemanticSearch] Found {len(results)} results, "
                f"top score: {results[0][1]:.3f}"
            )

            # Update UI state
            self.clear_btn.setVisible(True)
            self.status_label.setText(
                f"Found {len(results)} matches ≥{self._min_similarity:.0%} "
                f"(top: {results[0][1]:.1%})"
            )
            self.status_label.setVisible(True)

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
