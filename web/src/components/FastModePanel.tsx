"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Lightning, Clock, SpeakerHigh, CaretDown, CaretUp, Copy, ArrowCounterClockwise, Play, Article, Cpu, Timer, HardDrives } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import { getSubmissionByIdempotencyKey, submitFastMode, pollFastStatus, isDemoMode, isApiError, resolveMediaPreview, type FastModeResult, type FastStatusResponse } from "./api";
import { DEMO_FAST_MODE_RESULT } from "@/demo-data";
import { useSubmitting } from "@/hooks/useSubmitting";
import RuntimeMediaVideo from "./RuntimeMediaVideo";
import TransparencyStatus from "./TransparencyStatus";
import { withExplicitMediaGenerationIntent } from "@/lib/scenarioPayload";
import { classifyGenerationResult } from "@/lib/generationLifecycle";
import {
  createPendingSubmission,
  recoverPendingSubmission,
  submitIdempotently,
  type PendingSubmission,
  type SubmissionResolution,
} from "@/lib/idempotentSubmission";
import { usePipelineStore } from "@/stores/usePipelineStore";

type FastRecoveryUiState =
  | "idle"
  | "confirming"
  | "unknown"
  | "conflict"
  | "recovery_required";

export default function FastModePanel() {
  const { t } = useI18n();
  const [userPrompt, setUserPrompt] = useState("");
  const [duration, setDuration] = useState<10 | 15>(15);
  const [enableTTS, setEnableTTS] = useState(false);
  const { submitting: loading, wrap } = useSubmitting();
  const [result, setResult] = useState<FastModeResult | null>(null);
  const [error, setError] = useState("");
  const [showDebug, setShowDebug] = useState(false);
  const [copied, setCopied] = useState(false);
  const [progressStage, setProgressStage] = useState<FastStatusResponse["stage"] | null>(null);
  const [progressSec, setProgressSec] = useState(0);
  const [recoveryUi, setRecoveryUi] = useState<FastRecoveryUiState>("idle");
  const [recovering, setRecovering] = useState(false);
  const [showAbandonConfirm, setShowAbandonConfirm] = useState(false);
  const pendingSubmission = usePipelineStore((state) => state.pendingSubmission);
  const setPendingSubmission = usePipelineStore((state) => state.setPendingSubmission);
  const clearPendingSubmission = usePipelineStore((state) => state.clearPendingSubmission);
  const liveSubmissionKeyRef = useRef<string | null>(null);
  const recoveringSubmissionKeyRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const videoPreview = result?.video_url
    ? resolveMediaPreview(result.video_url)
    : { kind: "invalid" as const, url: "" as const };
  const lifecycleState = result ? classifyGenerationResult(result) : null;

  const pollOriginalFastJob = useCallback(async (
    resourceId: string,
    signal?: AbortSignal,
  ) => {
    setProgressStage("queued");
    try {
      const nextResult = await pollFastStatus(resourceId, {
        ...(signal ? { signal } : {}),
        intervalMs: 2000,
        maxWaitMs: 600_000,
        onProgress: (snapshot) => {
          setProgressStage(snapshot.stage);
          setProgressSec(snapshot.elapsed_sec);
        },
      });
      setResult(nextResult);
      setRecoveryUi("idle");
      clearPendingSubmission();
    } catch (pollError) {
      const name = pollError && typeof pollError === "object"
        ? String((pollError as { name?: unknown }).name || "")
        : "";
      const message = pollError instanceof Error ? pollError.message : String(pollError);
      if (name === "AbortError") {
        setRecoveryUi("unknown");
        setError(t("submission.waitingStopped"));
      } else if (message === "recovery_required") {
        setRecoveryUi("recovery_required");
        setError(t("submission.recoveryRequiredBody"));
      } else if (name === "FastTerminalError") {
        setRecoveryUi("idle");
        setError(message || t("fastMode.result.generationFailed"));
        clearPendingSubmission();
      } else {
        setRecoveryUi("unknown");
        setError(t("submission.pollingUnknown"));
      }
    } finally {
      setProgressStage(null);
    }
  }, [clearPendingSubmission, t]);

  const handleResolution = useCallback(async (
    resolution: SubmissionResolution,
    signal?: AbortSignal,
  ) => {
    if (resolution.kind === "unknown") {
      setRecoveryUi("unknown");
      setError(t("submission.unknownBody"));
      return;
    }
    if (resolution.kind === "recovery_required") {
      setRecoveryUi("recovery_required");
      setError(t("submission.recoveryRequiredBody"));
      return;
    }
    setRecoveryUi("idle");
    await pollOriginalFastJob(resolution.resourceId, signal);
  }, [pollOriginalFastJob, t]);

  const continueFastRecovery = useCallback(async (
    pending?: PendingSubmission | null,
  ) => {
    const candidate = pending ?? usePipelineStore.getState().pendingSubmission;
    if (!candidate || candidate.kind !== "fast") return;
    if (recoveringSubmissionKeyRef.current === candidate.idempotencyKey) return;
    recoveringSubmissionKeyRef.current = candidate.idempotencyKey;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    const recoverySignal = abortRef.current.signal;
    setRecovering(true);
    setRecoveryUi("confirming");
    setError("");
    try {
      const resolution = await recoverPendingSubmission({
        pending: candidate,
        persist: setPendingSubmission,
        readback: (idempotencyKey) => getSubmissionByIdempotencyKey(
          idempotencyKey,
          { signal: recoverySignal },
        ),
        signal: recoverySignal,
      });
      await handleResolution(resolution, recoverySignal);
    } finally {
      recoveringSubmissionKeyRef.current = null;
      setRecovering(false);
    }
  }, [handleResolution, setPendingSubmission]);

  useEffect(() => {
    if (!pendingSubmission || pendingSubmission.kind !== "fast") return;
    if (liveSubmissionKeyRef.current === pendingSubmission.idempotencyKey) return;
    void continueFastRecovery(pendingSubmission);
  }, [continueFastRecovery, pendingSubmission]);

  function handleGenerate() {
    if (!userPrompt.trim()) return;
    if (usePipelineStore.getState().pendingSubmission) {
      setRecoveryUi("unknown");
      setError(t("submission.unknownBody"));
      return;
    }
    void wrap(async () => {
      setError("");
      setResult(null);
      setProgressStage(null);
      setProgressSec(0);
      setRecoveryUi("idle");
      if (isDemoMode()) {
        await new Promise((r) => setTimeout(r, 800));
        setResult({
          ...(DEMO_FAST_MODE_RESULT as FastModeResult),
          user_prompt: userPrompt.trim(),
          duration_seconds: duration,
          timing: {
            ...DEMO_FAST_MODE_RESULT.timing,
            tts_ms: enableTTS ? 240 : 0,
          },
          model_info: {
            ...DEMO_FAST_MODE_RESULT.model_info,
            tts: enableTTS ? "doubao-tts" : "",
          },
        });
        return;
      }
      const pending = createPendingSubmission({ kind: "fast" });
      liveSubmissionKeyRef.current = pending.idempotencyKey;
      abortRef.current?.abort();
      abortRef.current = new AbortController();
      try {
        setRecoveryUi("confirming");
        const resolution = await submitIdempotently({
          pending,
          persist: setPendingSubmission,
          submit: (idempotencyKey) => submitFastMode(
            withExplicitMediaGenerationIntent({
              user_prompt: userPrompt.trim(),
              duration,
              enable_tts: enableTTS,
            }),
            {
              idempotencyKey,
              signal: abortRef.current?.signal,
            },
          ),
          readback: getSubmissionByIdempotencyKey,
        });
        await handleResolution(resolution, abortRef.current?.signal);
      } catch (e: unknown) {
        if (isApiError(e)) {
          const tail = e.info.retryAfterSec != null ? ` (retry in ${e.info.retryAfterSec}s)` : "";
          setError(e.info.message + tail);
          setRecoveryUi(e.info.status === 409 ? "conflict" : "unknown");
        } else {
          const msg = e instanceof Error ? e.message : String(e);
          setError(msg || "Generation failed");
          setRecoveryUi("unknown");
        }
      } finally {
        liveSubmissionKeyRef.current = null;
        setProgressStage(null);
      }
    });
  }

  function handleStopWaiting() {
    abortRef.current?.abort(new DOMException("Stopped waiting", "AbortError"));
    setRecoveryUi("unknown");
    setError(t("submission.waitingStopped"));
  }

  function confirmAbandon() {
    abortRef.current?.abort(new DOMException("Submission abandoned", "AbortError"));
    clearPendingSubmission();
    setRecoveryUi("idle");
    setError("");
    setProgressStage(null);
    setShowAbandonConfirm(false);
  }

  function handleCopyPrompt() {
    if (!result?.llm_prompt) return;
    navigator.clipboard.writeText(result.llm_prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatTime(ms: number): string {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  return (
    <div className="space-y-4 animate-slide-up">
      {/* Header */}
      <div className="apple-card p-4">
        <div className="flex items-center gap-2 mb-2">
          <Lightning size={20} weight="fill" className="text-[var(--gold-foil)]" />
          <h2 className="text-base font-semibold text-[var(--text-h1)]">{t("fastMode.title")}</h2>
        </div>
        <p className="text-xs text-[var(--text-body)]">{t("fastMode.subtitle")}</p>
      </div>

      {/* Input Panel */}
      <div className="apple-card p-4 space-y-4">
        {/* Text input */}
        <div>
          <label
            htmlFor="fast-prompt"
            className="block text-[12px] font-semibold text-[var(--text-body)] uppercase tracking-wider mb-1.5"
          >
            {t("fastMode.title")}
          </label>
          <textarea
            id="fast-prompt"
            name="prompt"
            value={userPrompt}
            onChange={(e) => setUserPrompt(e.target.value)}
            placeholder={t("fastMode.inputPlaceholder")}
            rows={4}
            aria-required="true"
            aria-describedby="fast-prompt-hint"
            className="w-full px-3 py-2 text-sm bg-[var(--bg-panel)] border border-[var(--border-default)] rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-[var(--gold-foil)]/30 focus:border-[var(--gold-foil)] transition-all"
          />
          <p id="fast-prompt-hint" className="text-[12px] text-[var(--text-muted)] mt-1">
            {t("fastMode.inputHint")}
          </p>
        </div>

        {/* Duration selector */}
        <div>
          <span
            id="fast-duration-label"
            className="block text-[12px] font-semibold text-[var(--text-body)] uppercase tracking-wider mb-1.5"
          >
            <Clock size={12} weight="fill" className="inline mr-1" />
            {t("fastMode.duration")}
          </span>
          <div
            role="radiogroup"
            aria-labelledby="fast-duration-label"
            className="flex gap-2"
          >
            {[10, 15].map((d) => (
              <button
                key={d}
                type="button"
                role="radio"
                aria-checked={duration === d}
                onClick={() => setDuration(d as 10 | 15)}
                className={`text-xs px-4 py-1.5 rounded-full font-medium transition-all cursor-pointer ${
                  duration === d
                    ? "bg-[var(--gold-foil)] text-white"
                    : "bg-[var(--bg-panel)] text-[var(--text-body)] hover:bg-[var(--border-default)]"
                }`}
              >
                {d === 10 ? t("fastMode.duration10s") : t("fastMode.duration15s")}
              </button>
            ))}
          </div>
        </div>

        {/* TTS toggle */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            role="switch"
            aria-checked={enableTTS}
            aria-label={t("fastMode.enableTTS")}
            onClick={() => setEnableTTS(!enableTTS)}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full transition-all cursor-pointer ${
              enableTTS
                ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] ring-1 ring-[rgba(215,92,112,0.18)]"
                : "bg-[var(--bg-panel)] text-[var(--text-body)] hover:bg-[var(--border-default)]"
            }`}
          >
            <SpeakerHigh size={12} weight="fill" />
            {t("fastMode.enableTTS")}
          </button>
        </div>

        {/* Generate button */}
        <button
          onClick={handleGenerate}
          disabled={loading || recovering || Boolean(pendingSubmission) || !userPrompt.trim()}
          className="w-full apple-btn apple-btn-primary text-sm py-2.5 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          style={{ backgroundColor: "var(--gold-foil)" }}
        >
          {loading || recovering ? (
            <span className="flex items-center justify-center gap-2">
              <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              {t("fastMode.generating")}
            </span>
          ) : (
            <span className="flex items-center justify-center gap-2">
              <Lightning size={16} weight="fill" />
              {t("fastMode.generate")}
            </span>
          )}
        </button>

        {(loading || recovering) && progressStage && (
          <div className="text-xs text-[var(--text-body)] bg-[rgba(215,168,52,0.05)] px-3 py-2 rounded-lg">
            <div className="flex items-center justify-between">
              <span>
                {progressStage === "queued" && t("fastMode.progress.queued")}
                {progressStage === "reserved" && t("submission.confirmingTitle")}
                {progressStage === "initializing" && t("submission.confirmingTitle")}
                {progressStage === "llm" && t("fastMode.progress.enhancingPrompt")}
                {progressStage === "video" && t("fastMode.progress.generatingVideo")}
                {progressStage === "tts" && t("fastMode.progress.synthesizingVoiceover")}
              </span>
              <span className="font-mono text-[var(--text-muted)]">{progressSec.toFixed(1)}s</span>
            </div>
            <button
              type="button"
              onClick={handleStopWaiting}
              className="mt-2 text-[12px] text-[var(--text-muted)] underline"
            >
              {t("submission.stopWaiting")}
            </button>
          </div>
        )}

        {recovering && !progressStage && (
          <div className="text-xs text-[var(--text-body)] bg-[rgba(215,168,52,0.05)] px-3 py-3 rounded-lg" role="status" aria-live="polite">
            <p className="font-medium">{t("submission.confirmingTitle")}</p>
            <p className="mt-1 text-[var(--text-muted)]">{t("submission.confirmingBody")}</p>
          </div>
        )}

        {pendingSubmission?.kind === "fast" && recoveryUi !== "idle" && !loading && !recovering && (
          <div className="text-xs text-[var(--text-body)] bg-[rgba(215,168,52,0.05)] px-3 py-3 rounded-lg" role="status" aria-live="polite">
            <p className="font-medium">
              {recoveryUi === "recovery_required"
                ? t("submission.recoveryRequiredTitle")
                : recoveryUi === "conflict"
                  ? t("submission.conflictTitle")
                  : t("submission.unknownTitle")}
            </p>
            <p className="mt-1 text-[var(--text-muted)]">
              {recoveryUi === "recovery_required"
                ? t("submission.recoveryRequiredBody")
                : recoveryUi === "conflict"
                  ? t("submission.conflictBody")
                  : t("submission.unknownBody")}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {recoveryUi !== "conflict" && (
                <button
                  type="button"
                  onClick={() => void continueFastRecovery(pendingSubmission)}
                  className="apple-btn apple-btn-primary px-3 py-1.5 text-[12px]"
                >
                  {t("submission.continueChecking")}
                </button>
              )}
              <button
                type="button"
                onClick={() => setShowAbandonConfirm(true)}
                className="px-3 py-1.5 rounded-lg border border-[var(--border-default)] text-[12px]"
              >
                {t("submission.abandon")}
              </button>
            </div>
          </div>
        )}

        {showAbandonConfirm && pendingSubmission?.kind === "fast" && (
          <div role="alertdialog" aria-modal="true" className="rounded-lg border border-[var(--crimson-mist)]/30 p-3 text-xs">
            <p>{t("submission.abandonConfirm")}</p>
            <div className="mt-2 flex gap-2">
              <button type="button" onClick={() => setShowAbandonConfirm(false)} className="px-3 py-1.5 rounded-lg border border-[var(--border-default)]">
                {t("confirm.cancel")}
              </button>
              <button type="button" onClick={confirmAbandon} className="px-3 py-1.5 rounded-lg bg-[var(--crimson-mist)] text-white">
                {t("submission.abandon")}
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="text-xs text-[var(--crimson-mist)] bg-[rgba(196,91,80,0.05)] px-3 py-2 rounded-lg">
            {error}
          </div>
        )}
      </div>

      {/* Result Panel */}
      {result && (
        <div className="apple-card p-4 space-y-4 animate-slide-up">
          <div className="flex items-center gap-2 mb-2">
            <Play size={18} weight="fill" className="text-[var(--fortune-red)]" />
            <h3 className="text-sm font-semibold text-[var(--text-h1)]">{t("fastMode.result.title")}</h3>
            {result.is_stub && (
              <span className="text-[12px] px-2 py-0.5 rounded-full bg-[rgba(215,168,52,0.10)] text-[var(--gold-foil)]">
                STUB
              </span>
            )}
          </div>

          <TransparencyStatus
            resourceType={result.resource_type}
            resourceId={result.resource_id}
          />

          {/* Error, bounded completion, or full media */}
          {lifecycleState === "error" ? (
            <div className="rounded-xl bg-[rgba(196,91,80,0.05)] border border-[rgba(196,91,80,0.20)] p-4">
              <p className="text-xs text-[var(--crimson-mist)] font-medium">{t("fastMode.result.generationFailed")}</p>
              <p className="text-[12px] text-[var(--crimson-mist)]/70 mt-1">{result.error || t("fastMode.result.unknownError")}</p>
            </div>
          ) : (
            <>
              {lifecycleState === "bounded" && (
                <div
                  role="status"
                  data-lifecycle-state="bounded"
                  className="rounded-xl bg-[rgba(215,168,52,0.06)] border border-[rgba(215,168,52,0.24)] p-4"
                >
                  <p className="text-xs text-[var(--gold-foil)] font-medium">
                    {t("result.bounded")}
                  </p>
                  <p className="text-[12px] text-[var(--text-body)] mt-1">
                    {t("result.boundedNotice")}
                  </p>
                </div>
              )}
              {videoPreview.kind !== "invalid" && (
                <div className="rounded-xl overflow-hidden bg-black">
                  {videoPreview.kind === "runtime" ? (
                    <RuntimeMediaVideo
                      src={videoPreview.url}
                      controls
                      className="w-full max-h-[400px]"
                    />
                  ) : (
                    <video
                      src={videoPreview.url}
                      controls
                      className="w-full max-h-[400px]"
                      poster=""
                    />
                  )}
                </div>
              )}
            </>
          )}

          {/* Video info */}
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-[var(--bg-panel)] rounded-lg p-2 text-center">
              <Timer size={14} weight="fill" className="mx-auto mb-1 text-[var(--text-body)]" />
              <p className="text-[12px] text-[var(--text-body)]">{t("fastMode.result.generationTime")}</p>
              <p className="text-xs font-semibold text-[var(--text-h1)]">{formatTime(result.generation_time_ms)}</p>
            </div>
            <div className="bg-[var(--bg-panel)] rounded-lg p-2 text-center">
              <HardDrives size={14} weight="fill" className="mx-auto mb-1 text-[var(--text-body)]" />
              <p className="text-[12px] text-[var(--text-body)]">{t("fastMode.result.videoInfo")}</p>
              <p className="text-xs font-semibold text-[var(--text-h1)]">{formatBytes(result.file_size_bytes)}</p>
            </div>
            <div className="bg-[var(--bg-panel)] rounded-lg p-2 text-center">
              <Cpu size={14} weight="fill" className="mx-auto mb-1 text-[var(--text-body)]" />
              <p className="text-[12px] text-[var(--text-body)]">{t("fastMode.result.modelInfo")}</p>
              <p className="text-xs font-semibold text-[var(--text-h1)]">{result.model_info.video}</p>
            </div>
          </div>

          {/* Timing breakdown */}
          <div className="text-[12px] text-[var(--text-body)] flex gap-3">
            <span>LLM: {formatTime(result.timing.llm_ms)}</span>
            <span>Video: {formatTime(result.timing.video_ms)}</span>
            {result.timing.tts_ms > 0 && <span>TTS: {formatTime(result.timing.tts_ms)}</span>}
          </div>

          {/* Debug Info (collapsible) */}
          <div className="border border-[var(--border-default)] rounded-xl overflow-hidden">
            <button
              onClick={() => setShowDebug(!showDebug)}
              className="w-full flex items-center justify-between px-3 py-2 text-xs text-[var(--text-body)] hover:bg-[var(--bg-panel)] transition-colors cursor-pointer"
            >
              <span className="flex items-center gap-1.5">
                <Article size={12} weight="fill" />
                {t("fastMode.result.debugInfo")}
              </span>
              {showDebug ? <CaretUp size={14} weight="fill" /> : <CaretDown size={14} weight="fill" />}
            </button>
            {showDebug && (
              <div className="px-3 pb-3 space-y-3">
                {/* LLM Prompt */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[12px] font-medium text-[var(--text-body)]">{t("fastMode.result.llmPrompt")}</span>
                    <button
                      onClick={handleCopyPrompt}
                      className="text-[12px] flex items-center gap-1 text-[var(--gold-foil)] hover:underline cursor-pointer"
                    >
                      <Copy size={10} />
                      {copied ? "Copied!" : t("fastMode.result.copyPrompt")}
                    </button>
                  </div>
                  <div className="bg-[var(--bg-panel)] rounded-lg p-2.5 text-[12px] text-[var(--text-h1)] leading-relaxed max-h-40 overflow-y-auto">
                    {result.llm_prompt}
                  </div>
                </div>

                {/* User Prompt */}
                <div>
                  <span className="text-[12px] font-medium text-[var(--text-body)] block mb-1">Original Input</span>
                  <div className="bg-[var(--bg-panel)] rounded-lg p-2.5 text-[12px] text-[var(--text-body)] leading-relaxed">
                    {result.user_prompt}
                  </div>
                </div>

                {/* Models */}
                <div className="grid grid-cols-2 gap-2 text-[12px]">
                  <div className="bg-[var(--bg-panel)] rounded-lg p-2">
                    <span className="text-[var(--text-body)]">LLM: </span>
                    <span className="font-medium text-[var(--text-h1)]">{result.model_info.llm}</span>
                  </div>
                  <div className="bg-[var(--bg-panel)] rounded-lg p-2">
                    <span className="text-[var(--text-body)]">Video: </span>
                    <span className="font-medium text-[var(--text-h1)]">{result.model_info.video}</span>
                  </div>
                  {result.model_info.tts && (
                    <div className="bg-[var(--bg-panel)] rounded-lg p-2">
                      <span className="text-[var(--text-body)]">TTS: </span>
                      <span className="font-medium text-[var(--text-h1)]">{result.model_info.tts}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Regenerate */}
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 text-xs text-[var(--gold-foil)] hover:bg-[rgba(215,168,52,0.05)] py-2 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
          >
            <ArrowCounterClockwise size={14} weight="fill" />
            {t("fastMode.result.regenerate")}
          </button>
        </div>
      )}
    </div>
  );
}
