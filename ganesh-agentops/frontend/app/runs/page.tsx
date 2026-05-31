"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Activity, RefreshCw, ExternalLink, Play } from "lucide-react";

import { api, type Run } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";

function fmtDuration(s: number | null): string {
  if (s == null) return "—";
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`;
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function RunsPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const autoRefRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchRuns = useCallback(async () => {
    setError(null);
    try {
      const list = await api.runs.list({ limit: 50 });
      setRuns(list);
      return list;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load runs");
      return [] as Run[];
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-refresh while any run is live
  useEffect(() => {
    fetchRuns().then((list) => {
      const hasLive = list.some(
        (r) => r.status === "pending" || r.status === "running"
      );
      if (hasLive) {
        autoRefRef.current = setInterval(() => {
          fetchRuns().then((updated) => {
            const stillLive = updated.some(
              (r) => r.status === "pending" || r.status === "running"
            );
            if (!stillLive && autoRefRef.current) {
              clearInterval(autoRefRef.current);
            }
          });
        }, 3000);
      }
    });
    return () => {
      if (autoRefRef.current) clearInterval(autoRefRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const totalTokens = runs.reduce((s, r) => s + (r.total_tokens ?? 0), 0);
  const totalCost = runs.reduce((s, r) => s + (r.estimated_cost_usd ?? 0), 0);
  const completedCount = runs.filter((r) => r.status === "completed").length;
  const failedCount = runs.filter((r) => r.status === "failed").length;
  const liveCount = runs.filter(
    (r) => r.status === "pending" || r.status === "running"
  ).length;

  return (
    <div className="px-8 py-8 max-w-6xl">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Runs</h1>
          <p className="text-gray-500 text-sm mt-1">
            {!loading && !error && (
              <>
                {runs.length} total
                {completedCount > 0 && (
                  <> · <span className="text-green-500">{completedCount} completed</span></>
                )}
                {failedCount > 0 && (
                  <> · <span className="text-red-400">{failedCount} failed</span></>
                )}
                {liveCount > 0 && (
                  <> · <span className="text-blue-400 animate-pulse">{liveCount} live</span></>
                )}
                {totalTokens > 0 && <> · {totalTokens.toLocaleString()} tok</>}
                {totalCost > 0 && <> · ${totalCost.toFixed(4)}</>}
              </>
            )}
          </p>
        </div>
        <button
          onClick={() => fetchRuns()}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {loading ? (
        <LoadingSpinner message="Loading runs…" />
      ) : error ? (
        <ErrorState message={error} onRetry={fetchRuns} />
      ) : !runs.length ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 py-16 text-center">
          <Activity size={32} className="text-gray-700 mx-auto mb-3" />
          <p className="text-gray-500 text-sm mb-4">No runs yet.</p>
          <Link
            href="/"
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <Play size={14} />
            Run Payment Failure Demo
          </Link>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-900/80">
                {[
                  ["Run", "w-16 text-left"],
                  ["Workflow", "text-left"],
                  ["Status", "text-left"],
                  ["Dur.", "text-right"],
                  ["Tokens", "text-right"],
                  ["Cost", "text-right"],
                  ["Started", "text-right"],
                  ["", "w-8"],
                ].map(([label, cls]) => (
                  <th
                    key={label}
                    className={`px-4 py-3 text-xs text-gray-500 font-medium uppercase tracking-wider ${cls}`}
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {runs.map((run) => {
                const isLive =
                  run.status === "pending" || run.status === "running";
                return (
                  <tr
                    key={run.run_id}
                    onClick={() => router.push(`/runs/${run.run_id}`)}
                    className={`cursor-pointer transition-colors ${
                      isLive
                        ? "bg-blue-950/20 hover:bg-blue-950/30"
                        : "bg-gray-950 hover:bg-gray-900/40"
                    }`}
                  >
                    <td className="px-4 py-3 font-mono text-gray-500 text-xs">
                      #{run.run_id}
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-gray-300 max-w-[200px] truncate">
                        {run.workflow_name ?? (
                          <span className="text-gray-600">—</span>
                        )}
                      </p>
                      {run.workflow_id && (
                        <p className="text-[10px] text-gray-600 font-mono mt-0.5">
                          wf#{run.workflow_id}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <StatusBadge status={run.status} />
                        {isLive && (
                          <div className="w-3 h-3 rounded-full border-2 border-blue-400/40 border-t-blue-400 animate-spin" />
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-400 tabular-nums text-xs">
                      {fmtDuration(run.duration_seconds)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-gray-400">
                      {run.total_tokens != null
                        ? run.total_tokens.toLocaleString()
                        : <span className="text-gray-700">—</span>}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      {run.estimated_cost_usd != null && run.estimated_cost_usd > 0 ? (
                        <span className="text-yellow-500/80">
                          ${run.estimated_cost_usd.toFixed(4)}
                        </span>
                      ) : (
                        <span className="text-gray-700">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 text-xs">
                      {fmtTime(run.started_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <ExternalLink size={12} className="text-gray-700 group-hover:text-gray-400 inline" />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="border-t border-gray-800 bg-gray-900/40 px-4 py-2.5 flex items-center justify-between text-xs text-gray-600">
            <span>{runs.length} run{runs.length !== 1 ? "s" : ""}</span>
            {totalCost > 0 && (
              <span>
                Total est. cost:{" "}
                <span className="text-yellow-500/70 font-mono">${totalCost.toFixed(4)}</span>
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
