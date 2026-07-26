"""
core/emailer.py — Email Report Sender
======================================
Sends formatted HTML reports via SMTP (Gmail or any provider).

Configuration (set in .env or as environment variables):
  EMAIL_USER        — Your Gmail address (or SMTP username)
  EMAIL_PASSWORD    — Gmail App Password (NOT your regular password)
                      Create one at: myaccount.google.com/apppasswords
  EMAIL_RECIPIENT   — Where to send reports (can be same as EMAIL_USER)

Optional (override defaults in config.yaml under 'email:'):
  email.smtp_host   — Default: smtp.gmail.com
  email.smtp_port   — Default: 587 (TLS)
"""

from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from core.config import Config

log = get_logger(__name__)

# ── Discord ────────────────────────────────────────────────────────────────────

_DISCORD_CHUNK = 3900   # Discord embed description limit is 4096; stay safe
_DISCORD_COLOR = 0x6C63FF  # purple


def send_discord_report(subject: str, body: str) -> bool:
    """
    Post a report to a Discord channel via webhook.

    Requires env var: DISCORD_WEBHOOK_URL
    Automatically splits long reports into multiple messages.
    Returns True on success.
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        log.warning(
            "Discord not configured — set DISCORD_WEBHOOK_URL in your .env file."
        )
        return False

    import httpx as _httpx

    # Split body into chunks that fit within Discord's embed limit
    chunks = [body[i:i + _DISCORD_CHUNK] for i in range(0, len(body), _DISCORD_CHUNK)]
    total  = len(chunks)

    try:
        for idx, chunk in enumerate(chunks, 1):
            title = subject if total == 1 else f"{subject} ({idx}/{total})"
            payload = {
                "embeds": [{
                    "title":       title,
                    "description": chunk,
                    "color":       _DISCORD_COLOR,
                    "footer":      {"text": "Pi Assistant · Sports Betting Scout"},
                }]
            }
            r = _httpx.post(webhook_url, json=payload, timeout=10)
            if r.status_code not in (200, 204):
                log.error(f"Discord webhook returned {r.status_code}: {r.text[:200]}")
                return False
        log.info(f"Discord report sent ({total} message(s)): {subject!r}")
        return True
    except Exception as exc:
        log.error(f"Failed to send Discord report: {exc}")
        return False


# ── Email ──────────────────────────────────────────────────────────────────────

def _is_configured() -> bool:
    """Return True if the minimum email env vars are set."""
    return bool(
        os.getenv("EMAIL_USER")
        and os.getenv("EMAIL_PASSWORD")
        and os.getenv("EMAIL_RECIPIENT")
    )


def send_report(subject: str, body: str, config: "Config | None" = None) -> bool:
    """
    Send a plain-text + HTML email report.

    Returns True on success, False if not configured or on error.
    """
    if not _is_configured():
        log.warning(
            "Email not configured — set EMAIL_USER, EMAIL_PASSWORD, EMAIL_RECIPIENT "
            "in your .env file to enable reports."
        )
        return False

    smtp_host = "smtp.gmail.com"
    smtp_port = 587
    if config:
        smtp_host = config.get("email.smtp_host", smtp_host)
        smtp_port = int(config.get("email.smtp_port", smtp_port))

    sender   = os.environ["EMAIL_USER"]
    password = os.environ["EMAIL_PASSWORD"]
    recipient = os.environ["EMAIL_RECIPIENT"]

    # ── Build message ──────────────────────────────────────────────────────────
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Pi Assistant <{sender}>"
    msg["To"]      = recipient

    # Plain text fallback
    msg.attach(MIMEText(body, "plain"))

    # HTML version
    html_body = _to_html(body)
    msg.attach(MIMEText(html_body, "html"))

    # ── Send ───────────────────────────────────────────────────────────────────
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        log.info(f"Report emailed to {recipient}: {subject!r}")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error(
            "Email authentication failed. Make sure you're using a Gmail App Password, "
            "not your regular account password. "
            "Create one at: myaccount.google.com/apppasswords"
        )
    except Exception as exc:
        log.error(f"Failed to send email: {exc}")
    return False


def _to_html(text: str) -> str:
    """Convert a markdown-ish plain text report into a simple HTML email."""
    lines = text.split("\n")
    html_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            html_lines.append(f'<h2 style="color:#6c63ff;margin-top:20px">{stripped[3:]}</h2>')
        elif stripped.startswith("# "):
            html_lines.append(f'<h1 style="color:#6c63ff">{stripped[2:]}</h1>')
        elif stripped.startswith("**") and stripped.endswith("**"):
            html_lines.append(f'<p><strong>{stripped[2:-2]}</strong></p>')
        elif stripped.startswith("- ") or stripped.startswith("• "):
            html_lines.append(f'<li>{stripped[2:]}</li>')
        elif stripped == "":
            html_lines.append("<br>")
        else:
            # Bold inline **text**
            import re
            formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
            html_lines.append(f"<p>{formatted}</p>")

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0f1117; color: #e2e2f0;
      max-width: 680px; margin: 0 auto; padding: 24px;
    }}
    h1, h2 {{ color: #6c63ff; }}
    p, li {{ line-height: 1.6; margin: 6px 0; color: #c8c8e0; }}
    ul {{ padding-left: 20px; }}
    .header {{
      border-bottom: 2px solid #6c63ff; padding-bottom: 12px; margin-bottom: 20px;
    }}
    .footer {{
      border-top: 1px solid #2a2d3a; padding-top: 12px; margin-top: 24px;
      font-size: 12px; color: #666;
    }}
  </style>
</head>
<body>
  <div class="header">
    <h1>🤖 Pi Assistant Report</h1>
    <p style="color:#8888a8;font-size:13px">Generated {timestamp}</p>
  </div>
  {''.join(html_lines)}
  <div class="footer">
    <p>Sent by Pi Assistant &mdash; your personal sports betting AI</p>
  </div>
</body>
</html>
"""
