"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api, type Agent, type Workflow, type Run } from "@/lib/api";
import StatsCard from "@/components/StatsCard";
import StatusBadge from "@/components/StatusBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";
import { Play, RefreshCw, ExternalLink } from "lucide-react";
import Link from "next/link";

interface DashboardData {
  agents: Agent[];
  workflows: Workflow[];
  runs: Run[];
}

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [demoState, setDemoState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [demoRunId, setDemoRunId] = useState<number | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [agents, workflows, runs] = await Promise.all([
        api.agents.list(),
        api.workflows.list(),
        api.runs.list({ limit: 10 }),
      ]);
      setData({ agents, workflows, runs });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const DEMO_MESSAGE =
    "Payment PAY-10291 failed for a customer in Brazil. " +
    "Card declined with error CARD_DECLINED. Please investigate and recommend next action.";

  async function runDemo() {
    setDemoState("loading");
    setDemoRunId(null);
    try {
      // Prefer the already-seeded workflow; create from template as fallback
      const workflows = data?.workflows ?? (await api.workflows.list());
      let wf = workflows.find((w) => w.template_type === "payment_failure_investigation");
      if (!wf) {
        wf = await api.templates.createWorkflow("payment_failure_investigation");
      }
      const queued = await api.workflows.run(wf.id, DEMO_MESSAGE);
      setDemoRunId(queued.run_id);
      setDemoState("done");
      // Navigate directly to the live run monitor so the user sees events stream in
      router.push(`/runs/${queued.run_id}`);
    } catch (err) {
      console.error(err);
      setDemoState("error");
    }
  }

  const totalTokens = data?.runs.reduce((s, r) => s + (r.total_tokens ?? 0), 0) ?? 0;
  const totalCost = data?.runs.reduce((s, r) => s + (r.estimated_cost_usd ?? 0), 0) ?? 0;
  const latestRun = data?.runs[0];

  return (
    <div className="px-8 py-8 max-w-6xl">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">Ganesh AgentOps · AI Agent Orchestration Platform</p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
        >
          <RefreshCw size={12} />
          Refresh
        </button>
      </div>

      {loading ? (
        <LoadingSpinner message="Loading dashboard..." />
      ) : error ? (
        <ErrorState message={error} onRetry={fetchData} />
      ) : (
        <>
          {/* Stats grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4 mb-8">
            <StatsCard
              title="Agents"
              value={data?.agents.length ?? 0}
              subtitle="configured"
              accent="blue"
            />
            <StatsCard
              title="Workflows"
              value={data?.workflows.length ?? 0}
              subtitle="pipelines"
              accent="blue"
            />
            <StatsCard
              title="Total Runs"
              value={data?.runs.length ?? 0}
              subtitle="all time"
            />
            <StatsCard
              title="Latest Status"
              value={latestRun?.status ?? "—"}
              subtitle={latestRun ? `run #${latestRun.run_id}` : "no runs yet"}
              accent={
                latestRun?.status === "completed"
                  ? "green"
                  : latestRun?.status === "failed"
                  ? "red"
                  : latestRun?.status === "running"
                  ? "blue"
                  : "default"
              }
            />
            <StatsCard
              title="Total Tokens"
              value={totalTokens > 0 ? totalTokens.toLocaleString() : "—"}
              subtitle="across all runs"
            />
            <StatsCard
              title="Est. Cost"
              value={totalCost > 0 ? `$${totalCost.toFixed(4)}` : "—"}
              subtitle="USD"
              accent={totalCost > 0 ? "yellow" : "default"}
            />
          </div>

          {/* Run Payment Failure Demo */}
          <div className="mb-8">
            <button
              onClick={runDemo}
              disabled={demoState === "loading"}
              className="w-full flex items-center justify-between px-6 py-5 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:cursor-not-allowed rounded-xl transition-all group border border-blue-500/30"
            >
              <div className="text-left">
                <p className="font-semibold text-white text-lg">Run Payment Failure Demo</p>
                <p className="text-blue-200 text-sm mt-1">
                  Investigate <span className="font-mono font-semibold">PAY-10291</span> · Brazil ·{" "}
                  4-agent pipeline → live event stream
                </p>
              </div>
              {demoState === "loading" ? (
                <div className="w-6 h-6 border-2 border-white/30 border-t-white rounded-full animate-spin shrink-0" />
              ) : (
                <Play
                  size={26}
                  className="text-white group-hover:scale-110 transition-transform shrink-0"
                />
              )}
            </button>
            {demoState === "done" && demoRunId !== null && (
              <p className="text-green-400 text-sm mt-2 text-center">
                Run #{demoRunId} queued — navigating to live monitor…{" "}
                <Link href={`/runs/${demoRunId}`} className="underline hover:text-green-300">
                  Open now →
                </Link>
              </p>
            )}
            {demoState === "error" && (
              <p className="text-red-400 text-sm mt-2 text-center">
                Failed to start demo. Is the backend running at{" "}
                <span className="font-mono">localhost:8000</span>?
              </p>
            )}
          </div>

          {/* Recent runs */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Recent Runs
              </h2>
              <Link
                href="/runs"
                className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
              >
                View all <ExternalLink size={11} />
              </Link>
            </div>

            {!data?.runs.length ? (
              <div className="rounded-xl border border-gray-800 bg-gray-900/60 py-12 text-center text-gray-600 text-sm">
                No runs yet — click the demo button above to start one.
              </div>
            ) : (
              <div className="rounded-xl border border-gray-800 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800 bg-gray-900/80">
                      <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                        Run
                      </th>
                      <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                        Workflow
                      </th>
                      <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                        Status
                      </th>
                      <th className="text-right px-4 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                        Tokens
                      </th>
                      <th className="text-right px-4 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                        Cost
                      </th>
                      <th className="text-right px-4 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider">
                        Duration
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60">
                    {data.runs.slice(0, 5).map((run) => (
                      <tr
                        key={run.run_id}
                        className="bg-gray-950 hover:bg-gray-900/40 transition-colors"
                      >
                        <td className="px-4 py-3 font-mono text-gray-500 text-xs">
                          #{run.run_id}
                        </td>
                        <td className="px-4 py-3 text-gray-300">
                          {run.workflow_name ?? (
                            <span className="text-gray-600">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={run.status} />
                        </td>
                        <td className="px-4 py-3 text-right text-gray-400 font-mono text-xs">
                          {run.total_tokens != null
                            ? run.total_tokens.toLocaleString()
                            : "—"}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-400 font-mono text-xs">
                          {run.estimated_cost_usd != null
                            ? `$${run.estimated_cost_usd.toFixed(4)}`
                            : "—"}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-400 text-xs">
                          {run.duration_seconds != null
                            ? `${run.duration_seconds.toFixed(1)}s`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
