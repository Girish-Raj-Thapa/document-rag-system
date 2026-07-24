import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from .models import DocumentStatus


class DocumentBase(BaseModel):
    original_filename: str
    content_type: Optional[str] = None
    file_size_bytes: int
    status: DocumentStatus


class DocumentRead(DocumentBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    processed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentChunkRead(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    parent_chunk_id: Optional[uuid.UUID] = None
    raw_text: str
    metadata_payload: dict
    
    model_config = ConfigDict(from_attributes=True)
    