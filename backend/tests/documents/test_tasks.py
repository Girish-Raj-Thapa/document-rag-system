import os
import uuid
import tempfile
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from app.modules.documents.tasks import _cleanup_orphaned_files_async
from app.modules.documents.models import Document
from app.core.config import get_settings

@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmpdirname:
        with patch("app.modules.documents.tasks.get_settings") as mock_settings:
            mock_settings.return_value.STORAGE_PATH = tmpdirname
            yield tmpdirname

def create_mock_file(base_dir, workspace_id, filename, age_hours):
    workspace_dir = os.path.join(base_dir, workspace_id, "documents")
    os.makedirs(workspace_dir, exist_ok=True)
    file_path = os.path.join(workspace_dir, filename)
    
    with open(file_path, "wb") as f:
        f.write(b"data")
        
    # Set mtime to past
    past_time = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).timestamp()
    os.utime(file_path, (past_time, past_time))
    
    return file_path

@pytest.mark.asyncio
async def test_cleanup_orphaned_files_removes_untracked_old_file(db_session, temp_storage):
    # Untracked file (no DB row), > 1hr old
    workspace_id = str(uuid.uuid4())
    path = create_mock_file(temp_storage, workspace_id, "old_orphan.pdf", age_hours=2)
    
    assert os.path.exists(path)
    await _cleanup_orphaned_files_async(session=db_session)
    assert not os.path.exists(path)

@pytest.mark.asyncio
async def test_cleanup_orphaned_files_preserves_recent_untracked_file(db_session, temp_storage):
    # Untracked file, < 1hr old (protects in-flight uploads)
    workspace_id = str(uuid.uuid4())
    path = create_mock_file(temp_storage, workspace_id, "recent_orphan.pdf", age_hours=0.5)
    
    assert os.path.exists(path)
    await _cleanup_orphaned_files_async(session=db_session)
    assert os.path.exists(path)

@pytest.mark.asyncio
async def test_cleanup_orphaned_files_preserves_tracked_file(db_session, make_workspace, temp_storage):
    workspace, owner = await make_workspace()
    
    path = create_mock_file(temp_storage, str(workspace.id), "tracked.pdf", age_hours=2)
    
    from app.modules.documents.repository import DocumentRepository
    repo = DocumentRepository(db_session)
    await repo.create(Document(
        workspace_id=workspace.id,
        uploaded_by_user_id=owner.id,
        original_filename="tracked.pdf",
        stored_filename="tracked.pdf",
        storage_path=path,
        content_type="application/pdf",
        file_size_bytes=4,
    ))
    await db_session.commit()
    
    assert os.path.exists(path)
    await _cleanup_orphaned_files_async(session=db_session)
    
    # Still exists because it's in the DB
    assert os.path.exists(path)

@pytest.mark.asyncio
async def test_cleanup_orphaned_files_handles_empty_workspace_dir(db_session, temp_storage):
    workspace_id = str(uuid.uuid4())
    os.makedirs(os.path.join(temp_storage, workspace_id, "documents"))
    
    # Should not crash
    await _cleanup_orphaned_files_async(session=db_session)
