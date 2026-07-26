#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install-service.sh — Install Pi Assistant as a systemd service
#
# Run this on the Raspberry Pi AFTER running setup.sh.
# Must be run as root (sudo).
#
# What it does:
# 1. Resolves the absolute project path and venv Python path.
# 2. Writes the final pi-assistant.service unit file to /etc/systemd/system/.
# 3. Enables and optionally starts the service.
#
# Usage:
#   cd pi-assistant
#   chmod +x install-service.sh
#   sudo ./install-service.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Must run as root ───────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: This script must be run as root."
  echo "       Run: sudo ./install-service.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
SERVICE_NAME="pi-assistant"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "─────────────────────────────────────────"
echo "  Pi Assistant — systemd Service Install"
echo "─────────────────────────────────────────"

# ── Validate venv ──────────────────────────────────────────────────────────
if [ ! -f "$VENV_PYTHON" ]; then
  echo "ERROR: Virtual environment not found at $VENV_PYTHON"
  echo "       Run ./setup.sh first, then retry."
  exit 1
fi

# ── Determine the user who owns the project directory ─────────────────────
# Default to 'pi' (standard Raspberry Pi OS user) or the sudo caller.
PROJECT_OWNER="${SUDO_USER:-pi}"
echo "Project directory : $PROJECT_DIR"
echo "Python binary     : $VENV_PYTHON"
echo "Service user      : $PROJECT_OWNER"
echo ""

# ── Write the systemd unit file ────────────────────────────────────────────
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Pi Assistant — Personal AI Assistant
# Start after the network is up so the dashboard is reachable immediately
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${PROJECT_OWNER}
Group=${PROJECT_OWNER}

# Working directory — all relative paths in the code resolve from here
WorkingDirectory=${PROJECT_DIR}

# The venv Python runs main.py
ExecStart=${VENV_PYTHON} ${PROJECT_DIR}/main.py

# Load .env so secrets are available in the process environment
EnvironmentFile=${PROJECT_DIR}/.env

# Restart policy — restart on crashes but not on clean exits
Restart=on-failure
RestartSec=5

# Log everything to the systemd journal (view with: journalctl -u pi-assistant -f)
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pi-assistant

[Install]
# Start on boot when multi-user (normal operating) mode is reached
WantedBy=multi-user.target
EOF

echo "Wrote unit file → $SERVICE_FILE"

# ── Enable the service ─────────────────────────────────────────────────────
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
echo "Service enabled (will start on next boot)"

# ── Optionally start right now ─────────────────────────────────────────────
echo ""
read -r -p "Start the service now? [Y/n] " START_NOW
START_NOW="${START_NOW:-Y}"
if [[ "$START_NOW" =~ ^[Yy]$ ]]; then
  systemctl start "$SERVICE_NAME"
  sleep 2
  systemctl status "$SERVICE_NAME" --no-pager --lines=10
else
  echo ""
  echo "Service installed but not started."
  echo "Start manually with: sudo systemctl start $SERVICE_NAME"
fi

echo ""
echo "─────────────────────────────────────────"
echo "  Useful commands:"
echo "  sudo systemctl start   $SERVICE_NAME"
echo "  sudo systemctl stop    $SERVICE_NAME"
echo "  sudo systemctl restart $SERVICE_NAME"
echo "  sudo systemctl status  $SERVICE_NAME"
echo "  journalctl -u $SERVICE_NAME -f   (live logs)"
echo "─────────────────────────────────────────"
