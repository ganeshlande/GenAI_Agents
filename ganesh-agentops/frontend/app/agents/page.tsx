"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type Agent, type AgentCreate } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";
import {
  Bot,
  Plus,
  Pencil,
  Trash2,
  X,
  RefreshCw,
  Save,
  ChevronDown,
  ChevronRight,
} from "lucide-react";

// ── Constants ─────────────────────────────────────────────────────────────────

const MODEL_OPTIONS = [
  "claude-sonnet-4-6",
  "claude-opus-4-8",
  "claude-haiku-4-5-20251001",
  "gpt-4o",
  "gpt-4o-mini",
  "mock",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function csvToArr(s: string): string[] {
  return s
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

function arrToCsv(arr: string[]): string {
  return arr.join(", ");
}

function jsonToStr(obj: Record<string, unknown>): string {
  return Object.keys(obj).length ? JSON.stringify(obj, null, 2) : "{}";
}

function parseJsonField(raw: string): {
  value: Record<string, unknown>;
  error: string | null;
} {
  const trimmed = raw.trim();
  if (!trimmed || trimmed === "{}") return { value: {}, error: null };
  try {
    const parsed = JSON.parse(trimmed);
    if (typeof parsed !== "object" || Array.isArray(parsed) || parsed === null) {
      return { value: {}, error: "Must be a JSON object { … }" };
    }
    return { value: parsed as Record<string, unknown>, error: null };
  } catch {
    return { value: {}, error: "Invalid JSON — check brackets and quotes" };
  }
}

// ── Form state ────────────────────────────────────────────────────────────────

interface FormFields {
  name: string;
  role: string;
  system_prompt: string;
  model: string;
  tools_raw: string;
  channels_raw: string;
  memory_enabled: boolean;
  guardrails_raw: string;
  limits_raw: string;
}

type FieldErrors = Partial<Record<keyof FormFields, string>>;

function blankForm(): FormFields {
  return {
    name: "",
    role: "",
    system_prompt: "",
    model: "claude-sonnet-4-6",
    tools_raw: "",
    channels_raw: "",
    memory_enabled: false,
    guardrails_raw: "{}",
    limits_raw: "{}",
  };
}

function agentToForm(a: Agent): FormFields {
  return {
    name: a.name,
    role: a.role,
    system_prompt: a.system_prompt,
    model: MODEL_OPTIONS.includes(a.model) ? a.model : a.model,
    tools_raw: arrToCsv(a.tools),
    channels_raw: arrToCsv(a.channels),
    memory_enabled: a.memory_enabled,
    guardrails_raw: jsonToStr(a.guardrails),
    limits_raw: jsonToStr(a.limits),
  };
}

function formToPayload(f: FormFields): AgentCreate {
  return {
    name: f.name.trim(),
    role: f.role.trim(),
    system_prompt: f.system_prompt.trim(),
    model: f.model,
    tools: csvToArr(f.tools_raw),
    channels: csvToArr(f.channels_raw),
    memory_enabled: f.memory_enabled,
    guardrails: parseJsonField(f.guardrails_raw).value,
    limits: parseJsonField(f.limits_raw).value,
  };
}

// ── Small components ──────────────────────────────────────────────────────────

function FieldLabel({
  children,
  required,
}: {
  children: React.ReactNode;
  required?: boolean;
}) {
  return (
    <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5">
      {children}
      {required && <span className="text-red-400 ml-0.5">*</span>}
    </label>
  );
}

const INPUT =
  "w-full bg-gray-800/80 border border-gray-700 text-white text-sm rounded-lg px-3 py-2.5 placeholder-gray-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 transition-colors";

const INPUT_ERROR =
  "border-red-600/70 focus:border-red-500 focus:ring-red-500/20";

function FieldError({ msg }: { msg?: string }) {
  if (!msg) return null;
  return <p className="mt-1.5 text-xs text-red-400">{msg}</p>;
}

function SectionDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-1">
      <span className="text-xs font-semibold text-gray-600 uppercase tracking-widest whitespace-nowrap">
        {label}
      </span>
      <div className="flex-1 h-px bg-gray-800" />
    </div>
  );
}

// ── Toggle ────────────────────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onChange}
      aria-pressed={checked}
      className={`relative w-11 h-6 rounded-full transition-colors shrink-0 focus:outline-none focus:ring-2 focus:ring-blue-500/40 ${
        checked ? "bg-blue-600" : "bg-gray-700"
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-sm transition-transform duration-200 ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

// ── Agent panel (right slide-over) ────────────────────────────────────────────

interface AgentPanelProps {
  mode: "create" | "edit" | null;
  form: FormFields;
  fieldErrors: FieldErrors;
  saving: boolean;
  saveError: string | null;
  onChange: (patch: Partial<FormFields>) => void;
  onSave: () => void;
  onClose: () => void;
  editingAgent: Agent | null;
}

function AgentPanel({
  mode,
  form,
  fieldErrors,
  saving,
  saveError,
  onChange,
  onSave,
  onClose,
  editingAgent,
}: AgentPanelProps) {
  const open = mode !== null;

  return (
    <div
      className={`fixed top-0 right-0 h-full w-[500px] bg-gray-900 border-l border-gray-800 z-40 flex flex-col shadow-2xl transition-transform duration-300 ease-in-out ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-5 border-b border-gray-800 shrink-0">
        <div>
          <h2 className="text-base font-semibold text-white">
            {mode === "create" ? "New Agent" : "Edit Agent"}
          </h2>
          {editingAgent && (
            <p className="text-xs text-gray-600 mt-0.5 font-mono">id: {editingAgent.id}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-2 text-gray-500 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
        {/* Identity */}
        <SectionDivider label="Identity" />

        <div>
          <FieldLabel required>Name</FieldLabel>
          <input
            type="text"
            value={form.name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder="Support Intake Agent"
            className={`${INPUT} ${fieldErrors.name ? INPUT_ERROR : ""}`}
          />
          <FieldError msg={fieldErrors.name} />
        </div>

        <div>
          <FieldLabel required>Role</FieldLabel>
          <input
            type="text"
            value={form.role}
            onChange={(e) => onChange({ role: e.target.value })}
            placeholder="Customer Support Intake Specialist"
            className={`${INPUT} ${fieldErrors.role ? INPUT_ERROR : ""}`}
          />
          <FieldError msg={fieldErrors.role} />
        </div>

        <div>
          <FieldLabel>Model</FieldLabel>
          <select
            value={form.model}
            onChange={(e) => onChange({ model: e.target.value })}
            className={INPUT}
          >
            {/* Keep custom model visible if not in list */}
            {!MODEL_OPTIONS.includes(form.model) && (
              <option value={form.model}>{form.model}</option>
            )}
            {MODEL_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center justify-between rounded-lg bg-gray-800/40 border border-gray-800 px-4 py-3">
          <div>
            <p className="text-sm font-medium text-white">Memory</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Persist context across sessions
            </p>
          </div>
          <Toggle
            checked={form.memory_enabled}
            onChange={() => onChange({ memory_enabled: !form.memory_enabled })}
          />
        </div>

        {/* Behaviour */}
        <SectionDivider label="Behaviour" />

        <div>
          <FieldLabel>System Prompt</FieldLabel>
          <textarea
            value={form.system_prompt}
            onChange={(e) => onChange({ system_prompt: e.target.value })}
            placeholder={"You are a… Describe responsibilities, routing rules, and constraints."}
            rows={7}
            className={`${INPUT} resize-y font-mono text-xs leading-relaxed`}
          />
        </div>

        {/* Connectivity */}
        <SectionDivider label="Connectivity" />

        <div>
          <FieldLabel>Tools</FieldLabel>
          <input
            type="text"
            value={form.tools_raw}
            onChange={(e) => onChange({ tools_raw: e.target.value })}
            placeholder="ticket_create, knowledge_base_search, customer_lookup"
            className={INPUT}
          />
          <p className="mt-1.5 text-xs text-gray-600">
            Comma-separated tool identifiers
          </p>
        </div>

        <div>
          <FieldLabel>Channels</FieldLabel>
          <input
            type="text"
            value={form.channels_raw}
            onChange={(e) => onChange({ channels_raw: e.target.value })}
            placeholder="telegram, internal, slack"
            className={INPUT}
          />
          <p className="mt-1.5 text-xs text-gray-600">
            Comma-separated channel names
          </p>
        </div>

        {/* Safety */}
        <SectionDivider label="Safety &amp; Limits" />

        <div>
          <FieldLabel>Guardrails</FieldLabel>
          <textarea
            value={form.guardrails_raw}
            onChange={(e) => onChange({ guardrails_raw: e.target.value })}
            rows={7}
            spellCheck={false}
            placeholder='{&#10;  "block_topics": ["competitor_pricing"],&#10;  "tone": "professional_empathetic"&#10;}'
            className={`${INPUT} resize-y font-mono text-xs leading-relaxed ${
              fieldErrors.guardrails_raw ? INPUT_ERROR : ""
            }`}
          />
          {fieldErrors.guardrails_raw ? (
            <FieldError msg={fieldErrors.guardrails_raw} />
          ) : (
            <p className="mt-1.5 text-xs text-gray-600">
              JSON object — block_topics, tone, pii_handling, prohibited_promises
            </p>
          )}
        </div>

        <div>
          <FieldLabel>Limits</FieldLabel>
          <textarea
            value={form.limits_raw}
            onChange={(e) => onChange({ limits_raw: e.target.value })}
            rows={5}
            spellCheck={false}
            placeholder='{&#10;  "max_iterations": 8,&#10;  "max_tokens": 2048,&#10;  "timeout_seconds": 30&#10;}'
            className={`${INPUT} resize-y font-mono text-xs leading-relaxed ${
              fieldErrors.limits_raw ? INPUT_ERROR : ""
            }`}
          />
          {fieldErrors.limits_raw ? (
            <FieldError msg={fieldErrors.limits_raw} />
          ) : (
            <p className="mt-1.5 text-xs text-gray-600">
              JSON object — max_iterations, max_tokens, timeout_seconds
            </p>
          )}
        </div>

        {/* Backend error */}
        {saveError && (
          <div className="rounded-lg bg-red-950/60 border border-red-800/50 px-4 py-3 text-sm text-red-300">
            <span className="font-medium">Save failed: </span>
            {saveError}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="shrink-0 border-t border-gray-800 px-6 py-4 flex items-center justify-end gap-3 bg-gray-900/80">
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={onSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:cursor-not-allowed rounded-lg transition-colors"
        >
          {saving ? (
            <div className="w-4 h-4 border-2 border-blue-300/40 border-t-white rounded-full animate-spin" />
          ) : (
            <Save size={14} />
          )}
          {mode === "create" ? "Create Agent" : "Save Changes"}
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Panel state
  const [panelMode, setPanelMode] = useState<"create" | "edit" | null>(null);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [form, setForm] = useState<FormFields>(blankForm());
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Delete state
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAgents(await api.agents.list());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  // ── Panel helpers ──

  function openCreate() {
    setForm(blankForm());
    setFieldErrors({});
    setSaveError(null);
    setEditingAgent(null);
    setPanelMode("create");
  }

  function openEdit(agent: Agent) {
    setForm(agentToForm(agent));
    setFieldErrors({});
    setSaveError(null);
    setEditingAgent(agent);
    setPanelMode("edit");
  }

  function closePanel() {
    setPanelMode(null);
    setEditingAgent(null);
  }

  function patchForm(patch: Partial<FormFields>) {
    setForm((prev) => ({ ...prev, ...patch }));
  }

  // ── Validation ──

  function validate(): boolean {
    const errs: FieldErrors = {};
    if (!form.name.trim()) errs.name = "Name is required";
    if (!form.role.trim()) errs.role = "Role is required";
    const g = parseJsonField(form.guardrails_raw);
    if (g.error) errs.guardrails_raw = g.error;
    const l = parseJsonField(form.limits_raw);
    if (l.error) errs.limits_raw = l.error;
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  // ── Save ──

  async function handleSave() {
    if (!validate()) return;
    setSaving(true);
    setSaveError(null);
    try {
      const payload = formToPayload(form);
      if (panelMode === "create") {
        const created = await api.agents.create(payload);
        setAgents((prev) => [created, ...prev]);
      } else if (editingAgent) {
        const updated = await api.agents.update(editingAgent.id, payload);
        setAgents((prev) =>
          prev.map((a) => (a.id === editingAgent.id ? updated : a))
        );
      }
      closePanel();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  // ── Delete ──

  async function handleDelete(id: number) {
    setDeleting(true);
    try {
      await api.agents.delete(id);
      setAgents((prev) => prev.filter((a) => a.id !== id));
      setDeleteConfirmId(null);
    } catch (err) {
      console.error("Delete failed:", err);
    } finally {
      setDeleting(false);
    }
  }

  // ── Render ──

  return (
    <>
      {/* Dim overlay when panel is open */}
      {panelMode && (
        <div
          className="fixed inset-0 bg-black/50 z-30 backdrop-blur-[1px]"
          onClick={closePanel}
        />
      )}

      <AgentPanel
        mode={panelMode}
        form={form}
        fieldErrors={fieldErrors}
        saving={saving}
        saveError={saveError}
        onChange={patchForm}
        onSave={handleSave}
        onClose={closePanel}
        editingAgent={editingAgent}
      />

      <div className="px-8 py-8 max-w-6xl">
        {/* Page header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Agents</h1>
            <p className="text-gray-500 text-sm mt-1">
              {loading
                ? "Loading…"
                : `${agents.length} agent${agents.length !== 1 ? "s" : ""} configured`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchAgents}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50"
            >
              <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
              Refresh
            </button>
            <button
              onClick={openCreate}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors"
            >
              <Plus size={15} />
              New Agent
            </button>
          </div>
        </div>

        {/* Content */}
        {loading ? (
          <LoadingSpinner message="Loading agents..." />
        ) : error ? (
          <ErrorState message={error} onRetry={fetchAgents} />
        ) : !agents.length ? (
          <div className="rounded-xl border border-dashed border-gray-700 bg-gray-900/30 py-20 text-center">
            <div className="w-14 h-14 bg-gray-800/60 border border-gray-700 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Bot size={26} className="text-gray-600" />
            </div>
            <p className="text-gray-400 font-medium mb-1">No agents yet</p>
            <p className="text-gray-600 text-sm mb-5">
              Create one manually or run the demo from the Dashboard.
            </p>
            <button
              onClick={openCreate}
              className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <Plus size={14} />
              Create your first agent
            </button>
          </div>
        ) : (
          <div className="rounded-xl border border-gray-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-900/80">
                  <th className="text-left px-5 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                    Agent
                  </th>
                  <th className="text-left px-5 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                    Model
                  </th>
                  <th className="text-left px-5 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                    Tools
                  </th>
                  <th className="text-left px-5 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                    Channels
                  </th>
                  <th className="text-center px-5 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                    Memory
                  </th>
                  <th className="text-right px-5 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {agents.map((agent) => (
                  <tr
                    key={agent.id}
                    className="bg-gray-950 hover:bg-gray-900/30 transition-colors"
                  >
                    {/* Agent name + role */}
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-blue-900/30 border border-blue-800/40 rounded-lg flex items-center justify-center shrink-0">
                          <Bot size={14} className="text-blue-400" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-white font-medium truncate max-w-[180px]">
                            {agent.name}
                          </p>
                          <p className="text-xs text-gray-600 truncate max-w-[180px] mt-0.5">
                            {agent.role}
                          </p>
                        </div>
                      </div>
                    </td>

                    {/* Model */}
                    <td className="px-5 py-4">
                      <span className="font-mono text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded whitespace-nowrap">
                        {agent.model}
                      </span>
                    </td>

                    {/* Tools */}
                    <td className="px-5 py-4">
                      <div className="flex flex-wrap gap-1">
                        {agent.tools.length === 0 ? (
                          <span className="text-gray-700 text-xs">—</span>
                        ) : (
                          <>
                            {agent.tools.slice(0, 2).map((t) => (
                              <span
                                key={t}
                                className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded"
                              >
                                {t}
                              </span>
                            ))}
                            {agent.tools.length > 2 && (
                              <span className="text-xs text-gray-600">
                                +{agent.tools.length - 2}
                              </span>
                            )}
                          </>
                        )}
                      </div>
                    </td>

                    {/* Channels */}
                    <td className="px-5 py-4">
                      <div className="flex flex-wrap gap-1">
                        {agent.channels.length === 0 ? (
                          <span className="text-gray-700 text-xs">—</span>
                        ) : (
                          agent.channels.map((c) => (
                            <span
                              key={c}
                              className="text-xs bg-gray-800/60 text-gray-500 border border-gray-700/50 px-2 py-0.5 rounded"
                            >
                              {c}
                            </span>
                          ))
                        )}
                      </div>
                    </td>

                    {/* Memory */}
                    <td className="px-5 py-4 text-center">
                      <span
                        className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${
                          agent.memory_enabled
                            ? "bg-green-500/10 text-green-400 border border-green-800/40"
                            : "bg-gray-800/60 text-gray-600 border border-gray-700/40"
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            agent.memory_enabled ? "bg-green-400" : "bg-gray-600"
                          }`}
                        />
                        {agent.memory_enabled ? "on" : "off"}
                      </span>
                    </td>

                    {/* Actions */}
                    <td className="px-5 py-4">
                      <div className="flex items-center justify-end gap-1">
                        {deleteConfirmId === agent.id ? (
                          /* Inline delete confirmation */
                          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-950/50 border border-red-800/40">
                            <span className="text-xs text-red-300 whitespace-nowrap">
                              Delete?
                            </span>
                            <button
                              onClick={() => handleDelete(agent.id)}
                              disabled={deleting}
                              className="text-xs font-semibold text-red-400 hover:text-red-300 transition-colors disabled:opacity-40"
                            >
                              {deleting ? "…" : "Yes"}
                            </button>
                            <span className="text-gray-700 text-xs">·</span>
                            <button
                              onClick={() => setDeleteConfirmId(null)}
                              disabled={deleting}
                              className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                            >
                              No
                            </button>
                          </div>
                        ) : (
                          <>
                            <button
                              onClick={() => openEdit(agent)}
                              title="Edit agent"
                              className="p-1.5 text-gray-600 hover:text-blue-400 hover:bg-blue-900/20 rounded-lg transition-colors"
                            >
                              <Pencil size={14} />
                            </button>
                            <button
                              onClick={() => setDeleteConfirmId(agent.id)}
                              title="Delete agent"
                              className="p-1.5 text-gray-600 hover:text-red-400 hover:bg-red-900/20 rounded-lg transition-colors"
                            >
                              <Trash2 size={14} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Footer */}
            <div className="border-t border-gray-800 bg-gray-900/40 px-5 py-2.5 flex items-center justify-between">
              <span className="text-xs text-gray-600">
                {agents.length} agent{agents.length !== 1 ? "s" : ""}
              </span>
              <span className="text-xs text-gray-700">
                Click a row's edit icon to configure
              </span>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
