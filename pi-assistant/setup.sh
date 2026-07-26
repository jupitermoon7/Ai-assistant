#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup.sh — One-shot environment setup
#
# Run this once on any machine (development laptop or Raspberry Pi) to create
# the virtual environment and install all dependencies.
#
# Usage:
#   cd pi-assistant
#   chmod +x setup.sh
#   ./setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "─────────────────────────────────────────"
echo "  Pi Assistant — Environment Setup"
echo "─────────────────────────────────────────"

# ── Python version check ───────────────────────────────────────────────────
PYTHON_BIN="python3"
PYTHON_VERSION=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
REQUIRED_MAJOR=3
REQUIRED_MINOR=9

echo "[1/5] Python version: $PYTHON_VERSION"
if ! "$PYTHON_BIN" -c "import sys; assert sys.version_info >= (${REQUIRED_MAJOR}, ${REQUIRED_MINOR})" 2>/dev/null; then
  echo "ERROR: Python ${REQUIRED_MAJOR}.${REQUIRED_MINOR}+ is required (found $PYTHON_VERSION)."
  echo "       On Raspberry Pi OS: sudo apt install python3"
  exit 1
fi

# ── Virtual environment ────────────────────────────────────────────────────
echo "[2/5] Creating virtual environment…"
if [ -d "venv" ]; then
  echo "       venv/ already exists — skipping creation"
else
  "$PYTHON_BIN" -m venv venv
  echo "       Created venv/"
fi

# ── Activate and install ───────────────────────────────────────────────────
echo "[3/5] Installing dependencies from requirements.txt…"
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "       Dependencies installed"

# ── Data directories ───────────────────────────────────────────────────────
echo "[4/5] Creating data directories…"
mkdir -p data/memory data/logs
echo "       data/memory/ and data/logs/ ready"

# ── .env file ─────────────────────────────────────────────────────────────
echo "[5/5] Checking .env file…"
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "       Created .env from .env.example"
  echo ""
  echo "  ┌──────────────────────────────────────────────────────────────┐"
  echo "  │  IMPORTANT: Edit .env before starting the assistant!         │"
  echo "  │                                                              │"
  echo "  │  Required:                                                   │"
  echo "  │    DASHBOARD_SECRET_KEY — generate with:                     │"
  echo "  │      python -c \"import secrets; print(secrets.token_hex(32))\"│"
  echo "  │    DASHBOARD_PASSWORD_HASH — generate with:                  │"
  echo "  │      python -c \"import bcrypt;                               │"
  echo "  │        print(bcrypt.hashpw(b'pass', bcrypt.gensalt()).decode())\"│"
  echo "  │    OPENAI_API_KEY — or set AI_BASE_URL for local Ollama      │"
  echo "  └──────────────────────────────────────────────────────────────┘"
else
  echo "       .env already exists — skipping"
fi

echo ""
echo "─────────────────────────────────────────"
echo "  Setup complete!"
echo ""
echo "  To start the assistant:"
echo "    source venv/bin/activate"
echo "    python main.py"
echo ""
echo "  To install as a systemd service (Pi):"
echo "    sudo ./install-service.sh"
echo "─────────────────────────────────────────"
