#!/bin/bash
# Execute this on the Hostinger VPS (Standby Node)
# SCRUM data-safety (2026-07-18): this script can wipe the standby data dir. It is now
# opt-in only — an accidental run will REFUSE unless NIDHI_ALLOW_STANDBY_WIPE=1 is set, and
# it will never wipe an unsafe path.

# Your Local Ubuntu Server's Public Static IP
PRIMARY_IP="100.83.65.7"
PRIMARY_PORT="5433" # Nidhi DB runs on 5433 mapped port
PG_DATA_DIR="./standby_nidhi_data"

if [ "${NIDHI_ALLOW_STANDBY_WIPE}" != "1" ]; then
  echo "REFUSING to wipe ${PG_DATA_DIR}: set NIDHI_ALLOW_STANDBY_WIPE=1 to proceed."
  exit 1
fi
if [ -z "${PG_DATA_DIR}" ] || [ "${PG_DATA_DIR}" = "/" ]; then
  echo "REFUSING: PG_DATA_DIR is unsafe ('${PG_DATA_DIR}')."
  exit 1
fi

echo "Wiping existing standby data (allowed by NIDHI_ALLOW_STANDBY_WIPE=1)..."
rm -rf "${PG_DATA_DIR:?}"/*

echo "Streaming base backup from Nidhi Primary..."
docker run --rm -v $(pwd)/${PG_DATA_DIR}:/var/lib/postgresql/data postgres:13 \
  bash -c "PGPASSWORD=StandbySecurePass123! pg_basebackup -h ${PRIMARY_IP} -p ${PRIMARY_PORT} -U replicator -D /var/lib/postgresql/data -Fp -Xs -P -R"

echo "Base backup complete. standby.signal has been dynamically generated!"
