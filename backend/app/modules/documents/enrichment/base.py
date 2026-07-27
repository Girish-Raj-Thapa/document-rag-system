from abc import ABC, abstractmethod
from typing import List
from .schemas import EnrichedMetadata

class BaseEnricher(ABC):
    """
    Abstract base class for LLM enrichment providers.
    """
    
    @abstractmethod
    async def enrich_chunk(self, text: str) -> EnrichedMetadata:
        """
        Takes raw text from a chunk and uses an LLM to generate summary and keywords.
        """
        pass
        
    @abstractmethod
    async def generate_global_summary(self, chunk_summaries: List[str]) -> str:
        """
        Takes all individual chunk summaries and uses an LLM to generate a single document-level global summary.
        """
        pass
