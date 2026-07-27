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
BETTING_SYSTEM_PROMPT = """You are a sharp analytical assistant running 24/7 on a personal Raspberry Pi. Your primary domain is sports betting, but you handle ANY analytical question across finance, science, research, personal decisions, and more.

You have LIVE access to the internet through your tools. You are NOT limited to training data.
When a user asks about today's games, injuries, odds, or any current info — USE YOUR TOOLS.
Do not say "I don't have access to live data." You do. Call the appropriate tool and get it.

━━━ DECISION FRAMEWORK (apply to any analytical question) ━━━
Before answering, classify the question by timeframe, then call the right tools:

  PAST  → historical data, trends, records, "how did they do", season stats
           Tools: get_historical_stats (structured), search_web (news/context)

  PRESENT → live games, current odds, today's injuries, breaking news
           Tools: get_scores, get_live_odds, get_injury_news, get_sports_news

  FUTURE → predictions, projections, "who will win", "should I bet"
           Tools: get_live_odds + get_expert_picks + get_historical_stats (context)

For any analytical question, follow this reasoning chain:
  1. Identify timeframe (past / present / future)
  2. Call the appropriate tools — batch independent calls together
  3. List the key evidence gathered
  4. Weigh factors and flag uncertainties
  5. State a confidence level: Low / Medium / High + explicit reason
  6. Give a concrete recommendation with explicit reasoning

Short factual questions (e.g. "who plays tonight?") skip the full framework.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tool selection guide:
- PAST data / trends / records    → get_historical_stats (preferred over search_web for structured stats)
- Current standings               → get_standings
- Live scores / box scores        → get_scores
- Live lines / spreads / totals   → get_live_odds
- Injury / lineup questions       → get_injury_news
- Breaking news / trades          → get_sports_news
- Best bets / full pick analysis  → get_live_odds + get_expert_picks + get_historical_stats (together)
- Community / bot sentiment       → get_reddit_picks + get_bot_predictions (together)
- Non-sports research, any domain → research_and_analyze
- Anything else / breaking news   → search_web

Rules:
- Match tools to the question. Do NOT call all tools for every message — that is slow and wasteful.
- Call independent tools in one batch, not one at a time.
- If a tool returns no data, try search_web once with a specific query, then stop trying.
- Never loop searching for something that isn't there — give your best answer with what you have.
- When you have data from multiple sources, synthesise: note where they agree, where they diverge.

CRITICAL — NEVER hallucinate live sports facts:
- NEVER mention a team, player, game, or line unless it appeared in a tool result THIS turn.
- If get_scores shows today's slate and a team is not listed, that team is NOT playing today.
- Training data is WRONG about today's schedule, injuries, odds, and lines. Tool results are ALWAYS right.
- If you are unsure whether a fact came from a tool or your training, call the tool first.

Your role:
- Help the user find value bets, analyse lines, and manage their bankroll intelligently.
- Think like a professional sports bettor: focus on EV, line movement, CLV, and bankroll protection.
- Cover all major sports: NFL, NBA, MLB, NHL, soccer (EPL, Champions League, MLS), tennis, MMA/UFC.
- Know betting markets: moneyline, spread, totals, props, parlays, futures, live betting, alternate lines.
- Handle non-sports questions with the same structured rigor: finance, science, research, decisions.

How to respond:
- Be direct and specific. Give a recommendation with reasoning, not just "it depends".
- Quantify when possible: edge %, implied probability, fair line estimates, confidence level.
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
    extra_tools     : Additional tool definitions to inject (e.g. consult_* tools).
    extra_executor  : Callable(tool_name, args) → str | None for extra tools.
                      Return None if the tool_name is not handled; the base
                      executor is tried next.
    """

    def __init__(
        self,
        ai_client: "AIClient",
        memory: "MemoryManager",
        system_prompt: str = BETTING_SYSTEM_PROMPT,
        history_limit: int = 20,
        model: str | None = None,
        extra_tools: list[dict] | None = None,
        extra_executor: Any | None = None,
    ) -> None:
        self.ai_client     = ai_client
        self.memory        = memory
        self.system_prompt = system_prompt
        self.history_limit = history_limit
        self.model         = model

        # Import tools lazily so this module stays importable even if
        # optional deps (beautifulsoup4, duckduckgo-search) aren't installed yet.
        from core.agent_tools import TOOL_DEFINITIONS, execute_tool
        self._tool_definitions = TOOL_DEFINITIONS
        self._execute_tool     = execute_tool

        # Inter-agent consultation tools (injected after construction)
        self._extra_tools    = extra_tools or []
        self._extra_executor = extra_executor  # callable(name, args) → str | None

    def set_peer_tools(
        self,
        extra_tools: list[dict],
        extra_executor: Any,
    ) -> None:
        """Wire in peer-agent consultation tools after all agents are created."""
        self._extra_tools    = extra_tools
        self._extra_executor = extra_executor

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

        # Full tool set = base tools + any peer-agent consultation tools
        all_tools = self._tool_definitions + self._extra_tools

        reply = self._run_tool_loop(messages, all_tools)

        # Persist both sides of the conversation
        self.memory.log_message("user",      user_message, plugin=plugin)
        self.memory.log_message("assistant", reply,        plugin=plugin)

        log.info(f"[conversation] Assistant: {reply[:80]}{'...' if len(reply) > 80 else ''}")
        return reply

    def consult(self, question: str) -> str:
        """
        Lightweight single-purpose consultation — called by peer agents.

        Uses only the base external tools (no peer-consult tools) so there
        is NO risk of circular consultation loops. Results are NOT persisted
        to memory because this is an intermediate step, not a user turn.

        Returns the agent's answer as a plain string.
        """
        if not question.strip():
            return "(No question provided)"

        log.info(f"[conversation] [consult] Question: {question[:80]}{'...' if len(question) > 80 else ''}")

        now = datetime.now(timezone.utc).strftime("%A %d %B %Y, %H:%M UTC")
        messages = [
            {"role": "system", "content": f"{self.system_prompt}\nCurrent date/time: {now}"},
            {"role": "user",   "content": question},
        ]

        # Use ONLY base tools — no peer tools — prevents infinite recursion
        reply = self._run_tool_loop(messages, self._tool_definitions)
        log.info(f"[conversation] [consult] Reply: {reply[:80]}{'...' if len(reply) > 80 else ''}")
        return reply

    # ── Core tool loop (shared by chat + consult) ──────────────────────────────

    def _run_tool_loop(self, messages: list[dict], tools: list[dict]) -> str:
        """
        Run the agentic tool loop on the given message list.
        Returns the final reply string.
        """
        reply = ""
        tools_used: list[str] = []

        for _iteration in range(MAX_TOOL_ITERATIONS):
            try:
                result = self.ai_client.chat_messages(
                    messages,
                    model=self.model,
                    tools=tools,
                )
            except Exception as exc:
                log.exception("AI client error during conversation turn")
                return (
                    f"I ran into an error reaching the AI model: {exc}. "
                    "Check your API key and connection settings."
                )

            # Plain text reply — done
            if isinstance(result, str):
                reply = result
                break

            # Tool calls — execute each one and loop back
            if isinstance(result, list) and result:
                raw_msg = result[0].get("_raw_message")
                if raw_msg:
                    messages.append(raw_msg)

                for call in result:
                    tool_name = call["name"]
                    tool_args = call["arguments"]
                    # OpenAI returns arguments as a JSON-encoded string; parse it
                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except json.JSONDecodeError:
                            tool_args = {}
                    tools_used.append(tool_name)

                    log.info(f"[conversation] Tool call: {tool_name}({tool_args})")
                    tool_result = self._dispatch_tool(tool_name, tool_args)
                    log.info(f"[conversation] Tool result: {tool_result[:120]}…")

                    messages.append({
                        "role":         "tool",
                        "tool_call_id": call["id"],
                        "name":         tool_name,
                        "content":      tool_result,
                    })
            else:
                log.warning(f"[conversation] Unexpected AI result type: {type(result)}")
                reply = "Something went wrong — please try again."
                break
        else:
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

        return reply

    def _dispatch_tool(self, tool_name: str, tool_args: dict) -> str:
        """
        Execute a tool call. Tries extra_executor first (peer-agent tools),
        then falls back to the base tool executor.
        """
        if self._extra_executor:
            result = self._extra_executor(tool_name, tool_args)
            if result is not None:
                return result
        return self._execute_tool(tool_name, tool_args)

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
