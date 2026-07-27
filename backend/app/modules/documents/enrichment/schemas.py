from pydantic import BaseModel, Field
from typing import List, Optional
from app.modules.documents.chunking.schemas import RawChunk

class EnrichedMetadata(BaseModel):
    summary: str = Field(..., description="A concise summary of the chunk's content.")
    keywords: List[str] = Field(..., description="Key topics or entities found in the chunk.")
    refined_category: Optional[str] = Field(None, description="Inferred category of the content.")

class EnrichedChunk(RawChunk):
    """
    Extends RawChunk with the output of the enrichment phase.
    The contextualized_text will be updated to include the global summary.
    The metadata dictionary will contain the EnrichedMetadata fields.
    """
    pass
