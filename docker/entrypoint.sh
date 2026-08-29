#!/bin/bash
set -e

# yt-dlp breaks frequently when YouTube changes its API.
# Upgrading at container start ensures we always run the newest version
# without rebuilding the image.
# --pre pulls the nightly channel: stable releases lag YouTube's gating by
# weeks (2026.07.04 stable 403'd on every stream; the nightly does not).
echo "[yt] Updating yt-dlp..."
pip install -q --user --upgrade --pre "yt-dlp[default]" \
  || echo "[yt] WARNING: yt-dlp update failed — continuing with installed version"

echo "[yt] Starting backend..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level "${LOG_LEVEL:-info}"
