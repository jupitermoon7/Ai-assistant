"""
plugins/betting_assistant/skill.py — Sports Betting Assistant Plugin
=====================================================================
The primary skill of the assistant.  Wires the ConversationManager
into the command system and adds betting-specific commands.

Commands registered
-------------------
chat            — Send a message and get an AI reply (main conversation loop)
analyze_bet     — Analyse a specific bet with structured input
track_bet       — Log a bet to long-term memory for tracking
bankroll        — View or update bankroll state
bets_today      — List all bets tracked for today
clear_history   — Clear the conversation history
conv_status     — Check AI connectivity and conversation stats

Scheduled jobs
--------------
None by default — uncomment the scheduled digest in setup() once you
have a sports data API connected (see api/sports_data.py stub).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.logger import get_logger
from core.plugin_manager import BasePlugin

log = get_logger(__name__)


class BettingAssistant(BasePlugin):
    """
    Sports betting AI assistant plugin.

    Owns the conversation loop and all betting-related commands.
    The ConversationManager is initialised in setup() once the assistant
    and its subsystems are fully available.
    """

    plugin_name = "Betting Assistant"
    plugin_version = "0.1.0"
    plugin_description = "Sports betting AI — conversation loop, bet tracking, bankroll management"

    def setup(self) -> None:
        """
        Initialise the ConversationManager and load persisted bankroll state.

        Called once when the assistant loads this plugin.
        """
        log.info(f"[{self.name}] Setting up Betting Assistant…")

        # ── Lazy imports to avoid circular deps at module load time ───────────
        from api.ai_client import AIClient
        from core.config import config
        from core.conversation import ConversationManager

        # Build the AI client from config / .env
        ai_client = AIClient.from_config(config)

        # Initialise the conversation manager (this is the core of the plugin)
        self._conv = ConversationManager(
            ai_client=ai_client,
            memory=self.assistant.memory,
            history_limit=self.config.get("history_limit", 20),
        )

        # Persist plugin load time
        self.assistant.memory.store(
            "betting_assistant.last_loaded",
            datetime.now(timezone.utc).isoformat(),
            category="system",
        )

        # Ensure bankroll entry exists (defaults to 0 until user sets it)
        if self.assistant.memory.recall("bankroll.current") is None:
            self.assistant.memory.store("bankroll.current", 0.0, category="bankroll")
        if self.assistant.memory.recall("bankroll.initial") is None:
            self.assistant.memory.store("bankroll.initial", 0.0, category="bankroll")

        log.info(f"[{self.name}] Ready — conversation loop active")

    def teardown(self) -> None:
        log.info(f"[{self.name}] Torn down")

    # ── Command registry ───────────────────────────────────────────────────────

    def get_commands(self) -> dict[str, Any]:
        return {
            "chat":          self.handle_chat,
            "analyze_bet":   self.handle_analyze_bet,
            "track_bet":     self.handle_track_bet,
            "bankroll":      self.handle_bankroll,
            "bets_today":    self.handle_bets_today,
            "clear_history": self.handle_clear_history,
            "conv_status":   self.handle_conv_status,
        }

    # ── Command handlers ───────────────────────────────────────────────────────

    def handle_chat(self, message: str = "", **_: Any) -> dict[str, Any]:
        """
        Main conversation entry point.

        Send any message to the AI and receive a sports betting–aware reply.

        Parameters
        ----------
        message : The user's text input.

        Returns
        -------
        {"reply": str, "ts": str}
        """
        if not message:
            return {"error": "message is required"}

        # Build context block from live memory state
        context = self._build_context()

        reply = self._conv.chat(
            user_message=message,
            context=context,
            plugin=self.name,
        )
        return {
            "reply": reply,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    def handle_analyze_bet(
        self,
        sport: str = "",
        game: str = "",
        bet_type: str = "",
        line: str = "",
        odds: str = "",
        stake: float = 0.0,
        notes: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """
        Analyse a specific bet with structured input.

        The structured fields are formatted into a natural-language question
        sent to the AI, giving it precise context for a better analysis.

        Parameters
        ----------
        sport    : Sport name, e.g. "NBA", "NFL", "Soccer - EPL".
        game     : Teams / matchup, e.g. "Lakers vs Warriors".
        bet_type : "spread" | "moneyline" | "total" | "prop" | "parlay" | etc.
        line     : The line/number, e.g. "-4.5", "Over 221.5".
        odds     : American odds, e.g. "-110", "+145".
        stake    : Amount you're considering wagering.
        notes    : Any extra context (injuries, weather, trends, etc.).

        Returns
        -------
        dict with "analysis" (AI text) and the input parameters echoed back.
        """
        if not game:
            return {"error": "game is required for bet analysis"}

        # Format a precise analytical prompt
        prompt_parts = [f"Analyse this bet for me:"]
        if sport:    prompt_parts.append(f"Sport: {sport}")
        if game:     prompt_parts.append(f"Game: {game}")
        if bet_type: prompt_parts.append(f"Bet type: {bet_type}")
        if line:     prompt_parts.append(f"Line: {line}")
        if odds:     prompt_parts.append(f"Odds: {odds}")
        if stake:    prompt_parts.append(f"Considering staking: ${stake:.2f}")
        if notes:    prompt_parts.append(f"Additional context: {notes}")
        prompt_parts.append(
            "\nGive me: (1) your assessment of the value, "
            "(2) key factors for and against, "
            "(3) a clear recommendation with reasoning."
        )

        prompt = "\n".join(prompt_parts)
        context = self._build_context()
        if sport:
            context["sport_focus"] = sport
        if game:
            context["game"] = game

        analysis = self._conv.chat(
            user_message=prompt,
            context=context,
            plugin=self.name,
        )

        return {
            "analysis": analysis,
            "input": {
                "sport": sport, "game": game, "bet_type": bet_type,
                "line": line, "odds": odds, "stake": stake,
            },
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    def handle_track_bet(
        self,
        sport: str = "",
        game: str = "",
        bet_type: str = "",
        line: str = "",
        odds: str = "",
        stake: float = 0.0,
        result: str = "pending",
        notes: str = "",
        **_: Any,
    ) -> dict[str, Any]:
        """
        Log a bet to long-term memory for tracking.

        Parameters
        ----------
        sport    : Sport name.
        game     : Teams / matchup.
        bet_type : Type of bet.
        line     : Line or selection.
        odds     : American odds string.
        stake    : Dollar amount wagered.
        result   : "pending" | "win" | "loss" | "push" | "void".
        notes    : Free text notes.

        Returns
        -------
        dict with "bet_id" (memory key), "message" (confirmation text).
        """
        if not game:
            return {"error": "game is required to track a bet"}

        now = datetime.now(timezone.utc)
        bet_id = f"bet.{now.strftime('%Y%m%d_%H%M%S')}"

        bet_record = {
            "id":       bet_id,
            "ts":       now.isoformat(),
            "sport":    sport,
            "game":     game,
            "bet_type": bet_type,
            "line":     line,
            "odds":     odds,
            "stake":    stake,
            "result":   result,
            "notes":    notes,
        }

        self.assistant.memory.store(bet_id, bet_record, category="bet")

        # Deduct stake from bankroll if it's set and bet is pending
        if stake > 0 and result == "pending":
            current = self.assistant.memory.recall("bankroll.current", 0.0) or 0.0
            new_balance = current - stake
            self.assistant.memory.store("bankroll.current", new_balance, category="bankroll")

        log.info(f"[{self.name}] Bet tracked: {bet_id} — {game} {bet_type} {line}")

        return {
            "bet_id":  bet_id,
            "message": f"Bet tracked: {game} | {bet_type} {line} @ {odds} | ${stake:.2f} | {result}",
            "record":  bet_record,
        }

    def handle_bankroll(
        self,
        action: str = "view",
        amount: float = 0.0,
        **_: Any,
    ) -> dict[str, Any]:
        """
        View or update bankroll state.

        Parameters
        ----------
        action : "view" | "set" | "add" | "subtract"
        amount : Amount for set/add/subtract actions.

        Returns
        -------
        dict with current bankroll state.
        """
        current = self.assistant.memory.recall("bankroll.current", 0.0) or 0.0
        initial = self.assistant.memory.recall("bankroll.initial", 0.0) or 0.0

        if action == "set":
            self.assistant.memory.store("bankroll.current", amount, category="bankroll")
            self.assistant.memory.store("bankroll.initial", amount, category="bankroll")
            current = amount
            initial = amount
        elif action == "add":
            current += amount
            self.assistant.memory.store("bankroll.current", current, category="bankroll")
        elif action == "subtract":
            current -= amount
            self.assistant.memory.store("bankroll.current", current, category="bankroll")
        elif action == "view":
            pass
        else:
            return {"error": f"Unknown action {action!r}. Use: view, set, add, subtract"}

        roi = ((current - initial) / initial * 100) if initial > 0 else 0.0

        return {
            "current":  round(current, 2),
            "initial":  round(initial, 2),
            "pnl":      round(current - initial, 2),
            "roi_pct":  round(roi, 2),
            "message":  f"Bankroll: ${current:.2f} (ROI: {roi:+.1f}%)",
        }

    def handle_bets_today(self, **_: Any) -> dict[str, Any]:
        """
        List all bets tracked today (UTC date).

        Returns
        -------
        dict with "bets" list and summary counts.
        """
        today_prefix = f"bet.{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        all_bets = self.assistant.memory.list_memories(category="bet", limit=200)

        today_bets = [
            b for b in all_bets
            if b["key"].startswith(today_prefix)
        ]

        wins    = sum(1 for b in today_bets if b["value"].get("result") == "win")
        losses  = sum(1 for b in today_bets if b["value"].get("result") == "loss")
        pending = sum(1 for b in today_bets if b["value"].get("result") == "pending")
        staked  = sum(b["value"].get("stake", 0) for b in today_bets)

        return {
            "date":    datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "count":   len(today_bets),
            "wins":    wins,
            "losses":  losses,
            "pending": pending,
            "staked":  round(staked, 2),
            "bets":    [b["value"] for b in today_bets],
        }

    def handle_clear_history(self, **_: Any) -> dict[str, Any]:
        """Clear all conversation history (keeps bets and bankroll data)."""
        count = self._conv.clear()
        return {"cleared": count, "message": f"Conversation history cleared ({count} messages)."}

    def handle_conv_status(self, **_: Any) -> dict[str, Any]:
        """Return AI connectivity status and conversation stats."""
        ai_health = self._conv.ai_client.health_check()
        history = self.assistant.memory.get_history(limit=1)
        bankroll = self.handle_bankroll(action="view")
        bets = self.handle_bets_today()

        return {
            "ai":        ai_health,
            "messages":  len(self.assistant.memory.get_history(limit=1000)),
            "bankroll":  bankroll,
            "bets_today": bets["count"],
        }

    # ── Health check ───────────────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """Return plugin health including AI reachability."""
        try:
            ai_ok = self._conv.ai_client.health_check()
            status = "ok" if ai_ok.get("reachable") else "degraded"
            return {
                "status":  status,
                "plugin":  self.name,
                "version": self.plugin_version,
                "ai":      ai_ok,
            }
        except Exception as exc:
            return {"status": "error", "plugin": self.name, "error": str(exc)}

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_context(self) -> dict[str, Any]:
        """
        Assemble a context dict from live memory state.

        This is injected into every AI prompt so the model always knows
        the current bankroll and how many bets are active.
        """
        bankroll = self.assistant.memory.recall("bankroll.current", 0.0) or 0.0

        # Count pending bets
        all_bets = self.assistant.memory.list_memories(category="bet", limit=500)
        pending_bets = [b for b in all_bets if b["value"].get("result") == "pending"]

        context: dict[str, Any] = {}
        if bankroll > 0:
            context["bankroll"] = f"${bankroll:.2f}"
        if pending_bets:
            context["active_pending_bets"] = len(pending_bets)
            # Include the most recent 3 pending bets for context
            recent = pending_bets[:3]
            for i, b in enumerate(recent, 1):
                v = b["value"]
                context[f"pending_bet_{i}"] = (
                    f"{v.get('game','')} | {v.get('bet_type','')} {v.get('line','')} "
                    f"@ {v.get('odds','')} | ${v.get('stake',0):.2f}"
                )
        return context
