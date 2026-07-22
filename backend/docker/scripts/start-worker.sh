#!/bin/bash
set -e

# Wait for database
bash /app/docker/scripts/wait-for-db.sh

# Start the Celery worker
# -A: the Celery app location
# --loglevel=info: see task execution logs
# --concurrency: number of worker processes (default: number of CPUs)
echo "Starting Celery worker..."
exec celery -A app.worker.celery:celery_app worker \
    --loglevel=info \
    --concurrency=2