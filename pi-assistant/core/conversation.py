"""
core/conversation.py — Agentic AI Conversation Manager
=======================================================
Manages the full lifecycle of a conversation turn with live tool access:

    User message → Call AI (with tools) → AI requests tools → Execute tools
    → Feed results back → AI calls more tools (if needed) → Final reply

The AI decides in real-time which tools to use and when. It can:
  - search_web        live DuckDuckGo search
  - get_live_odds     live lines from Action Network
  - get_injury_news   live injury/lineup updates from ESPN + RotoWire
  - get_sports_news   live headlines from ESPN

No schedules, no stale cache — the agent goes and gets exactly what it needs.

Max tool iterations per turn: 6 (prevents runaway loops).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from core.logger import get_logger

if TYPE_CHECKING:
    from api.ai_client import AIClient
    from core.memory import MemoryManager

log = get_logger(__name__)

# Maximum tool-call rounds per conversation turn (safety cap)
MAX_TOOL_ITERATIONS = 6

# ── System prompt ─────────────────────────────────────────────────────────────
BETTING_SYSTEM_PROMPT = """You are a sharp, real-time sports betting assistant running 24/7 on a personal Raspberry Pi.

You have LIVE access to the internet through your tools. You are NOT limited to training data.
When a user asks about today's games, injuries, odds, or any current info — USE YOUR TOOLS.
Do not say "I don't have access to live data." You do. Call the appropriate tool and get it.

Tool usage rules:
- Always call get_live_odds before analysing any specific bet — get the actual current line.
- Always call get_injury_news before recommending a bet involving key players.
- Always call get_reddit_picks AND get_expert_picks when asked for best bets or recommendations — know what the community and experts are saying before forming your opinion.
- Always call get_bot_predictions when asked about a specific game — find out what other AI models and prediction bots are saying, then compare and contrast with your own analysis.
- Use search_web for anything not covered by the other tools: trends, weather, stats, specific player news, or when other tools return no data.
- You may call multiple tools in parallel in one turn — do this freely, don't wait.
- Never guess lines, odds, injury status, or what other systems think — look them up.
- When you have data from multiple sources (Reddit, experts, bots, odds), synthesise them: note where they agree, where they diverge, and why your recommendation follows or fades the consensus.

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
- Keep responses concise — the user is often checking from a phone.
- Never encourage chasing losses or irresponsible gambling. Bankroll management is sacred.

Current date/time is provided at the start of each message."""


class ConversationManager:
    """
    Agentic conversation manager with live tool access.

    The AI calls tools as needed during each turn — fetching live odds,
    injuries, news, or web search results — then produces a final reply
    grounded in real current data.

    Parameters
    ----------
    ai_client       : Initialised AIClient instance.
    memory          : MemoryManager for history persistence.
    system_prompt   : Override the default betting system prompt.
    history_limit   : Maximum past turns to include per request (default 20).
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
        self.ai_client    = ai_client
        self.memory       = memory
        self.system_prompt = system_prompt
        self.history_limit = history_limit
        self.model        = model

        # Import tools lazily so this module stays importable even if
        # optional deps (beautifulsoup4, duckduckgo-search) aren't installed yet.
        from core.agent_tools import TOOL_DEFINITIONS, execute_tool
        self._tool_definitions = TOOL_DEFINITIONS
        self._execute_tool     = execute_tool

    # ── Public interface ───────────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        context: dict[str, Any] | None = None,
        plugin: str = "betting_assistant",
    ) -> str:
        """
        Process one conversation turn and return the assistant's reply.

        Runs the agentic tool loop:
          1. Send messages + tool definitions to the AI.
          2. If the AI returns tool calls, execute them and feed results back.
          3. Repeat until the AI produces a text reply (or MAX_TOOL_ITERATIONS).

        Parameters
        ----------
        user_message : The user's raw input text.
        context      : Optional structured data injected into the system prompt.
        plugin       : Plugin name for conversation log attribution.

        Returns
        -------
        str : The assistant's final reply text.
        """
        if not user_message.strip():
            return "I didn't catch that — what would you like to know?"

        log.info(f"[conversation] User: {user_message[:80]}{'...' if len(user_message) > 80 else ''}")

        # Build the initial message list
        messages = self._build_messages(user_message, context)

        # ── Agentic tool loop ──────────────────────────────────────────────────
        reply = ""
        tools_used: list[str] = []

        for iteration in range(MAX_TOOL_ITERATIONS):
            try:
                result = self.ai_client.chat_messages(
                    messages,
                    model=self.model,
                    tools=self._tool_definitions,
                )
            except Exception as exc:
                log.exception("AI client error during conversation turn")
                return (
                    f"I ran into an error reaching the AI model: {exc}. "
                    "Check your API key and connection settings."
                )

            # ── Plain text reply — we're done ──────────────────────────────────
            if isinstance(result, str):
                reply = result
                break

            # ── Tool calls — execute each one and loop back ────────────────────
            if isinstance(result, list) and result:
                # The raw assistant message (with tool_calls) must be in history
                raw_msg = result[0].get("_raw_message")
                if raw_msg:
                    messages.append(raw_msg)

                for call in result:
                    tool_name = call["name"]
                    tool_args = call["arguments"]
                    tools_used.append(tool_name)

                    log.info(f"[conversation] Tool call: {tool_name}({tool_args})")
                    tool_result = self._execute_tool(tool_name, tool_args)
                    log.info(f"[conversation] Tool result: {tool_result[:120]}…")

                    # Feed the tool result back as a tool message
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": call["id"],
                        "name":         tool_name,
                        "content":      tool_result,
                    })
            else:
                # Unexpected — break to avoid infinite loop
                log.warning(f"[conversation] Unexpected AI result type: {type(result)}")
                reply = "Something went wrong — please try again."
                break
        else:
            # Hit the iteration cap — ask the AI for a final answer with what it has
            log.warning(f"[conversation] Hit MAX_TOOL_ITERATIONS ({MAX_TOOL_ITERATIONS})")
            try:
                messages.append({
                    "role":    "user",
                    "content": "Please give me your best answer based on the data you've gathered so far.",
                })
                final = self.ai_client.chat_messages(messages, model=self.model)
                reply = final if isinstance(final, str) else "Could not generate a final response."
            except Exception:
                reply = "Reached the tool-use limit — please try a more specific question."

        if tools_used:
            log.info(f"[conversation] Tools used this turn: {', '.join(tools_used)}")

        # Persist both sides of the conversation
        self.memory.log_message("user",      user_message, plugin=plugin)
        self.memory.log_message("assistant", reply,        plugin=plugin)

        log.info(f"[conversation] Assistant: {reply[:80]}{'...' if len(reply) > 80 else ''}")
        return reply

    def get_history_for_display(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent conversation history for the dashboard UI."""
        return self.memory.get_history(limit=limit, plugin=None)

    def clear(self) -> int:
        """Wipe conversation history. Returns number of entries deleted."""
        count = self.memory.clear_history()
        log.info(f"[conversation] History cleared ({count} entries)")
        return count

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_messages(
        self,
        user_message: str,
        context: dict[str, Any] | None,
    ) -> list[dict]:
        """
        Assemble the initial message list for a turn:

            [system_prompt] + [history turns] + [current user message]
        """
        now = datetime.now(timezone.utc).strftime("%A %d %B %Y, %H:%M UTC")

        system_parts = [self.system_prompt, f"\nCurrent date/time: {now}"]
        if context:
            system_parts.append(self._format_context(context))

        messages: list[dict] = [
            {"role": "system", "content": "\n".join(system_parts)}
        ]

        history = self.memory.get_history(limit=self.history_limit)
        for entry in history:
            if entry["role"] in ("user", "assistant"):
                messages.append({"role": entry["role"], "content": entry["content"]})

        messages.append({"role": "user", "content": user_message})
        return messages

    @staticmethod
    def _format_context(context: dict[str, Any]) -> str:
        """Format a context dict into a system-prompt block."""
        lines = ["", "--- Current context ---"]
        for key, value in context.items():
            label = key.replace("_", " ").title()
            lines.append(f"{label}: {value}")
        lines.append("-----------------------")
        return "\n".join(lines)
