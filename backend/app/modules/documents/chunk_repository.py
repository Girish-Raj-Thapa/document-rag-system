import hashlib
import json
import logging
import uuid
from typing import List

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import DocumentChunk
from app.modules.documents.enrichment.schemas import EnrichedChunk

logger = logging.getLogger(__name__)

class ChunkRepository:
    """
    Repository for managing DocumentChunk persistence, tailored for vector database operations.
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _generate_chunk_hash(document_id: uuid.UUID, text: str) -> str:
        """
        Generates a deterministic SHA-256 hash for a chunk based on the document and the text content.
        This provides idempotency during Celery task retries.
        """
        hash_input = f"{document_id}:{text}".encode('utf-8')
        return hashlib.sha256(hash_input).hexdigest()

    async def batch_insert_chunks(
        self, 
        workspace_id: uuid.UUID, 
        document_id: uuid.UUID, 
        chunks: List[EnrichedChunk], 
        embeddings: List[List[float]]
    ) -> int:
        """
        Batch inserts enriched chunks and their embeddings into the database.
        Uses PostgreSQL ON CONFLICT DO NOTHING to ensure idempotency.
        
        Args:
            workspace_id: The ID of the workspace.
            document_id: The ID of the document.
            chunks: List of EnrichedChunk objects containing text and metadata.
            embeddings: List of 768-dimensional float vectors corresponding to each chunk.
            
        Returns:
            The number of chunks processed.
        """
        if not chunks or len(chunks) != len(embeddings):
            raise ValueError("The number of chunks must match the number of embeddings.")

        logger.info(f"Preparing batch insert for {len(chunks)} chunks into document {document_id}")
        
        # Prepare list of dictionaries for bulk insert
        values = []
        for chunk, embedding in zip(chunks, embeddings):
            # Prefer contextualized_text for uniqueness, fallback to raw_text
            primary_text = chunk.contextualized_text if chunk.contextualized_text else chunk.raw_text
            content_hash = self._generate_chunk_hash(document_id, primary_text)
            
            values.append({
                "id": uuid.uuid4(),
                "workspace_id": workspace_id,
                "document_id": document_id,
                "content_hash": content_hash,
                "raw_text": chunk.raw_text,
                "contextualized_text": chunk.contextualized_text,
                "embedding": embedding,
                "metadata_payload": chunk.metadata,
                "embedding_model_version": "v1-bge-base-en-v1.5"
            })

        # We execute in batches of ~500 to prevent oversized SQL statements
        BATCH_SIZE = 500
        inserted_count = 0
        
        for i in range(0, len(values), BATCH_SIZE):
            batch = values[i:i + BATCH_SIZE]
            
            stmt = insert(DocumentChunk).values(batch)
            
            # If the exact same (document_id, content_hash) exists, do nothing.
            # This handles the case where a Celery worker dies mid-processing and restarts the task.
            stmt = stmt.on_conflict_do_nothing(
                index_elements=['document_id', 'content_hash']
            )
            
            result = await self.session.execute(stmt)
            # Rowcount isn't fully accurate with on_conflict_do_nothing in some drivers, 
            # but we track the attempted batch count for logging.
            inserted_count += len(batch)
            
        logger.info(f"Successfully executed batch insert for {inserted_count} chunks.")
        return inserted_count

    async def delete_by_document(self, document_id: uuid.UUID) -> None:
        """
        Deletes all chunks associated with a specific document.
        Useful for re-processing a document from scratch.
        """
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        await self.session.execute(stmt)
        logger.info(f"Deleted existing chunks for document {document_id}")
