import logging
from typing import List

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Singleton instance to avoid reloading the model in memory across multiple tasks in the same worker
_model_instance = None
_MODEL_NAME = "BAAI/bge-base-en-v1.5"

def get_embedding_model() -> SentenceTransformer:
    """
    Lazily loads and returns the SentenceTransformer model.
    If already loaded in the worker process, returns the cached instance.
    """
    global _model_instance
    if _model_instance is None:
        logger.info(f"Loading embedding model '{_MODEL_NAME}' into memory...")
        # Loads model to GPU if available, else CPU
        _model_instance = SentenceTransformer(_MODEL_NAME)
        logger.info("Embedding model loaded successfully.")
    return _model_instance

def warmup_embedding_model():
    """
    Called when the Celery worker initializes to pre-download 
    and pre-load the model into memory. This avoids latency on the first task.
    """
    get_embedding_model()

class Embedder:
    """
    Utility class for generating vector embeddings.
    """
    def __init__(self):
        self.model = get_embedding_model()
        
    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Embeds a list of strings into a list of float vectors (768 dimensions for bge-base-en-v1.5).
        
        Args:
            texts: List of strings to embed.
            batch_size: The batch size used for inference.
            
        Returns:
            List of 768-dimensional float vectors.
        """
        if not texts:
            return []
            
        logger.info(f"Generating embeddings for {len(texts)} chunks...")
        # normalize_embeddings=True is highly recommended for BAAI/bge models to use cosine similarity efficiently
        embeddings = self.model.encode(
            texts, 
            batch_size=batch_size, 
            normalize_embeddings=True, 
            show_progress_bar=False,
            convert_to_numpy=True
        )
        return embeddings.tolist()
