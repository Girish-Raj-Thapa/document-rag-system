import uuid
import os
from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.config import get_settings

from .models import Document
from .repository import DocumentRepository
from .storage import StorageProvider

class DocumentService:
    def __init__(self, session: AsyncSession, storage_provider: StorageProvider):
        self.session = session
        self.storage = storage_provider
        self.repo = DocumentRepository(session)

    async def upload_document(self, workspace_id: uuid.UUID, user_id: uuid.UUID, file: UploadFile) -> Document:
        settings = get_settings()
        MAX_UPLOAD_SIZE_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        if file.size and file.size > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f"File exceeds max size of {settings.MAX_UPLOAD_SIZE_MB}MB")

        if file.content_type not in settings.ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=415, detail=f"Unsupported content type: {file.content_type}")

        # Generate unique filename for storage
        file_ext = os.path.splitext(file.filename)[1]
        stored_filename = f"{uuid.uuid4().hex}{file_ext}"

        # Upload file via strategy
        storage_path = await self.storage.upload_file(str(workspace_id), stored_filename, file)

        try:
            # Create DB record
            doc = Document(
                workspace_id=workspace_id,
                uploaded_by_user_id=user_id,
                original_filename=file.filename,
                stored_filename=stored_filename,
                storage_path=storage_path,
                content_type=file.content_type,
                file_size_bytes=file.size or 0,
            )
            
            doc = await self.repo.create(doc)
            await self.session.commit()
            await self.session.refresh(doc)
        except Exception:
            # Best-effort immediate cleanup; Celery sweep is the real safety net
            if os.path.exists(storage_path):
                os.remove(storage_path)
            raise

        # TODO: Phase 7 - Dispatch Celery task
        # process_document_task.delay(str(doc.id))
        print(f"STUB: Dispatched celery task for document {doc.id}")

        return doc

    async def get_document(self, workspace_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        doc = await self.repo.get_by_id(workspace_id, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc

    async def list_documents(self, workspace_id: uuid.UUID, limit: int = 50, offset: int = 0) -> List[Document]:
        return await self.repo.list_by_workspace(workspace_id, limit, offset)

    async def delete_document(self, workspace_id: uuid.UUID, document_id: uuid.UUID) -> None:
        doc = await self.get_document(workspace_id, document_id)
        await self.repo.soft_delete(doc)
        
        await self.session.commit()

    async def get_document_file_path(self, workspace_id: uuid.UUID, document_id: uuid.UUID) -> str:
        doc = await self.get_document(workspace_id, document_id)
        path = self.storage.get_file_path(doc.storage_path)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Physical file not found on disk")
        return path
