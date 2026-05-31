/**
 * Typed API client for the Ganesh AgentOps backend.
 * Supports NEXT_PUBLIC_API_BASE_URL (primary) or NEXT_PUBLIC_API_URL (legacy).
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

const BASE = API_BASE;

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Domain types ──────────────────────────────────────────────────────────────

export interface Agent {
  id: number;
  name: string;
  role: string;
  system_prompt: string;
  model: string;
  tools: string[];
  channels: string[];
  memory_enabled: boolean;
  guardrails: Record<string, unknown>;
  limits: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export type AgentCreate = Omit<Agent, "id" | "created_at" | "updated_at">;
export type AgentUpdate = Partial<AgentCreate>;

export interface Workflow {
  id: number;
  name: string;
  description: string;
  nodes: unknown[];
  edges: unknown[];
  template_type: string | null;
  created_at: string;
  updated_at: string;
}

export type WorkflowCreate = Omit<Workflow, "id" | "created_at" | "updated_at">;

export interface WorkflowUpdate {
  name?: string;
  description?: string;
  nodes?: unknown[];
  edges?: unknown[];
  template_type?: string | null;
}

export interface WorkflowTemplate {
  template_type: string;
  name: string;
  description: string;
  agents: string[];
  tools: string[];
  nodes: unknown[];
  edges: unknown[];
}

export interface Run {
  run_id: number;
  workflow_id: number | null;
  workflow_name: string | null;
  status: string;
  total_tokens: number | null;
  estimated_cost_usd: number | null;
  duration_seconds: number | null;
  message_count: number;
  log_count: number;
  event_count: number;
  started_at: string | null;
  completed_at: string | null;
  output: Record<string, unknown> | null;
}

export interface RunQueued {
  run_id: number;
  workflow_id: number;
  workflow_name: string;
  status: string;
  events_url: string;
  poll_url: string;
  message: string;
}

export interface RunMessage {
  id: number;
  run_id: number;
  sender_agent: string | null;
  receiver_agent: string | null;
  channel: string;
  message_type: string;
  content: string;
  created_at: string;
}

export interface RunLog {
  id: number;
  run_id: number;
  level: string;
  event_type: string;
  message: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
}

export interface RunEvent {
  run_id: number;
  event_id: number;
  timestamp: string;
  /** workflow_start | workflow_end | workflow_error | agent_start | agent_end |
   *  agent_message | tool_call | tool_result | guardrail_blocked */
  event_type: string;
  sender_agent: string | null;
  receiver_agent: string | null;
  content: string;
  metadata: Record<string, unknown>;
}

// ── API surface ───────────────────────────────────────────────────────────────

export const api = {
  health: () => req<HealthStatus>("/health"),

  agents: {
    list: (skip = 0, limit = 100) =>
      req<Agent[]>(`/api/agents?skip=${skip}&limit=${limit}`),
    get: (id: number) => req<Agent>(`/api/agents/${id}`),
    create: (data: AgentCreate) =>
      req<Agent>("/api/agents", { method: "POST", body: JSON.stringify(data) }),
    update: (id: number, data: AgentUpdate) =>
      req<Agent>(`/api/agents/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (id: number) =>
      req<void>(`/api/agents/${id}`, { method: "DELETE" }),
  },

  workflows: {
    list: (skip = 0, limit = 100) =>
      req<Workflow[]>(`/api/workflows?skip=${skip}&limit=${limit}`),
    get: (id: number) => req<Workflow>(`/api/workflows/${id}`),
    create: (data: WorkflowCreate) =>
      req<Workflow>("/api/workflows", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (id: number, data: WorkflowUpdate) =>
      req<Workflow>(`/api/workflows/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (id: number) =>
      req<void>(`/api/workflows/${id}`, { method: "DELETE" }),
    run: (id: number, message: string) =>
      req<RunQueued>(`/api/workflows/${id}/run`, {
        method: "POST",
        body: JSON.stringify({ message }),
      }),
  },

  templates: {
    list: () => req<WorkflowTemplate[]>("/api/templates"),
    get: (type: string) => req<WorkflowTemplate>(`/api/templates/${type}`),
    createWorkflow: (type: string, name?: string, description?: string) =>
      req<Workflow>(`/api/templates/${type}/create-workflow`, {
        method: "POST",
        body: JSON.stringify({ name, description }),
      }),
  },

  runs: {
    list: (params?: {
      workflow_id?: number;
      status?: string;
      skip?: number;
      limit?: number;
    }) => {
      const q = new URLSearchParams();
      if (params?.workflow_id != null)
        q.set("workflow_id", String(params.workflow_id));
      if (params?.status) q.set("status", params.status);
      if (params?.skip != null) q.set("skip", String(params.skip));
      if (params?.limit != null) q.set("limit", String(params.limit));
      return req<Run[]>(`/api/runs?${q}`);
    },
    get: (id: number) => req<Run>(`/api/runs/${id}`),
    messages: (id: number) => req<RunMessage[]>(`/api/runs/${id}/messages`),
    logs: (id: number) => req<RunLog[]>(`/api/runs/${id}/logs`),
    poll: (id: number) =>
      req<Run>(`/api/runs/${id}`),
  },

  messages: {
    list: (params?: {
      run_id?: number;
      agent?: string;
      channel?: string;
      limit?: number;
    }) => {
      const q = new URLSearchParams();
      if (params?.run_id != null) q.set("run_id", String(params.run_id));
      if (params?.agent) q.set("agent", params.agent);
      if (params?.channel) q.set("channel", params.channel);
      if (params?.limit != null) q.set("limit", String(params.limit));
      return req<RunMessage[]>(`/api/messages?${q}`);
    },
  },
};
