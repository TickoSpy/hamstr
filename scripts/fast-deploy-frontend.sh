#!/usr/bin/env bash
#
# Fast frontend deploy — no Docker image rebuild, no container restart.
#
# The frontend container is just nginx serving the static Vite build from
# /usr/share/nginx/html. So instead of the slow `docker compose up --build`
# (npm ci + vite build inside the image), we build the bundle locally and copy
# it straight into the running container. Takes a few seconds instead of minutes.
#
# Frontend changes only. Backend (Python) changes still need `docker compose
# up --build` because the backend image bakes in the code.
#
# Usage:
#   scripts/fast-deploy-frontend.sh root@your-server
#   scripts/fast-deploy-frontend.sh root@your-server hamstr-frontend-1
#
# The target host can also come from $DEPLOY_HOST instead of the first argument.
#
set -euo pipefail

HOST="${1:-${DEPLOY_HOST:?target host required: pass root@your-server or set DEPLOY_HOST}}"
CONTAINER="${2:-hamstr-frontend-1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "→ Building frontend bundle…"
npm run build --prefix "$ROOT/frontend"

echo "→ Shipping dist to $CONTAINER on $HOST…"
# Clear stale hashed assets, then stream the new build straight into nginx's webroot.
ssh "$HOST" "docker exec $CONTAINER sh -c 'rm -rf /usr/share/nginx/html/*'"
tar -C "$ROOT/frontend/dist" -cf - . | ssh "$HOST" "docker cp - $CONTAINER:/usr/share/nginx/html"

echo "✓ Frontend updated live (reload the page). Backend changes still need a rebuild."
