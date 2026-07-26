from typing import List

from .schemas import RawChunk
from .aggregator import SemanticAggregator
from app.modules.documents.extraction.schemas import ExtractedElement


def build_chunks(elements: List[ExtractedElement], max_tokens: int = 500, overlap: float = 0.15) -> List[RawChunk]:
    """
    Orchestrates the chunking pipeline. Takes a list of structural ExtractedElements
    and produces a list of Semantic RawChunks ready for embedding.
    
    Args:
        elements: The extracted structural elements.
        max_tokens: The maximum token length for any chunk.
        overlap: The percentage of tokens to overlap when hard-splitting long text.
        
    Returns:
        List of RawChunk objects.
    """
    aggregator = SemanticAggregator(max_tokens=max_tokens, overlap=overlap)
    chunks = list(aggregator.process(elements))
    return chunks
