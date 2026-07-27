import pytest
from unittest.mock import AsyncMock, patch
from app.modules.documents.chunking.schemas import RawChunk
from app.modules.documents.enrichment.batch import AsyncBatchEnricher
from app.modules.documents.enrichment.schemas import EnrichedMetadata

@pytest.mark.asyncio
async def test_batch_enricher():
    chunks = [
        RawChunk(raw_text="This is the first section.", contextualized_text="Title > Section 1\n\nThis is the first section.", metadata={}),
        RawChunk(raw_text="This is the second section.", contextualized_text="Title > Section 2\n\nThis is the second section.", metadata={})
    ]
    
    mock_enricher = AsyncMock()
    mock_enricher.enrich_chunk.side_effect = [
        EnrichedMetadata(summary="Summary 1", keywords=["first"], refined_category="test"),
        EnrichedMetadata(summary="Summary 2", keywords=["second"], refined_category="test")
    ]
    mock_enricher.generate_global_summary.return_value = "Global Test Summary"
    
    with patch("app.modules.documents.enrichment.batch.EnricherFactory.get_enricher", return_value=mock_enricher):
        batch_enricher = AsyncBatchEnricher(provider_name="mock")
        enriched_chunks = await batch_enricher.process_batch(chunks)
        
        assert len(enriched_chunks) == 2
        assert mock_enricher.enrich_chunk.call_count == 2
        assert mock_enricher.generate_global_summary.call_count == 1
        
        # Verify the context format
        assert "Global Document Context: Global Test Summary" in enriched_chunks[0].contextualized_text
        assert "Section Context: Title > Section 1" in enriched_chunks[0].contextualized_text
        
        # Verify metadata merging
        assert enriched_chunks[0].metadata["summary"] == "Summary 1"
        assert enriched_chunks[0].metadata["keywords"] == ["first"]
