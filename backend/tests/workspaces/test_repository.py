import pytest
from app.modules.workspaces.repository import WorkspaceRepository
from app.modules.workspaces.models import WorkspaceRole

pytestmark = pytest.mark.asyncio

async def test_create_workspace(db_session):
    repo = WorkspaceRepository(db_session)
    workspace = await repo.create_workspace(name="New Workspace")
    
    assert workspace.id is not None
    assert workspace.name == "New Workspace"

    fetched = await repo.get_by_id(workspace.id)
    assert fetched is not None
    assert fetched.id == workspace.id
    assert fetched.name == "New Workspace"

async def test_add_member(db_session, make_workspace, make_user):
    workspace, owner = await make_workspace()
    new_user = await make_user(email="newuser@example.com")
    
    repo = WorkspaceRepository(db_session)
    member = await repo.add_member(
        workspace_id=workspace.id,
        user_id=new_user.id,
        role=WorkspaceRole.ADMIN
    )
    
    assert member.id is not None
    assert member.workspace_id == workspace.id
    assert member.user_id == new_user.id
    assert member.role == WorkspaceRole.ADMIN

    # Verify retrieval
    fetched = await repo.get_member(workspace.id, new_user.id)
    assert fetched is not None
    assert fetched.user.email == "newuser@example.com"

async def test_list_for_user(db_session, make_workspace, make_user):
    user = await make_user()
    workspace1, _ = await make_workspace(owner=user, name="WS 1")
    workspace2, _ = await make_workspace(owner=user, name="WS 2")
    
    repo = WorkspaceRepository(db_session)
    workspaces = await repo.list_for_user(user.id)
    
    assert len(workspaces) == 2
    names = {w.name for w in workspaces}
    assert "WS 1" in names
    assert "WS 2" in names

async def test_list_members(db_session, make_workspace, make_user):
    workspace, owner = await make_workspace()
    user2 = await make_user(email="member2@example.com")
    user3 = await make_user(email="member3@example.com")
    
    repo = WorkspaceRepository(db_session)
    await repo.add_member(workspace.id, user2.id, WorkspaceRole.MEMBER)
    await repo.add_member(workspace.id, user3.id, WorkspaceRole.VIEWER)
    
    members = await repo.list_members(workspace.id)
    assert len(members) == 3
    roles = {m.role for m in members}
    assert roles == {WorkspaceRole.OWNER, WorkspaceRole.MEMBER, WorkspaceRole.VIEWER}

async def test_update_member_role(db_session, make_workspace, make_user):
    workspace, owner = await make_workspace()
    user = await make_user(email="member@example.com")
    
    repo = WorkspaceRepository(db_session)
    member = await repo.add_member(workspace.id, user.id, WorkspaceRole.MEMBER)
    
    updated = await repo.update_member_role(workspace.id, member.id, WorkspaceRole.ADMIN)
    assert updated.role == WorkspaceRole.ADMIN
    
    fetched = await repo.get_member_by_id(workspace.id, member.id)
    assert fetched.role == WorkspaceRole.ADMIN

async def test_remove_member(db_session, make_workspace, make_user):
    workspace, owner = await make_workspace()
    user = await make_user(email="member@example.com")
    
    repo = WorkspaceRepository(db_session)
    member = await repo.add_member(workspace.id, user.id, WorkspaceRole.MEMBER)
    
    assert len(await repo.list_members(workspace.id)) == 2
    
    success = await repo.remove_member(workspace.id, member.id)
    assert success is True
    
    assert len(await repo.list_members(workspace.id)) == 1
    assert await repo.get_member(workspace.id, user.id) is None

async def test_count_owners(db_session, make_workspace, make_user):
    workspace, owner = await make_workspace()
    user2 = await make_user(email="owner2@example.com")
    
    repo = WorkspaceRepository(db_session)
    assert await repo.count_owners(workspace.id) == 1
    
    await repo.add_member(workspace.id, user2.id, WorkspaceRole.OWNER)
    assert await repo.count_owners(workspace.id) == 2
