"""
RD-Agent embedding fallback: use sentence-transformers if Ollama/cloud fails.
This module provides a drop-in replacement for create_embedding calls.
"""
from typing import Any
from sentence_transformers import SentenceTransformer

_model = None

def get_model():
    """Lazy load and cache the embedding model."""
    global _model
    if _model is None:
        # Multilingual model works for Chinese + English
        _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _model

def create_embedding(texts: list[str] | str) -> list[list[float]]:
    """
    Create embeddings using local sentence-transformers.
    
    Args:
        texts: Single string or list of strings to embed.
        
    Returns:
        List of embedding vectors (each is list[float] with dimension 384).
    """
    if isinstance(texts, str):
        texts = [texts]
    
    model = get_model()
    embeddings = model.encode(texts, convert_to_tensor=False)
    return embeddings.tolist()
