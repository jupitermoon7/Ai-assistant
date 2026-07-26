# Pi Assistant — Raspberry Pi Deployment Guide

This guide gets Pi Assistant running 24/7 on your Raspberry Pi 4 (8 GB).
Once done, you control it from your Android phone on the same Wi-Fi network.

---

## Prerequisites

- Raspberry Pi 4 (8 GB RAM) running **Raspberry Pi OS Lite** (64-bit recommended)
- Pi is connected to your home Wi-Fi / router
- You can SSH into the Pi (`ssh pi@<pi-ip>`)
- Your router has assigned the Pi a static/reserved IP (recommended)

---

## Step 1 — Find Your Pi's IP Address

On the Pi (or via your router's admin page):

```bash
hostname -I
# e.g. 192.168.1.42
```

Write this down — it's the address you'll use on your Android browser.

---

## Step 2 — Install Python 3.11

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip git
```

---

## Step 3 — Get the Code onto the Pi

**Option A — Git (recommended):**

```bash
# On the Pi
cd ~
git clone <your-repo-url> pi-assistant-project
cd pi-assistant-project/pi-assistant
```

**Option B — Copy from this Replit project:**

```bash
# On your computer (not the Pi)
scp -r pi-assistant/ pi@<pi-ip>:~/pi-assistant/
ssh pi@<pi-ip>
cd ~/pi-assistant
```

---

## Step 4 — Run the Setup Script

```bash
cd ~/pi-assistant   # make sure you're in the pi-assistant folder
chmod +x setup.sh
./setup.sh
```

This creates a virtual environment and installs all Python dependencies.

---

## Step 5 — Create Your `.env` File

```bash
nano .env
```

Paste and fill in your values:

```env
# Required — your OpenAI API key
OPENAI_API_KEY=sk-...your-key-here...

# Dashboard login
DASHBOARD_SECRET_KEY=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD_HASH=<generate — see below>

# Email reports (optional but recommended)
EMAIL_USER=yourgmail@gmail.com
EMAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx   # Gmail App Password, NOT your real password
EMAIL_RECIPIENT=yourgmail@gmail.com   # Where reports are sent
```

**Generate your password hash** (run this on the Pi):

```bash
source venv/bin/activate
python3 -c "import bcrypt; print(bcrypt.hashpw(b'YourPassword', bcrypt.gensalt()).decode())"
```

Paste the output as `DASHBOARD_PASSWORD_HASH` in `.env`.

**Gmail App Password** — Create one at:
https://myaccount.google.com/apppasswords
(You must have 2-Step Verification enabled on your Google account.)

---

## Step 6 — Test It First

```bash
source venv/bin/activate
python3 main.py
```

You should see:
```
INFO  Initialising Pi Assistant v0.1.0
INFO  Dashboard starting on http://0.0.0.0:8000
```

Open your Android browser and go to:
```
http://192.168.1.42:8000     ← use YOUR Pi's IP
```

Log in and send a test message. If it works, Ctrl+C to stop and continue.

---

## Step 7 — Install as a System Service (runs 24/7)

```bash
chmod +x install-service.sh
sudo ./install-service.sh
```

This installs and enables the `pi-assistant` systemd service so it:
- Starts automatically on boot
- Restarts automatically if it crashes

**Service commands:**
```bash
sudo systemctl status pi-assistant     # Check if running
sudo systemctl restart pi-assistant    # Restart after config changes
sudo systemctl stop pi-assistant       # Stop it
sudo journalctl -u pi-assistant -f     # Live logs
```

---

## Step 8 — Access from Android

1. Connect your Android phone to **the same Wi-Fi network** as the Pi
2. Open Chrome (or any browser) and go to:
   ```
   http://192.168.1.42:8000
   ```
3. Log in — you're in

**Tip:** Add it to your Android home screen for app-like access:
Chrome → three-dot menu → "Add to Home screen"

---

## Accessing from Outside Your Home Network (optional)

The dashboard is only reachable on your local network by default.
To access it from anywhere:

- **Tailscale** (easiest, free) — installs a VPN on both Pi and phone:
  ```bash
  curl -fsSL https://tailscale.com/install.sh | sh
  sudo tailscale up
  ```
  Then use the Tailscale IP instead of your local IP.

- **Cloudflare Tunnel** — free, no port forwarding needed
- **Port forward on your router** — works but exposes the Pi to the internet

---

## Keeping the Code Updated

When you make changes on Replit and want to push them to the Pi:

```bash
# On the Pi
cd ~/pi-assistant-project
git pull
sudo systemctl restart pi-assistant
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Dashboard won't load | `sudo systemctl status pi-assistant` — check for errors |
| AI not responding | Check `OPENAI_API_KEY` in `.env` |
| Email not sending | Use a Gmail **App Password**, not your normal password |
| Port 8000 in use | Another process is on 8000 — change `dashboard.port` in `config.yaml` |
| Can't reach from Android | Make sure phone and Pi are on the same Wi-Fi |
