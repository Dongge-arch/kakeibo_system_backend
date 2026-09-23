#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST_ALIAS="${HOME_KAKEIBO_HOST_ALIAS:-kakeibo-server}"
REMOTE_DIR="${HOME_KAKEIBO_REMOTE_DIR:-/home/armbian/home-kakeibo-batch}"

command -v rsync >/dev/null
command -v ssh >/dev/null

ssh "${HOST_ALIAS}" "mkdir -p '${REMOTE_DIR}/lambda_api' '${REMOTE_DIR}/deploy/armbian'"
rsync -az --delete --delete-excluded \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  "${ROOT_DIR}/src/" "${HOST_ALIAS}:${REMOTE_DIR}/src/"
rsync -az \
  "${ROOT_DIR}/lambda_api/requirements-layer.txt" \
  "${HOST_ALIAS}:${REMOTE_DIR}/lambda_api/requirements-layer.txt"
rsync -az --delete \
  "${ROOT_DIR}/deploy/armbian/" "${HOST_ALIAS}:${REMOTE_DIR}/deploy/armbian/"

ssh "${HOST_ALIAS}" "cd '${REMOTE_DIR}' && bash deploy/armbian/install_batch_user.sh"
ssh "${HOST_ALIAS}" "cd '${REMOTE_DIR}' && .venv/bin/python -m compileall -q src && .venv/bin/python -m src.batch.kakeibo.auto_input_scheduler.server_runner --help >/dev/null"

printf 'Armbian batch deployed to %s:%s\n' "${HOST_ALIAS}" "${REMOTE_DIR}"
