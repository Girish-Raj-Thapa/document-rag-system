import uuid
from typing import Callable, Sequence
from fastapi import Depends, Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.exceptions import PermissionDeniedError, NotFoundError
from app.modules.accounts.models import User
from app.modules.accounts.dependencies import get_current_user
from app.modules.workspaces.models import WorkspaceMember, WorkspaceRole
from app.modules.workspaces.repository import WorkspaceRepository


async def require_workspace_membership(
    workspace_id: uuid.UUID = Path(..., description="The ID of the workspace"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WorkspaceMember:
    """
    Validates that the current user belongs to the requested workspace.
    Returns the WorkspaceMember record.
    """
    repo = WorkspaceRepository(db)
    member = await repo.get_member(workspace_id=workspace_id, user_id=current_user.id)
    
    if not member:
        # Returning PermissionDenied or NotFound? 
        # Usually NotFound is better to not leak workspace existence, but 403 is also fine.
        raise PermissionDeniedError("You do not have access to this workspace")
        
    return member


def require_workspace_roles(*allowed_roles: WorkspaceRole) -> Callable:
    """
    Returns a FastAPI dependency that checks if the user's workspace role
    is in the allowed_roles list.
    """
    async def _check_role(
        member: WorkspaceMember = Depends(require_workspace_membership)
    ) -> WorkspaceMember:
        if member.role not in allowed_roles:
            allowed_roles_str = ", ".join([r.value for r in allowed_roles])
            raise PermissionDeniedError(
                f"You do not have the required role to perform this action. "
                f"Required one of: {allowed_roles_str}"
            )
        return member

    return _check_role
