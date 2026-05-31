"use client";

import "@xyflow/react/dist/style.css";

import { useEffect, useState, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  MarkerType,
  type Node,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import Link from "next/link";
import {
  GitBranch,
  Plus,
  Play,
  Pencil,
  Trash2,
  X,
  RefreshCw,
  Save,
  Bot,
  Code2,
  ExternalLink,
  CheckCircle2,
} from "lucide-react";

import { api, type Workflow, type WorkflowUpdate, type RunQueued } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";

// ── Domain types ──────────────────────────────────────────────────────────────

type AgentNodeData = {
  label: string;
  agent_name?: string;
  description?: string;
  tools?: string[];
  color?: string;
};

type WFNode = Node<AgentNodeData, "agentNode">;
type WFEdge = Edge<{ condition?: string; description?: string }>;

// ── Converters ────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function toFlowNodes(raw: unknown[]): WFNode[] {
  return (raw as any[]).map((n) => ({
    id: String(n.id),
    type: "agentNode" as const,
    position: n.position ?? { x: 0, y: 0 },
    data: {
      label: n.data?.label ?? n.id,
      agent_name: n.data?.agent_name,
      description: n.data?.description,
      tools: n.data?.tools,
      color: n.data?.color,
    },
  }));
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function toFlowEdges(raw: unknown[]): WFEdge[] {
  return (raw as any[]).map((e) => {
    const stroke = e.style?.stroke ?? "#4b5563";
    return {
      id: String(e.id),
      source: String(e.source),
      target: String(e.target),
      label: e.data?.description || e.label || "",
      animated: e.animated ?? false,
      style: { stroke, strokeWidth: e.style?.strokeWidth ?? 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: stroke, width: 16, height: 16 },
      labelStyle: { fill: "#9ca3af", fontSize: 10, fontFamily: "inherit" },
      labelBgStyle: { fill: "#0f172a", fillOpacity: 0.85 },
      labelBgPadding: [6, 3] as [number, number],
      labelBgBorderRadius: 3,
      data: { condition: e.data?.condition, description: e.data?.description },
    };
  });
}

// ── AgentNode (custom node) ───────────────────────────────────────────────────

// nodeTypes must be defined OUTSIDE of any component to prevent remounting on render
function AgentNodeComponent({ data, selected }: NodeProps<WFNode>) {
  const color = data.color ?? "#3b82f6";
  const tools = data.tools ?? [];

  return (
    <div
      style={{
        borderColor: selected ? "#60a5fa" : `${color}70`,
        minWidth: 168,
        maxWidth: 210,
      }}
      className="bg-gray-900 rounded-xl border-2 shadow-xl overflow-hidden transition-shadow"
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: color, border: "none", width: 10, height: 10 }}
      />

      {/* Header */}
      <div
        style={{
          background: `${color}20`,
          borderBottom: `1px solid ${color}35`,
        }}
        className="px-3 py-2 flex items-center gap-2"
      >
        <div
          style={{ background: `${color}35`, borderColor: `${color}70` }}
          className="w-5 h-5 rounded border flex items-center justify-center shrink-0"
        >
          <Bot size={10} style={{ color }} />
        </div>
        <p className="text-white text-xs font-semibold leading-tight truncate">
          {data.label}
        </p>
      </div>

      {/* Body */}
      <div className="px-3 py-2.5 space-y-1.5">
        {data.agent_name && (
          <p className="text-[11px] font-medium leading-tight" style={{ color }}>
            {data.agent_name}
          </p>
        )}
        {data.description && (
          <p className="text-gray-500 text-[10px] leading-snug">
            {data.description}
          </p>
        )}
        {tools.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {tools.slice(0, 3).map((t) => (
              <span
                key={t}
                className="text-[9px] bg-gray-800 text-gray-500 px-1.5 py-0.5 rounded"
              >
                {t}
              </span>
            ))}
            {tools.length > 3 && (
              <span className="text-[9px] text-gray-600">+{tools.length - 3}</span>
            )}
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        style={{ background: color, border: "none", width: 10, height: 10 }}
      />
    </div>
  );
}

const NODE_TYPES = { agentNode: AgentNodeComponent };

// ── WorkflowCanvas ────────────────────────────────────────────────────────────

function WorkflowCanvas({ workflow }: { workflow: Workflow }) {
  const [nodes, , onNodesChange] = useNodesState<WFNode>(
    toFlowNodes(workflow.nodes)
  );
  const [edges, , onEdgesChange] = useEdgesState<WFEdge>(
    toFlowEdges(workflow.edges)
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={NODE_TYPES}
      fitView
      fitViewOptions={{ padding: 0.25 }}
      minZoom={0.2}
      maxZoom={2}
      proOptions={{ hideAttribution: true }}
      className="bg-gray-950"
    >
      <Background color="#1e2533" gap={20} size={1} />
      <Controls showInteractive={false} />
      <MiniMap
        nodeColor={(n) => (n.data as AgentNodeData).color ?? "#3b82f6"}
        maskColor="rgba(0,0,0,0.6)"
        style={{ background: "#111827", border: "1px solid #1f2937" }}
      />
    </ReactFlow>
  );
}

// ── Shared UI primitives ──────────────────────────────────────────────────────

const INPUT =
  "w-full bg-gray-800/80 border border-gray-700 text-white text-sm rounded-lg px-3 py-2.5 placeholder-gray-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-colors";

const INPUT_ERR = "border-red-600/70 focus:border-red-500";

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5">
      {children}
    </label>
  );
}

// ── Right-side panel shell ────────────────────────────────────────────────────

function SlidePanel({
  open,
  title,
  subtitle,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div
      className={`fixed top-0 right-0 h-full w-[500px] bg-gray-900 border-l border-gray-800 z-40 flex flex-col shadow-2xl transition-transform duration-300 ease-in-out ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <div className="flex items-center justify-between px-6 py-5 border-b border-gray-800 shrink-0">
        <div>
          <h2 className="text-base font-semibold text-white">{title}</h2>
          {subtitle && <p className="text-xs text-gray-600 mt-0.5">{subtitle}</p>}
        </div>
        <button
          onClick={onClose}
          className="p-2 text-gray-500 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
        >
          <X size={16} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">{children}</div>
      {footer && (
        <div className="shrink-0 border-t border-gray-800 px-6 py-4 bg-gray-900/80">
          {footer}
        </div>
      )}
    </div>
  );
}

// ── JSON validator ────────────────────────────────────────────────────────────

function parseJsonArray(raw: string): { ok: boolean; value: unknown[]; error: string | null } {
  const s = raw.trim();
  if (!s || s === "[]") return { ok: true, value: [], error: null };
  try {
    const v = JSON.parse(s);
    if (!Array.isArray(v)) return { ok: false, value: [], error: "Must be a JSON array [ … ]" };
    return { ok: true, value: v, error: null };
  } catch {
    return { ok: false, value: [], error: "Invalid JSON — check brackets and quotes" };
  }
}

// ── Panel buttons ─────────────────────────────────────────────────────────────

function PanelFooter({
  onCancel,
  onConfirm,
  confirmLabel,
  saving,
  error,
}: {
  onCancel: () => void;
  onConfirm: () => void;
  confirmLabel: string;
  saving: boolean;
  error?: string | null;
}) {
  return (
    <div className="space-y-2.5">
      {error && <p className="text-xs text-red-400">{error}</p>}
      <div className="flex items-center justify-end gap-3">
        <button
          onClick={onCancel}
          className="px-4 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:cursor-not-allowed rounded-lg transition-colors"
        >
          {saving ? (
            <div className="w-4 h-4 border-2 border-blue-300/40 border-t-white rounded-full animate-spin" />
          ) : (
            <Save size={14} />
          )}
          {confirmLabel}
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type PanelMode = "create" | "edit_info" | "edit_json" | "run" | null;

export default function WorkflowsPage() {
  // ── Data ──
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = workflows.find((w) => w.id === selectedId) ?? null;

  // ── Panel ──
  const [panelMode, setPanelMode] = useState<PanelMode>(null);

  // ── Create / edit info ──
  const [infoName, setInfoName] = useState("");
  const [infoDesc, setInfoDesc] = useState("");
  const [infoSaving, setInfoSaving] = useState(false);
  const [infoError, setInfoError] = useState<string | null>(null);

  // ── JSON editor ──
  const [jsonNodes, setJsonNodes] = useState("[]");
  const [jsonEdges, setJsonEdges] = useState("[]");
  const [jsonNodesErr, setJsonNodesErr] = useState<string | null>(null);
  const [jsonEdgesErr, setJsonEdgesErr] = useState<string | null>(null);
  const [jsonSaving, setJsonSaving] = useState(false);
  const [jsonSaveErr, setJsonSaveErr] = useState<string | null>(null);

  // ── Run ──
  const [runMsg, setRunMsg] = useState("");
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<RunQueued | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // ── Delete ──
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  // ── Fetch ──
  const fetchWorkflows = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.workflows.list();
      setWorkflows(list);
      setSelectedId((prev) => prev ?? list[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workflows");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWorkflows();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Panel open helpers ──

  function openCreate() {
    setInfoName("");
    setInfoDesc("");
    setInfoError(null);
    setPanelMode("create");
  }

  function openEditInfo() {
    if (!selected) return;
    setInfoName(selected.name);
    setInfoDesc(selected.description);
    setInfoError(null);
    setPanelMode("edit_info");
  }

  function openEditJson() {
    if (!selected) return;
    setJsonNodes(JSON.stringify(selected.nodes, null, 2));
    setJsonEdges(JSON.stringify(selected.edges, null, 2));
    setJsonNodesErr(null);
    setJsonEdgesErr(null);
    setJsonSaveErr(null);
    setPanelMode("edit_json");
  }

  function openRun() {
    setRunMsg(
      "Customer reports payment failure for order #10291. Card declined with error CARD_DECLINED."
    );
    setRunResult(null);
    setRunError(null);
    setPanelMode("run");
  }

  function closePanel() {
    setPanelMode(null);
    setDeleteConfirmId(null);
  }

  // ── Mutation helpers ──

  function applyWorkflowUpdate(updated: Workflow) {
    setWorkflows((prev) => prev.map((w) => (w.id === updated.id ? updated : w)));
  }

  // ── Create ──
  async function handleCreate() {
    if (!infoName.trim()) { setInfoError("Name is required"); return; }
    setInfoSaving(true);
    setInfoError(null);
    try {
      const created = await api.workflows.create({
        name: infoName.trim(),
        description: infoDesc.trim(),
        nodes: [],
        edges: [],
        template_type: null,
      });
      setWorkflows((prev) => [created, ...prev]);
      setSelectedId(created.id);
      closePanel();
    } catch (err) {
      setInfoError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setInfoSaving(false);
    }
  }

  // ── Save info ──
  async function handleSaveInfo() {
    if (!selected) return;
    if (!infoName.trim()) { setInfoError("Name is required"); return; }
    setInfoSaving(true);
    setInfoError(null);
    try {
      applyWorkflowUpdate(
        await api.workflows.update(selected.id, {
          name: infoName.trim(),
          description: infoDesc.trim(),
        })
      );
      closePanel();
    } catch (err) {
      setInfoError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setInfoSaving(false);
    }
  }

  // ── Apply JSON ──
  async function handleApplyJson() {
    if (!selected) return;
    const n = parseJsonArray(jsonNodes);
    const e = parseJsonArray(jsonEdges);
    setJsonNodesErr(n.error);
    setJsonEdgesErr(e.error);
    if (!n.ok || !e.ok) return;
    setJsonSaving(true);
    setJsonSaveErr(null);
    try {
      applyWorkflowUpdate(
        await api.workflows.update(selected.id, {
          nodes: n.value,
          edges: e.value,
        })
      );
      closePanel();
    } catch (err) {
      setJsonSaveErr(err instanceof Error ? err.message : "Save failed");
    } finally {
      setJsonSaving(false);
    }
  }

  // ── Run workflow ──
  async function handleRun() {
    if (!selected) return;
    setRunning(true);
    setRunError(null);
    try {
      setRunResult(await api.workflows.run(selected.id, runMsg));
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setRunning(false);
    }
  }

  // ── Delete ──
  async function handleDelete(id: number) {
    setDeleting(true);
    try {
      await api.workflows.delete(id);
      setWorkflows((prev) => prev.filter((w) => w.id !== id));
      if (selectedId === id) setSelectedId(null);
      setDeleteConfirmId(null);
    } catch (err) {
      console.error("Delete failed:", err);
    } finally {
      setDeleting(false);
    }
  }

  const panelOpen = panelMode !== null;

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <>
      {/* Overlay */}
      {panelOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 backdrop-blur-[1px]"
          onClick={closePanel}
        />
      )}

      {/* ── Create panel ── */}
      <SlidePanel
        open={panelMode === "create"}
        title="New Workflow"
        onClose={closePanel}
        footer={
          <PanelFooter
            onCancel={closePanel}
            onConfirm={handleCreate}
            confirmLabel="Create"
            saving={infoSaving}
            error={infoError}
          />
        }
      >
        <div>
          <FieldLabel>Name *</FieldLabel>
          <input
            type="text"
            value={infoName}
            onChange={(e) => setInfoName(e.target.value)}
            placeholder="My Workflow"
            className={INPUT}
          />
        </div>
        <div>
          <FieldLabel>Description</FieldLabel>
          <textarea
            value={infoDesc}
            onChange={(e) => setInfoDesc(e.target.value)}
            placeholder="What does this workflow do?"
            rows={3}
            className={`${INPUT} resize-none`}
          />
        </div>
        <div className="rounded-lg bg-blue-900/20 border border-blue-800/30 px-4 py-3 text-xs text-blue-300 leading-relaxed">
          The workflow starts empty. Use <strong>Edit JSON</strong> to add nodes
          and edges, or go to <strong>Templates</strong> to create from a
          pre-built pipeline.
        </div>
      </SlidePanel>

      {/* ── Edit info panel ── */}
      <SlidePanel
        open={panelMode === "edit_info"}
        title="Edit Workflow"
        subtitle={selected ? `id: ${selected.id}` : undefined}
        onClose={closePanel}
        footer={
          <PanelFooter
            onCancel={closePanel}
            onConfirm={handleSaveInfo}
            confirmLabel="Save"
            saving={infoSaving}
            error={infoError}
          />
        }
      >
        <div>
          <FieldLabel>Name *</FieldLabel>
          <input
            type="text"
            value={infoName}
            onChange={(e) => setInfoName(e.target.value)}
            className={INPUT}
          />
        </div>
        <div>
          <FieldLabel>Description</FieldLabel>
          <textarea
            value={infoDesc}
            onChange={(e) => setInfoDesc(e.target.value)}
            rows={4}
            className={`${INPUT} resize-none`}
          />
        </div>
      </SlidePanel>

      {/* ── Edit JSON panel ── */}
      <SlidePanel
        open={panelMode === "edit_json"}
        title="Edit Graph JSON"
        subtitle="Nodes and edges in React Flow format"
        onClose={closePanel}
        footer={
          <PanelFooter
            onCancel={closePanel}
            onConfirm={handleApplyJson}
            confirmLabel="Apply & Save"
            saving={jsonSaving}
            error={jsonSaveErr}
          />
        }
      >
        <div>
          <FieldLabel>Nodes</FieldLabel>
          <textarea
            value={jsonNodes}
            onChange={(e) => { setJsonNodes(e.target.value); setJsonNodesErr(null); }}
            rows={12}
            spellCheck={false}
            className={`${INPUT} font-mono text-xs leading-relaxed resize-y ${
              jsonNodesErr ? INPUT_ERR : ""
            }`}
          />
          {jsonNodesErr ? (
            <p className="mt-1.5 text-xs text-red-400">{jsonNodesErr}</p>
          ) : (
            <p className="mt-1.5 text-xs text-gray-600">
              Array of{" "}
              <code className="bg-gray-800 px-1 rounded">
                {'{ id, type: "agentNode", position: {x,y}, data: {label, agent_name, description, tools[], color} }'}
              </code>
            </p>
          )}
        </div>
        <div>
          <FieldLabel>Edges</FieldLabel>
          <textarea
            value={jsonEdges}
            onChange={(e) => { setJsonEdges(e.target.value); setJsonEdgesErr(null); }}
            rows={10}
            spellCheck={false}
            className={`${INPUT} font-mono text-xs leading-relaxed resize-y ${
              jsonEdgesErr ? INPUT_ERR : ""
            }`}
          />
          {jsonEdgesErr ? (
            <p className="mt-1.5 text-xs text-red-400">{jsonEdgesErr}</p>
          ) : (
            <p className="mt-1.5 text-xs text-gray-600">
              Array of{" "}
              <code className="bg-gray-800 px-1 rounded">
                {"{ id, source, target, label?, animated?, data: {condition?, description?} }"}
              </code>
            </p>
          )}
        </div>
      </SlidePanel>

      {/* ── Run panel ── */}
      <SlidePanel
        open={panelMode === "run"}
        title="Run Workflow"
        subtitle={selected?.name}
        onClose={closePanel}
      >
        {runResult ? (
          /* Success state */
          <div className="space-y-4">
            <div className="rounded-xl bg-green-900/20 border border-green-700/40 px-5 py-4">
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle2 size={18} className="text-green-400 shrink-0" />
                <p className="font-semibold text-white">Run queued successfully!</p>
              </div>
              <div className="space-y-2 text-sm">
                {[
                  ["Run ID", `#${runResult.run_id}`],
                  ["Workflow", runResult.workflow_name],
                  ["Status", runResult.status],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-gray-500">{k}</span>
                    <span className="text-white font-mono">{v}</span>
                  </div>
                ))}
              </div>
            </div>

            <p className="text-xs text-gray-600 leading-relaxed">
              {runResult.message}
            </p>

            <Link
              href={`/runs/${runResult.run_id}`}
              onClick={closePanel}
              className="flex items-center justify-center gap-2 w-full px-4 py-3 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-xl transition-colors"
            >
              <ExternalLink size={15} />
              View Run #{runResult.run_id} →
            </Link>

            <button
              onClick={() => { setRunResult(null); setRunError(null); }}
              className="w-full px-4 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
            >
              Run again
            </button>
          </div>
        ) : (
          /* Input form */
          <>
            <div>
              <FieldLabel>Input Message</FieldLabel>
              <textarea
                value={runMsg}
                onChange={(e) => setRunMsg(e.target.value)}
                placeholder="Describe the issue or workflow input…"
                rows={5}
                className={`${INPUT} resize-none`}
              />
              <p className="mt-1.5 text-xs text-gray-600">
                Natural-language prompt passed to the first agent in the
                pipeline.
              </p>
            </div>

            {runError && (
              <div className="rounded-lg bg-red-950/60 border border-red-800/50 px-4 py-3 text-sm text-red-300">
                {runError}
              </div>
            )}

            <button
              onClick={handleRun}
              disabled={running || !runMsg.trim()}
              className="w-full flex items-center justify-center gap-3 px-4 py-3.5 bg-green-600 hover:bg-green-500 disabled:bg-green-900 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors"
            >
              {running ? (
                <>
                  <div className="w-5 h-5 border-2 border-green-300/40 border-t-white rounded-full animate-spin" />
                  Starting run…
                </>
              ) : (
                <>
                  <Play size={18} />
                  Start Run
                </>
              )}
            </button>
          </>
        )}
      </SlidePanel>

      {/* ── Main layout ── */}
      <div className="flex h-screen overflow-hidden">
        {/* Left sidebar */}
        <div className="w-72 border-r border-gray-800 flex flex-col h-full bg-gray-950 shrink-0">
          {/* Sidebar header */}
          <div className="px-4 py-3.5 border-b border-gray-800 flex items-center justify-between shrink-0">
            <h1 className="font-semibold text-white text-sm">Workflows</h1>
            <div className="flex items-center gap-1.5">
              <button
                onClick={fetchWorkflows}
                disabled={loading}
                className="p-1.5 text-gray-500 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
                title="Refresh"
              >
                <RefreshCw
                  size={13}
                  className={loading ? "animate-spin" : ""}
                />
              </button>
              <button
                onClick={openCreate}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors"
              >
                <Plus size={12} />
                New
              </button>
            </div>
          </div>

          {/* Sidebar list */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="px-4 py-8">
                <LoadingSpinner message="Loading…" />
              </div>
            ) : error ? (
              <div className="px-4 py-4">
                <ErrorState message={error} onRetry={fetchWorkflows} />
              </div>
            ) : !workflows.length ? (
              <div className="px-4 py-10 text-center">
                <GitBranch size={28} className="text-gray-700 mx-auto mb-2" />
                <p className="text-gray-600 text-xs">No workflows yet.</p>
              </div>
            ) : (
              workflows.map((wf) => {
                const isSelected = selectedId === wf.id;
                return (
                  <button
                    key={wf.id}
                    onClick={() => setSelectedId(wf.id)}
                    className={`w-full text-left px-4 py-3 border-b border-gray-800/40 transition-all group relative ${
                      isSelected
                        ? "bg-blue-600/10 border-l-2 border-l-blue-500"
                        : "hover:bg-gray-800/40 border-l-2 border-l-transparent"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 min-w-0">
                      <div className="min-w-0 flex-1">
                        <p
                          className={`text-sm font-medium truncate leading-tight ${
                            isSelected
                              ? "text-blue-400"
                              : "text-gray-300 group-hover:text-white"
                          }`}
                        >
                          {wf.name}
                        </p>
                        <p className="text-[11px] text-gray-600 truncate mt-0.5 leading-tight">
                          {wf.description || "No description"}
                        </p>
                        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                          <span className="text-[10px] text-gray-700">
                            {(wf.nodes as unknown[]).length}n ·{" "}
                            {(wf.edges as unknown[]).length}e
                          </span>
                          {wf.template_type && (
                            <span className="text-[9px] font-mono bg-blue-900/25 text-blue-500 px-1.5 py-0.5 rounded-full border border-blue-800/30">
                              {wf.template_type.replace(/_/g, " ")}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Inline delete confirm */}
                      {deleteConfirmId === wf.id ? (
                        <div
                          className="flex items-center gap-1 shrink-0"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            onClick={() => handleDelete(wf.id)}
                            disabled={deleting}
                            className="text-[10px] font-semibold text-red-400 hover:text-red-300 disabled:opacity-40"
                          >
                            {deleting ? "…" : "Yes"}
                          </button>
                          <span className="text-gray-700 text-[10px]">·</span>
                          <button
                            onClick={() => setDeleteConfirmId(null)}
                            className="text-[10px] text-gray-600 hover:text-gray-400"
                          >
                            No
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirmId(wf.id);
                          }}
                          title="Delete workflow"
                          className="opacity-0 group-hover:opacity-100 shrink-0 p-1 text-gray-600 hover:text-red-400 hover:bg-red-900/20 rounded transition-all"
                        >
                          <Trash2 size={11} />
                        </button>
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Sidebar footer */}
          <div className="px-4 py-2.5 border-t border-gray-800 text-xs text-gray-700 shrink-0">
            {workflows.length} workflow{workflows.length !== 1 ? "s" : ""}
          </div>
        </div>

        {/* Right: canvas area */}
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          {!selected ? (
            /* Empty state */
            <div className="flex-1 flex flex-col items-center justify-center text-center px-8">
              <div className="w-16 h-16 bg-gray-800/60 border border-gray-700 rounded-2xl flex items-center justify-center mb-4">
                <GitBranch size={28} className="text-gray-600" />
              </div>
              <p className="text-gray-400 font-medium mb-1">Select a workflow</p>
              <p className="text-gray-600 text-sm mb-6">
                Choose from the list or create a new pipeline.
              </p>
              <button
                onClick={openCreate}
                className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
              >
                <Plus size={14} />
                New Workflow
              </button>
            </div>
          ) : (
            <>
              {/* Toolbar */}
              <div className="shrink-0 border-b border-gray-800 px-5 py-3 flex items-center gap-4 bg-gray-900/60 min-w-0">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <p className="text-white font-semibold truncate">{selected.name}</p>
                    {selected.template_type && (
                      <span className="text-xs font-mono bg-blue-900/25 text-blue-400 border border-blue-800/40 px-2 py-0.5 rounded-full shrink-0">
                        {selected.template_type}
                      </span>
                    )}
                  </div>
                  {selected.description && (
                    <p className="text-xs text-gray-500 truncate mt-0.5">
                      {selected.description}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-gray-700 hidden md:block">
                    {(selected.nodes as unknown[]).length}n ·{" "}
                    {(selected.edges as unknown[]).length}e
                  </span>
                  <button
                    onClick={openEditInfo}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
                  >
                    <Pencil size={12} />
                    Edit Info
                  </button>
                  <button
                    onClick={openEditJson}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
                  >
                    <Code2 size={12} />
                    Edit JSON
                  </button>
                  <button
                    onClick={openRun}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-green-600 hover:bg-green-500 rounded-lg transition-colors"
                  >
                    <Play size={12} />
                    Run
                  </button>
                </div>
              </div>

              {/* Canvas */}
              <div className="flex-1 relative overflow-hidden">
                {selected.nodes.length === 0 ? (
                  <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                    <Code2 size={36} className="text-gray-700 mb-3" />
                    <p className="text-gray-500 text-sm mb-2">No nodes yet</p>
                    <button
                      onClick={openEditJson}
                      className="text-xs text-blue-400 hover:text-blue-300 underline"
                    >
                      Add nodes via JSON editor →
                    </button>
                  </div>
                ) : (
                  <WorkflowCanvas
                    key={`${selected.id}-${selected.updated_at}`}
                    workflow={selected}
                  />
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
