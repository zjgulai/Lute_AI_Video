"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { errorMessage } from "@/lib/errors";
import { getSoftDegradedSummary } from "@/lib/softDegraded";
import QualityGateReportPanel, { extractQualityGateReport } from "./QualityGateReportPanel";

interface Props {
  label: string;
  state: Record<string, unknown>;
  onStepComplete: (newState: Record<string, unknown>) => void;
  onResume: (finalState: Record<string, unknown>) => void;
  onError?: (message: string) => void;
  loading: boolean;
}

const _FALLBACK_STEP_ORDER = [
  "strategy",
  "scripts",
  "compliance",
  "storyboards",
  "keyframe_images",
  "video_prompts",
  "thumbnail_prompts",
  "seedance_clips",
  "tts_audio",
  "thumbnail_images",
  "assemble_final",
  "audit",
];

const STEP_LABELS: Record<string, string> = {
  strategy: "step.strategy",
  scripts: "step.scripts",
  compliance: "step.compliance",
  storyboards: "step.storyboards",
  video_prompts: "step.video_prompts",
  thumbnail_prompts: "step.thumbnail_prompts",
  seedance_clips: "step.seedance_clips",
  tts_audio: "step.tts_audio",
  thumbnail_images: "step.thumbnail_images",
  assemble_final: "step.assemble_final",
  audit: "step.audit",
};

type StepItem = Record<string, unknown> & {
  platform?: string;
  hook_type?: string;
  product_name?: string;
  brand_name?: string;
  description?: string;
  key_message?: string;
  id?: string;
  script_id?: string;
  prompt?: string;
};

type ScriptSegment = Record<string, unknown> & {
  segment_type?: string;
  start_time?: number;
  end_time?: number;
  voiceover?: string;
  description?: string;
  visual_description?: string;
};

type ScriptItem = StepItem & {
  segments?: ScriptSegment[];
};

type StoryboardItem = Record<string, unknown> & {
  script_id?: string;
  total_duration?: number;
  shots?: unknown[];
};

type ClipDetail = {
  duration?: number;
  is_stub?: boolean;
  is_filler?: boolean;
};

type AuditCriterion = {
  name?: string;
  status?: string;
};

type CommercialInjection = {
  hard_token_ids?: unknown;
  soft_token_ids?: unknown;
  source_token_ids?: unknown;
  bundle_refs?: unknown;
  toolbox_refs?: unknown;
  contract_refs?: unknown;
  gate_checks?: unknown;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : [];
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function getCommercialInjection(stepData: Record<string, unknown>): CommercialInjection | null {
  const injection = stepData.commercial_injection;
  return injection && typeof injection === "object" && !Array.isArray(injection) ? injection as CommercialInjection : null;
}

export default function StepByStepView({ label, state, onStepComplete, onResume, onError, loading }: Props) {
  const { t } = useI18n();
  const [viewingStep, setViewingStep] = useState<string | null>(null);
  const [editingStep, setEditingStep] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>("");
  const [confirmRegen, setConfirmRegen] = useState<string | null>(null);

  const steps = (state?.steps as Record<string, Record<string, unknown>>) || {};
  const stepOrder: string[] = (state?.meta as Record<string, unknown>)?.step_order as string[] || _FALLBACK_STEP_ORDER;
  const softDegradedReasons: Array<{ step?: string; reason?: string; detail?: string }> =
    (state?.soft_degraded_reasons as Array<{ step?: string; reason?: string; detail?: string }>) || [];
  const softDegradedSummary = softDegradedReasons[0];
  const softDegradedDisplay = getSoftDegradedSummary(softDegradedSummary, t);
  const qualityGateReport = extractQualityGateReport(state);

  const getCurrentStep = (): string | null => {
    for (const step of stepOrder) {
      if (!steps[step] || steps[step].status !== "done") {
        return step;
      }
    }
    return null;
  };

  const currentStep = getCurrentStep();
  const allDone = currentStep === null;

  // Determine which steps are dependencies of current step (should be done before current)
  const getDepsFor = (stepName: string): string[] => {
    const idx = stepOrder.indexOf(stepName);
    if (idx < 0) return [];
    return stepOrder.slice(0, idx);
  };

  const handleRunStep = async (stepName: string) => {
    const { runS1Step } = await import("./api");
    try {
      const result = await runS1Step(label, stepName);
      onStepComplete(result?.state || result);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Step execution failed:", err);
      onError?.(t("toast.stepExecFailed") + `: ${errorMessage(err).slice(0, 80)}`);
      const { fetchS1State } = await import("./api");
      const freshState = await fetchS1State(label);
      onStepComplete(freshState);
    }
  };

  const handleRegenerate = async (stepName: string) => {
    setConfirmRegen(null);
    const { regenerateS1Step } = await import("./api");
    try {
      const result = await regenerateS1Step(label, stepName);
      onStepComplete(result?.state || result);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Regeneration failed:", err);
      onError?.(t("toast.regenerateFailed") + `: ${errorMessage(err).slice(0, 80)}`);
      const { fetchS1State } = await import("./api");
      const freshState = await fetchS1State(label);
      onStepComplete(freshState);
    }
  };

  const handleResume = async () => {
    const { resumeS1 } = await import("./api");
    try {
      const result = await resumeS1(label);
      onResume(result?.state || result);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Resume failed:", err);
      onError?.(t("toast.resumeFailed") + `: ${errorMessage(err).slice(0, 80)}`);
    }
  };

  // ── Edit support ──

  const openEditor = (stepName: string) => {
    const stepData = steps[stepName] || {};
    const output = stepData.edited_output ?? stepData.output;
    const raw = output !== undefined && output !== null
      ? (typeof output === "object" ? JSON.stringify(output, null, 2) : String(output))
      : "";
    setEditValue(raw);
    setEditingStep(stepName);
  };

  const saveEdit = async () => {
    if (!editingStep) return;
    const { updateS1State } = await import("./api");
    try {
      // Parse the edit value — try JSON first, fallback to plain text
      let parsed: unknown;
      try {
        parsed = JSON.parse(editValue);
      } catch {
        parsed = editValue; // Keep as plain string
      }

      await updateS1State(label, {
        steps: {
          [editingStep]: {
            edited: true,
            edited_output: parsed,
          },
        },
      });

      // Reload state
      const { fetchS1State } = await import("./api");
      const freshState = await fetchS1State(label);
      onStepComplete(freshState);
      setEditingStep(null);
      setEditValue("");
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Save edit failed:", err);
      onError?.(t("toast.saveFailed") + `: ${errorMessage(err).slice(0, 80)}`);
    }
  };

  const cancelEdit = () => {
    setEditingStep(null);
    setEditValue("");
  };

  const getOutputPreview = (stepName: string): string => {
    const sd = steps[stepName] || {};
    const output = sd.edited_output ?? sd.output;
    if (!output) return "";
    if (Array.isArray(output)) return `${output.length}${t("step.items")}`;
    if (typeof output === "object") {
      const obj = output as { overall_status?: string; summary?: string };
      if (obj.overall_status) return `${t("quality.overallStatus")}: ${obj.overall_status}`;
      if (obj.summary) return String(obj.summary).slice(0, 60);
      const keys = Object.keys(output);
      if (keys.length > 0) return `${keys.length}${t("step.fields")}`;
    }
    return String(output).slice(0, 60);
  };

  const getDownstreamSteps = (stepName: string): string[] => {
    const idx = stepOrder.indexOf(stepName);
    if (idx < 0 || idx >= stepOrder.length - 1) return [];
    return stepOrder.slice(idx + 1);
  };

  return (
    <div className="space-y-3 animate-slide-up">
      {/* Header card */}
      <div className="apple-card p-4">
        <div className="flex items-center justify-between mb-1">
          <div>
            <h2 className="text-base font-semibold text-[var(--text-h1)]">{t("stepbystep.title")}</h2>
            <p className="text-[12px] text-[var(--text-body)] mt-0.5 font-mono">{t("stepbystep.runId")}: {label}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-[12px] font-semibold px-2 py-0.5 rounded-full ${allDone ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]" : "bg-[rgba(255,149,0,0.10)] text-[var(--gold-foil)]"}`}>
              {allDone ? t("step.allDone") : t("step.executing")}
            </span>
          </div>
        </div>

        {softDegradedReasons.length > 0 && (
          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2.5">
            <p className="text-[12px] font-medium text-amber-800">
              {t("degraded.softTitle")}
              {softDegradedDisplay.stepLabel ? ` · ${softDegradedDisplay.stepLabel}` : ""}
              {softDegradedDisplay.reasonLabel ? ` · ${softDegradedDisplay.reasonLabel}` : ""}
            </p>
            {softDegradedDisplay.detail ? (
              <p className="mt-1 text-[12px] text-amber-700">{softDegradedDisplay.detail}</p>
            ) : null}
          </div>
        )}

        {qualityGateReport && (
          <div className="mt-3">
            <QualityGateReportPanel report={qualityGateReport} />
          </div>
        )}

        {/* Step list */}
        <div className="space-y-1 mt-3">
          {stepOrder.map((stepName, index) => {
            const stepData = steps[stepName] || { status: "pending" };
            const isDone = stepData.status === "done";
            const isCurrent = stepName === currentStep && !isDone;
            const isFuture = !isDone && !isCurrent;
            const deps = getDepsFor(stepName);
            const depsAllComplete = deps.every((d) => {
              const sd = steps[d];
              return sd && sd.status === "done";
            });
            const canRun = isCurrent && depsAllComplete;
            const isEditing = editingStep === stepName;
            const downstream = getDownstreamSteps(stepName);
            const commercialInjection = getCommercialInjection(stepData);

            return (
              <div key={stepName}>
                {/* Step row */}
                <div
                  className={`flex items-center gap-2 p-2.5 rounded-lg border transition-all cursor-pointer ${
                    isDone
                      ? "bg-[var(--bg-panel)] border-[var(--border-default)] hover:bg-[rgba(215,92,112,0.10)]"
                      : isCurrent
                      ? "bg-[var(--bg-card)] border-[var(--fortune-red)] ring-1 ring-[rgba(215,92,112,0.20)]"
                      : "bg-[var(--bg-card)] border-[var(--border-default)] opacity-60"
                  }`}
                  onClick={() => {
                    if (isDone && !isEditing) {
                      setViewingStep(viewingStep === stepName ? null : stepName);
                    }
                  }}
                >
                  <span className="text-[12px] font-mono text-[var(--text-muted)] w-5 shrink-0">{index + 1}</span>

                  <div className={`w-2 h-2 rounded-full shrink-0 ${isDone ? "bg-[var(--jade-accent)]" : isCurrent ? "bg-[var(--gold-foil)] animate-pulse" : "bg-[var(--border-default)]"}`} />

                  <span className={`text-xs font-medium flex-1 min-w-0 ${isDone ? "text-[var(--text-h1)]" : isCurrent ? "text-[var(--text-h1)]" : "text-[var(--text-muted)]"}`}>
                    {t(STEP_LABELS[stepName])}
                    {commercialInjection && (
                      <span className="ml-2 inline-flex max-w-full items-center gap-1 rounded-full border border-[rgba(220,190,120,0.35)] bg-[rgba(220,190,120,0.10)] px-1.5 py-0.5 align-middle text-[11px] font-semibold text-[var(--gold-foil)]">
                        <span>{t("commercialInjection.badge")}</span>
                        <span className="text-[var(--text-muted)]">{t("commercialInjection.readOnly")}</span>
                      </span>
                    )}
                    {isDone && getOutputPreview(stepName) && (
                      <span className="ml-2 text-[12px] text-[var(--text-muted)] font-normal">
                        {getOutputPreview(stepName)}
                      </span>
                    )}
                  </span>

                  <span className={`text-[12px] font-medium shrink-0 ${isDone ? "text-[var(--jade-accent)]" : isCurrent ? "text-[var(--gold-foil)]" : "text-[var(--text-muted)]"}`}>
                    {isDone ? t("step.done") : isCurrent ? t("step.pending") : t("step.notStarted")}
                  </span>

                  {/* Actions for completed steps */}
                  {isDone && (
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={(e) => { e.stopPropagation(); setViewingStep(viewingStep === stepName ? null : stepName); }}
                        className="text-[12px] text-[var(--fortune-red)] hover:underline cursor-pointer px-1.5 py-0.5 rounded hover:bg-[rgba(215,92,112,0.05)]"
                      >
                        {viewingStep === stepName ? t("step.hide") : t("step.view")}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); openEditor(stepName); }}
                        className="text-[12px] text-[var(--text-body)] hover:text-[var(--text-h1)] cursor-pointer px-1.5 py-0.5 rounded hover:bg-[rgba(215,92,112,0.18)]"
                      >
                        {t("step.edit")}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setConfirmRegen(confirmRegen === stepName ? null : stepName); }}
                        disabled={loading}
                        className="text-[12px] text-[var(--text-body)] hover:text-[var(--crimson-mist)] cursor-pointer px-1.5 py-0.5 rounded hover:bg-[rgba(196,91,80,0.05)] disabled:opacity-50"
                      >
                        {t("step.regenerate")}
                      </button>
                    </div>
                  )}

                  {/* Run step button for current/pending steps */}
                  {!isDone && canRun && (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRunStep(stepName); }}
                      disabled={loading}
                      className="apple-btn apple-btn-primary text-[12px] px-2.5 py-1 disabled:opacity-50 shrink-0"
                    >
                      {loading ? t("step.running") : t("step.run")}
                    </button>
                  )}

                  {/* Show run button even for non-current pending steps if all their deps are done */}
                  {!isDone && !canRun && isFuture && depsAllComplete && (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRunStep(stepName); }}
                      disabled={loading}
                      className="text-[12px] text-[var(--text-body)] hover:text-[var(--text-h1)] cursor-pointer px-1.5 py-0.5 rounded hover:bg-[rgba(215,92,112,0.18)] shrink-0"
                    >
                      {t("step.run")}
                    </button>
                  )}
                </div>

                {commercialInjection && (
                  <CommercialInjectionPanel injection={commercialInjection} />
                )}

                {/* Regenerate confirmation warning */}
                {confirmRegen === stepName && (
                  <div className="ml-7 mt-1 mb-1 p-2.5 rounded-lg bg-[rgba(196,91,80,0.08)] border border-[rgba(196,91,80,0.20)] animate-slide-up">
                    <div className="flex items-start gap-2">
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0 mt-0.5">
                        <circle cx="7" cy="7" r="6" stroke="var(--crimson-mist)" strokeWidth="1.2" />
                        <line x1="7" y1="4" x2="7" y2="8" stroke="var(--crimson-mist)" strokeWidth="1.2" strokeLinecap="round" />
                        <circle cx="7" cy="10" r="0.8" fill="var(--crimson-mist)" />
                      </svg>
                      <div className="flex-1">
                        <p className="text-[12px] font-medium text-[var(--crimson-mist)] mb-1">
                          {t("step.regenerateWarning")} &ldquo;{t(STEP_LABELS[stepName])}&rdquo; {t("step.downstreamWarning")}
                        </p>
                        <div className="flex flex-wrap gap-1 mb-2">
                          {downstream.map((ds) => (
                            <span key={ds} className="text-[12px] px-1.5 py-0.5 rounded bg-[rgba(196,91,80,0.10)] text-[var(--crimson-mist)]">
                              {t(STEP_LABELS[ds]) || ds}
                            </span>
                          ))}
                          {downstream.length === 0 && (
                            <span className="text-[12px] text-[var(--text-body)]">{t("step.noDownstream")}</span>
                          )}
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleRegenerate(stepName)}
                            disabled={loading}
                            className="text-[12px] bg-[var(--crimson-mist)] text-white px-2.5 py-1 rounded-lg hover:bg-[var(--neon-red)] disabled:opacity-50"
                          >
                            {loading ? t("step.regenerating") : t("step.confirmRegen")}
                          </button>
                          <button
                            onClick={() => setConfirmRegen(null)}
                            className="text-[12px] text-[var(--text-body)] px-2.5 py-1 rounded-lg hover:bg-[rgba(215,92,112,0.18)]"
                          >
                            {t("step.cancel")}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Step output (view mode) */}
                {viewingStep === stepName && isDone && !isEditing && (
                  <div className="ml-7 mt-1 mb-1 animate-slide-up">
                    <StepOutput stepName={stepName} output={stepData.edited_output ?? stepData.output} />
                  </div>
                )}

                {/* Inline editor */}
                {isEditing && (
                  <div className="ml-7 mt-1 mb-1 p-3 rounded-lg bg-[var(--bg-card)] border border-[var(--fortune-red)] ring-1 ring-[rgba(215,92,112,0.20)] animate-slide-up">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[12px] font-semibold text-[var(--text-h1)]">
                        {t("step.editTitle")} &ldquo;{t(STEP_LABELS[stepName])}&rdquo; {t("step.editOutput")}
                      </span>
                      <span className="text-[12px] text-[var(--text-muted)]">{t("step.editDesc")}</span>
                    </div>
                    <textarea
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      className="w-full min-h-[120px] p-2.5 text-[12px] font-mono text-[var(--text-h1)] bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[rgba(215,92,112,0.30)] focus:border-[var(--fortune-red)] resize-y"
                      placeholder={t("step.jsonPlaceholder")}
                    />
                    <div className="flex gap-2 mt-2">
                      <button
                        onClick={saveEdit}
                        disabled={loading}
                        className="apple-btn apple-btn-primary text-[12px] px-3 py-1.5 disabled:opacity-50"
                      >
                        {loading ? t("step.saving") : t("step.save")}
                      </button>
                      <button
                        onClick={cancelEdit}
                        className="text-[12px] text-[var(--text-body)] px-3 py-1.5 rounded-lg hover:bg-[rgba(215,92,112,0.18)]"
                      >
                        {t("step.cancel")}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Bottom actions */}
        <div className="mt-4 pt-3 border-t border-[var(--border-default)] space-y-2">
          <button
            onClick={handleResume}
            disabled={loading || allDone}
            className="apple-btn apple-btn-primary w-full py-2 text-sm disabled:opacity-50"
          >
            {loading ? t("step.running") : allDone ? t("step.allDone") : t("step.resume")}
          </button>

          {!allDone && (
            <div className="flex items-center justify-center gap-2">
              <span className="text-[12px] text-[var(--text-muted)]">
                {t("stepbystep.progress")} {stepOrder.filter((s) => (steps[s] || {}).status === "done").length}{t("stepbystep.of")}{stepOrder.length}
              </span>
            </div>
          )}

          {allDone && (
            <div className="text-center">
              <div className="inline-flex items-center gap-1.5 text-xs text-[var(--jade-accent)] font-medium">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M3 6.5L5 8.5L9 3.5" stroke="var(--jade-accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {t("stepbystep.stepsComplete")}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CommercialInjectionPanel({ injection }: { injection: CommercialInjection }) {
  const { t } = useI18n();
  const groups = [
    { label: t("commercialInjection.bundle"), values: stringList(injection.bundle_refs) },
    { label: t("commercialInjection.toolbox"), values: stringList(injection.toolbox_refs) },
    { label: t("commercialInjection.contract"), values: stringList(injection.contract_refs) },
    { label: t("commercialInjection.gate"), values: stringList(injection.gate_checks) },
    {
      label: t("commercialInjection.tokens"),
      values: [
        ...stringList(injection.hard_token_ids),
        ...stringList(injection.soft_token_ids),
        ...stringList(injection.source_token_ids),
      ],
    },
  ].filter((group) => group.values.length > 0);

  if (groups.length === 0) return null;

  return (
    <div className="ml-7 mt-1 mb-1 rounded-lg border border-[rgba(220,190,120,0.22)] bg-[rgba(220,190,120,0.06)] px-2.5 py-2">
      <div className="flex flex-wrap gap-1.5">
        {groups.map((group) => (
          <div key={group.label} className="flex min-w-0 max-w-full items-center gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">
              {group.label}
            </span>
            <div className="flex min-w-0 flex-wrap gap-1">
              {group.values.map((value) => (
                <span
                  key={`${group.label}-${value}`}
                  className="max-w-[180px] truncate rounded-md bg-[var(--bg-panel)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--text-h1)]"
                  title={value}
                >
                  {value}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Step Output Renderer ──

function StepOutput({ stepName, output }: { stepName: string; output: unknown }) {
  const { t } = useI18n();
  if (!output) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noOutput")}</p>;
  const outputRecord = asRecord(output);

  if (stepName === "strategy" || stepName === "compliance") {
    const briefs = Array.isArray(output)
      ? asArray<StepItem>(output)
      : asArray<StepItem>(outputRecord.briefs || outputRecord.reports);
    if (briefs.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noData")}</p>;
    return (
      <div className="space-y-2 p-2">
        {briefs.map((b, i) => (
          <div key={i} className="apple-card p-3 bg-[var(--bg-card)]">
            <div className="flex items-start gap-2 mb-1">
              {b.platform && (
                <span className="text-[12px] font-semibold px-2 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] shrink-0">
                  {t("platform." + b.platform)}
                </span>
              )}
              {b.hook_type && (
                <span className="text-[12px] font-medium px-2 py-0.5 rounded-full bg-[rgba(89,88,94,0.10)] text-[var(--text-body)]">
                  {b.hook_type}
                </span>
              )}
            </div>
            <h4 className="text-sm font-semibold text-[var(--text-h1)] mb-1">{b.product_name || b.brand_name || "Item"}</h4>
            {b.description && <p className="text-xs text-[var(--text-body)] leading-relaxed">{b.description}</p>}
            {b.key_message && <p className="text-xs text-[var(--text-body)] leading-relaxed mt-1">{b.key_message}</p>}
          </div>
        ))}
      </div>
    );
  }

  if (stepName === "scripts") {
    const scripts = Array.isArray(output) ? asArray<ScriptItem>(output) : asArray<ScriptItem>(outputRecord.scripts);
    if (scripts.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noScript")}</p>;
    return (
      <div className="space-y-2 p-2">
        {scripts.map((s, i) => (
          <details key={i} className="apple-card overflow-hidden">
            <summary className="p-3 cursor-pointer flex items-center gap-2 list-none">
              <span className="text-[12px] font-mono text-[var(--text-muted)]">{s.id || `S${i + 1}`}</span>
              <span className="text-sm font-medium text-[var(--text-h1)] flex-1">{s.product_name || s.brand_name || "Script"}</span>
              <span className="text-[12px] text-[var(--text-muted)]">{(s.segments || []).length}{t("step.segments")}</span>
            </summary>
            <div className="px-3 pb-3 space-y-2 border-t border-[var(--border-default)] pt-2">
              {(s.segments || []).map((seg, j) => (
                <div key={j} className="pl-3 border-l-2 border-[var(--border-default)]">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[12px] font-semibold text-[var(--fortune-red)] uppercase">{seg.segment_type}</span>
                    <span className="text-[12px] text-[var(--text-muted)] font-mono">
                      {seg.start_time ?? 0}s — {seg.end_time ?? 0}s
                    </span>
                  </div>
                  <p className="text-xs text-[var(--text-h1)]">{seg.voiceover || seg.description}</p>
                  {seg.visual_description && (
                    <p className="text-[12px] text-[var(--text-body)] mt-1 italic">{seg.visual_description}</p>
                  )}
                </div>
              ))}
            </div>
          </details>
        ))}
      </div>
    );
  }

  if (stepName === "storyboards") {
    const boards = Array.isArray(output) ? asArray<StoryboardItem>(output) : asArray<StoryboardItem>(outputRecord.storyboards);
    if (boards.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noStoryboard")}</p>;
    return (
      <div className="space-y-2 p-2">
        {boards.map((board, i) => (
          <div key={i} className="apple-card p-3 bg-[var(--bg-card)]">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[12px] font-mono text-[var(--text-muted)]">{board.script_id || `Board ${i + 1}`}</span>
              <span className="text-[12px] text-[var(--text-muted)]">{board.total_duration || "?"}s</span>
            </div>
            <p className="text-[12px] text-[var(--text-body)]">{(board.shots || []).length}{t("step.shots")}</p>
          </div>
        ))}
      </div>
    );
  }

  if (stepName === "video_prompts" || stepName === "thumbnail_prompts") {
    const items = Array.isArray(output)
      ? asArray<StepItem>(output)
      : asArray<StepItem>(outputRecord.prompts || outputRecord.variants);
    if (items.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noData")}</p>;
    return (
      <div className="space-y-1 p-2">
        {items.map((item, i) => (
          <div key={i} className="apple-card p-2 bg-[var(--bg-card)]">
            <p className="text-[12px] font-mono text-[var(--text-muted)] mb-1">{item.script_id || `Item ${i + 1}`}</p>
            <p className="text-[12px] text-[var(--text-h1)] font-mono whitespace-pre-wrap break-all">
              {typeof item.prompt === "string" ? item.prompt.slice(0, 200) : JSON.stringify(item).slice(0, 200)}
            </p>
          </div>
        ))}
      </div>
    );
  }

  if (stepName === "seedance_clips") {
    const isNewFormat = !Array.isArray(output) && Array.isArray(outputRecord.clip_paths);
    const paths = isNewFormat ? asArray<string>(outputRecord.clip_paths) : asArray<string>(output);
    const details = isNewFormat ? asArray<ClipDetail>(outputRecord.clip_details) : [];
    if (paths.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noMedia")}</p>;
    return (
      <div className="p-2 space-y-1">
        {paths.map((path: string, i: number) => {
          const meta = details[i] || {};
          const duration = meta.duration;
          const name = path.split("/").pop() || path;
          return (
            <div key={i} className="flex items-center gap-2 text-[12px] font-mono text-[var(--text-body)]">
              <span className="w-1 h-1 rounded-full bg-[var(--fortune-red)] shrink-0" />
              <span className="truncate">{name}</span>
              {typeof duration === "number" && duration > 0 && <span className="text-[var(--text-muted)] shrink-0">{duration.toFixed(1)}s</span>}
              {meta.is_stub && <span className="text-[var(--gold-foil)] shrink-0">[stub]</span>}
              {meta.is_filler && <span className="text-[var(--cinema-azure)] shrink-0">[filler]</span>}
            </div>
          );
        })}
      </div>
    );
  }

  if (stepName === "tts_audio") {
    const paths = Array.isArray(output)
      ? asArray<string>(output)
      : asArray<string>(outputRecord.audio_paths);
    if (paths.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noMedia")}</p>;
    return (
      <div className="p-2">
        <p className="text-[12px] text-[var(--text-body)]">{paths.length}{t("step.files")}</p>
        <div className="space-y-1 mt-1">
          {paths.map((path: string, i: number) => (
            <div key={i} className="flex items-center gap-1 text-[12px] font-mono text-[var(--text-body)] truncate">
              <span className="w-1 h-1 rounded-full bg-[var(--fortune-red)] shrink-0" />
              {path.split("/").pop() || path}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (stepName === "thumbnail_images") {
    const paths = asArray<string>(output);
    if (paths.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noMedia")}</p>;
    return (
      <div className="p-2">
        <p className="text-[12px] text-[var(--text-body)]">{paths.length}{t("step.files")}</p>
        <div className="space-y-1 mt-1">
          {paths.map((path: string, i: number) => (
            <div key={i} className="flex items-center gap-1 text-[12px] font-mono text-[var(--text-body)] truncate">
              <span className="w-1 h-1 rounded-full bg-[var(--fortune-red)] shrink-0" />
              {path.split("/").pop() || path}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (stepName === "assemble_final") {
    if (typeof output === "string") {
      return <p className="text-xs text-[var(--text-body)] p-2">{output}</p>;
    }
    if (Array.isArray(output)) {
      return <p className="text-xs text-[var(--text-body)] p-2">{output[0] || "N/A"}</p>;
    }
    return (
      <div className="p-2">
        <p className="text-xs text-[var(--text-body)]">
          {typeof outputRecord.video_path === "string" ? outputRecord.video_path : "N/A"}
        </p>
        {typeof outputRecord.render_json_path === "string" && (
          <p className="text-xs text-[var(--text-body)] mt-1">
            {outputRecord.render_json_path}
          </p>
        )}
      </div>
    );
  }

  if (stepName === "audit") {
    const report = asRecord(output);
    return (
      <div className="p-2 space-y-1">
        <div className="flex items-center gap-2">
          <span className={`text-[12px] font-semibold px-2 py-0.5 rounded-full ${
            report.overall_status === "PASS"
              ? "bg-[rgba(110,150,110,0.12)] text-[var(--jade-accent)]"
              : report.overall_status === "WARN"
              ? "bg-[rgba(255,149,0,0.10)] text-[var(--gold-foil)]"
              : "bg-[rgba(196,91,80,0.10)] text-[var(--crimson-mist)]"
          }`}>
            {typeof report.overall_status === "string" ? report.overall_status : "UNKNOWN"}
          </span>
          {typeof report.overall_score === "number" && (
            <span className="text-[12px] text-[var(--text-body)]">
              {(report.overall_score * 100).toFixed(0)}%
            </span>
          )}
        </div>
        {typeof report.summary === "string" && <p className="text-xs text-[var(--text-body)]">{report.summary}</p>}
        {Array.isArray(report.criteria) && (
          <div className="space-y-0.5 mt-1">
            {asArray<AuditCriterion>(report.criteria).map((c, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <span className={`w-1 h-1 rounded-full ${
                  c.status === "PASS" ? "bg-[var(--jade-accent)]" : c.status === "WARN" ? "bg-[var(--gold-foil)]" : "bg-[var(--crimson-mist)]"
                }`} />
                <span className="text-[12px] text-[var(--text-h1)]">{c.name}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <pre className="text-[12px] font-mono text-[var(--text-body)] bg-[var(--bg-card)] p-3 rounded-lg overflow-auto max-h-[300px] whitespace-pre-wrap break-all">
      {JSON.stringify(output, null, 2)}
    </pre>
  );
}
