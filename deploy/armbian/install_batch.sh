#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${HOME_KAKEIBO_APP_DIR:-/opt/home-kakeibo-batch}"
SERVICE_USER="${HOME_KAKEIBO_SERVICE_USER:-$(id -un)}"
SERVICE_GROUP="${HOME_KAKEIBO_SERVICE_GROUP:-$(id -gn)}"
ENV_FILE="${HOME_KAKEIBO_ENV_FILE:-/etc/home-kakeibo-batch.env}"
PYTHON_BIN="${HOME_KAKEIBO_PYTHON:-python3}"

cd "${APP_DIR}"

if [ ! -d ".venv" ]; then
  "${PYTHON_BIN}" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r lambda_api/requirements-layer.txt

if [ ! -f "${ENV_FILE}" ]; then
  sudo install -m 600 -o root -g root deploy/armbian/home-kakeibo-batch.env.example "${ENV_FILE}"
  echo "Created ${ENV_FILE}. Please set real cloud DB/API values before production run."
fi

SERVICE_FILE="/etc/systemd/system/home-kakeibo-auto-input.service"
TIMER_FILE="/etc/systemd/system/home-kakeibo-auto-input.timer"

sudo tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=Home Kakeibo auto input batch
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${APP_DIR}
EnvironmentFile=-${ENV_FILE}
ExecStart=${APP_DIR}/.venv/bin/python -m src.batch.auto_input_scheduler.server_runner --connection-types BELC,ETC,AMAZON --schedule-name daily-midnight
EOF

sudo tee "${TIMER_FILE}" >/dev/null <<EOF
[Unit]
Description=Run Home Kakeibo auto input batch every day at 00:00

[Timer]
OnCalendar=*-*-* 00:00:00
Persistent=true
Unit=home-kakeibo-auto-input.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now home-kakeibo-auto-input.timer

# 2026-07-15 Codex: 初期導入後すぐ状態確認できるよう、タイマー一覧を表示する。
systemctl list-timers home-kakeibo-auto-input.timer --no-pager
