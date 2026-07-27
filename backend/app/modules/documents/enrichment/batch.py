import asyncio
import logging
from typing import List
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from app.modules.documents.chunking.schemas import RawChunk
from app.modules.documents.enrichment.schemas import EnrichedChunk, EnrichedMetadata
from app.modules.documents.enrichment.factory import EnricherFactory

logger = logging.getLogger(__name__)

class AsyncBatchEnricher:
    """
    Orchestrates the Map-Reduce enrichment pipeline.
    """
    def __init__(self, provider_name: str = None, max_concurrency: int = 5):
        self.enricher = EnricherFactory.get_enricher(provider_name)
        self.semaphore = asyncio.Semaphore(max_concurrency)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def _enrich_single_chunk(self, chunk: RawChunk) -> EnrichedMetadata:
        async with self.semaphore:
            return await self.enricher.enrich_chunk(chunk.raw_text)

    async def _safe_enrich_single_chunk(self, chunk: RawChunk) -> EnrichedMetadata:
        try:
            return await self._enrich_single_chunk(chunk)
        except Exception as e:
            logger.warning(f"Failed to enrich chunk after retries. Error: {str(e)}")
            return EnrichedMetadata(
                summary="Enrichment failed.",
                keywords=[],
                refined_category=None
            )

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def _generate_global_summary(self, summaries: List[str]) -> str:
        if not summaries:
            return ""
        return await self.enricher.generate_global_summary(summaries)

    async def _safe_generate_global_summary(self, summaries: List[str]) -> str:
        valid_summaries = [s for s in summaries if s and s != "Enrichment failed."]
        if not valid_summaries:
            return "No valid summaries were generated."
            
        try:
            return await self._generate_global_summary(valid_summaries)
        except Exception as e:
            logger.warning(f"Failed to generate global summary after retries. Error: {str(e)}")
            return "Global summary generation failed."

    async def process_batch(self, chunks: List[RawChunk]) -> List[EnrichedChunk]:
        """
        Map-Reduce flow:
        1. Map: Enrich all chunks concurrently.
        2. Reduce: Generate global summary from chunk summaries.
        3. Finalize: Prepend global summary to each chunk's contextualized_text.
        """
        if not chunks:
            return []

        # Map Phase
        logger.info(f"Starting map phase for {len(chunks)} chunks.")
        enrichment_tasks = [self._safe_enrich_single_chunk(chunk) for chunk in chunks]
        metadata_results = await asyncio.gather(*enrichment_tasks)

        # Reduce Phase
        logger.info("Starting reduce phase (global summary generation).")
        chunk_summaries = [meta.summary for meta in metadata_results]
        global_summary = await self._safe_generate_global_summary(chunk_summaries)
        logger.info(f"Generated global summary: {global_summary[:100]}...")

        # Finalize
        enriched_chunks = []
        for chunk, meta in zip(chunks, metadata_results):
            # Prepend global summary to the existing contextualized text
            final_context = f"Global Document Context: {global_summary}\n\nSection Context: {chunk.contextualized_text}"
            
            # Combine existing metadata with new enriched metadata
            final_metadata = dict(chunk.metadata)
            final_metadata.update(meta.model_dump())
            
            enriched_chunks.append(
                EnrichedChunk(
                    raw_text=chunk.raw_text,
                    contextualized_text=final_context,
                    metadata=final_metadata
                )
            )
            
        return enriched_chunks
