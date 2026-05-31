"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  RefreshCw,
  ChevronRight,
  ChevronDown,
  Clock,
  Zap,
  DollarSign,
  MessageSquare,
  Wrench,
  CheckCircle2,
  XCircle,
  Loader2,
  Circle,
  Wifi,
  WifiOff,
  Play,
} from "lucide-react";

import {
  api,
  type Run,
  type RunMessage,
  type RunLog,
  type RunEvent,
  API_BASE,
} from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";

// ── Agent palette ─────────────────────────────────────────────────────────────

const AGENT_META: Record<string, { color: string; short: string }> = {
  "Support Intake Agent":       { color: "#3b82f6", short: "SI" },
  "Payment Investigator Agent": { color: "#8b5cf6", short: "PI" },
  "Risk & Compliance Agent":    { color: "#ef4444", short: "RC" },
  "Resolution Agent":           { color: "#22c55e", short: "RE" },
};

function agentColor(name: string | null) {
  return AGENT_META[name ?? ""]?.color ?? "#6b7280";
}
function agentInitials(name: string | null) {
  return AGENT_META[name ?? ""]?.short ?? (name?.split(" ").map(w => w[0]).join("").slice(0, 2) ?? "?");
}

// ── Event-type decoration ─────────────────────────────────────────────────────

const EVT_STYLE: Record<string, { dot: string; label: string; dim?: boolean }> = {
  workflow_start:       { dot: "bg-gray-500",    label: "start" },
  graph_build:          { dot: "bg-gray-600",    label: "build",       dim: true },
  agent_start:          { dot: "bg-blue-500",    label: "agent_start" },
  agent_end:            { dot: "bg-green-500",   label: "agent_end" },
  tool_call:            { dot: "bg-violet-500",  label: "tool_call" },
  tool_result:          { dot: "bg-violet-400",  label: "tool_result", dim: true },
  agent_message:        { dot: "bg-blue-400",    label: "message" },
  guardrail_blocked:    { dot: "bg-yellow-500",  label: "guardrail" },
  tool_blocked:         { dot: "bg-orange-500",  label: "tool_blocked" },
  step_limit_exceeded:  { dot: "bg-red-400",     label: "step_limit" },
  token_limit_warning:  { dot: "bg-yellow-400",  label: "token_warn",  dim: true },
  workflow_end:         { dot: "bg-green-400",   label: "end" },
  workflow_error:       { dot: "bg-red-500",     label: "error" },
};

// ── Markdown renderer (bold + newlines only) ──────────────────────────────────

function mdHtml(s: string): string {
  return s
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br />");
}

// ── Agent pipeline helpers ────────────────────────────────────────────────────

type AgentPhase = "pending" | "running" | "done";

interface AgentSlot {
  name: string;
  phase: AgentPhase;
  inTokens: number;
  outTokens: number;
}

function buildPipeline(logs: RunLog[], liveEvents: RunEvent[]): AgentSlot[] {
  // Collect all agent names in order of first appearance
  const order: string[] = [];
  const phases = new Map<string, AgentPhase>();
  const tokens = new Map<string, { in: number; out: number }>();

  function processEvent(etype: string, msg: string, meta: Record<string, unknown>) {
    const startM = msg.match(/Agent '(.+?)' started/);
    const endM = msg.match(/Agent '(.+?)' completed/);
    if (startM) {
      const name = startM[1];
      if (!order.includes(name)) order.push(name);
      if (phases.get(name) !== "done") phases.set(name, "running");
    }
    if (endM) {
      const name = endM[1];
      if (!order.includes(name)) order.push(name);
      phases.set(name, "done");
      tokens.set(name, {
        in:  Number(meta?.in_tokens  ?? meta?.input_tokens  ?? 0),
        out: Number(meta?.out_tokens ?? meta?.output_tokens ?? 0),
      });
    }
  }

  for (const log of logs) {
    if (log.event_type === "agent_start" || log.event_type === "agent_end") {
      processEvent(log.event_type, log.message, log.metadata as Record<string, unknown>);
    }
  }
  for (const evt of liveEvents) {
    if (evt.event_type === "agent_start" || evt.event_type === "agent_end") {
      processEvent(evt.event_type, evt.content, evt.metadata);
    }
  }

  return order.map((name) => ({
    name,
    phase: phases.get(name) ?? "pending",
    inTokens:  tokens.get(name)?.in  ?? 0,
    outTokens: tokens.get(name)?.out ?? 0,
  }));
}

// ── Tool-execution helpers ────────────────────────────────────────────────────

interface ToolExec {
  agent: string;
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
}

function buildToolExecs(logs: RunLog[]): ToolExec[] {
  const execs: ToolExec[] = [];
  const pending = new Map<string, { agent: string; args: Record<string, unknown> }>();

  for (const log of logs) {
    const meta = log.metadata as Record<string, unknown> | null ?? {};
    if (log.event_type === "tool_call") {
      const tool = meta.tool as string ?? "";
      const agentM = log.message.match(/'(.+?)' -> tool/);
      if (tool) {
        pending.set(tool, {
          agent: agentM?.[1] ?? "",
          args: (meta.args as Record<string, unknown>) ?? {},
        });
      }
    }
    if (log.event_type === "tool_result") {
      const tool = meta.tool as string ?? "";
      const pend = pending.get(tool);
      if (pend) {
        execs.push({
          agent: pend.agent,
          tool,
          args: pend.args,
          result: (meta.result as Record<string, unknown>) ?? {},
        });
        pending.delete(tool);
      }
    }
  }
  return execs;
}

// ── Cost summary helpers ──────────────────────────────────────────────────────

interface AgentCost {
  agent: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

function extractCosts(run: Run): AgentCost[] {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const out = run.output as any;
  return (out?.cost_summary?.per_agent as AgentCost[]) ?? [];
}

// ── Collapsible section ───────────────────────────────────────────────────────

function Section({
  title,
  badge,
  children,
  defaultOpen = true,
}: {
  title: string;
  badge?: string | number;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 mb-3"
      >
        {open ? (
          <ChevronDown size={13} className="text-gray-600 shrink-0" />
        ) : (
          <ChevronRight size={13} className="text-gray-600 shrink-0" />
        )}
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-widest">
          {title}
        </span>
        {badge !== undefined && (
          <span className="text-[10px] font-mono bg-gray-800 text-gray-500 px-1.5 py-0.5 rounded-full">
            {badge}
          </span>
        )}
        <div className="flex-1 h-px bg-gray-800/80 ml-1" />
      </button>
      {open && children}
    </div>
  );
}

// ── Agent avatar ──────────────────────────────────────────────────────────────

function Avatar({ name, size = "md" }: { name: string | null; size?: "sm" | "md" | "lg" }) {
  const color = agentColor(name);
  const initials = agentInitials(name);
  const sz = size === "sm" ? "w-7 h-7 text-[10px]" : size === "lg" ? "w-12 h-12 text-sm" : "w-9 h-9 text-xs";
  return (
    <div
      style={{ background: `${color}22`, borderColor: `${color}55`, color }}
      className={`${sz} rounded-xl border-2 flex items-center justify-center font-bold shrink-0 tabular-nums`}
    >
      {initials}
    </div>
  );
}

// ── Agent pipeline strip ──────────────────────────────────────────────────────

function AgentPipelineStrip({ slots }: { slots: AgentSlot[] }) {
  if (!slots.length) return null;

  return (
    <div className="flex items-start gap-2 flex-wrap">
      {slots.map((slot, i) => {
        const color = agentColor(slot.name);
        const isRunning = slot.phase === "running";
        const isDone    = slot.phase === "done";

        return (
          <div key={slot.name} className="flex items-center gap-2">
            {i > 0 && (
              <ChevronRight
                size={14}
                className={isDone || isRunning ? "text-gray-500" : "text-gray-700"}
              />
            )}
            <div
              style={{
                borderColor: isDone
                  ? `${color}80`
                  : isRunning
                  ? color
                  : "#374151",
                boxShadow: isRunning ? `0 0 12px ${color}60` : undefined,
              }}
              className={`rounded-xl border-2 px-3.5 py-2.5 min-w-[130px] transition-all ${
                isDone
                  ? "bg-gray-900/60"
                  : isRunning
                  ? "bg-gray-900"
                  : "bg-gray-900/30 opacity-50"
              }`}
            >
              {/* Header row */}
              <div className="flex items-center gap-2 mb-1">
                <div
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    isRunning ? "animate-pulse" : ""
                  }`}
                  style={{ background: isDone ? color : isRunning ? color : "#374151" }}
                />
                <span
                  className="text-xs font-semibold truncate"
                  style={{ color: isDone || isRunning ? color : "#6b7280" }}
                >
                  {slot.name.replace(" Agent", "")}
                </span>
                {isDone && (
                  <CheckCircle2
                    size={12}
                    className="ml-auto shrink-0"
                    style={{ color }}
                  />
                )}
                {isRunning && (
                  <Loader2 size={12} className="ml-auto shrink-0 animate-spin text-blue-400" />
                )}
              </div>

              {/* Token count */}
              {isDone && (slot.inTokens > 0 || slot.outTokens > 0) && (
                <p className="text-[10px] text-gray-600 tabular-nums mt-0.5">
                  {(slot.inTokens + slot.outTokens).toLocaleString()} tok
                  <span className="text-gray-700 mx-1">·</span>
                  <span className="text-green-600">{slot.outTokens} out</span>
                </p>
              )}
              {isRunning && (
                <p className="text-[10px] text-blue-400">processing…</p>
              )}
              {slot.phase === "pending" && (
                <p className="text-[10px] text-gray-700">waiting</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Live event feed ───────────────────────────────────────────────────────────

function LiveFeed({
  events,
  isLive,
}: {
  events: RunEvent[];
  isLive: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  if (!events.length && !isLive) return null;

  return (
    <Section title="Event Stream" badge={events.length}>
      <div className="rounded-xl border border-gray-800 overflow-hidden bg-gray-950">
        <div className="max-h-72 overflow-y-auto font-mono text-xs">
          {!events.length && isLive && (
            <div className="flex items-center gap-2 px-4 py-3 text-gray-600">
              <Loader2 size={12} className="animate-spin" />
              Connecting to event stream…
            </div>
          )}
          {events.map((evt, i) => {
            const style = EVT_STYLE[evt.event_type] ?? { dot: "bg-gray-600", label: evt.event_type };
            return (
              <div
                key={`${evt.event_id}-${i}`}
                className={`flex items-start gap-3 px-4 py-1.5 border-b border-gray-800/40 transition-colors ${
                  style.dim ? "opacity-40" : "hover:bg-gray-800/30"
                }`}
              >
                <span className="text-gray-700 shrink-0 tabular-nums w-6 text-right">
                  {evt.event_id}
                </span>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 mt-1 ${style.dot}`}
                />
                <span className="text-gray-600 w-24 shrink-0">
                  {style.label}
                </span>
                <span
                  className="flex-1 truncate"
                  style={{
                    color: evt.sender_agent ? agentColor(evt.sender_agent) : "#6b7280",
                  }}
                >
                  {evt.sender_agent && (
                    <span className="text-gray-600 mr-1.5">
                      [{agentInitials(evt.sender_agent)}]
                    </span>
                  )}
                  {evt.content.slice(0, 80)}
                </span>
                <span className="text-gray-700 shrink-0 hidden lg:block">
                  {new Date(evt.timestamp).toLocaleTimeString(undefined, {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
              </div>
            );
          })}
          {isLive && events.length > 0 && (
            <div className="flex items-center gap-2 px-4 py-2 text-blue-500 text-[10px]">
              <div className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              Live — waiting for events…
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </Section>
  );
}

// ── Message timeline ──────────────────────────────────────────────────────────

function MessageTimeline({ messages }: { messages: RunMessage[] }) {
  // Deduplicate by sender+content (re-runs can store duplicates)
  const unique = messages.filter(
    (m, i, a) =>
      a.findIndex(
        (x) => x.sender_agent === m.sender_agent && x.content === m.content
      ) === i
  );

  if (!unique.length) return null;

  return (
    <Section title="Agent Messages" badge={unique.length}>
      <div className="space-y-4">
        {unique.map((msg) => {
          const color = agentColor(msg.sender_agent);
          return (
            <div key={msg.id} className="flex items-start gap-3">
              <Avatar name={msg.sender_agent} size="md" />
              <div className="flex-1 min-w-0">
                {/* Header */}
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span className="text-sm font-semibold" style={{ color }}>
                    {msg.sender_agent ?? "System"}
                  </span>
                  {msg.receiver_agent && (
                    <>
                      <ChevronRight size={12} className="text-gray-600" />
                      <span
                        className="text-xs font-medium"
                        style={{ color: agentColor(msg.receiver_agent) }}
                      >
                        {msg.receiver_agent}
                      </span>
                    </>
                  )}
                  <span className="ml-auto text-[10px] text-gray-600 font-mono shrink-0">
                    {new Date(msg.created_at).toLocaleTimeString(undefined, {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </span>
                </div>

                {/* Message bubble */}
                <div
                  className="text-sm text-gray-200 leading-relaxed rounded-xl px-4 py-3.5 border"
                  style={{
                    background: `${color}08`,
                    borderColor: `${color}25`,
                    borderLeftWidth: 3,
                    borderLeftColor: color,
                  }}
                  // eslint-disable-next-line react/no-danger
                  dangerouslySetInnerHTML={{ __html: mdHtml(msg.content) }}
                />

                {/* Meta */}
                <div className="flex items-center gap-2 mt-1.5">
                  <span
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                    style={{
                      background: `${color}15`,
                      color: `${color}cc`,
                    }}
                  >
                    {msg.channel}
                  </span>
                  <span className="text-[10px] text-gray-700">{msg.message_type}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

// ── Tools executed ────────────────────────────────────────────────────────────

function ToolsPanel({ execs }: { execs: ToolExec[] }) {
  if (!execs.length) return null;
  return (
    <Section title="Tools Executed" badge={execs.length}>
      <div className="space-y-2">
        {execs.map((ex, i) => (
          <div
            key={i}
            className="rounded-lg border border-gray-800 bg-gray-900/60 px-3.5 py-2.5"
          >
            <div className="flex items-center gap-2 mb-1.5">
              <div
                className="w-5 h-5 rounded border flex items-center justify-center shrink-0"
                style={{
                  background: `${agentColor(ex.agent)}18`,
                  borderColor: `${agentColor(ex.agent)}45`,
                }}
              >
                <Wrench size={10} style={{ color: agentColor(ex.agent) }} />
              </div>
              <span
                className="text-xs font-semibold font-mono"
                style={{ color: agentColor(ex.agent) }}
              >
                {ex.tool}
              </span>
              <span className="text-[10px] text-gray-600 truncate ml-1">
                {ex.agent.replace(" Agent", "")}
              </span>
            </div>
            {Object.keys(ex.args).length > 0 && (
              <div className="text-[10px] font-mono text-gray-600 truncate">
                args: {JSON.stringify(ex.args).slice(0, 60)}
              </div>
            )}
            {Object.keys(ex.result).length > 0 && (
              <div className="text-[10px] font-mono text-gray-500 truncate mt-0.5">
                → {JSON.stringify(ex.result).slice(0, 60)}
              </div>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}

// ── Token / cost breakdown ────────────────────────────────────────────────────

function TokenPanel({ costs }: { costs: AgentCost[] }) {
  if (!costs.length) return null;
  const total = costs.reduce((s, c) => s + c.input_tokens + c.output_tokens, 0);
  return (
    <Section title="Token Usage" badge={`${total.toLocaleString()} tok`}>
      <div className="space-y-2">
        {costs.map((c) => {
          const tok = c.input_tokens + c.output_tokens;
          const pct = total > 0 ? (tok / total) * 100 : 0;
          const color = agentColor(c.agent);
          return (
            <div key={c.agent} className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span style={{ color }} className="font-medium truncate max-w-[140px]">
                  {c.agent.replace(" Agent", "")}
                </span>
                <span className="font-mono text-gray-400 tabular-nums">
                  {tok.toLocaleString()}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-gray-800">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${pct}%`, background: color }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-gray-700 font-mono">
                <span>{c.input_tokens.toLocaleString()} in</span>
                <span>{c.output_tokens.toLocaleString()} out</span>
                <span className="font-mono bg-gray-800 text-gray-600 px-1 rounded">{c.model}</span>
              </div>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

// ── Runtime logs ──────────────────────────────────────────────────────────────

function LogsPanel({ logs }: { logs: RunLog[] }) {
  if (!logs.length) return null;
  return (
    <Section title="Runtime Logs" badge={logs.length} defaultOpen={false}>
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <div className="max-h-60 overflow-y-auto font-mono text-[11px]">
          {logs.map((log) => (
            <div
              key={log.id}
              className="flex items-start gap-2.5 px-3.5 py-1.5 border-b border-gray-800/40 hover:bg-gray-800/20"
            >
              <span
                className={`shrink-0 font-semibold uppercase text-[9px] w-8 mt-0.5 ${
                  log.level === "error"
                    ? "text-red-400"
                    : log.level === "warning"
                    ? "text-yellow-400"
                    : "text-gray-700"
                }`}
              >
                {log.level.slice(0, 4)}
              </span>
              <span className="text-violet-500/60 w-20 shrink-0 truncate">
                {log.event_type}
              </span>
              <span className="text-gray-500 flex-1 truncate">{log.message}</span>
            </div>
          ))}
        </div>
      </div>
    </Section>
  );
}

// ── Input / output panels ─────────────────────────────────────────────────────

function InputSection({ run }: { run: Run }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const out = run.output as any;
  const extracted = out?.extracted_data as Record<string, unknown> | undefined;
  if (!extracted || !Object.keys(extracted).length) return null;

  return (
    <Section title="Extracted Data" badge={Object.keys(extracted).length}>
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-xs">
          <tbody className="divide-y divide-gray-800/50">
            {Object.entries(extracted).map(([k, v]) => (
              <tr key={k} className="bg-gray-950 hover:bg-gray-900/30">
                <td className="px-3.5 py-2 font-mono text-gray-600 w-48">{k}</td>
                <td className="px-3.5 py-2 text-gray-300 font-mono">
                  {typeof v === "boolean"
                    ? v
                      ? <span className="text-green-400">true</span>
                      : <span className="text-red-400">false</span>
                    : typeof v === "object"
                    ? JSON.stringify(v)
                    : String(v)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function OutputSection({ run }: { run: Run }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const out = run.output as any;
  const finalOutput = out?.final_output as string | undefined;
  if (!finalOutput) return null;

  return (
    <Section title="Final Output" defaultOpen>
      <div
        className="rounded-xl border border-green-800/30 bg-green-950/10 px-4 py-3.5 text-sm text-gray-200 leading-relaxed"
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{ __html: mdHtml(finalOutput) }}
      />
    </Section>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function RunDetailPage() {
  const params = useParams();
  const runId = Number(params.run_id);

  const [run, setRun] = useState<Run | null>(null);
  const [messages, setMessages] = useState<RunMessage[]>([]);
  const [logs, setLogs] = useState<RunLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // SSE state
  const [liveEvents, setLiveEvents] = useState<RunEvent[]>([]);
  const [sseStatus, setSseStatus] = useState<"idle" | "live" | "done" | "error">("idle");
  const sseRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  // ── REST fetch ──
  const fetchAll = useCallback(async (): Promise<string> => {
    try {
      const [runData, msgs, runLogs] = await Promise.all([
        api.runs.get(runId),
        api.runs.messages(runId),
        api.runs.logs(runId),
      ]);
      if (!mountedRef.current) return runData.status;
      setRun(runData);
      setMessages(msgs);
      setLogs(runLogs);
      setError(null);
      return runData.status;
    } catch (err) {
      if (!mountedRef.current) return "error";
      setError(err instanceof Error ? err.message : "Failed to load run");
      return "error";
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [runId]);

  // ── Polling fallback ──
  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      const status = await fetchAll();
      if (status !== "pending" && status !== "running") {
        clearInterval(pollRef.current!);
        pollRef.current = null;
      }
    }, 2000);
  }

  // ── SSE connection ──
  function connectSSE() {
    if (sseRef.current) return;
    setSseStatus("live");

    const es = new EventSource(`${API_BASE}/api/runs/${runId}/events`);
    sseRef.current = es;

    es.onmessage = (evt) => {
      if (!mountedRef.current) return;
      // Skip SSE comment lines (they come as empty data)
      if (!evt.data || evt.data.startsWith(":")) return;
      try {
        const data = JSON.parse(evt.data) as Record<string, unknown>;

        if (data.type === "stream_complete" || data.type === "timeout") {
          es.close();
          sseRef.current = null;
          setSseStatus("done");
          // Final REST fetch to get persisted data
          setTimeout(() => fetchAll(), 300);
          return;
        }

        // It's a RunEvent
        const evt2 = data as unknown as RunEvent;
        setLiveEvents((prev) => {
          if (prev.find((e) => e.event_id === evt2.event_id)) return prev;
          return [...prev, evt2];
        });

        // Terminal events → fetch final state
        if (evt2.event_type === "workflow_end" || evt2.event_type === "workflow_error") {
          es.close();
          sseRef.current = null;
          setSseStatus("done");
          setTimeout(() => fetchAll(), 400);
        }
      } catch {}
    };

    es.onerror = () => {
      es.close();
      sseRef.current = null;
      if (!mountedRef.current) return;
      setSseStatus("error");
      // Fall back to polling
      startPolling();
    };
  }

  // ── Bootstrap ──
  useEffect(() => {
    mountedRef.current = true;

    fetchAll().then((status) => {
      if (!mountedRef.current) return;
      if (status === "pending" || status === "running") {
        connectSSE();
      } else {
        // Completed run — connect SSE anyway to replay stored events
        connectSSE();
      }
    });

    return () => {
      mountedRef.current = false;
      sseRef.current?.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  // ── Derived data ──
  const isLive = run?.status === "pending" || run?.status === "running";
  const isSseLive = sseStatus === "live";
  const pipeline = buildPipeline(logs, liveEvents);
  const toolExecs = buildToolExecs(logs);
  const costs = run ? extractCosts(run) : [];

  // ── Render ──
  return (
    <div className="min-h-screen">
      {/* Page header */}
      <div className="border-b border-gray-800 bg-gray-900/50 px-8 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
          {/* Left: breadcrumb + title */}
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm mb-1">
              <Link
                href="/runs"
                className="text-gray-500 hover:text-white transition-colors flex items-center gap-1"
              >
                <ArrowLeft size={13} />
                Runs
              </Link>
              <ChevronRight size={12} className="text-gray-700" />
              <span className="text-gray-500 font-mono">#{runId}</span>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-xl font-bold text-white">
                Run #{runId}
              </h1>
              {run && <StatusBadge status={run.status} />}
              {isLive && (
                <div className="flex items-center gap-1.5 text-xs text-blue-400">
                  <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                  Live
                </div>
              )}
              {/* SSE indicator */}
              <div className="flex items-center gap-1 ml-auto">
                {isSseLive ? (
                  <span className="flex items-center gap-1 text-[10px] text-green-500 font-mono">
                    <Wifi size={10} /> SSE
                  </span>
                ) : sseStatus === "error" ? (
                  <span className="flex items-center gap-1 text-[10px] text-yellow-500 font-mono">
                    <WifiOff size={10} /> polling
                  </span>
                ) : sseStatus === "done" ? (
                  <span className="flex items-center gap-1 text-[10px] text-gray-600 font-mono">
                    <Wifi size={10} /> stream done
                  </span>
                ) : null}
              </div>
            </div>
            {run?.workflow_name && (
              <p className="text-gray-500 text-sm mt-0.5">{run.workflow_name}</p>
            )}
          </div>

          {/* Right: refresh */}
          <button
            onClick={() => fetchAll()}
            className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors shrink-0"
          >
            <RefreshCw size={12} />
            Refresh
          </button>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="px-8 py-16">
          <LoadingSpinner message="Loading run…" />
        </div>
      ) : error ? (
        <div className="px-8 py-16">
          <ErrorState message={error} onRetry={() => fetchAll()} />
        </div>
      ) : !run ? null : (
        <div className="px-8 py-6 max-w-7xl mx-auto">
          {/* ── Stats row ── */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            {[
              {
                icon: Clock,
                label: "Duration",
                value: run.duration_seconds != null ? `${run.duration_seconds.toFixed(2)}s` : "—",
                accent: undefined,
              },
              {
                icon: Zap,
                label: "Tokens",
                value: run.total_tokens?.toLocaleString() ?? "—",
                accent: undefined,
              },
              {
                icon: DollarSign,
                label: "Est. Cost",
                value:
                  run.estimated_cost_usd != null && run.estimated_cost_usd > 0
                    ? `$${run.estimated_cost_usd.toFixed(4)}`
                    : "—",
                accent: undefined,
              },
              {
                icon: MessageSquare,
                label: "Messages",
                value: run.message_count,
                accent: undefined,
              },
            ].map(({ icon: Icon, label, value }) => (
              <div
                key={label}
                className="rounded-xl border border-gray-800 bg-gray-900/60 px-4 py-3.5 flex items-center gap-3"
              >
                <div className="w-8 h-8 bg-gray-800 rounded-lg flex items-center justify-center shrink-0">
                  <Icon size={14} className="text-gray-500" />
                </div>
                <div>
                  <p className="text-[10px] text-gray-600 uppercase tracking-widest font-semibold">
                    {label}
                  </p>
                  <p className="text-white font-bold text-sm tabular-nums">{value}</p>
                </div>
              </div>
            ))}
          </div>

          {/* ── Timing strip ── */}
          <div className="mb-6 rounded-xl border border-gray-800 bg-gray-900/30 px-5 py-3 flex flex-wrap gap-6 text-sm">
            {run.started_at && (
              <div>
                <p className="text-[10px] text-gray-600 uppercase tracking-widest font-semibold mb-0.5">Started</p>
                <p className="text-gray-300">{new Date(run.started_at).toLocaleString()}</p>
              </div>
            )}
            {run.completed_at && (
              <div>
                <p className="text-[10px] text-gray-600 uppercase tracking-widest font-semibold mb-0.5">Completed</p>
                <p className="text-gray-300">{new Date(run.completed_at).toLocaleString()}</p>
              </div>
            )}
            {run.workflow_id && (
              <div>
                <p className="text-[10px] text-gray-600 uppercase tracking-widest font-semibold mb-0.5">Workflow</p>
                <Link href="/workflows" className="text-blue-400 hover:text-blue-300 font-mono">
                  #{run.workflow_id}
                </Link>
              </div>
            )}
            {run.log_count > 0 && (
              <div>
                <p className="text-[10px] text-gray-600 uppercase tracking-widest font-semibold mb-0.5">Logs</p>
                <p className="text-gray-500">{run.log_count}</p>
              </div>
            )}
          </div>

          {/* ── Agent Pipeline ── */}
          {pipeline.length > 0 && (
            <div className="mb-6">
              <p className="text-[10px] text-gray-600 uppercase tracking-widest font-semibold mb-3">
                Agent Pipeline
              </p>
              <AgentPipelineStrip slots={pipeline} />
            </div>
          )}

          {/* ── Main two-column layout ── */}
          <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
            {/* Left column: events + messages + extracted data */}
            <div className="xl:col-span-3 space-y-7">
              <LiveFeed events={liveEvents} isLive={isSseLive && isLive} />
              <MessageTimeline messages={messages} />
              <OutputSection run={run} />
              <InputSection run={run} />
            </div>

            {/* Right column: tools + tokens + logs */}
            <div className="xl:col-span-2 space-y-6">
              <ToolsPanel execs={toolExecs} />
              <TokenPanel costs={costs} />
              <LogsPanel logs={logs} />

              {/* Raw output (very bottom) */}
              {run.output && (
                <Section title="Raw Output" defaultOpen={false}>
                  <pre className="rounded-xl border border-gray-800 bg-gray-900/60 px-4 py-3.5 text-[11px] text-gray-500 font-mono overflow-x-auto leading-relaxed max-h-64 overflow-y-auto">
                    {JSON.stringify(run.output, null, 2)}
                  </pre>
                </Section>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
