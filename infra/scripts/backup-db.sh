#!/usr/bin/env bash
# infra/scripts/backup-db.sh
#
# Backup the SmartVoucherDetection PostgreSQL database.
# Usage:
#   bash ~/SmartVoucherDetection/infra/scripts/backup-db.sh
#
# Make executable: chmod +x ~/SmartVoucherDetection/infra/scripts/backup-db.sh
#
# Required env vars:
#   POSTGRES_USER      — database user
#   POSTGRES_PASSWORD  — database password (used by pg_dump via PGPASSWORD)
#   POSTGRES_DB        — database name
#
# Optional env vars:
#   BACKUP_DIR         — local backup directory (default: ~/backups/db)
#   RCLONE_REMOTE      — rclone remote name (e.g. "s3"); if unset, upload is skipped
#   RCLONE_BUCKET      — bucket/path on the remote (default: smartvoucher-backups)
#
# Cron example (runs daily at 02:00):
#   0 2 * * * /bin/bash ~/SmartVoucherDetection/infra/scripts/backup-db.sh >> ~/logs/backup-db.log 2>&1
#
# Idempotent: filenames are timestamped to the minute; a second run in the
# same minute produces a second file rather than overwriting the first.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"

BACKUP_DIR="${BACKUP_DIR:-${HOME}/backups/db}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
RCLONE_BUCKET="${RCLONE_BUCKET:-smartvoucher-backups}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ts()  { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*"; }

# ---------------------------------------------------------------------------
# Prepare backup directory
# ---------------------------------------------------------------------------
mkdir -p "${BACKUP_DIR}"

FILENAME="${BACKUP_DIR}/$(date +%Y-%m-%d_%H-%M).sql.gz"

# ---------------------------------------------------------------------------
# Dump
# ---------------------------------------------------------------------------
log "Starting database backup → ${FILENAME}"

PGPASSWORD="${POSTGRES_PASSWORD}" \
    docker exec postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
    | gzip > "${FILENAME}"

SIZE=$(du -sh "${FILENAME}" | cut -f1)
log "Backup complete: ${FILENAME} (${SIZE})"

# ---------------------------------------------------------------------------
# Upload to remote (optional)
# ---------------------------------------------------------------------------
if [[ -n "${RCLONE_REMOTE}" ]]; then
    log "Uploading to ${RCLONE_REMOTE}:${RCLONE_BUCKET}/db/ ..."
    rclone copy "${FILENAME}" "${RCLONE_REMOTE}:${RCLONE_BUCKET}/db/"
    log "Upload complete."
else
    log "RCLONE_REMOTE not set — skipping remote upload."
fi

# ---------------------------------------------------------------------------
# Retention: keep 7 days locally
# ---------------------------------------------------------------------------
log "Removing local backups older than 7 days..."
find "${BACKUP_DIR}" -name "*.sql.gz" -mtime +7 -delete
log "Retention cleanup done."
