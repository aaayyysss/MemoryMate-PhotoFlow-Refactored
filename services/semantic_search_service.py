# services/semantic_search_service.py
# Semantic search service using CLIP embeddings for photo content search
# Allows searching photos by natural language queries (e.g., "person with blue shirt", "sunset", "eyes")

from typing import List, Dict, Tuple, Optional
import numpy as np
from dataclasses import dataclass
import time
import os
from pathlib import Path

from logging_config import get_logger
from repository import PhotoRepository

logger = get_logger(__name__)


@dataclass
class SemanticSearchResult:
    """Result from semantic search."""
    path: str
    similarity: float
    photo_id: Optional[int] = None


class SemanticSearchService:
    """
    Semantic search service using CLIP embeddings.

    Features:
    - Extract CLIP embeddings from photos
    - Search photos by natural language queries
    - Query expansion for better matching
    - Configurable similarity thresholds
    - Model selection (base vs large CLIP)
    """

    def __init__(self, model_name: str = "large", device: Optional[str] = None):
        """
        Initialize semantic search service.

        Args:
            model_name: 'base' or 'large' (default: 'large' for better quality)
            device: 'cpu', 'cuda', or None for auto-detection
        """
        self.photo_repo = PhotoRepository()
        self.model = None
        self.processor = None
        self.device = device or self._auto_detect_device()
        self.model_name = model_name

        # Model configurations
        self.model_configs = {
            "base": {
                "name": "openai/clip-vit-base-patch32",
                "dimensions": 512,
                "quality": "Basic",
                "size_mb": 150,
            },
            "large": {
                "name": "openai/clip-vit-large-patch14",
                "dimensions": 768,
                "quality": "High (Recommended)",
                "size_mb": 890,
            }
        }

        # Query expansion patterns
        self.query_expansions = self._build_query_expansions()

        logger.info(f"SemanticSearchService initialized (model: {model_name}, device: {self.device})")

    def _auto_detect_device(self) -> str:
        """Auto-detect best available device (GPU if available, otherwise CPU)."""
        try:
            import torch
            if torch.cuda.is_available():
                logger.info("CUDA GPU detected, using GPU acceleration")
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                logger.info("Apple MPS detected, using Metal acceleration")
                return "mps"
        except Exception as e:
            logger.debug(f"Device detection failed: {e}")

        logger.info("Using CPU for CLIP inference")
        return "cpu"

    def _load_model(self):
        """Lazy-load CLIP model on first use."""
        if self.model is not None:
            return

        try:
            from transformers import CLIPModel, CLIPProcessor
            import torch

            model_config = self.model_configs[self.model_name]
            model_path = model_config["name"]

            logger.info(f"Loading CLIP model: {model_path} ({model_config['size_mb']}MB)")
            start_time = time.time()

            self.processor = CLIPProcessor.from_pretrained(model_path)
            self.model = CLIPModel.from_pretrained(model_path)
            self.model.to(self.device)
            self.model.eval()  # Set to evaluation mode

            load_time = time.time() - start_time
            logger.info(f"✅ CLIP model loaded successfully in {load_time:.2f}s")
            logger.info(f"   Quality: {model_config['quality']}, Dimensions: {model_config['dimensions']}-D")

        except ImportError as e:
            logger.error("CLIP dependencies not installed. Run: pip install torch transformers")
            raise RuntimeError("Missing dependencies: torch, transformers") from e
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            raise

    def _build_query_expansions(self) -> Dict[str, str]:
        """
        Build query expansion mappings for better CLIP matching.

        Simple queries like "eyes" are expanded to descriptive phrases like
        "close-up photo of person's eyes" for better CLIP matching.
        """
        return {
            # Body parts
            "eye": "close-up photo of person's eyes",
            "eyes": "close-up photo of person's eyes",
            "mouth": "photo of person's mouth and lips",
            "lips": "photo of person's lips",
            "nose": "photo of person's nose",
            "ear": "photo of person's ear",
            "ears": "photo of person's ears",
            "hair": "photo of person's hair and hairstyle",
            "face": "photo of person's face",
            "hand": "photo of person's hand or hands",
            "hands": "photo of person's hands",
            "finger": "photo of person's fingers or hand",
            "fingers": "photo of person's fingers",
            "arm": "photo of person's arm",
            "arms": "photo of person's arms",
            "leg": "photo of person's leg or legs",
            "feet": "photo of person's feet",
            "foot": "photo of person's foot",

            # Colors
            "red": "photo with red color or red object or person wearing red",
            "blue": "photo with blue color or blue object or person wearing blue",
            "green": "photo with green color or green object or person wearing green",
            "yellow": "photo with yellow color or yellow object or person wearing yellow",
            "orange": "photo with orange color or orange object or person wearing orange",
            "purple": "photo with purple color or purple object or person wearing purple",
            "pink": "photo with pink color or pink object or person wearing pink",
            "black": "photo with black color or black object or person wearing black",
            "white": "photo with white color or white object or person wearing white",
            "brown": "photo with brown color or brown object",
            "gray": "photo with gray color or gray object",
            "grey": "photo with grey color or grey object",

            # Common objects
            "car": "photo of a car or vehicle",
            "dog": "photo of a dog or puppy",
            "cat": "photo of a cat or kitten",
            "tree": "photo of a tree or trees",
            "flower": "photo of a flower or flowers",
            "building": "photo of a building or architecture",
            "sky": "photo of the sky or clouds",
            "water": "photo of water, ocean, lake, or river",
            "food": "photo of food or meal",
            "drink": "photo of a drink or beverage",

            # Activities
            "smile": "photo of person smiling or happy expression",
            "smiling": "photo of person smiling or happy",
            "laugh": "photo of person laughing or having fun",
            "laughing": "photo of person laughing",
            "sad": "photo of person with sad expression",
            "happy": "photo of happy person or joyful scene",
            "angry": "photo of person with angry expression",

            # Scenes
            "sunset": "photo of sunset or dusk with orange and red sky",
            "sunrise": "photo of sunrise or dawn",
            "beach": "photo of beach or ocean shore",
            "mountain": "photo of mountain or mountains",
            "forest": "photo of forest or woods with trees",
            "city": "photo of city or urban scene",
            "indoor": "photo taken indoors",
            "outdoor": "photo taken outdoors",
        }

    def expand_query(self, query: str) -> str:
        """
        Expand simple queries to descriptive phrases for better CLIP matching.

        Args:
            query: User's search query

        Returns:
            Expanded query (or original if no expansion found)
        """
        query_lower = query.lower().strip()

        # Check for exact match in expansions
        if query_lower in self.query_expansions:
            expanded = self.query_expansions[query_lower]
            logger.debug(f"Query expanded: '{query}' → '{expanded}'")
            return expanded

        # If query is a single word and not in expansions, prefix with "photo of"
        if len(query.split()) == 1 and query_lower not in self.query_expansions:
            expanded = f"photo of {query}"
            logger.debug(f"Query auto-expanded: '{query}' → '{expanded}'")
            return expanded

        # Return original query for multi-word queries
        return query

    def extract_image_embedding(self, image_path: str) -> Optional[np.ndarray]:
        """
        Extract CLIP embedding from an image.

        Args:
            image_path: Path to image file

        Returns:
            Numpy array of embedding (512-D or 768-D) or None if extraction fails
        """
        self._load_model()

        try:
            from PIL import Image
            import torch

            # Load and process image
            image = Image.open(image_path).convert("RGB")
            inputs = self.processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Extract embedding
            with torch.no_grad():
                image_features = self.model.get_image_features(**inputs)
                # Normalize embedding
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            # Convert to numpy
            embedding = image_features.cpu().numpy()[0]

            logger.debug(f"Extracted embedding for {os.path.basename(image_path)}: {embedding.shape}")
            return embedding

        except Exception as e:
            logger.error(f"Failed to extract embedding from {image_path}: {e}")
            return None

    def extract_text_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Extract CLIP embedding from text query.

        Args:
            text: Text query (will be auto-expanded if single word)

        Returns:
            Numpy array of embedding (512-D or 768-D) or None if extraction fails
        """
        self._load_model()

        try:
            import torch

            # Expand query for better matching
            expanded_text = self.expand_query(text)

            # Process text
            inputs = self.processor(text=[expanded_text], return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Extract embedding
            with torch.no_grad():
                text_features = self.model.get_text_features(**inputs)
                # Normalize embedding
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

            # Convert to numpy
            embedding = text_features.cpu().numpy()[0]

            logger.debug(f"Extracted text embedding for '{text}': {embedding.shape}")
            return embedding

        except Exception as e:
            logger.error(f"Failed to extract text embedding for '{text}': {e}")
            return None

    def cosine_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Similarity score (0.0 to 1.0, higher is more similar)
        """
        # Normalize embeddings
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        # Cosine similarity = dot product of normalized vectors
        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)

        # Clamp to [0, 1] range (can be slightly outside due to float precision)
        return float(np.clip(similarity, 0.0, 1.0))

    def search(self,
               query: str,
               threshold: float = 0.25,
               limit: int = 100,
               project_id: Optional[int] = None) -> List[SemanticSearchResult]:
        """
        Search photos by semantic query.

        Args:
            query: Natural language search query (e.g., "person with blue shirt")
            threshold: Minimum similarity score (0.0-1.0, default 0.25)
            limit: Maximum number of results
            project_id: Optional project ID filter

        Returns:
            List of SemanticSearchResult sorted by similarity (highest first)
        """
        start_time = time.time()

        logger.info(f"[SemanticSearch] Query: '{query}', Threshold: {threshold:.2f}, Limit: {limit}")

        # Extract text embedding from query
        query_embedding = self.extract_text_embedding(query)
        if query_embedding is None:
            logger.error("[SemanticSearch] Failed to extract query embedding")
            return []

        # Get all photos with embeddings from database
        where_clause = "embedding IS NOT NULL"
        params = []

        if project_id is not None:
            where_clause += " AND project_id = ?"
            params.append(project_id)

        photos = self.photo_repo.find_all(
            where_clause=where_clause,
            params=tuple(params) if params else None
        )

        if not photos:
            logger.warning("[SemanticSearch] No photos with embeddings found")
            return []

        logger.info(f"[SemanticSearch] Searching {len(photos)} photos with embeddings")

        # Calculate similarity for each photo
        results = []
        for photo in photos:
            try:
                # Deserialize embedding from database
                embedding_blob = photo.get('embedding')
                if not embedding_blob:
                    continue

                photo_embedding = np.frombuffer(embedding_blob, dtype=np.float32)

                # Calculate similarity
                similarity = self.cosine_similarity(query_embedding, photo_embedding)

                # Filter by threshold
                if similarity >= threshold:
                    results.append(SemanticSearchResult(
                        path=photo['path'],
                        similarity=similarity,
                        photo_id=photo.get('id')
                    ))
            except Exception as e:
                logger.debug(f"Skipping photo {photo.get('path')}: {e}")
                continue

        # Sort by similarity (highest first)
        results.sort(key=lambda x: x.similarity, reverse=True)

        # Apply limit
        results = results[:limit]

        search_time = time.time() - start_time

        logger.info(f"[SemanticSearch] Found {len(results)} results above {threshold:.2f} threshold")
        if results:
            logger.info(f"[SemanticSearch] Top score: {results[0].similarity:.3f}, "
                       f"Lowest score: {results[-1].similarity:.3f}")
        logger.info(f"[SemanticSearch] Search completed in {search_time:.2f}s")

        return results

    def get_score_distribution(self, query: str, project_id: Optional[int] = None) -> Dict[str, int]:
        """
        Get distribution of similarity scores for a query without applying threshold.
        Useful for suggesting optimal threshold values.

        Args:
            query: Search query
            project_id: Optional project filter

        Returns:
            Dictionary with score ranges and counts
        """
        # Search with very low threshold to get all scores
        results = self.search(query, threshold=0.0, limit=10000, project_id=project_id)

        if not results:
            return {}

        # Calculate distribution
        distribution = {
            "very_high_0.60+": 0,
            "high_0.40-0.60": 0,
            "medium_0.25-0.40": 0,
            "low_0.15-0.25": 0,
            "very_low_<0.15": 0
        }

        for result in results:
            score = result.similarity
            if score >= 0.60:
                distribution["very_high_0.60+"] += 1
            elif score >= 0.40:
                distribution["high_0.40-0.60"] += 1
            elif score >= 0.25:
                distribution["medium_0.25-0.40"] += 1
            elif score >= 0.15:
                distribution["low_0.15-0.25"] += 1
            else:
                distribution["very_low_<0.15"] += 1

        return distribution

    def suggest_threshold(self, query: str, project_id: Optional[int] = None) -> float:
        """
        Suggest optimal threshold based on score distribution.

        Args:
            query: Search query
            project_id: Optional project filter

        Returns:
            Suggested threshold value
        """
        distribution = self.get_score_distribution(query, project_id)

        if not distribution:
            return 0.25  # Default

        # If there are high-quality matches, use strict threshold
        if distribution.get("very_high_0.60+", 0) > 0:
            return 0.40
        elif distribution.get("high_0.40-0.60", 0) > 0:
            return 0.25
        elif distribution.get("medium_0.25-0.40", 0) > 0:
            return 0.15
        else:
            return 0.10
