"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowClockwise,
  ClipboardText,
  LockKey,
  PlayCircle,
  ShieldCheck,
  WarningCircle,
} from "@phosphor-icons/react";
import TopHeader from "@/components/TopHeader";
import {
  fetchToolboxAuditSummary,
  fetchToolboxRun,
  fetchToolboxRuns,
  planToolboxRun,
  previewToolboxInjectionDraft,
  previewToolboxPrompt,
  runToolboxDryRun,
  type ToolboxArtifact,
  type ToolboxInjectionAuditSummaryResponse,
  type ToolboxInjectionDraftResponse,
  type ToolboxInjectionTarget,
  type ToolboxPlanResponse,
  type ToolboxPromptPreviewResponse,
  type ToolboxRequestPayload,
  type ToolboxRunResponse,
  type ToolboxToolId,
} from "@/components/api";
import { useI18n } from "@/i18n/I18nProvider";
import {
  getToolPresentation,
  isToolboxToolId,
} from "@/components/toolbox/toolboxCatalog";

type BusyAction = "plan" | "preview" | "run" | "refresh" | "loadRun" | "injectDraft" | "auditSummary" | null;

type ToolboxFormState = {
  brandId: string;
  brandBundleRef: string;
  productRef: string;
  brief: string;
  platform: string;
  aspectRatio: string;
  stylePreset: string;
  targetScenario: string;
  assetRefsText: string;
  durationSeconds: string;
};

type FieldName = keyof ToolboxFormState;

const DEFAULT_ASSET_REF = "asset://brand/momcozy/product/reference-001";
const DEFAULT_BUNDLE_REF = "bundle_momcozy_candidate";
const TARGET_SCENARIOS = ["", "s1", "s2", "s3", "s4", "s5"];
const PLATFORM_OPTIONS = ["shopify", "amazon", "tiktok", "instagram", "youtube"];
const ASPECT_RATIO_OPTIONS = ["1:1", "4:5", "9:16", "16:9"];
const STYLE_PRESETS = ["clean_pdp", "warm_lifestyle", "premium_brand", "creator_demo"];

function defaultFormState(toolId: ToolboxToolId): ToolboxFormState {
  return {
    brandId: "momcozy",
    brandBundleRef: DEFAULT_BUNDLE_REF,
    productRef: "sku://momcozy/reference-product",
    brief: defaultBrief(toolId),
    platform: toolId === "storyboard" || toolId === "digital-human" ? "tiktok" : "shopify",
    aspectRatio: toolId === "storyboard" || toolId === "digital-human" ? "9:16" : "1:1",
    stylePreset: toolId === "six-view" ? "clean_pdp" : "premium_brand",
    targetScenario: "",
    assetRefsText: DEFAULT_ASSET_REF,
    durationSeconds: toolId === "storyboard" || toolId === "digital-human" ? "120" : "15",
  };
}

function defaultBrief(toolId: ToolboxToolId): string {
  switch (toolId) {
    case "product-image":
      return "Plan a dry-run product image set for ecommerce PDP and thumbnail use.";
    case "six-view":
      return "Plan canonical six-view references for product consistency.";
    case "ecommerce-visual":
      return "Plan a commercial visual pack for ecommerce and social channels.";
    case "digital-human":
      return "Plan a presenter-led demo with likeness and voice consent locked.";
    case "storyboard":
      return "Plan a long-form product education storyboard with review checkpoints.";
  }
}

function parseAssetRefs(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toPositiveInteger(value: string): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 15;
}

function createRequestId(toolId: ToolboxToolId): string {
  return `tbx_req_${toolId.replaceAll("-", "_")}_${Date.now()}`;
}

function normalizeEcommerceChannel(platform: string): string {
  if (platform === "instagram") return "reels";
  if (platform === "youtube") return "youtube_shorts";
  if (["shopify", "amazon", "tiktok"].includes(platform)) return platform;
  return "shopify";
}

function buildToolInput(toolId: ToolboxToolId, form: ToolboxFormState, assetRefs: string[]): Record<string, unknown> {
  const duration = toPositiveInteger(form.durationSeconds);
  switch (toolId) {
    case "product-image":
      return {
        tool_id: toolId,
        product_ref: form.productRef,
        image_type: "main_white_bg",
        aspect_ratio: form.aspectRatio,
        reference_asset_refs: assetRefs,
      };
    case "six-view":
      return {
        tool_id: toolId,
        product_ref: form.productRef,
        seed_image_refs: assetRefs,
        required_views: ["front", "back", "left", "right", "top", "detail"],
        consistency_level: "strict",
      };
    case "ecommerce-visual":
      return {
        tool_id: toolId,
        campaign_brief: form.brief,
        channel: normalizeEcommerceChannel(form.platform),
        visual_format: normalizeEcommerceChannel(form.platform) === "shopify" ? "detail_module" : "social_ad",
        product_image_refs: assetRefs,
        aspect_ratio: form.aspectRatio,
      };
    case "digital-human":
      return {
        tool_id: toolId,
        presenter_policy: form.brief || "brand_demo_locked",
        voice_policy: "none",
      };
    case "storyboard":
      return {
        tool_id: toolId,
        brief: form.brief,
        duration_target_seconds: duration,
        platform: normalizeEcommerceChannel(form.platform),
        planned_timeline_block_count: Math.max(3, Math.ceil(duration / 30)),
        review_checkpoint_refs: ["storyboard://review/checkpoint-001"],
        storyboard_grid: 12,
        asset_refs: assetRefs,
      };
  }
}

function buildToolboxRequest(toolId: ToolboxToolId, form: ToolboxFormState): ToolboxRequestPayload {
  const assetRefs = parseAssetRefs(form.assetRefsText);
  return {
    request_id: createRequestId(toolId),
    tool_id: toolId,
    brand_id: form.brandId.trim() || "momcozy",
    platform_target: {
      platform: form.platform,
      aspect_ratio: form.aspectRatio,
      locale: "en",
      duration_seconds: toPositiveInteger(form.durationSeconds),
    },
    brand_bundle_ref: form.brandBundleRef.trim() || DEFAULT_BUNDLE_REF,
    asset_refs: assetRefs.map((assetRef) => ({
      asset_ref: assetRef,
      asset_kind: "image",
      rights_ref: "rights://candidate/reference",
    })),
    target_scenario: form.targetScenario || null,
    tool_input: buildToolInput(toolId, form, assetRefs) as ToolboxRequestPayload["tool_input"],
  };
}

function errorToMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function FieldRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-[var(--text-body)]">{label}</span>
      {children}
    </label>
  );
}

function SelectField({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-10 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-layer2)] px-3 text-sm text-[var(--text-h1)] outline-none transition focus:border-[var(--fortune-red)]"
    >
      {options.map((option) => (
        <option key={option} value={option}>
          {option || "-"}
        </option>
      ))}
    </select>
  );
}

function TextInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-10 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-layer2)] px-3 text-sm text-[var(--text-h1)] outline-none transition focus:border-[var(--fortune-red)]"
    />
  );
}

function ValueRow({ label, value }: { label: string; value: string | boolean | number | null | undefined }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-[var(--divider-subtle)] py-2 last:border-b-0">
      <span className="text-xs font-semibold text-[var(--text-muted)]">{label}</span>
      <span className="max-w-[220px] break-words text-right text-xs font-semibold text-[var(--text-h1)]">
        {String(value ?? "-")}
      </span>
    </div>
  );
}

function ArtifactList({ artifacts }: { artifacts: ToolboxArtifact[] }) {
  if (artifacts.length === 0) {
    return <div className="text-sm text-[var(--text-muted)]">-</div>;
  }
  return (
    <ul className="space-y-2">
      {artifacts.map((artifact) => (
        <li key={artifact.artifact_id} className="rounded-lg bg-[var(--bg-layer2)] p-3 text-xs text-[var(--text-muted)]">
          <div className="font-semibold text-[var(--text-h1)]">{artifact.artifact_type}</div>
          <div className="mt-1 break-all">{artifact.artifact_ref}</div>
        </li>
      ))}
    </ul>
  );
}

function RefList({ values }: { values: string[] }) {
  if (values.length === 0) {
    return <div className="text-xs text-[var(--text-muted)]">-</div>;
  }
  return (
    <ul className="space-y-1.5">
      {values.map((value) => (
        <li key={value} className="break-all rounded-lg bg-[var(--bg-panel)] px-2.5 py-2 text-[11px] leading-5 text-[var(--text-muted)]">
          {value}
        </li>
      ))}
    </ul>
  );
}

function InjectionTargetDiff({
  plannedRefs,
  targets,
  t,
}: {
  plannedRefs: string[];
  targets: ToolboxInjectionTarget[];
  t: (key: string, fallback?: string) => string;
}) {
  return (
    <div className="grid gap-3">
      <section className="rounded-lg bg-[var(--bg-layer2)] p-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("toolbox.injection.plannedRefs")}
        </h3>
        <div className="mt-3">
          <RefList values={plannedRefs} />
        </div>
      </section>
      {targets.length > 0 ? (
        targets.map((target) => (
          <section key={target.target_ref} className="rounded-lg bg-[var(--bg-layer2)] p-3" data-injection-target={target.target_ref}>
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-xs font-semibold text-[var(--text-h1)]">{target.scenario}</h3>
              <span className="rounded-full bg-[var(--bg-panel)] px-2 py-1 text-[11px] font-semibold text-[var(--text-muted)]">
                {target.step_name}
              </span>
            </div>
            <div className="mt-3 space-y-3">
              <div>
                <div className="mb-1.5 text-[11px] font-semibold text-[var(--text-muted)]">{t("toolbox.injection.artifactRefs")}</div>
                <RefList values={target.artifact_refs} />
              </div>
              <div>
                <div className="mb-1.5 text-[11px] font-semibold text-[var(--text-muted)]">{t("toolbox.injection.contractRefs")}</div>
                <RefList values={target.contract_refs} />
              </div>
              <div>
                <div className="mb-1.5 text-[11px] font-semibold text-[var(--text-muted)]">{t("toolbox.injection.bundleRefs")}</div>
                <RefList values={target.bundle_refs ?? []} />
              </div>
            </div>
          </section>
        ))
      ) : (
        <section className="rounded-lg border border-dashed border-[var(--border-default)] bg-[var(--bg-layer2)] p-3 text-xs text-[var(--text-muted)]">
          {t("toolbox.injection.noTargets")}
        </section>
      )}
    </div>
  );
}

function InjectionDraftPanel({
  draft,
  t,
}: {
  draft: ToolboxInjectionDraftResponse | null;
  t: (key: string, fallback?: string) => string;
}) {
  if (!draft) {
    return (
      <section className="rounded-lg border border-dashed border-[var(--border-default)] bg-[var(--bg-layer2)] p-3 text-xs text-[var(--text-muted)]">
        {t("toolbox.injection.noDraft")}
      </section>
    );
  }

  return (
    <section className="rounded-lg bg-[var(--bg-layer2)] p-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {t("toolbox.injectionDraft")}
      </h3>
      <div className="mt-3">
        <ValueRow label="draft_id" value={draft.draft_id} />
        <ValueRow label="draft_ref" value={draft.draft_ref} />
        <ValueRow label="mode" value={draft.mode} />
        <ValueRow label="state_write" value={draft.state_write} />
        <ValueRow label="provider_call" value={draft.provider_call} />
        <ValueRow label="delivery_accepted" value={draft.delivery_accepted} />
        <ValueRow label="publish_allowed" value={draft.publish_allowed} />
      </div>
      <div className="mt-3 space-y-3">
        <div>
          <div className="mb-1.5 text-[11px] font-semibold text-[var(--text-muted)]">{t("toolbox.injection.artifactRefs")}</div>
          <RefList values={draft.artifact_refs} />
        </div>
        <div>
          <div className="mb-1.5 text-[11px] font-semibold text-[var(--text-muted)]">{t("toolbox.injection.contractRefs")}</div>
          <RefList values={draft.contract_refs} />
        </div>
        <div>
          <div className="mb-1.5 text-[11px] font-semibold text-[var(--text-muted)]">{t("toolbox.injection.bundleRefs")}</div>
          <RefList values={draft.bundle_refs} />
        </div>
        <div>
          <div className="mb-1.5 text-[11px] font-semibold text-[var(--text-muted)]">{t("toolbox.injection.warnings")}</div>
          <RefList values={draft.warnings ?? []} />
        </div>
      </div>
    </section>
  );
}

function auditStatusClassName(status: "passed" | "advisory" | "blocked"): string {
  if (status === "passed") {
    return "border-[#9fd8ce] bg-[rgba(28,125,115,0.08)] text-[#1c7d73]";
  }
  if (status === "advisory") {
    return "border-[#e2c37c] bg-[rgba(166,107,31,0.08)] text-[#a66b1f]";
  }
  return "border-[var(--danger)] bg-[rgba(185,28,28,0.06)] text-[var(--danger)]";
}

function InjectionAuditSummaryPanel({
  summary,
  t,
}: {
  summary: ToolboxInjectionAuditSummaryResponse | null;
  t: (key: string, fallback?: string) => string;
}) {
  if (!summary) {
    return (
      <section className="rounded-lg border border-dashed border-[var(--border-default)] bg-[var(--bg-layer2)] p-3 text-xs text-[var(--text-muted)]">
        {t("toolbox.audit.noSummary")}
      </section>
    );
  }

  return (
    <section className="rounded-lg bg-[var(--bg-layer2)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("toolbox.injectionAuditSummary")}
        </h3>
        <span
          className={`inline-flex h-7 items-center rounded-full border px-2.5 text-[11px] font-semibold ${
            summary.ready_for_scenario_injection
              ? "border-[#9fd8ce] bg-[rgba(28,125,115,0.08)] text-[#1c7d73]"
              : "border-[var(--danger)] bg-[rgba(185,28,28,0.06)] text-[var(--danger)]"
          }`}
        >
          {summary.ready_for_scenario_injection ? t("toolbox.audit.ready") : t("toolbox.audit.notReady")}
        </span>
      </div>
      <div className="mt-3">
        <ValueRow label="summary_id" value={summary.summary_id} />
        <ValueRow label="state_write" value={summary.state_write} />
        <ValueRow label="provider_call" value={summary.provider_call} />
        <ValueRow label="delivery_accepted" value={summary.delivery_accepted} />
        <ValueRow label="publish_allowed" value={summary.publish_allowed} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <ValueRow label={t("toolbox.audit.targetCount")} value={summary.target_count} />
        <ValueRow label={t("toolbox.audit.artifactRefCount")} value={summary.artifact_ref_count} />
        <ValueRow label={t("toolbox.audit.contractRefCount")} value={summary.contract_ref_count} />
        <ValueRow label={t("toolbox.audit.bundleRefCount")} value={summary.bundle_ref_count} />
      </div>
      <div className="mt-3 space-y-2">
        {summary.checks.map((check) => (
          <div key={check.check_id} className={`rounded-lg border px-3 py-2 ${auditStatusClassName(check.status)}`}>
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-semibold">{check.label}</span>
              <span className="text-[11px] font-semibold uppercase">{check.status}</span>
            </div>
            {check.message ? <div className="mt-1 text-[11px] leading-5">{check.message}</div> : null}
          </div>
        ))}
      </div>
      {summary.blocking_reasons?.length ? (
        <div className="mt-3">
          <div className="mb-1.5 text-[11px] font-semibold text-[var(--text-muted)]">{t("toolbox.audit.blockingReasons")}</div>
          <RefList values={summary.blocking_reasons} />
        </div>
      ) : null}
      {summary.advisory_reasons?.length ? (
        <div className="mt-3">
          <div className="mb-1.5 text-[11px] font-semibold text-[var(--text-muted)]">{t("toolbox.audit.advisoryReasons")}</div>
          <RefList values={summary.advisory_reasons} />
        </div>
      ) : null}
    </section>
  );
}

export default function ToolboxToolPage({ toolId }: { toolId: string }) {
  const { t } = useI18n();

  if (!isToolboxToolId(toolId)) {
    return (
      <div className="min-h-screen bg-[var(--bg-page)] text-[var(--text-body)]">
        <TopHeader />
        <main className="mx-auto w-full max-w-[960px] px-4 py-10 sm:px-6">
          <Link href="/toolbox" className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--fortune-red)]">
            <ArrowLeft size={16} weight="bold" />
            {t("toolbox.back")}
          </Link>
          <section className="mt-6 rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-6">
            <h1 className="text-xl font-semibold text-[var(--text-h1)]">{t("toolbox.unknown.title")}</h1>
            <p className="mt-2 text-sm text-[var(--text-muted)]">{t("toolbox.unknown.desc")}</p>
          </section>
        </main>
      </div>
    );
  }

  return <ValidToolboxToolPage toolId={toolId} />;
}

function ValidToolboxToolPage({ toolId }: { toolId: ToolboxToolId }) {
  const { t } = useI18n();
  const presentation = getToolPresentation(toolId);
  const [form, setForm] = useState<ToolboxFormState>(() => defaultFormState(toolId));
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<ToolboxPlanResponse | null>(null);
  const [preview, setPreview] = useState<ToolboxPromptPreviewResponse | null>(null);
  const [run, setRun] = useState<ToolboxRunResponse | null>(null);
  const [injectionDraft, setInjectionDraft] = useState<ToolboxInjectionDraftResponse | null>(null);
  const [auditSummary, setAuditSummary] = useState<ToolboxInjectionAuditSummaryResponse | null>(null);
  const [recentRuns, setRecentRuns] = useState<ToolboxRunResponse[]>([]);
  const activeRunIdRef = useRef<string | null>(null);

  const updateField = (field: FieldName, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const requestPreview = useMemo(() => buildToolboxRequest(toolId, form), [form, toolId]);
  const Icon = presentation.icon;
  const requiredChecks = plan?.required_checks ?? presentation.fallbackChecks;
  const artifacts = run?.artifacts ?? [];
  const plannedInjectionRefs = plan?.injection_target_refs ?? [];
  const injectionTargets = run?.injection_targets ?? [];

  const applyRunState = useCallback((nextRun: ToolboxRunResponse) => {
    activeRunIdRef.current = nextRun.run_id;
    setRun(nextRun);
    setPlan(nextRun.plan);
    setPreview(nextRun.prompt_preview ?? null);
    setInjectionDraft(null);
    setAuditSummary(null);
  }, []);

  const refreshAuditSummaryForRun = useCallback(async (runId: string, options?: { signal?: AbortSignal }) => {
    try {
      const requestOptions = options?.signal ? { signal: options.signal } : undefined;
      const summary = await fetchToolboxAuditSummary(runId, requestOptions);
      if (activeRunIdRef.current === runId) {
        setAuditSummary(summary);
      }
    } catch (nextError: unknown) {
      if (nextError instanceof DOMException && nextError.name === "AbortError") return;
      if (activeRunIdRef.current === runId) {
        setAuditSummary(null);
        setError(errorToMessage(nextError));
      }
    }
  }, []);

  const refreshRecentRuns = useCallback(async (options?: { applyLatest?: boolean }) => {
    setBusyAction("refresh");
    setError(null);
    try {
      const data = await fetchToolboxRuns({ toolId, limit: 5 });
      setRecentRuns(data.runs);
      if (options?.applyLatest && data.runs[0]) {
        applyRunState(data.runs[0]);
        void refreshAuditSummaryForRun(data.runs[0].run_id);
      }
    } catch (nextError: unknown) {
      setError(errorToMessage(nextError));
    } finally {
      setBusyAction(null);
    }
  }, [applyRunState, refreshAuditSummaryForRun, toolId]);

  useEffect(() => {
    const controller = new AbortController();
    fetchToolboxRuns({ toolId, limit: 5, signal: controller.signal })
      .then((data) => {
        setRecentRuns(data.runs);
        if (data.runs[0]) {
          applyRunState(data.runs[0]);
          void refreshAuditSummaryForRun(data.runs[0].run_id, { signal: controller.signal });
        }
      })
      .catch((nextError: unknown) => {
        if (nextError instanceof DOMException && nextError.name === "AbortError") return;
        setError(errorToMessage(nextError));
      });
    return () => controller.abort();
  }, [applyRunState, refreshAuditSummaryForRun, toolId]);

  const callAction = async <T,>(action: BusyAction, execute: () => Promise<T>, commit: (value: T) => void) => {
    if (!action) return;
    setBusyAction(action);
    setError(null);
    try {
      const result = await execute();
      commit(result);
    } catch (nextError: unknown) {
      setError(errorToMessage(nextError));
    } finally {
      setBusyAction(null);
    }
  };

  const handlePreparePlan = () => {
    const body = buildToolboxRequest(toolId, form);
    void callAction("plan", () => planToolboxRun(toolId, body), setPlan);
  };

  const handlePreviewPrompt = () => {
    const body = buildToolboxRequest(toolId, form);
    void callAction("preview", () => previewToolboxPrompt(toolId, body), setPreview);
  };

  const handleDryRun = () => {
    const body = buildToolboxRequest(toolId, form);
    void callAction("run", () => runToolboxDryRun(toolId, body), (result) => {
      applyRunState(result);
      void refreshAuditSummaryForRun(result.run_id);
      setRecentRuns((current) => [
        result,
        ...current.filter((item) => item.run_id !== result.run_id),
      ].slice(0, 5));
    });
  };

  const handleRefreshRuns = () => {
    void refreshRecentRuns({ applyLatest: false });
  };

  const handleLoadRun = (runId: string) => {
    void callAction("loadRun", () => fetchToolboxRun(runId), (result) => {
      applyRunState(result);
      void refreshAuditSummaryForRun(result.run_id);
    });
  };

  const handlePreviewInjectionDraft = () => {
    if (!run) return;
    void callAction("injectDraft", () => previewToolboxInjectionDraft(run.run_id), setInjectionDraft);
  };

  const handleFetchAuditSummary = () => {
    if (!run) return;
    void callAction("auditSummary", () => fetchToolboxAuditSummary(run.run_id), setAuditSummary);
  };

  return (
    <div className="min-h-screen bg-[var(--bg-page)] text-[var(--text-body)]" data-testid="toolbox-tool-page">
      <TopHeader />
      <main className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-4 py-6 sm:px-6 lg:py-8">
        <section className="border-b border-[var(--divider-subtle)] pb-6">
          <Link href="/toolbox" className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--fortune-red)]">
            <ArrowLeft size={16} weight="bold" />
            {t("toolbox.back")}
          </Link>
          <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
            <div className="flex items-start gap-4">
              <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-lg ${presentation.accentClassName}`}>
                <Icon size={26} weight="fill" />
              </span>
              <div>
                <h1 className="text-3xl font-semibold tracking-normal text-[var(--text-h1)] sm:text-4xl">
                  {t(presentation.titleKey)}
                </h1>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--text-muted)] sm:text-base">
                  {t(presentation.descriptionKey)}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 lg:justify-end">
              <span className="inline-flex h-8 items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--bg-panel)] px-3 text-xs font-semibold text-[var(--text-muted)]">
                <ClipboardText size={15} weight="fill" />
                L2-fixture-or-dry-run
              </span>
              <span className="inline-flex h-8 items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--bg-panel)] px-3 text-xs font-semibold text-[var(--text-muted)]">
                <LockKey size={15} weight="fill" />
                {t("toolbox.liveLocked")}
              </span>
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)_360px]">
          <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
            <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.detail.input")}</h2>
            <div className="mt-4 grid gap-3">
              <FieldRow label={t("toolbox.form.brandId")}>
                <TextInput value={form.brandId} onChange={(value) => updateField("brandId", value)} />
              </FieldRow>
              <FieldRow label={t("toolbox.form.brandBundleRef")}>
                <TextInput value={form.brandBundleRef} onChange={(value) => updateField("brandBundleRef", value)} />
              </FieldRow>
              <FieldRow label={t("toolbox.form.productRef")}>
                <TextInput value={form.productRef} onChange={(value) => updateField("productRef", value)} />
              </FieldRow>
              <div className="grid grid-cols-2 gap-3">
                <FieldRow label={t("toolbox.form.platform")}>
                  <SelectField value={form.platform} options={PLATFORM_OPTIONS} onChange={(value) => updateField("platform", value)} />
                </FieldRow>
                <FieldRow label={t("toolbox.form.aspectRatio")}>
                  <SelectField value={form.aspectRatio} options={ASPECT_RATIO_OPTIONS} onChange={(value) => updateField("aspectRatio", value)} />
                </FieldRow>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <FieldRow label={t("toolbox.form.stylePreset")}>
                  <SelectField value={form.stylePreset} options={STYLE_PRESETS} onChange={(value) => updateField("stylePreset", value)} />
                </FieldRow>
                <FieldRow label={t("toolbox.form.targetScenario")}>
                  <SelectField value={form.targetScenario} options={TARGET_SCENARIOS} onChange={(value) => updateField("targetScenario", value)} />
                </FieldRow>
              </div>
              <FieldRow label={t("toolbox.form.duration")}>
                <TextInput value={form.durationSeconds} onChange={(value) => updateField("durationSeconds", value)} />
              </FieldRow>
              <FieldRow label={t("toolbox.form.brief")}>
                <textarea
                  value={form.brief}
                  onChange={(event) => updateField("brief", event.target.value)}
                  className="min-h-[112px] w-full resize-y rounded-lg border border-[var(--border-default)] bg-[var(--bg-layer2)] px-3 py-2 text-sm leading-6 text-[var(--text-h1)] outline-none transition focus:border-[var(--fortune-red)]"
                />
              </FieldRow>
              <FieldRow label={t("toolbox.form.assetRefs")}>
                <textarea
                  value={form.assetRefsText}
                  onChange={(event) => updateField("assetRefsText", event.target.value)}
                  className="min-h-[84px] w-full resize-y rounded-lg border border-[var(--border-default)] bg-[var(--bg-layer2)] px-3 py-2 text-sm leading-6 text-[var(--text-h1)] outline-none transition focus:border-[var(--fortune-red)]"
                />
              </FieldRow>
            </div>
            <div className="mt-5 grid gap-2">
              <button
                type="button"
                onClick={handlePreparePlan}
                disabled={busyAction !== null}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-[var(--fortune-red)] px-4 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-60"
              >
                <ClipboardText size={17} weight="fill" />
                {busyAction === "plan" ? t("toolbox.actionRunning") : t("toolbox.preparePlan")}
              </button>
              <button
                type="button"
                onClick={handlePreviewPrompt}
                disabled={busyAction !== null}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-[var(--border-default)] px-4 text-sm font-semibold text-[var(--text-h1)] transition hover:border-[var(--fortune-red)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <ShieldCheck size={17} weight="fill" />
                {busyAction === "preview" ? t("toolbox.actionRunning") : t("toolbox.previewPrompt")}
              </button>
              <button
                type="button"
                onClick={handleDryRun}
                disabled={busyAction !== null}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-[var(--border-default)] px-4 text-sm font-semibold text-[var(--text-h1)] transition hover:border-[var(--fortune-red)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <PlayCircle size={17} weight="fill" />
                {busyAction === "run" ? t("toolbox.actionRunning") : t("toolbox.runDryRun")}
              </button>
              <button
                type="button"
                disabled
                className="inline-flex h-10 cursor-not-allowed items-center justify-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-layer2)] px-4 text-sm font-semibold text-[var(--text-muted)]"
              >
                <LockKey size={17} weight="fill" />
                {t("toolbox.liveLocked")}
              </button>
            </div>
            {error ? (
              <div className="mt-4 rounded-lg border border-[var(--danger)] bg-[rgba(185,28,28,0.06)] p-3 text-sm text-[var(--danger)]" role="alert">
                {error}
              </div>
            ) : null}
          </section>

          <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
            <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.detail.planPreview")}</h2>
            <div className="mt-4 grid gap-4">
              <section className="rounded-lg bg-[var(--bg-layer2)] p-4">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{t("toolbox.preview.requestEnvelope")}</h3>
                <div className="mt-3">
                  <ValueRow label="tool_id" value={requestPreview.tool_id} />
                  <ValueRow label="brand_id" value={requestPreview.brand_id} />
                  <ValueRow label="brand_bundle_ref" value={requestPreview.brand_bundle_ref} />
                  <ValueRow label="target_scenario" value={requestPreview.target_scenario} />
                  <ValueRow label="platform" value={requestPreview.platform_target.platform} />
                  <ValueRow label="aspect_ratio" value={requestPreview.platform_target.aspect_ratio} />
                </div>
              </section>
              <section className="rounded-lg bg-[var(--bg-layer2)] p-4">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{t("toolbox.preview.plan")}</h3>
                <div className="mt-3">
                  <ValueRow label="plan_id" value={plan?.plan_id} />
                  <ValueRow label={t("toolbox.preview.providerCall")} value={plan?.provider_call ?? false} />
                  <ValueRow label={t("toolbox.preview.deliveryAccepted")} value={plan?.delivery_accepted ?? false} />
                  <ValueRow label={t("toolbox.preview.promptHash")} value={plan?.prompt_hash} />
                </div>
              </section>
              <section className="rounded-lg bg-[var(--bg-layer2)] p-4">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{t("toolbox.preview.promptBlocks")}</h3>
                <div className="mt-3 space-y-2 text-sm text-[var(--text-muted)]">
                  {(preview?.sanitized_prompt_blocks ?? [t("toolbox.preview.noPrompt")]).map((block) => (
                    <p key={block} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] px-3 py-2">
                      {block}
                    </p>
                  ))}
                </div>
              </section>
              <section className="rounded-lg bg-[var(--bg-layer2)] p-4">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{t("toolbox.preview.providerWarnings")}</h3>
                <div className="mt-3 flex items-start gap-2 text-sm leading-6 text-[var(--text-muted)]">
                  <WarningCircle size={17} weight="fill" className="mt-0.5 text-[#a66b1f]" />
                  <span>{t("toolbox.providerNoToken")}</span>
                </div>
              </section>
            </div>
          </section>

          <aside className="grid gap-4">
            <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.preview.qualityGate")}</h2>
              <div className="mt-3 space-y-2">
                {requiredChecks.map((check) => (
                  <div key={check} className="rounded-lg bg-[var(--bg-layer2)] px-3 py-2 text-xs font-semibold text-[var(--text-muted)]">
                    {check}
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.currentRun")}</h2>
                <button
                  type="button"
                  onClick={handleRefreshRuns}
                  disabled={busyAction !== null}
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-[var(--border-default)] px-2.5 text-xs font-semibold text-[var(--text-h1)] transition hover:border-[var(--fortune-red)] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <ArrowClockwise size={14} weight="bold" />
                  {busyAction === "refresh" ? t("toolbox.actionRunning") : t("toolbox.refreshRuns")}
                </button>
              </div>
              <div className="mt-3 rounded-lg bg-[var(--bg-layer2)] p-3 text-xs text-[var(--text-muted)]">
                <div className="font-semibold text-[var(--text-h1)]">{run?.run_id ?? t("toolbox.preview.noRun")}</div>
                <div className="mt-1">{run?.status ?? "-"}</div>
              </div>
              <div className="mt-3 space-y-2">
                {recentRuns.length > 0 ? (
                  recentRuns.map((item) => (
                    <button
                      key={item.run_id}
                      type="button"
                      onClick={() => handleLoadRun(item.run_id)}
                      disabled={busyAction !== null}
                      data-toolbox-run-select={item.run_id}
                      className="block w-full rounded-lg bg-[var(--bg-layer2)] p-3 text-left transition hover:bg-[rgba(215,92,112,0.08)] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <span className="block text-xs font-semibold text-[var(--text-h1)]">{item.tool_id}</span>
                      <span className="mt-1 block break-all text-[11px] leading-5 text-[var(--text-muted)]">{item.run_id}</span>
                      <span className="mt-1 block text-[11px] font-semibold text-[#1c7d73]">{item.status}</span>
                    </button>
                  ))
                ) : (
                  <div className="rounded-lg border border-dashed border-[var(--border-default)] p-3 text-xs text-[var(--text-muted)]">
                    {t("toolbox.recentRunsEmpty")}
                  </div>
                )}
              </div>
            </section>

            <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.preview.jobLedger")}</h2>
              <div className="mt-3">
                <ValueRow label={t("toolbox.preview.jobId")} value={run?.job_record?.job_id} />
                <ValueRow label={t("toolbox.preview.status")} value={run?.job_record?.status ?? t("toolbox.preview.noRun")} />
                <ValueRow label={t("toolbox.preview.deliveryAccepted")} value={run?.job_record?.delivery_accepted ?? false} />
                <ValueRow label={t("toolbox.preview.publishAllowed")} value={run?.job_record?.publish_allowed ?? false} />
              </div>
            </section>

            <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.preview.repairPlan")}</h2>
              <p className="mt-3 text-sm leading-6 text-[var(--text-muted)]">{t("toolbox.preview.noRepair")}</p>
            </section>
          </aside>
        </section>

        <section className="grid gap-6 border-t border-[var(--divider-subtle)] pt-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
            <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.preview.artifactManifest")}</h2>
            <div className="mt-4">
              <ArtifactList artifacts={artifacts} />
            </div>
          </section>
          <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.preview.injectionBoundary")}</h2>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleFetchAuditSummary}
                  disabled={!run || busyAction !== null}
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-[var(--border-default)] px-2.5 text-xs font-semibold text-[var(--text-h1)] transition hover:border-[var(--fortune-red)] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <ShieldCheck size={14} weight="fill" />
                  {busyAction === "auditSummary" ? t("toolbox.actionRunning") : t("toolbox.previewAuditSummary")}
                </button>
                <button
                  type="button"
                  onClick={handlePreviewInjectionDraft}
                  disabled={!run || busyAction !== null}
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-[var(--border-default)] px-2.5 text-xs font-semibold text-[var(--text-h1)] transition hover:border-[var(--fortune-red)] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <ClipboardText size={14} weight="fill" />
                  {busyAction === "injectDraft" ? t("toolbox.actionRunning") : t("toolbox.previewInjectionDraft")}
                </button>
              </div>
            </div>
            <div className="mt-3 space-y-3 text-sm leading-6 text-[var(--text-muted)]">
              <p>{t("toolbox.preview.refsOnly")}</p>
              <InjectionAuditSummaryPanel summary={auditSummary} t={t} />
              <InjectionTargetDiff plannedRefs={plannedInjectionRefs} targets={injectionTargets} t={t} />
              <InjectionDraftPanel draft={injectionDraft} t={t} />
            </div>
          </section>
        </section>
      </main>
    </div>
  );
}
