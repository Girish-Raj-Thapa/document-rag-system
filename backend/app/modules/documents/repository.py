import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timezone
from .models import Document, DocumentStatus, DocumentChunk

class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, document: Document) -> Document:
        self.session.add(document)
        await self.session.flush()
        return document

    async def get_by_id(self, workspace_id: uuid.UUID, document_id: uuid.UUID) -> Optional[Document]:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_workspace(self, workspace_id: uuid.UUID, limit: int = 50, offset: int = 0) -> List[Document]:
        stmt = select(Document).where(
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None)
        ).order_by(Document.created_at.desc()).limit(limit).offset(offset)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete(self, document: Document) -> Document:
        document.status = DocumentStatus.deleted
        document.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
        return document
        
    async def update_status(self, document: Document, status: DocumentStatus, error_message: str = None) -> Document:
        document.status = status
        if error_message:
            document.error_message = error_message
        await self.session.flush()
        return document
