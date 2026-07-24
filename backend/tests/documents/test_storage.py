import os
import uuid
import tempfile
import io
import pytest
from unittest.mock import patch
from app.modules.documents.storage import LocalStorageProvider

class MockUploadFile:
    def __init__(self, filename, content=b"fake data"):
        self.filename = filename
        self.file = io.BytesIO(content)

@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmpdirname:
        with patch("app.modules.documents.storage.get_settings") as mock_settings:
            mock_settings.return_value.STORAGE_PATH = tmpdirname
            provider = LocalStorageProvider()
            yield provider

@pytest.mark.asyncio
async def test_local_storage_creates_workspace_dir(temp_storage):
    workspace_id = str(uuid.uuid4())
    mock_file = MockUploadFile(filename="test.pdf")
    
    await temp_storage.upload_file(workspace_id, "test.pdf", mock_file)
    
    workspace_dir = os.path.join(temp_storage.base_dir, workspace_id, "documents")
    assert os.path.isdir(workspace_dir)

@pytest.mark.asyncio
async def test_local_storage_upload_file_writes_correct_content(temp_storage):
    workspace_id = str(uuid.uuid4())
    mock_file = MockUploadFile(filename="test.pdf", content=b"hello storage")
    
    path = await temp_storage.upload_file(workspace_id, "file1.pdf", mock_file)
    
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == b"hello storage"

@pytest.mark.asyncio
async def test_local_storage_isolates_workspaces(temp_storage):
    workspace1 = str(uuid.uuid4())
    workspace2 = str(uuid.uuid4())
    
    await temp_storage.upload_file(workspace1, "file1.pdf", MockUploadFile("file1.pdf"))
    await temp_storage.upload_file(workspace2, "file2.pdf", MockUploadFile("file2.pdf"))
    
    w1_dir = os.path.join(temp_storage.base_dir, workspace1, "documents")
    w2_dir = os.path.join(temp_storage.base_dir, workspace2, "documents")
    
    assert "file1.pdf" in os.listdir(w1_dir)
    assert "file2.pdf" not in os.listdir(w1_dir)
    
    assert "file2.pdf" in os.listdir(w2_dir)
    assert "file1.pdf" not in os.listdir(w2_dir)
