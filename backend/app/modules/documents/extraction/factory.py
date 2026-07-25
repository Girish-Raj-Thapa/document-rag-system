from .base import BaseExtractor
from .unstructured_extractor import UnstructuredExtractor

class ExtractorFactory:
    """Factory to route file types to the appropriate extraction strategy."""
    
    @staticmethod
    def get_extractor(file_type: str) -> BaseExtractor:
        """
        Returns the appropriate extractor based on the file extension.
        
        Args:
            file_type: File extension, e.g., '.pdf', '.txt'.
            
        Returns:
            An instance of BaseExtractor.
            
        Raises:
            ValueError: If the file_type is unsupported.
        """
        ext = file_type.lower().strip()
        
        if ext in [".txt", ".md", ".csv"]:
            return UnstructuredExtractor(strategy="fast", infer_table_structure=False)
            
        elif ext in [".pdf", ".docx"]:
            return UnstructuredExtractor(strategy="hi_res", infer_table_structure=True)
            
        else:
            raise ValueError(f"Unsupported file type for extraction: '{ext}'")
