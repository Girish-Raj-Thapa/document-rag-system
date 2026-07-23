import pytest
import uuid
from app.modules.workspaces.service import WorkspaceService
from app.modules.workspaces.schemas import WorkspaceCreate
from app.modules.workspaces.models import WorkspaceRole
from app.core.exceptions import ConflictError, NotFoundError

pytestmark = pytest.mark.asyncio

async def test_create_workspace(db_session, make_user):
    user = await make_user()
    service = WorkspaceService(db_session)
    
    workspace = await service.create_workspace(
        user=user, 
        payload=WorkspaceCreate(name="Service Workspace")
    )
    
    assert workspace.id is not None
    assert workspace.name == "Service Workspace"
    
    members = await service.list_workspace_members(workspace.id)
    assert len(members) == 1
    assert members[0].user_id == user.id
    assert members[0].role == WorkspaceRole.OWNER

async def test_invite_member(db_session, make_workspace, make_user):
    workspace, owner = await make_workspace()
    new_user = await make_user(email="invitee@example.com")
    
    service = WorkspaceService(db_session)
    member = await service.invite_member(
        workspace_id=workspace.id,
        email="invitee@example.com",
        role=WorkspaceRole.MEMBER
    )
    
    assert member.user_id == new_user.id
    assert member.role == WorkspaceRole.MEMBER

async def test_invite_member_not_found(db_session, make_workspace):
    workspace, owner = await make_workspace()
    
    service = WorkspaceService(db_session)
    with pytest.raises(NotFoundError, match="not found"):
        await service.invite_member(
            workspace_id=workspace.id,
            email="nonexistent@example.com",
            role=WorkspaceRole.MEMBER
        )

async def test_invite_member_already_exists(db_session, make_workspace):
    workspace, owner = await make_workspace()
    
    service = WorkspaceService(db_session)
    with pytest.raises(ConflictError, match="already a member"):
        await service.invite_member(
            workspace_id=workspace.id,
            email=owner.email,
            role=WorkspaceRole.MEMBER
        )

async def test_update_member_role_success(db_session, make_workspace, make_user):
    workspace, owner = await make_workspace()
    user = await make_user(email="user@example.com")
    
    service = WorkspaceService(db_session)
    member = await service.invite_member(workspace.id, user.email, WorkspaceRole.MEMBER)
    
    updated = await service.update_member_role(
        workspace_id=workspace.id,
        member_id=member.id,
        new_role=WorkspaceRole.ADMIN
    )
    assert updated.role == WorkspaceRole.ADMIN

async def test_update_member_role_last_owner_demotion(db_session, make_workspace):
    workspace, owner = await make_workspace()
    
    service = WorkspaceService(db_session)
    members = await service.list_workspace_members(workspace.id)
    owner_member = members[0]
    
    with pytest.raises(ConflictError, match="Cannot demote the last owner"):
        await service.update_member_role(
            workspace_id=workspace.id,
            member_id=owner_member.id,
            new_role=WorkspaceRole.ADMIN
        )

async def test_remove_member_success(db_session, make_workspace, make_user):
    workspace, owner = await make_workspace()
    user = await make_user(email="user@example.com")
    
    service = WorkspaceService(db_session)
    member = await service.invite_member(workspace.id, user.email, WorkspaceRole.MEMBER)
    
    await service.remove_member(workspace.id, member.id)
    
    members = await service.list_workspace_members(workspace.id)
    assert len(members) == 1

async def test_remove_last_owner(db_session, make_workspace):
    workspace, owner = await make_workspace()
    
    service = WorkspaceService(db_session)
    members = await service.list_workspace_members(workspace.id)
    owner_member = members[0]
    
    with pytest.raises(ConflictError, match="Cannot remove the last owner"):
        await service.remove_member(
            workspace_id=workspace.id,
            member_id=owner_member.id
        )

async def test_not_found_scenarios(db_session):
    service = WorkspaceService(db_session)
    fake_uuid = uuid.uuid4()
    
    with pytest.raises(NotFoundError):
        await service.get_workspace(fake_uuid)
        
    with pytest.raises(NotFoundError):
        await service.update_member_role(fake_uuid, fake_uuid, WorkspaceRole.ADMIN)
        
    with pytest.raises(NotFoundError):
        await service.remove_member(fake_uuid, fake_uuid)
