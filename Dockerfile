FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_TOOL_BIN_DIR=/usr/local/bin \
    PATH="/root/.local/bin:/usr/local/bin:${PATH}"

# Install tmux, bubblewrap, git, and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux \
    bubblewrap \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv for tool management
RUN pip install --no-cache-dir uv

# Install Omnigent with databricks extras and numpy/scipy support
RUN uv tool install "omnigent[databricks]==0.16.0" --with numpy --with scipy \
    && (which omni || ln -s /root/.local/bin/omni /usr/local/bin/omni)

WORKDIR /app

# Install backend dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt optuna tmm pvlib

# Copy repo files
COPY . /app

# Preserve runs/example as a template for volume restoration
RUN mkdir -p /app/runs_template && \
    if [ -d /app/runs/example ]; then cp -r /app/runs/example /app/runs_template/example; fi

# Editable install of scientific packages (physics_lab, lab, bench, analysis)
RUN pip install --no-cache-dir -e .

RUN chmod +x /app/docker/render-start.sh

ENV PYTHONPATH="/app:/app/backend"
ENV LAB_ALLOW_START=1
ENV PORT=8000

EXPOSE 8000

CMD ["/app/docker/render-start.sh"]
