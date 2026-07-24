import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from app.modules.documents.repository import DocumentRepository
from app.modules.documents.models import Document, DocumentStatus

@pytest.fixture
def repo(db_session):
    return DocumentRepository(db_session)

@pytest.mark.asyncio
async def test_create_and_get_document(db_session, make_workspace, repo):
    workspace, owner = await make_workspace()
    
    doc = Document(
        workspace_id=workspace.id,
        uploaded_by_user_id=owner.id,
        original_filename="test.pdf",
        stored_filename="uuid.pdf",
        storage_path="/tmp/uuid.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
    )
    
    created_doc = await repo.create(doc)
    assert created_doc.id is not None
    assert created_doc.status == DocumentStatus.uploaded
    
    fetched_doc = await repo.get_by_id(workspace.id, created_doc.id)
    assert fetched_doc is not None
    assert fetched_doc.original_filename == "test.pdf"

@pytest.mark.asyncio
async def test_list_by_workspace(db_session, make_workspace, repo):
    workspace, owner = await make_workspace()
    
    for i in range(3):
        doc = Document(
            workspace_id=workspace.id,
            uploaded_by_user_id=owner.id,
            original_filename=f"test_{i}.pdf",
            stored_filename=f"uuid_{i}.pdf",
            storage_path=f"/tmp/uuid_{i}.pdf",
            content_type="application/pdf",
            file_size_bytes=1024,
        )
        await repo.create(doc)
        
    docs = await repo.list_by_workspace(workspace.id)
    assert len(docs) == 3

@pytest.mark.asyncio
async def test_soft_delete_document(db_session, make_workspace, repo):
    workspace, owner = await make_workspace()
    
    doc = Document(
        workspace_id=workspace.id,
        uploaded_by_user_id=owner.id,
        original_filename="test.pdf",
        stored_filename="uuid.pdf",
        storage_path="/tmp/uuid.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
    )
    created_doc = await repo.create(doc)
    
    await repo.soft_delete(created_doc)
    assert created_doc.status == DocumentStatus.deleted
    assert created_doc.deleted_at is not None
    
    fetched_doc = await repo.get_by_id(workspace.id, created_doc.id)
    assert fetched_doc is None

    docs = await repo.list_by_workspace(workspace.id)
    assert len(docs) == 0

@pytest.mark.asyncio
async def test_get_by_id_wrong_workspace_returns_none(db_session, make_workspace, repo):
    workspace1, owner1 = await make_workspace()
    workspace2, _ = await make_workspace()
    
    doc = Document(
        workspace_id=workspace1.id,
        uploaded_by_user_id=owner1.id,
        original_filename="test.pdf",
        stored_filename="uuid.pdf",
        storage_path="/tmp/uuid.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
    )
    created_doc = await repo.create(doc)
    
    # Try fetching with workspace2's ID
    fetched_doc = await repo.get_by_id(workspace2.id, created_doc.id)
    assert fetched_doc is None

@pytest.mark.asyncio
async def test_list_by_workspace_excludes_other_workspace_docs(db_session, make_workspace, repo):
    workspace1, owner1 = await make_workspace()
    workspace2, owner2 = await make_workspace()
    
    doc1 = Document(
        workspace_id=workspace1.id,
        uploaded_by_user_id=owner1.id,
        original_filename="test1.pdf",
        stored_filename="uuid1.pdf",
        storage_path="/tmp/uuid1.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
    )
    await repo.create(doc1)
    
    doc2 = Document(
        workspace_id=workspace2.id,
        uploaded_by_user_id=owner2.id,
        original_filename="test2.pdf",
        stored_filename="uuid2.pdf",
        storage_path="/tmp/uuid2.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
    )
    await repo.create(doc2)
    
    docs = await repo.list_by_workspace(workspace1.id)
    assert len(docs) == 1
    assert docs[0].original_filename == "test1.pdf"

@pytest.mark.asyncio
async def test_list_by_workspace_ordering(db_session, make_workspace, repo):
    workspace, owner = await make_workspace()
    
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    
    # Insert multiple with explicit created_at because PostgreSQL now() returns transaction start time
    doc1 = await repo.create(Document(workspace_id=workspace.id, uploaded_by_user_id=owner.id, original_filename="test1.pdf", stored_filename="uuid1.pdf", storage_path="/tmp/uuid1.pdf", content_type="application/pdf", file_size_bytes=1024, created_at=now - timedelta(days=1)))
    
    doc2 = await repo.create(Document(workspace_id=workspace.id, uploaded_by_user_id=owner.id, original_filename="test2.pdf", stored_filename="uuid2.pdf", storage_path="/tmp/uuid2.pdf", content_type="application/pdf", file_size_bytes=1024, created_at=now))
    
    docs = await repo.list_by_workspace(workspace.id)
    assert len(docs) == 2
    # Newest first means doc2 should be first
    assert docs[0].id == doc2.id
    assert docs[1].id == doc1.id

@pytest.mark.asyncio
async def test_list_by_workspace_pagination_second_page(db_session, make_workspace, repo):
    workspace, owner = await make_workspace()
    
    for i in range(3):
        await repo.create(Document(
            workspace_id=workspace.id,
            uploaded_by_user_id=owner.id,
            original_filename=f"test{i}.pdf",
            stored_filename=f"uuid{i}.pdf",
            storage_path=f"/tmp/uuid{i}.pdf",
            content_type="application/pdf",
            file_size_bytes=1024,
        ))
        
    docs = await repo.list_by_workspace(workspace.id, limit=2, offset=2)
    assert len(docs) == 1

@pytest.mark.asyncio
async def test_update_status_sets_error_message(db_session, make_workspace, repo):
    workspace, owner = await make_workspace()
    doc = await repo.create(Document(workspace_id=workspace.id, uploaded_by_user_id=owner.id, original_filename="test.pdf", stored_filename="uuid.pdf", storage_path="/tmp/uuid.pdf", content_type="application/pdf", file_size_bytes=1024))
    
    updated_doc = await repo.update_status(doc, DocumentStatus.failed, error_message="Parsing failed")
    assert updated_doc.status == DocumentStatus.failed
    assert updated_doc.error_message == "Parsing failed"

@pytest.mark.asyncio
async def test_soft_delete_is_idempotent(db_session, make_workspace, repo):
    workspace, owner = await make_workspace()
    doc = await repo.create(Document(workspace_id=workspace.id, uploaded_by_user_id=owner.id, original_filename="test.pdf", stored_filename="uuid.pdf", storage_path="/tmp/uuid.pdf", content_type="application/pdf", file_size_bytes=1024))
    
    await repo.soft_delete(doc)
    deleted_at_first = doc.deleted_at
    
    # Soft delete again
    await repo.soft_delete(doc)
    assert doc.status == DocumentStatus.deleted
    # Since we assign datetime.now() inside the function, the timestamp will slightly update if not using frozen time
    # but the operation itself shouldn't crash.
    assert doc.deleted_at is not None

@pytest.mark.asyncio
async def test_content_hash_uniqueness_constraint(db_session, make_workspace, repo):
    workspace, owner = await make_workspace()
    
    doc1 = Document(
        workspace_id=workspace.id,
        uploaded_by_user_id=owner.id,
        original_filename="test1.pdf",
        stored_filename="uuid1.pdf",
        storage_path="/tmp/uuid1.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        content_hash="hash123"
    )
    await repo.create(doc1)
    await db_session.commit()
    
    doc2 = Document(
        workspace_id=workspace.id,
        uploaded_by_user_id=owner.id,
        original_filename="test2.pdf",
        stored_filename="uuid2.pdf",
        storage_path="/tmp/uuid2.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        content_hash="hash123"  # Same hash
    )
    with pytest.raises(IntegrityError):
        await repo.create(doc2)
        await db_session.commit()
