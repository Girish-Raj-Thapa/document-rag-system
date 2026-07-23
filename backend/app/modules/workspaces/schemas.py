import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, EmailStr

from app.modules.workspaces.models import WorkspaceRole


class WorkspaceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class WorkspaceCreate(WorkspaceBase):
    pass


class WorkspaceRead(WorkspaceBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceMemberRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: WorkspaceRole
    created_at: datetime
    updated_at: datetime

    # Include nested user details
    user_email: str = Field(alias="email", default="")
    user_full_name: str = Field(alias="full_name", default="")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @classmethod
    def from_orm(cls, obj):
        # Handle the joined 'user' relationship manually if needed for Pydantic v2
        # Actually in Pydantic V2 from_attributes handles it better if we define it right, 
        # but a simple way is to pass the data manually or use aliases.
        pass

# A cleaner way to represent member with user details in Pydantic v2
class WorkspaceMemberResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: WorkspaceRole
    email: str
    full_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.MEMBER


class UpdateMemberRoleRequest(BaseModel):
    role: WorkspaceRole
