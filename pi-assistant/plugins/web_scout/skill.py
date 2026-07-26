"""
plugins/web_scout/skill.py — Web Scout Plugin
==============================================
Scours public sports betting sources for picks, injury news, line moves,
and forum consensus — then uses AI to distill it into a concise betting
intelligence report.

Sources
-------
  ✅ Reddit          r/sportsbook, r/sportsbetting, r/nfl, r/nba, r/soccer
  ✅ ESPN            Live news headlines for NFL, NBA, MLB, NHL
  ✅ Action Network  Game lines & totals (public scoreboard API)
  ✅ RotoWire        Injury & player news for NBA and NFL
  ✅ Covers.com      Consensus picks and expert opinions
  ❌ Twitter/X       Requires paid API ($100/month) — not supported
  ❌ Discord         Requires OAuth bot token — not supported
  ❌ Facebook        No public scraping API available

Schedule
--------
Auto-runs every 6 hours. Manual trigger: command "scout"

Commands
--------
  scout           — Run a full scout immediately and email the report
  scout_results   — Show the last cached report
  scout_sources   — List which sources were hit in the last run
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from core.plugin_manager import BasePlugin
from core.logger import get_logger
from api.ai_client import AIClient, AIClientError

log = get_logger(__name__)

# Polite bot user-agent — some sites block generic Python agents
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PiAssistant/1.0; "
        "+https://github.com/your-username/pi-assistant)"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class WebScoutPlugin(BasePlugin):
    plugin_name = "Web Scout"
    plugin_version = "1.0.0"
    plugin_description = (
        "Scours Reddit, ESPN, Action Network & RotoWire for betting insights. "
        "Auto-runs on schedule, emails reports when done."
    )

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def setup(self) -> None:
        interval_hours = self.config.get("scout_interval_hours", 6)
        self.assistant.scheduler.add_interval_job(
            self._scheduled_scout,
            "web_scout.scheduled_scout",
            hours=interval_hours,
        )
        log.info(
            f"[web_scout] Ready — auto-scout every {interval_hours}h. "
            "Use 'scout' command to run immediately."
        )

    def teardown(self) -> None:
        pass

    # ── Commands ───────────────────────────────────────────────────────────────

    def get_commands(self) -> dict[str, Any]:
        return {
            "scout":         self.cmd_scout,
            "scout_results": self.cmd_results,
            "scout_sources": self.cmd_sources,
        }

    def cmd_scout(self, args: str = "", **kwargs) -> str:
        """Trigger an immediate full scout run."""
        log.info("[web_scout] Manual scout triggered")
        return self._run_scout(send_email=True)

    def cmd_results(self, args: str = "", **kwargs) -> str:
        """Return the last cached scout report."""
        if not self.assistant or not self.assistant.memory:
            return "Memory not available."
        report = self.assistant.memory.recall("web_scout.last_report")
        run_at = self.assistant.memory.recall("web_scout.last_run")
        if not report:
            return (
                "No scout results yet. "
                "Run the 'scout' command to fetch fresh data."
            )
        return f"**Last scouted:** {run_at}\n\n{report}"

    def cmd_sources(self, args: str = "", **kwargs) -> str:
        """List sources hit in the last run with item counts."""
        if not self.assistant or not self.assistant.memory:
            return "Memory not available."
        sources_raw = self.assistant.memory.recall("web_scout.last_sources")
        if not sources_raw:
            return "No scout run yet."
        return f"Sources from last run:\n{sources_raw}"

    # ── Core scout logic ───────────────────────────────────────────────────────

    def _scheduled_scout(self) -> None:
        """Called by the scheduler — run scout and email."""
        try:
            self._run_scout(send_email=True)
        except Exception:
            log.exception("[web_scout] Scheduled scout failed")

    def _run_scout(self, send_email: bool = False) -> str:
        findings: list[dict] = []
        source_summary: list[str] = []

        # ── Scrape all sources ─────────────────────────────────────────────────
        scrapers = [
            ("Reddit",         self._scrape_reddit),
            ("ESPN",           self._scrape_espn),
            ("Action Network", self._scrape_action_network),
            ("RotoWire",       self._scrape_rotowire),
            ("Covers.com",     self._scrape_covers),
        ]

        for name, scraper in scrapers:
            try:
                items = scraper()
                findings.extend(items)
                source_summary.append(f"  {name}: {len(items)} items")
                log.info(f"[web_scout] {name}: {len(items)} items")
            except Exception as exc:
                log.warning(f"[web_scout] {name} failed: {exc}")
                source_summary.append(f"  {name}: FAILED ({exc})")

        if not findings:
            return (
                "Scout completed but all sources returned no data. "
                "This can happen due to rate limiting — try again in 10 minutes."
            )

        # ── AI summary ────────────────────────────────────────────────────────
        report = self._summarise(findings)
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        # ── Persist ───────────────────────────────────────────────────────────
        if self.assistant and self.assistant.memory:
            self.assistant.memory.store("web_scout.last_report",  report)
            self.assistant.memory.store("web_scout.last_run",     now)
            self.assistant.memory.store(
                "web_scout.last_sources", "\n".join(source_summary)
            )

        # ── Notify (Discord first, fall back to email) ─────────────────────────
        if send_email:
            try:
                from core.emailer import send_discord_report, send_report
                notified = send_discord_report(
                    subject=f"Pi Assistant Scout Report — {now}",
                    body=report,
                )
                if not notified:
                    send_report(
                        subject=f"Pi Assistant Scout Report — {now}",
                        body=report,
                        config=self.assistant.config if self.assistant else None,
                    )
            except Exception as exc:
                log.warning(f"[web_scout] Notification failed: {exc}")

        return report

    # ── Scrapers ───────────────────────────────────────────────────────────────

    def _scrape_reddit(self) -> list[dict]:
        """Fetch hot posts from sports betting subreddits using Reddit's JSON API."""
        subreddits = [
            "sportsbook", "sportsbetting", "nfl", "nba",
            "soccer", "mlb", "nhl", "fantasyfootball",
        ]
        findings = []
        for sub in subreddits:
            try:
                url = f"https://www.reddit.com/r/{sub}/hot.json?limit=15"
                r = httpx.get(url, headers=_HEADERS, timeout=12, follow_redirects=True)
                if r.status_code != 200:
                    continue
                data = r.json()
                posts = data.get("data", {}).get("children", [])
                for post in posts[:8]:
                    p = post.get("data", {})
                    score = p.get("score", 0)
                    # Only include reasonably upvoted posts
                    if score < 20:
                        continue
                    title = p.get("title", "").strip()
                    body  = (p.get("selftext") or "").strip()[:600]
                    # Skip image-only posts
                    if not title:
                        continue
                    findings.append({
                        "source": f"Reddit r/{sub}",
                        "title": title,
                        "body":  body,
                        "score": score,
                        "url":   f"https://reddit.com{p.get('permalink', '')}",
                    })
            except Exception as exc:
                log.debug(f"[web_scout] Reddit r/{sub} error: {exc}")
        return findings

    def _scrape_espn(self) -> list[dict]:
        """Fetch recent news headlines from ESPN's public sports API."""
        sports = [
            ("football",    "nfl"),
            ("basketball",  "nba"),
            ("baseball",    "mlb"),
            ("hockey",      "nhl"),
            ("soccer",      "eng.1"),  # Premier League
        ]
        findings = []
        for sport, league in sports:
            try:
                url = (
                    f"https://site.api.espn.com/apis/site/v2/sports"
                    f"/{sport}/{league}/news?limit=5"
                )
                r = httpx.get(url, headers=_HEADERS, timeout=10)
                if r.status_code != 200:
                    continue
                articles = r.json().get("articles", [])
                for article in articles[:4]:
                    headline = article.get("headline", "").strip()
                    desc = (article.get("description") or "").strip()[:500]
                    if not headline:
                        continue
                    findings.append({
                        "source": f"ESPN {league.upper().replace('.1','')}",
                        "title": headline,
                        "body":  desc,
                    })
            except Exception as exc:
                log.debug(f"[web_scout] ESPN {league} error: {exc}")
        return findings

    def _scrape_action_network(self) -> list[dict]:
        """Fetch today's games and betting lines from Action Network's public API."""
        sports = ["nfl", "nba", "mlb", "nhl", "ncaab", "ncaaf"]
        today  = datetime.utcnow().strftime("%Y%m%d")
        findings = []

        for sport in sports:
            try:
                url = (
                    f"https://api.actionnetwork.com/web/v1/scoreboard/{sport}"
                    f"?period=event&bookIds=15,30,76&date={today}"
                )
                r = httpx.get(url, headers=_HEADERS, timeout=10)
                if r.status_code != 200:
                    continue
                games = r.json().get("games", [])
                for game in games[:6]:
                    home = game.get("home_team", {}).get("full_name", "TBD")
                    away = game.get("away_team", {}).get("full_name", "TBD")
                    lines = game.get("lines", [])

                    spread = total = ml_home = ml_away = "N/A"
                    if lines:
                        best = lines[0]
                        spread  = best.get("spread",    "N/A")
                        total   = best.get("total",     "N/A")
                        ml_home = best.get("home_ml",   "N/A")
                        ml_away = best.get("away_ml",   "N/A")

                    # Consensus betting %
                    consensus = game.get("consensus", {})
                    away_pct  = consensus.get("away_ml", "?")
                    home_pct  = consensus.get("home_ml", "?")

                    body = (
                        f"Spread: {spread} | Total: {total} | "
                        f"ML: {away} {ml_away} / {home} {ml_home} | "
                        f"Public: {away_pct}% {away} / {home_pct}% {home}"
                    )
                    findings.append({
                        "source": f"Action Network {sport.upper()}",
                        "title": f"{away} @ {home}",
                        "body":  body,
                    })
            except Exception as exc:
                log.debug(f"[web_scout] Action Network {sport} error: {exc}")
        return findings

    def _scrape_rotowire(self) -> list[dict]:
        """Scrape RotoWire injury and player news (requires BeautifulSoup)."""
        if not BS4_AVAILABLE:
            log.warning("[web_scout] beautifulsoup4 not installed — skipping RotoWire")
            return []

        pages = [
            ("RotoWire NFL",  "https://www.rotowire.com/football/news.php"),
            ("RotoWire NBA",  "https://www.rotowire.com/basketball/news.php"),
            ("RotoWire MLB",  "https://www.rotowire.com/baseball/news.php"),
        ]
        findings = []
        for source, url in pages:
            try:
                r = httpx.get(url, headers=_HEADERS, timeout=12, follow_redirects=True)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "lxml")
                # RotoWire uses various CSS classes — try common ones
                items = (
                    soup.select(".news-update")
                    or soup.select("[class*='news-item']")
                    or soup.select("article")
                )
                for item in items[:6]:
                    title_el = (
                        item.select_one(".news-update__title")
                        or item.select_one("h4")
                        or item.select_one("h3")
                    )
                    body_el = (
                        item.select_one(".news-update__news")
                        or item.select_one(".news-update__analysis")
                        or item.select_one("p")
                    )
                    title = title_el.get_text(strip=True) if title_el else ""
                    body  = body_el.get_text(strip=True)[:500]  if body_el  else ""
                    if title:
                        findings.append({
                            "source": source,
                            "title": title,
                            "body":  body,
                        })
            except Exception as exc:
                log.debug(f"[web_scout] RotoWire error: {exc}")
        return findings

    def _scrape_covers(self) -> list[dict]:
        """Scrape Covers.com consensus picks (requires BeautifulSoup)."""
        if not BS4_AVAILABLE:
            return []

        findings = []
        try:
            url = "https://www.covers.com/picks/consensus"
            r = httpx.get(url, headers=_HEADERS, timeout=12, follow_redirects=True)
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, "lxml")

            # Covers renders consensus percentages in a table
            rows = soup.select("table tr") or soup.select("[class*='consensus'] [class*='row']")
            for row in rows[:10]:
                cells = row.select("td")
                if len(cells) >= 3:
                    text = " | ".join(c.get_text(strip=True) for c in cells if c.get_text(strip=True))
                    if text:
                        findings.append({
                            "source": "Covers.com Consensus",
                            "title": text[:120],
                            "body":  "",
                        })
        except Exception as exc:
            log.debug(f"[web_scout] Covers.com error: {exc}")
        return findings

    # ── AI Summariser ──────────────────────────────────────────────────────────

    def _summarise(self, findings: list[dict]) -> str:
        """Send collected data to OpenAI and return a structured betting report."""
        # Cap at 40 items to keep the prompt reasonable
        capped = findings[:40]
        raw_text = "\n\n".join(
            f"[{f['source']}] {f['title']}\n{f.get('body', '')}".strip()
            for f in capped
        )

        prompt = f"""You are a sharp, no-nonsense sports betting analyst. \
Review the raw data below collected from Reddit, ESPN, Action Network, RotoWire, and Covers.com.

Produce a concise **Betting Intelligence Report** using exactly this structure:

## 🔥 Top Picks / Best Bets Today
List the 3-5 plays with the strongest signal or widest consensus. \
Include the bet type (spread/total/ML), why it has value, and a confidence level (Low/Medium/High).

## 🏥 Key Injuries & Line Moves
Any injuries, lineup changes, or line movement that affects today's slate. \
Flag anything that changes a pick.

## 📊 Public vs. Sharp Money
Identify any games where public betting % and line movement diverge \
(a sign of sharp action). Note contrarian opportunities.

## 🎯 Sports to Focus On Today
Which 1-2 sports have the best betting opportunities in today's slate and why.

## ⚠️ Traps / Avoid
Games or bets that look appealing but are likely sucker bets.

Be direct. No padding. Every sentence must be actionable.

--- RAW DATA ({len(capped)} items from {len(set(f['source'] for f in capped))} sources) ---
{raw_text}
"""

        try:
            ai = AIClient.from_config(self.assistant.config)
            report = ai.chat(prompt)
            return report
        except AIClientError as exc:
            log.error(f"[web_scout] AI summary failed: {exc}")
            # Return a raw digest so the user still gets something useful
            lines = [f"**AI summary unavailable:** {exc}\n"]
            lines.append("**Raw findings:**\n")
            for f in capped[:15]:
                lines.append(f"• [{f['source']}] {f['title']}")
            return "\n".join(lines)
