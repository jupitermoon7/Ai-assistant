"""
core/conversation.py — AI Conversation Manager
================================================
Manages the full lifecycle of a conversation turn:

    User message → Build context → Call LLM → Store history → Return reply

Features
--------
- Sports betting–focused system prompt injected automatically on every turn.
- Pulls recent conversation history from long-term memory to give the AI
  continuity across sessions (even after restarts).
- Optional "context injection" dict lets plugins pass structured data into
  the prompt (live odds, bankroll state, upcoming games, etc.).
- Streaming-ready: the ``chat()`` method returns a full string now;
  swap ``_call_ai()`` for a streaming version when ready.
- Token budget: limits history length so long sessions don't hit context limits.

Usage
-----
    from core.conversation import ConversationManager

    conv = ConversationManager(ai_client=client, memory=memory)

    reply = conv.chat(
        user_message="Is Lakers -4.5 good value tonight?",
        context={"bankroll": 1000, "active_bets": 2},
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from core.logger import get_logger

if TYPE_CHECKING:
    from api.ai_client import AIClient
    from core.memory import MemoryManager

log = get_logger(__name__)

# ── Default system prompt ─────────────────────────────────────────────────────
# Guides the AI's persona for every conversation turn.
# Plugins can override this via ConversationManager.system_prompt.
BETTING_SYSTEM_PROMPT = """You are a sharp, analytical sports betting assistant running 24/7 on a personal Raspberry Pi.

Your role:
- Help the user find value bets, analyse lines, and manage their bankroll intelligently.
- Think like a professional sports bettor: focus on expected value (EV), line movement,
  closing line value (CLV), and bankroll protection — not just picking winners.
- Cover all major sports: NFL, NBA, MLB, NHL, soccer (EPL, Champions League, MLS),
  tennis, MMA/UFC, and others on request.
- Know betting markets: moneyline, spread, totals (over/under), props, parlays,
  futures, live in-game betting, alternate lines.
- Understand sportsbook concepts: juice/vig, line shopping, sharp vs. public money,
  steam moves, reverse line movement, and middling opportunities.

How to respond:
- Be direct and specific. Give a recommendation with reasoning, not just "it depends".
- Quantify when possible: edge percentage, implied probability, fair line estimates.
- Flag high-risk bets clearly (e.g. long parlays, bad value props).
- When the user asks to track a bet, confirm you've noted it.
- When context data is provided (bankroll, active bets, odds), incorporate it.
- Keep responses concise — the user is often checking from a phone.
- Never encourage chasing losses or irresponsible gambling. Bankroll management is sacred.

Current date/time is provided at the start of each message."""


class ConversationManager:
    """
    Manages conversation state and routes messages through the AI model.

    Parameters
    ----------
    ai_client       : Initialised AIClient instance.
    memory          : MemoryManager for history persistence.
    system_prompt   : Override the default betting system prompt.
    history_limit   : Maximum past turns to include in each request (default 20).
    model           : Override the default model for this conversation.
    """

    def __init__(
        self,
        ai_client: "AIClient",
        memory: "MemoryManager",
        system_prompt: str = BETTING_SYSTEM_PROMPT,
        history_limit: int = 20,
        model: str | None = None,
    ) -> None:
        self.ai_client = ai_client
        self.memory = memory
        self.system_prompt = system_prompt
        self.history_limit = history_limit
        self.model = model

    # ── Public interface ───────────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        context: dict[str, Any] | None = None,
        plugin: str = "betting_assistant",
    ) -> str:
        """
        Process one conversation turn and return the assistant's reply.

        Parameters
        ----------
        user_message : The user's raw input text.
        context      : Optional structured data injected into the system prompt
                       (e.g. {"bankroll": 1000, "sport": "NBA", "game": "Lakers vs Warriors"}).
        plugin       : Plugin name used for conversation log attribution.

        Returns
        -------
        str : The assistant's reply text.
        """
        if not user_message.strip():
            return "I didn't catch that — what would you like to know?"

        log.info(f"[conversation] User: {user_message[:80]}{'...' if len(user_message) > 80 else ''}")

        # 1. Build the full message list for this turn
        messages = self._build_messages(user_message, context)

        # 2. Call the AI
        try:
            reply = self.ai_client.chat_messages(messages, model=self.model)
        except Exception as exc:
            log.exception("AI client error during conversation turn")
            return (
                f"I ran into an error reaching the AI model: {exc}. "
                "Check your API key and connection settings."
            )

        # 3. Persist both sides of the conversation
        self.memory.log_message("user", user_message, plugin=plugin)
        self.memory.log_message("assistant", reply, plugin=plugin)

        log.info(f"[conversation] Assistant: {reply[:80]}{'...' if len(reply) > 80 else ''}")
        return reply

    def get_history_for_display(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Return recent conversation history formatted for the dashboard UI.

        Parameters
        ----------
        limit : Maximum number of turns to return.
        """
        return self.memory.get_history(limit=limit, plugin=None)

    def clear(self) -> int:
        """
        Wipe the conversation history.

        Returns the number of entries deleted.
        """
        count = self.memory.clear_history()
        log.info(f"[conversation] History cleared ({count} entries)")
        return count

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_messages(
        self,
        user_message: str,
        context: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        """
        Assemble the message list sent to the AI:

            [system_prompt] + [history turns] + [current user message]

        The system prompt is enriched with:
        - Current date/time (so the AI knows today's date for fixtures, etc.)
        - Any structured context passed by the plugin (bankroll, active bets, etc.)
        """
        now = datetime.now(timezone.utc).strftime("%A %d %B %Y, %H:%M UTC")

        # Build system content
        system_parts = [self.system_prompt, f"\nCurrent date/time: {now}"]
        if context:
            system_parts.append(self._format_context(context))

        messages: list[dict[str, str]] = [
            {"role": "system", "content": "\n".join(system_parts)}
        ]

        # Append recent history (capped to avoid context overflow)
        history = self.memory.get_history(limit=self.history_limit)
        for entry in history:
            if entry["role"] in ("user", "assistant"):
                messages.append({"role": entry["role"], "content": entry["content"]})

        # Current user turn
        messages.append({"role": "user", "content": user_message})

        return messages

    @staticmethod
    def _format_context(context: dict[str, Any]) -> str:
        """
        Format a context dict into a readable system-prompt block.

        Example output:
            --- Current context ---
            Bankroll: $1,200
            Active bets: 3
            Sport focus: NBA
            -----------------------
        """
        lines = ["", "--- Current context ---"]
        for key, value in context.items():
            label = key.replace("_", " ").title()
            lines.append(f"{label}: {value}")
        lines.append("-----------------------")
        return "\n".join(lines)
