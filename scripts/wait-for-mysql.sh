#!/bin/bash
# Wait for MySQL to be ready before starting other services

DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-3306}
DB_USER=${DB_USER:-seerrbridge}
DB_PASSWORD=${DB_PASSWORD:-seerrbridge}
DB_NAME=${DB_NAME:-seerrbridge}
MAX_WAIT=${MAX_WAIT:-120}
WAITED=0

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Waiting for MySQL to be ready..."

# Skip if SQLite is used
if [ "$DB_TYPE" = "sqlite" ]; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Using SQLite, skipping MySQL wait"
    exit 0
fi

while [ $WAITED -lt $MAX_WAIT ]; do
    # Try multiple ways to connect:
    # 1. Local socket (most reliable for root inside container)
    # 2. TCP localhost
    # 3. TCP 127.0.0.1
    if mysqladmin ping -u root -p"${MYSQL_ROOT_PASSWORD}" --silent 2>/dev/null || \
       mysqladmin ping -h localhost -P "$DB_PORT" -u root -p"${MYSQL_ROOT_PASSWORD}" --silent 2>/dev/null || \
       mysqladmin ping -h 127.0.0.1 -P "$DB_PORT" -u root -p"${MYSQL_ROOT_PASSWORD}" --silent 2>/dev/null || \
       mysqladmin ping -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" --silent 2>/dev/null; then
        echo "[$(date +'%Y-%m-%d %H:%M:%S')] MySQL is ready!"
        exit 0
    fi
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] MySQL not ready yet, waiting 2 seconds... (waited ${WAITED}/${MAX_WAIT}s)"
    sleep 2
    WAITED=$((WAITED + 2))
done

echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: MySQL did not become ready within ${MAX_WAIT} seconds"
exit 1

