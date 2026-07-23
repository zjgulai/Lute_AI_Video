"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { adminFetchJson } from "@/components/api";
import { Plus, MagnifyingGlass, Circle, X } from "@phosphor-icons/react";
import { TableRowSkeleton } from "@/components/Skeleton";

import { errorMessage } from "@/lib/errors";
import { useI18n } from "@/i18n/I18nProvider";
import { useModalBehavior } from "@/hooks/useModalBehavior";
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
  const { t } = useI18n();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newTenantId, setNewTenantId] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newContactEmail, setNewContactEmail] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const createCloseRef = useRef<HTMLButtonElement>(null);

  const closeCreate = useCallback(() => setShowCreate(false), []);
  useModalBehavior({
    open: showCreate,
    onClose: closeCreate,
    initialFocusRef: createCloseRef,
  });

  const load = useCallback(async (pageOverride = page) => {
    setLoading(true);
    setError(false);
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
      setError(true);
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
      setCreateError(errorMessage(err, t("admin.tenants.createFailed")));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[var(--text-h1)]">{t("admin.nav.tenants")}</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 apple-btn apple-btn-primary text-xs py-1.5 px-3"
        >
          <Plus size={14} weight="fill" />
          {t("admin.tenants.new")}
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
            aria-label={t("admin.tenants.search")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setPage(1);
                setAppliedQ(q);
              }
            }}
            placeholder={t("admin.tenants.searchPlaceholder")}
            className="apple-input text-xs pl-7 w-full"
          />
        </div>
        <button
          onClick={() => { setPage(1); setAppliedQ(q); }}
          className="apple-btn text-xs py-1.5 px-3 border border-[var(--border-default)]"
        >
          {t("admin.tenants.search")}
        </button>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="apple-modal-overlay" onClick={closeCreate}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-new-tenant-title"
            className="apple-card w-full max-w-sm mx-4 p-4 animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h2 id="admin-new-tenant-title" className="text-sm font-semibold text-[var(--text-h1)]">
                {t("admin.tenants.new")}
              </h2>
              <button
                ref={createCloseRef}
                onClick={closeCreate}
                className="cursor-pointer"
                aria-label={t("admin.tenants.closeCreate")}
              >
                <X size={16} weight="fill" className="text-[var(--text-muted)]" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="space-y-3">
              <label htmlFor="admin-new-tenant-id" className="sr-only">
                {t("admin.tenants.tenantId")}
              </label>
              <input
                id="admin-new-tenant-id"
                type="text"
                value={newTenantId}
                onChange={(e) => setNewTenantId(e.target.value)}
                placeholder={t("admin.tenants.idPlaceholder")}
                required
                pattern="^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$"
                className="apple-input text-xs w-full"
              />
              <label htmlFor="admin-new-display-name" className="sr-only">
                {t("admin.tenants.displayName")}
              </label>
              <input
                id="admin-new-display-name"
                type="text"
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
                placeholder={t("admin.tenants.displayName")}
                required
                className="apple-input text-xs w-full"
              />
              <label htmlFor="admin-new-contact-email" className="sr-only">
                {t("admin.tenants.contactEmail")}
              </label>
              <input
                id="admin-new-contact-email"
                type="email"
                value={newContactEmail}
                onChange={(e) => setNewContactEmail(e.target.value)}
                placeholder={t("admin.tenants.contactEmail")}
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
                {creating ? t("admin.tenants.creating") : t("admin.tenants.create")}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="text-center py-8">
          <p className="text-xs text-[var(--text-muted)] mb-2">{t("admin.tenants.loadFailed")}</p>
          <button onClick={() => void load()} className="apple-btn text-xs py-1 px-3 border border-[var(--border-default)]">
            {t("admin.common.retry")}
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="apple-card overflow-hidden" aria-busy="true" aria-live="polite">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--divider-light)]">
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">{t("admin.tenants.tenant")}</th>
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">{t("admin.common.status")}</th>
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">{t("admin.tenants.keys")}</th>
                <th className="text-left p-3 text-[var(--text-muted)] font-medium">{t("admin.common.created")}</th>
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
                {appliedQ ? t("admin.tenants.noMatch") : t("admin.tenants.empty")}
              </p>
            </div>
          ) : (
            <div className="apple-card overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--divider-light)]">
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">{t("admin.tenants.tenant")}</th>
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">{t("admin.common.status")}</th>
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">{t("admin.tenants.keys")}</th>
                    <th className="text-left p-3 text-[var(--text-muted)] font-medium">{t("admin.common.created")}</th>
                  </tr>
                </thead>
                <tbody>
                  {tenants.map((tenant) => (
                    <tr
                      key={tenant.id}
                      className="border-b border-[var(--divider-light)] last:border-0 hover:bg-[var(--bg-panel)] transition-colors"
                    >
                      <td className="p-3">
                        <Link
                          href={`/admin/tenants/${tenant.tenant_id}`}
                          className="no-underline"
                        >
                          <p className="font-medium text-[var(--text-h1)]">
                            {tenant.display_name}
                          </p>
                          <p className="text-[var(--text-muted)]">{tenant.tenant_id}</p>
                        </Link>
                      </td>
                      <td className="p-3">
                        <span
                          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] ${
                            tenant.status === "active"
                              ? "bg-[rgba(120,175,140,0.12)] text-[var(--jade-accent)]"
                              : "bg-[rgba(208,78,90,0.1)] text-[var(--crimson-mist)]"
                          }`}
                        >
                          <Circle size={6} weight="fill" />
                          {t(tenant.status === "active" ? "admin.common.active" : "admin.common.disabled")}
                        </span>
                      </td>
                      <td className="p-3 text-[var(--text-body)]">{tenant.key_count}</td>
                      <td className="p-3 text-[var(--text-muted)]">
                        {tenant.created_at
                          ? new Date(tenant.created_at).toLocaleDateString()
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
                {t("admin.tenants.total").replace("{count}", String(total))}
              </span>
              <div className="flex gap-1">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                  className="apple-btn text-xs py-1 px-2 border border-[var(--border-default)] disabled:opacity-30"
                >
                  {t("admin.common.previous")}
                </button>
                <button
                  disabled={page * 20 >= total}
                  onClick={() => setPage(page + 1)}
                  className="apple-btn text-xs py-1 px-2 border border-[var(--border-default)] disabled:opacity-30"
                >
                  {t("admin.common.next")}
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
