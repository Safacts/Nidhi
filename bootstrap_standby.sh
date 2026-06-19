#!/bin/bash
# Execute this on the Hostinger VPS (Standby Node)

# Your Local Ubuntu Server's Public Static IP
PRIMARY_IP="100.83.65.7"
PRIMARY_PORT="5433" # Nidhi DB runs on 5433 mapped port
PG_DATA_DIR="./standby_nidhi_data"

echo "Wiping existing standby data..."
rm -rf ${PG_DATA_DIR}/*

echo "Streaming base backup from Nidhi Primary..."
docker run --rm -v $(pwd)/${PG_DATA_DIR}:/var/lib/postgresql/data postgres:13 \
  bash -c "PGPASSWORD=StandbySecurePass123! pg_basebackup -h ${PRIMARY_IP} -p ${PRIMARY_PORT} -U replicator -D /var/lib/postgresql/data -Fp -Xs -P -R"

echo "Base backup complete. standby.signal has been dynamically generated!"
