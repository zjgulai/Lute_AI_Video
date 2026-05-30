"use client";

import { useCallback, useEffect, useState } from "react";
import { adminFetchJson } from "@/components/api";
import { X } from "@phosphor-icons/react";
import { TableRowSkeleton } from "@/components/Skeleton";

interface LogEntry {
  id: string;
  tenant_id: string;
  scenario: string;
  error_code: string;
  message: string;
  created_at: string;
}

interface LogDetail extends LogEntry {
  traceback: string | null;
}

const SCENARIOS = ["", "s1", "s2", "s3", "s4", "s5"];
const TIME_RANGES = [
  { label: "1h", value: "1h" },
  { label: "6h", value: "6h" },
  { label: "24h", value: "24h" },
  { label: "7d", value: "7d" },
];

export default function AdminLogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [scenario, setScenario] = useState("");
  const [tenantFilter, setTenantFilter] = useState("");
  const [appliedScenario, setAppliedScenario] = useState("");
  const [appliedTenantFilter, setAppliedTenantFilter] = useState("");
  const [timeRange, setTimeRange] = useState("24h");
  const [detail, setDetail] = useState<LogDetail | null>(null);

  const getTimeFrom = (range: string): string => {
    const now = new Date();
    switch (range) {
      case "1h": return new Date(now.getTime() - 3600000).toISOString();
      case "6h": return new Date(now.getTime() - 21600000).toISOString();
      case "24h": return new Date(now.getTime() - 86400000).toISOString();
      case "7d": return new Date(now.getTime() - 604800000).toISOString();
      default: return "";
    }
  };

  const load = useCallback(async (pageOverride = page) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("page", String(pageOverride));
      params.set("limit", "50");
      if (appliedScenario) params.set("scenario", appliedScenario);
      if (appliedTenantFilter) params.set("tenant_id", appliedTenantFilter);
      const from = getTimeFrom(timeRange);
      if (from) params.set("from", from);

      const data = await adminFetchJson<{
        items: LogEntry[];
        total: number;
      }>(`/api/admin/logs?${params}`);
      setLogs(data.items);
      setTotal(data.total);
    } catch {
      setError("Failed to load logs");
    } finally {
      setLoading(false);
    }
  }, [page, appliedScenario, appliedTenantFilter, timeRange]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const openDetail = async (logId: string) => {
    try {
      const data = await adminFetchJson<LogDetail>(`/api/admin/logs/${logId}`);
      setDetail(data);
    } catch {
      // silently fail
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-[var(--text-h1)]">System Logs</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <select
          value={scenario}
          onChange={(e) => { setScenario(e.target.value); setPage(1); }}
          className="apple-input text-xs py-1.5"
        >
          {SCENARIOS.map((s) => (
            <option key={s} value={s}>{s || "All scenarios"}</option>
          ))}
        </select>
        <input
          type="text"
          value={tenantFilter}
          onChange={(e) => setTenantFilter(e.target.value)}
          placeholder="Tenant ID"
          className="apple-input text-xs py-1.5 w-32"
        />
        <div className="flex rounded-lg border border-[var(--border-default)] overflow-hidden">
          {TIME_RANGES.map((tr) => (
            <button
              key={tr.value}
              onClick={() => { setTimeRange(tr.value); setPage(1); }}
              className={`text-xs px-2.5 py-1.5 transition-colors ${
                timeRange === tr.value
                  ? "bg-[var(--fortune-red)] text-white"
                  : "bg-transparent text-[var(--text-body)] hover:bg-[var(--bg-panel)]"
              }`}
            >
              {tr.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => {
            setPage(1);
            setAppliedScenario(scenario);
            setAppliedTenantFilter(tenantFilter);
          }}
          className="apple-btn text-xs py-1.5 px-3 border border-[var(--border-default)]"
        >
          Apply Filters
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="text-center py-8">
          <p className="text-xs text-[var(--text-muted)] mb-2">{error}</p>
          <button onClick={() => void load()} className="apple-btn text-xs py-1 px-3 border border-[var(--border-default)]">
            Retry
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="apple-card overflow-hidden" aria-busy="true" aria-live="polite">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--divider-light)]">
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">Time</th>
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">Code</th>
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">Tenant</th>
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">Message</th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 8 }).map((_, i) => (
                <TableRowSkeleton key={i} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Table */}
      {!loading && !error && (
        <>
          {logs.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)] text-center py-16">
              No errors found
            </p>
          ) : (
            <div className="apple-card overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--divider-light)]">
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">Time</th>
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">Code</th>
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">Tenant</th>
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr
                      key={log.id}
                      onClick={() => openDetail(log.id)}
                      className="border-b border-[var(--divider-light)] last:border-0 hover:bg-[var(--bg-panel)] transition-colors cursor-pointer"
                    >
                      <td className="p-3 text-[var(--text-muted)] whitespace-nowrap">
                        {log.created_at
                          ? new Date(log.created_at).toLocaleString()
                          : ""}
                      </td>
                      <td className="p-3">
                        <span className="text-[10px] font-mono bg-[var(--bg-layer3)] px-1.5 py-0.5 rounded">
                          {log.error_code}
                        </span>
                      </td>
                      <td className="p-3 text-[var(--text-muted)]">
                        {log.tenant_id || "—"}
                      </td>
                      <td className="p-3 text-[var(--text-body)] truncate max-w-xs">
                        {log.message}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > 50 && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-[var(--text-muted)]">{total} entries</span>
              <div className="flex gap-1">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                  className="apple-btn text-xs py-1 px-2 border border-[var(--border-default)] disabled:opacity-30"
                >
                  Prev
                </button>
                <button
                  disabled={page * 50 >= total}
                  onClick={() => setPage(page + 1)}
                  className="apple-btn text-xs py-1 px-2 border border-[var(--border-default)] disabled:opacity-30"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Detail modal */}
      {detail && (
        <div className="apple-modal-overlay" onClick={() => setDetail(null)}>
          <div
            className="apple-card w-full max-w-lg mx-4 p-4 animate-scale-in max-h-[80vh] overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">
                Error Detail
              </h2>
              <button onClick={() => setDetail(null)} className="cursor-pointer">
                <X size={16} weight="fill" className="text-[var(--text-muted)]" />
              </button>
            </div>
            <div className="space-y-2 text-xs">
              <div>
                <span className="text-[var(--text-muted)]">Code: </span>
                <span className="font-mono">{detail.error_code}</span>
              </div>
              <div>
                <span className="text-[var(--text-muted)]">Tenant: </span>
                {detail.tenant_id || "—"}
              </div>
              <div>
                <span className="text-[var(--text-muted)]">Time: </span>
                {detail.created_at
                  ? new Date(detail.created_at).toLocaleString()
                  : ""}
              </div>
              <div>
                <span className="text-[var(--text-muted)]">Message: </span>
                <p className="mt-1 text-[var(--text-body)] break-words">
                  {detail.message}
                </p>
              </div>
              {detail.traceback && (
                <div>
                  <span className="text-[var(--text-muted)]">Traceback: </span>
                  <pre className="mt-1 p-2 rounded bg-[var(--bg-layer3)] text-[11px] text-[var(--text-body)] overflow-x-auto max-h-60 whitespace-pre-wrap break-all font-mono">
                    {detail.traceback}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
