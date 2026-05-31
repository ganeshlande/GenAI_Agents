"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  LayoutTemplate,
  Plus,
  Play,
  RefreshCw,
  CheckCircle2,
  ChevronRight,
  Bot,
  Wrench,
  Workflow,
  CreditCard,
  Building2,
  AlertCircle,
} from "lucide-react";

import { api, type WorkflowTemplate, type Workflow as WFType } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";

// ── Static per-template metadata ──────────────────────────────────────────────

const TEMPLATE_META: Record<
  string,
  {
    icon: React.ElementType;
    accentColor: string;
    purpose: string;
    sampleInput: string;
    tags: string[];
  }
> = {
  payment_failure_investigation: {
    icon: CreditCard,
    accentColor: "#3b82f6",
    purpose:
      "Automates the investigation of failed payment transactions. The intake agent classifies the issue and routes it: fraud signals escalate to risk & compliance, while card-declined or bank-side failures go directly to the resolution agent for customer remediation.",
    sampleInput:
      "Payment PAY-10291 failed for a customer in Brazil. Please investigate and recommend next action.",
    tags: ["Payments", "Fraud Detection", "Customer Support"],
  },
  merchant_onboarding_review: {
    icon: Building2,
    accentColor: "#22c55e",
    purpose:
      "Runs a parallel compliance and documentation review for new merchant applications. The intake agent fans out simultaneously to AML/KYC screening and document verification, then both results are merged by the decision agent for an approve/reject/more-info outcome.",
    sampleInput:
      "Merchant ACME Travel Brazil submitted onboarding documents. Please review risk and missing information.",
    tags: ["Onboarding", "KYC / AML", "Parallel Processing"],
  },
};

const AGENT_COLORS: Record<string, string> = {
  "Support Intake Agent": "#3b82f6",
  "Payment Investigator Agent": "#8b5cf6",
  "Risk & Compliance Agent": "#ef4444",
  "Resolution Agent": "#22c55e",
};

function agentColor(name: string): string {
  return AGENT_COLORS[name] ?? "#6b7280";
}

// ── Pipeline preview ──────────────────────────────────────────────────────────

interface RawNode {
  id: string;
  position: { x: number; y: number };
  data: { label: string; color?: string };
}

function PipelinePreview({ nodes }: { nodes: unknown[] }) {
  const nodeList = nodes as RawNode[];
  if (!nodeList.length) return null;

  // Group nodes by x-bucket (group within 80px)
  const sorted = [...nodeList].sort((a, b) => a.position.x - b.position.x);
  const groups: RawNode[][] = [];

  for (const node of sorted) {
    const lastGroup = groups[groups.length - 1];
    const lastX = lastGroup?.[0]?.position.x ?? -9999;
    if (Math.abs(node.position.x - lastX) < 80) {
      lastGroup.push(node);
    } else {
      groups.push([node]);
    }
  }

  return (
    <div className="flex items-center gap-1.5 flex-wrap min-h-[26px]">
      {groups.map((group, gi) => (
        <div key={gi} className="flex items-center gap-1.5">
          {gi > 0 && (
            <ChevronRight size={12} className="text-gray-600 shrink-0" />
          )}
          <div
            className={`flex gap-1 ${
              group.length > 1 ? "flex-col items-start" : "flex-row"
            }`}
          >
            {group.map((n) => (
              <span
                key={n.id}
                style={{
                  background: `${n.data.color ?? "#6b7280"}18`,
                  borderColor: `${n.data.color ?? "#6b7280"}45`,
                  color: n.data.color ?? "#6b7280",
                }}
                className="text-[10px] font-medium px-2 py-0.5 rounded-md border leading-tight whitespace-nowrap"
              >
                {n.data.label}
              </span>
            ))}
            {group.length > 1 && (
              <span className="text-[9px] text-gray-600 ml-0.5">parallel</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Per-template action state ─────────────────────────────────────────────────

interface ActionState {
  creating: boolean;
  created: boolean;
  createError: string | null;
  running: boolean;
  runId: number | null;
  runError: string | null;
}

function initialState(): ActionState {
  return {
    creating: false,
    created: false,
    createError: null,
    running: false,
    runId: null,
    runError: null,
  };
}

// ── Template card ─────────────────────────────────────────────────────────────

interface TemplateCardProps {
  tpl: WorkflowTemplate;
  state: ActionState;
  existingWorkflow: WFType | undefined;
  onCreateWorkflow: () => void;
  onRunDemo: () => void;
}

function TemplateCard({
  tpl,
  state,
  existingWorkflow,
  onCreateWorkflow,
  onRunDemo,
}: TemplateCardProps) {
  const meta = TEMPLATE_META[tpl.template_type];
  const Icon = meta?.icon ?? LayoutTemplate;
  const accent = meta?.accentColor ?? "#3b82f6";
  const tags = meta?.tags ?? [];
  const sampleInput = meta?.sampleInput ?? "";

  const isRunning = state.running;
  const isCreating = state.creating;
  const busy = isRunning || isCreating;

  return (
    <div
      className="rounded-2xl border border-gray-800 bg-gray-900/60 flex flex-col overflow-hidden hover:border-gray-700 transition-colors"
      style={{ borderTopColor: `${accent}40`, borderTopWidth: 2 }}
    >
      {/* ── Card header ── */}
      <div className="px-6 pt-6 pb-4">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div
            className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0 border"
            style={{
              background: `${accent}18`,
              borderColor: `${accent}40`,
            }}
          >
            <Icon size={20} style={{ color: accent }} />
          </div>
          <span className="text-[10px] font-mono bg-gray-800 text-gray-500 px-2 py-0.5 rounded-full border border-gray-700 mt-1">
            {tpl.template_type}
          </span>
        </div>

        <h2 className="text-lg font-bold text-white mb-1.5">{tpl.name}</h2>

        {/* Tags */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          {tags.map((tag) => (
            <span
              key={tag}
              className="text-[10px] font-medium px-2 py-0.5 rounded-full"
              style={{
                background: `${accent}15`,
                color: accent,
                border: `1px solid ${accent}30`,
              }}
            >
              {tag}
            </span>
          ))}
        </div>

        {/* Business purpose */}
        <p className="text-sm text-gray-400 leading-relaxed">
          {meta?.purpose ?? tpl.description}
        </p>
      </div>

      {/* ── Pipeline flow ── */}
      <div className="px-6 py-3.5 border-y border-gray-800/60 bg-gray-950/40">
        <p className="text-[10px] text-gray-600 uppercase tracking-widest font-semibold mb-2">
          Pipeline
        </p>
        <PipelinePreview nodes={tpl.nodes} />
      </div>

      {/* ── Agents + Tools ── */}
      <div className="px-6 py-4 grid grid-cols-2 gap-5">
        {/* Agents */}
        <div>
          <div className="flex items-center gap-1.5 mb-2.5">
            <Bot size={12} className="text-gray-600" />
            <p className="text-[10px] text-gray-600 uppercase tracking-widest font-semibold">
              Agents
            </p>
          </div>
          <ol className="space-y-1.5">
            {tpl.agents.map((agent, i) => (
              <li key={agent} className="flex items-center gap-2">
                <span
                  className="w-4 h-4 rounded text-[9px] font-bold flex items-center justify-center shrink-0"
                  style={{
                    background: `${agentColor(agent)}25`,
                    color: agentColor(agent),
                  }}
                >
                  {i + 1}
                </span>
                <span className="text-xs text-gray-400 leading-tight truncate">
                  {agent}
                </span>
              </li>
            ))}
          </ol>
        </div>

        {/* Tools */}
        <div>
          <div className="flex items-center gap-1.5 mb-2.5">
            <Wrench size={12} className="text-gray-600" />
            <p className="text-[10px] text-gray-600 uppercase tracking-widest font-semibold">
              Tools
            </p>
          </div>
          <ul className="space-y-1.5">
            {tpl.tools.map((tool) => (
              <li key={tool} className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-600 shrink-0" />
                <span className="text-xs font-mono text-gray-500 truncate">
                  {tool}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ── Stats row ── */}
      <div className="px-6 py-2.5 border-t border-gray-800/60 flex items-center gap-5 text-xs text-gray-600">
        <span>
          <span className="text-gray-400 font-medium tabular-nums">
            {tpl.agents.length}
          </span>{" "}
          agents
        </span>
        <span>
          <span className="text-gray-400 font-medium tabular-nums">
            {(tpl.nodes as unknown[]).length}
          </span>{" "}
          nodes
        </span>
        <span>
          <span className="text-gray-400 font-medium tabular-nums">
            {(tpl.edges as unknown[]).length}
          </span>{" "}
          edges
        </span>
        {existingWorkflow && (
          <span className="ml-auto flex items-center gap-1 text-green-500">
            <CheckCircle2 size={11} />
            workflow #{existingWorkflow.id}
          </span>
        )}
      </div>

      {/* ── Sample input preview ── */}
      {sampleInput && (
        <div className="px-6 py-3 border-t border-gray-800/60 bg-gray-950/30">
          <p className="text-[10px] text-gray-600 uppercase tracking-widest font-semibold mb-1.5">
            Demo Input
          </p>
          <p className="text-xs text-gray-500 italic leading-relaxed line-clamp-2">
            &ldquo;{sampleInput}&rdquo;
          </p>
        </div>
      )}

      {/* ── Error messages ── */}
      {(state.createError || state.runError) && (
        <div className="px-6 py-3 border-t border-gray-800/60">
          <div className="flex items-start gap-2 text-xs text-red-400">
            <AlertCircle size={13} className="shrink-0 mt-0.5" />
            <span>{state.createError ?? state.runError}</span>
          </div>
        </div>
      )}

      {/* ── Actions ── */}
      <div className="px-6 py-4 border-t border-gray-800 flex gap-3 mt-auto">
        {/* Create Workflow */}
        <button
          onClick={onCreateWorkflow}
          disabled={busy || state.creating}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors border border-gray-700 hover:border-gray-600 bg-gray-800/60 hover:bg-gray-800 text-gray-300 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {state.creating ? (
            <div className="w-4 h-4 border-2 border-gray-500 border-t-gray-300 rounded-full animate-spin" />
          ) : state.created ? (
            <>
              <CheckCircle2 size={14} className="text-green-400" />
              <span className="text-green-400">Created</span>
            </>
          ) : (
            <>
              <Plus size={14} />
              Create Workflow
            </>
          )}
        </button>

        {/* Run Demo */}
        <button
          onClick={onRunDemo}
          disabled={busy}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors text-white disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            background: busy ? `${accent}50` : accent,
          }}
        >
          {state.running ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Running…
            </>
          ) : (
            <>
              <Play size={14} />
              Run Demo
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TemplatesPage() {
  const router = useRouter();

  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [workflows, setWorkflows] = useState<WFType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [states, setStates] = useState<Record<string, ActionState>>({});

  // ── Helpers ──

  function getState(type: string): ActionState {
    return states[type] ?? initialState();
  }

  function patchState(type: string, patch: Partial<ActionState>) {
    setStates((prev) => ({
      ...prev,
      [type]: { ...(prev[type] ?? initialState()), ...patch },
    }));
  }

  // ── Fetch ──

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tpls, wfs] = await Promise.all([
        api.templates.list(),
        api.workflows.list(),
      ]);
      setTemplates(tpls);
      setWorkflows(wfs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load templates");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // ── Create Workflow ──

  async function handleCreateWorkflow(tpl: WorkflowTemplate) {
    const type = tpl.template_type;
    patchState(type, { creating: true, created: false, createError: null });
    try {
      const created = await api.templates.createWorkflow(type);
      setWorkflows((prev) => [created, ...prev]);
      patchState(type, { creating: false, created: true });
    } catch (err) {
      patchState(type, {
        creating: false,
        createError: err instanceof Error ? err.message : "Create failed",
      });
    }
  }

  // ── Run Demo ──

  async function handleRunDemo(tpl: WorkflowTemplate) {
    const type = tpl.template_type;
    const sampleInput = TEMPLATE_META[type]?.sampleInput ?? "Run demo workflow.";
    patchState(type, { running: true, runId: null, runError: null });

    try {
      // 1. Find an existing workflow for this template, or create one
      let wf = workflows.find((w) => w.template_type === type);
      if (!wf) {
        wf = await api.templates.createWorkflow(type);
        setWorkflows((prev) => [wf!, ...prev]);
      }

      // 2. Trigger the run
      const queued = await api.workflows.run(wf.id, sampleInput);
      patchState(type, { running: false, runId: queued.run_id });

      // 3. Navigate to the run monitor
      router.push(`/runs/${queued.run_id}`);
    } catch (err) {
      patchState(type, {
        running: false,
        runError: err instanceof Error ? err.message : "Run failed",
      });
    }
  }

  // ── Render ──

  return (
    <div className="px-8 py-8 max-w-6xl">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Templates</h1>
          <p className="text-gray-500 text-sm mt-1">
            Pre-built multi-agent pipelines ready to instantiate and run
          </p>
        </div>
        <button
          onClick={fetchAll}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* How it works strip */}
      <div className="mb-8 rounded-xl border border-gray-800 bg-gray-900/40 px-5 py-3.5 flex items-center gap-6 text-xs text-gray-500">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-full bg-blue-900/40 border border-blue-800/50 flex items-center justify-center text-[10px] font-bold text-blue-400">
            1
          </div>
          <span>
            <strong className="text-gray-300">Create Workflow</strong> saves a
            configurable instance to your database
          </span>
        </div>
        <div className="h-4 w-px bg-gray-800" />
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-full bg-green-900/40 border border-green-800/50 flex items-center justify-center text-[10px] font-bold text-green-400">
            2
          </div>
          <span>
            <strong className="text-gray-300">Run Demo</strong> creates the
            workflow (if needed) and starts a run with sample input
          </span>
        </div>
        <div className="h-4 w-px bg-gray-800" />
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-full bg-purple-900/40 border border-purple-800/50 flex items-center justify-center text-[10px] font-bold text-purple-400">
            3
          </div>
          <span>
            <strong className="text-gray-300">Run Monitor</strong> shows live
            agent messages, logs, and cost breakdown
          </span>
        </div>
      </div>

      {loading ? (
        <LoadingSpinner message="Loading templates…" />
      ) : error ? (
        <ErrorState message={error} onRetry={fetchAll} />
      ) : !templates.length ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 py-16 text-center">
          <LayoutTemplate size={32} className="text-gray-700 mx-auto mb-3" />
          <p className="text-gray-500 text-sm">No templates available.</p>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {templates.map((tpl) => (
            <TemplateCard
              key={tpl.template_type}
              tpl={tpl}
              state={getState(tpl.template_type)}
              existingWorkflow={workflows.find(
                (w) => w.template_type === tpl.template_type
              )}
              onCreateWorkflow={() => handleCreateWorkflow(tpl)}
              onRunDemo={() => handleRunDemo(tpl)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
