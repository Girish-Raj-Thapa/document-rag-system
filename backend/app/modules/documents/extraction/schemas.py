import logging
from enum import Enum
from typing import Any, List, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger("ingestion_pipeline")

class ElementType(str, Enum):
    TITLE = "Title"
    HEADER = "Header"
    NARRATIVE_TEXT = "NarrativeText"
    TABLE = "Table"
    LIST_ITEM = "ListItem"
    HEADER_FOOTER = "HeaderFooter"
    UNKNOWN = "Unknown"

    @classmethod
    def _missing_(cls, value: Any) -> "ElementType":
        """Fallback for unmapped unstructured element types."""
        logger.warning(f"Unmapped layout element string encountered: '{value}'. Forcing fallback to UNKNOWN.")
        return cls.UNKNOWN


class ElementMetadata(BaseModel):
    """Layout attributes for the extracted element."""
    text_as_html: Optional[str] = None
    coordinates: Optional[List[Tuple[float, float]]] = None
    file_name: Optional[str] = None


class ExtractedElement(BaseModel):
    """Standardized representation of a document element."""
    text: str = Field(..., min_length=1)
    element_type: ElementType
    page_number: Optional[int] = Field(None, ge=1)
    metadata: ElementMetadata = Field(default_factory=ElementMetadata)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
