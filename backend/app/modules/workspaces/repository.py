import uuid
from typing import Sequence
from sqlalchemy import select, and_, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.modules.workspaces.models import Workspace, WorkspaceMember, WorkspaceRole
from app.modules.accounts.models import User


class WorkspaceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_workspace(self, name: str) -> Workspace:
        """Create a new workspace."""
        workspace = Workspace(name=name)
        self.db.add(workspace)
        await self.db.flush()
        return workspace

    async def get_by_id(self, workspace_id: uuid.UUID) -> Workspace | None:
        """Get a workspace by ID."""
        return await self.db.get(Workspace, workspace_id)

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Workspace]:
        """List all workspaces a user belongs to."""
        stmt = (
            select(Workspace)
            .join(WorkspaceMember)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def add_member(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, role: WorkspaceRole
    ) -> WorkspaceMember:
        """Add a user to a workspace with a specific role."""
        member = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=user_id,
            role=role
        )
        self.db.add(member)
        await self.db.flush()
        return member

    async def get_member(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMember | None:
        """Get a specific member of a workspace."""
        stmt = select(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id
            )
        ).options(joinedload(WorkspaceMember.user))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_member_by_id(
        self, workspace_id: uuid.UUID, member_id: uuid.UUID
    ) -> WorkspaceMember | None:
        """Get a specific member of a workspace by their member ID."""
        stmt = select(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.id == member_id
            )
        ).options(joinedload(WorkspaceMember.user))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_members(self, workspace_id: uuid.UUID) -> Sequence[WorkspaceMember]:
        """List all members of a workspace."""
        stmt = (
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .options(joinedload(WorkspaceMember.user))
            .order_by(WorkspaceMember.created_at)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_member_role(
        self, workspace_id: uuid.UUID, member_id: uuid.UUID, new_role: WorkspaceRole
    ) -> WorkspaceMember | None:
        """Update a member's role."""
        stmt = (
            update(WorkspaceMember)
            .where(
                and_(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.id == member_id
                )
            )
            .values(role=new_role)
            .returning(WorkspaceMember)
        )
        result = await self.db.execute(stmt)
        updated_member = result.scalar_one_or_none()
        if updated_member:
            await self.db.flush()
        return updated_member

    async def remove_member(
        self, workspace_id: uuid.UUID, member_id: uuid.UUID
    ) -> bool:
        """Remove a member from a workspace."""
        stmt = delete(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.id == member_id
            )
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount > 0

    async def count_owners(self, workspace_id: uuid.UUID) -> int:
        """Count the number of owners in a workspace. Critical for the OWNER invariant."""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == WorkspaceRole.OWNER
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()
