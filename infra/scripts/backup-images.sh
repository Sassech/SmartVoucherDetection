#!/usr/bin/env bash
# infra/scripts/backup-images.sh
#
# Sync uploaded voucher images to a cloud remote via rclone.
# Usage:
#   bash ~/SmartVoucherDetection/infra/scripts/backup-images.sh
#
# Make executable: chmod +x ~/SmartVoucherDetection/infra/scripts/backup-images.sh
#
# Optional env vars:
#   UPLOADS_DIR     — local uploads directory
#                     (default: ~/SmartVoucherDetection/data/uploads)
#   RCLONE_REMOTE   — rclone remote name (e.g. "s3"); REQUIRED for upload.
#                     If unset, the script prints a notice and exits 0.
#   RCLONE_BUCKET   — bucket/path on the remote (default: smartvoucher-backups)
#
# Cron example (runs daily at 03:00):
#   0 3 * * * /bin/bash ~/SmartVoucherDetection/infra/scripts/backup-images.sh >> ~/logs/backup-images.log 2>&1

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
UPLOADS_DIR="${UPLOADS_DIR:-${HOME}/SmartVoucherDetection/data/uploads}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
RCLONE_BUCKET="${RCLONE_BUCKET:-smartvoucher-backups}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ts()  { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*"; }

# ---------------------------------------------------------------------------
# Guard: RCLONE_REMOTE must be set
# ---------------------------------------------------------------------------
if [[ -z "${RCLONE_REMOTE}" ]]; then
    log "RCLONE_REMOTE not set, skipping image backup."
    exit 0
fi

# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------
log "Syncing uploads → ${RCLONE_REMOTE}:${RCLONE_BUCKET}/uploads/ ..."
rclone sync "${UPLOADS_DIR}" "${RCLONE_REMOTE}:${RCLONE_BUCKET}/uploads/" --progress
log "Image sync complete."
