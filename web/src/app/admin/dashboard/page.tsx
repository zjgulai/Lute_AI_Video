"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { adminFetchJson } from "@/components/api";
import {
  Users,
  FilmSlate,
  WarningOctagon,
} from "@phosphor-icons/react";

interface DashboardData {
  tenant_count: number;
  tenant_count_today: number;
  pipeline_runs_today: {
    total: number;
    success: number;
    failed: number;
    running: number;
  };
  error_rate_24h: number;
  recent_errors: Array<{
    id: string;
    tenant_id: string;
    scenario: string;
    error_code: string;
    message: string;
    created_at: string;
  }>;
}

export default function AdminDashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadData = async () => {
    setLoading(true);
    setError("");
    try {
      const result = await adminFetchJson<DashboardData>(
        "/api/admin/dashboard/summary"
      );
      setData(result);
    } catch {
      setError("Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-5 h-5 border-2 border-[var(--fortune-red)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-[var(--text-muted)] mb-2">{error || "No data"}</p>
        <button
          onClick={loadData}
          className="apple-btn text-xs py-1.5 px-3 border border-[var(--border-default)]"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[var(--text-h1)]">
          Dashboard
        </h1>
        <button
          onClick={loadData}
          className="text-xs text-[var(--text-muted)] hover:text-[var(--fortune-red)] transition-colors cursor-pointer"
        >
          Refresh
        </button>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Link
          href="/admin/tenants"
          className="apple-card p-4 no-underline hover:shadow-md transition-shadow"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[rgba(215,92,112,0.1)] flex items-center justify-center">
              <Users size={20} weight="fill" className="text-[var(--fortune-red)]" />
            </div>
            <div>
              <p className="text-2xl font-bold text-[var(--text-h1)]">
                {data.tenant_count}
              </p>
              <p className="text-xs text-[var(--text-muted)]">
                Active Tenants{data.tenant_count_today > 0 ? ` · +${data.tenant_count_today} today` : ""}
              </p>
            </div>
          </div>
        </Link>

        <Link
          href="/admin/logs"
          className="apple-card p-4 no-underline hover:shadow-md transition-shadow"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[rgba(120,175,140,0.12)] flex items-center justify-center">
              <FilmSlate size={20} weight="fill" className="text-[var(--jade-accent)]" />
            </div>
            <div>
              <p className="text-2xl font-bold text-[var(--text-h1)]">
                {data.pipeline_runs_today.total}
              </p>
              <p className="text-xs text-[var(--text-muted)]">
                Pipeline runs today
                {data.pipeline_runs_today.failed > 0
                  ? ` · ${data.pipeline_runs_today.failed} failed`
                  : ""}
              </p>
            </div>
          </div>
        </Link>

        <div className="apple-card p-4">
          <div className="flex items-center gap-3">
            <div
              className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                data.error_rate_24h > 0.1
                  ? "bg-[rgba(208,78,90,0.12)]"
                  : "bg-[rgba(245,181,87,0.12)]"
              }`}
            >
              <WarningOctagon
                size={20}
                weight="fill"
                className={
                  data.error_rate_24h > 0.1
                    ? "text-[var(--crimson-mist)]"
                    : "text-[var(--gold-foil)]"
                }
              />
            </div>
            <div>
              <p className="text-2xl font-bold text-[var(--text-h1)]">
                {(data.error_rate_24h * 100).toFixed(1)}%
              </p>
              <p className="text-xs text-[var(--text-muted)]">
                Error rate (24h)
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Recent errors */}
      <div className="apple-card p-4">
        <h2 className="text-sm font-medium text-[var(--text-h1)] mb-3">
          Recent Errors
        </h2>
        {data.recent_errors.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)] py-4 text-center">
            No errors recorded — system healthy
          </p>
        ) : (
          <div className="space-y-2">
            {data.recent_errors.map((err) => (
              <Link
                key={err.id}
                href={`/admin/logs`}
                className="block p-2.5 rounded-lg bg-[var(--bg-panel)] hover:bg-[var(--bg-layer3)] no-underline transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-layer3)] px-1.5 py-0.5 rounded shrink-0">
                      {err.error_code}
                    </span>
                    <span className="text-xs text-[var(--text-body)] truncate">
                      {err.message}
                    </span>
                  </div>
                  <span className="text-[11px] text-[var(--text-muted)] shrink-0 ml-2">
                    {err.created_at
                      ? new Date(err.created_at).toLocaleTimeString()
                      : ""}
                  </span>
                </div>
                <div className="flex gap-2 mt-1">
                  {err.tenant_id && (
                    <span className="text-[10px] text-[var(--text-muted)]">
                      {err.tenant_id}
                    </span>
                  )}
                  {err.scenario && (
                    <span className="text-[10px] text-[var(--text-muted)]">
                      {err.scenario}
                    </span>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
