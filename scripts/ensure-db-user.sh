#!/bin/bash
# Ensure database user exists with correct password
# This is needed when database is already initialized but user might not exist or have wrong password

set -e

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Set default values if not provided
export MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD:-seerrbridge_root}
export DB_NAME=${DB_NAME:-seerrbridge}
export DB_USER=${DB_USER:-seerrbridge}
export DB_PASSWORD=${DB_PASSWORD:-seerrbridge}

# Ensure database user '${DB_USER}' exists with correct password...
log "Using root password from environment"

# Wait for MySQL to be ready (up to 60s)
# We try both local socket (no -h) and TCP (-h localhost) to be sure
for i in {1..60}; do
    if mysqladmin ping -u root -p"${MYSQL_ROOT_PASSWORD}" --silent 2>/dev/null || \
       mysqladmin ping -h localhost -u root -p"${MYSQL_ROOT_PASSWORD}" --silent 2>/dev/null; then
        log "MySQL is alive and reachable"
        break
    fi
    if [ $i -eq 60 ]; then
        log "ERROR: MySQL is not ready after 60s in ensure-db-user.sh"
        exit 1
    fi
    sleep 1
done

# Ensure database exists
log "Ensuring database '${DB_NAME}' exists..."
mysql -h localhost -u root -p"${MYSQL_ROOT_PASSWORD}" -e "CREATE DATABASE IF NOT EXISTS ${DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null || true

# Ensure user exists and has correct password
log "Ensuring user '${DB_USER}' exists and has permissions..."
# Use local socket for these commands to ensure they succeed
mysql -u root -p"${MYSQL_ROOT_PASSWORD}" <<EOF 2>/dev/null
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'127.0.0.1';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'%';
-- Also allow root from 127.0.0.1 for health checks
CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY '${MYSQL_ROOT_PASSWORD}';
ALTER USER 'root'@'127.0.0.1' IDENTIFIED BY '${MYSQL_ROOT_PASSWORD}';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
FLUSH PRIVILEGES;
EOF

log "Database user '${DB_USER}' verified/created successfully"

# Initialize database tables if they don't exist (using SQL script)
if [ -f "/docker-entrypoint-initdb.d/00-complete-init.sql" ]; then
    log "Ensuring database tables are initialized from SQL script..."
    # Check if tables exist by counting them
    TABLE_COUNT=$(mysql -h localhost -u root -p"${MYSQL_ROOT_PASSWORD}" -N -s -e "SELECT count(*) FROM information_schema.tables WHERE table_schema = '${DB_NAME}';" 2>/dev/null || echo "0")
    if [ "$TABLE_COUNT" -eq "0" ]; then
        log "Running database initialization SQL script..."
        mysql -h localhost -u root -p"${MYSQL_ROOT_PASSWORD}" "${DB_NAME}" < /docker-entrypoint-initdb.d/00-complete-init.sql 2>/dev/null || {
            log "Warning: Database tables initialization script had errors (this might be okay if tables partially exist)"
        }
        log "Database tables initialization completed"
    else
        log "Database tables already exist (count: ${TABLE_COUNT}), skipping SQL initialization"
    fi
else
    log "Note: SQL initialization script not found, tables will be created by backend on first run"
fi

