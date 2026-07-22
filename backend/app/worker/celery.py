"""
Celery application configuration.

The worker process imports this:
    celery -A app.worker.celery:celery_app worker

Celery handles background tasks (document ingestion) in separate worker processes, so the FastAPI server stays responsive.
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "docrag",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# ── Celery Configuration ──
celery_app.conf.update(
    # Serialize task arguments as JSON (human-readable, debuggable)
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Don't lose tasks if a worker crashes mid-execution
    # The task will be redelivered to another worker
    task_acks_late=True,

    # Each worker only prefetches 1 task at a time
    # Prevents one slow task from blocking others
    worker_prefetch_multiplier=1,
)
