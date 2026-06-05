"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import {
  ArrowLeft,
  ClipboardText,
  LockKey,
  PlayCircle,
  ShieldCheck,
  WarningCircle,
} from "@phosphor-icons/react";
import TopHeader from "@/components/TopHeader";
import {
  planToolboxRun,
  previewToolboxPrompt,
  runToolboxDryRun,
  type ToolboxArtifact,
  type ToolboxPlanResponse,
  type ToolboxPromptPreviewResponse,
  type ToolboxRequestPayload,
  type ToolboxRunResponse,
  type ToolboxToolId,
} from "@/components/api";
import { useI18n } from "@/i18n/I18nProvider";
import {
  formatToolboxList,
  getToolPresentation,
  isToolboxToolId,
} from "@/components/toolbox/toolboxCatalog";

type BusyAction = "plan" | "preview" | "run" | null;

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

function buildToolInput(toolId: ToolboxToolId, form: ToolboxFormState, assetRefs: string[]): Record<string, unknown> {
  const duration = toPositiveInteger(form.durationSeconds);
  switch (toolId) {
    case "product-image":
      return {
        tool_id: toolId,
        product_ref: form.productRef,
        image_type: "main_white_bg",
        aspect_ratio: form.aspectRatio,
        style_preset: form.stylePreset,
        reference_asset_refs: assetRefs,
        brief: form.brief,
      };
    case "six-view":
      return {
        tool_id: toolId,
        product_ref: form.productRef,
        seed_image_refs: assetRefs,
        required_views: ["front", "back", "left", "right", "top", "detail"],
        style_preset: form.stylePreset,
        brief: form.brief,
      };
    case "ecommerce-visual":
      return {
        tool_id: toolId,
        campaign_brief: form.brief,
        channel: form.platform,
        visual_format: "commercial_pack",
        product_image_refs: assetRefs,
        aspect_ratio: form.aspectRatio,
        style_preset: form.stylePreset,
      };
    case "digital-human":
      return {
        tool_id: toolId,
        presenter_brief: form.brief,
        product_ref: form.productRef,
        reference_asset_refs: assetRefs,
        duration_target_seconds: duration,
        consent_gate: "locked_by_default",
        style_preset: form.stylePreset,
      };
    case "storyboard":
      return {
        tool_id: toolId,
        brief: form.brief,
        duration_target_seconds: duration,
        planned_timeline_block_count: Math.max(3, Math.ceil(duration / 30)),
        review_checkpoint_refs: ["storyboard://review/checkpoint-001"],
        storyboard_grid: 12,
        reference_asset_refs: assetRefs,
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

  const updateField = (field: FieldName, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const requestPreview = useMemo(() => buildToolboxRequest(toolId, form), [form, toolId]);
  const Icon = presentation.icon;
  const requiredChecks = plan?.required_checks ?? presentation.fallbackChecks;
  const artifacts = run?.artifacts ?? [];

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
      setRun(result);
      setPlan(result.plan);
      if (result.prompt_preview) setPreview(result.prompt_preview);
    });
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
            <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.preview.injectionBoundary")}</h2>
            <div className="mt-3 space-y-3 text-sm leading-6 text-[var(--text-muted)]">
              <p>{t("toolbox.preview.refsOnly")}</p>
              <p className="font-semibold text-[var(--text-h1)]">
                {formatToolboxList(plan?.injection_target_refs ?? presentation.fallbackScenarios)}
              </p>
            </div>
          </section>
        </section>
      </main>
    </div>
  );
}
