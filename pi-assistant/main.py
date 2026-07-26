"""
main.py — Entry Point
======================
Start the Pi Assistant from this file:

    python main.py

This module does three things and nothing else:
1. Adds the project root to sys.path so all package imports resolve correctly.
2. Instantiates the Assistant orchestrator.
3. Calls start() → run() which blocks until a shutdown signal is received.

Everything else — logging, memory, scheduler, plugins, dashboard — is
initialised inside core/assistant.py.

Run modes
---------
Development (this machine):
    python main.py

Production (Raspberry Pi, via systemd):
    /path/to/venv/bin/python main.py

The systemd unit file (pi-assistant.service) and install script
(install-service.sh) handle the production setup automatically.
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so ``from core.xxx import yyy`` works
# regardless of the working directory the process was launched from.
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    """Bootstrap and run the assistant until a shutdown signal is received."""
    from core.assistant import Assistant

    assistant = Assistant()
    assistant.start()
    assistant.run()   # blocks here until SIGINT or SIGTERM


if __name__ == "__main__":
    main()
