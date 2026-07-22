#!/bin/bash
set -e

# Wait for database
bash /app/docker/scripts/wait-for-db.sh

# Run database migrations
# This ensures the schema is always up-to-date when the container starts.
# In production, you might want to run this as a separate init container instead.
if [ -f "alembic.ini" ]; then
    echo "Running database migrations..."
    alembic upgrade head
    echo "Migrations complete."
fi

# Start the FastAPI server
# --reload: auto-restart on code changes (dev only — remove in production)
# --host 0.0.0.0: listen on all interfaces (required inside Docker)
echo "Starting FastAPI server..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload