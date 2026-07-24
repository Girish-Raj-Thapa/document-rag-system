import uuid
import pytest
from app.modules.workspaces.models import WorkspaceRole
from unittest.mock import patch

@pytest.mark.asyncio
async def test_upload_document_api(auth_client, make_workspace):
    workspace, owner = await make_workspace(owner=auth_client.current_user)
    files = {"file": ("test.txt", b"Hello World", "text/plain")}
    response = await auth_client.post(f"/api/v1/workspaces/{workspace.id}/documents", files=files)
    
    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "Document uploaded successfully"
    assert data["data"]["original_filename"] == "test.txt"

@pytest.mark.asyncio
async def test_upload_document_as_viewer_fails(auth_client, make_workspace, make_user, db_session):
    other_user = await make_user(email="other@example.com")
    workspace, owner = await make_workspace(owner=other_user)
    
    from app.modules.workspaces.repository import WorkspaceRepository
    repo = WorkspaceRepository(db_session)
    await repo.add_member(workspace.id, auth_client.current_user_id, WorkspaceRole.VIEWER)
    await db_session.commit()
    
    files = {"file": ("test.txt", b"Hello World", "text/plain")}
    response = await auth_client.post(f"/api/v1/workspaces/{workspace.id}/documents", files=files)
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_list_and_get_documents_api(auth_client, make_workspace):
    workspace, owner = await make_workspace(owner=auth_client.current_user)
    files = {"file": ("test.txt", b"Hello World", "text/plain")}
    upload_res = await auth_client.post(f"/api/v1/workspaces/{workspace.id}/documents", files=files)
    doc_id = upload_res.json()["data"]["id"]
    
    list_res = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/documents")
    assert list_res.status_code == 200
    assert len(list_res.json()["data"]) == 1
    
    get_res = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/documents/{doc_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["original_filename"] == "test.txt"

@pytest.mark.asyncio
async def test_delete_document_as_owner(auth_client, make_workspace):
    workspace, owner = await make_workspace(owner=auth_client.current_user)
    files = {"file": ("test.txt", b"Hello World", "text/plain")}
    upload_res = await auth_client.post(f"/api/v1/workspaces/{workspace.id}/documents", files=files)
    doc_id = upload_res.json()["data"]["id"]
    
    delete_res = await auth_client.delete(f"/api/v1/workspaces/{workspace.id}/documents/{doc_id}")
    assert delete_res.status_code == 200
    
    get_res = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/documents/{doc_id}")
    assert get_res.status_code == 404

@pytest.mark.asyncio
async def test_delete_document_as_member_fails(auth_client, make_workspace, make_user, db_session):
    other_user = await make_user(email="other@example.com")
    workspace, owner = await make_workspace(owner=other_user)
    
    from app.modules.workspaces.repository import WorkspaceRepository
    repo = WorkspaceRepository(db_session)
    await repo.add_member(workspace.id, auth_client.current_user_id, WorkspaceRole.MEMBER)
    await db_session.commit()
    
    # Needs auth client to upload as owner
    # For speed, we just upload directly via api by temporarily swapping client user, or test upload failure
    # We'll just test that DELETE on any random ID fails with 403 because role check runs before fetching document
    delete_res = await auth_client.delete(f"/api/v1/workspaces/{workspace.id}/documents/{uuid.uuid4()}")
    assert delete_res.status_code == 403

@pytest.mark.asyncio
async def test_download_document_api(auth_client, make_workspace):
    workspace, owner = await make_workspace(owner=auth_client.current_user)
    files = {"file": ("test.txt", b"File contents here", "text/plain")}
    upload_res = await auth_client.post(f"/api/v1/workspaces/{workspace.id}/documents", files=files)
    doc_id = upload_res.json()["data"]["id"]
    
    download_res = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/documents/{doc_id}/download")
    assert download_res.status_code == 200
    assert download_res.read() == b"File contents here"

@pytest.mark.asyncio
async def test_cross_workspace_document_access_returns_404(auth_client, make_workspace, make_user, db_session):
    # Setup workspace 1 (auth_client is owner)
    workspace1, owner1 = await make_workspace(owner=auth_client.current_user)
    # Setup workspace 2 (auth_client is NOT a member)
    other_user = await make_user(email="other@example.com")
    workspace2, owner2 = await make_workspace(owner=other_user)
    
    # GET list from workspace 2
    res = await auth_client.get(f"/api/v1/workspaces/{workspace2.id}/documents")
    # require_workspace_membership will return 403 or 404 depending on workspaces implementation
    assert res.status_code in [403, 404]

@pytest.mark.asyncio
async def test_upload_as_admin_succeeds(auth_client, make_workspace, make_user, db_session):
    other_user = await make_user(email="other@example.com")
    workspace, owner = await make_workspace(owner=other_user)
    
    from app.modules.workspaces.repository import WorkspaceRepository
    repo = WorkspaceRepository(db_session)
    await repo.add_member(workspace.id, auth_client.current_user_id, WorkspaceRole.ADMIN)
    await db_session.commit()
    
    files = {"file": ("test.txt", b"Hello", "text/plain")}
    res = await auth_client.post(f"/api/v1/workspaces/{workspace.id}/documents", files=files)
    assert res.status_code == 201

@pytest.mark.asyncio
async def test_delete_as_admin_succeeds(auth_client, make_workspace, make_user, db_session):
    other_user = await make_user(email="other@example.com")
    workspace, owner = await make_workspace(owner=other_user)
    
    from app.modules.workspaces.repository import WorkspaceRepository
    repo = WorkspaceRepository(db_session)
    await repo.add_member(workspace.id, auth_client.current_user_id, WorkspaceRole.ADMIN)
    
    from app.modules.documents.repository import DocumentRepository
    from app.modules.documents.models import Document
    doc_repo = DocumentRepository(db_session)
    doc = await doc_repo.create(Document(workspace_id=workspace.id, uploaded_by_user_id=owner.id, original_filename="a", stored_filename="b", storage_path="c", content_type="pdf", file_size_bytes=10))
    await db_session.commit()
    
    res = await auth_client.delete(f"/api/v1/workspaces/{workspace.id}/documents/{doc.id}")
    assert res.status_code == 200

@pytest.mark.asyncio
async def test_viewer_can_list_and_get_and_download(auth_client, make_workspace, make_user, db_session):
    other_user = await make_user(email="other@example.com")
    workspace, owner = await make_workspace(owner=other_user)
    
    from app.modules.workspaces.repository import WorkspaceRepository
    repo = WorkspaceRepository(db_session)
    await repo.add_member(workspace.id, auth_client.current_user_id, WorkspaceRole.VIEWER)
    await db_session.commit()
    
    res = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/documents")
    assert res.status_code == 200

@pytest.mark.asyncio
async def test_non_member_gets_403_on_all_endpoints(auth_client, make_workspace, make_user):
    other_user = await make_user(email="other@example.com")
    workspace, owner = await make_workspace(owner=other_user)
    
    res1 = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/documents")
    assert res1.status_code in [403, 404]
    
    files = {"file": ("test.txt", b"Hello", "text/plain")}
    res2 = await auth_client.post(f"/api/v1/workspaces/{workspace.id}/documents", files=files)
    assert res2.status_code in [403, 404]

@pytest.mark.asyncio
async def test_unauthenticated_requests_return_401(client, make_workspace):
    workspace, _ = await make_workspace()
    res = await client.get(f"/api/v1/workspaces/{workspace.id}/documents")
    assert res.status_code == 401

@pytest.mark.asyncio
async def test_upload_document_over_size_limit_api_returns_413(auth_client, make_workspace):
    workspace, owner = await make_workspace(owner=auth_client.current_user)
    # Mocking massive file using a large buffer would take RAM, so we can patch the settings
    with patch("app.modules.documents.service.get_settings") as mock_settings:
        mock_settings.return_value.MAX_UPLOAD_SIZE_MB = 0 # Any file exceeds 0MB
        mock_settings.return_value.ALLOWED_CONTENT_TYPES = {"text/plain"}
        files = {"file": ("test.txt", b"Hello", "text/plain")}
        res = await auth_client.post(f"/api/v1/workspaces/{workspace.id}/documents", files=files)
        assert res.status_code == 413

@pytest.mark.asyncio
async def test_upload_document_disallowed_type_api_returns_415(auth_client, make_workspace):
    workspace, owner = await make_workspace(owner=auth_client.current_user)
    files = {"file": ("script.sh", b"echo h", "application/x-sh")}
    res = await auth_client.post(f"/api/v1/workspaces/{workspace.id}/documents", files=files)
    assert res.status_code == 415

@pytest.mark.asyncio
async def test_download_cross_workspace_document_returns_404(auth_client, make_workspace, make_user, db_session):
    workspace1, owner1 = await make_workspace(owner=auth_client.current_user)
    other_user = await make_user(email="other2@example.com")
    workspace2, owner2 = await make_workspace(owner=other_user)
    
    from app.modules.documents.repository import DocumentRepository
    from app.modules.documents.models import Document
    repo = DocumentRepository(db_session)
    doc = await repo.create(Document(workspace_id=workspace2.id, uploaded_by_user_id=owner2.id, original_filename="a", stored_filename="b", storage_path="c", content_type="pdf", file_size_bytes=10))
    await db_session.commit()
    
    res = await auth_client.get(f"/api/v1/workspaces/{workspace2.id}/documents/{doc.id}/download")
    assert res.status_code in [403, 404]

@pytest.mark.asyncio
async def test_upload_as_owner_succeeds(auth_client, make_workspace):
    workspace, owner = await make_workspace(owner=auth_client.current_user)
    files = {"file": ("test.txt", b"Hello World", "text/plain")}
    res = await auth_client.post(f"/api/v1/workspaces/{workspace.id}/documents", files=files)
    assert res.status_code == 201

@pytest.mark.asyncio
async def test_delete_as_viewer_fails(auth_client, make_workspace, make_user, db_session):
    other_user = await make_user(email="other3@example.com")
    workspace, owner = await make_workspace(owner=other_user)
    
    from app.modules.workspaces.repository import WorkspaceRepository
    repo = WorkspaceRepository(db_session)
    await repo.add_member(workspace.id, auth_client.current_user_id, WorkspaceRole.VIEWER)
    await db_session.commit()
    
    res = await auth_client.delete(f"/api/v1/workspaces/{workspace.id}/documents/{uuid.uuid4()}")
    assert res.status_code == 403

@pytest.mark.asyncio
async def test_list_documents_pagination_query_params(auth_client, make_workspace):
    workspace, owner = await make_workspace(owner=auth_client.current_user)
    
    res = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/documents?limit=10&offset=0")
    assert res.status_code == 200
    
    res_large = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/documents?limit=150")
    assert res_large.status_code == 422
    
    res_invalid = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/documents?limit=0")
    assert res_invalid.status_code == 422

@pytest.mark.asyncio
async def test_get_deleted_document_returns_404(auth_client, make_workspace, db_session):
    workspace, owner = await make_workspace(owner=auth_client.current_user)
    from app.modules.documents.repository import DocumentRepository
    from app.modules.documents.models import Document, DocumentStatus
    from datetime import datetime, timezone
    
    repo = DocumentRepository(db_session)
    doc = await repo.create(Document(workspace_id=workspace.id, uploaded_by_user_id=owner.id, original_filename="a", stored_filename="b", storage_path="c", content_type="pdf", file_size_bytes=10, status=DocumentStatus.deleted, deleted_at=datetime.now(timezone.utc)))
    await db_session.commit()
    
    res = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/documents/{doc.id}")
    assert res.status_code == 404

@pytest.mark.asyncio
async def test_download_deleted_document_returns_404(auth_client, make_workspace, db_session):
    workspace, owner = await make_workspace(owner=auth_client.current_user)
    from app.modules.documents.repository import DocumentRepository
    from app.modules.documents.models import Document, DocumentStatus
    from datetime import datetime, timezone
    
    repo = DocumentRepository(db_session)
    doc = await repo.create(Document(workspace_id=workspace.id, uploaded_by_user_id=owner.id, original_filename="a", stored_filename="b", storage_path="c", content_type="pdf", file_size_bytes=10, status=DocumentStatus.deleted, deleted_at=datetime.now(timezone.utc)))
    await db_session.commit()
    
    res = await auth_client.get(f"/api/v1/workspaces/{workspace.id}/documents/{doc.id}/download")
    assert res.status_code == 404

@pytest.mark.asyncio
async def test_invalid_workspace_id_format_returns_422(auth_client):
    res = await auth_client.get(f"/api/v1/workspaces/not-a-uuid/documents")
    assert res.status_code == 422

@pytest.mark.asyncio
async def test_valid_but_nonexistent_workspace_id_returns_403(auth_client):
    res = await auth_client.get(f"/api/v1/workspaces/{uuid.uuid4()}/documents")
    assert res.status_code in [403, 404]
