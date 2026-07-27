"""
core/agent_tools.py — Live Tool Implementations for the AI Agent
=================================================================
These are the real-world tools the AI can call during a conversation.
The AI decides which ones to use and when — no schedule, no stale cache.

Tools available
---------------
  browse_url            — Fetch and read the full content of ANY URL on the web
  search_web            — DuckDuckGo web search (free, no API key required)
  get_live_odds         — Live betting lines from ESPN/DraftKings
  get_injury_news       — Injury / lineup updates from ESPN + RotoWire
  get_sports_news       — Latest headlines from ESPN
  get_reddit_picks      — Community picks & bot posts from Reddit betting subs
  get_expert_picks      — Expert picks from Covers.com + Action Network experts
  get_bot_predictions   — AI/bot prediction aggregation from prediction sites
  get_historical_stats  — Historical team/player stats, recent form, game logs
  get_standings         — Current standings, W/L records, playoff picture via ESPN
  research_and_analyze  — Multi-source structured research for any domain/topic

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
            "name": "browse_url",
            "description": (
                "Fetch and read the full text content of ANY URL on the web. "
                "Use this to read a specific article, stats page, forum thread, "
                "financial report, Wikipedia entry, odds site, or any other webpage. "
                "Works on any website — not limited to sports. "
                "Use search_web first to find relevant URLs, then browse_url to read them deeply."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to fetch (must start with http:// or https://)",
                    },
                    "goal": {
                        "type": "string",
                        "description": "What you're looking for on this page — helps focus the extraction. E.g. 'player hitting stats', 'ATS record last 10 games', 'quarterly earnings'.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Search the live web for any information — sports, finance, science, news, "
                "research, or any other topic. Returns titles, snippets, and URLs from the top results. "
                "Use this to find relevant pages, then use browse_url to read any of them in full. "
                "Always prefer this over training data for anything current or factual."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query. Be specific — e.g. 'Yankees ATS record last 10 games 2026' or 'NVDA earnings Q2 2026 results'.",
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
    {
        "type": "function",
        "function": {
            "name": "get_reddit_picks",
            "description": (
                "Scrape Reddit betting communities for today's top picks, hot takes, "
                "and bot-generated analysis. Hits r/sportsbook, r/sportsbetting, and "
                "sport-specific subs. Use this to see what the community and bots are "
                "backing — great for gauging public sentiment and finding contrarian angles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sport": {
                        "type": "string",
                        "description": "Sport to focus on: nfl, nba, mlb, nhl, soccer, or 'all' for everything",
                        "enum": ["nfl", "nba", "mlb", "nhl", "soccer", "all"],
                    }
                },
                "required": ["sport"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_expert_picks",
            "description": (
                "Fetch expert picks and consensus data from Covers.com and Action Network. "
                "These are picks from professional handicappers, not just public bettors. "
                "Use this to see which side the experts are on and compare against public money."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sport": {
                        "type": "string",
                        "description": "Sport code: nfl, nba, mlb, nhl",
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
            "name": "get_bot_predictions",
            "description": (
                "Search multiple AI and bot prediction sources for a specific game or sport. "
                "Pulls from prediction aggregator sites and searches for AI model picks. "
                "Use this when you want to know what prediction bots and AI systems are saying "
                "about a game — compare their outputs against your own analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Game or topic to find predictions for. E.g. 'Lakers vs Warriors prediction' or 'NFL Week 5 AI picks'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_scores",
            "description": (
                "Get live scores, final results, box scores, and standings for games today or recently completed. "
                "Use this for: checking if a game is in progress, finding the final score, "
                "looking up home runs hit today, checking which games are left today, or any "
                "question about actual game outcomes and stats."
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
    {
        "type": "function",
        "function": {
            "name": "get_historical_stats",
            "description": (
                "Retrieve historical performance data for a team or player from ESPN's API. "
                "Use this for PAST data: recent form (last 5-10 games), season stats, game logs, "
                "home/away splits, ATS (against the spread) records, and trend analysis. "
                "Prefer this over search_web when you need structured historical stats. "
                "Use search_web instead for breaking news or real-time updates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sport": {
                        "type": "string",
                        "description": "Sport code: nfl, nba, mlb, nhl",
                        "enum": ["nfl", "nba", "mlb", "nhl"],
                    },
                    "entity_type": {
                        "type": "string",
                        "description": "Whether you are looking up a team or a player.",
                        "enum": ["team", "player"],
                    },
                    "entity_name": {
                        "type": "string",
                        "description": "Full or common name of the team (e.g. 'Los Angeles Lakers', 'Chiefs') or player (e.g. 'LeBron James', 'Patrick Mahomes').",
                    },
                    "stat_type": {
                        "type": "string",
                        "description": (
                            "What kind of historical data to retrieve: "
                            "'recent_form' = last 5-10 game results and performance trend; "
                            "'season_stats' = full season statistics summary; "
                            "'game_log' = per-game results for the current season; "
                            "'splits' = home/away/conference/division splits."
                        ),
                        "enum": ["recent_form", "season_stats", "game_log", "splits"],
                    },
                },
                "required": ["sport", "entity_type", "entity_name", "stat_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_standings",
            "description": (
                "Get current league standings including W/L record, win percentage, streak, "
                "home/away record, and playoff positioning. Use for any question about where "
                "a team sits in the standings, playoff races, or league rankings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sport": {
                        "type": "string",
                        "description": "Sport code: nfl, nba, mlb, nhl",
                        "enum": ["nfl", "nba", "mlb", "nhl"],
                    },
                    "conference": {
                        "type": "string",
                        "description": "Optional filter: 'east', 'west', 'afc', 'nfc', or leave empty for full standings.",
                    },
                },
                "required": ["sport"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_and_analyze",
            "description": (
                "General-purpose structured research tool for ANY domain — science, math, finance, "
                "medicine, technology, personal decisions, current events, and more. "
                "Runs multiple targeted web searches, synthesises the results, and returns a "
                "structured brief: what is known, what is uncertain, key factors, and a "
                "confidence-weighted summary. Use for non-sports topics or when you need "
                "multi-source evidence synthesis rather than a single search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The subject area or domain (e.g. 'personal finance', 'quantum computing', 'intermittent fasting').",
                    },
                    "question": {
                        "type": "string",
                        "description": "The specific question to answer or decision to inform (e.g. 'Is a 15-year vs 30-year mortgage better for me?').",
                    },
                },
                "required": ["topic", "question"],
            },
        },
    },
]


# ── Tool implementations ───────────────────────────────────────────────────────

def browse_url(url: str, goal: str = "") -> str:
    """
    Fetch and extract readable text from any URL on the web.
    Uses trafilatura for article extraction with BeautifulSoup fallback.
    Works on any website — news, stats, forums, financial reports, Wikipedia, etc.
    """
    log.info(f"[agent_tools] browse_url: {url!r} goal={goal!r}")

    if not url.startswith(("http://", "https://")):
        return f"Invalid URL: {url!r} — must start with http:// or https://"

    try:
        r = httpx.get(url, headers=_HEADERS, timeout=15, follow_redirects=True)
        if r.status_code != 200:
            return f"HTTP {r.status_code} fetching {url}"

        content_type = r.headers.get("content-type", "")

        # ── JSON response — return formatted ──────────────────────────────
        if "application/json" in content_type:
            try:
                return json.dumps(r.json(), indent=2)[:6000]
            except Exception:
                return r.text[:6000]

        # ── HTML — extract readable text ──────────────────────────────────
        raw_html = r.text

        # Try trafilatura first (best for articles)
        text: str | None = None
        try:
            import trafilatura
            text = trafilatura.extract(
                raw_html,
                include_tables=True,
                include_links=False,
                no_fallback=False,
            )
        except Exception as exc:
            log.debug(f"[agent_tools] trafilatura error: {exc}")

        # BeautifulSoup fallback
        if not text or len(text.strip()) < 100:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(raw_html, "lxml")
                # Remove noise tags
                for tag in soup(["script", "style", "nav", "footer", "header",
                                  "aside", "form", "button", "iframe", "noscript"]):
                    tag.decompose()
                # Prefer article/main content containers
                main = (soup.find("article") or soup.find("main") or
                        soup.find(id="content") or soup.find(class_="content") or
                        soup.find(class_="article") or soup.body)
                if main:
                    text = main.get_text(separator="\n", strip=True)
                else:
                    text = soup.get_text(separator="\n", strip=True)
                # Collapse blank lines
                lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
                text = "\n".join(lines)
            except Exception as exc:
                log.debug(f"[agent_tools] BeautifulSoup error: {exc}")

        if not text or len(text.strip()) < 50:
            return f"Could not extract readable content from {url}"

        # Trim to a useful but not overwhelming length (~6 000 chars)
        trimmed = text.strip()[:6000]
        if len(text.strip()) > 6000:
            trimmed += "\n\n[... content truncated — use browse_url again with a more specific goal if you need more]"

        goal_note = f" (looking for: {goal})" if goal else ""
        return f"Content from {url}{goal_note}:\n\n{trimmed}"

    except httpx.TimeoutException:
        return f"Timeout fetching {url} — site too slow or blocked."
    except Exception as exc:
        log.warning(f"[agent_tools] browse_url error: {exc}")
        return f"Could not fetch {url}: {exc}"


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
            from ddgs import DDGS
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
    Fetch today's live lines from ESPN's scoreboard API (DraftKings odds).
    Returns spread, total, ML, and game time for each game.
    """
    log.info(f"[agent_tools] get_live_odds: {sport}")

    sport_map = {
        "nfl":    ("football",   "nfl"),
        "nba":    ("basketball", "nba"),
        "mlb":    ("baseball",   "mlb"),
        "nhl":    ("hockey",     "nhl"),
        "soccer": ("soccer",     "eng.1"),
    }
    sport_path, league = sport_map.get(sport.lower(), ("baseball", "mlb"))

    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/{league}/scoreboard"
        r = httpx.get(url, headers=_HEADERS, timeout=12, follow_redirects=True)
        if r.status_code != 200:
            return f"ESPN odds returned HTTP {r.status_code} for {sport.upper()}."

        events = r.json().get("events", [])
        if not events:
            return f"No {sport.upper()} games found today — {sport.upper()} may not be in season."

        now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
        lines_out: list[str] = [f"Live {sport.upper()} odds via DraftKings ({now_str}):"]

        for event in events:
            name       = event.get("name", "Unknown game")
            comp       = (event.get("competitions") or [{}])[0]
            competitors = comp.get("competitors", [])
            status_obj = event.get("status", {})
            status_desc = status_obj.get("type", {}).get("shortDetail", "")

            # Team names from competitors
            home_name = away_name = ""
            for c in competitors:
                tname = c.get("team", {}).get("shortDisplayName", "")
                if c.get("homeAway") == "home":
                    home_name = tname
                else:
                    away_name = tname
            if not home_name or not away_name:
                home_name = away_name = name

            # Odds from ESPN/DraftKings
            odds_list = comp.get("odds", [])
            if odds_list:
                o        = odds_list[0]
                book     = o.get("provider", {}).get("name", "DraftKings")
                details  = o.get("details", "N/A")        # e.g. "SEA -136"
                total    = o.get("overUnder", "N/A")
                spread   = o.get("spread", "N/A")
                ml_obj   = o.get("moneyline") or o.get("moneyLine") or {}
                away_ml  = ((ml_obj.get("away") or {}).get("close") or {}).get("odds", "N/A")
                home_ml  = ((ml_obj.get("home") or {}).get("close") or {}).get("odds", "N/A")
                fav      = "away" if (o.get("awayTeamOdds") or {}).get("favorite") else "home"
                fav_name = away_name if fav == "away" else home_name

                lines_out.append(
                    f"\n{away_name} @ {home_name}  [{status_desc}]"
                    f"\n  Favorite: {fav_name} ({details})  |  O/U: {total}"
                    f"\n  Spread: {spread}  |  ML: {away_name} {away_ml} / {home_name} {home_ml}"
                    f"\n  Book: {book}"
                )
            else:
                lines_out.append(
                    f"\n{away_name} @ {home_name}  [{status_desc}]"
                    f"\n  Odds not yet available"
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


def get_reddit_picks(sport: str) -> str:
    """
    Pull today's top picks and bot posts from Reddit betting communities.
    Targets high-signal posts: pick threads, bot analysis, and daily discussion.
    """
    log.info(f"[agent_tools] get_reddit_picks: {sport}")

    sport_sub_map = {
        "nfl":    ["sportsbook", "sportsbetting", "nfl", "NFLpickem"],
        "nba":    ["sportsbook", "sportsbetting", "nba", "nbadraft"],
        "mlb":    ["sportsbook", "sportsbetting", "baseball"],
        "nhl":    ["sportsbook", "sportsbetting", "hockey"],
        "soccer": ["sportsbook", "sportsbetting", "soccer", "MLS"],
        "all":    ["sportsbook", "sportsbetting"],
    }
    subreddits = sport_sub_map.get(sport, ["sportsbook", "sportsbetting"])

    # Keywords that signal picks/analysis posts (including bot-style posts)
    pick_keywords = [
        "pick", "bet", "play", "lock", "fade", "sharp", "value",
        "prediction", "analysis", "best bet", "parlay", "line",
        "model", "algorithm", "bot", "ai pick", "system",
    ]

    results: list[str] = []

    for sub in subreddits:
        try:
            # Search for pick-related posts first
            search_url = f"https://www.reddit.com/r/{sub}/search.json"
            r = httpx.get(
                search_url,
                params={"q": f"{sport} picks bets today", "sort": "top", "t": "day", "limit": 10},
                headers={**_HEADERS, "User-Agent": "PiAssistant/1.0 (sports betting research)"},
                timeout=12,
                follow_redirects=True,
            )
            if r.status_code == 200:
                posts = r.json().get("data", {}).get("children", [])
                for post in posts[:5]:
                    p = post.get("data", {})
                    title = p.get("title", "").strip()
                    body  = (p.get("selftext") or "").strip()[:400]
                    score = p.get("score", 0)
                    author = p.get("author", "")
                    flair  = p.get("link_flair_text") or ""

                    # Prioritise bot posts and high-score pick posts
                    title_lower = title.lower()
                    if score < 5 and not any(kw in title_lower for kw in pick_keywords):
                        continue

                    author_tag = f"[BOT: {author}]" if "bot" in author.lower() else f"[u/{author}]"
                    flair_tag  = f" [{flair}]" if flair else ""
                    results.append(
                        f"• {title}{flair_tag} — {author_tag} 👍{score}"
                        + (f"\n  {body[:200]}" if body else "")
                    )
        except Exception as exc:
            log.debug(f"[agent_tools] Reddit picks r/{sub} error: {exc}")

        # Also grab hot posts from the sub directly
        try:
            hot_url = f"https://www.reddit.com/r/{sub}/hot.json?limit=15"
            r = httpx.get(
                hot_url,
                headers={**_HEADERS, "User-Agent": "PiAssistant/1.0 (sports betting research)"},
                timeout=12,
                follow_redirects=True,
            )
            if r.status_code == 200:
                posts = r.json().get("data", {}).get("children", [])
                for post in posts[:8]:
                    p = post.get("data", {})
                    title = p.get("title", "").strip()
                    score = p.get("score", 0)
                    author = p.get("author", "")
                    body   = (p.get("selftext") or "").strip()[:300]

                    title_lower = title.lower()
                    is_bot_post = "bot" in author.lower()
                    is_pick_post = any(kw in title_lower for kw in pick_keywords)

                    if score < 30 and not is_bot_post and not is_pick_post:
                        continue

                    author_tag = f"[BOT: {author}]" if is_bot_post else f"[u/{author}]"
                    results.append(
                        f"• {title} — {author_tag} 👍{score}"
                        + (f"\n  {body[:200]}" if body else "")
                    )
        except Exception as exc:
            log.debug(f"[agent_tools] Reddit hot r/{sub} error: {exc}")

        if len(results) >= 15:
            break

    if not results:
        return (
            f"No strong Reddit picks found for {sport.upper()} right now. "
            "Community may be quiet — try searching the web for picks instead."
        )

    header = (
        f"Reddit Community Picks — {sport.upper()} "
        f"({datetime.now(timezone.utc).strftime('%H:%M UTC')}):"
    )
    return header + "\n\n" + "\n\n".join(results[:12])


def get_expert_picks(sport: str) -> str:
    """
    Scrape expert consensus picks from Covers.com and Action Network.
    Returns professional handicapper picks, not just public money %.
    """
    log.info(f"[agent_tools] get_expert_picks: {sport}")
    results: list[str] = []

    # ── Action Network expert picks ────────────────────────────────────────
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = f"https://api.actionnetwork.com/web/v1/picks?sport={sport}&date={today}&type=expert"
        r = httpx.get(url, headers=_HEADERS, timeout=12, follow_redirects=True)
        if r.status_code == 200:
            picks = r.json().get("picks", [])
            for pick in picks[:10]:
                expert = pick.get("user", {}).get("name", "Expert")
                game   = pick.get("game", {})
                away   = game.get("away_team", {}).get("full_name", "Away")
                home   = game.get("home_team", {}).get("full_name", "Home")
                bet    = pick.get("pick_text", "")
                analysis = (pick.get("analysis") or "")[:250]
                results.append(
                    f"• {expert} on {away} @ {home}: **{bet}**"
                    + (f"\n  {analysis}" if analysis else "")
                )
    except Exception as exc:
        log.debug(f"[agent_tools] Action Network expert picks error: {exc}")

    # ── Covers.com consensus scrape ────────────────────────────────────────
    covers_sport_map = {
        "nfl": "https://www.covers.com/picks/nfl",
        "nba": "https://www.covers.com/picks/nba",
        "mlb": "https://www.covers.com/picks/mlb",
        "nhl": "https://www.covers.com/picks/nhl",
    }
    covers_url = covers_sport_map.get(sport, "")
    if covers_url:
        try:
            from bs4 import BeautifulSoup
            r = httpx.get(covers_url, headers=_HEADERS, timeout=14, follow_redirects=True)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml")

                # Covers pick cards
                pick_cards = (
                    soup.select(".cmg_picks_content")
                    or soup.select("[class*='pick-card']")
                    or soup.select("[class*='consensus']")
                    or soup.select("article")
                )
                for card in pick_cards[:8]:
                    title_el = (
                        card.select_one("h3") or card.select_one("h4")
                        or card.select_one("[class*='title']")
                    )
                    body_el = (
                        card.select_one("p") or card.select_one("[class*='desc']")
                    )
                    title = title_el.get_text(strip=True) if title_el else ""
                    body  = body_el.get_text(strip=True)[:250] if body_el else ""
                    if title and len(title) > 5:
                        results.append(
                            f"• [Covers] {title}"
                            + (f": {body}" if body else "")
                        )
        except ImportError:
            pass
        except Exception as exc:
            log.debug(f"[agent_tools] Covers.com picks error: {exc}")

    # ── Fallback: DuckDuckGo search for expert picks ───────────────────────
    if not results:
        try:
            from ddgs import DDGS
            query = f"{sport.upper()} expert picks today site:covers.com OR site:actionnetwork.com OR site:oddstrader.com"
            with DDGS() as ddgs:
                for hit in ddgs.text(query, max_results=5):
                    title = hit.get("title", "")
                    body  = hit.get("body", "")[:250]
                    href  = hit.get("href", "")
                    results.append(f"• {title}: {body} [{href}]")
        except Exception as exc:
            log.debug(f"[agent_tools] expert picks DDG fallback error: {exc}")

    if not results:
        return (
            f"No expert picks found for {sport.upper()} right now. "
            "Try get_bot_predictions or search_web with a specific game."
        )

    header = (
        f"Expert Picks — {sport.upper()} "
        f"({datetime.now(timezone.utc).strftime('%H:%M UTC')}):"
    )
    return header + "\n\n" + "\n\n".join(results[:12])


def get_bot_predictions(query: str) -> str:
    """
    Search multiple AI/bot prediction sources for a specific game or topic.
    Aggregates picks from prediction sites, AI models, and handicapping bots.
    Sources: Oddstrader, Dimers, PredictIt-style aggregators, AI pick sites.
    """
    log.info(f"[agent_tools] get_bot_predictions: {query!r}")
    results: list[str] = []

    # ── Targeted search across known AI/bot prediction sites ──────────────
    prediction_sites = [
        "site:dimers.com",
        "site:oddstrader.com",
        "site:pikdawgz.com",
        "site:wunderdog.com",
        "site:sportsprediction.com",
    ]

    try:
        from ddgs import DDGS
        # Search across multiple prediction sites at once
        site_query = f"{query} prediction picks " + " OR ".join(prediction_sites)
        with DDGS() as ddgs:
            for hit in ddgs.text(site_query, max_results=8):
                title = hit.get("title", "")
                body  = hit.get("body", "")[:350]
                href  = hit.get("href", "")
                source = href.split("/")[2] if "/" in href else href
                results.append(f"• [{source}] {title}: {body}")
    except ImportError:
        log.debug("[agent_tools] duckduckgo-search not available for bot_predictions")
    except Exception as exc:
        log.debug(f"[agent_tools] bot_predictions DDG search error: {exc}")

    # ── Dimers.com (AI-powered predictions, free) ──────────────────────────
    if not results:
        try:
            from bs4 import BeautifulSoup
            sport_guess = ""
            q_lower = query.lower()
            for s in ["nfl", "nba", "mlb", "nhl", "soccer", "ncaab", "ncaaf"]:
                if s in q_lower:
                    sport_guess = s
                    break

            if sport_guess:
                url = f"https://www.dimers.com/bet-hub/{sport_guess}/schedule"
                r = httpx.get(url, headers=_HEADERS, timeout=14, follow_redirects=True)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "lxml")
                    cards = soup.select("[class*='game-card']") or soup.select("[class*='matchup']")
                    for card in cards[:8]:
                        text = card.get_text(separator=" ", strip=True)[:300]
                        if text:
                            results.append(f"• [Dimers AI] {text}")
        except Exception as exc:
            log.debug(f"[agent_tools] Dimers scrape error: {exc}")

    # ── Broad fallback: general AI picks search ────────────────────────────
    if not results:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                for hit in ddgs.text(f"{query} AI prediction bot picks today", max_results=6):
                    title = hit.get("title", "")
                    body  = hit.get("body", "")[:300]
                    href  = hit.get("href", "")
                    results.append(f"• {title}: {body} [{href}]")
        except Exception as exc:
            log.debug(f"[agent_tools] bot_predictions broad fallback error: {exc}")

    if not results:
        return (
            f"No bot/AI predictions found for '{query}'. "
            "Try search_web with a more specific team name or matchup."
        )

    header = (
        f"AI & Bot Predictions for '{query}' "
        f"({datetime.now(timezone.utc).strftime('%H:%M UTC')}):"
    )
    return header + "\n\n" + "\n\n".join(results[:10])


def get_scores(sport: str) -> str:
    """
    Pull live scores, final results, and box score highlights from ESPN.
    Works for games in progress AND recently completed games.
    """
    log.info(f"[agent_tools] get_scores: {sport}")

    sport_map = {
        "nfl":    ("football",   "nfl"),
        "nba":    ("basketball", "nba"),
        "mlb":    ("baseball",   "mlb"),
        "nhl":    ("hockey",     "nhl"),
        "soccer": ("soccer",     "eng.1"),
    }
    sport_path, league = sport_map.get(sport, ("baseball", "mlb"))

    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/{league}/scoreboard"
        r = httpx.get(url, headers=_HEADERS, timeout=12, follow_redirects=True)
        if r.status_code != 200:
            return f"ESPN scoreboard returned HTTP {r.status_code} for {sport.upper()}."

        data   = r.json()
        events = data.get("events", [])
        if not events:
            return f"No {sport.upper()} games found on the scoreboard today."

        lines = [f"{sport.upper()} Scoreboard ({datetime.now(timezone.utc).strftime('%H:%M UTC')}):"]

        for event in events:
            name        = event.get("name", "Unknown game")
            status_obj  = event.get("status", {})
            status_type = status_obj.get("type", {})
            state       = status_type.get("state", "")        # pre / in / post
            status_desc = status_type.get("shortDetail", "")  # "Final", "7th Inning", etc.

            competitions = event.get("competitions", [{}])
            comp         = competitions[0] if competitions else {}
            competitors  = comp.get("competitors", [])

            score_line = name
            if len(competitors) >= 2:
                home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                home_name  = home.get("team", {}).get("shortDisplayName", "Home")
                away_name  = away.get("team", {}).get("shortDisplayName", "Away")
                home_score = home.get("score", "-")
                away_score = away.get("score", "-")
                winner_tag = ""
                if state == "post":
                    if home.get("winner"):
                        winner_tag = f" ← WIN"
                    elif away.get("winner"):
                        winner_tag = ""
                score_line = f"{away_name} {away_score}  @  {home_name} {home_score}{winner_tag}"

            # Box score highlights (HR, leaders, etc.) for baseball
            leaders: list[str] = []
            for cl in comp.get("competitionLeaders", []):
                cat   = cl.get("name", "")
                for leader_group in cl.get("leaders", []):
                    for leader in leader_group.get("leaders", [])[:2]:
                        athlete = leader.get("athlete", {}).get("displayName", "")
                        value   = leader.get("displayValue", "")
                        if athlete and value:
                            leaders.append(f"    {cat}: {athlete} — {value}")

            lines.append(f"\n{score_line}  [{status_desc}]")
            lines.extend(leaders[:4])

        return "\n".join(lines)

    except Exception as exc:
        log.warning(f"[agent_tools] get_scores error: {exc}")
        return f"Could not fetch {sport.upper()} scores: {exc}"


def get_historical_stats(
    sport: str,
    entity_type: str,
    entity_name: str,
    stat_type: str,
) -> str:
    """
    Retrieve historical stats for a team or player via ESPN's public API.
    Covers NFL, NBA, MLB, NHL — recent form, season stats, game logs, splits.
    """
    log.info(f"[agent_tools] get_historical_stats: {sport}/{entity_type}/{entity_name}/{stat_type}")

    sport_map = {
        "nfl": ("football",   "nfl"),
        "nba": ("basketball", "nba"),
        "mlb": ("baseball",   "mlb"),
        "nhl": ("hockey",     "nhl"),
    }
    sport_path, league = sport_map.get(sport.lower(), ("basketball", "nba"))
    base = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/{league}"

    results: list[str] = []
    entity_id: str | None = None

    # ── Step 1: Find the entity ID via ESPN search ─────────────────────────
    try:
        search_url = f"https://site.api.espn.com/apis/common/v3/search"
        r = httpx.get(
            search_url,
            params={"query": entity_name, "limit": 5, "sport": sport.lower()},
            headers=_HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            for result_group in data.get("results", []):
                for item in result_group.get("contents", []):
                    item_type = item.get("type", "")
                    if entity_type == "team" and item_type in ("team", "franchise"):
                        entity_id = str(item.get("id", ""))
                        break
                    elif entity_type == "player" and item_type in ("player", "athlete"):
                        entity_id = str(item.get("id", ""))
                        break
                if entity_id:
                    break
    except Exception as exc:
        log.debug(f"[agent_tools] ESPN search error for {entity_name}: {exc}")

    # ── Step 2: Fetch stats based on entity type and stat_type ────────────
    if entity_type == "team":
        # Try to get team schedule/results for recent_form and game_log
        team_url = f"{base}/teams"
        try:
            r = httpx.get(team_url, headers=_HEADERS, timeout=10)
            if r.status_code == 200:
                teams = r.json().get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
                for t in teams:
                    team_data = t.get("team", {})
                    name_check = team_data.get("displayName", "").lower()
                    short_check = team_data.get("shortDisplayName", "").lower()
                    abbr_check  = team_data.get("abbreviation", "").lower()
                    search_lower = entity_name.lower()
                    if (search_lower in name_check or search_lower in short_check
                            or abbr_check in search_lower or search_lower in abbr_check):
                        entity_id = str(team_data.get("id", ""))
                        break
        except Exception as exc:
            log.debug(f"[agent_tools] ESPN teams list error: {exc}")

        if entity_id:
            try:
                sched_url = f"{base}/teams/{entity_id}/schedule"
                r = httpx.get(sched_url, headers=_HEADERS, timeout=12)
                if r.status_code == 200:
                    sched_data = r.json()
                    team_name = (
                        sched_data.get("team", {}).get("displayName", entity_name)
                    )
                    events = sched_data.get("events", [])
                    completed = [e for e in events if e.get("competitions", [{}])[0]
                                 .get("status", {}).get("type", {}).get("completed", False)]

                    if stat_type in ("recent_form", "game_log"):
                        game_slice = completed[-10:] if stat_type == "recent_form" else completed
                        results.append(f"**{team_name} — {stat_type.replace('_', ' ').title()} ({sport.upper()})**")
                        wins = losses = 0
                        home_w = home_l = away_w = away_l = 0
                        for ev in game_slice:
                            comp = ev.get("competitions", [{}])[0]
                            comps = comp.get("competitors", [])
                            our_team = next(
                                (c for c in comps if str(c.get("id", "")) == entity_id),
                                None,
                            )
                            opp_team = next(
                                (c for c in comps if str(c.get("id", "")) != entity_id),
                                None,
                            )
                            if not our_team or not opp_team:
                                continue
                            our_score  = our_team.get("score", {}).get("value", "?")
                            opp_score  = opp_team.get("score", {}).get("value", "?")
                            opp_name   = opp_team.get("team", {}).get("shortDisplayName", "Opp")
                            home_away  = "vs" if our_team.get("homeAway") == "home" else "@"
                            won        = our_team.get("winner", False)
                            wl         = "W" if won else "L"
                            date_str   = ev.get("date", "")[:10]
                            if won:
                                wins += 1
                                if our_team.get("homeAway") == "home": home_w += 1
                                else: away_w += 1
                            else:
                                losses += 1
                                if our_team.get("homeAway") == "home": home_l += 1
                                else: away_l += 1
                            results.append(
                                f"  {date_str}  {wl}  {home_away} {opp_name}  "
                                f"{our_score}-{opp_score}"
                            )
                        if stat_type == "recent_form":
                            results.insert(
                                1,
                                f"  Record (last {len(game_slice)}): {wins}-{losses}  |  "
                                f"Home: {home_w}-{home_l}  Away: {away_w}-{away_l}",
                            )

                    elif stat_type == "splits":
                        results.append(f"**{team_name} — Home/Away Splits ({sport.upper()})**")
                        home_w = home_l = away_w = away_l = 0
                        for ev in completed:
                            comp  = ev.get("competitions", [{}])[0]
                            comps = comp.get("competitors", [])
                            our   = next((c for c in comps if str(c.get("id", "")) == entity_id), None)
                            if not our: continue
                            won = our.get("winner", False)
                            if our.get("homeAway") == "home":
                                if won: home_w += 1
                                else:   home_l += 1
                            else:
                                if won: away_w += 1
                                else:   away_l += 1
                        total = home_w + home_l + away_w + away_l
                        results.append(
                            f"  Overall: {home_w+away_w}-{home_l+away_l} ({total} games)\n"
                            f"  Home:    {home_w}-{home_l}\n"
                            f"  Away:    {away_w}-{away_l}"
                        )

                    elif stat_type == "season_stats":
                        # Season stats from team record
                        record_obj = sched_data.get("team", {}).get("record", {})
                        items_list = record_obj.get("items", [])
                        results.append(f"**{team_name} — Season Stats ({sport.upper()})**")
                        for record_item in items_list[:4]:
                            desc = record_item.get("description", "")
                            summary = record_item.get("summary", "")
                            if desc or summary:
                                results.append(f"  {desc}: {summary}")

            except Exception as exc:
                log.debug(f"[agent_tools] ESPN schedule fetch error: {exc}")

    elif entity_type == "player":
        # ── MLB: use the official MLB Stats API (most accurate) ────────────
        if sport.lower() == "mlb":
            try:
                sr = httpx.get(
                    "https://statsapi.mlb.com/api/v1/people/search",
                    params={"names": entity_name, "sportId": 1},
                    headers=_HEADERS, timeout=10,
                )
                mlb_id: str | None = None
                found_name = entity_name
                if sr.status_code == 200:
                    people = sr.json().get("people", [])
                    if people:
                        mlb_id     = str(people[0]["id"])
                        found_name = people[0].get("fullName", entity_name)

                if mlb_id:
                    if stat_type in ("season_stats",):
                        pr = httpx.get(
                            f"https://statsapi.mlb.com/api/v1/people/{mlb_id}/stats",
                            params={"stats": "season", "season": "2026",
                                    "group": "hitting,pitching"},
                            headers=_HEADERS, timeout=12,
                        )
                        if pr.status_code == 200:
                            results.append(f"**{found_name} — 2026 Season Stats (MLB)**")
                            for sg in pr.json().get("stats", []):
                                group   = sg.get("group", {}).get("displayName", "").title()
                                splits  = sg.get("splits", [])
                                if not splits:
                                    continue
                                stat_obj = splits[0].get("stat", {})
                                results.append(f"\n  [{group}]")
                                # Key stats only
                                hitting_keys  = ["gamesPlayed","avg","homeRuns","rbi","runs",
                                                  "hits","doubles","triples","stolenBases",
                                                  "baseOnBalls","strikeOuts","obp","slg","ops"]
                                pitching_keys = ["gamesPlayed","gamesStarted","wins","losses",
                                                  "era","strikeOuts","baseOnBalls","whip",
                                                  "inningsPitched","hits","homeRuns","saves"]
                                keys = pitching_keys if group.lower() == "pitching" else hitting_keys
                                for k in keys:
                                    v = stat_obj.get(k)
                                    if v not in (None, "", "-.--", ".---"):
                                        results.append(f"    {k}: {v}")

                    elif stat_type in ("game_log", "recent_form"):
                        gl = httpx.get(
                            f"https://statsapi.mlb.com/api/v1/people/{mlb_id}/stats",
                            params={"stats": "gameLog", "season": "2026",
                                    "group": "hitting"},
                            headers=_HEADERS, timeout=12,
                        )
                        if gl.status_code == 200:
                            results.append(f"**{found_name} — Recent Game Log (MLB, 2026)**")
                            all_splits = []
                            for sg in gl.json().get("stats", []):
                                all_splits.extend(sg.get("splits", []))
                            recent = all_splits[-10:] if stat_type == "recent_form" else all_splits[-20:]
                            for sp in recent:
                                date_str = sp.get("date", "")[:10]
                                opp_obj  = sp.get("opponent", {})
                                opp      = opp_obj.get("abbreviation", opp_obj.get("name", "?"))
                                summary  = sp.get("stat", {}).get("summary", "")
                                results.append(f"  {date_str}  vs {opp}:  {summary}")

            except Exception as exc:
                log.debug(f"[agent_tools] MLB Stats API error for {entity_name}: {exc}")

        # ── Other sports: ESPN sports core API ────────────────────────────
        if not results and entity_id:
            try:
                stats_url = (
                    f"https://sports.core.api.espn.com/v2/sports/{sport_path}"
                    f"/leagues/{league}/athletes/{entity_id}/statistics/0"
                )
                sr = httpx.get(stats_url, headers=_HEADERS, timeout=12)
                if sr.status_code == 200:
                    sdata = sr.json()
                    results.append(
                        f"**{entity_name} — {stat_type.replace('_', ' ').title()} ({sport.upper()})**"
                    )
                    for cat in sdata.get("splits", {}).get("categories", [])[:3]:
                        cat_name  = cat.get("displayName", "")
                        stat_list = cat.get("stats", cat.get("statistics", []))[:8]
                        if cat_name:
                            results.append(f"\n  [{cat_name}]")
                        for s in stat_list:
                            n = s.get("displayName", s.get("name", ""))
                            v = s.get("displayValue", str(s.get("value", "")))
                            if n and v:
                                results.append(f"    {n}: {v}")
            except Exception as exc:
                log.debug(f"[agent_tools] ESPN core stats error for {entity_name}: {exc}")

    # ── Fallback: web search ───────────────────────────────────────────────
    if not results:
        log.info(f"[agent_tools] ESPN historical stats fallback to web search for {entity_name}")
        query = f"{entity_name} {sport.upper()} {stat_type.replace('_', ' ')} stats 2024 2025"
        return search_web(query)

    return "\n".join(results)


def get_standings(sport: str, conference: str = "") -> str:
    """
    Fetch current league standings from ESPN's public API.
    Returns W/L, win %, streak, home/away record, and playoff positioning.
    """
    log.info(f"[agent_tools] get_standings: {sport} conference={conference!r}")

    sport_map = {
        "nfl": ("football",   "nfl"),
        "nba": ("basketball", "nba"),
        "mlb": ("baseball",   "mlb"),
        "nhl": ("hockey",     "nhl"),
    }
    sport_path, league = sport_map.get(sport.lower(), ("basketball", "nba"))

    try:
        url = (
            f"https://site.api.espn.com/apis/v2/sports/{sport_path}/{league}/standings"
        )
        r = httpx.get(url, headers=_HEADERS, timeout=12, follow_redirects=True)
        if r.status_code != 200:
            # Try alternate standings URL
            url2 = (
                f"https://site.web.api.espn.com/apis/v2/sports/{sport_path}/{league}/standings"
            )
            r = httpx.get(url2, headers=_HEADERS, timeout=12, follow_redirects=True)

        if r.status_code != 200:
            raise ValueError(f"HTTP {r.status_code}")

        data = r.json()
        lines: list[str] = [
            f"**{sport.upper()} Standings ({datetime.now(timezone.utc).strftime('%b %d %Y')})**"
        ]

        # ESPN standings structure varies by sport
        children = data.get("children", []) or data.get("standings", {}).get("entries", [])

        if not children:
            # Try flat entries
            entries = data.get("standings", {}).get("entries", [])
            if entries:
                children = [{"name": sport.upper(), "standings": {"entries": entries}}]

        conf_filter = conference.lower().strip() if conference else ""

        for group in children:
            group_name = group.get("name", "") or group.get("abbreviation", "")

            # Apply conference filter
            if conf_filter:
                gn_lower = group_name.lower()
                if conf_filter not in gn_lower:
                    # Check abbreviation
                    if conf_filter not in group.get("abbreviation", "").lower():
                        continue

            lines.append(f"\n**{group_name}**")

            # Some groups have sub-groups (e.g. divisions within conference)
            sub_children = group.get("children", [])
            entry_sources = sub_children if sub_children else [group]

            for sub in entry_sources:
                sub_name = sub.get("name", "")
                if sub_name and sub_name != group_name:
                    lines.append(f"  [{sub_name}]")
                entries = (
                    sub.get("standings", {}).get("entries", [])
                    or sub.get("entries", [])
                )
                for entry in entries:
                    team = entry.get("team", {})
                    team_name = team.get("shortDisplayName", team.get("displayName", "?"))
                    stats_raw = entry.get("stats", [])
                    stat_map: dict[str, str] = {}
                    for s in stats_raw:
                        k = s.get("name", s.get("abbreviation", ""))
                        v = s.get("displayValue", str(s.get("value", "")))
                        stat_map[k] = v

                    # Build a readable line with common stats
                    w   = stat_map.get("wins",       stat_map.get("W",   "?"))
                    l   = stat_map.get("losses",     stat_map.get("L",   "?"))
                    pct = stat_map.get("winPercent", stat_map.get("PCT", ""))
                    str_ = stat_map.get("streak",    stat_map.get("streakCode", ""))
                    gb  = stat_map.get("gamesBehind", stat_map.get("GB", ""))
                    hw  = stat_map.get("homeWins",   "")
                    hl  = stat_map.get("homeLosses", "")
                    aw  = stat_map.get("awayWins",   "")
                    al  = stat_map.get("awayLosses", "")
                    playoff = stat_map.get("playoffSeed", stat_map.get("seed", ""))

                    parts = [f"  {team_name:<22} {w}-{l}"]
                    if pct:     parts.append(f"  .{pct}" if not pct.startswith(".") else f"  {pct}")
                    if gb:      parts.append(f"  GB: {gb}")
                    if str_:    parts.append(f"  Streak: {str_}")
                    if hw and hl: parts.append(f"  Home: {hw}-{hl}")
                    if aw and al: parts.append(f"  Away: {aw}-{al}")
                    if playoff: parts.append(f"  #{playoff}")
                    lines.append("".join(parts))

        if len(lines) <= 1:
            # Fallback to web search
            query = f"{sport.upper()} standings {conference} current season"
            return search_web(query)

        return "\n".join(lines)

    except Exception as exc:
        log.warning(f"[agent_tools] get_standings error: {exc}")
        query = f"{sport.upper()} standings {conference} current season"
        return search_web(query)


def research_and_analyze(topic: str, question: str) -> str:
    """
    Multi-source structured research for any domain.
    Runs 3 targeted DuckDuckGo searches, synthesises the results, and
    returns a structured brief: what is known, uncertainties, key factors,
    and a confidence-weighted summary.
    """
    log.info(f"[agent_tools] research_and_analyze: topic={topic!r} question={question!r}")

    # Build three targeted queries from different angles
    queries = [
        f"{question} {topic}",
        f"{topic} evidence research data analysis",
        f"{question} pros cons factors consider",
    ]

    all_results: list[str] = []

    for q in queries:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                for hit in ddgs.text(q, max_results=4):
                    title  = hit.get("title", "").strip()
                    body   = hit.get("body", "").strip()[:400]
                    source = hit.get("href", "").split("/")[2] if "/" in hit.get("href", "") else ""
                    if title:
                        all_results.append(f"[{source}] {title}: {body}")
        except ImportError:
            # Fallback to DuckDuckGo instant API
            try:
                r = httpx.get(
                    "https://api.duckduckgo.com/",
                    params={"q": q, "format": "json", "no_html": "1"},
                    headers=_HEADERS,
                    timeout=10,
                    follow_redirects=True,
                )
                if r.status_code == 200:
                    d = r.json()
                    abstract = (d.get("AbstractText") or "").strip()
                    if abstract:
                        all_results.append(f"[DuckDuckGo] {abstract}")
                    for item in (d.get("RelatedTopics") or [])[:3]:
                        t = (item.get("Text") or "").strip()
                        if t:
                            all_results.append(f"• {t}")
            except Exception as exc:
                log.debug(f"[agent_tools] research DDG instant error: {exc}")
        except Exception as exc:
            log.debug(f"[agent_tools] research DDG search error for {q!r}: {exc}")

    if not all_results:
        return (
            f"No research results found for topic '{topic}' / question '{question}'. "
            "Try search_web with a more specific query."
        )

    # Deduplicate
    seen: set[str] = set()
    unique_results: list[str] = []
    for item in all_results:
        key = item[:80]
        if key not in seen:
            seen.add(key)
            unique_results.append(item)

    # Build structured brief
    now_str = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    header = (
        f"**Research Brief: {topic}**\n"
        f"**Question:** {question}\n"
        f"**Sources gathered:** {len(unique_results)}  |  {now_str}\n"
    )

    evidence_block = "\n**Evidence from sources:**\n" + "\n".join(
        f"  {i+1}. {r}" for i, r in enumerate(unique_results[:10])
    )

    guidance = (
        "\n\n**Instructions for the agent synthesising this:**\n"
        "Using only the evidence above, produce a structured analysis with:\n"
        "  • What is known / well-established\n"
        "  • What is uncertain or contested\n"
        "  • Key factors relevant to the question\n"
        "  • Confidence level (low / medium / high) with explicit reasoning\n"
        "  • Concrete recommendation or answer\n"
        "Do NOT add facts from training data that are not in the evidence above."
    )

    return header + evidence_block + guidance


# ── Tool dispatcher ────────────────────────────────────────────────────────────

TOOL_FUNCTIONS: dict[str, Any] = {
    "browse_url":            browse_url,
    "search_web":            search_web,
    "get_live_odds":         get_live_odds,
    "get_injury_news":       get_injury_news,
    "get_sports_news":       get_sports_news,
    "get_reddit_picks":      get_reddit_picks,
    "get_expert_picks":      get_expert_picks,
    "get_bot_predictions":   get_bot_predictions,
    "get_scores":            get_scores,
    "get_historical_stats":  get_historical_stats,
    "get_standings":         get_standings,
    "research_and_analyze":  research_and_analyze,
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
