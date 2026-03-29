#!/bin/bash
# Generate a self-signed SSL certificate for PostgreSQL if one doesn't exist.
# Runs as a Docker entrypoint init script (mounted in /docker-entrypoint-initdb.d/).

DATADIR="${PGDATA:-/var/lib/postgresql/data}"

if [ ! -f "$DATADIR/server.crt" ]; then
    echo "Generating self-signed SSL certificate for PostgreSQL..."
    openssl req -new -x509 -days 3650 -nodes \
        -subj "/CN=tallied-postgres" \
        -keyout "$DATADIR/server.key" \
        -out "$DATADIR/server.crt" \
        > /dev/null 2>&1
    chmod 600 "$DATADIR/server.key"
    chown postgres:postgres "$DATADIR/server.key" "$DATADIR/server.crt"
    echo "SSL certificate generated."
else
    echo "SSL certificate already exists, skipping generation."
fi
