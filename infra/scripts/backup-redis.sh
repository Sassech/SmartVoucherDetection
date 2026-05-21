#!/usr/bin/env bash
# infra/scripts/backup-redis.sh
#
# Backup the SmartVoucherDetection Redis dataset (RDB snapshot).
# Usage:
#   bash ~/SmartVoucherDetection/infra/scripts/backup-redis.sh
#
# Make executable: chmod +x ~/SmartVoucherDetection/infra/scripts/backup-redis.sh
#
# Optional env vars:
#   BACKUP_DIR        — local backup directory (default: ~/backups/redis)
#   REDIS_CONTAINER   — Docker container name for Redis (default: redis)
#
# Cron example (runs daily at 02:30, after the DB backup):
#   30 2 * * * /bin/bash ~/SmartVoucherDetection/infra/scripts/backup-redis.sh >> ~/logs/backup-redis.log 2>&1
#
# Idempotent: filenames are dated to the day; a second run on the same day
# overwrites the previous file (only one RDB per day is kept).

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BACKUP_DIR="${BACKUP_DIR:-${HOME}/backups/redis}"
REDIS_CONTAINER="${REDIS_CONTAINER:-redis}"
MAX_WAIT=30   # seconds to wait for BGSAVE to complete

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ts()  { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*"; }

# ---------------------------------------------------------------------------
# Prepare backup directory
# ---------------------------------------------------------------------------
mkdir -p "${BACKUP_DIR}"

DEST="${BACKUP_DIR}/$(date +%Y-%m-%d).rdb"

# ---------------------------------------------------------------------------
# Trigger background save and wait for completion
# ---------------------------------------------------------------------------
log "Triggering BGSAVE on container '${REDIS_CONTAINER}'..."

LASTSAVE_BEFORE=$(docker exec "${REDIS_CONTAINER}" redis-cli LASTSAVE)
docker exec "${REDIS_CONTAINER}" redis-cli BGSAVE > /dev/null

log "Waiting for BGSAVE to complete (max ${MAX_WAIT}s)..."
elapsed=0
while true; do
    sleep 2
    elapsed=$((elapsed + 2))
    LASTSAVE_NOW=$(docker exec "${REDIS_CONTAINER}" redis-cli LASTSAVE)
    if [[ "${LASTSAVE_NOW}" != "${LASTSAVE_BEFORE}" ]]; then
        log "BGSAVE completed (LASTSAVE changed: ${LASTSAVE_BEFORE} → ${LASTSAVE_NOW})"
        break
    fi
    if [[ "${elapsed}" -ge "${MAX_WAIT}" ]]; then
        echo "[$(ts)] ERROR: BGSAVE did not complete within ${MAX_WAIT}s." >&2
        exit 1
    fi
    log "  Still waiting... (${elapsed}s elapsed)"
done

# ---------------------------------------------------------------------------
# Copy RDB file out of container
# ---------------------------------------------------------------------------
log "Copying dump.rdb → ${DEST}"
docker cp "${REDIS_CONTAINER}:/data/dump.rdb" "${DEST}"

SIZE=$(du -sh "${DEST}" | cut -f1)
log "Backup complete: ${DEST} (${SIZE})"

# ---------------------------------------------------------------------------
# Retention: keep 7 days locally
# ---------------------------------------------------------------------------
log "Removing local backups older than 7 days..."
find "${BACKUP_DIR}" -name "*.rdb" -mtime +7 -delete
log "Retention cleanup done."
