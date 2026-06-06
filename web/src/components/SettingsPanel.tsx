"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { useSubmitting } from "@/hooks/useSubmitting";
import {
  getApiBase,
  getApiKey,
  isDemoMode,
  maskApiKeyForDisplay,
  setApiBase,
  setApiKey,
  setDemoMode,
  resetApiConfig,
  testConnection,
  getModelProviderConfig,
  setModelProviderConfig,
  type ModelProviderConfig,
} from "./api";
import {
  MODEL_ROUTE_GROUPS,
  PROVIDER_KEY_SPECS,
  type ModelRouteGroup,
  type ProviderApiKeyName,
  type ProviderRouteStatus,
} from "@/lib/modelProviderConfig";
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

const GROUP_ICONS: Record<ModelRouteGroup["id"], typeof HardDrives> = {
  text: Database,
  image: Cloud,
  video: VideoCamera,
  voice: ShieldCheck,
  music: Lightning,
};

const STATUS_CLASSES: Record<ProviderRouteStatus, string> = {
  production: "border-[rgba(120,175,140,0.22)] bg-[rgba(120,175,140,0.10)] text-[var(--jade-accent)]",
  fallback: "border-[rgba(93,132,187,0.18)] bg-[rgba(93,132,187,0.10)] text-[var(--text-body)]",
  candidate: "border-[rgba(215,92,112,0.18)] bg-[rgba(215,92,112,0.08)] text-[var(--fortune-red)]",
  legacy: "border-[var(--divider-light)] bg-[var(--bg-panel)] text-[var(--text-muted)]",
};

function countConfiguredProviderKeys(config: ModelProviderConfig): number {
  return Object.values(config.apiKeys).filter((value) => typeof value === "string" && value.trim()).length;
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
  const [providerConfig, setProviderConfigState] = useState<ModelProviderConfig>(() => getModelProviderConfig());
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
  const providerKeysTitle = t("settings.providers.keys.title", "Provider API keys");
  const providerKeysDesc = t(
    "settings.providers.keys.desc",
    "Store provider keys for this browser session and pass them to scenario runs."
  );
  const modelRoutesTitle = t("settings.providers.routes.title", "Model route catalog");
  const modelRoutesDesc = t(
    "settings.providers.routes.desc",
    "Production routes and replacement candidates grouped by generation layer."
  );
  const currentModeTitle = t("settings.providers.mode.title", "Current mode");
  const currentModeDesc = t(
    "settings.providers.mode.desc",
    "Use this as a quick visual cue before saving and leaving the dialog."
  );
  const currentModeStatusLabel = t("settings.providers.mode.status", "Status");
  const configuredKeysLabel = t("settings.providers.mode.configuredKeys", "Configured provider keys");
  const providerKeyCount = countConfiguredProviderKeys(providerConfig);
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
  const dialogDescriptionId = "settings-dialog-description";
  const urlInputId = "settings-api-base-url";
  const urlHintId = "settings-api-base-url-hint";
  const apiKeyInputId = "settings-api-key";
  const apiKeyHintId = "settings-api-key-hint";

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setBaseUrl(getApiBase());
    setKey(getApiKey());
    setDemo(isDemoMode());
    setProviderConfigState(getModelProviderConfig());
  }, []);

  const handleSave = () => {
    setApiBase(baseUrl.trim());
    setApiKey(key.trim());
    setDemoMode(demo);
    setModelProviderConfig(providerConfig);
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
    setProviderConfigState({ apiKeys: {} });
    setTestResult(null);
    setShowResetConfirm(false);
  };

  const updateProviderKey = (envName: ProviderApiKeyName, value: string) => {
    setProviderConfigState((prev) => ({
      ...prev,
      apiKeys: {
        ...prev.apiKeys,
        [envName]: value,
      },
    }));
  };

  const providerStatusLabel = (status: ProviderRouteStatus) =>
    t(`settings.providers.status.${status}`, status);

  const capabilityLabel = (group: ModelRouteGroup) =>
    t(`settings.providers.capability.${group.id}`, group.title);

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
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-dialog-title"
        aria-describedby={dialogDescriptionId}
        className="apple-card w-full max-w-5xl mx-4 flex max-h-[90vh] flex-col overflow-hidden animate-scale-in"
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
                  <h2 id="settings-dialog-title" className="text-[18px] font-semibold text-[var(--text-h1)]">{title}</h2>
                  <span className="rounded-full border border-[rgba(215,92,112,0.14)] bg-[rgba(215,92,112,0.06)] px-2 py-0.5 text-[11px] font-medium text-[var(--fortune-red)]">
                    {demoBadge}
                  </span>
                </div>
                <p id={dialogDescriptionId} className="mt-1 max-w-[38rem] text-[13px] leading-5 text-[var(--text-body)]">{summaryDescription}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label={t("common.close", "Close")}
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
              <p className="mt-1 truncate text-[12px] font-medium text-[var(--text-h1)]">{maskApiKeyForDisplay(key)}</p>
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
                      <label htmlFor={urlInputId} className="mb-1.5 flex items-center gap-1.5 text-[12px] font-medium text-[var(--text-body)]">
                        <HardDrives size={12} weight="fill" />
                        {accessUrlLabel}
                      </label>
                      <input
                        id={urlInputId}
                        type="text"
                        value={baseUrl}
                        onChange={(e) => setBaseUrl(e.target.value)}
                        placeholder="https://video.lute-tlz-dddd.top"
                        aria-describedby={urlHintId}
                        className="apple-input text-sm"
                      />
                      <p id={urlHintId} className="mt-1 text-[12px] leading-5 text-[var(--text-muted)]">{accessUrlHint}</p>
                    </div>

                    <div>
                      <label htmlFor={apiKeyInputId} className="mb-1.5 flex items-center gap-1.5 text-[12px] font-medium text-[var(--text-body)]">
                        <Key size={12} weight="fill" />
                        {accessKeyLabel}
                      </label>
                      <input
                        id={apiKeyInputId}
                        type="password"
                        value={key}
                        onChange={(e) => setKey(e.target.value)}
                        placeholder="ai_video_demo_2026"
                        className="apple-input text-sm"
                        autoComplete="current-password"
                        aria-describedby={apiKeyHintId}
                      />
                      <p id={apiKeyHintId} className="mt-1 text-[12px] leading-5 text-[var(--text-muted)]">{accessKeyHint}</p>
                    </div>
                  </div>
                </PanelCard>

                <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                  <button
                    type="button"
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
                    type="button"
                    onClick={handleReset}
                    className="apple-btn inline-flex items-center justify-center gap-2 border border-[rgba(208,78,90,0.25)] text-xs py-2.5 text-[var(--crimson-mist)] hover:bg-[rgba(208,78,90,0.06)]"
                  >
                    <ArrowCounterClockwise size={14} weight="fill" />
                    {resetLabel}
                  </button>
                </div>

                {testResult && (
                  <div
                    role={testResult.ok ? "status" : "alert"}
                    aria-live={testResult.ok ? "polite" : "assertive"}
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
            <div className="grid gap-4 xl:grid-cols-[minmax(300px,0.92fr)_minmax(0,1.08fr)]">
              <div className="space-y-4">
                <PanelCard
                  title={providerKeysTitle}
                  description={providerKeysDesc}
                  icon={Key}
                  accent
                  extra={
                    <span className="shrink-0 rounded-full border border-[rgba(215,92,112,0.16)] bg-white/80 px-2 py-1 text-[11px] font-medium text-[var(--fortune-red)]">
                      {providerKeyCount}/{PROVIDER_KEY_SPECS.length}
                    </span>
                  }
                >
                  <div className="grid gap-3">
                    {PROVIDER_KEY_SPECS.map((spec) => {
                      const inputId = `settings-provider-key-${spec.envName}`;
                      const value = providerConfig.apiKeys[spec.envName] ?? "";
                      return (
                        <div key={spec.envName} className="rounded-xl border border-[var(--divider-light)] bg-[var(--bg-panel)] px-3 py-3">
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div className="min-w-0">
                              <label htmlFor={inputId} className="text-[12px] font-semibold text-[var(--text-h1)]">
                                {spec.provider}
                              </label>
                              <p className="mt-0.5 text-[11px] leading-4 text-[var(--text-muted)]">{spec.scope}</p>
                            </div>
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${STATUS_CLASSES[spec.status]}`}>
                              {providerStatusLabel(spec.status)}
                            </span>
                          </div>
                          <input
                            id={inputId}
                            type="password"
                            value={value}
                            onChange={(event) => updateProviderKey(spec.envName, event.target.value)}
                            placeholder={spec.envName}
                            autoComplete="off"
                            className="apple-input mt-2 text-xs"
                          />
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            <span className="rounded-md border border-[var(--divider-light)] bg-white px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                              {spec.envName}
                            </span>
                            {spec.requiredForProduction && (
                              <span className="rounded-md border border-[rgba(120,175,140,0.18)] bg-[rgba(120,175,140,0.08)] px-1.5 py-0.5 text-[10px] text-[var(--jade-accent)]">
                                {t("settings.providers.required", "Production required")}
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </PanelCard>

                <PanelCard
                  title={providerDemoTitle}
                  description={providerDemoDesc}
                  icon={Lightning}
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
                      <p className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-muted)]">{configuredKeysLabel}</p>
                      <p className="mt-1 text-[13px] font-medium text-[var(--text-h1)]">
                        {providerKeyCount}/{PROVIDER_KEY_SPECS.length}
                      </p>
                    </div>
                  </div>
                </PanelCard>
              </div>

              <div className="space-y-4">
                <PanelCard
                  title={modelRoutesTitle}
                  description={modelRoutesDesc}
                  icon={HardDrives}
                >
                  <div className="grid gap-3">
                    {MODEL_ROUTE_GROUPS.map((group) => {
                      const Icon = GROUP_ICONS[group.id];
                      return (
                        <section key={group.id} className="rounded-xl border border-[var(--divider-light)] bg-[var(--bg-panel)]">
                          <div className="flex items-center gap-2 border-b border-[var(--divider-light)] px-3 py-2.5">
                            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white text-[var(--fortune-red)]">
                              <Icon size={14} weight="fill" />
                            </span>
                            <h4 className="text-[12px] font-semibold text-[var(--text-h1)]">{capabilityLabel(group)}</h4>
                          </div>
                          <div className="divide-y divide-[var(--divider-light)]">
                            {group.routes.map((route) => (
                              <div key={`${group.id}-${route.provider}-${route.role}`} className="px-3 py-3">
                                <div className="flex flex-wrap items-start justify-between gap-2">
                                  <div className="min-w-0">
                                    <p className="text-[12px] font-semibold text-[var(--text-h1)]">{route.provider}</p>
                                    <p className="mt-0.5 text-[11px] leading-4 text-[var(--text-muted)]">{route.role}</p>
                                  </div>
                                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${STATUS_CLASSES[route.status]}`}>
                                    {providerStatusLabel(route.status)}
                                  </span>
                                </div>
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                  <span className="rounded-md border border-[var(--divider-light)] bg-white px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                                    {route.keyEnv}
                                  </span>
                                  {route.modelEnv && (
                                    <span className="rounded-md border border-[var(--divider-light)] bg-white px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                                      {route.modelEnv}: {route.currentDefault}
                                    </span>
                                  )}
                                  {route.baseEnv && (
                                    <span className="rounded-md border border-[var(--divider-light)] bg-white px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                                      {route.baseEnv}
                                    </span>
                                  )}
                                </div>
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                  {route.candidateModels.map((model) => (
                                    <span key={model} className="rounded-full bg-white px-2 py-0.5 text-[10px] text-[var(--text-body)]">
                                      {model}
                                    </span>
                                  ))}
                                </div>
                                {route.note && (
                                  <p className="mt-2 text-[11px] leading-4 text-[var(--text-muted)]">{route.note}</p>
                                )}
                              </div>
                            ))}
                          </div>
                        </section>
                      );
                    })}
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
                type="button"
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
              type="button"
              onClick={onClose}
              className="apple-btn border border-[var(--border-default)] bg-[var(--bg-panel)] px-3 py-2 text-xs text-[var(--text-body)]"
            >
              {cancelLabel}
            </button>
            <button type="button" onClick={handleSave} className="apple-btn apple-btn-primary px-4 py-2 text-xs">
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
        closeLabel={t("common.close")}
        onConfirm={confirmReset}
        onCancel={() => setShowResetConfirm(false)}
      />
    </div>
  );
}
