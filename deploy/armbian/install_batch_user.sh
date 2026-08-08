#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${HOME_KAKEIBO_APP_DIR:-$(pwd)}"
ENV_FILE="${HOME_KAKEIBO_ENV_FILE:-${APP_DIR}/.env}"
PYTHON_BIN="${HOME_KAKEIBO_PYTHON:-python3}"
LOG_DIR="${APP_DIR}/logs"
CRON_MARKER="home-kakeibo-auto-input"

cd "${APP_DIR}"
mkdir -p "${LOG_DIR}"

if [ ! -d ".venv" ]; then
  "${PYTHON_BIN}" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r lambda_api/requirements-layer.txt

if [ ! -f "${ENV_FILE}" ]; then
  cp deploy/armbian/home-kakeibo-batch.env.example "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  echo "Created ${ENV_FILE}. Please set real cloud DB/API values before production run."
fi

RUN_SCRIPT="${APP_DIR}/run_auto_input_batch.sh"
cat > "${RUN_SCRIPT}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "${APP_DIR}"
set -a
[ -f "${ENV_FILE}" ] && . "${ENV_FILE}"
set +a
.venv/bin/python -m src.batch.auto_input_scheduler.server_runner --connection-types BELC,ETC,AMAZON --schedule-name daily-midnight >> "${LOG_DIR}/auto-input.log" 2>&1
EOF
chmod +x "${RUN_SCRIPT}"

# 2026-07-15 Codex: sudoなし環境でも毎日0時に同期できるよう、ユーザーcrontabで起動する。
(crontab -l 2>/dev/null | grep -v "${CRON_MARKER}" || true; echo "0 0 * * * ${RUN_SCRIPT} # ${CRON_MARKER}") | crontab -

crontab -l | grep "${CRON_MARKER}" || true
