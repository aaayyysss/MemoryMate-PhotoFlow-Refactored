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
    QMessageBox, QProgressDialog
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon

from typing import Optional, List, Tuple
from services.embedding_service import get_embedding_service
from repository.photo_repository import PhotoRepository
from logging_config import get_logger
from translation_manager import tr

logger = get_logger(__name__)


class SemanticSearchWidget(QWidget):
    """
    Semantic search bar for natural language photo search.

    Emits signals when search is triggered with results.
    """

    # Signal: (photo_ids, query_text)
    searchTriggered = Signal(list, str)

    # Signal: () - emitted when search is cleared
    searchCleared = Signal()

    # Signal: (error_message)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.embedding_service = None
        self.photo_repo = PhotoRepository()
        self._last_query = ""
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

        # Search button
        self.search_btn = QPushButton("Semantic Search")
        self.search_btn.setToolTip("Search photos by description using AI")
        self.search_btn.clicked.connect(self._on_search)
        layout.addWidget(self.search_btn)

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

    def _on_search(self):
        """Trigger semantic search."""
        query = self.search_input.text().strip()

        if not query:
            self._on_clear()
            return

        if query == self._last_query:
            logger.info(f"[SemanticSearch] Same query, skipping: {query}")
            return

        logger.info(f"[SemanticSearch] Searching for: '{query}'")
        self._last_query = query

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

            # Extract query embedding
            logger.info("[SemanticSearch] Extracting query embedding...")
            query_embedding = self.embedding_service.extract_text_embedding(query)

            # Search for similar images
            logger.info("[SemanticSearch] Searching database...")
            results = self.embedding_service.search_similar(
                query_embedding,
                top_k=100,  # Get top 100 results
                model_id=self.embedding_service._clip_model_id
            )

            if not results:
                QMessageBox.information(
                    self,
                    "No Results",
                    "No photos found matching your description.\n\n"
                    "Make sure embeddings have been extracted for your photos.\n"
                    "(Scan → Extract Embeddings)"
                )
                self.status_label.setText("No results found")
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
                f"Found {len(results)} matches "
                f"(top similarity: {results[0][1]:.1%})"
            )
            self.status_label.setVisible(True)

            # Emit signal with results
            self.searchTriggered.emit(photo_ids, query)

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
