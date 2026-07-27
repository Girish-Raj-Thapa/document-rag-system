import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import DBAPIError

from app.modules.documents.models import Document, DocumentStatus
from app.modules.documents.tasks import _process_document_async, process_document_task
from app.modules.documents.enrichment.schemas import EnrichedChunk

@pytest.fixture
def mock_document():
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        uploaded_by_user_id=uuid.uuid4(),
        original_filename="test.pdf",
        stored_filename="test_stored.pdf",
        storage_path="/tmp/test_stored.pdf",
        content_type="application/pdf",
        file_size_bytes=1000,
        status=DocumentStatus.pending
    )
    return doc

@pytest.fixture
def dummy_enriched():
    return [
        EnrichedChunk(raw_text="chunk1", contextualized_text="ctx1", metadata={}),
        EnrichedChunk(raw_text="chunk2", contextualized_text="ctx2", metadata={})
    ]

@pytest.mark.asyncio
@patch("app.modules.documents.tasks.AsyncSessionLocal")
@patch("app.modules.documents.tasks.ExtractorFactory")
@patch("app.modules.documents.tasks.SemanticAggregator")
@patch("app.modules.documents.tasks.AsyncBatchEnricher")
@patch("app.modules.documents.tasks.Embedder")
@patch("app.modules.documents.tasks.ChunkRepository")
async def test_process_document_success(
    MockChunkRepo, MockEmbedder, MockEnricher, MockAggregator, MockExtractorFactory, MockSessionLocal, mock_document, dummy_enriched
):
    mock_session = AsyncMock()
    MockSessionLocal.return_value.__aenter__.return_value = mock_session
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_document
    mock_session.execute.return_value = mock_result
    
    mock_extractor = AsyncMock()
    mock_extractor.extract.return_value = ["element1", "element2"]
    MockExtractorFactory.get_extractor.return_value = mock_extractor
    
    MockAggregator.return_value.process.return_value = ["raw_chunk1", "raw_chunk2"]
    MockEnricher.return_value.process_batch.return_value = dummy_enriched
    MockEmbedder.return_value.embed_texts.return_value = [[0.1]*768, [0.2]*768]
    MockChunkRepo.return_value.batch_insert_chunks.return_value = 2
    
    await _process_document_async(str(mock_document.id))
    
    assert mock_document.status == DocumentStatus.processed
    assert mock_document.chunk_count == 2
    assert mock_document.processed_at is not None
    assert mock_session.commit.call_count == 2


@pytest.mark.asyncio
@patch("app.modules.documents.tasks.AsyncSessionLocal")
async def test_process_document_not_found(MockSessionLocal):
    # Edge Case: Document deleted or not found in DB before processing starts
    mock_session = AsyncMock()
    MockSessionLocal.return_value.__aenter__.return_value = mock_session
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    
    await _process_document_async(str(uuid.uuid4()))
    
    # Should exit early without raising or updating status
    mock_session.commit.assert_not_called()


@pytest.mark.asyncio
@patch("app.modules.documents.tasks.AsyncSessionLocal")
async def test_process_document_wrong_status(MockSessionLocal, mock_document):
    # Edge Case: Document is already PROCESSED or DELETED (skip processing)
    mock_document.status = DocumentStatus.processed
    
    mock_session = AsyncMock()
    MockSessionLocal.return_value.__aenter__.return_value = mock_session
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_document
    mock_session.execute.return_value = mock_result
    
    await _process_document_async(str(mock_document.id))
    
    mock_session.commit.assert_not_called()


@pytest.mark.asyncio
@patch("app.modules.documents.tasks.AsyncSessionLocal")
@patch("app.modules.documents.tasks.ExtractorFactory")
async def test_process_document_zero_elements(MockExtractorFactory, MockSessionLocal, mock_document):
    # Edge Case: Extraction succeeds but returns 0 elements (empty file)
    mock_session = AsyncMock()
    MockSessionLocal.return_value.__aenter__.return_value = mock_session
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_document
    mock_session.execute.return_value = mock_result
    
    mock_extractor = AsyncMock()
    mock_extractor.extract.return_value = []
    MockExtractorFactory.get_extractor.return_value = mock_extractor
    
    with pytest.raises(ValueError, match="Extraction yielded zero elements"):
        await _process_document_async(str(mock_document.id))
        
    assert mock_document.status == DocumentStatus.failed
    mock_session.rollback.assert_called_once()


@pytest.mark.asyncio
@patch("app.modules.documents.tasks.AsyncSessionLocal")
@patch("app.modules.documents.tasks.ExtractorFactory")
@patch("app.modules.documents.tasks.SemanticAggregator")
@patch("app.modules.documents.tasks.AsyncBatchEnricher")
@patch("app.modules.documents.tasks.Embedder")
@patch("app.modules.documents.tasks.ChunkRepository")
async def test_process_document_db_storage_failure(
    MockChunkRepo, MockEmbedder, MockEnricher, MockAggregator, MockExtractorFactory, MockSessionLocal, mock_document, dummy_enriched
):
    # Edge Case: Everything succeeds, but DB crashes during storage (e.g. connection drop)
    mock_session = AsyncMock()
    MockSessionLocal.return_value.__aenter__.return_value = mock_session
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_document
    mock_session.execute.return_value = mock_result
    
    mock_extractor = AsyncMock()
    mock_extractor.extract.return_value = ["element"]
    MockExtractorFactory.get_extractor.return_value = mock_extractor
    
    MockAggregator.return_value.process.return_value = ["chunk"]
    MockEnricher.return_value.process_batch.return_value = dummy_enriched
    MockEmbedder.return_value.embed_texts.return_value = [[0.1]*768, [0.2]*768]
    
    mock_chunk_repo_inst = AsyncMock()
    mock_chunk_repo_inst.batch_insert_chunks.side_effect = DBAPIError("connection lost", "params", "orig")
    MockChunkRepo.return_value = mock_chunk_repo_inst
    
    with pytest.raises(DBAPIError):
        await _process_document_async(str(mock_document.id))
        
    assert mock_document.status == DocumentStatus.failed
    assert "connection lost" in mock_document.error_message
    mock_session.rollback.assert_called_once()


@patch("app.modules.documents.tasks.asyncio.run")
def test_celery_task_retry_mechanism(mock_async_run):
    # Edge Case: Test the Celery wrapper itself to ensure `self.retry` is called
    mock_async_run.side_effect = Exception("Transient Network Error")
    
    # Mock the celery task instance `self`
    class MockCeleryTask:
        def retry(self, exc):
            return Exception("CeleryRetry")
            
    task_instance = MockCeleryTask()
    
    # Run the bounded celery task explicitly
    with pytest.raises(Exception, match="CeleryRetry"):
        process_document_task(task_instance, "dummy_id")
