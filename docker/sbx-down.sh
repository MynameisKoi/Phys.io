#!/usr/bin/env bash
set -euo pipefail

SANDBOX_NAME="${SANDBOX_NAME:-physio-live}"
BACKUP_DIR="${BACKUP_DIR:-./runs-backup}"

echo "=== [sbx-down] Docker Cloud Sandbox Teardown ==="
echo "Sandbox Name: ${SANDBOX_NAME}"

if ! command -v sbx >/dev/null 2>&1; then
    echo "Error: sbx CLI is not installed." >&2
    exit 1
fi

# 1. Download run artifacts before termination if requested or if runs exist
if [ "${1:-}" == "--save-runs" ] || [ "${SAVE_RUNS:-1}" == "1" ]; then
    echo "[sbx-down] Exporting runs directory to ${BACKUP_DIR}..."
    mkdir -p "${BACKUP_DIR}"
    sbx --cloud cp "${SANDBOX_NAME}:/workspace/runs" "${BACKUP_DIR}" 2>/dev/null || \
        echo "[sbx-down] Note: Could not copy /workspace/runs (may be empty or already saved)."
fi

# 2. Stop and remove sandbox
if [ "${1:-}" == "--stop-only" ]; then
    echo "[sbx-down] Stopping sandbox without deletion..."
    sbx --cloud stop "${SANDBOX_NAME}"
    echo "[sbx-down] Sandbox stopped. Can be resumed with 'sbx --cloud attach ${SANDBOX_NAME}'."
else
    echo "[sbx-down] Deleting sandbox ${SANDBOX_NAME}..."
    sbx --cloud rm -f "${SANDBOX_NAME}"
    echo "[sbx-down] Sandbox ${SANDBOX_NAME} removed."
fi
