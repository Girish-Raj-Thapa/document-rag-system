from abc import ABC, abstractmethod
from typing import List

from .schemas import ExtractedElement


class BaseExtractor(ABC):
    """Abstract base class for all document extractors."""

    @abstractmethod
    async def extract(self, file_path: str, file_type: str) -> List[ExtractedElement]:
        """
        Extract structured elements from a document file.
        
        Args:
            file_path: Absolute path to the file on disk.
            file_type: File extension (e.g., '.pdf', '.txt').
            
        Returns:
            A list of ExtractedElement objects.
        """
        pass
