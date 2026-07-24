import uuid
import os
import tempfile
import io
import pytest
from fastapi import UploadFile, HTTPException
from unittest.mock import patch, Mock

from app.modules.documents.service import DocumentService
from app.modules.documents.storage import LocalStorageProvider
from app.modules.documents.models import DocumentStatus

class MockUploadFile:
    def __init__(self, filename, content=b"fake data", content_type="application/pdf"):
        self.filename = filename
        self.content_type = content_type
        self.size = len(content)
        self.file = io.BytesIO(content)

@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmpdirname:
        with patch("app.modules.documents.storage.get_settings") as mock_settings:
            mock_settings.return_value.STORAGE_PATH = tmpdirname
            provider = LocalStorageProvider()
            yield provider

@pytest.mark.asyncio
async def test_upload_document_success(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    mock_file = MockUploadFile(filename="invoice.pdf")
    doc = await service.upload_document(workspace.id, owner.id, mock_file)
    
    assert doc.id is not None
    assert doc.original_filename == "invoice.pdf"
    assert doc.status == DocumentStatus.uploaded
    assert os.path.exists(doc.storage_path)

@pytest.mark.asyncio
async def test_upload_document_no_filename(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    mock_file = MockUploadFile(filename="")
    with pytest.raises(HTTPException) as excinfo:
        await service.upload_document(workspace.id, owner.id, mock_file)
        
    assert excinfo.value.status_code == 400
    assert "No filename provided" in excinfo.value.detail

@pytest.mark.asyncio
async def test_get_document_not_found(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    with pytest.raises(HTTPException) as excinfo:
        await service.get_document(workspace.id, uuid.uuid4())
        
    assert excinfo.value.status_code == 404

@pytest.mark.asyncio
async def test_get_document_file_path_missing_disk_file(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    mock_file = MockUploadFile(filename="missing.pdf")
    doc = await service.upload_document(workspace.id, owner.id, mock_file)
    
    os.remove(doc.storage_path)
    
    with pytest.raises(HTTPException) as excinfo:
        await service.get_document_file_path(workspace.id, doc.id)
        
    assert excinfo.value.status_code == 404
    assert "Physical file not found on disk" in excinfo.value.detail

@pytest.mark.asyncio
async def test_upload_document_generates_uuid_stored_filename(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    mock_file = MockUploadFile(filename="test.pdf")
    doc = await service.upload_document(workspace.id, owner.id, mock_file)
    
    assert doc.stored_filename != "test.pdf"
    assert doc.stored_filename.endswith(".pdf")
    assert len(doc.stored_filename) > 30

@pytest.mark.asyncio
async def test_upload_document_no_extension(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    mock_file = MockUploadFile(filename="testfile_without_ext", content_type="text/plain")
    doc = await service.upload_document(workspace.id, owner.id, mock_file)
    
    assert doc.original_filename == "testfile_without_ext"
    assert "." not in doc.stored_filename

@pytest.mark.asyncio
async def test_upload_document_exceeds_size_limit_returns_413(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    mock_file = MockUploadFile(filename="large.pdf")
    # Mocking a size larger than 25MB (25 * 1024 * 1024 = 26214400)
    mock_file.size = 26214401 
    
    with pytest.raises(HTTPException) as excinfo:
        await service.upload_document(workspace.id, owner.id, mock_file)
        
    assert excinfo.value.status_code == 413

@pytest.mark.asyncio
async def test_upload_document_at_exact_size_limit_succeeds(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    mock_file = MockUploadFile(filename="exact.pdf")
    mock_file.size = 26214400  # Exactly 25MB
    
    doc = await service.upload_document(workspace.id, owner.id, mock_file)
    assert doc.id is not None

@pytest.mark.asyncio
async def test_upload_document_rejects_disallowed_content_type_returns_415(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    mock_file = MockUploadFile(filename="script.sh", content_type="application/x-sh")
    
    with pytest.raises(HTTPException) as excinfo:
        await service.upload_document(workspace.id, owner.id, mock_file)
        
    assert excinfo.value.status_code == 415

@pytest.mark.asyncio
async def test_upload_document_zero_byte_file(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    mock_file = MockUploadFile(filename="empty.pdf", content=b"")
    doc = await service.upload_document(workspace.id, owner.id, mock_file)
    
    assert doc.file_size_bytes == 0

@pytest.mark.asyncio
async def test_upload_document_db_failure_triggers_inline_cleanup(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    mock_file = MockUploadFile(filename="test.pdf")
    
    # Mock the repository to throw an exception
    with patch.object(service.repo, 'create', side_effect=Exception("DB Failure")):
        with pytest.raises(Exception) as excinfo:
            await service.upload_document(workspace.id, owner.id, mock_file)
            
        assert str(excinfo.value) == "DB Failure"
        
    # How to assert file removed? We don't have the path since it failed, but we can check the tempdir
    workspace_dir = temp_storage._get_workspace_dir(workspace.id)
    assert len(os.listdir(workspace_dir)) == 0

@pytest.mark.asyncio
async def test_delete_document_leaves_file_on_disk(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    service = DocumentService(db_session, temp_storage)
    
    mock_file = MockUploadFile(filename="test.pdf")
    doc = await service.upload_document(workspace.id, owner.id, mock_file)
    
    assert os.path.exists(doc.storage_path)
    
    await service.delete_document(workspace.id, doc.id)
    
    # The file should still be on disk (soft delete doesn't remove physical files natively unless explicitly configured so)
    assert os.path.exists(doc.storage_path)
