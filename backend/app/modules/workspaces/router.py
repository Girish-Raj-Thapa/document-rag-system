import uuid
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.responses import ApiResponse
from app.modules.accounts.models import User
from app.modules.accounts.dependencies import get_current_user
from app.modules.workspaces.models import WorkspaceMember, WorkspaceRole
from app.modules.workspaces.schemas import (
    WorkspaceCreate,
    WorkspaceRead,
    WorkspaceMemberRead,
    InviteMemberRequest,
    UpdateMemberRoleRequest,
    WorkspaceMemberResponse
)
from app.modules.workspaces.service import WorkspaceService
from app.modules.workspaces.dependencies import (
    require_workspace_membership,
    require_workspace_roles
)

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.post(
    "",
    response_model=ApiResponse[WorkspaceRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new workspace.
    """
    service = WorkspaceService(db)
    workspace = await service.create_workspace(user=current_user, payload=payload)
    return ApiResponse(
        message="Workspace created successfully",
        data=WorkspaceRead.model_validate(workspace),
    )


@router.get(
    "",
    response_model=ApiResponse[List[WorkspaceRead]],
)
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all workspaces the current user is a member of.
    """
    service = WorkspaceService(db)
    workspaces = await service.list_user_workspaces(user_id=current_user.id)
    return ApiResponse(
        message="Workspaces retrieved successfully",
        data=[WorkspaceRead.model_validate(w) for w in workspaces],
    )


@router.get(
    "/{workspace_id}",
    response_model=ApiResponse[WorkspaceRead],
)
async def get_workspace(
    workspace_id: uuid.UUID,
    member: WorkspaceMember = Depends(require_workspace_membership),
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific workspace.
    """
    service = WorkspaceService(db)
    workspace = await service.get_workspace(workspace_id)
    return ApiResponse(
        message="Workspace retrieved successfully",
        data=WorkspaceRead.model_validate(workspace),
    )


@router.get(
    "/{workspace_id}/members",
    response_model=ApiResponse[List[WorkspaceMemberResponse]],
)
async def list_workspace_members(
    workspace_id: uuid.UUID,
    member: WorkspaceMember = Depends(require_workspace_membership),
    db: AsyncSession = Depends(get_db)
):
    """
    List all members of a workspace.
    """
    service = WorkspaceService(db)
    members = await service.list_workspace_members(workspace_id)
    
    # Map to schema manually since we used a clean flat schema
    response_data = []
    for m in members:
        response_data.append(
            WorkspaceMemberResponse(
                id=m.id,
                workspace_id=m.workspace_id,
                user_id=m.user_id,
                role=m.role,
                email=m.user.email,
                full_name=m.user.full_name,
                created_at=m.created_at
            )
        )
        
    return ApiResponse(
        message="Workspace members retrieved successfully",
        data=response_data,
    )


@router.post(
    "/{workspace_id}/members",
    response_model=ApiResponse[WorkspaceMemberResponse],
)
async def invite_member(
    workspace_id: uuid.UUID,
    payload: InviteMemberRequest,
    member: WorkspaceMember = Depends(
        require_workspace_roles(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    Invite a user to the workspace (OWNER or ADMIN only).
    """
    service = WorkspaceService(db)
    new_member = await service.invite_member(
        workspace_id=workspace_id, email=payload.email, role=payload.role
    )
    
    # Must get full member with user joined
    from app.modules.workspaces.repository import WorkspaceRepository
    repo = WorkspaceRepository(db)
    full_member = await repo.get_member_by_id(workspace_id, new_member.id)
    
    return ApiResponse(
        message="Member invited successfully",
        data=WorkspaceMemberResponse(
            id=full_member.id,
            workspace_id=full_member.workspace_id,
            user_id=full_member.user_id,
            role=full_member.role,
            email=full_member.user.email,
            full_name=full_member.user.full_name,
            created_at=full_member.created_at
        ),
    )


@router.patch(
    "/{workspace_id}/members/{member_id}",
    response_model=ApiResponse[WorkspaceMemberResponse],
)
async def update_member_role(
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: UpdateMemberRoleRequest,
    member: WorkspaceMember = Depends(
        require_workspace_roles(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a member's role (OWNER or ADMIN only).
    """
    service = WorkspaceService(db)
    updated_member = await service.update_member_role(
        workspace_id=workspace_id, member_id=member_id, new_role=payload.role
    )
    
    from app.modules.workspaces.repository import WorkspaceRepository
    repo = WorkspaceRepository(db)
    full_member = await repo.get_member_by_id(workspace_id, updated_member.id)
    
    return ApiResponse(
        message="Member role updated successfully",
        data=WorkspaceMemberResponse(
            id=full_member.id,
            workspace_id=full_member.workspace_id,
            user_id=full_member.user_id,
            role=full_member.role,
            email=full_member.user.email,
            full_name=full_member.user.full_name,
            created_at=full_member.created_at
        ),
    )


@router.delete(
    "/{workspace_id}/members/{member_id}",
    response_model=ApiResponse[None],
)
async def remove_member(
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
    member: WorkspaceMember = Depends(
        require_workspace_roles(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove a member from the workspace (OWNER or ADMIN only).
    """
    service = WorkspaceService(db)
    await service.remove_member(workspace_id=workspace_id, member_id=member_id)
    return ApiResponse(
        message="Member removed successfully",
        data=None,
    )
