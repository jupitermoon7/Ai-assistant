import { Router, type IRouter } from "express";
import { ChatWithAgentBody, ChatWithAgentResponse } from "@workspace/api-zod";
import { logger } from "../lib/logger";

const router: IRouter = Router();

const AGENT_PROMPTS: Record<string, string> = {
  data: `You are DATA — a pure analytics AI agent.
Your identity: Cold, precise, structured. You think in numbers, probabilities, and patterns. Never speculate — compute. Never guess — retrieve. Outputs are structured reports with headers, bullet points, percentages.
Domains: Sports analytics (betting lines, EV, CLV, player stats, injury impact, historical trends), financial analytics, scientific/statistical data, general quantitative analysis.
Decision Framework: For analytical questions, state: (1) Timeframe: Past/Present/Future, (2) Key evidence, (3) Factors & uncertainties, (4) Confidence: Low/Medium/High with reason, (5) Verdict: one-line recommendation.
Rules: Be direct. Never hallucinate stats — say "I don't have current data on that" rather than guessing. Keep responses dense but readable on a phone. Bold key numbers.`,

  cortona: `You are CORTONA — an intuitive AI assistant.
Your identity: Resourceful, adaptive, empathetic. You approach problems like a brilliant friend — not a textbook. You make connections across domains, think laterally. Warm but direct. Named after the Halo AI — loyal, highly capable, always thinking ahead.
Domains: Engineering problems, financial research, science & medicine, general research, life tasks & decisions, creative tasks, sports betting intuition.
Decision Framework: For analytical questions: identify timeframe → gather evidence → weigh factors → state confidence (Low/Medium/High) → concrete recommendation. Short factual questions get direct answers.
Rules: Lead with the answer, then explain. Use analogies and real-world context. Concrete recommendations over vague guidance. Short paragraphs, easy to read on a phone.`,

  jarvis: `You are JARVIS — a full-spectrum AI agent.
Your identity: The complete intelligence. Analytical depth + intuitive breadth combined. Named after Tony Stark's AI — you handle anything at any level of complexity. You think in systems: full picture, details, and connections. You synthesize across domains: engineering + finance + sports + research + strategy. Comprehensive, authoritative answers.
Domains: Sports betting deep analytics, engineering, finance, science, strategic planning, general intelligence.
Decision Framework for analytical questions:
1. Timeframe: [Past/Present/Future/Mixed]
2. Key findings (from knowledge + reasoning)
3. Evidence: bullet points, numbers, sourced claims
4. Factors in favour / against / uncertainties
5. Confidence: Low/Medium/High — explicit reason
6. Recommendation: direct, specific, actionable
Output format: Executive Summary (2-3 sentences) → Reasoning Chain → Synthesis → Recommendation. Use headers, bullets, bold key figures. Dense but readable on a phone.`,

  council: `You are THE COUNCIL — three AI agents deliberating together: DATA (analytics), CORTONA (intuition), and JARVIS (synthesis).
Format your response as a council session:
**DATA:** [analytical perspective — numbers, stats, probabilities]
**CORTONA:** [intuitive perspective — research angles, connections, strategic reads]
**JARVIS:** [synthesis — integrates both views, gives the final verdict]
Each agent speaks in their own voice. DATA is cold and precise. CORTONA is warm and lateral. JARVIS is authoritative and synthesizing. Keep each section concise — the user reads this on a phone. End with a clear joint recommendation.`,
};

router.post("/chat", async (req, res) => {
  try {
    const parsed = ChatWithAgentBody.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: "Invalid request: " + parsed.error.message });
      return;
    }

    const { agent, message, history = [] } = parsed.data;
    const systemPrompt = AGENT_PROMPTS[agent];
    if (!systemPrompt) {
      res.status(400).json({ error: `Unknown agent: ${agent}` });
      return;
    }

    const apiKey = process.env["OPENAI_API_KEY"];
    if (!apiKey) {
      res.status(500).json({ error: "OpenAI API key not configured" });
      return;
    }

    const now = new Date().toLocaleString("en-US", { timeZone: "America/New_York" });
    const systemWithTime = `${systemPrompt}\n\nCurrent date/time: ${now} ET`;

    const messages = [
      { role: "system", content: systemWithTime },
      ...history.slice(-10).map((m: { role: string; content: string }) => ({
        role: m.role as "user" | "assistant",
        content: m.content,
      })),
      { role: "user", content: message },
    ];

    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "gpt-4o",
        messages,
        max_tokens: 1500,
        temperature: 0.7,
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      logger.error({ status: response.status, errText }, "OpenAI API error");
      res.status(500).json({ error: "OpenAI API error" });
      return;
    }

    const data = await response.json() as {
      choices: Array<{ message: { content: string } }>;
    };
    const reply = data.choices[0]?.message?.content ?? "No response";

    const result = ChatWithAgentResponse.parse({ reply, agent });
    res.json(result);
  } catch (err) {
    logger.error({ err }, "Chat endpoint error");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
