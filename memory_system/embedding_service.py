import logging
import os
import asyncio
from typing import List, Dict, Any, Optional, Union
import numpy as np

# Import optional dependencies
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

logger = logging.getLogger(__name__)

class EmbeddingService:
    """
    Service for generating embeddings from text using various embedding models.
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize the embedding service.
        
        Args:
            model_name: Name of the embedding model to use
        """
        self.model_name = model_name
        self.model = None
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the embedding model"""
        try:
            if not HAS_SENTENCE_TRANSFORMERS:
                logger.warning("sentence-transformers not installed. Using fallback methods.")
                return
            
            logger.info(f"Initializing embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"Embedding model initialized successfully")
        
        except Exception as e:
            logger.error(f"Error initializing embedding model: {e}")
            # Fall back to a simple embedding method if model initialization fails
            self.model = None
    
    async def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text.
        
        Args:
            text: Text to generate embedding for
            
        Returns:
            Embedding vector as a list of floats
        """
        if not text:
            logger.warning("Received empty text for embedding")
            # Return a zero vector if text is empty
            return [0.0] * (384 if self.model_name == "all-MiniLM-L6-v2" else 512)
        
        try:
            if self.model is not None:
                # Run in executor to avoid blocking
                loop = asyncio.get_event_loop()
                embedding = await loop.run_in_executor(
                    None, 
                    lambda: self.model.encode(text, convert_to_numpy=True).tolist()
                )
                return embedding
            else:
                # Fallback to simple embedding if model is not available
                return self._fallback_embedding(text)
        
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            # Return fallback embedding on error
            return self._fallback_embedding(text)
    
    def _fallback_embedding(self, text: str) -> List[float]:
        """
        Generate a simple fallback embedding when the model is not available.
        This is a very simple hash-based approach for demo purposes only.
        
        Args:
            text: Text to generate embedding for
            
        Returns:
            Simple embedding vector
        """
        logger.warning("Using fallback embedding method")
        
        # Default dimension for the fallback embedding
        dim = 384 if self.model_name == "all-MiniLM-L6-v2" else 512
        
        # Generate a deterministic but very simple embedding
        np.random.seed(sum(ord(c) for c in text))
        embedding = np.random.normal(0, 0.1, dim).tolist()
        
        # Normalize the embedding
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = [x / norm for x in embedding]
        
        return embedding
    
    async def batch_get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to generate embeddings for
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        try:
            if self.model is not None:
                # Run in executor to avoid blocking
                loop = asyncio.get_event_loop()
                embeddings = await loop.run_in_executor(
                    None, 
                    lambda: self.model.encode(texts, convert_to_numpy=True).tolist()
                )
                return embeddings
            else:
                # Fall back to individual processing
                return [self._fallback_embedding(text) for text in texts]
        
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            # Fall back to individual processing on error
            return [self._fallback_embedding(text) for text in texts]