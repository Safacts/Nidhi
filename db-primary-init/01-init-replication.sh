#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE replicator WITH REPLICATION PASSWORD 'StandbySecurePass123!' LOGIN;
EOSQL

# Docker Userland Proxy masks the source IP. UFW secures the traffic, so `all` is safe here.
echo "host replication replicator all md5" >> "$PGDATA/pg_hba.conf"
