"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { adminFetchJson } from "@/components/api";
import { errorMessage } from "@/lib/errors";
import { useI18n } from "@/i18n/I18nProvider";
import { useModalBehavior } from "@/hooks/useModalBehavior";
import {
  ArrowLeft,
  Key,
  Trash,
  Copy,
  Eye,
  EyeSlash,
  X,
  WarningCircle,
} from "@phosphor-icons/react";

interface ApiKey {
  id: string;
  key_preview: string;
  label: string;
  status: string;
  created_at: string | null;
  expires_at: string | null;
  last_used_at: string | null;
}

interface TenantDetail {
  id: string;
  tenant_id: string;
  display_name: string;
  contact_email: string;
  status: string;
  keys: ApiKey[];
}

function defaultExpiryDate(): string {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() + 90);
  return value.toISOString().slice(0, 10);
}

export default function AdminTenantDetailClient({ tenantId }: { tenantId: string }) {
  const { t } = useI18n();
  const [data, setData] = useState<TenantDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Key creation
  const [showCreateKey, setShowCreateKey] = useState(false);
  const [keyLabel, setKeyLabel] = useState("");
  const [keyExpiresAt, setKeyExpiresAt] = useState(defaultExpiryDate);
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [keyVisible, setKeyVisible] = useState(false);

  // Disable confirm
  const [showDisable, setShowDisable] = useState(false);
  const [disableConfirm, setDisableConfirm] = useState("");
  const disableDialogRef = useRef<HTMLButtonElement>(null);
  const createKeyDialogRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await adminFetchJson<TenantDetail>(
        `/api/admin/tenants/${tenantId}`
      );
      setData(result);
    } catch {
      setError("load_failed");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  const closeDisable = useCallback(() => {
    setShowDisable(false);
    setDisableConfirm("");
  }, []);
  const closeCreateKey = useCallback(() => {
    setShowCreateKey(false);
    if (newKey) void load();
  }, [load, newKey]);

  useModalBehavior({
    open: showDisable,
    onClose: closeDisable,
    initialFocusRef: disableDialogRef,
  });
  useModalBehavior({
    open: showCreateKey,
    onClose: closeCreateKey,
    initialFocusRef: createKeyDialogRef,
  });

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const result = await adminFetchJson<{
        id: string;
        api_key: string;
      }>(`/api/admin/tenants/${tenantId}/keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: keyLabel.trim(),
          expires_at: `${keyExpiresAt}T23:59:59Z`,
        }),
      });
      setNewKey(result.api_key);
      setKeyVisible(false);
    } catch (err: unknown) {
      alert(errorMessage(err, t("admin.tenant.createKeyFailed")));
    } finally {
      setCreating(false);
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    if (!confirm(t("admin.tenant.revokeConfirm"))) return;
    try {
      await adminFetchJson(
        `/api/admin/tenants/${tenantId}/keys/${keyId}/revoke`,
        { method: "POST" }
      );
      void load();
    } catch (err: unknown) {
      alert(errorMessage(err, t("admin.tenant.revokeKeyFailed")));
    }
  };

  const handleToggleStatus = async () => {
    const newStatus = data?.status === "active" ? "disabled" : "active";
    if (
      newStatus === "disabled" &&
      !confirm(
        t("admin.tenant.disableConfirm")
      )
    ) {
      return;
    }
    try {
      await adminFetchJson(`/api/admin/tenants/${tenantId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      void load();
      setShowDisable(false);
    } catch (err: unknown) {
      alert(errorMessage(err, t("admin.tenant.updateFailed")));
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <div className="w-5 h-5 border-2 border-[var(--fortune-red)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="text-center py-16">
        <p className="text-xs text-[var(--text-muted)] mb-2">
          {error ? t("admin.tenant.loadFailed") : t("admin.tenant.notFound")}
        </p>
        <Link href="/admin/tenants" className="apple-btn text-xs py-1.5 px-3 border border-[var(--border-default)] no-underline">
          {t("admin.tenant.back")}
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Back link */}
      <Link
        href="/admin/tenants"
        className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--fortune-red)] no-underline transition-colors"
      >
        <ArrowLeft size={12} weight="fill" />
        {t("admin.tenant.back")}
      </Link>

      <h1 className="text-lg font-semibold text-[var(--text-h1)]">
        {data.display_name}
      </h1>

      {/* Info card */}
      <div className="apple-card p-4 space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-[var(--text-muted)]">{t("admin.tenant.tenantId")}</p>
            <p className="text-sm font-mono text-[var(--text-h1)]">
              {data.tenant_id}
            </p>
          </div>
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${
              data.status === "active"
                ? "bg-[rgba(120,175,140,0.12)] text-[var(--jade-accent)]"
                : "bg-[rgba(208,78,90,0.1)] text-[var(--crimson-mist)]"
            }`}
          >
            {t(data.status === "active" ? "admin.common.active" : "admin.common.disabled")}
          </span>
        </div>
        <div>
          <p className="text-xs text-[var(--text-muted)]">{t("admin.tenant.contact")}</p>
          <p className="text-sm text-[var(--text-body)]">
            {data.contact_email || "—"}
          </p>
        </div>
        <button
          onClick={() => setShowDisable(true)}
          className={`apple-btn text-xs py-1.5 px-3 border ${
            data.status === "active"
              ? "border-[var(--crimson-mist)] text-[var(--crimson-mist)]"
              : "border-[var(--jade-accent)] text-[var(--jade-accent)]"
          }`}
        >
          {data.status === "active" ? t("admin.tenant.disable") : t("admin.tenant.enable")}
        </button>
      </div>

      {/* API Keys */}
      <div className="apple-card p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-[var(--text-h1)]">
            {t("admin.tenant.apiKeys")} ({data.keys.length})
          </h2>
          <button
            onClick={() => {
              setShowCreateKey(true);
              setNewKey(null);
              setKeyLabel("");
              setKeyExpiresAt(defaultExpiryDate());
            }}
            className="flex items-center gap-1 apple-btn apple-btn-primary text-xs py-1 px-2"
          >
            <Key size={12} weight="fill" />
            {t("admin.tenant.newKey")}
          </button>
        </div>

        {data.keys.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)] py-4 text-center">
            {t("admin.tenant.noKeys")}
          </p>
        ) : (
          <div className="space-y-1">
            {data.keys.map((key) => (
              <div
                key={key.id}
                className="flex items-center justify-between p-2 rounded bg-[var(--bg-panel)]"
              >
                <div className="min-w-0">
                  <p className="text-xs font-mono text-[var(--text-body)]">
                    {key.key_preview}
                    {key.label ? ` · ${key.label}` : ""}
                  </p>
                  <p className="text-[11px] text-[var(--text-muted)]">
                    {t(
                      key.status === "active"
                        ? "admin.common.active"
                        : key.status === "revoked"
                          ? "admin.common.revoked"
                          : "admin.common.disabled",
                    )}
                    {key.last_used_at
                      ? ` · ${t("admin.tenant.lastUsed").replace(
                          "{date}",
                          new Date(key.last_used_at).toLocaleDateString(),
                        )}`
                      : ""}
                    {key.expires_at
                      ? ` · ${t("admin.tenant.expires").replace(
                          "{date}",
                          new Date(key.expires_at).toLocaleDateString(),
                        )}`
                      : ""}
                  </p>
                </div>
                {key.status === "active" && (
                  <button
                    onClick={() => handleRevokeKey(key.id)}
                    aria-label={t("admin.tenant.revokeKey").replace("{key}", key.key_preview)}
                    className="cursor-pointer text-[var(--text-muted)] hover:text-[var(--crimson-mist)] transition-colors"
                  >
                    <Trash size={14} weight="fill" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Disable confirm modal */}
      {showDisable && (
        <div className="apple-modal-overlay" onClick={closeDisable}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-tenant-status-dialog-title"
            className="apple-card w-full max-w-sm mx-4 p-4 animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="admin-tenant-status-dialog-title" className="text-sm font-semibold text-[var(--text-h1)] mb-2">
              {data.status === "active" ? t("admin.tenant.disableTitle") : t("admin.tenant.enableTitle")}
            </h2>
            {data.status === "active" && (
              <>
                <p className="text-xs text-[var(--text-muted)] mb-3">
                  {t("admin.tenant.disableBody")}
                </p>
                <input
                  type="text"
                  aria-label={t("admin.tenant.confirmTenantId")}
                  value={disableConfirm}
                  onChange={(e) => setDisableConfirm(e.target.value)}
                  placeholder={data.tenant_id}
                  className="apple-input text-xs w-full mb-3"
                />
              </>
            )}
            <div className="flex gap-2 justify-end">
              <button
                ref={disableDialogRef}
                onClick={closeDisable}
                className="apple-btn text-xs py-1.5 px-3 border border-[var(--border-default)]"
              >
                {t("admin.tenant.cancel")}
              </button>
              <button
                onClick={handleToggleStatus}
                disabled={
                  data.status === "active" && disableConfirm !== data.tenant_id
                }
                className={`apple-btn text-xs py-1.5 px-3 disabled:opacity-30 ${
                  data.status === "active"
                    ? "bg-[var(--crimson-mist)] text-white"
                    : "bg-[var(--jade-accent)] text-white"
                }`}
              >
                {data.status === "active" ? t("admin.tenant.disableAction") : t("admin.tenant.enableAction")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create key modal */}
      {showCreateKey && (
        <div className="apple-modal-overlay" onClick={closeCreateKey}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-create-key-dialog-title"
            className="apple-card w-full max-w-sm mx-4 p-4 animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h2 id="admin-create-key-dialog-title" className="text-sm font-semibold text-[var(--text-h1)]">
                {newKey ? t("admin.tenant.keyCreated") : t("admin.tenant.createKey")}
              </h2>
              <button
                ref={createKeyDialogRef}
                onClick={closeCreateKey}
                className="cursor-pointer"
                aria-label={t("admin.tenant.closeKeyDialog")}
              >
                <X size={16} weight="fill" className="text-[var(--text-muted)]" />
              </button>
            </div>

            {newKey ? (
              <div className="space-y-3">
                <div className="p-3 rounded-lg bg-[rgba(215,92,112,0.06)] border border-[rgba(215,92,112,0.2)]">
                  <p className="text-[11px] text-[var(--text-muted)] mb-1">
                    {t("admin.tenant.copyNow")}
                  </p>
                  <div className="flex items-center gap-1">
                    <code className="flex-1 text-xs break-all bg-[var(--bg-layer3)] p-1.5 rounded font-mono">
                      {keyVisible ? newKey : "•".repeat(64)}
                    </code>
                    <button
                      onClick={() => setKeyVisible(!keyVisible)}
                      aria-label={t(keyVisible ? "admin.tenant.hideKey" : "admin.tenant.showKey")}
                      className="cursor-pointer text-[var(--text-muted)] hover:text-[var(--fortune-red)] p-1"
                    >
                      {keyVisible ? (
                        <EyeSlash size={14} weight="fill" />
                      ) : (
                        <Eye size={14} weight="fill" />
                      )}
                    </button>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(newKey);
                      }}
                      className="cursor-pointer text-[var(--text-muted)] hover:text-[var(--fortune-red)] p-1"
                      aria-label={t("admin.tenant.copyKey")}
                    >
                      <Copy size={14} weight="fill" />
                    </button>
                  </div>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-[var(--gold-foil)]">
                  <WarningCircle size={12} weight="fill" />
                  {t("admin.tenant.storeSecurely")}
                </div>
              </div>
            ) : (
              <form onSubmit={handleCreateKey} className="space-y-3">
                <input
                  type="text"
                  aria-label={t("admin.tenant.keyLabelAria")}
                  value={keyLabel}
                  onChange={(e) => setKeyLabel(e.target.value)}
                  placeholder={t("admin.tenant.keyLabel")}
                  className="apple-input text-xs w-full"
                />
                <label className="block text-xs text-[var(--text-muted)]">
                  {t("admin.tenant.expiresOn")}
                  <input
                    type="date"
                    required
                    min={new Date().toISOString().slice(0, 10)}
                    value={keyExpiresAt}
                    onChange={(event) => setKeyExpiresAt(event.target.value)}
                    className="apple-input text-xs w-full mt-1"
                  />
                </label>
                <button
                  type="submit"
                  disabled={creating}
                  className="apple-btn apple-btn-primary text-xs w-full py-2 disabled:opacity-50"
                >
                  {creating ? t("admin.tenant.generating") : t("admin.tenant.generateKey")}
                </button>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
