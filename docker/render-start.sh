#!/usr/bin/env bash
set -euo pipefail

# 1. Puts runs/ and ~/.omnigent on /data when that is writable,
# and copies runs/example (the Experiment Runner's template) there.
DATA_DIR="/data"
if [ -d "$DATA_DIR" ] && [ -w "$DATA_DIR" ]; then
    echo "[render-start] /data is writable. Setting up persistent storage..."
    mkdir -p /data/runs /data/.omnigent
    
    # Setup runs/ as symlink to /data/runs
    if [ ! -L "/app/runs" ]; then
        if [ -d "/app/runs" ]; then
            cp -rn /app/runs/* /data/runs/ 2>/dev/null || true
            rm -rf /app/runs
        fi
        ln -sf /data/runs /app/runs
    fi

    # Setup ~/.omnigent as symlink to /data/.omnigent
    mkdir -p "$HOME"
    if [ ! -L "$HOME/.omnigent" ]; then
        if [ -d "$HOME/.omnigent" ]; then
            cp -rn "$HOME/.omnigent"/* /data/.omnigent/ 2>/dev/null || true
            rm -rf "$HOME/.omnigent"
        fi
        ln -sf /data/.omnigent "$HOME/.omnigent"
    fi
else
    echo "[render-start] /data is not mounted or not writable. Using local container storage."
    mkdir -p /app/runs "$HOME/.omnigent"
fi

# Ensure runs/example template is in place
if [ ! -d "/app/runs/example" ]; then
    echo "[render-start] Restoring runs/example template..."
    mkdir -p /app/runs
    if [ -d "/app/runs_template/example" ]; then
        cp -r /app/runs_template/example /app/runs/example
    fi
fi

# 2. Writes an Omnigent provider entry (api_key_ref: env:ANTHROPIC_API_KEY)
mkdir -p "$HOME/.omnigent"
cat << 'EOF' > "$HOME/.omnigent/config.yaml"
auto_open_conversation: true
default_agent: backend/app/agents
providers:
  anthropic:
    anthropic:
      api_key_ref: env:ANTHROPIC_API_KEY
      base_url: https://api.anthropic.com
    kind: key
EOF

# 3. Writes BRIGHTDATA_API_TOKEN to .env
touch /app/.env
if [ -n "${BRIGHTDATA_API_TOKEN:-}" ]; then
    sed -i '/^BRIGHTDATA_API_TOKEN=/d' /app/.env 2>/dev/null || true
    echo "BRIGHTDATA_API_TOKEN=${BRIGHTDATA_API_TOKEN}" >> /app/.env
fi

if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    sed -i '/^ANTHROPIC_API_KEY=/d' /app/.env 2>/dev/null || true
    echo "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}" >> /app/.env
fi

# 4. Runs omni start, then uvicorn
export PYTHONPATH="/app:/app/backend:${PYTHONPATH:-}"
echo "[render-start] Starting Omnigent server..."
omni start

echo "[render-start] Starting Uvicorn backend on port ${PORT:-8000}..."
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
