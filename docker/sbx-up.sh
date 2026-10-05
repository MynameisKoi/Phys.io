#!/usr/bin/env bash
set -euo pipefail

# Configuration
SANDBOX_NAME="${SANDBOX_NAME:-physio-live}"
CPUS="${CPUS:-4}"
MEMORY="${MEMORY:-8g}"
TTL="${TTL:-24h}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== [sbx-up] Docker Cloud Sandbox Provisioning ==="
echo "Sandbox Name:  ${SANDBOX_NAME}"
echo "Sizing:        ${CPUS} CPUs, ${MEMORY} RAM"
echo "TTL:           ${TTL}"
echo "Repo Dir:      ${REPO_DIR}"

# 1. Verify sbx CLI and cloud authentication
if ! command -v sbx >/dev/null 2>&1; then
    echo "Error: sbx CLI is not installed. Please install Docker Sandboxes CLI." >&2
    exit 1
fi

if ! sbx --cloud ls >/dev/null 2>&1; then
    echo "Error: You are not authenticated to Docker Cloud Sandboxes." >&2
    echo "Please run: sbx login" >&2
    exit 1
fi

# 2. Check if sandbox already exists
EXISTING=$(sbx --cloud ls --json 2>/dev/null | grep "\"${SANDBOX_NAME}\"" || true)
if [ -n "$EXISTING" ]; then
    echo "[sbx-up] Sandbox '${SANDBOX_NAME}' already exists. Reusing existing instance..."
else
    echo "[sbx-up] Creating cloud microVM '${SANDBOX_NAME}'..."
    sbx --cloud create shell \
        --name "${SANDBOX_NAME}" \
        --cpus "${CPUS}" \
        --memory "${MEMORY}" \
        --ttl "${TTL}" \
        --allow-network "api.anthropic.com" \
        --allow-network "api.openalex.org" \
        --allow-network "mcp.brightdata.com" \
        --allow-network "pypi.org" \
        --allow-network "files.pythonhosted.org" \
        --allow-network "github.com" \
        --allow-network "registry-1.docker.io" \
        --allow-network "production.cloudflare.docker.com" \
        --allow-network "auth.docker.io" \
        --allow-network "deb.debian.org"
fi

# 3. Copy repository into sandbox
echo "[sbx-up] Copying repository to sandbox /workspace..."
sbx --cloud cp "${REPO_DIR}" "${SANDBOX_NAME}:/workspace"

# 4. Build image inside microVM
echo "[sbx-up] Building physio-live image inside microVM..."
sbx --cloud exec "${SANDBOX_NAME}" -- docker build -t physio-live /workspace

# 5. Run container with --privileged to enable bwrap
echo "[sbx-up] Launching physio-live container with --privileged..."
# Remove any existing container inside sandbox
sbx --cloud exec "${SANDBOX_NAME}" -- sh -c "docker rm -f physio-app 2>/dev/null || true"

# Pass credentials if available in local environment or .env
ANTHROPIC_KEY="${ANTHROPIC_API_KEY:-}"
BRIGHTDATA_TOKEN="${BRIGHTDATA_API_TOKEN:-}"

if [ -z "$ANTHROPIC_KEY" ] && [ -f "${REPO_DIR}/.env" ]; then
    ANTHROPIC_KEY="$(grep -E '^ANTHROPIC_API_KEY=' "${REPO_DIR}/.env" | cut -d '=' -f2- || true)"
fi
if [ -z "$BRIGHTDATA_TOKEN" ] && [ -f "${REPO_DIR}/.env" ]; then
    BRIGHTDATA_TOKEN="$(grep -E '^BRIGHTDATA_API_TOKEN=' "${REPO_DIR}/.env" | cut -d '=' -f2- || true)"
fi

sbx --cloud exec "${SANDBOX_NAME}" -- docker run -d \
    --restart unless-stopped \
    --privileged \
    --name physio-app \
    -p 8000:8000 \
    -e ANTHROPIC_API_KEY="${ANTHROPIC_KEY}" \
    -e BRIGHTDATA_API_TOKEN="${BRIGHTDATA_TOKEN}" \
    -e LAB_ALLOW_START=1 \
    physio-live

# 6. Publish port 8000 and print public URL
echo "[sbx-up] Publishing port 8000 to obtain public HTTPS URL..."
sbx --cloud ports "${SANDBOX_NAME}" --publish 8000 || true

echo ""
echo "=== [sbx-up] MicroVM Lab Ready! ==="
echo "Published ports:"
sbx --cloud ports "${SANDBOX_NAME}"

echo ""
echo "Next step for Render proxy (Issue #6):"
echo "  Set LAB_REMOTE_URL on Render to the public HTTPS URL printed above."
