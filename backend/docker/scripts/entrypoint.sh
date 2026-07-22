#!/bin/bash
set -e

# Fix ownership of mounted volumes (they might be owned by root)
chown -R appuser:appuser /app/storage /app/logs 2>/dev/null || true

# Execute the CMD as appuser instead of root
# gosu is like sudo but designed for containers — it doesn't create a new
# process layer, so signals (SIGTERM for graceful shutdown) propagate correctly
exec gosu appuser "$@"