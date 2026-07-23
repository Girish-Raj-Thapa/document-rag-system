import uuid
from enum import Enum
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ENUM as pgEnum

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class WorkspaceRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String, nullable=False)

    # Relationships
    members = relationship(
        "WorkspaceMember", 
        back_populates="workspace", 
        cascade="all, delete-orphan"
    )


class WorkspaceMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[WorkspaceRole] = mapped_column(
        pgEnum(WorkspaceRole, name="workspace_role_enum", create_type=True),
        nullable=False,
        default=WorkspaceRole.MEMBER
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", lazy="joined")  # Eager load user details by default
