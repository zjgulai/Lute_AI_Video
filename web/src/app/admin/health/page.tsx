"use client";

import { useEffect, useState } from "react";
import { adminFetchJson } from "@/components/api";
import {
  CheckCircle,
  WarningCircle,
  XCircle,
  Clock,
} from "@phosphor-icons/react";

interface ServiceStatus {
  status: "healthy" | "degraded" | "down";
  latency_ms: number;
  available?: boolean;
}

interface HealthData {
  checked_at: string | null;
  services: Record<string, ServiceStatus>;
}

interface HealthHistoryEntry {
  checked_at: string;
  services: Record<string, ServiceStatus>;
}

const SERVICE_LABELS: Record<string, string> = {
  postgres: "PostgreSQL",
  deepseek: "DeepSeek API",
  poyo: "POYO API",
  siliconflow: "SiliconFlow",
  remotion: "Remotion Renderer",
};

export default function AdminHealthPage() {
  const [data, setData] = useState<HealthData | null>(null);
  const [history, setHistory] = useState<HealthHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [statusData, historyData] = await Promise.all([
        adminFetchJson<HealthData>("/api/admin/health/status"),
        adminFetchJson<{ checks: HealthHistoryEntry[] }>(
          "/api/admin/health/history?hours=24"
        ),
      ]);
      setData(statusData);
      setHistory(historyData.checks);
    } catch {
      setError("Failed to load health data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, []);

  const StatusIcon = ({ status }: { status: string }) => {
    switch (status) {
      case "healthy":
        return <CheckCircle size={18} weight="fill" className="text-[var(--jade-accent)]" />;
      case "degraded":
        return <WarningCircle size={18} weight="fill" className="text-[var(--gold-foil)]" />;
      default:
        return <XCircle size={18} weight="fill" className="text-[var(--crimson-mist)]" />;
    }
  };

  const statusBg = (status: string) => {
    switch (status) {
      case "healthy": return "bg-[rgba(120,175,140,0.08)] border-[rgba(120,175,140,0.2)]";
      case "degraded": return "bg-[rgba(245,181,87,0.08)] border-[rgba(245,181,87,0.2)]";
      default: return "bg-[rgba(208,78,90,0.06)] border-[rgba(208,78,90,0.15)]";
    }
  };

  if (loading) {
    return (
      <div className="space-y-4" aria-busy="true" aria-live="polite">
        <div className="flex items-center justify-between">
          <div className="h-5 w-32 skeleton rounded" />
          <div className="h-3 w-20 skeleton rounded" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="apple-card p-3 border border-[var(--divider-light)]">
              <div className="flex items-center justify-between mb-2">
                <div className="h-3 w-24 skeleton rounded" />
                <div className="w-4 h-4 rounded-full skeleton" />
              </div>
              <div className="flex items-center gap-2">
                <div className="h-3 w-12 skeleton rounded-full" />
                <div className="h-3 w-10 skeleton rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[var(--text-h1)]">
          System Health
        </h1>
        <button
          onClick={load}
          className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--fortune-red)] transition-colors cursor-pointer"
        >
          <Clock size={12} weight="fill" />
          Check Now
        </button>
      </div>

      {error && (
        <div className="text-center py-8">
          <p className="text-xs text-[var(--text-muted)] mb-2">{error}</p>
          <button onClick={load} className="apple-btn text-xs py-1 px-3 border border-[var(--border-default)]">Retry</button>
        </div>
      )}

      {/* Status cards */}
      {!error && data?.services && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Object.entries(data.services).map(([key, svc]) => (
            <div
              key={key}
              className={`apple-card p-3 border ${statusBg(svc.status)}`}
            >
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-xs font-medium text-[var(--text-h1)]">
                  {SERVICE_LABELS[key] || key}
                </h3>
                <StatusIcon status={svc.status} />
              </div>
              <div className="flex items-center gap-2 text-[11px]">
                <span
                  className={`px-1.5 py-0.5 rounded-full ${
                    svc.status === "healthy"
                      ? "bg-[rgba(120,175,140,0.15)] text-[var(--jade-accent)]"
                      : svc.status === "degraded"
                      ? "bg-[rgba(245,181,87,0.15)] text-[var(--gold-foil)]"
                      : "bg-[rgba(208,78,90,0.1)] text-[var(--crimson-mist)]"
                  }`}
                >
                  {svc.status}
                </span>
                {svc.latency_ms > 0 && (
                  <span className="text-[var(--text-muted)]">
                    {svc.latency_ms}ms
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Checked at */}
      {data?.checked_at && (
        <p className="text-[11px] text-[var(--text-muted)]">
          Last checked: {new Date(data.checked_at).toLocaleString()}
        </p>
      )}

      {/* History table */}
      {history.length > 0 && (
        <div className="apple-card overflow-hidden mt-4">
          <h2 className="text-sm font-medium text-[var(--text-h1)] p-4 pb-2 border-b border-[var(--divider-light)]">
            Health Check History (24h)
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-[var(--divider-light)]">
                  <th className="text-left p-2 text-[var(--text-muted)] font-medium">Time</th>
                  {Object.keys(history[0]?.services || {}).map((svc) => (
                    <th key={svc} className="text-left p-2 text-[var(--text-muted)] font-medium">
                      {SERVICE_LABELS[svc] || svc}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.slice(-20).reverse().map((entry, i) => (
                  <tr
                    key={i}
                    className="border-b border-[var(--divider-light)] last:border-0 hover:bg-[var(--bg-panel)]"
                  >
                    <td className="p-2 text-[var(--text-muted)] whitespace-nowrap">
                      {new Date(entry.checked_at).toLocaleTimeString()}
                    </td>
                    {Object.entries(entry.services).map(([svcKey, svc]) => (
                      <td key={svcKey} className="p-2">
                        <span
                          className={`inline-block w-2 h-2 rounded-full ${
                            svc.status === "healthy"
                              ? "bg-[var(--jade-accent)]"
                              : svc.status === "degraded"
                              ? "bg-[var(--gold-foil)]"
                              : "bg-[var(--crimson-mist)]"
                          }`}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
