"use client";

import { useEffect, useRef, useState } from "react";
import { Key, ArrowRight, WarningCircle, Clock } from "@phosphor-icons/react";
import { getApiKey, setApiKey, apiFetch } from "./api";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  onUnlock: () => void;
}

export default function ApiKeyGate({ onUnlock }: Props) {
  const { t } = useI18n();
  const [input, setInput] = useState(() => getApiKey());
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const submitLockRef = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("session_expired") === "1") {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSessionExpired(true);
      params.delete("session_expired");
      const newSearch = params.toString();
      const newUrl = window.location.pathname + (newSearch ? "?" + newSearch : "");
      window.history.replaceState(null, "", newUrl);
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitLockRef.current) return;
    const trimmed = input.trim();
    if (!trimmed) {
      setError(t("apiGate.errorEmpty"));
      return;
    }
    submitLockRef.current = true;
    setVerifying(true);
    setError(null);
    setSessionExpired(false);
    setApiKey(trimmed);
    try {
      const res = await apiFetch("/distribution/platforms");
      if (res.status === 401) {
        setError(t("apiGate.errorInvalid"));
        setApiKey("");
        return;
      }
      if (!res.ok) {
        setError(`${t("apiGate.errorGeneric")} (HTTP ${res.status})`);
        setApiKey("");
        return;
      }
      onUnlock();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t("apiGate.errorNetworkFallback");
      setError(`${t("apiGate.errorNetwork")}: ${msg}`);
      setApiKey("");
    } finally {
      submitLockRef.current = false;
      setVerifying(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center px-4"
      style={{ background: "radial-gradient(ellipse at 30% 20%, rgba(215,92,112,0.10) 0%, #FDF8F6 55%, #FCF5F2 100%)" }}
    >
      <form
        onSubmit={handleSubmit}
        className="apple-card w-full max-w-md p-8 flex flex-col gap-5"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-[rgba(215,92,112,0.12)] flex items-center justify-center">
            <Key size={20} weight="fill" className="text-[var(--fortune-red)]" />
          </div>
          <div>
            <div className="text-[16px] font-semibold text-[var(--text-h1)]">{t("apiGate.title")}</div>
            <div className="text-[12px] text-[var(--text-muted)] mt-0.5">{t("apiGate.subtitle")}</div>
          </div>
        </div>

        {sessionExpired && (
          <div role="alert" className="flex items-start gap-2 px-3 py-2 rounded-lg border border-[var(--neon-red)]/40 bg-[var(--neon-red)]/8">
            <Clock size={14} weight="fill" className="shrink-0 mt-0.5 text-[var(--neon-red)]" />
            <span className="text-[12px] text-[var(--neon-red)]">{t("apiGate.sessionExpired")}</span>
          </div>
        )}

        <div className="flex flex-col gap-2">
          <label htmlFor="apikey-input" className="text-[12px] font-medium text-[var(--text-body)]">X-API-Key</label>
          <input
            id="apikey-input"
            type="password"
            value={input}
            onChange={(e) => { setInput(e.target.value); if (error) setError(null); }}
            placeholder={t("apiGate.placeholder")}
            disabled={verifying}
            autoFocus
            aria-invalid={!!error}
            aria-describedby={error ? "apikey-input-err" : undefined}
            className={`px-4 py-2.5 rounded-lg bg-[var(--bg-panel)] border text-[14px] text-[var(--text-h1)] focus:outline-none disabled:opacity-50 transition-colors ${
              error ? "border-[var(--neon-red)] focus:border-[var(--neon-red)]" : "border-[var(--border-default)] focus:border-[var(--fortune-red)]"
            }`}
          />
          {error && (
            <div id="apikey-input-err" role="alert" className="flex items-start gap-2 text-[12px] text-[var(--neon-red)]">
              <WarningCircle size={14} weight="fill" className="shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={verifying || !input.trim()}
          aria-busy={verifying}
          className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-[14px] font-medium bg-[var(--fortune-red)] text-white hover:bg-[var(--fortune-red-600)] active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {verifying && (
            <span className="inline-block w-3 h-3 rounded-full border-2 border-white/40 border-t-white animate-spin" aria-hidden="true" />
          )}
          {verifying ? t("apiGate.verifying") : t("apiGate.enter")}
          {!verifying && <ArrowRight size={16} weight="bold" />}
        </button>

        <div className="text-[11px] text-[var(--text-placeholder)] leading-relaxed pt-1 border-t border-[var(--border-default)]">
          {t("apiGate.hint")}
        </div>
      </form>
    </div>
  );
}
