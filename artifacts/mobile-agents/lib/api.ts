/**
 * API client for the Pi Assistant Flask server.
 *
 * All chat endpoints live on the Pi's Flask server (port 8000),
 * served at the root path of the api-server artifact.
 * The domain is injected via EXPO_PUBLIC_DOMAIN at bundle time.
 */

export interface CouncilRound {
  round: number;
  label: string;
  data: string;
  cortona: string;
  jarvis: string;
}

export interface CouncilResponse {
  question: string;
  ts: string;
  rounds: CouncilRound[];
}

function baseUrl(): string {
  const domain = process.env.EXPO_PUBLIC_DOMAIN;
  if (!domain) throw new Error('EXPO_PUBLIC_DOMAIN is not set');
  return `https://${domain}`;
}

async function post<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${baseUrl()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  let json: { ok: boolean; data?: T; error?: string };
  try {
    json = await res.json();
  } catch {
    throw new Error(`Server returned non-JSON response (status ${res.status})`);
  }

  if (!json.ok) {
    throw new Error(json.error ?? `Request failed (status ${res.status})`);
  }

  return json.data as T;
}

interface AgentReply {
  agent: string;
  reply: string;
  ts: string;
}

export async function chatData(message: string): Promise<string> {
  const data = await post<AgentReply>('/api/chat/data', { message });
  return data.reply;
}

export async function chatCortona(message: string): Promise<string> {
  const data = await post<AgentReply>('/api/chat/cortona', { message });
  return data.reply;
}

export async function chatJarvis(message: string): Promise<string> {
  const data = await post<AgentReply>('/api/chat/jarvis', { message });
  return data.reply;
}

export async function chatCouncil(message: string): Promise<CouncilResponse> {
  return await post<CouncilResponse>('/api/chat/council', { message });
}
