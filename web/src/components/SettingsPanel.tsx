"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { useSubmitting } from "@/hooks/useSubmitting";
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
import {
  X,
  Check,
  WarningCircle,
  ArrowCounterClockwise,
  HardDrives,
  Key,
  Lightning,
  Globe,
  Database,
  ShieldCheck,
  Cloud,
  VideoCamera,
} from "@phosphor-icons/react";
import { ConfirmModal } from "./ConfirmModal";

interface Props {
  onClose: () => void;
}

type SettingsTab = "access" | "providers" | "advanced";

const TABS: Array<{
  id: SettingsTab;
  label: string;
  description: string;
  icon: typeof HardDrives;
}> = [
  {
    id: "access",
    label: "settings.tabs.access.label",
    description: "settings.tabs.access.desc",
    icon: Globe,
  },
  {
    id: "providers",
    label: "settings.tabs.providers.label",
    description: "settings.tabs.providers.desc",
    icon: Key,
  },
  {
    id: "advanced",
    label: "settings.tabs.advanced.label",
    description: "settings.tabs.advanced.desc",
    icon: Lightning,
  },
];

const PROVIDERS = [
  { label: "Text", value: "DeepSeek", icon: Database },
  { label: "Image", value: "poyo.ai GPT Image", icon: Cloud },
  { label: "Video", value: "poyo.ai Seedance", icon: VideoCamera },
  { label: "Voice", value: "SiliconFlow CosyVoice", icon: ShieldCheck },
] as const;

function maskSecret(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "Not set";
  if (trimmed.length <= 8) return "Set";
  return `${trimmed.slice(0, 4)}····${trimmed.slice(-3)}`;
}

function safeHostname(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "Not configured";
  try {
    return new URL(trimmed).host;
  } catch {
    return trimmed;
  }
}

function PanelCard({
  title,
  description,
  children,
  icon: Icon,
  extra,
  accent = false,
}: {
  title: string;
  description: string;
  children: ReactNode;
  icon: typeof HardDrives;
  extra?: ReactNode;
  accent?: boolean;
}) {
  return (
    <section
      className={`rounded-2xl border p-4 shadow-sm ${
        accent
          ? "border-[rgba(215,92,112,0.20)] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(253,240,242,0.96))]"
          : "border-[var(--border-default)] bg-[var(--bg-card)]"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <span
            className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${
              accent
                ? "bg-[rgba(215,92,112,0.12)] text-[var(--fortune-red)]"
                : "bg-[var(--bg-panel)] text-[var(--text-body)]"
            }`}
          >
            <Icon size={16} weight="fill" />
          </span>
          <div className="min-w-0">
            <h3 className="text-[14px] font-semibold text-[var(--text-h1)]">{title}</h3>
            <p className="mt-0.5 text-[12px] leading-5 text-[var(--text-muted)]">{description}</p>
          </div>
        </div>
        {extra}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export default function SettingsPanel({ onClose }: Props) {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<SettingsTab>("access");
  const [baseUrl, setBaseUrl] = useState(getApiBase());
  const [key, setKey] = useState(getApiKey());
  const [demo, setDemo] = useState(isDemoMode());
  const { submitting: testing, wrap: wrapTest } = useSubmitting();
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok?: boolean;
    message?: string;
  } | null>(null);
  const title = t("settings.title", "Settings");
  const demoBadge = demo ? t("settings.badge.demo", "Demo mode") : t("settings.badge.live", "Live mode");
  const summaryDescription = t(
    "settings.description",
    "Manage the backend endpoint, local key storage, and model mode for this browser session."
  );
  const accessCardTitle = t("settings.access.card.title", "Backend access");
  const accessCardDesc = t(
    "settings.access.card.desc",
    "Point the interface at a local FastAPI endpoint or the production host."
  );
  const accessUrlLabel = t("settings.access.url.label", "Backend URL");
  const accessUrlHint = t("settings.access.url.hint", "Production domain or local FastAPI endpoint.");
  const accessKeyLabel = t("settings.access.key.label", "API Key");
  const accessKeyHint = t("settings.access.key.hint", "Use a tenant key or the local test bundle key.");
  const testLabel = t("settings.actions.test", "Test connection");
  const testingLabel = t("settings.actions.testing", "Testing connection");
  const resetLabel = t("settings.actions.reset", "Reset defaults");
  const liveSnapshotTitle = t("settings.snapshot.card.title", "Live snapshot");
  const liveSnapshotDesc = t(
    "settings.snapshot.card.desc",
    "Current values are held in browser storage until you save or reset."
  );
  const hostLabel = t("settings.snapshot.hostValue", "Host");
  const modeLabel = t("settings.snapshot.mode", "Mode");
  const secretLengthLabel = t("settings.snapshot.secretLength", "Secret length");
  const providerDemoTitle = t("settings.providers.demo.title", "Demo mode");
  const providerDemoDesc = t(
    "settings.providers.demo.desc",
    "Keep the UI in mock-data mode while testing layout, flows, or docs."
  );
  const providerStackTitle = t("settings.providers.stack.title", "Provider stack");
  const providerStackDesc = t(
    "settings.providers.stack.desc",
    "The pipeline keeps one upstream service per generation layer."
  );
  const currentModeTitle = t("settings.providers.mode.title", "Current mode");
  const currentModeDesc = t(
    "settings.providers.mode.desc",
    "Use this as a quick visual cue before saving and leaving the dialog."
  );
  const currentModeStatusLabel = t("settings.providers.mode.status", "Status");
  const currentModeCoverageLabel = t("settings.providers.mode.coverage", "Coverage");
  const providerCoverageValue = t(
    "settings.providers.coverage.value",
    "Text, image, video, and voice providers"
  );
  const advancedCardTitle = t("settings.advanced.card.title", "Browser storage");
  const advancedCardDesc = t(
    "settings.advanced.card.desc",
    "Backend URL, API key, and demo mode are stored only in this browser."
  );
  const advancedCardBody = t(
    "settings.advanced.card.body",
    "This panel does not sync secrets across devices or sessions."
  );
  const cancelLabel = t("settings.footer.cancel", t("common.cancel", "Cancel"));
  const saveLabel = t("settings.footer.save", t("common.save", "Save"));

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
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

  const handleTest = () =>
    wrapTest(async () => {
      setTestResult(null);
      const prevBase = getApiBase();
      const prevKey = getApiKey();
      setApiBase(baseUrl.trim());
      setApiKey(key.trim());
      try {
        const result = await testConnection();
        if (result.ok) {
          const data = (result.data || {}) as {
            status?: string;
            version?: string;
            persistence?: { backend?: string };
            remotion?: { available?: boolean };
          };
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
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        setTestResult({ ok: false, message: msg || "Unknown error" });
      } finally {
        setApiBase(prevBase);
        setApiKey(prevKey);
      }
    });

  return (
    <div className="apple-modal-overlay" onClick={onClose}>
      <div
        className="apple-card w-full max-w-2xl mx-4 flex max-h-[90vh] flex-col overflow-hidden animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-[var(--divider-light)] bg-[linear-gradient(180deg,rgba(255,255,255,0.95),rgba(252,245,242,0.94))] px-5 py-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex min-w-0 items-start gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[rgba(215,92,112,0.12)] shadow-[0_0_14px_rgba(215,92,112,0.12)]">
                <HardDrives size={20} weight="fill" className="text-[var(--fortune-red)]" />
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-[18px] font-semibold text-[var(--text-h1)]">{title}</h2>
                  <span className="rounded-full border border-[rgba(215,92,112,0.14)] bg-[rgba(215,92,112,0.06)] px-2 py-0.5 text-[11px] font-medium text-[var(--fortune-red)]">
                    {demoBadge}
                  </span>
                </div>
                <p className="mt-1 max-w-[38rem] text-[13px] leading-5 text-[var(--text-body)]">{summaryDescription}</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-panel)] hover:text-[var(--text-h1)]"
            >
              <X size={16} weight="bold" />
            </button>
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            <div className="rounded-xl border border-[var(--divider-light)] bg-white/80 px-3 py-2">
              <p className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-muted)]">{t("settings.snapshot.host", "Target host")}</p>
              <p className="mt-1 truncate text-[12px] font-medium text-[var(--text-h1)]">{safeHostname(baseUrl)}</p>
            </div>
            <div className="rounded-xl border border-[var(--divider-light)] bg-white/80 px-3 py-2">
              <p className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-muted)]">{t("settings.snapshot.apiKey", "API Key")}</p>
              <p className="mt-1 truncate text-[12px] font-medium text-[var(--text-h1)]">{maskSecret(key)}</p>
            </div>
            <div className="rounded-xl border border-[var(--divider-light)] bg-white/80 px-3 py-2">
              <p className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-muted)]">{t("settings.snapshot.storage", "Storage")}</p>
              <p className="mt-1 truncate text-[12px] font-medium text-[var(--text-h1)]">{t("settings.snapshot.storageValue", "Browser-local only")}</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-2 border-b border-[var(--divider-light)] bg-[var(--bg-panel)] p-2 sm:grid-cols-3">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const selected = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`flex h-[68px] flex-col items-center justify-center gap-1 rounded-xl border px-3 text-center transition-all ${
                  selected
                    ? "border-[rgba(215,92,112,0.28)] bg-[rgba(255,255,255,0.96)] text-[var(--text-h1)] shadow-[0_2px_10px_rgba(215,92,112,0.08)]"
                    : "border-transparent text-[var(--text-muted)] hover:border-[var(--divider-light)] hover:bg-white/60 hover:text-[var(--text-body)]"
                }`}
              >
                <Icon size={16} weight="fill" className={selected ? "text-[var(--fortune-red)]" : ""} />
                <span className="text-[12px] font-medium">{t(tab.label, tab.label)}</span>
                <span className="text-[11px] leading-4">{t(tab.description, tab.description)}</span>
              </button>
            );
          })}
        </div>

        <div className="max-h-[calc(90vh-260px)] overflow-y-auto p-4 sm:p-5">
          {activeTab === "access" && (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(240px,0.7fr)]">
              <div className="space-y-4">
                <PanelCard
                  title={accessCardTitle}
                  description={accessCardDesc}
                  icon={Globe}
                  accent
                >
                  <div className="space-y-4">
                    <div>
                      <label className="mb-1.5 flex items-center gap-1.5 text-[12px] font-medium text-[var(--text-body)]">
                        <HardDrives size={12} weight="fill" />
                        {accessUrlLabel}
                      </label>
                      <input
                        type="text"
                        value={baseUrl}
                        onChange={(e) => setBaseUrl(e.target.value)}
                        placeholder="https://video.lute-tlz-dddd.top"
                        className="apple-input text-sm"
                      />
                      <p className="mt-1 text-[12px] leading-5 text-[var(--text-muted)]">{accessUrlHint}</p>
                    </div>

                    <div>
                      <label className="mb-1.5 flex items-center gap-1.5 text-[12px] font-medium text-[var(--text-body)]">
                        <Key size={12} weight="fill" />
                        {accessKeyLabel}
                      </label>
                      <input
                        type="password"
                        value={key}
                        onChange={(e) => setKey(e.target.value)}
                        placeholder="ai_video_demo_2026"
                        className="apple-input text-sm"
                        autoComplete="off"
                      />
                      <p className="mt-1 text-[12px] leading-5 text-[var(--text-muted)]">{accessKeyHint}</p>
                    </div>
                  </div>
                </PanelCard>

                <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                  <button
                    onClick={handleTest}
                    disabled={testing || !baseUrl.trim()}
                    className="apple-btn apple-btn-primary inline-flex items-center justify-center gap-2 text-xs py-2.5 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {testing ? (
                      <>
                        <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/60 border-t-transparent" />
                        {testingLabel}
                      </>
                    ) : (
                      <>
                        <HardDrives size={15} weight="fill" />
                        {testLabel}
                      </>
                    )}
                  </button>
                  <button
                    onClick={handleReset}
                    className="apple-btn inline-flex items-center justify-center gap-2 border border-[rgba(208,78,90,0.25)] text-xs py-2.5 text-[var(--crimson-mist)] hover:bg-[rgba(208,78,90,0.06)]"
                  >
                    <ArrowCounterClockwise size={14} weight="fill" />
                    {resetLabel}
                  </button>
                </div>

                {testResult && (
                  <div
                    className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-xs ${
                      testResult.ok
                        ? "border-[rgba(120,175,140,0.18)] bg-[rgba(120,175,140,0.10)] text-[var(--jade-accent)]"
                        : "border-[rgba(208,78,90,0.18)] bg-[rgba(208,78,90,0.10)] text-[var(--crimson-mist)]"
                    }`}
                  >
                    {testResult.ok ? (
                      <Check size={16} weight="fill" className="mt-0.5 shrink-0" />
                    ) : (
                      <WarningCircle size={16} weight="fill" className="mt-0.5 shrink-0" />
                    )}
                    <span className="break-words leading-5">{testResult.message}</span>
                  </div>
                )}
              </div>

              <div className="space-y-4">
                <PanelCard
                  title={liveSnapshotTitle}
                  description={liveSnapshotDesc}
                  icon={Database}
                >
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-3 rounded-xl bg-[var(--bg-panel)] px-3 py-2">
                      <span className="text-[12px] text-[var(--text-muted)]">{hostLabel}</span>
                      <span className="max-w-[11rem] truncate text-[12px] font-medium text-[var(--text-h1)]">
                        {safeHostname(baseUrl)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-3 rounded-xl bg-[var(--bg-panel)] px-3 py-2">
                      <span className="text-[12px] text-[var(--text-muted)]">{modeLabel}</span>
                      <span className="text-[12px] font-medium text-[var(--text-h1)]">
                        {demo ? t("settings.badge.demo", "Demo mode") : t("settings.badge.live", "Live mode")}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-3 rounded-xl bg-[var(--bg-panel)] px-3 py-2">
                      <span className="text-[12px] text-[var(--text-muted)]">{secretLengthLabel}</span>
                      <span className="text-[12px] font-medium text-[var(--text-h1)]">{key.trim().length || 0}</span>
                    </div>
                  </div>
                </PanelCard>
              </div>
            </div>
          )}

          {activeTab === "providers" && (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(240px,0.9fr)]">
              <div className="space-y-4">
                <PanelCard
                  title={providerDemoTitle}
                  description={providerDemoDesc}
                  icon={Lightning}
                  accent
                  extra={
                    <label className="relative inline-flex cursor-pointer items-center shrink-0">
                      <input
                        type="checkbox"
                        checked={demo}
                        onChange={(e) => setDemo(e.target.checked)}
                        className="peer sr-only"
                      />
                      <div className="h-5.5 w-10 rounded-full bg-[var(--bg-layer3)] transition-colors after:absolute after:left-[3px] after:top-[3px] after:h-[18px] after:w-[18px] after:rounded-full after:bg-white after:transition-all peer-checked:bg-[var(--neon-red)] peer-checked:shadow-[0_0_10px_rgba(215,92,112,0.35)] peer-checked:after:translate-x-[18px]" />
                    </label>
                  }
                >
                  <p className="text-[12px] leading-5 text-[var(--text-muted)]">{providerDemoDesc}</p>
                </PanelCard>

                <PanelCard
                  title={providerStackTitle}
                  description={providerStackDesc}
                  icon={HardDrives}
                >
                  <div className="grid gap-2">
                    {PROVIDERS.map(({ label, value, icon: Icon }) => (
                      <div
                        key={label}
                        className="flex items-center justify-between gap-3 rounded-xl border border-[var(--divider-light)] bg-[var(--bg-panel)] px-3 py-2.5"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white text-[var(--fortune-red)]">
                            <Icon size={14} weight="fill" />
                          </span>
                          <span className="text-[12px] font-medium text-[var(--text-h1)]">{label}</span>
                        </div>
                        <span className="truncate text-right text-[12px] text-[var(--text-body)]">{value}</span>
                      </div>
                    ))}
                  </div>
                </PanelCard>
              </div>

              <div className="space-y-4">
                <PanelCard
                  title={currentModeTitle}
                  description={currentModeDesc}
                  icon={ShieldCheck}
                >
                  <div className="space-y-2">
                    <div className="rounded-xl bg-[var(--bg-panel)] px-3 py-2.5">
                      <p className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-muted)]">{currentModeStatusLabel}</p>
                      <p className="mt-1 text-[13px] font-medium text-[var(--text-h1)]">
                        {demo ? t("settings.badge.demo", "Demo mode") : t("settings.badge.live", "Live mode")}
                      </p>
                    </div>
                    <div className="rounded-xl bg-[var(--bg-panel)] px-3 py-2.5">
                      <p className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-muted)]">{currentModeCoverageLabel}</p>
                      <p className="mt-1 text-[13px] font-medium text-[var(--text-h1)]">{providerCoverageValue}</p>
                    </div>
                  </div>
                </PanelCard>
              </div>
            </div>
          )}

          {activeTab === "advanced" && (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
              <PanelCard
                title={advancedCardTitle}
                description={advancedCardDesc}
                icon={Database}
                accent
              >
                <p className="text-[12px] leading-5 text-[var(--text-muted)]">{advancedCardBody}</p>
              </PanelCard>

              <button
                onClick={handleReset}
                className="apple-btn inline-flex items-center justify-center gap-2 border border-[rgba(208,78,90,0.35)] px-4 py-3 text-xs text-[var(--crimson-mist)] hover:bg-[rgba(208,78,90,0.08)]"
              >
                <ArrowCounterClockwise size={14} weight="fill" />
                {resetLabel}
              </button>
            </div>
          )}
        </div>

        <div className="border-t border-[var(--divider-light)] bg-[var(--bg-card)] px-5 py-4">
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={onClose}
              className="apple-btn border border-[var(--border-default)] bg-[var(--bg-panel)] px-3 py-2 text-xs text-[var(--text-body)]"
            >
              {cancelLabel}
            </button>
            <button onClick={handleSave} className="apple-btn apple-btn-primary px-4 py-2 text-xs">
              {saveLabel}
            </button>
          </div>
        </div>
      </div>

      <ConfirmModal
        open={showResetConfirm}
        title={t("confirm.resetSettings.title", "Reset API settings?")}
        body={t(
          "confirm.resetSettings.body",
          "This clears the custom backend URL, API key, and demo mode toggle and restores the defaults."
        )}
        confirmLabel={t("confirm.resetSettings.yes", "Reset")}
        confirmVariant="danger"
        cancelLabel={cancelLabel}
        onConfirm={confirmReset}
        onCancel={() => setShowResetConfirm(false)}
      />
    </div>
  );
}
