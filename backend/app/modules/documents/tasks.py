import os
import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone

from celery import shared_task
from celery.signals import worker_process_init
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.worker.celery import celery_app
from app.modules.documents.models import Document, DocumentStatus
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal

# Sub-modules
from app.modules.documents.extraction.factory import ExtractorFactory
from app.modules.documents.chunking.aggregator import SemanticAggregator
from app.modules.documents.enrichment.batch import AsyncBatchEnricher
from app.modules.documents.embedding import Embedder, warmup_embedding_model
from app.modules.documents.chunk_repository import ChunkRepository

logger = logging.getLogger(__name__)

@worker_process_init.connect
def on_worker_init(**kwargs):
    """
    Called when a Celery worker process is spun up.
    We use this to preload the embedding model into memory so the 
    first task doesn't suffer a massive download/initialization latency.
    """
    logger.info("Initializing Celery worker... Preloading models.")
    warmup_embedding_model()


async def _process_document_async(document_id: str):
    """
    The main asynchronous pipeline for document ingestion.
    """
    logger.info(f"Starting ingestion pipeline for document {document_id}")
    
    async with AsyncSessionLocal() as session:
        # 1. Fetch & Lock
        stmt = select(Document).where(Document.id == document_id)
        result = await session.execute(stmt)
        document = result.scalar_one_or_none()
        
        if not document:
            logger.error(f"Document {document_id} not found in database.")
            return
            
        if document.status not in (DocumentStatus.pending, DocumentStatus.uploaded, DocumentStatus.failed):
            logger.warning(f"Document {document_id} is in status {document.status}, skipping.")
            return

        # Update status to processing
        document.status = DocumentStatus.processing
        await session.commit()
        
        try:
            # 2. Extraction (Phase 7A)
            logger.info(f"[{document_id}] Starting extraction...")
            extractor = ExtractorFactory.get_extractor(document.original_filename)
            elements = await extractor.extract(document.storage_path, document.content_type)
            
            if not elements:
                raise ValueError("Extraction yielded zero elements. File might be empty or corrupted.")
            
            # 3. Chunking (Phase 7B)
            logger.info(f"[{document_id}] Starting chunking on {len(elements)} elements...")
            # We use a flat chunking strategy by default for Phase 7
            aggregator = SemanticAggregator(max_chunk_size=1000, overlap_size=100)
            raw_chunks = list(aggregator.process(elements))
            
            # 4. Enrichment (Phase 7C)
            logger.info(f"[{document_id}] Starting enrichment on {len(raw_chunks)} chunks...")
            # Settings could be injected here, but for now we default to what's configured in environment
            batch_enricher = AsyncBatchEnricher()
            enriched_chunks = await batch_enricher.process_batch(raw_chunks)
            
            # 5. Embedding (Phase 7D)
            logger.info(f"[{document_id}] Generating embeddings...")
            texts_to_embed = [
                chunk.contextualized_text if chunk.contextualized_text else chunk.raw_text 
                for chunk in enriched_chunks
            ]
            embedder = Embedder()
            embeddings = embedder.embed_texts(texts_to_embed)
            
            # 6. Storage (Phase 7D)
            logger.info(f"[{document_id}] Storing chunks to database...")
            chunk_repo = ChunkRepository(session)
            # In case this is a retry, wipe old chunks
            await chunk_repo.delete_by_document(document.id)
            
            inserted_count = await chunk_repo.batch_insert_chunks(
                workspace_id=document.workspace_id,
                document_id=document.id,
                chunks=enriched_chunks,
                embeddings=embeddings
            )
            
            # 7. Finalize
            logger.info(f"[{document_id}] Finalizing document...")
            document.status = DocumentStatus.processed
            document.chunk_count = inserted_count
            document.processed_at = datetime.now(timezone.utc)
            await session.commit()
            
            logger.info(f"Successfully processed document {document_id}")
            
        except Exception as e:
            logger.error(f"Pipeline failed for document {document_id}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Rollback any pending DB transactions from the failure
            await session.rollback()
            
            # Update document with failure state
            document.status = DocumentStatus.failed
            document.error_message = traceback.format_exc()
            await session.commit()
            raise  # Re-raise to trigger Celery retry


@celery_app.task(bind=True, name="documents.process_document_task", max_retries=3, default_retry_delay=60)
def process_document_task(self, document_id: str):
    """
    Celery task that triggers the ingestion pipeline.
    """
    try:
        asyncio.run(_process_document_async(document_id))
    except Exception as exc:
        logger.error(f"Task failed for document {document_id}, retrying...")
        raise self.retry(exc=exc)


async def _cleanup_orphaned_files_async(session=None):
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

    async def _do_work(sess):
        stmt = select(Document.storage_path).where(Document.deleted_at.is_(None))
        result = await sess.execute(stmt)
        return {row[0] for row in result.all()}

    if session:
        known_paths = await _do_work(session)
    else:
        async with AsyncSessionLocal() as sess:
            known_paths = await _do_work(sess)

    # Cleanup logic (synchronous file operations are fine here)
    if not os.path.exists(settings.STORAGE_PATH):
        return

    for workspace_dir in os.listdir(settings.STORAGE_PATH):
        docs_dir = os.path.join(settings.STORAGE_PATH, workspace_dir, "documents")
        if not os.path.isdir(docs_dir):
            continue
            
        for fname in os.listdir(docs_dir):
            full_path = os.path.join(docs_dir, fname)
            # Ensure we're checking a file
            if not os.path.isfile(full_path):
                continue
                
            file_mtime = datetime.fromtimestamp(os.path.getmtime(full_path), tz=timezone.utc)
            if full_path not in known_paths and file_mtime < cutoff:
                os.remove(full_path)


@celery_app.task(name="documents.cleanup_orphaned_files")
def cleanup_orphaned_files():
    """
    Runs periodically (e.g. every hour). Finds physical files on disk
    with no matching Document row (or only a stale 'pending' row older
    than a threshold), and deletes them.
    """
    asyncio.run(_cleanup_orphaned_files_async())
