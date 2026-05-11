"use client";

import { useState, useEffect } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import {
  getApiBase,
  getApiKey,
  isDemoMode,
  setApiBase,
  setApiKey,
  setDemoMode,
  resetApiConfig,
  testConnection,
} from "./api";
import { X, Check, WarningCircle, ArrowCounterClockwise, HardDrives, Key, Lightning } from "@phosphor-icons/react";
import { ConfirmModal } from "./ConfirmModal";

interface Props {
  onClose: () => void;
}

export default function SettingsPanel({ onClose }: Props) {
  const { t } = useI18n();
  const [baseUrl, setBaseUrl] = useState(getApiBase());
  const [key, setKey] = useState(getApiKey());
  const [demo, setDemo] = useState(isDemoMode());
  const [testing, setTesting] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok?: boolean;
    message?: string;
  } | null>(null);

  useEffect(() => {
    setBaseUrl(getApiBase());
    setKey(getApiKey());
    setDemo(isDemoMode());
  }, []);

  const handleSave = () => {
    setApiBase(baseUrl.trim());
    setApiKey(key.trim());
    setDemoMode(demo);
    setTestResult(null);
    onClose();
  };

  const handleReset = () => {
    setShowResetConfirm(true);
  };

  const confirmReset = () => {
    resetApiConfig();
    setBaseUrl(getApiBase());
    setKey(getApiKey());
    setDemo(isDemoMode());
    setTestResult(null);
    setShowResetConfirm(false);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    // Temporarily set values for the test
    const prevBase = getApiBase();
    const prevKey = getApiKey();
    setApiBase(baseUrl.trim());
    setApiKey(key.trim());
    try {
      const result = await testConnection();
      if (result.ok) {
        const data = result.data || {};
        const parts: string[] = [];
        if (data.status) parts.push(String(data.status).toUpperCase());
        if (data.version) parts.push("v" + data.version);
        const persistence = data.persistence?.backend;
        if (persistence) parts.push(persistence);
        const remotion = data.remotion;
        const renderUnavailable = remotion && remotion.available === false;
        const summary = parts.length > 0 ? parts.join(" · ") : "OK";
        setTestResult({
          ok: true,
          message: renderUnavailable
            ? "Connected — " + summary + " · " + t("settings.renderUnavailable")
            : "Connected — " + summary,
        });
      } else {
        setTestResult({ ok: false, message: result.error || "Connection failed (" + result.status + ")" });
      }
    } catch (e: any) {
      setTestResult({ ok: false, message: e.message || "Unknown error" });
    } finally {
      // Restore previous values if user hasn't saved yet
      setApiBase(prevBase);
      setApiKey(prevKey);
      setTesting(false);
    }
  };

  return (
    <div className="apple-modal-overlay" onClick={onClose}>
      <div
        className="apple-card w-full max-w-md mx-4 flex flex-col animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--divider-light)]">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-[rgba(215,92,112,0.12)] flex items-center justify-center shadow-[0_0_8px_rgba(215,92,112,0.18)]">
              <HardDrives size={16} weight="fill" className="text-[var(--fortune-red)]" />
            </div>
            <h2 className="text-base font-semibold text-[var(--text-h1)]">API Configuration</h2>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg hover:bg-[var(--bg-panel)] flex items-center justify-center cursor-pointer"
          >
            <X size={16} weight="fill" className="text-[var(--text-muted)]" />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-4">
          {/* Backend URL */}
          <div>
            <label className="flex items-center gap-1.5 text-[12px] font-medium text-[var(--text-body)] mb-1.5">
              <HardDrives size={12} weight="fill" />
              Backend URL
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://your-backend.onrender.com"
              className="apple-input text-sm"
            />
            <p className="text-[12px] text-[var(--text-muted)] mt-1">
              e.g. https://lute-ai-video-backend.onrender.com or http://localhost:8001
            </p>
          </div>

          {/* API Key */}
          <div>
            <label className="flex items-center gap-1.5 text-[12px] font-medium text-[var(--text-body)] mb-1.5">
              <Key size={12} weight="fill" />
              API Key
            </label>
            <input
              type="text"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="ai_video_demo_2026"
              className="apple-input text-sm"
            />
            <p className="text-[12px] text-[var(--text-muted)] mt-1">
              Must match the API_KEY environment variable on your backend.
            </p>
          </div>

          {/* Demo mode toggle */}
          <div className="flex items-center justify-between p-3 rounded-xl bg-[var(--bg-panel)]">
            <div className="flex items-center gap-2">
              <Lightning size={16} weight="fill" className="text-[var(--gold-foil)]" />
              <div>
                <p className="text-xs font-medium text-[var(--text-h1)]">Demo Mode</p>
                <p className="text-[12px] text-[var(--text-muted)]">Skip API calls, use mock data</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={demo}
                onChange={(e) => setDemo(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-10 h-5.5 bg-[var(--bg-layer3)] rounded-full peer peer-checked:bg-[var(--neon-red)] peer-checked:shadow-[0_0_10px_rgba(215,92,112,0.45)] transition-colors after:content-[''] after:absolute after:top-[3px] after:left-[3px] after:w-[18px] after:h-[18px] after:bg-white after:rounded-full after:transition-all peer-checked:after:translate-x-[18px]" />
            </label>
          </div>

          {/* Test connection */}
          <button
            onClick={handleTest}
            disabled={testing || !baseUrl.trim()}
            className="w-full apple-btn text-xs py-2 border border-[var(--border-default)] hover:bg-[var(--bg-panel)] disabled:opacity-50 text-[var(--text-body)]"
          >
            {testing ? (
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 border-2 border-[var(--text-muted)] border-t-transparent rounded-full animate-spin" />
                Testing...
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <HardDrives size={16} weight="fill" />
                Test Connection
              </span>
            )}
          </button>

          {/* Test result */}
          {testResult && (
            <div
              className={`flex items-center gap-2 p-2.5 rounded-lg text-xs ${
                testResult.ok
                  ? "bg-[rgba(120,175,140,0.12)] text-[var(--jade-accent)]"
                  : "bg-[rgba(208,78,90,0.12)] text-[var(--crimson-mist)]"
              }`}
            >
              {testResult.ok ? (
                <Check size={16} weight="fill" className="shrink-0" />
              ) : (
                <WarningCircle size={16} weight="fill" className="shrink-0" />
              )}
              <span className="break-all">{testResult.message}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-[var(--divider-light)]">
          <button
            onClick={handleReset}
            className="flex items-center gap-1 text-[12px] text-[var(--text-muted)] hover:text-[var(--text-h1)] transition-colors cursor-pointer"
          >
            <ArrowCounterClockwise size={12} weight="fill" />
            Reset Defaults
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="apple-btn text-xs py-2 px-3 bg-[var(--bg-panel)] text-[var(--text-body)] border border-[var(--border-default)]"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              className="apple-btn apple-btn-primary text-xs py-2 px-3"
            >
              Save
            </button>
          </div>
        </div>
      </div>
      <ConfirmModal
        open={showResetConfirm}
        title={t("confirm.resetSettings.title", "重置 API 设置？")}
        body={t("confirm.resetSettings.body", "将清除自定义后端地址、API Key 和 Demo 模式开关，恢复为默认值。")}
        confirmLabel={t("confirm.resetSettings.yes", "确认重置")}
        confirmVariant="danger"
        cancelLabel={t("confirm.cancel", "取消")}
        onConfirm={confirmReset}
        onCancel={() => setShowResetConfirm(false)}
      />
    </div>
  );
}
