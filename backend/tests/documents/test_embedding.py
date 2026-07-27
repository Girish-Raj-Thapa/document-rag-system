import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from app.modules.documents.embedding import Embedder, get_embedding_model, warmup_embedding_model

def test_get_embedding_model_singleton():
    """
    Ensure the embedding model is loaded as a singleton.
    """
    with patch("app.modules.documents.embedding.SentenceTransformer") as MockTransformer:
        mock_instance = MagicMock()
        MockTransformer.return_value = mock_instance
        
        # Reset the global variable for tests
        import app.modules.documents.embedding as embedding_module
        embedding_module._model_instance = None
        
        # First call should instantiate
        model1 = get_embedding_model()
        assert model1 is mock_instance
        assert MockTransformer.call_count == 1
        
        # Second call should return cached instance
        model2 = get_embedding_model()
        assert model2 is mock_instance
        assert MockTransformer.call_count == 1

def test_warmup_embedding_model():
    """
    Ensure warmup calls get_embedding_model.
    """
    with patch("app.modules.documents.embedding.get_embedding_model") as mock_get:
        warmup_embedding_model()
        mock_get.assert_called_once()

def test_embedder_embed_texts():
    """
    Ensure Embedder calls model.encode with correct parameters and formats output.
    """
    with patch("app.modules.documents.embedding.get_embedding_model") as mock_get:
        mock_model = MagicMock()
        # Return a dummy numpy array to simulate embeddings
        dummy_embedding = np.array([[0.1] * 768, [0.2] * 768])
        mock_model.encode.return_value = dummy_embedding
        mock_get.return_value = mock_model
        
        embedder = Embedder()
        texts = ["hello", "world"]
        result = embedder.embed_texts(texts, batch_size=2)
        
        # Validate output format
        assert isinstance(result, list)
        assert len(result) == 2
        assert len(result[0]) == 768
        
        # Validate model.encode was called correctly
        mock_model.encode.assert_called_once_with(
            texts, 
            batch_size=2, 
            normalize_embeddings=True, 
            show_progress_bar=False,
            convert_to_numpy=True
        )

def test_embedder_empty_input():
    with patch("app.modules.documents.embedding.get_embedding_model"):
        embedder = Embedder()
        assert embedder.embed_texts([]) == []
