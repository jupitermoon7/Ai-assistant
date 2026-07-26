# Pi Assistant

A production-quality, modular personal AI assistant designed to run 24/7 on a Raspberry Pi 4 and be controlled from an Android phone via a secure web dashboard.

---

## Architecture Overview

```
pi-assistant/
├── main.py                    # Entry point — starts all subsystems
├── config.yaml                # All runtime configuration
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable template
├── setup.sh                   # One-shot setup script
├── install-service.sh         # Installs the systemd service
├── pi-assistant.service       # systemd unit file
│
├── core/                      # Core subsystems (always running)
│   ├── assistant.py           # Main orchestrator — wires everything together
│   ├── config.py              # Config loader (YAML + env vars)
│   ├── logger.py              # Centralised structured logging
│   ├── memory.py              # Long-term memory (SQLite, upgradeable)
│   ├── scheduler.py           # Task scheduler (APScheduler)
│   └── plugin_manager.py      # Plugin discovery and lifecycle manager
│
├── api/                       # API integration layer
│   ├── ai_client.py           # OpenAI-compatible LLM client
│   └── external.py            # Generic external service client
│
├── plugins/                   # Skills / feature plugins (drop-in)
│   └── example_skill/         # Reference plugin implementation
│       ├── __init__.py
│       └── skill.py
│
├── dashboard/                 # Secure web dashboard (Flask)
│   ├── app.py                 # Flask app factory
│   ├── auth.py                # Login / session management
│   ├── routes/
│   │   ├── main.py            # Dashboard UI routes
│   │   └── api.py             # REST API routes (for Android client)
│   └── templates/             # Jinja2 HTML templates
│
├── data/
│   ├── memory/                # SQLite memory database lives here
│   └── logs/                  # Rotating log files
│
└── tests/                     # Unit tests
    └── test_core.py
```

---

## Quick Start (Development)

```bash
cd pi-assistant
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your secrets
python main.py
```

## Raspberry Pi Deployment

```bash
# On the Pi, after copying the project:
cd pi-assistant
chmod +x setup.sh install-service.sh
./setup.sh
# Edit .env with production values
sudo ./install-service.sh
sudo systemctl start pi-assistant
sudo systemctl status pi-assistant
```

## Dashboard Access

Navigate to `http://<pi-ip>:8080` from your Android browser.  
Default credentials are set in `config.yaml` — **change them before deployment**.

## Adding a New Skill

1. Create a folder under `plugins/your_skill_name/`.
2. Add `__init__.py` and `skill.py` implementing the `BasePlugin` interface.
3. Restart the assistant — the plugin manager will auto-discover it.

See `plugins/example_skill/skill.py` for a complete reference implementation.
