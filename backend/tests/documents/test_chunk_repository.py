import pytest
import uuid
from unittest.mock import AsyncMock

from app.modules.documents.chunk_repository import ChunkRepository
from app.modules.documents.enrichment.schemas import EnrichedChunk

@pytest.fixture
def chunk_repo():
    mock_session = AsyncMock()
    return ChunkRepository(session=mock_session)

@pytest.fixture
def dummy_chunks():
    return [
        EnrichedChunk(
            raw_text="Chunk 1 text",
            contextualized_text="Global > Chunk 1 text",
            metadata={"source": "test"}
        ),
        EnrichedChunk(
            raw_text="Chunk 2 text",
            contextualized_text=None,  # Fallback to raw_text
            metadata={"source": "test"}
        )
    ]

@pytest.fixture
def dummy_embeddings():
    return [[0.1] * 768, [0.2] * 768]

@pytest.mark.asyncio
async def test_batch_insert_chunks(chunk_repo, dummy_chunks, dummy_embeddings):
    workspace_id = uuid.uuid4()
    document_id = uuid.uuid4()
    
    inserted = await chunk_repo.batch_insert_chunks(
        workspace_id=workspace_id,
        document_id=document_id,
        chunks=dummy_chunks,
        embeddings=dummy_embeddings
    )
    
    assert inserted == 2
    chunk_repo.session.execute.assert_called_once()
    
    stmt_str = str(chunk_repo.session.execute.call_args[0][0])
    assert "ON CONFLICT" in stmt_str
    assert "DO NOTHING" in stmt_str

@pytest.mark.asyncio
async def test_batch_insert_large_batch(chunk_repo):
    # Edge case: Bulk inserting more than BATCH_SIZE (500)
    # This ensures the internal loop handles pagination properly
    workspace_id = uuid.uuid4()
    document_id = uuid.uuid4()
    
    large_chunks = [
        EnrichedChunk(raw_text=f"Chunk {i}", metadata={}) for i in range(1005)
    ]
    large_embeddings = [[0.1] * 768] * 1005
    
    inserted = await chunk_repo.batch_insert_chunks(
        workspace_id=workspace_id,
        document_id=document_id,
        chunks=large_chunks,
        embeddings=large_embeddings
    )
    
    assert inserted == 1005
    # Since batch size is 500, we expect 3 loop iterations (500, 500, 5)
    assert chunk_repo.session.execute.call_count == 3


@pytest.mark.asyncio
async def test_batch_insert_mismatch(chunk_repo, dummy_chunks):
    # Edge Case: Validation of matching lengths
    with pytest.raises(ValueError, match="must match the number of embeddings"):
        await chunk_repo.batch_insert_chunks(
            workspace_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunks=dummy_chunks,
            embeddings=[[0.1]*768] # Only 1 embedding for 2 chunks
        )

@pytest.mark.asyncio
async def test_batch_insert_empty(chunk_repo):
    # Edge Case: Empty list handling
    with pytest.raises(ValueError, match="must match the number of embeddings"):
        await chunk_repo.batch_insert_chunks(
            workspace_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunks=[],
            embeddings=[]
        )

@pytest.mark.asyncio
async def test_delete_by_document(chunk_repo):
    document_id = uuid.uuid4()
    await chunk_repo.delete_by_document(document_id)
    chunk_repo.session.execute.assert_called_once()
    
    stmt_str = str(chunk_repo.session.execute.call_args[0][0])
    assert "DELETE FROM document_chunks" in stmt_str
