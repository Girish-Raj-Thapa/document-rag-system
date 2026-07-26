from pydantic import BaseModel, Field


class RawChunk(BaseModel):
    """
    Represents a logically aggregated chunk of text before it is embedded and inserted into the DB.
    """
    raw_text: str = Field(..., description="The exact raw text of the chunk")
    contextualized_text: str = Field(..., description="The chunk text prepended with Title and Header context")
    metadata: dict = Field(default_factory=dict, description="Metadata such as page numbers and source element types")
