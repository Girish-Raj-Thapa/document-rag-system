import uuid
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.modules.workspaces.models import Workspace, WorkspaceMember, WorkspaceRole
from app.modules.workspaces.repository import WorkspaceRepository
from app.modules.workspaces.schemas import WorkspaceCreate
from app.modules.accounts.models import User
from app.modules.accounts.repository import UserRepository


class WorkspaceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.workspace_repo = WorkspaceRepository(db)
        self.user_repo = UserRepository(db)

    async def create_workspace(self, user: User, payload: WorkspaceCreate) -> Workspace:
        """Create a new workspace and add the creator as the OWNER."""
        workspace = await self.workspace_repo.create_workspace(name=payload.name)
        await self.workspace_repo.add_member(
            workspace_id=workspace.id,
            user_id=user.id,
            role=WorkspaceRole.OWNER
        )
        await self.db.commit()
        return workspace

    async def get_workspace(self, workspace_id: uuid.UUID) -> Workspace:
        workspace = await self.workspace_repo.get_by_id(workspace_id)
        if not workspace:
            raise NotFoundError("Workspace not found")
        return workspace

    async def list_user_workspaces(self, user_id: uuid.UUID) -> Sequence[Workspace]:
        return await self.workspace_repo.list_for_user(user_id)

    async def list_workspace_members(self, workspace_id: uuid.UUID) -> Sequence[WorkspaceMember]:
        return await self.workspace_repo.list_members(workspace_id)

    async def invite_member(
        self, workspace_id: uuid.UUID, email: str, role: WorkspaceRole
    ) -> WorkspaceMember:
        """Invite a user to the workspace by email."""
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise NotFoundError(f"User with email {email} not found")

        try:
            member = await self.workspace_repo.add_member(
                workspace_id=workspace_id,
                user_id=user.id,
                role=role
            )
            await self.db.commit()
            return member
        except IntegrityError:
            await self.db.rollback()
            raise ConflictError("User is already a member of this workspace")

    async def update_member_role(
        self, workspace_id: uuid.UUID, member_id: uuid.UUID, new_role: WorkspaceRole
    ) -> WorkspaceMember:
        """Update a member's role, enforcing the OWNER invariant."""
        member = await self.workspace_repo.get_member_by_id(workspace_id, member_id)
        if not member:
            raise NotFoundError("Workspace member not found")

        if member.role == WorkspaceRole.OWNER and new_role != WorkspaceRole.OWNER:
            # Check if this is the last owner
            owner_count = await self.workspace_repo.count_owners(workspace_id)
            if owner_count <= 1:
                raise ConflictError("Cannot demote the last owner of a workspace")

        updated_member = await self.workspace_repo.update_member_role(
            workspace_id=workspace_id, member_id=member_id, new_role=new_role
        )
        if not updated_member:
            raise NotFoundError("Failed to update workspace member")
            
        await self.db.commit()
        return updated_member

    async def remove_member(
        self, workspace_id: uuid.UUID, member_id: uuid.UUID
    ) -> None:
        """Remove a member from the workspace, enforcing the OWNER invariant."""
        member = await self.workspace_repo.get_member_by_id(workspace_id, member_id)
        if not member:
            raise NotFoundError("Workspace member not found")

        if member.role == WorkspaceRole.OWNER:
            # Check if this is the last owner
            owner_count = await self.workspace_repo.count_owners(workspace_id)
            if owner_count <= 1:
                raise ConflictError("Cannot remove the last owner of a workspace")

        success = await self.workspace_repo.remove_member(
            workspace_id=workspace_id, member_id=member_id
        )
        if not success:
            raise NotFoundError("Failed to remove workspace member")

        await self.db.commit()
