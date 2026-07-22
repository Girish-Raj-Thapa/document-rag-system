#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."

# Loop until PostgreSQL accepts connections
# nc (netcat) just checks if the TCP port is open
# We extract host and port from DATABASE_URL
DB_HOST="${DATABASE_URL##*@}"     # Remove everything before @
DB_HOST="${DB_HOST%%:*}"          # Remove everything after first :
DB_PORT="${DATABASE_URL##*:}"     # Get the port
DB_PORT="${DB_PORT%%/*}"          # Remove the database name

until nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; do
    echo "  PostgreSQL is not ready yet — sleeping 1s..."
    sleep 1
done

echo "PostgreSQL is ready!"