import pytest
import uuid
from app.modules.workspaces.models import WorkspaceRole
from app.modules.workspaces.repository import WorkspaceRepository

pytestmark = pytest.mark.asyncio

async def test_create_workspace(auth_client):
    response = await auth_client.post(
        "/api/v1/workspaces",
        json={"name": "API Workspace"}
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == "API Workspace"
    assert "id" in data

async def test_list_workspaces(auth_client, make_workspace, db_session):
    from app.modules.accounts.repository import UserRepository
    user_repo = UserRepository(db_session)
    user = await user_repo.get_by_id(auth_client.current_user_id)
    
    await make_workspace(owner=user, name="My WS 1")
    await make_workspace(owner=user, name="My WS 2")
    
    response = await auth_client.get("/api/v1/workspaces")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) >= 2
    names = [w["name"] for w in data]
    assert "My WS 1" in names
    assert "My WS 2" in names

async def test_get_workspace(auth_client, make_workspace, db_session):
    from app.modules.accounts.repository import UserRepository
    user_repo = UserRepository(db_session)
    user = await user_repo.get_by_id(auth_client.current_user_id)
    
    workspace, _ = await make_workspace(owner=user, name="Secret WS")
    
    response = await auth_client.get(f"/api/v1/workspaces/{workspace.id}")
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Secret WS"

async def test_get_workspace_no_access(auth_client, make_workspace):
    # Workspace owned by someone else
    workspace, _ = await make_workspace()
    
    response = await auth_client.get(f"/api/v1/workspaces/{workspace.id}")
    assert response.status_code == 403

async def test_list_workspace_members(auth_client, make_workspace, make_user, db_session):
    from app.modules.accounts.repository import UserRepository
    user_repo = UserRepository(db_session)
    user = await user_repo.get_by_id(auth_client.current_user_id)
    
    workspace, _ = await make_workspace(owner=user)
    new_user = await make_user(email="member@example.com")
    
    repo = WorkspaceRepository(db_session)
    await repo.add_member(workspace.id, new_user.id, WorkspaceRole.MEMBER)
    
    response = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/members")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 2

async def test_invite_member_success(auth_client, make_workspace, make_user, db_session):
    from app.modules.accounts.repository import UserRepository
    user_repo = UserRepository(db_session)
    user = await user_repo.get_by_id(auth_client.current_user_id)
    workspace, _ = await make_workspace(owner=user)
    
    # Needs to exist to be invited
    await make_user(email="newguy@example.com")
    
    response = await auth_client.post(
        f"/api/v1/workspaces/{workspace.id}/members",
        json={"email": "newguy@example.com", "role": "member"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == "newguy@example.com"
    assert data["role"] == "member"

async def test_invite_member_permission_denied(auth_client, make_workspace, make_user, db_session):
    workspace, _ = await make_workspace()
    
    from app.modules.accounts.repository import UserRepository
    user_repo = UserRepository(db_session)
    current_user = await user_repo.get_by_id(auth_client.current_user_id)
    
    # Add current_user as a MEMBER
    repo = WorkspaceRepository(db_session)
    await repo.add_member(workspace.id, current_user.id, WorkspaceRole.MEMBER)
    
    await make_user(email="newguy@example.com")
    
    # Try to invite as a MEMBER (not OWNER/ADMIN)
    response = await auth_client.post(
        f"/api/v1/workspaces/{workspace.id}/members",
        json={"email": "newguy@example.com", "role": "viewer"}
    )
    assert response.status_code == 403

async def test_update_member_role(auth_client, make_workspace, make_user, db_session):
    from app.modules.accounts.repository import UserRepository
    user_repo = UserRepository(db_session)
    user = await user_repo.get_by_id(auth_client.current_user_id)
    workspace, _ = await make_workspace(owner=user)
    
    new_user = await make_user(email="update_me@example.com")
    repo = WorkspaceRepository(db_session)
    member = await repo.add_member(workspace.id, new_user.id, WorkspaceRole.VIEWER)
    
    response = await auth_client.patch(
        f"/api/v1/workspaces/{workspace.id}/members/{member.id}",
        json={"role": "admin"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "admin"

async def test_remove_member(auth_client, make_workspace, make_user, db_session):
    from app.modules.accounts.repository import UserRepository
    user_repo = UserRepository(db_session)
    user = await user_repo.get_by_id(auth_client.current_user_id)
    workspace, _ = await make_workspace(owner=user)
    
    new_user = await make_user(email="remove_me@example.com")
    repo = WorkspaceRepository(db_session)
    member = await repo.add_member(workspace.id, new_user.id, WorkspaceRole.VIEWER)
    
    response = await auth_client.delete(
        f"/api/v1/workspaces/{workspace.id}/members/{member.id}"
    )
    assert response.status_code == 200
    
    # Verify removal
    response = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/members")
    assert len(response.json()["data"]) == 1
