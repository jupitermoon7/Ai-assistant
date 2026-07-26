"""
core/agent_tools.py — Live Tool Implementations for the AI Agent
=================================================================
These are the real-world tools the AI can call during a conversation.
The AI decides which ones to use and when — no schedule, no stale cache.

Tools available
---------------
  search_web            — DuckDuckGo web search (free, no API key required)
  get_live_odds         — Live betting lines from Action Network
  get_injury_news       — Injury / lineup updates from ESPN + RotoWire
  get_sports_news       — Latest headlines from ESPN
  get_reddit_picks      — Community picks & bot posts from Reddit betting subs
  get_expert_picks      — Expert picks from Covers.com + Action Network experts
  get_bot_predictions   — AI/bot prediction aggregation from prediction sites

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


# ── Tool dispatcher ────────────────────────────────────────────────────────────

TOOL_FUNCTIONS: dict[str, Any] = {
    "search_web":          search_web,
    "get_live_odds":       get_live_odds,
    "get_injury_news":     get_injury_news,
    "get_sports_news":     get_sports_news,
    "get_reddit_picks":    get_reddit_picks,
    "get_expert_picks":    get_expert_picks,
    "get_bot_predictions": get_bot_predictions,
    "get_scores":          get_scores,
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
