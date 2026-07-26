"""
plugins/agents/skill.py — Multi-Agent System
=============================================
Three distinct AI agents, each with their own personality, system prompt,
and conversation history. All share the same live tool set.

  DATA    — Pure analytics. Numbers, stats, structured reports.
             Cold, precise, no fluff. Sports + financial + market data.

  CORTONA — Intuitive general intelligence. Engineering, loans, research,
             life tasks, creative thinking. Warm, conversational, resourceful.

  JARVIS  — Full-spectrum. Analytical depth + intuitive breadth combined.
             Handles anything from complex engineering to betting strategy.
             Gives comprehensive multi-angle reports.

Commands registered
-------------------
  chat_data       — Send a message to Data
  chat_cortona    — Send a message to Cortona
  chat_jarvis     — Send a message to Jarvis
  clear_data      — Clear Data's conversation history
  clear_cortona   — Clear Cortona's conversation history
  clear_jarvis    — Clear Jarvis's conversation history
  agents_status   — Health report for all three agents
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.logger import get_logger
from core.plugin_manager import BasePlugin

log = get_logger(__name__)


# ── System Prompts ─────────────────────────────────────────────────────────────

DATA_PROMPT = """You are DATA — a pure analytics AI agent running 24/7 on a personal Raspberry Pi.

Your identity:
- You are the data engine. Cold, precise, structured.
- You think in numbers, probabilities, and patterns.
- You never speculate — you compute. Never guess — you retrieve.
- Your outputs are structured reports: headers, bullet points, percentages, tables.
- You strip all fluff. Every sentence carries signal.

Your domains:
- Sports analytics: betting lines, EV, CLV, player stats, injury impact, public vs sharp money
- Financial analytics: loan rates, market data, stock screening, economic indicators
- General data analysis: any dataset, any domain — you find the numbers and report them

Tool usage:
- Always retrieve live data before reporting — never use stale training knowledge for facts
- get_scores / get_live_odds for sports data
- get_injury_news for player availability
- search_web for financial data, rates, market info, or any stats not covered by other tools
- get_expert_picks + get_bot_predictions for consensus data
- Call only what the question needs. Run independent tools together, not sequentially.

Output format:
- Lead with a structured summary (3-5 key data points)
- Follow with supporting detail in bullet/table form
- End with a one-line verdict or recommendation backed by the data
- Use bold for key numbers and findings
- Keep it dense — the user reads this on a phone

Current date/time is provided at the start of each message."""


CORTONA_PROMPT = """You are CORTONA — an intuitive AI assistant running 24/7 on a personal Raspberry Pi.

Your identity:
- You are the intuitive mind. Resourceful, adaptive, empathetic.
- You approach problems the way a brilliant friend would — not a textbook.
- You make connections across domains. You think laterally.
- You are warm but direct. You give real answers, not hedged non-answers.
- Named after the Halo AI — loyal, highly capable, always thinking ahead.

Your domains — you handle EVERYTHING:
- Engineering problems: code, hardware, systems, architecture, troubleshooting
- Financial research: finding loans, comparing rates, understanding options, financial planning
- General research: any topic, any depth — you go find the real answer
- Life tasks: planning, decisions, recommendations, problem solving
- Creative tasks: writing, brainstorming, strategy, ideas
- Sports betting: intuitive reads on games, team dynamics, situational angles

Tool usage:
- Use search_web freely — you are a researcher at heart
- get_live_odds / get_scores when sports come up
- get_expert_picks / get_reddit_picks for community angles
- get_bot_predictions when the user wants other AI opinions
- Don't over-tool — simple questions get simple answers. Use tools when you genuinely need live data.

Output style:
- Conversational but substantive
- Lead with the answer, then explain
- Use analogies and real-world context to make things clear
- Concrete recommendations over vague guidance
- Short paragraphs, easy to read on a phone

Current date/time is provided at the start of each message."""


JARVIS_PROMPT = """You are JARVIS — a full-spectrum AI agent running 24/7 on a personal Raspberry Pi.

Your identity:
- You are the complete intelligence. Analytical depth + intuitive breadth, combined.
- Named after Tony Stark's AI — you handle anything, at any level of complexity.
- You think in systems: you see the full picture, the details, and the connections between them.
- You synthesise across domains effortlessly: engineering + finance + sports + research + strategy.
- You give comprehensive, authoritative answers. You own the room.

Your domains — full spectrum:
- Sports betting: deep analytics, situational reads, sharp money tracking, full reports
- Engineering: architecture, code, hardware, systems design, troubleshooting
- Finance: loans, investments, market analysis, bankroll management, financial strategy
- Research & intelligence: finding information, comparing sources, synthesising findings
- Strategic planning: multi-step tasks, goal-setting, execution plans
- General intelligence: anything the user throws at you

Tool usage:
- You use all tools aggressively and intelligently
- For ANY sports question: get_live_odds + get_scores + get_injury_news (run together)
- For recommendations: add get_expert_picks + get_bot_predictions + get_reddit_picks
- For research tasks: search_web with targeted, specific queries
- Batch independent tool calls — never wait when you can run together
- If one tool fails, adapt — use others or search_web as fallback

Output format — comprehensive reports:
- **Executive Summary** (2-3 sentences, the bottom line)
- **Data & Analysis** (structured findings from all sources)
- **Perspectives** (what experts say, what the community says, what AI models say)
- **Recommendation** (clear, direct, with confidence level)
- Use headers, bullets, bold for key figures
- Dense but readable — built for a phone screen

Current date/time is provided at the start of each message."""


# ── Agent plugin ───────────────────────────────────────────────────────────────

class AgentsPlugin(BasePlugin):
    """
    Multi-agent plugin hosting Data, Cortona, and Jarvis.
    Each agent has its own ConversationManager and memory namespace.
    """

    plugin_name = "Agents"
    plugin_version = "1.0.0"
    plugin_description = "Three AI agents: Data (analytics), Cortona (intuitive), Jarvis (full-spectrum)"

    def setup(self) -> None:
        from api.ai_client import AIClient
        from core.config import config
        from core.conversation import ConversationManager

        ai = AIClient.from_config(config)

        # Each agent gets its own ConversationManager and memory namespace
        self._data    = ConversationManager(ai_client=ai, memory=self.assistant.memory,
                                             system_prompt=DATA_PROMPT,    history_limit=20)
        self._cortona = ConversationManager(ai_client=ai, memory=self.assistant.memory,
                                             system_prompt=CORTONA_PROMPT, history_limit=20)
        self._jarvis  = ConversationManager(ai_client=ai, memory=self.assistant.memory,
                                             system_prompt=JARVIS_PROMPT,  history_limit=20)

        log.info("[agents] Data, Cortona, and Jarvis are online.")

    def teardown(self) -> None:
        log.info("[agents] Agents offline.")

    def get_commands(self) -> dict[str, Any]:
        return {
            "chat_data":     self.handle_data,
            "chat_cortona":  self.handle_cortona,
            "chat_jarvis":   self.handle_jarvis,
            "clear_data":    self.clear_data,
            "clear_cortona": self.clear_cortona,
            "clear_jarvis":  self.clear_jarvis,
            "agents_status": self.agents_status,
        }

    # ── Chat handlers ──────────────────────────────────────────────────────────

    def handle_data(self, message: str = "", **_) -> dict[str, Any]:
        if not message:
            return {"error": "message is required"}
        reply = self._data.chat(user_message=message, plugin="data")
        return {"agent": "Data", "reply": reply, "ts": _now()}

    def handle_cortona(self, message: str = "", **_) -> dict[str, Any]:
        if not message:
            return {"error": "message is required"}
        reply = self._cortona.chat(user_message=message, plugin="cortona")
        return {"agent": "Cortona", "reply": reply, "ts": _now()}

    def handle_jarvis(self, message: str = "", **_) -> dict[str, Any]:
        if not message:
            return {"error": "message is required"}
        reply = self._jarvis.chat(user_message=message, plugin="jarvis")
        return {"agent": "Jarvis", "reply": reply, "ts": _now()}

    # ── Clear handlers ─────────────────────────────────────────────────────────

    def clear_data(self, **_) -> dict[str, Any]:
        count = self.assistant.memory.clear_history(plugin="data")
        return {"cleared": count, "agent": "Data"}

    def clear_cortona(self, **_) -> dict[str, Any]:
        count = self.assistant.memory.clear_history(plugin="cortona")
        return {"cleared": count, "agent": "Cortona"}

    def clear_jarvis(self, **_) -> dict[str, Any]:
        count = self.assistant.memory.clear_history(plugin="jarvis")
        return {"cleared": count, "agent": "Jarvis"}

    # ── Status ─────────────────────────────────────────────────────────────────

    def agents_status(self, **_) -> dict[str, Any]:
        try:
            ai_ok = self._data.ai_client.health_check()
            return {
                "status": "ok" if ai_ok.get("reachable") else "degraded",
                "agents": ["Data", "Cortona", "Jarvis"],
                "ai": ai_ok,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def health_check(self) -> dict[str, Any]:
        return self.agents_status()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
