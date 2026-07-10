"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { adminFetchJson } from "@/components/api";
import { errorMessage } from "@/lib/errors";
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

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await adminFetchJson<TenantDetail>(
        `/api/admin/tenants/${tenantId}`
      );
      setData(result);
    } catch {
      setError("Failed to load tenant");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

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
      alert(errorMessage(err, "Failed to create key"));
    } finally {
      setCreating(false);
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    if (!confirm("Revoke this API key? This cannot be undone.")) return;
    try {
      await adminFetchJson(
        `/api/admin/tenants/${tenantId}/keys/${keyId}/revoke`,
        { method: "POST" }
      );
      void load();
    } catch (err: unknown) {
      alert(errorMessage(err, "Failed to revoke key"));
    }
  };

  const handleToggleStatus = async () => {
    const newStatus = data?.status === "active" ? "disabled" : "active";
    if (
      newStatus === "disabled" &&
      !confirm(
        "Disabling will immediately revoke ALL API keys. Continue?"
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
      alert(errorMessage(err, "Failed to update tenant"));
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
        <p className="text-xs text-[var(--text-muted)] mb-2">{error || "Not found"}</p>
        <Link href="/admin/tenants" className="apple-btn text-xs py-1.5 px-3 border border-[var(--border-default)] no-underline">
          Back to Tenants
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
        Back to Tenants
      </Link>

      <h1 className="text-lg font-semibold text-[var(--text-h1)]">
        {data.display_name}
      </h1>

      {/* Info card */}
      <div className="apple-card p-4 space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-[var(--text-muted)]">Tenant ID</p>
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
            {data.status}
          </span>
        </div>
        <div>
          <p className="text-xs text-[var(--text-muted)]">Contact</p>
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
          {data.status === "active" ? "Disable Tenant" : "Enable Tenant"}
        </button>
      </div>

      {/* API Keys */}
      <div className="apple-card p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-[var(--text-h1)]">
            API Keys ({data.keys.length})
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
            New Key
          </button>
        </div>

        {data.keys.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)] py-4 text-center">
            No API keys yet
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
                    {key.status}
                    {key.last_used_at
                      ? ` · last used ${new Date(key.last_used_at).toLocaleDateString()}`
                      : ""}
                    {key.expires_at
                      ? ` · expires ${new Date(key.expires_at).toLocaleDateString()}`
                      : ""}
                  </p>
                </div>
                {key.status === "active" && (
                  <button
                    onClick={() => handleRevokeKey(key.id)}
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
        <div className="apple-modal-overlay" onClick={() => setShowDisable(false)}>
          <div
            className="apple-card w-full max-w-sm mx-4 p-4 animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-sm font-semibold text-[var(--text-h1)] mb-2">
              {data.status === "active" ? "Disable" : "Enable"} Tenant
            </h2>
            {data.status === "active" && (
              <>
                <p className="text-xs text-[var(--text-muted)] mb-3">
                  This will immediately revoke all API keys. Type the tenant ID to confirm:
                </p>
                <input
                  type="text"
                  value={disableConfirm}
                  onChange={(e) => setDisableConfirm(e.target.value)}
                  placeholder={data.tenant_id}
                  className="apple-input text-xs w-full mb-3"
                />
              </>
            )}
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setShowDisable(false); setDisableConfirm(""); }}
                className="apple-btn text-xs py-1.5 px-3 border border-[var(--border-default)]"
              >
                Cancel
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
                {data.status === "active" ? "Disable" : "Enable"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create key modal */}
      {showCreateKey && (
        <div className="apple-modal-overlay" onClick={() => setShowCreateKey(false)}>
          <div
            className="apple-card w-full max-w-sm mx-4 p-4 animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">
                {newKey ? "API Key Created" : "Create API Key"}
              </h2>
              <button
                onClick={() => {
                  setShowCreateKey(false);
                  if (newKey) void load();
                }}
                className="cursor-pointer"
              >
                <X size={16} weight="fill" className="text-[var(--text-muted)]" />
              </button>
            </div>

            {newKey ? (
              <div className="space-y-3">
                <div className="p-3 rounded-lg bg-[rgba(215,92,112,0.06)] border border-[rgba(215,92,112,0.2)]">
                  <p className="text-[11px] text-[var(--text-muted)] mb-1">
                    Copy this key now — it will not be shown again:
                  </p>
                  <div className="flex items-center gap-1">
                    <code className="flex-1 text-xs break-all bg-[var(--bg-layer3)] p-1.5 rounded font-mono">
                      {keyVisible ? newKey : "•".repeat(64)}
                    </code>
                    <button
                      onClick={() => setKeyVisible(!keyVisible)}
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
                    >
                      <Copy size={14} weight="fill" />
                    </button>
                  </div>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-[var(--gold-foil)]">
                  <WarningCircle size={12} weight="fill" />
                  Store this key securely. You won&apos;t see it again.
                </div>
              </div>
            ) : (
              <form onSubmit={handleCreateKey} className="space-y-3">
                <input
                  type="text"
                  value={keyLabel}
                  onChange={(e) => setKeyLabel(e.target.value)}
                  placeholder="Key label (optional, e.g. production)"
                  className="apple-input text-xs w-full"
                />
                <label className="block text-xs text-[var(--text-muted)]">
                  Expires on
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
                  {creating ? "Generating..." : "Generate Key"}
                </button>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
