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
.venv/bin/python -m pip install -r deploy/armbian/requirements-batch.txt

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
export KAKEIBO_LOG_DIR="${LOG_DIR}"

RUNNER_LOG="${LOG_DIR}/auto-input-runner.log"
if [ -f "\${RUNNER_LOG}" ] && [ "\$(wc -c < "\${RUNNER_LOG}")" -ge 1048576 ]; then
  mv -f "\${RUNNER_LOG}.2" "\${RUNNER_LOG}.3" 2>/dev/null || true
  mv -f "\${RUNNER_LOG}.1" "\${RUNNER_LOG}.2" 2>/dev/null || true
  mv -f "\${RUNNER_LOG}" "\${RUNNER_LOG}.1"
fi

exec 9>"${APP_DIR}/.auto-input.lock"
flock -n 9 || exit 0
xvfb-run -a .venv/bin/python -m src.batch.kakeibo.auto_input_scheduler.server_runner \
  --connection-types NITORI,CAINZ,MUJI \
  --schedule-name daily-midnight >> "\${RUNNER_LOG}" 2>&1
EOF
chmod +x "${RUN_SCRIPT}"

# 2026-07-15 Codex: sudoなし環境でも毎日0時に同期できるよう、ユーザーcrontabで起動する。
(crontab -l 2>/dev/null | grep -v "${CRON_MARKER}" || true; echo "0 0 * * * ${RUN_SCRIPT} # ${CRON_MARKER}") | crontab -

crontab -l | grep "${CRON_MARKER}" || true
