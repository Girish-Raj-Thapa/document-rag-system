import os
import asyncio
from datetime import datetime, timedelta, timezone
from celery import shared_task
from sqlalchemy import select
from app.worker.celery import celery_app
from app.modules.documents.models import Document, DocumentStatus
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal

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
