"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { adminFetchJson } from "@/components/api";
import { Plus, MagnifyingGlass, Circle, X } from "@phosphor-icons/react";
import { TableRowSkeleton } from "@/components/Skeleton";

import { errorMessage } from "@/lib/errors";
interface Tenant {
  id: string;
  tenant_id: string;
  display_name: string;
  contact_email: string;
  status: string;
  key_count: number;
  created_at: string;
  last_active: string | null;
}

export default function AdminTenantsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newTenantId, setNewTenantId] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newContactEmail, setNewContactEmail] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const load = useCallback(async (pageOverride = page) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("page", String(pageOverride));
      params.set("limit", "20");
      if (appliedQ) params.set("q", appliedQ);
      const data = await adminFetchJson<{
        items: Tenant[];
        total: number;
      }>(`/api/admin/tenants?${params}`);
      setTenants(data.items);
      setTotal(data.total);
    } catch {
      setError("Failed to load tenants");
    } finally {
      setLoading(false);
    }
  }, [page, appliedQ]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setCreateError("");
    try {
      await adminFetchJson("/api/admin/tenants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: newTenantId.trim().toLowerCase(),
          display_name: newDisplayName.trim(),
          contact_email: newContactEmail.trim(),
        }),
      });
      setShowCreate(false);
      setNewTenantId("");
      setNewDisplayName("");
      setNewContactEmail("");
      void load();
    } catch (err: unknown) {
      setCreateError(errorMessage(err, "Failed to create tenant"));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[var(--text-h1)]">Tenants</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 apple-btn apple-btn-primary text-xs py-1.5 px-3"
        >
          <Plus size={14} weight="fill" />
          New Tenant
        </button>
      </div>

      {/* Search */}
      <div className="flex gap-2">
        <div className="flex-1 relative">
          <MagnifyingGlass
            size={14}
            weight="fill"
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          />
          <input
            type="text"
            aria-label="Search tenants"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setPage(1);
                setAppliedQ(q);
              }
            }}
            placeholder="Search tenants..."
            className="apple-input text-xs pl-7 w-full"
          />
        </div>
        <button
          onClick={() => { setPage(1); setAppliedQ(q); }}
          className="apple-btn text-xs py-1.5 px-3 border border-[var(--border-default)]"
        >
          Search
        </button>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="apple-modal-overlay" onClick={() => setShowCreate(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-new-tenant-title"
            className="apple-card w-full max-w-sm mx-4 p-4 animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h2 id="admin-new-tenant-title" className="text-sm font-semibold text-[var(--text-h1)]">
                New Tenant
              </h2>
              <button
                onClick={() => setShowCreate(false)}
                className="cursor-pointer"
                aria-label="Close new tenant dialog"
              >
                <X size={16} weight="fill" className="text-[var(--text-muted)]" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="space-y-3">
              <label htmlFor="admin-new-tenant-id" className="sr-only">
                Tenant ID
              </label>
              <input
                id="admin-new-tenant-id"
                type="text"
                value={newTenantId}
                onChange={(e) => setNewTenantId(e.target.value)}
                placeholder="tenant-id (lowercase, 3-32 chars)"
                required
                pattern="^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$"
                className="apple-input text-xs w-full"
              />
              <label htmlFor="admin-new-display-name" className="sr-only">
                Display name
              </label>
              <input
                id="admin-new-display-name"
                type="text"
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
                placeholder="Display name"
                required
                className="apple-input text-xs w-full"
              />
              <label htmlFor="admin-new-contact-email" className="sr-only">
                Contact email
              </label>
              <input
                id="admin-new-contact-email"
                type="email"
                value={newContactEmail}
                onChange={(e) => setNewContactEmail(e.target.value)}
                placeholder="Contact email (optional)"
                className="apple-input text-xs w-full"
              />
              {createError && (
                <p role="alert" className="text-xs text-[var(--crimson-mist)]">{createError}</p>
              )}
              <button
                type="submit"
                disabled={creating}
                className="apple-btn apple-btn-primary text-xs w-full py-2 disabled:opacity-50"
              >
                {creating ? "Creating..." : "Create Tenant"}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Error state */}
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
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">Tenant</th>
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">Status</th>
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">Keys</th>
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 5 }).map((_, i) => (
                <TableRowSkeleton key={i} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Table */}
      {!loading && !error && (
        <>
          {tenants.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-xs text-[var(--text-muted)]">
                {q ? "No tenants match your search" : "No tenants yet"}
              </p>
            </div>
          ) : (
            <div className="apple-card overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--divider-light)]">
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">Tenant</th>
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">Status</th>
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">Keys</th>
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {tenants.map((t) => (
                    <tr
                      key={t.id}
                      className="border-b border-[var(--divider-light)] last:border-0 hover:bg-[var(--bg-panel)] transition-colors"
                    >
                      <td className="p-3">
                        <Link
                          href={`/admin/tenants/${t.tenant_id}`}
                          className="no-underline"
                        >
                          <p className="font-medium text-[var(--text-h1)]">
                            {t.display_name}
                          </p>
                          <p className="text-[var(--text-muted)]">{t.tenant_id}</p>
                        </Link>
                      </td>
                      <td className="p-3">
                        <span
                          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] ${
                            t.status === "active"
                              ? "bg-[rgba(120,175,140,0.12)] text-[var(--jade-accent)]"
                              : "bg-[rgba(208,78,90,0.1)] text-[var(--crimson-mist)]"
                          }`}
                        >
                          <Circle size={6} weight="fill" />
                          {t.status}
                        </span>
                      </td>
                      <td className="p-3 text-[var(--text-body)]">{t.key_count}</td>
                      <td className="p-3 text-[var(--text-muted)]">
                        {t.created_at
                          ? new Date(t.created_at).toLocaleDateString()
                          : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > 20 && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-[var(--text-muted)]">
                {total} tenants total
              </span>
              <div className="flex gap-1">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                  className="apple-btn text-xs py-1 px-2 border border-[var(--border-default)] disabled:opacity-30"
                >
                  Prev
                </button>
                <button
                  disabled={page * 20 >= total}
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
    </div>
  );
}
