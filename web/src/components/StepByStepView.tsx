"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  label: string;
  state: any;
  onStepComplete: (newState: any) => void;
  onResume: (finalState: any) => void;
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

const STEP_DESCRIPTIONS: Record<string, string> = {
  strategy: "stepDesc.strategy",
  scripts: "stepDesc.scripts",
  compliance: "stepDesc.compliance",
  storyboards: "stepDesc.storyboards",
  keyframe_images: "stepDesc.keyframe_images",
  video_prompts: "stepDesc.video_prompts",
  thumbnail_prompts: "stepDesc.thumbnail_prompts",
  seedance_clips: "stepDesc.seedance_clips",
  tts_audio: "stepDesc.tts_audio",
  thumbnail_images: "stepDesc.thumbnail_images",
  assemble_final: "stepDesc.assemble_final",
  audit: "stepDesc.audit",
};

export default function StepByStepView({ label, state, onStepComplete, onResume, onError, loading }: Props) {
  const { t } = useI18n();
  const [viewingStep, setViewingStep] = useState<string | null>(null);
  const [editingStep, setEditingStep] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>("");
  const [confirmRegen, setConfirmRegen] = useState<string | null>(null);

  const steps = state?.steps || {};
  const stepOrder: string[] = state?.meta?.step_order || _FALLBACK_STEP_ORDER;

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
    } catch (err: any) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Step execution failed:", err);
      onError?.(t("toast.stepExecFailed") + `: ${err?.message || String(err).slice(0, 80)}`);
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
    } catch (err: any) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Regeneration failed:", err);
      onError?.(t("toast.regenerateFailed") + `: ${err?.message || String(err).slice(0, 80)}`);
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
    } catch (err: any) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Resume failed:", err);
      onError?.(t("toast.resumeFailed") + `: ${err?.message || String(err).slice(0, 80)}`);
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
      let parsed: any;
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
    } catch (err: any) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Save edit failed:", err);
      onError?.(t("toast.saveFailed") + `: ${err?.message || String(err).slice(0, 80)}`);
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
      if (output.overall_status) return `${t("quality.overallStatus")}: ${output.overall_status}`;
      if (output.summary) return String(output.summary).slice(0, 60);
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

// ── Step Output Renderer ──

function StepOutput({ stepName, output }: { stepName: string; output: any }) {
  const { t } = useI18n();
  if (!output) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noOutput")}</p>;

  if (stepName === "strategy" || stepName === "compliance") {
    const briefs = Array.isArray(output) ? output : output.briefs || output.reports || [];
    if (briefs.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noData")}</p>;
    return (
      <div className="space-y-2 p-2">
        {briefs.map((b: any, i: number) => (
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
    const scripts = Array.isArray(output) ? output : output.scripts || [];
    if (scripts.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noScript")}</p>;
    return (
      <div className="space-y-2 p-2">
        {scripts.map((s: any, i: number) => (
          <details key={i} className="apple-card overflow-hidden">
            <summary className="p-3 cursor-pointer flex items-center gap-2 list-none">
              <span className="text-[12px] font-mono text-[var(--text-muted)]">{s.id || `S${i + 1}`}</span>
              <span className="text-sm font-medium text-[var(--text-h1)] flex-1">{s.product_name || s.brand_name || "Script"}</span>
              <span className="text-[12px] text-[var(--text-muted)]">{(s.segments || []).length}{t("step.segments")}</span>
            </summary>
            <div className="px-3 pb-3 space-y-2 border-t border-[var(--border-default)] pt-2">
              {(s.segments || []).map((seg: any, j: number) => (
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
    const boards = Array.isArray(output) ? output : output.storyboards || [];
    if (boards.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noStoryboard")}</p>;
    return (
      <div className="space-y-2 p-2">
        {boards.map((board: any, i: number) => (
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
    const items = Array.isArray(output) ? output : output.prompts || output.variants || [];
    if (items.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noData")}</p>;
    return (
      <div className="space-y-1 p-2">
        {items.map((item: any, i: number) => (
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
    const isNewFormat = output && !Array.isArray(output) && output.clip_paths;
    const paths = isNewFormat ? output.clip_paths : (Array.isArray(output) ? output : []);
    const details = isNewFormat ? (output.clip_details || []) : [];
    if (paths.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{t("step.noMedia")}</p>;
    return (
      <div className="p-2 space-y-1">
        {paths.map((path: string, i: number) => {
          const meta = details[i] || {};
          const name = path.split("/").pop() || path;
          return (
            <div key={i} className="flex items-center gap-2 text-[12px] font-mono text-[var(--text-body)]">
              <span className="w-1 h-1 rounded-full bg-[var(--fortune-red)] shrink-0" />
              <span className="truncate">{name}</span>
              {meta.duration > 0 && <span className="text-[var(--text-muted)] shrink-0">{meta.duration.toFixed(1)}s</span>}
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
      ? output
      : (output.audio_paths || []);
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
    const paths = Array.isArray(output) ? output : [];
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
          {output.video_path || output[0] || "N/A"}
        </p>
        {output.render_json_path && (
          <p className="text-xs text-[var(--text-body)] mt-1">
            {output.render_json_path}
          </p>
        )}
      </div>
    );
  }

  if (stepName === "audit") {
    const report = typeof output === "object" ? output : {};
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
            {report.overall_status || "UNKNOWN"}
          </span>
          {report.overall_score != null && (
            <span className="text-[12px] text-[var(--text-body)]">
              {(report.overall_score * 100).toFixed(0)}%
            </span>
          )}
        </div>
        {report.summary && <p className="text-xs text-[var(--text-body)]">{report.summary}</p>}
        {report.criteria && (
          <div className="space-y-0.5 mt-1">
            {report.criteria.map((c: any, i: number) => (
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
