import uuid
from typing import List

from fastapi import APIRouter, Depends, UploadFile, File, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.responses import ApiResponse
from app.modules.accounts.models import User
from app.modules.accounts.dependencies import get_current_user
from app.modules.workspaces.dependencies import require_workspace_membership, require_workspace_roles
from app.modules.workspaces.models import WorkspaceMember, WorkspaceRole

from .schemas import DocumentRead
from .service import DocumentService
from .storage import StorageProvider, get_storage_provider

router = APIRouter()

def get_document_service(
    session: AsyncSession = Depends(get_db),
    storage: StorageProvider = Depends(get_storage_provider)
) -> DocumentService:
    return DocumentService(session, storage)


@router.post(
    "/{workspace_id}/documents",
    response_model=ApiResponse[DocumentRead],
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    member: WorkspaceMember = Depends(
        require_workspace_roles(WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER)
    ),
    user: User = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service)
):
    """
    Upload a new document to the workspace.
    """
    doc = await service.upload_document(workspace_id, user.id, file)
    return ApiResponse(
        message="Document uploaded successfully",
        data=DocumentRead.model_validate(doc)
    )


@router.get(
    "/{workspace_id}/documents",
    response_model=ApiResponse[List[DocumentRead]],
)
async def list_documents(
    workspace_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    member: WorkspaceMember = Depends(require_workspace_membership),
    service: DocumentService = Depends(get_document_service)
):
    """
    List all documents in the workspace.
    """
    docs = await service.list_documents(workspace_id, limit, offset)
    return ApiResponse(
        message="Documents retrieved successfully",
        data=[DocumentRead.model_validate(d) for d in docs]
    )


@router.get(
    "/{workspace_id}/documents/{document_id}",
    response_model=ApiResponse[DocumentRead],
)
async def get_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    member: WorkspaceMember = Depends(require_workspace_membership),
    service: DocumentService = Depends(get_document_service)
):
    """
    Get document metadata by ID.
    """
    doc = await service.get_document(workspace_id, document_id)
    return ApiResponse(
        message="Document retrieved successfully",
        data=DocumentRead.model_validate(doc)
    )


@router.delete(
    "/{workspace_id}/documents/{document_id}",
    response_model=ApiResponse[None],
)
async def delete_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    member: WorkspaceMember = Depends(
        require_workspace_roles(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
    ),
    service: DocumentService = Depends(get_document_service)
):
    """
    Soft delete a document (Owner/Admin only).
    """
    await service.delete_document(workspace_id, document_id)
    return ApiResponse(
        message="Document deleted successfully",
        data=None
    )


@router.get(
    "/{workspace_id}/documents/{document_id}/download"
)
async def download_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    member: WorkspaceMember = Depends(require_workspace_membership),
    service: DocumentService = Depends(get_document_service)
):
    """
    Securely download the document file.
    """
    file_path = await service.get_document_file_path(workspace_id, document_id)
    return FileResponse(path=file_path)