"""
core/agent_tools.py — Live Tool Implementations for the AI Agent
=================================================================
These are the real-world tools the AI can call during a conversation.
The AI decides which ones to use and when — no schedule, no stale cache.

Tools available
---------------
  search_web        — DuckDuckGo web search (free, no API key required)
  get_live_odds     — Live betting lines from Action Network
  get_injury_news   — Injury / lineup updates from ESPN + RotoWire
  get_sports_news   — Latest headlines from ESPN

Each tool function takes plain Python args and returns a plain string.
The agent loop in conversation.py handles dispatching and result injection.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from core.logger import get_logger

log = get_logger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── OpenAI tool definitions (passed in every API call) ────────────────────────

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Search the live web for any sports betting information — "
                "injuries, predictions, line analysis, expert picks, news, trends, "
                "or anything else. Use this whenever you need current information "
                "that might not be in your training data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query. Be specific — e.g. 'Lakers vs Warriors injury report tonight' or 'NFL Week 5 best bets experts'.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_live_odds",
            "description": (
                "Fetch live betting lines, spreads, totals, and moneylines for today's games. "
                "Also returns public betting percentages. Use this to check current lines "
                "before analysing any bet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sport": {
                        "type": "string",
                        "description": "Sport code: nfl, nba, mlb, nhl, ncaab, ncaaf, soccer",
                        "enum": ["nfl", "nba", "mlb", "nhl", "ncaab", "ncaaf", "soccer"],
                    }
                },
                "required": ["sport"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_injury_news",
            "description": (
                "Get the latest injury reports, lineup changes, and player availability "
                "updates for a sport. Critical for evaluating bets — always check this "
                "before recommending a bet involving key players."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sport": {
                        "type": "string",
                        "description": "Sport name: nfl, nba, mlb, nhl",
                        "enum": ["nfl", "nba", "mlb", "nhl"],
                    }
                },
                "required": ["sport"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sports_news",
            "description": (
                "Get the latest sports news headlines from ESPN. Use this for "
                "breaking news, trade rumors, suspensions, weather reports, "
                "or anything that could affect a game outcome."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sport": {
                        "type": "string",
                        "description": "Sport code: nfl, nba, mlb, nhl, soccer",
                        "enum": ["nfl", "nba", "mlb", "nhl", "soccer"],
                    }
                },
                "required": ["sport"],
            },
        },
    },
]


# ── Tool implementations ───────────────────────────────────────────────────────

def search_web(query: str) -> str:
    """
    Search the web via DuckDuckGo's instant-answer API.
    Falls back to the HTML search scrape if the instant API returns nothing.
    Free — no API key required.
    """
    log.info(f"[agent_tools] search_web: {query!r}")
    results: list[str] = []

    # ── Try DuckDuckGo Instant Answer API first ────────────────────────────
    try:
        r = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            headers=_HEADERS,
            timeout=10,
            follow_redirects=True,
        )
        if r.status_code == 200:
            data = r.json()
            abstract = (data.get("AbstractText") or "").strip()
            if abstract:
                results.append(f"Summary: {abstract}")
            for item in (data.get("RelatedTopics") or [])[:5]:
                text = (item.get("Text") or "").strip()
                if text:
                    results.append(f"• {text}")
    except Exception as exc:
        log.debug(f"[agent_tools] DDG instant API error: {exc}")

    # ── Try duckduckgo-search library if installed ─────────────────────────
    if not results:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                for hit in ddgs.text(query, max_results=6):
                    title = hit.get("title", "")
                    body  = hit.get("body", "")[:300]
                    href  = hit.get("href", "")
                    results.append(f"• {title}: {body} [{href}]")
        except ImportError:
            log.debug("[agent_tools] duckduckgo-search not installed")
        except Exception as exc:
            log.debug(f"[agent_tools] duckduckgo-search error: {exc}")

    # ── Fallback: ESPN search ──────────────────────────────────────────────
    if not results:
        try:
            r = httpx.get(
                "https://site.api.espn.com/apis/common/v3/search",
                params={"query": query, "limit": 5, "type": "article"},
                headers=_HEADERS,
                timeout=10,
            )
            if r.status_code == 200:
                hits = r.json().get("results", [])
                for hit in hits[:5]:
                    items = hit.get("contents", [])
                    for item in items[:3]:
                        headline = item.get("headline", "")
                        desc     = item.get("description", "")[:250]
                        if headline:
                            results.append(f"• {headline}: {desc}")
        except Exception as exc:
            log.debug(f"[agent_tools] ESPN search error: {exc}")

    if not results:
        return f"No web results found for: {query!r}. Try rephrasing the query."

    return f"Web search results for '{query}':\n" + "\n".join(results[:8])


def get_live_odds(sport: str) -> str:
    """
    Fetch today's live lines from Action Network's public API.
    Returns spread, total, ML, and public betting % for each game.
    """
    log.info(f"[agent_tools] get_live_odds: {sport}")
    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    try:
        url = (
            f"https://api.actionnetwork.com/web/v1/scoreboard/{sport}"
            f"?period=event&bookIds=15,30,76&date={today}"
        )
        r = httpx.get(url, headers=_HEADERS, timeout=12, follow_redirects=True)
        if r.status_code != 200:
            return f"Action Network returned HTTP {r.status_code} for {sport.upper()}."

        games = r.json().get("games", [])
        if not games:
            return f"No {sport.upper()} games found today ({today})."

        lines_out: list[str] = [
            f"Live {sport.upper()} lines ({datetime.now(timezone.utc).strftime('%H:%M UTC')}):"
        ]
        for game in games[:10]:
            home = game.get("home_team", {}).get("full_name", "TBD")
            away = game.get("away_team", {}).get("full_name", "TBD")
            start = game.get("start_time", "")

            spread = total = ml_home = ml_away = "N/A"
            raw_lines = game.get("lines", [])
            if raw_lines:
                best = raw_lines[0]
                spread  = best.get("spread",  "N/A")
                total   = best.get("total",   "N/A")
                ml_home = best.get("home_ml", "N/A")
                ml_away = best.get("away_ml", "N/A")

            consensus = game.get("consensus", {})
            away_pct  = consensus.get("away_ml", "?")
            home_pct  = consensus.get("home_ml", "?")

            lines_out.append(
                f"\n{away} @ {home}  [{start}]"
                f"\n  Spread: {spread}  |  Total: {total}"
                f"\n  ML: {away} {ml_away} / {home} {ml_home}"
                f"\n  Public money: {away_pct}% {away} / {home_pct}% {home}"
            )

        return "\n".join(lines_out)

    except Exception as exc:
        log.warning(f"[agent_tools] get_live_odds error: {exc}")
        return f"Could not fetch live odds for {sport.upper()}: {exc}"


def get_injury_news(sport: str) -> str:
    """
    Fetch injury and player availability updates from ESPN's public API.
    Falls back to RotoWire HTML scrape.
    """
    log.info(f"[agent_tools] get_injury_news: {sport}")
    results: list[str] = []

    # ── ESPN injuries endpoint ─────────────────────────────────────────────
    sport_map = {
        "nfl": ("football",   "nfl"),
        "nba": ("basketball", "nba"),
        "mlb": ("baseball",   "mlb"),
        "nhl": ("hockey",     "nhl"),
    }
    sport_path, league = sport_map.get(sport, ("football", "nfl"))

    try:
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports"
            f"/{sport_path}/{league}/injuries"
        )
        r = httpx.get(url, headers=_HEADERS, timeout=10, follow_redirects=True)
        if r.status_code == 200:
            data  = r.json()
            teams = data.get("injuries", [])
            for team_data in teams[:8]:
                team_name = team_data.get("team", {}).get("displayName", "Unknown")
                injuries  = team_data.get("injuries", [])
                for inj in injuries[:3]:
                    athlete = inj.get("athlete", {}).get("displayName", "Unknown")
                    status  = inj.get("status", "Unknown")
                    desc    = inj.get("details", {}).get("type", "")
                    results.append(f"• {team_name} — {athlete}: {status} ({desc})")
    except Exception as exc:
        log.debug(f"[agent_tools] ESPN injuries error: {exc}")

    # ── RotoWire scrape fallback ───────────────────────────────────────────
    if not results:
        roto_map = {
            "nfl": "https://www.rotowire.com/football/news.php",
            "nba": "https://www.rotowire.com/basketball/news.php",
            "mlb": "https://www.rotowire.com/baseball/news.php",
            "nhl": "https://www.rotowire.com/hockey/news.php",
        }
        url = roto_map.get(sport, "")
        if url:
            try:
                from bs4 import BeautifulSoup
                r = httpx.get(url, headers=_HEADERS, timeout=12, follow_redirects=True)
                if r.status_code == 200:
                    soup  = BeautifulSoup(r.text, "lxml")
                    items = soup.select(".news-update") or soup.select("article")
                    for item in items[:8]:
                        title_el = item.select_one(".news-update__title") or item.select_one("h4")
                        body_el  = item.select_one(".news-update__news") or item.select_one("p")
                        title    = title_el.get_text(strip=True) if title_el else ""
                        body     = body_el.get_text(strip=True)[:200] if body_el else ""
                        if title:
                            results.append(f"• {title}: {body}")
            except ImportError:
                pass
            except Exception as exc:
                log.debug(f"[agent_tools] RotoWire scrape error: {exc}")

    if not results:
        return f"No {sport.upper()} injury data found right now. Try searching the web for specific player names."

    header = f"{sport.upper()} Injury / Availability Report ({datetime.now(timezone.utc).strftime('%H:%M UTC')}):"
    return header + "\n" + "\n".join(results[:20])


def get_sports_news(sport: str) -> str:
    """
    Fetch the latest headlines from ESPN's public sports news API.
    """
    log.info(f"[agent_tools] get_sports_news: {sport}")

    sport_map = {
        "nfl":    ("football",   "nfl"),
        "nba":    ("basketball", "nba"),
        "mlb":    ("baseball",   "mlb"),
        "nhl":    ("hockey",     "nhl"),
        "soccer": ("soccer",     "eng.1"),
    }
    sport_path, league = sport_map.get(sport, ("football", "nfl"))

    try:
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports"
            f"/{sport_path}/{league}/news?limit=10"
        )
        r = httpx.get(url, headers=_HEADERS, timeout=10, follow_redirects=True)
        if r.status_code != 200:
            return f"ESPN returned HTTP {r.status_code} for {sport.upper()} news."

        articles = r.json().get("articles", [])
        if not articles:
            return f"No {sport.upper()} news found right now."

        lines = [
            f"{sport.upper()} News ({datetime.now(timezone.utc).strftime('%H:%M UTC')}):"
        ]
        for article in articles[:8]:
            headline = article.get("headline", "").strip()
            desc     = (article.get("description") or "").strip()[:200]
            if headline:
                lines.append(f"• {headline}" + (f": {desc}" if desc else ""))

        return "\n".join(lines)

    except Exception as exc:
        log.warning(f"[agent_tools] get_sports_news error: {exc}")
        return f"Could not fetch {sport.upper()} news: {exc}"


# ── Tool dispatcher ────────────────────────────────────────────────────────────

TOOL_FUNCTIONS: dict[str, Any] = {
    "search_web":      search_web,
    "get_live_odds":   get_live_odds,
    "get_injury_news": get_injury_news,
    "get_sports_news": get_sports_news,
}


def execute_tool(name: str, arguments: str | dict) -> str:
    """
    Dispatch a tool call from the AI and return the string result.

    Parameters
    ----------
    name      : Tool name (must match a key in TOOL_FUNCTIONS).
    arguments : JSON string or dict of arguments from the AI.
    """
    func = TOOL_FUNCTIONS.get(name)
    if not func:
        return f"Unknown tool: {name!r}"

    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        return func(**args)
    except Exception as exc:
        log.warning(f"[agent_tools] Tool {name!r} raised: {exc}")
        return f"Tool {name!r} failed: {exc}"
