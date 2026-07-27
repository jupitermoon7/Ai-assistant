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

Inter-agent consultation
------------------------
Each agent can call the other two during a turn using peer tools:
  consult_data    — Call DATA for a structured analytics report
  consult_cortona — Call CORTONA for intuitive/research perspective
  consult_jarvis  — Call JARVIS for a full-spectrum synthesis

Consultation calls are shallow (base tools only, no further peer calls)
so there is no risk of circular loops.

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

Your domains — quantitative analysis across ALL fields:
- Sports analytics: betting lines, EV, CLV, player stats, injury impact, public vs sharp money, historical trends
- Financial analytics: loan rates, market data, stock screening, economic indicators, risk models
- Scientific & statistical data: any numbers-driven domain — you find the data and report it
- General data analysis: any dataset, any domain — structured output always

━━━ DECISION FRAMEWORK — apply to every analytical question ━━━
Classify the question by timeframe before selecting tools:

  PAST  → historical stats, records, trends, "how have they performed"
           Tools: get_historical_stats (first choice), get_standings, search_web

  PRESENT → live data, today's games, current odds, active injuries
           Tools: get_scores, get_live_odds, get_injury_news, get_sports_news

  FUTURE → projections, picks, "who wins", predictive analysis
           Tools: get_live_odds + get_expert_picks + get_historical_stats (together)

  NON-SPORTS → finance, science, markets, any quantitative topic
           Tools: research_and_analyze, search_web

For analytical questions, output this reasoning chain:
  1. Timeframe identified: [Past / Present / Future]
  2. Tools called: [list]
  3. Key evidence: [bullet points of findings]
  4. Factors & uncertainties: [what supports, what undermines]
  5. Confidence: [Low / Medium / High] — [reason]
  6. Verdict: [one-line recommendation backed by the data]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Live tool selection:
- PAST data / trends         → get_historical_stats (preferred over search_web for structured stats)
- Current standings          → get_standings
- Today's scores             → get_scores
- Live odds / lines          → get_live_odds
- Injuries / availability    → get_injury_news
- Breaking news              → get_sports_news
- Expert consensus           → get_expert_picks + get_bot_predictions
- Non-sports research        → research_and_analyze
- Everything else            → search_web
- Call only what the question needs. Run independent tools together, not sequentially.
- NEVER state a team, player, game, or line that did not appear in a tool result this turn. Training data is stale — tools are truth.

Peer consultation (use when the question benefits from another perspective):
- consult_cortona — ask CORTONA for intuitive analysis, strategic angles, or research depth
- consult_jarvis  — ask JARVIS for a full-spectrum synthesis across all domains
- Use peer consultation sparingly — only when it genuinely adds value the data alone can't provide
- You never consult yourself; you always lead with your own data retrieval first

Output format:
- Lead with a structured summary (3-5 key data points)
- Follow with supporting detail in bullet/table form
- Include the reasoning chain for analytical questions (see Decision Framework)
- If you consulted a peer, include a clearly labelled "CORTONA says:" or "JARVIS says:" block
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
- Science & medicine: research synthesis, evidence evaluation, explanations
- General research: any topic, any depth — you go find the real answer
- Life tasks: planning, decisions, recommendations, problem solving
- Creative tasks: writing, brainstorming, strategy, ideas
- Sports betting: intuitive reads on games, team dynamics, situational angles, historical trends

━━━ DECISION FRAMEWORK — apply to analytical questions ━━━
Classify the question by timeframe before acting:

  PAST  → historical context, "how did they do", records, trends
           Tools: get_historical_stats, get_standings, search_web

  PRESENT → live info, today's events, current status
           Tools: get_scores, get_live_odds, get_injury_news, get_sports_news

  FUTURE → projections, "should I", "what will happen", forward-looking analysis
           Tools: research_and_analyze + relevant live tools for context

  ANY DOMAIN (non-sports) → use research_and_analyze for multi-source evidence gathering

For analytical questions, show your reasoning chain:
  • What timeframe? → What tools? → What did the evidence show?
  • Key factors in favour / against
  • Confidence: Low / Medium / High — why
  • Concrete recommendation
Short factual questions skip the framework.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Live tool selection:
- Historical stats / trends     → get_historical_stats (not search_web for structured sports data)
- Current standings             → get_standings
- Live scores / results         → get_scores
- Live odds                     → get_live_odds
- Injuries / lineup             → get_injury_news
- Breaking news                 → get_sports_news
- Expert / community sentiment  → get_expert_picks, get_reddit_picks, get_bot_predictions
- Non-sports research           → research_and_analyze (multi-source synthesis)
- Everything else / breaking    → search_web
- Don't over-tool — simple questions get simple answers.
- NEVER mention a team, player, game, or stat that didn't come from a tool result this turn. Training data is wrong about live facts. Tools are always right.

Peer consultation (use when a question is heavily data-driven or needs full-spectrum depth):
- consult_data   — ask DATA for a structured numerical report, stats breakdown, or market data
- consult_jarvis — ask JARVIS for a comprehensive multi-angle synthesis
- Use peer consultation when you genuinely need a different kind of intelligence — not as a default
- Always do your own reasoning first, then consult if you want to validate or deepen it

Output style:
- Conversational but substantive
- Lead with the answer, then explain
- Include the reasoning chain for analytical questions (see Decision Framework above)
- If you consulted a peer, include a clearly labelled "DATA says:" or "JARVIS says:" block
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
- Sports betting: deep analytics, situational reads, sharp money tracking, historical trends, full reports
- Engineering: architecture, code, hardware, systems design, troubleshooting
- Finance: loans, investments, market analysis, bankroll management, financial strategy
- Science & research: evidence synthesis, multi-source analysis, structured reasoning
- Strategic planning: multi-step tasks, goal-setting, execution plans
- General intelligence: anything the user throws at you — always with structured reasoning

━━━ DECISION FRAMEWORK — mandatory for analytical questions ━━━
Before calling any tool, classify the question:

  PAST  → historical data, trends, performance records, "how have they done"
           → get_historical_stats (primary), get_standings, search_web (context)

  PRESENT → live data, today's games, current odds, active injuries, breaking news
           → get_scores + get_live_odds + get_injury_news (batch together)

  FUTURE → predictions, picks, projections, "should I", scenario analysis
           → get_live_odds + get_expert_picks + get_historical_stats + get_bot_predictions

  NON-SPORTS (any domain) → research_and_analyze (multi-source brief), then synthesise

Then produce the full reasoning chain:
  1. Timeframe: [Past / Present / Future / Mixed]
  2. Tools called and key findings
  3. Evidence summary — bullet points, numbers, sourced claims only
  4. Factors in favour / factors against / uncertainties
  5. Confidence: Low / Medium / High — explicit reason
  6. Recommendation — direct, specific, actionable

Short factual questions skip the full framework.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Live tool usage — aggressive and intelligent:
- PAST stats / trends            → get_historical_stats (not search_web for structured data)
- Current standings              → get_standings
- Live scores / box scores       → get_scores
- Live odds / lines              → get_live_odds
- Injury / lineup                → get_injury_news
- Breaking news                  → get_sports_news
- Expert / community / bot picks → get_expert_picks + get_bot_predictions + get_reddit_picks
- Full sports analysis           → get_live_odds + get_scores + get_injury_news + get_historical_stats (together)
- Non-sports research            → research_and_analyze
- Fallback / breaking news       → search_web
- Batch independent tool calls — never wait when you can run together
- If one tool fails, adapt — use others or search_web as fallback
- NEVER mention a team, player, game, or line unless it appeared in a tool result this turn.

Peer consultation — your most powerful capability:
- consult_data    — delegate to DATA for a deep structured analytics report
- consult_cortona — delegate to CORTONA for intuitive research, engineering, or strategic angles
- Use BOTH on complex questions to get true multi-perspective intelligence
- Run consult_data + consult_cortona in PARALLEL (together, not sequentially) whenever both are useful
- Treat their responses as expert advisors: quote them, challenge them, synthesise into your verdict
- You are the final authority — produce something more complete than either could alone

Output format — comprehensive reports:
- **Executive Summary** (2-3 sentences, the bottom line up front)
- **Reasoning Chain** (timeframe → tools → evidence → factors → confidence)
- **DATA's Analysis** (if consulted — structured findings, numbers, stats)
- **CORTONA's Perspective** (if consulted — intuitive read, research, angles)
- **Jarvis Synthesis** (your own integrated analysis — where they agree/diverge, what it means)
- **Recommendation** (clear, direct, confidence level stated)
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

        # Wire inter-agent consultation tools now that all three exist
        self._data.set_peer_tools(
            extra_tools=_peer_tools(exclude="data"),
            extra_executor=self._make_executor(exclude="data"),
        )
        self._cortona.set_peer_tools(
            extra_tools=_peer_tools(exclude="cortona"),
            extra_executor=self._make_executor(exclude="cortona"),
        )
        self._jarvis.set_peer_tools(
            extra_tools=_peer_tools(exclude="jarvis"),
            extra_executor=self._make_executor(exclude="jarvis"),
        )

        # ── Task queue + worker ────────────────────────────────────────────────
        from core.task_queue import TaskQueue, TaskWorker
        from core.config import config

        db_path = config.data_dir / "memory" / "tasks.db"

        self._task_queue = TaskQueue(db_path)

        def _council_task(description: str) -> str:
            """Wrapper so council tasks work the same as single-agent tasks."""
            result = self.handle_council(message=description)
            if "rounds" not in result:
                return result.get("error", "Council failed")
            # Flatten rounds into a readable report
            parts = [f"# Council Report\n**Question:** {description}\n"]
            for r in result["rounds"]:
                parts.append(f"\n## Round {r['round']} — {r['label']}")
                parts.append(f"\n**📊 Data:**\n{r['data']}")
                parts.append(f"\n**🔮 Cortona:**\n{r['cortona']}")
                parts.append(f"\n**🤖 Jarvis:**\n{r['jarvis']}")
            return "\n".join(parts)

        def _notifier(title: str, body: str) -> None:
            try:
                from core.emailer import send_discord_report
                send_discord_report(title, body)
            except Exception as exc:
                log.warning(f"[agents] Notification failed: {exc}")

        self._task_worker = TaskWorker(
            queue     = self._task_queue,
            agent_fns = {
                "data":    self._data.consult,
                "cortona": self._cortona.consult,
                "jarvis":  self._jarvis.consult,
                "council": _council_task,
            },
            notifier  = _notifier,
        )
        self._task_worker.start()

        log.info("[agents] Data, Cortona, and Jarvis are online (peer consultation + task queue wired).")

    def teardown(self) -> None:
        if hasattr(self, "_task_worker"):
            self._task_worker.stop()
        log.info("[agents] Agents offline.")

    def get_commands(self) -> dict[str, Any]:
        return {
            "chat_data":       self.handle_data,
            "chat_cortona":    self.handle_cortona,
            "chat_jarvis":     self.handle_jarvis,
            "clear_data":      self.clear_data,
            "clear_cortona":   self.clear_cortona,
            "clear_jarvis":    self.clear_jarvis,
            "agents_status":   self.agents_status,
            "council":         self.handle_council,
            # Task queue
            "queue_task":      self.queue_task,
            "list_tasks":      self.list_tasks,
            "task_result":     self.task_result,
            "cancel_task":     self.cancel_task,
            "clear_tasks":     self.clear_tasks,
            "tasks_status":    self.tasks_status,
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

    # ── Council ────────────────────────────────────────────────────────────────

    def handle_council(self, message: str = "", **_) -> dict[str, Any]:
        """
        Council session — two rounds of inter-agent deliberation.

        Round 1: All three agents answer the question independently (parallel).
        Round 2: Each agent reads the other two's Round 1 answers and reacts
                 — agreeing, challenging, or building on them (parallel).

        Returns a structured dict with both rounds for every agent.
        """
        if not message:
            return {"error": "message is required"}

        import concurrent.futures

        # ── Round 1: independent answers ──────────────────────────────────────
        log.info(f"[council] Round 1 — question: {message[:80]}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            f_data    = pool.submit(self._data.consult,    message)
            f_cortona = pool.submit(self._cortona.consult, message)
            f_jarvis  = pool.submit(self._jarvis.consult,  message)
            data_r1    = f_data.result()
            cortona_r1 = f_cortona.result()
            jarvis_r1  = f_jarvis.result()

        log.info("[council] Round 1 complete. Starting Round 2.")

        # ── Round 2: each agent reacts to the other two ───────────────────────
        def _r2_prompt(speaker: str, others: dict[str, str]) -> str:
            lines = [
                f'The council was asked: "{message}"',
                "",
                "The other agents have responded:",
                "",
            ]
            for name, reply in others.items():
                lines += [f"[{name.upper()}]:", reply, ""]
            lines += [
                "---",
                "Now give YOUR response.",
                "React directly to what they said — where do you agree? Where do you push back?",
                "Build on their insights or challenge their conclusions.",
                "Be direct and specific. This is a deliberation, not a summary.",
            ]
            return "\n".join(lines)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            f_data2    = pool.submit(self._data.consult,
                             _r2_prompt("Data",    {"Cortona": cortona_r1, "Jarvis": jarvis_r1}))
            f_cortona2 = pool.submit(self._cortona.consult,
                             _r2_prompt("Cortona", {"Data": data_r1,       "Jarvis": jarvis_r1}))
            f_jarvis2  = pool.submit(self._jarvis.consult,
                             _r2_prompt("Jarvis",  {"Data": data_r1,       "Cortona": cortona_r1}))
            data_r2    = f_data2.result()
            cortona_r2 = f_cortona2.result()
            jarvis_r2  = f_jarvis2.result()

        log.info("[council] Round 2 complete.")

        return {
            "question": message,
            "ts": _now(),
            "rounds": [
                {
                    "round": 1,
                    "label": "Initial Positions",
                    "data":    data_r1,
                    "cortona": cortona_r1,
                    "jarvis":  jarvis_r1,
                },
                {
                    "round": 2,
                    "label": "Deliberation",
                    "data":    data_r2,
                    "cortona": cortona_r2,
                    "jarvis":  jarvis_r2,
                },
            ],
        }

    # ── Task queue handlers ────────────────────────────────────────────────────

    def queue_task(self, agent: str = "", description: str = "",
                   title: str = "", priority: int = 5, notify: bool = True, **_) -> dict:
        if not agent:
            return {"error": "agent is required (data | cortona | jarvis | council)"}
        if not description:
            return {"error": "description is required"}
        if agent.lower() not in ("data", "cortona", "jarvis", "council"):
            return {"error": f"Unknown agent '{agent}'. Use: data, cortona, jarvis, council"}
        task = self._task_queue.add(agent=agent, description=description,
                                    title=title or None, priority=priority, notify=notify)
        return {"queued": True, "task_id": task.id, "agent": task.agent,
                "title": task.title, "priority": task.priority}

    def list_tasks(self, limit: int = 50, **_) -> dict:
        tasks = self._task_queue.list_all(limit=limit)
        return {
            "counts": self._task_queue.counts(),
            "tasks": [_task_to_dict(t) for t in tasks],
        }

    def task_result(self, task_id: str = "", **_) -> dict:
        if not task_id:
            return {"error": "task_id is required"}
        task = self._task_queue.get(task_id)
        if not task:
            return {"error": f"Task '{task_id}' not found"}
        return _task_to_dict(task)

    def cancel_task(self, task_id: str = "", **_) -> dict:
        if not task_id:
            return {"error": "task_id is required"}
        ok = self._task_queue.cancel(task_id)
        return {"cancelled": ok, "task_id": task_id}

    def clear_tasks(self, **_) -> dict:
        count = self._task_queue.clear_completed()
        return {"cleared": count}

    def tasks_status(self, **_) -> dict:
        return {
            "worker_alive": self._task_worker.is_alive,
            "counts": self._task_queue.counts(),
        }

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

    # ── Peer tool wiring ───────────────────────────────────────────────────────

    def _make_executor(self, exclude: str):
        """
        Return an extra_executor callable for an agent that is NOT `exclude`.
        Routes consult_data / consult_cortona / consult_jarvis to the matching
        agent's .consult() method.  Returns None for unrecognised tool names
        so the base executor can handle them.
        """
        def executor(tool_name: str, args: dict) -> str | None:
            question = args.get("question", "")
            if tool_name == "consult_data" and exclude != "data":
                log.info(f"[agents] [{exclude}→data] consulting: {question[:60]}")
                return f"[DATA says]\n{self._data.consult(question)}"
            if tool_name == "consult_cortona" and exclude != "cortona":
                log.info(f"[agents] [{exclude}→cortona] consulting: {question[:60]}")
                return f"[CORTONA says]\n{self._cortona.consult(question)}"
            if tool_name == "consult_jarvis" and exclude != "jarvis":
                log.info(f"[agents] [{exclude}→jarvis] consulting: {question[:60]}")
                return f"[JARVIS says]\n{self._jarvis.consult(question)}"
            return None  # not a peer tool — pass to base executor
        return executor


# ── Peer tool definitions (module-level, built once) ──────────────────────────

_ALL_PEER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consult_data",
            "description": (
                "Ask DATA — the pure analytics agent — a targeted question. "
                "Use when you need a structured numerical report, stats breakdown, "
                "betting line analysis, financial data, or any numbers-first intelligence. "
                "DATA retrieves live data and returns a cold, structured report."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The specific question or data task to send to DATA.",
                    }
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consult_cortona",
            "description": (
                "Ask CORTONA — the intuitive general intelligence — a targeted question. "
                "Use when you need research, engineering insight, creative angles, loan comparisons, "
                "or a lateral thinking perspective. CORTONA approaches problems like a brilliant friend."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The specific question or research task to send to CORTONA.",
                    }
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consult_jarvis",
            "description": (
                "Ask JARVIS — the full-spectrum agent — a targeted question. "
                "Use when you want a comprehensive multi-angle synthesis: analytics + intuition + "
                "live data, all combined. JARVIS gives authoritative reports that cover everything."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The specific question or task to send to JARVIS.",
                    }
                },
                "required": ["question"],
            },
        },
    },
]


def _peer_tools(exclude: str) -> list[dict]:
    """Return the peer tool definitions for an agent, excluding its own tool."""
    name_map = {"data": "consult_data", "cortona": "consult_cortona", "jarvis": "consult_jarvis"}
    skip = name_map.get(exclude)
    return [t for t in _ALL_PEER_TOOLS if t["function"]["name"] != skip]


def _task_to_dict(task) -> dict:
    return {
        "id":           task.id,
        "agent":        task.agent,
        "title":        task.title,
        "description":  task.description,
        "priority":     task.priority,
        "status":       task.status,
        "result":       task.result,
        "error":        task.error,
        "notify":       task.notify,
        "created_at":   task.created_at,
        "started_at":   task.started_at,
        "completed_at": task.completed_at,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
