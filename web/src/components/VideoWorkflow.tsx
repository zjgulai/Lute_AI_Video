"use client";

import { useState, useCallback } from "react";
import { getMediaUrl } from "./api";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  config: any;
  label: string;
  state: any;
  onStateChange: (newState: any) => void;
  onComplete: (finalState: any) => void;
  onReset: () => void;
  loading: boolean;
  setLoading: (v: boolean) => void;
  setLoadingText: (v: string) => void;
}

const STEP_ORDER = [
  "strategy",
  "scripts",
  "compliance",
  "storyboards",
  "video_prompts",
  "thumbnail_prompts",
  "seedance_clips",
  "tts_audio",
  "thumbnail_images",
  "assemble_final",
  "audit",
];

const STEP_DURATIONS: Record<string, string> = {
  strategy: "~5s",
  scripts: "~5s",
  compliance: "~2s",
  storyboards: "~4s",
  video_prompts: "~3s",
  thumbnail_prompts: "~3s",
  seedance_clips: "~6min",      // 2 clips × ~3min each
  tts_audio: "~3min",          // merged: 1 call per script
  thumbnail_images: "~2min",   // 2 images
  assemble_final: "~15s",
  audit: "~5s",
};

export default function VideoWorkflow({
  config,
  label,
  state,
  onStateChange,
  onComplete,
  onReset,
  loading,
  setLoading,
  setLoadingText,
}: Props) {
  const { t } = useI18n();
  const [viewingStep, setViewingStep] = useState<string | null>(null);
  const [editingStep, setEditingStep] = useState<string | null>(null);
  const [runningStep, setRunningStep] = useState<string | null>(null);

  const steps = state?.steps || {};

  /** Format a duration from milliseconds to human-readable text.
   *  e.g. 5000 → "~5s", 180000 → "~3min"
   */
  const formatDuration = (ms: number): string => {
    if (ms < 1000) return "~0s";
    if (ms < 60000) return `~${Math.round(ms / 1000)}s`;
    return `~${Math.round(ms / 60000)}min`;
  };

  /** Return display label for a step's duration.
   *  Prefers recorded duration_ms from state, falls back to hard-coded estimate.
   */
  const getStepDurationLabel = (stepName: string): string => {
    const dur = steps[stepName]?.duration_ms;
    if (dur && dur > 0) {
      return formatDuration(dur);
    }
    return STEP_DURATIONS[stepName] || "";
  };

  const getCurrentStep = (): string | null => {
    for (const step of STEP_ORDER) {
      if (!steps[step] || steps[step].status !== "done") {
        return step;
      }
    }
    return null;
  };

  const currentStep = getCurrentStep();
  const allDone = currentStep === null;

  const refreshState = useCallback(async () => {
    const { fetchS1State } = await import("./api");
    const fresh = await fetchS1State(label);
    onStateChange(fresh.state || fresh);
  }, [label, onStateChange]);

  const handleRunStep = async (stepName: string) => {
    setLoading(true);
    setLoadingText(t("editors.running") + `: ${t("wstep." + stepName)}...`);
    setRunningStep(stepName);
    try {
      const { runS1Step } = await import("./api");
      const result = await runS1Step(label, stepName);
      const newState = result?.state || result;
      onStateChange(newState);
      setViewingStep(stepName);
    } catch (e: any) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      const msg = e?.message || String(e);
      try { await refreshState(); } catch { /* best-effort reload */ }
      showToast(t("toast.stepExecFailed") + `: ${msg}`, "error");
    } finally {
      setLoading(false);
      setRunningStep(null);
      setLoadingText(t("app.loading"));
    }
  };

  const handleRegenerate = async (stepName: string) => {
    setLoading(true);
    setLoadingText(t("editors.regenerating") + `: ${t("wstep." + stepName)}...`);
    setRunningStep(stepName);
    try {
      const { regenerateS1Step } = await import("./api");
      const result = await regenerateS1Step(label, stepName);
      const newState = result?.state || result;
      onStateChange(newState);
      setViewingStep(stepName);
      setEditingStep(null);
    } catch (e: any) {
      const msg = e?.message || String(e);
      if (e instanceof DOMException && e.name === "AbortError") return;
      try { await refreshState(); } catch { /* best-effort reload */ }
      showToast(t("toast.regenerateFailed") + `: ${msg}`, "error");
    } finally {
      setLoading(false);
      setRunningStep(null);
      setLoadingText(t("app.loading"));
    }
  };

  const handleSaveEdit = async (stepName: string, newOutput: any) => {
    setLoading(true);
    setLoadingText(t("editors.saving"));
    try {
      const { updateS1State } = await import("./api");
      const updatedSteps = { ...steps };
      updatedSteps[stepName] = {
        ...updatedSteps[stepName],
        output: newOutput,
        edited: true,
        edited_output: newOutput,
      };
      await updateS1State(label, { steps: updatedSteps });
      onStateChange({ ...state, steps: updatedSteps });
      setEditingStep(null);
      showToast(t("toast.saveSuccess"), "success");
    } catch (e: any) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      try { await refreshState(); } catch { /* best-effort reload */ }
      showToast(t("toast.saveFailed") + `: ${e?.message || String(e)}`, "error");
    } finally {
      setLoading(false);
      setLoadingText(t("app.loading"));
    }
  };

  const handleResume = async () => {
    setLoading(true);
    setLoadingText(t("editors.resuming"));
    try {
      const { resumeS1 } = await import("./api");
      const result = await resumeS1(label);
      const finalState = result?.state || result;
      onStateChange(finalState);
      onComplete(finalState);
    } catch (e: any) {
      const msg = e?.message || String(e);
      if (e instanceof DOMException && e.name === "AbortError") return;
      try { await refreshState(); } catch { /* best-effort reload */ }
      showToast(t("toast.resumeFailed") + `: ${msg}`, "error");
    } finally {
      setLoading(false);
      setLoadingText(t("app.loading"));
    }
  };

  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const showToast = (message: string, type: "success" | "error") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const productName = config?.product_catalog?.products?.[0]?.name
    || config?.product_catalog?.name
    || t("common.unknownProduct");
  const brandName = config?.brand_guidelines?.brand_name || "";
  const platforms = config?.target_platforms || [];
  const duration = config?.video_duration || 10;
  const scenarioLabel = config?.content_scenario === "product_direct" ? t("workflow.productDirect") : t("workflow.liveShoot");

  return (
    <div className="space-y-3 animate-slide-up">
      {toast && (
        <div className={`apple-toast apple-toast-${toast.type}`}>
          <div className="flex items-center gap-2">{toast.message}</div>
        </div>
      )}

      {/* Config Summary Card */}
      <div className="apple-card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#6A2B3A]/10 flex items-center justify-center">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6A2B3A" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <line x1="9" y1="9" x2="15" y2="9" />
                <line x1="9" y1="12" x2="15" y2="12" />
                <line x1="9" y1="15" x2="11" y2="15" />
              </svg>
            </div>
            <div>
              <h2 className="text-sm font-semibold text-[#35353B]">{t("workflow.title")}</h2>
              <p className="text-[11px] text-[#59585E]">Label: {label}</p>
            </div>
          </div>
          <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${allDone ? "bg-[#6A2B3A]/10 text-[#6A2B3A]" : "bg-[#ff9500]/10 text-[#ff9500]"}`}>
            {allDone ? t("wstatus.allDone") : t("wstatus.running")}
          </span>
        </div>

        <div className="grid grid-cols-4 gap-2">
          <div className="bg-[#FCE4E2] rounded-lg p-2">
            <p className="text-[9px] text-[#59585E] uppercase">{t("workflow.product")}</p>
            <p className="text-xs font-medium text-[#35353B] truncate">{productName}</p>
          </div>
          <div className="bg-[#FCE4E2] rounded-lg p-2">
            <p className="text-[9px] text-[#59585E] uppercase">{t("workflow.brand")}</p>
            <p className="text-xs font-medium text-[#35353B]">{brandName || "-"}</p>
          </div>
          <div className="bg-[#FCE4E2] rounded-lg p-2">
            <p className="text-[9px] text-[#59585E] uppercase">{t("workflow.duration")}</p>
            <p className="text-xs font-medium text-[#35353B]">{duration}s</p>
          </div>
          <div className="bg-[#FCE4E2] rounded-lg p-2">
            <p className="text-[9px] text-[#59585E] uppercase">{t("workflow.scenario")}</p>
            <p className="text-xs font-medium text-[#35353B]">{scenarioLabel}</p>
          </div>
        </div>

        {platforms.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {platforms.map((p: string) => (
              <span key={p} className="text-[11px] px-2 py-0.5 rounded-full bg-[#6A2B3A]/10 text-[#6A2B3A] border border-[#6A2B3A]/15">
                {t("platform." + p)}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Steps Timeline */}
      <div className="apple-card p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold text-[#35353B]">{t("workflow.timeline")}</h3>
          <span className="text-[11px] text-[#59585E]">
            {STEP_ORDER.filter((s) => steps[s]?.status === "done").length} / {STEP_ORDER.length} {t("workflow.completed")}
          </span>
        </div>

        <div className="space-y-1">
          {STEP_ORDER.map((stepName, index) => {
            const stepData = steps[stepName] || { status: "pending" };
            const isDone = stepData.status === "done";
            const isCurrent = stepName === currentStep;
            const isFuture = !isDone && !isCurrent;
            const isRunning = runningStep === stepName;
            const hasError = stepData.status === "error" || (state?.errors || []).some((e: string) => e.includes(stepName));
            const isEdited = stepData.edited === true;

            return (
              <div key={stepName} className="space-y-1">
                <div
                  className={`flex items-center gap-2 p-2.5 rounded-lg border transition-all ${
                    hasError
                      ? "bg-[#fff5f5] border-[#C45B50] ring-1 ring-[#C45B50]/10"
                      : isDone
                      ? isEdited
                        ? "bg-[#6A2B3A]/5 border-[#6A2B3A]/30 ring-1 ring-[#6A2B3A]/10"
                        : "bg-[#FCE4E2] border-[#EDD3D1]"
                      : isCurrent
                      ? "bg-white border-[#6A2B3A] ring-1 ring-[#6A2B3A]/20"
                      : "bg-[#FFF5F2] border-[#EDD3D1] opacity-50"
                  }`}
                >
                  <span className={`text-[11px] font-mono w-5 text-center ${isDone ? "text-[#6A2B3A]" : isCurrent ? "text-[#ff9500]" : "text-[#9FA0A0]"}`}>
                    {isDone ? (
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                        <path d="M4 8.5L7 11.5L12 5" stroke="#6A2B3A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    ) : (
                      index + 1
                    )}
                  </span>

                  <div className={`w-2 h-2 rounded-full shrink-0 ${
                    hasError ? "bg-[#C45B50]" : isDone ? "bg-[#6A2B3A]" : isCurrent ? "bg-[#ff9500] animate-pulse" : "bg-[#EDD3D1]"
                  }`} />

                  <span className={`text-xs font-medium flex-1 ${hasError ? "text-[#C45B50]" : isDone ? "text-[#35353B]" : isCurrent ? "text-[#35353B]" : "text-[#9FA0A0]"}`}>
                    {t("wstep." + stepName)}
                  </span>

                  {isEdited && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-[#6A2B3A]/10 text-[#6A2B3A] font-medium">{t("stepStatus.edited")}</span>
                  )}

                  <span className="text-[9px] text-[#9FA0A0] hidden sm:inline">{getStepDurationLabel(stepName)}</span>

                  <span className={`text-[11px] font-medium ${hasError ? "text-[#C45B50]" : isDone ? "text-[#6A2B3A]" : isCurrent ? "text-[#ff9500]" : "text-[#9FA0A0]"}`}>
                    {hasError ? t("stepStatus.failed") : isDone ? t("stepStatus.completed") : isCurrent ? t("stepStatus.pending") : t("stepStatus.notStarted")}
                  </span>

                  {isDone && !isRunning && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => {
                          setViewingStep(viewingStep === stepName ? null : stepName);
                          setEditingStep(null);
                        }}
                        className="text-[11px] text-[#6A2B3A] hover:underline cursor-pointer px-1.5 py-0.5 rounded hover:bg-[#6A2B3A]/5"
                      >
                        {viewingStep === stepName ? t("waction.hide") : t("waction.view")}
                      </button>
                      <button
                        onClick={() => {
                          setEditingStep(editingStep === stepName ? null : stepName);
                          setViewingStep(stepName);
                        }}
                        className="text-[11px] text-[#ff9500] hover:underline cursor-pointer px-1.5 py-0.5 rounded hover:bg-[#ff9500]/5"
                      >
                        {editingStep === stepName ? t("waction.cancelEdit") : t("waction.edit")}
                      </button>
                      <button
                        onClick={() => handleRegenerate(stepName)}
                        disabled={loading}
                        className="text-[11px] text-[#59585E] hover:text-[#35353B] cursor-pointer px-1.5 py-0.5 rounded hover:bg-[#EDD3D1]/50 disabled:opacity-50"
                      >
                        {t("waction.regenerate")}
                      </button>
                    </div>
                  )}

                  {isCurrent && (
                    <button
                      onClick={() => handleRunStep(stepName)}
                      disabled={loading}
                      className="apple-btn apple-btn-primary text-[11px] px-2.5 py-1 disabled:opacity-50"
                    >
                      {isRunning ? (
                        <span className="flex items-center gap-1">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" className="animate-spin">
                            <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.3)" strokeWidth="3" />
                            <path d="M12 2a10 10 0 0 1 10 10" stroke="white" strokeWidth="3" strokeLinecap="round" />
                          </svg>
                          {t("waction.running")}
                        </span>
                      ) : (
                        t("waction.runStep")
                      )}
                    </button>
                  )}

                  {hasError && (
                    <button
                      onClick={() => handleRunStep(stepName)}
                      disabled={loading}
                      className="apple-btn text-[11px] px-2.5 py-1 bg-[#C45B50] hover:bg-[#e03a30] text-white disabled:opacity-50"
                    >
                      {t("waction.retry")}
                    </button>
                  )}
                </div>

                {/* Step Output / Edit Panel */}
                {viewingStep === stepName && isDone && (
                  <div className="ml-7 animate-slide-up">
                    {editingStep === stepName ? (
                      <StepEditor
                        stepName={stepName}
                        output={stepData.output}
                        onSave={(newOutput) => handleSaveEdit(stepName, newOutput)}
                        onCancel={() => setEditingStep(null)}
                      />
                    ) : (
                      <StepOutput stepName={stepName} output={stepData.output} />
                    )}
                  </div>
                )}

                {hasError && state?.errors?.filter((e: string) => e.includes(stepName)).map((err: string, i: number) => (
                  <div key={i} className="ml-7 p-2 bg-[#fff5f5] rounded-lg border border-[#C45B50]/20">
                    <p className="text-[11px] text-[#C45B50]">{err}</p>
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        <div className="mt-4 pt-3 border-t border-[#EDD3D1] flex gap-2">
          {!allDone && (
            <button
              onClick={handleResume}
              disabled={loading}
              className="apple-btn apple-btn-primary flex-1 py-2 text-sm disabled:opacity-50"
            >
              {t("waction.resumeAll")}
            </button>
          )}
          {allDone && (
            <button
              onClick={() => onComplete(state)}
              className="apple-btn apple-btn-primary flex-1 py-2 text-sm"
            >
              {t("waction.viewResult")}
            </button>
          )}
          <button
            onClick={onReset}
            disabled={loading}
            className="apple-btn py-2 text-sm px-4 bg-[#FCE4E2] text-[#59585E] hover:text-[#35353B] hover:bg-[#EDD3D1] disabled:opacity-50"
          >
            {t("waction.abandon")}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Step Editor ── */

function StepEditor({ stepName, output, onSave, onCancel }: {
  stepName: string;
  output: any;
  onSave: (v: any) => void;
  onCancel: () => void;
}) {
  const { t: te } = useI18n();
  const [draft, setDraft] = useState(() => JSON.parse(JSON.stringify(output)));

  const handleSave = () => {
    onSave(draft);
  };

  if (stepName === "strategy" || stepName === "compliance") {
    const briefs = Array.isArray(draft) ? draft : draft.briefs || [];
    return (
      <div className="space-y-2 p-2">
        <p className="text-[11px] text-[#59585E] mb-1">{te("editors.briefs")}</p>
        {briefs.map((b: any, i: number) => (
          <div key={i} className="apple-card p-3 bg-white space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono text-[#9FA0A0]">#{i + 1}</span>
              <span className="text-[11px] font-semibold text-[#6A2B3A]">{b.id || `BRIEF-${String(i + 1).padStart(3, "0")}`}</span>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-[#59585E] mb-0.5">{te("editors.topic")}</label>
              <input
                type="text"
                value={b.topic || ""}
                onChange={(e) => {
                  const newBriefs = [...briefs];
                  newBriefs[i] = { ...b, topic: e.target.value };
                  setDraft({ ...draft, briefs: newBriefs });
                }}
                className="apple-input text-xs w-full"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-[#59585E] mb-0.5">{te("editors.target_audience")}</label>
              <input
                type="text"
                value={b.target_audience || ""}
                onChange={(e) => {
                  const newBriefs = [...briefs];
                  newBriefs[i] = { ...b, target_audience: e.target.value };
                  setDraft({ ...draft, briefs: newBriefs });
                }}
                className="apple-input text-xs w-full"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-[#59585E] mb-0.5">{te("editors.key_message")}</label>
              <textarea
                value={b.key_message || ""}
                onChange={(e) => {
                  const newBriefs = [...briefs];
                  newBriefs[i] = { ...b, key_message: e.target.value };
                  setDraft({ ...draft, briefs: newBriefs });
                }}
                className="apple-input text-xs w-full resize-none"
                rows={2}
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-[#59585E] mb-0.5">{te("editors.hook_type")}</label>
              <input
                type="text"
                value={b.hook_type || ""}
                onChange={(e) => {
                  const newBriefs = [...briefs];
                  newBriefs[i] = { ...b, hook_type: e.target.value };
                  setDraft({ ...draft, briefs: newBriefs });
                }}
                className="apple-input text-xs w-full"
              />
            </div>
          </div>
        ))}
        <div className="flex gap-2 pt-1">
          <button onClick={handleSave} className="apple-btn apple-btn-primary text-xs px-3 py-1.5">{te("editors.save")}</button>
          <button onClick={onCancel} className="apple-btn text-xs px-3 py-1.5 bg-[#FCE4E2] text-[#59585E]">{te("editors.cancel")}</button>
        </div>
      </div>
    );
  }

  if (stepName === "scripts") {
    const scripts = Array.isArray(draft) ? draft : draft.scripts || [];
    return (
      <div className="space-y-2 p-2">
        <p className="text-[11px] text-[#59585E] mb-1">{te("editors.scripts")}</p>
        {scripts.map((s: any, si: number) => (
          <div key={si} className="apple-card p-3 bg-white space-y-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] font-mono text-[#9FA0A0]">{s.id || `S${si + 1}`}</span>
              <span className="text-xs font-semibold text-[#35353B]">{s.product_name || s.brand_name || "Script"}</span>
            </div>
            {(s.segments || []).map((seg: any, j: number) => (
              <div key={j} className="pl-3 border-l-2 border-[#EDD3D1] space-y-1.5 py-1">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-semibold text-[#6A2B3A] uppercase">{seg.segment_type}</span>
                  <span className="text-[11px] text-[#9FA0A0] font-mono">{seg.start_time ?? 0}s — {seg.end_time ?? 0}s</span>
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-[#59585E] mb-0.5">{te("editors.voiceover")}</label>
                  <textarea
                    value={seg.voiceover || ""}
                    onChange={(e) => {
                      const newScripts = [...scripts];
                      const newSegs = [...(s.segments || [])];
                      newSegs[j] = { ...seg, voiceover: e.target.value };
                      newScripts[si] = { ...s, segments: newSegs };
                      setDraft({ ...draft, scripts: newScripts });
                    }}
                    className="apple-input text-xs w-full resize-none"
                    rows={2}
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-[#59585E] mb-0.5">{te("editors.visual_desc")}</label>
                  <textarea
                    value={seg.visual_description || ""}
                    onChange={(e) => {
                      const newScripts = [...scripts];
                      const newSegs = [...(s.segments || [])];
                      newSegs[j] = { ...seg, visual_description: e.target.value };
                      newScripts[si] = { ...s, segments: newSegs };
                      setDraft({ ...draft, scripts: newScripts });
                    }}
                    className="apple-input text-xs w-full resize-none"
                    rows={2}
                  />
                </div>
                <div className="mt-2">
                  <label className="text-[11px] font-medium text-[#59585E] mb-1 block">{te("editors.text_overlay")}</label>
                  <input
                    type="text"
                    value={seg.text_overlay || ''}
                    onChange={(e) => {
                      const newScripts = [...scripts];
                      const newSegs = [...(s.segments || [])];
                      newSegs[j] = { ...seg, text_overlay: e.target.value };
                      newScripts[si] = { ...s, segments: newSegs };
                      setDraft({ ...draft, scripts: newScripts });
                    }}
                    placeholder={te("editors.text_overlay_placeholder")}
                    className="w-full bg-[#FFF5F2] border border-[#EDD3D1] rounded-lg px-3 py-1.5 text-[13px] text-[#35353B] focus:outline-none focus:border-[#6A2B3A] transition-colors"
                  />
                </div>
              </div>
            ))}
          </div>
        ))}
        <div className="flex gap-2 pt-1">
          <button onClick={handleSave} className="apple-btn apple-btn-primary text-xs px-3 py-1.5">{te("editors.save")}</button>
          <button onClick={onCancel} className="apple-btn text-xs px-3 py-1.5 bg-[#FCE4E2] text-[#59585E]">{te("editors.cancel")}</button>
        </div>
      </div>
    );
  }

  if (stepName === "storyboards") {
    const boards = Array.isArray(draft) ? draft : draft.storyboards || [];
    return (
      <div className="space-y-2 p-2">
        <p className="text-[11px] text-[#59585E] mb-1">{te("editors.storyboards")}</p>
        {boards.map((b: any, i: number) => (
          <div key={i} className="apple-card p-3 bg-white space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono text-[#9FA0A0]">#{i + 1}</span>
              <input
                type="text"
                value={b.scene_title || ""}
                onChange={(e) => {
                  const newBoards = [...boards];
                  newBoards[i] = { ...b, scene_title: e.target.value };
                  setDraft({ ...draft, storyboards: newBoards });
                }}
                className="apple-input text-xs flex-1"
                placeholder={te("editors.scene_title_placeholder")}
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-[#59585E] mb-0.5">{te("editors.visual_desc")}</label>
              <textarea
                value={b.visual_description || ""}
                onChange={(e) => {
                  const newBoards = [...boards];
                  newBoards[i] = { ...b, visual_description: e.target.value };
                  setDraft({ ...draft, storyboards: newBoards });
                }}
                className="apple-input text-xs w-full resize-none"
                rows={3}
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-[#59585E] mb-0.5">{te("editors.shot_type")}</label>
              <input
                type="text"
                value={b.shot_type || ""}
                onChange={(e) => {
                  const newBoards = [...boards];
                  newBoards[i] = { ...b, shot_type: e.target.value };
                  setDraft({ ...draft, storyboards: newBoards });
                }}
                className="apple-input text-xs w-full"
                placeholder={te("editors.shot_type_placeholder")}
              />
            </div>
          </div>
        ))}
        <div className="flex gap-2 pt-1">
          <button onClick={handleSave} className="apple-btn apple-btn-primary text-xs px-3 py-1.5">{te("editors.save")}</button>
          <button onClick={onCancel} className="apple-btn text-xs px-3 py-1.5 bg-[#FCE4E2] text-[#59585E]">{te("editors.cancel")}</button>
        </div>
      </div>
    );
  }

  if (stepName === "video_prompts" || stepName === "thumbnail_prompts") {
    const prompts = Array.isArray(draft) ? draft : draft.prompts || [];
    return (
      <div className="space-y-2 p-2">
        <p className="text-[11px] text-[#59585E] mb-1">{te("editors.prompts")}</p>
        {prompts.map((p: any, i: number) => (
          <div key={i} className="apple-card p-3 bg-white space-y-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] font-mono text-[#9FA0A0]">#{i + 1}</span>
              {p.platform && (
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#6A2B3A]/10 text-[#6A2B3A]">
                  {te("platform." + p.platform)}
                </span>
              )}
            </div>
            <textarea
              value={typeof p === "string" ? p : p.text || p.prompt || ""}
              onChange={(e) => {
                const newPrompts = [...prompts];
                if (typeof p === "string") {
                  newPrompts[i] = e.target.value;
                } else {
                  newPrompts[i] = { ...p, text: e.target.value, prompt: e.target.value };
                }
                setDraft({ ...draft, prompts: newPrompts });
              }}
              className="apple-input text-xs w-full resize-none"
              rows={4}
            />
          </div>
        ))}
        <div className="flex gap-2 pt-1">
          <button onClick={handleSave} className="apple-btn apple-btn-primary text-xs px-3 py-1.5">{te("editors.save")}</button>
          <button onClick={onCancel} className="apple-btn text-xs px-3 py-1.5 bg-[#FCE4E2] text-[#59585E]">{te("editors.cancel")}</button>
        </div>
      </div>
    );
  }

  // Fallback: generic JSON editor for any other step
  return (
    <div className="space-y-2 p-2">
      <p className="text-[11px] text-[#59585E] mb-1">{te("editors.json")}</p>
      <textarea
        value={JSON.stringify(draft, null, 2)}
        onChange={(e) => {
          try {
            setDraft(JSON.parse(e.target.value));
          } catch { /* invalid JSON — user is still typing */ }
        }}
        className="apple-input text-xs w-full font-mono resize-none"
        rows={10}
      />
      <div className="flex gap-2 pt-1">
        <button onClick={handleSave} className="apple-btn apple-btn-primary text-xs px-3 py-1.5">{te("editors.save")}</button>
        <button onClick={onCancel} className="apple-btn text-xs px-3 py-1.5 bg-[#FCE4E2] text-[#59585E]">{te("editors.cancel")}</button>
      </div>
    </div>
  );
}

/* ── Step Output (read-only) ── */

function StepOutput({ stepName, output }: { stepName: string; output: any }) {
  const { t: to } = useI18n();
  if (!output) return <p className="text-xs text-[#9FA0A0] p-2">{to("step.noOutput")}</p>;

  if (stepName === "strategy" || stepName === "compliance") {
    const briefs = Array.isArray(output) ? output : output.briefs || [];
    if (briefs.length === 0) return <p className="text-xs text-[#9FA0A0] p-2">{to("step.noStrategy")}</p>;
    return (
      <div className="space-y-2 p-2">
        {briefs.map((b: any, i: number) => (
          <div key={i} className="apple-card p-3 bg-[#FFF5F2]">
            <div className="flex items-start gap-2 mb-1">
              {b.platform && (
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#6A2B3A]/10 text-[#6A2B3A] shrink-0">
                  {to("platform." + b.platform)}
                </span>
              )}
              {b.hook_type && (
                <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#59585E]/10 text-[#59585E]">
                  {b.hook_type}
                </span>
              )}
            </div>
            <h4 className="text-sm font-semibold text-[#35353B] mb-1">{b.topic || b.product_name || b.brand_name || "Brief"}</h4>
            {b.target_audience && <p className="text-[11px] text-[#9FA0A0] mb-1">{to("editors.target_audience")}:{b.target_audience}</p>}
            {b.key_message && <p className="text-xs text-[#59585E] leading-relaxed">{b.key_message}</p>}
            {b.description && <p className="text-xs text-[#59585E] leading-relaxed mt-1">{b.description}</p>}
          </div>
        ))}
      </div>
    );
  }

  if (stepName === "scripts") {
    const scripts = Array.isArray(output) ? output : output.scripts || [];
    if (scripts.length === 0) return <p className="text-xs text-[#9FA0A0] p-2">{to("step.noScript")}</p>;
    return (
      <div className="space-y-2 p-2">
        {scripts.map((s: any, i: number) => (
          <details key={i} className="apple-card overflow-hidden">
            <summary className="p-3 cursor-pointer flex items-center gap-2 list-none">
              <span className="text-[11px] font-mono text-[#9FA0A0]">{s.id || `S${i + 1}`}</span>
              <span className="text-sm font-medium text-[#35353B] flex-1">{s.product_name || s.brand_name || "Script"}</span>
              <span className="text-[11px] text-[#9FA0A0]">{(s.segments || []).length}{to("step.segments")}</span>
            </summary>
            <div className="px-3 pb-3 space-y-2 border-t border-[#EDD3D1] pt-2">
              {(s.segments || []).map((seg: any, j: number) => (
                <div key={j} className="pl-3 border-l-2 border-[#EDD3D1]">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[11px] font-semibold text-[#6A2B3A] uppercase">{seg.segment_type}</span>
                    <span className="text-[11px] text-[#9FA0A0] font-mono">
                      {seg.start_time ?? 0}s — {seg.end_time ?? 0}s
                    </span>
                  </div>
                  <p className="text-xs text-[#35353B]">{seg.voiceover}</p>
                  {seg.visual_description && <p className="text-[11px] text-[#59585E] mt-1 italic">{seg.visual_description}</p>}
                  {seg.text_overlay && (
                    <p className="text-[11px] text-[#6A2B3A] font-medium mt-1 bg-[#f0f7e8] px-2 py-0.5 rounded-md inline-block">
                      {seg.text_overlay}
                    </p>
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
    if (boards.length === 0) return <p className="text-xs text-[#9FA0A0] p-2">{to("step.noStoryboard")}</p>;
    return (
      <div className="space-y-2 p-2">
        {boards.map((b: any, i: number) => (
          <div key={i} className="apple-card p-3 bg-[#FFF5F2]">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] font-mono text-[#9FA0A0]">#{i + 1}</span>
              <span className="text-xs font-semibold text-[#35353B]">{b.scene_title || "Scene"}</span>
            </div>
            {b.visual_description && <p className="text-[11px] text-[#59585E] italic">{b.visual_description}</p>}
            {b.shot_type && <p className="text-[11px] text-[#9FA0A0] mt-1">{to("editors.shot_type")}:{b.shot_type}</p>}
          </div>
        ))}
      </div>
    );
  }

  if (stepName === "seedance_clips") {
    // New format: {clip_paths, clip_details, total_duration, target_duration}
    // Old format: string[]
    const isNewFormat = output && !Array.isArray(output) && output.clip_paths;
    const rawUrls = isNewFormat ? output.clip_paths : (Array.isArray(output) ? output : output.urls || []);
    const details = isNewFormat ? (output.clip_details || []) : [];
    const totalDur = isNewFormat ? (output.total_duration || 0) : 0;
    const targetDur = isNewFormat ? (output.target_duration || 0) : 0;
    const urls = rawUrls.map((url: string) => getMediaUrl(url));
    if (urls.length === 0) return <p className="text-xs text-[#9FA0A0] p-2">{to("step.noMedia")}</p>;
    return (
      <div className="space-y-2 p-2">
        {isNewFormat && targetDur > 0 && (
          <div className="flex items-center gap-2 text-[11px]">
            <span className="text-[#59585E]">
              {to("step.totalDuration")}: {totalDur.toFixed(1)}s / {targetDur}s
            </span>
            <span className={`px-1.5 py-0.5 rounded-full font-medium ${totalDur >= targetDur * 0.8 ? "bg-[#6A2B3A]/10 text-[#6A2B3A]" : "bg-[#ff9500]/10 text-[#ff9500]"}`}>
              {totalDur >= targetDur * 0.8 ? to("step.durationOk") : to("step.durationShort")}
            </span>
          </div>
        )}
        <div className="grid grid-cols-2 gap-2">
          {urls.map((url: string, i: number) => {
            const meta = details[i] || {};
            const isStub = meta.is_stub;
            const isFiller = meta.is_filler;
            const hasContinuity = meta.continuity_frame;
            const ver = meta.verification || {};
            const verOk = ver.all_ok !== false;
            return (
              <div key={i} className={`apple-card overflow-hidden ${isStub ? "border-[#ff9500]/30" : ""} ${isFiller ? "border-[#7A96BB]/30" : ""}`}>
                <video src={url} controls className="w-full h-32 object-cover" />
                <div className="p-2 space-y-1">
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className="text-[9px] font-mono text-[#9FA0A0]">#{i + 1}</span>
                    {meta.duration > 0 && (
                      <span className="text-[9px] text-[#59585E]">{meta.duration.toFixed(1)}s</span>
                    )}
                    {isStub && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-[#ff9500]/10 text-[#ff9500] font-medium">
                        {to("step.stub")}
                      </span>
                    )}
                    {isFiller && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-[#7A96BB]/10 text-[#7A96BB] font-medium">
                        {to("step.filler")}
                      </span>
                    )}
                    {hasContinuity && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-[#6A2B3A]/10 text-[#6A2B3A] font-medium">
                        {to("step.continuity")}
                      </span>
                    )}
                    {!verOk && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-[#C45B50]/10 text-[#C45B50] font-medium">
                        {to("step.verifyFail")}
                      </span>
                    )}
                  </div>
                  <p className="text-[9px] text-[#9FA0A0] truncate">{url}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  if (stepName === "thumbnail_images") {
    const rawUrls = Array.isArray(output) ? output : output.urls || [];
    const urls = rawUrls.map((url: string) => getMediaUrl(url));
    if (urls.length === 0) return <p className="text-xs text-[#9FA0A0] p-2">{to("step.noMedia")}</p>;
    return (
      <div className="grid grid-cols-2 gap-2 p-2">
        {urls.map((url: string, i: number) => (
          <div key={i} className="apple-card overflow-hidden">
            <img src={url} alt={`Asset ${i + 1}`} className="w-full h-32 object-cover" />
            <p className="text-[9px] text-[#9FA0A0] p-2 truncate">{url}</p>
          </div>
        ))}
      </div>
    );
  }

  if (stepName === "tts_audio") {
    // Format: {"audio_paths": [...], "lyrics_paths": [...]}
    const rawUrls = Array.isArray(output)
      ? output
      : (output.audio_paths || output.urls || []);
    const urls = rawUrls.map((url: string) => getMediaUrl(url));
    if (urls.length === 0) return <p className="text-xs text-[#9FA0A0] p-2">{to("step.noMedia")}</p>;
    return (
      <div className="space-y-2 p-2">
        {urls.map((url: string, i: number) => (
          <div key={i} className="apple-card p-3 bg-[#FFF5F2]">
            <audio src={url} controls className="w-full" />
          </div>
        ))}
      </div>
    );
  }

  if (stepName === "assemble_final") {
    const rawUrl = typeof output === "string" ? output : output.final_video_url;
    const finalUrl = getMediaUrl(rawUrl);
    if (!finalUrl) return <p className="text-xs text-[#9FA0A0] p-2">{to("step.noData")}</p>;
    return (
      <div className="p-2">
        <div className="apple-card overflow-hidden">
          <video src={finalUrl} controls className="w-full" />
          <div className="p-2">
            <a href={finalUrl} target="_blank" rel="noopener noreferrer" className="text-[11px] text-[#6A2B3A] hover:underline">
              {to("result.downloadVideo")}
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <pre className="text-[11px] font-mono text-[#59585E] bg-[#FFF5F2] p-3 rounded-lg overflow-auto max-h-[300px] whitespace-pre-wrap break-all">
      {JSON.stringify(output, null, 2)}
    </pre>
  );
}
