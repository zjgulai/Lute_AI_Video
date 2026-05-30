"use client";

import { useEffect, useCallback, useRef, useMemo, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense } from "react";
import { ShieldCheck } from "@phosphor-icons/react";
import type { AuditReport, ReviewState } from "@/components/types";
import { REVIEW_NODES } from "@/components/types";
import { errorMessage } from "@/lib/errors";
import { handleSmartCreateStageError } from "@/lib/smartCreateError";
import { withScenarioContinuityConfig } from "@/lib/scenarioContinuity";
import { sceneToPath, sceneToScenarioId } from "@/lib/scenarioRouting";
import {
  fetchState,
  submitReview,
  runS1ProductDirect,
  runS5BrandVlog,
  startS1StepByStep,
  fetchS1State,
  getMediaUrl,
  isDemoMode,
  submitScenario,
  hasApiKey,
  isApiError,
} from "@/components/api";
import SceneTabs from "@/components/SceneTabs";
import SceneForm from "@/components/SceneForm";
import PipelineMonitor from "@/components/PipelineMonitor";
import PipelineStatusBar from "@/components/PipelineStatusBar";
import ReviewPanel from "@/components/ReviewPanel";
import DistributionView from "@/components/DistributionView";
import OneShotResultView from "@/components/OneShotResultView";
import { ConfirmModal } from "@/components/ConfirmModal";
import CompareView, { Version } from "@/components/CompareView";
import StepByStepView from "@/components/StepByStepView";
import VideoWorkflow from "@/components/VideoWorkflow";
import GatePanel from "@/components/GatePanel";
import StageProgress from "@/components/StageProgress";
import SplashScreen from "@/components/SplashScreen";
import ApiKeyGate from "@/components/ApiKeyGate";
import RecommendPanel from "@/components/RecommendPanel";
import FastModePanel from "@/components/FastModePanel";
import Nav from "@/components/Nav";
import SettingsPanel from "@/components/SettingsPanel";
import ExecutionBar from "@/components/ExecutionBar";
import ErrorBoundary from "@/components/ErrorBoundary";
import { useI18n } from "@/i18n/I18nProvider";
import { DEMO_RESULT_1, DEMO_RESULT_2, DEMO_RESULT_VLOG } from "@/demo-data";
import { useAppStore } from "@/stores/useAppStore";
import { usePipelineStore } from "@/stores/usePipelineStore";
import { useExpertStore } from "@/stores/useExpertStore";
import { useExecutionBar } from "@/hooks/useExecutionBar";
import { useSubmitting } from "@/hooks/useSubmitting";

const STORAGE_KEY = "ai_video_thread_id";

type UnknownRecord = Record<string, unknown>;

type PipelineStepLike = {
  output?: unknown;
};

type PipelineStateLike = {
  steps?: Record<string, PipelineStepLike>;
};

type SceneConfig = UnknownRecord & {
  mode?: string;
  content_scenario?: string;
  product_catalog?: UnknownRecord & {
    name?: string;
    products?: Array<UnknownRecord & { name?: string; usps?: unknown }>;
    usps?: unknown;
  };
  brand_guidelines?: UnknownRecord & { brand_name?: string };
  target_platforms?: string[];
  target_languages?: string[];
  content_calendar_week?: string;
  video_duration?: number;
  brand_id?: string;
  product_sku?: unknown;
  scene_id?: string;
  selected_models?: unknown[];
  story_description?: string;
  enable_media_synthesis?: boolean;
  continuity_mode?: boolean | string;
  continuity_generation_mode?: string;
  storyboard_grid?: number | string;
  clip_group_size?: number;
  transition_style?: string;
};

type GalleryResult = {
  briefs?: UnknownRecord[];
  scripts?: UnknownRecord[];
  thumbnail_image_paths?: string[];
  final_video_path?: string;
  video_duration?: number;
  audit_report?: { overall_score?: number };
};

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}

function asAuditReport(value: unknown): AuditReport | null {
  const record = asRecord(value);
  if (typeof record.overall_score === "number" && typeof record.overall_status === "string") {
    return value as AuditReport;
  }
  return null;
}

function supportsStepByStep(contentScenario: string): boolean {
  return contentScenario === "product_direct";
}

function extractVersions(state: PipelineStateLike): Version[] {
  const versions: Version[] = [];
  const steps = state?.steps || {};
  const assembleOutput = steps.assemble_final?.output;
  const auditOutput = steps.audit?.output;
  const auditRecord = asRecord(auditOutput);
  const scripts = Array.isArray(steps.scripts?.output) ? steps.scripts.output : [];

  // Extract video path from assemble_final output (string, or object with video_path, or array)
  const assembleRecord = asRecord(assembleOutput);
  const videoPath =
    typeof assembleOutput === "string"
      ? assembleOutput
      : String(assembleRecord.video_path || (Array.isArray(assembleOutput) ? assembleOutput[0] : ""));

  const firstScript = asRecord(scripts[0]);

  versions.push({
    label: "Version A",
    scriptVariant: String(firstScript.variant || "standard"),
    videoPath,
    thumbnailPath: Array.isArray(steps.thumbnail_images?.output) ? String(steps.thumbnail_images.output[0] || "") : "",
    auditReport: asAuditReport(auditOutput),
    duration: typeof auditRecord.duration_seconds === "number" ? auditRecord.duration_seconds : 0,
    fileSize: 0,
  });

  // If the user selected 2 scripts in Gate 1, the pipeline may produce 2 assembled videos
  // Try to find a second video if multiple scripts were used
  if (scripts.length >= 2) {
    const secondVideoPath = Array.isArray(assembleOutput)
      ? assembleOutput[1] || ""
      : assembleRecord.video_path_2
        ? assembleRecord.video_path_2
        : "";

    if (secondVideoPath) {
      const secondScript = asRecord(scripts[1]);
      versions.push({
        label: "Version B",
        scriptVariant: String(secondScript.variant || "creative"),
        videoPath: String(secondVideoPath),
        thumbnailPath: Array.isArray(steps.thumbnail_images?.output)
          ? String(steps.thumbnail_images.output[1] || steps.thumbnail_images.output[0] || "")
          : "",
        auditReport: asAuditReport(auditOutput),
        duration: typeof auditRecord.duration_seconds === "number" ? auditRecord.duration_seconds : 0,
        fileSize: 0,
      });
    }
  }

  return versions;
}

// ── P2: Review progress indicator — extracted to avoid re-computation on every parent render ──
interface ReviewProgressProps {
  currentReview: string | null | undefined;
  reviewState: ReviewState | null;
}

function ReviewProgressIndicator({ currentReview, reviewState }: ReviewProgressProps) {
  const { t } = useI18n();

  const nodes = useMemo(() => {
    return REVIEW_NODES.map((node, i) => {
      const nodeKey = node.replace("_review", "");
      const isCurrent = currentReview === node;
      const reviewData = reviewState?.state?.human_reviews?.[node];
      const isDone = reviewData?.status === "approved";
      const isRejected = reviewData?.status === "rejected";
      return {
        node,
        nodeKey,
        isCurrent,
        isDone,
        isRejected,
        index: i,
      };
    });
  }, [currentReview, reviewState]);

  return (
    <div className="flex items-center gap-1.5 mb-3 px-1">
      {nodes.map(({ node, nodeKey, isCurrent, isDone, isRejected, index }) => (
        <div key={node} className="flex items-center gap-1.5 flex-1 last:flex-none">
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-[12px] font-medium transition-all ${
            isCurrent ? "bg-[rgba(215,92,112,0.12)] text-[var(--fortune-red)] ring-1 ring-[rgba(215,92,112,0.35)] shadow-[0_0_6px_rgba(215,92,112,0.15)]" :
            isDone ? "bg-[rgba(120,175,140,0.12)] text-[var(--jade-accent)]" :
            isRejected ? "bg-[rgba(208,78,90,0.10)] text-[var(--cinnabar)]" :
            "bg-[var(--bg-panel)] text-[var(--text-muted)]"
          }`}>
            <span className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[8px] font-bold ${
              isDone ? "bg-[var(--jade-accent)] text-white" :
              isRejected ? "bg-[var(--crimson-mist)] text-white" :
              isCurrent ? "bg-[var(--fortune-red-600)] text-white shadow-[0_0_6px_rgba(215,92,112,0.20)]" :
              "bg-[var(--bg-layer3)] text-[var(--text-muted)]"
            }`}>{isDone ? "✓" : isRejected ? "✗" : index + 1}</span>
            {t(`step.${nodeKey}`)}
          </div>
          {index < REVIEW_NODES.length - 1 && (
            <div className={`flex-1 h-px ${isDone ? "bg-[var(--jade-accent)]" : "bg-[var(--divider-subtle)]"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

export default function Home() {
  // Zustand stores (P1-13 — migrated incrementally)
  const {
    showSplash, setShowSplash,
    showSettings, setShowSettings,
    loading, setLoading,
    loadingText, setLoadingText,
    toast, showToast, clearToast,
    stage, setStage,
    activeScene, setActiveScene,
    mode, setMode,
    pipelineMode,
    videoDuration,
    disconnected, setDisconnected,
  } = useAppStore();

  const [keyConfigured, setKeyConfigured] = useState<boolean>(() => hasApiKey());
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const {
    threadId, setThreadId,
    reviewState, setReviewState,
    oneshotResult, setOneshotResult,
    oneshotScenario, setOneshotScenario,
    stepByStepLabel,
    stepByStepState, setStepByStepState,
    showStepByStep, setShowStepByStep,
    smartCreateLabel, setSmartCreateLabel,
    workflowConfig, setWorkflowConfig,
    workflowLabel, setWorkflowLabel,
    workflowState, setWorkflowState,
    showWorkflow, setShowWorkflow,
    currentStepIdx,
    showSteps,
    startActivePipeline,
    clearActivePipeline,
  } = usePipelineStore();

  const {
    currentGate, setCurrentGate,
    setShowStageProgress,
    compareVersions, setCompareVersions,
    showCompare, setShowCompare,
  } = useExpertStore();

  // v2.0: Execution bar for Smart Create
  const { isGenerating, generatingLabel, generatingProgress, startGenerating, stopGenerating } = useExecutionBar();

  // GAP-A: synchronous lock — `loading` from store is async-propagated so a
  // rapid double-click can fire the pipeline twice before the button disables.
  const { submitting: starting, wrap: wrapStart } = useSubmitting();

  const { t } = useI18n();

  // GAP-C: ApiError → fieldErrors state for inline form rendering; 429 → retry hint;
  // other → toast only. Callers MUST `setFieldErrors({})` before resubmit.
  const reportSubmitError = useCallback((e: unknown, fallbackKey: string) => {
    if (isApiError(e)) {
      setFieldErrors(e.info.fieldErrors);
      const tail =
        e.info.retryAfterSec != null
          ? ` (retry in ${e.info.retryAfterSec}s)`
          : "";
      showToast(t(fallbackKey) + `: ${e.info.message}${tail}`, "error");
      return;
    }
    const msg = e instanceof Error ? e.message : String(e);
    if (e instanceof TypeError && (msg.includes("Failed to fetch") || msg.includes("NetworkError"))) {
      setDisconnected(true);
      showToast(t("toast.backendDisconnected"), "error");
    } else {
      showToast(t(fallbackKey) + `: ${msg}`, "error");
    }
  }, [t, showToast, setDisconnected]);

  // v2.0: Save completed creations to gallery (localStorage)
  const saveToGallery = useCallback((result: GalleryResult, scenario: string) => {
    try {
      const brief = result?.briefs?.[0] || {};
      const script = result?.scripts?.[0] || {};
      const item = {
        id: `${scenario}-${Date.now()}`,
        title: brief.product_name || brief.brand_name || script.product_name || t("gallery.untitled") || "Untitled",
        scene: scenario,
        videoType: brief.video_type || "default",
        thumbnail: result?.thumbnail_image_paths?.[0] || "",
        videoPath: result?.final_video_path || "",
        duration: result?.video_duration || 0,
        score: result?.audit_report?.overall_score || 0,
        createdAt: new Date().toISOString(),
      };
      const stored = JSON.parse(localStorage.getItem("hermes_gallery_items") || "[]");
      stored.unshift(item);
      localStorage.setItem("hermes_gallery_items", JSON.stringify(stored.slice(0, 50)));
    } catch {
      // ignore storage errors
    }
  }, [t]);

  const router = useRouter();
  const pathname = usePathname();

  // Expert Studio gate progression
  const GATE_SEQUENCE = [
    { gateId: "gate_1_script", gateLabel: t("gate.selectScript"), maxSelections: 2 },
    { gateId: "gate_2_keyframe", gateLabel: t("gate.reviewKeyframes"), maxSelections: 1 },
    { gateId: "gate_3_clips", gateLabel: t("gate.selectClips"), maxSelections: 1 },
    { gateId: "gate_4_final", gateLabel: t("gate.finalReview"), maxSelections: 1 },
  ];
  const currentGateDef = currentGate >= 1 ? GATE_SEQUENCE[currentGate - 1] : null;

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  /** Cancel current async operation, recover partial state if possible. */
  const handleCancel = useCallback(async () => {
    abortRef.current?.abort();
    setLoading(false);
    setShowStageProgress(false);
    if (stepByStepLabel) {
      try {
        const partial = await fetchS1State(stepByStepLabel);
        if (partial) { setStepByStepState(partial); setShowStepByStep(true); }
      } catch { showToast(t("toast.cancelNoPartial"), "info"); }
    }
  }, [
    setLoading,
    setShowStageProgress,
    setShowStepByStep,
    setStepByStepState,
    showToast,
    stepByStepLabel,
    t,
  ]);

  const S1_STEPS = [
    { label: t("wstep.strategy"), duration: 5000 },
    { label: t("wstep.scripts"), duration: 5000 },
    { label: t("wstep.compliance"), duration: 2000 },
    { label: t("wstep.storyboards"), duration: 4000 },
    { label: t("wstep.video_prompts"), duration: 3000 },
    { label: t("wstep.thumbnail_prompts"), duration: 3000 },
    { label: t("wstep.seedance_clips"), duration: 360000 },    // 2 clips × ~3min
    { label: t("wstep.tts_audio"), duration: 180000 },          // merged: ~3min
    { label: t("wstep.thumbnail_images"), duration: 120000 },   // 2 images × ~1min
    { label: t("wstep.assemble_final"), duration: 15000 },
    { label: t("wstep.audit"), duration: 5000 },
    { label: t("step.distribution"), duration: 3000 },
  ];

  useEffect(() => {
    // Demo mode: clear any stale localStorage and skip all API recovery
    if (isDemoMode()) {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem("ai_video_expert_session");
      return;
    }

    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      setThreadId(stored);
      fetchState(stored)
        .then((data) => {
          if (data.status === "not_found" || data.status === "error") {
            localStorage.removeItem(STORAGE_KEY);
            setThreadId(null);
            return;
          }
          setReviewState(data);
        })
        .catch(() => {
          // Fix A: clear stale thread ID on fetch failure (e.g. old LangGraph endpoint)
          localStorage.removeItem(STORAGE_KEY);
          setThreadId(null);
        });
    }

    // Expert mode session recovery (Fix A: enforce max age)
    const storedSession = localStorage.getItem("ai_video_expert_session");
    if (storedSession) {
      try {
        const session = JSON.parse(storedSession);
        const maxAge = 24 * 60 * 60 * 1000; // 24 hours
        if (session.savedAt && Date.now() - session.savedAt > maxAge) {
          localStorage.removeItem("ai_video_expert_session");
        } else if (session.workflowLabel && session.currentGate && session.mode) {
          setWorkflowLabel(session.workflowLabel);
          setCurrentGate(session.currentGate);
          setMode(session.mode);
          setStage("generate");
          setShowWorkflow(true);
          // Restore workflow state asynchronously; clear stale session on failure
          fetchS1State(session.workflowLabel)
            .then((state) => setWorkflowState(state))
            .catch(() => {
              localStorage.removeItem("ai_video_expert_session");
              setWorkflowLabel(null);
              setCurrentGate(0);
              setStage("home");
              setShowWorkflow(false);
            });
        }
      } catch {
        localStorage.removeItem("ai_video_expert_session");
      }
    }
  }, [
    setCurrentGate,
    setMode,
    setReviewState,
    setShowWorkflow,
    setStage,
    setThreadId,
    setWorkflowLabel,
    setWorkflowState,
  ]);

  // showToast is now useAppStore.getState().showToast

  // Persist expert mode session on gate changes
  useEffect(() => {
    if (stage === "generate" && mode === "expert" && workflowLabel && currentGate > 0) {
      localStorage.setItem("ai_video_expert_session", JSON.stringify({
        workflowLabel,
        currentGate,
        mode,
        savedAt: Date.now(),
      }));
    }
  }, [currentGate, workflowLabel, mode, stage]);

  const refreshState = useCallback(async () => {
    if (!threadId) return;
    try {
      const data = await fetchState(threadId);
      if (data.status === "not_found" || data.status === "error") {
        localStorage.removeItem(STORAGE_KEY);
        setThreadId(null);
        setReviewState(null);
        return;
      }
      setReviewState(data);
      setDisconnected(false);
    } catch (e: unknown) {
      if (
        e instanceof TypeError &&
        (e.message === "Failed to fetch" || e.message.includes("NetworkError"))
      ) {
        setDisconnected(true);
      }
    }
  }, [setDisconnected, setReviewState, setThreadId, threadId]);

  // P3-2: Adaptive polling — active 3s, complete 10s, disconnected 30s
  const getPollInterval = useCallback((): number => {
    if (disconnected) return 30000;
    if (reviewState?.pipeline_complete) return 10000;
    return 3000;
  }, [disconnected, reviewState?.pipeline_complete]);

  useEffect(() => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    if (threadId) {
      pollingRef.current = setInterval(refreshState, getPollInterval());
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [threadId, refreshState, getPollInterval]);

  useEffect(() => {
    if (!loading) return;
    const timer = setTimeout(() => {
      if (usePipelineStore.getState().activePipeline) {
        setLoading(false);
      }
    }, 5000);
    return () => clearTimeout(timer);
  }, [loading, setLoading]);

  const [pendingConfig, setPendingConfig] = useState<SceneConfig | null>(null);

  const handleSceneSubmit = useCallback((config: Record<string, unknown>) => {
    const sceneConfig = config as SceneConfig;
    setPendingConfig(sceneConfig);
    // Extract mode from the submitted config if present
    if (sceneConfig.mode === "expert" || sceneConfig.mode === "smart") {
      setMode(sceneConfig.mode);
    }
    setStage("recommend");
  }, [setMode, setStage]);

  const startSmartCreate = (config: SceneConfig) => wrapStart(async () => {
    const scenario = config.content_scenario || "product_direct";
    const scenarioId = sceneToScenarioId(scenario);
    setFieldErrors({});

    // Demo mode: skip API calls, serve mock data instantly
    if (isDemoMode()) {
      const isBrand = scenario === "brand_campaign";
      const isVlog = scenario === "brand_vlog";
      const demoResult = isVlog ? DEMO_RESULT_VLOG : isBrand ? DEMO_RESULT_2 : DEMO_RESULT_1;
      setOneshotResult(demoResult);
      setOneshotScenario(scenario);
      setStage("result");
      showToast(isVlog ? t("toast.vlogDone") : t("toast.autoDone"), "success");
      return;
    }

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setShowStageProgress(true);
    startGenerating(t("exec.narrative.analyzing"));
    try {
      const submitPayload = {
        product_catalog: config.product_catalog,
        brand_guidelines: config.brand_guidelines,
        target_platforms: config.target_platforms,
        target_languages: config.target_languages || ["en"],
        week: config.content_calendar_week || "",
        video_duration: config.video_duration || 30,
      };
      // Phase 1B: Unified async submit — returns label immediately, pipeline runs in background
      const submitResult = await submitScenario(
        scenarioId,
        withScenarioContinuityConfig(config, submitPayload),
        { signal: abortRef.current?.signal }
      );
      setSmartCreateLabel(submitResult.label);
      startActivePipeline({
        label: submitResult.label,
        scenario: scenarioId,
        scene: scenario,
        startedAt: Date.now(),
      });
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      // Fallback: legacy blocking endpoint for s1 only
      if (scenarioId === "s1") {
        try {
          const result = await runS1ProductDirect(
            withScenarioContinuityConfig(config, {
              product_catalog: config.product_catalog,
              brand_guidelines: config.brand_guidelines,
              target_platforms: config.target_platforms,
              target_languages: config.target_languages || ["en"],
              week: config.content_calendar_week || "",
              video_duration: config.video_duration || 30,
            }),
            { signal: abortRef.current?.signal }
          );
          const label = result?.label || `s1_${Date.now()}`;
          setSmartCreateLabel(label);
          startActivePipeline({
            label,
            scenario: scenarioId,
            scene: scenario,
            startedAt: Date.now(),
          });
        } catch (fallbackErr: unknown) {
          if (fallbackErr instanceof DOMException && fallbackErr.name === "AbortError") return;
          reportSubmitError(fallbackErr, "toast.execFailed");
          setShowStageProgress(false);
          stopGenerating();
        }
      } else {
        reportSubmitError(e, "toast.execFailed");
        setShowStageProgress(false);
        stopGenerating();
      }
    }
  });

  const handleSmartCreateError = useCallback((errors: string[]) => {
    handleSmartCreateStageError(errors, {
      stopGenerating,
      clearActivePipeline,
      showToast,
      t,
    });
  }, [clearActivePipeline, showToast, stopGenerating, t]);

  const handleStart = (config: SceneConfig) => wrapStart(async () => {
    setFieldErrors({});
    // Demo mode: skip all API calls, serve mock data instantly
    if (isDemoMode()) {
      const scenario = config.content_scenario || "product_direct";
      const isBrand = scenario === "brand_campaign";
      const isVlog = scenario === "brand_vlog";
      const effectiveMode = config.mode || pipelineMode;
      const demoResult = isVlog ? DEMO_RESULT_VLOG : isBrand ? DEMO_RESULT_2 : DEMO_RESULT_1;

      if (effectiveMode === "auto" || effectiveMode === "smart") {
        // Smart/Auto mode: show final result directly
        setOneshotResult(demoResult);
        setOneshotScenario(scenario);
        setStage("result");
        showToast(isVlog ? t("toast.vlogDone") : t("toast.autoDone"), "success");
        return;
      }

      // Expert Studio mode: build workflow state from demo data and enter gate flow
      const demoState = {
        steps: {
          strategy: { status: "done", output: demoResult.briefs },
          scripts: { status: "done", output: demoResult.scripts },
          compliance: { status: "done", output: { briefs: demoResult.briefs, passed: true } },
          storyboards: { status: "done", output: demoResult.storyboards },
          video_prompts: { status: "done", output: demoResult.video_prompts },
          thumbnail_prompts: { status: "done", output: demoResult.thumbnail_sets },
          seedance_clips: { status: "done", output: demoResult.seedance_output },
          tts_audio: { status: "done", output: { audio_paths: demoResult.audio_paths } },
          thumbnail_images: { status: "done", output: demoResult.thumbnail_image_paths },
          assemble_final: { status: "done", output: demoResult.final_video_path },
          audit: { status: "done", output: demoResult.audit_report },
        },
        errors: [],
      };
      setWorkflowConfig(config);
      setWorkflowLabel(`demo_${scenario}_${Date.now()}`);
      setWorkflowState(demoState);
      setShowWorkflow(true);
      setCurrentGate(1);
      showToast(t("toast.workflowInit"), "success");
      return;
    }

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setLoading(true);
    const scenario = config.content_scenario || "product_direct";

    const effectiveModeRaw = config.mode || pipelineMode;
    const effectiveMode = supportsStepByStep(scenario) ? effectiveModeRaw : "auto";
    if (effectiveModeRaw === "step_by_step" && !supportsStepByStep(scenario)) {
      showToast(t("toast.stepByStepS1Only"), "info");
    }
    if (scenario === "brand_vlog") {
      // S5 Brand VLOG — dedicated endpoint
      setLoadingText(t("app.loading"));
      try {
        const result = await runS5BrandVlog({
          brand_id: config.brand_id || "momcozy",
          product_sku: config.product_sku || {},
          scene_id: config.scene_id || "living-room",
          selected_models: config.selected_models || [],
          story_description: config.story_description || "",
          video_duration: config.video_duration || 30,
          ...withScenarioContinuityConfig(config, {}),
        }, { signal: abortRef.current?.signal });
        setOneshotResult(result);
        setOneshotScenario(scenario);
        saveToGallery(result, scenario);
        showToast(t("toast.vlogDone"), "success");
      } catch (e: unknown) {
        reportSubmitError(e, "toast.execFailed");
      }
      setLoading(false);
      return;
    }

    if (effectiveMode === "auto") {
      // Auto mode: run all steps in one shot
      setLoadingText(t("app.loading"));
      try {
        const result = await runS1ProductDirect(
          withScenarioContinuityConfig(config, {
            product_catalog: {
              name: config.product_catalog?.products?.[0]?.name
                || config.product_catalog?.name
                || "Product",
              ...(config.product_catalog || {}),
            },
            brand_guidelines: config.brand_guidelines,
            target_platforms: config.target_platforms || ["tiktok", "shopify"],
            target_languages: config.target_languages || ["en"],
            week: config.content_calendar_week || "",
            video_duration: config.video_duration || videoDuration,
          }),
          { signal: abortRef.current?.signal }
        );

        setOneshotResult(result);
        setOneshotScenario(scenario);
        saveToGallery(result, scenario);
        showToast(t("toast.autoDone"), "success");
      } catch (e: unknown) {
        reportSubmitError(e, "toast.execFailed");
      }
      setLoading(false);
      return;
    }

    // Step-by-step mode
    try {
      setLoadingText(t("app.loading"));
      const result = await startS1StepByStep(
        withScenarioContinuityConfig(config, {
          product_catalog: {
            name: config.product_catalog?.products?.[0]?.name
              || config.product_catalog?.name
              || "Product",
            brand_name: config.brand_guidelines?.brand_name || "",
            usps: config.product_catalog?.products?.[0]?.usps
              || config.product_catalog?.usps
              || [],
            // Preserve all product context fields from SceneForm
            ...(config.product_catalog?.products?.[0] || {}),
          },
          brand_guidelines: config.brand_guidelines,
          target_platforms: config.target_platforms || ["tiktok", "shopify"],
          target_languages: config.target_languages || ["en"],
          week: config.content_calendar_week || "",
          video_duration: config.video_duration || videoDuration,
        }),
        { signal: abortRef.current?.signal }
      );
      if (!result || !result.label) {
        showToast(t("toast.abnormalData"), "error");
        setLoading(false);
        return;
      }
      setWorkflowConfig(config);
      setWorkflowLabel(result.label);
      setWorkflowState(result.state || {});
      setShowWorkflow(true);
      setCurrentGate(1);
      startActivePipeline({
        label: result.label,
        scenario: "s1",
        scene: config.content_scenario || "product_direct",
        startedAt: Date.now(),
      });
      showToast(t("toast.workflowInit"), "success");
    } catch (e: unknown) {
      reportSubmitError(e, "toast.initFailed");
    }
    setLoading(false);
  });

  const handleReview = async (
    action: "approve" | "reject" | "request_changes",
    notes?: string,
  ) => {
    if (loading || !threadId || !reviewState?.current_review) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setLoading(true);

    const labels: Record<string, string> = {
      approve: t("review.label.approve"),
      reject: t("review.label.reject"),
      request_changes: t("review.label.request_changes"),
    };
    setLoadingText(t("review.submitting") + `: ${labels[action]}...`);

    try {
      await submitReview(threadId, reviewState.current_review, action, notes || "");
      showToast(t("toast.reviewSubmitted"), "success");

      for (let i = 0; i < 5; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        try {
          const data = await fetchState(threadId, { signal: abortRef.current?.signal });
          if (
            data.current_review !== reviewState?.current_review ||
            data.pipeline_complete ||
            data.current_review === null
          ) {
            setReviewState(data);
            break;
          }
        } catch {
          // retry
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      if (
        e instanceof TypeError &&
        (e.message.includes("Failed to fetch") || e.message.includes("NetworkError"))
      ) {
        setDisconnected(true);
        showToast(t("app.backendDisconnectShort"), "error");
      } else {
        showToast(t("toast.reviewSubmitFailed") + `: ${errorMessage(e)}`, "error");
      }
    }
    setLoading(false);
  };



  const resetAll = () => {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem("ai_video_expert_session");
    usePipelineStore.getState().resetAll();
    useExpertStore.getState().resetExpert();
    useAppStore.getState().resetApp();
  };

  const [showAbandonConfirm, setShowAbandonConfirm] = useState(false);
  const requestAbandon = () => {
    if (threadId || oneshotResult) {
      setShowAbandonConfirm(true);
    } else {
      resetAll();
    }
  };
  const confirmAbandon = () => {
    setShowAbandonConfirm(false);
    resetAll();
  };

  const currentReview = reviewState?.current_review;
  const pipelineComplete =
    reviewState?.pipeline_complete === true && reviewState?.current_review === null;

  // Stage-machine-aware view flags (backward-compatible with existing logic)
  const showSelector = !threadId && !oneshotResult && !showStepByStep && !showWorkflow && stage === "home";
  const showOneshot = oneshotResult && !threadId;
  const showCompletion = !!threadId && pipelineComplete;
  const showReview = !!threadId && reviewState && !pipelineComplete;

  return (
    <>
      <Suspense fallback={null}>
        <URLSync activeScene={activeScene} mode={mode} pathname={pathname} router={router} showSplash={showSplash} />
      </Suspense>
      {showSplash && <SplashScreen onEnter={() => setShowSplash(false)} />}
      {!showSplash && !keyConfigured && <ApiKeyGate onUnlock={() => setKeyConfigured(true)} />}
      <ErrorBoundary>
      <div className={`min-h-screen bg-[var(--color-bg)] overflow-x-hidden transition-opacity duration-700 ${showSplash ? 'opacity-0' : 'opacity-100'}`}>
        {/* Toast */}
        {toast && (
          <div
            className={`apple-toast apple-toast-${toast.type}`}
            onClick={() => clearToast()}
          >
            <div className="flex items-center gap-2">
              {toast.type === "success" && (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M4 8.5L7 11.5L12 5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
              {toast.type === "error" && (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M5 5L11 11M11 5L5 11" stroke="white" strokeWidth="2" strokeLinecap="round" />
                </svg>
              )}
              {toast.message}
            </div>
          </div>
        )}

        {/* Loading overlay */}
        {loading && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
            <div className="apple-card px-8 py-8 flex flex-col items-center gap-5 w-full max-w-md mx-4">
              <div className="relative w-10 h-10">
                <svg className="animate-spin w-10 h-10" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="var(--border-default)" strokeWidth="3" />
                  <path d="M12 2a10 10 0 0 1 10 10" stroke="var(--neon-red)" strokeWidth="3" strokeLinecap="round" />
                </svg>
              </div>
              <div className="text-center space-y-1">
                <p className="text-sm text-[var(--text-body)]">{loadingText}</p>
                {showSteps && currentStepIdx < S1_STEPS.length && currentStepIdx >= 0 && (
                  <p className="text-base font-semibold text-[var(--text-h1)]">
                    {S1_STEPS[currentStepIdx]?.label}
                  </p>
                )}
              </div>
              {showSteps && (
                <div className="w-full space-y-2">
                  <div className="h-1.5 w-full bg-[var(--bg-panel)] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[var(--fortune-red)] rounded-full transition-all duration-700 ease-out"
                      style={{
                        width: `${Math.min(((currentStepIdx + 0.5) / S1_STEPS.length) * 100, 100)}%`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-[12px] text-[var(--text-muted)]">
                    <span>{t("app.step")} {Math.min(currentStepIdx + 1, S1_STEPS.length)} / {S1_STEPS.length}</span>
                    <span>{Math.round(Math.min(((currentStepIdx + 0.5) / S1_STEPS.length) * 100, 100))}%</span>
                  </div>
                </div>
              )}
              {showSteps && (
                <div className="flex flex-wrap justify-center gap-1.5 max-w-sm">
                  {S1_STEPS.map((step, i) => {
                    const done = i < currentStepIdx;
                    const active = i === currentStepIdx;
                    return (
                      <span
                        key={i}
                        className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-[12px] font-medium transition-all duration-300 ${
                          done
                            ? "bg-[rgba(215,92,112,0.12)] text-[var(--fortune-red)]"
                            : active
                            ? "bg-[var(--fortune-red-600)] text-white shadow-[0_0_6px_rgba(215,92,112,0.20)] ring-2 ring-[rgba(215,92,112,0.30)]"
                            : "bg-[var(--bg-panel)] text-[var(--text-muted)]"
                        }`}
                      >
                        {done && (
                          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                            <path d="M2 5.5L4 7.5L8 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                        {active && (
                          <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                        )}
                        {step.label}
                      </span>
                    );
                  })}
                </div>
              )}
              <button
                onClick={handleCancel}
                className="mt-3 px-4 py-2 rounded-xl text-xs font-medium text-[var(--text-muted)] border border-[var(--border-default)] hover:text-[var(--cinnabar)] hover:border-[var(--cinnabar)] hover:bg-[rgba(208,78,90,0.08)] transition-colors duration-200 cursor-pointer"
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        )}

        {/* Header */}
        <header className="sticky top-0 z-40 bg-[var(--bg-page)]/85 backdrop-blur-xl border-b border-[var(--divider-subtle)]">
          <div className="max-w-[1440px] mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              <Link href="/" className="flex items-center gap-2 sm:gap-3 shrink-0" aria-label={t("app.title")}>
                <div className="w-7 h-7 rounded-lg bg-[var(--fortune-red)] flex items-center justify-center">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                    <path d="M8 5v14l11-7z" fill="white" />
                  </svg>
                </div>
                <span className="hidden lg:inline text-sm font-semibold text-[var(--text-h1)] tracking-tight">
                  {t("app.title")}
                </span>
              </Link>
              <Nav />
            </div>
            <div className="flex items-center gap-1 sm:gap-2 shrink-0">
              <Link
                href="/admin/dashboard"
                aria-label={t("nav.admin")}
                title={t("nav.admin")}
                className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-[rgba(53,20,26,0.06)] text-[var(--text-muted)] hover:text-[var(--fortune-red)] transition-colors cursor-pointer"
              >
                <ShieldCheck size={16} weight="fill" />
              </Link>
              {Boolean(threadId || oneshotResult) && (
                <button
                  onClick={requestAbandon}
                  className="text-xs text-[var(--text-muted)] hover:text-[var(--text-h1)] transition-colors px-3 py-1.5 rounded-lg hover:bg-[rgba(53,20,26,0.06)] cursor-pointer"
                >
                  {t("app.abandon")}
                </button>
              )}
            </div>
          </div>
          <PipelineStatusBar />
        </header>

        <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6 overflow-x-hidden">
          <div key={stage + (activeScene || "")}>
          {/* Stage 0: Home — Scene selection + form */}
          {stage === "home" && showSelector && (
            <div className="space-y-3">
              <SceneTabs
                activeScene={activeScene}
                onChange={setActiveScene}
                videoCounts={{ product_direct: 0, brand_campaign: 0, influencer_remix: 0, fast_mode: 0 }}
              />
              {activeScene === "fast_mode" ? (
                <FastModePanel />
              ) : (
                <SceneForm
                  scene={activeScene}
                  onSubmit={handleSceneSubmit}
                  loading={loading || starting}
                  fieldErrors={fieldErrors}
                />
              )}
            </div>
          )}

          {/* Stage 1: Recommend — AI recommendation panel */}
          {stage === "recommend" && pendingConfig !== null ? (
            <RecommendPanel
              config={pendingConfig}
              onBack={() => setStage("home")}
              onStart={(finalConfig) => {
                if (finalConfig.mode === "smart" || mode === "smart") {
                  // Smart Create: auto-execute, show StageProgress
                  setStage("generate");
                  setMode("smart");
                  startSmartCreate(finalConfig);
                } else {
                  // Expert Studio: step-by-step with gates
                  setStage("generate");
                  setMode("expert");
                  handleStart(finalConfig);
                }
              }}
            />
          ) : null}

          {/* Stage 2: Generate — pipeline execution view */}
          {stage === "generate" && mode === "expert" ? (
            showCompare ? (
              <CompareView
                versions={compareVersions}
                selectedVersion={null}
                onSelect={() => {
                  // Track which version the user selected
                }}
                onDownload={(label) => {
                  const v = compareVersions.find(v => v.label === label);
                  if (v?.videoPath) {
                    window.open(getMediaUrl(v.videoPath), '_blank');
                  }
                }}
                onNewCreation={() => {
                  resetAll();
                  setStage("home");
                }}
                onBack={() => {
                  setShowCompare(false);
                  setCurrentGate(4);
                }}
                onPublish={() => {
                  // Placeholder for future publish flow
                }}
              />
            ) : showWorkflow && workflowLabel && currentGate >= 1 ? (
              workflowState !== null ? (
                <GatePanel
                  key={`gate-${currentGate}`}
                  label={workflowLabel}
                  gateId={currentGateDef?.gateId || "gate_1_script"}
                  gateLabel={currentGateDef?.gateLabel || ""}
                  maxSelections={currentGateDef?.maxSelections || 1}
                  currentStep={currentGate}
                  totalSteps={GATE_SEQUENCE.length}
                  gateSequence={GATE_SEQUENCE}
                  onApprove={async () => {
                    if (currentGate === GATE_SEQUENCE.length) {
                      // Gate 4 (final) approved — fetch final state and show CompareView
                      if (!workflowLabel) {
                        showToast(t("toast.execFailed"), "error");
                        return;
                      }
                      try {
                        showToast(t("gate.finalReview") + " approved — loading results...", "info");
                        // Demo mode: build versions directly from workflowState
                        if (isDemoMode()) {
                          const ws = asRecord(workflowState);
                          const wsSteps = asRecord(ws.steps);
                          const demoVersions = extractVersions({ steps: wsSteps as PipelineStateLike["steps"] || {} });
                          const assembleFinal = asRecord(wsSteps.assemble_final);
                          const thumbnailImages = asRecord(wsSteps.thumbnail_images);
                          const auditStep = asRecord(wsSteps.audit);
                          const thumbnailOutput = Array.isArray(thumbnailImages.output) ? thumbnailImages.output : [];
                          const auditOutput = auditStep.output;
                          const auditRecord = asRecord(auditOutput);
                          setCompareVersions(demoVersions.length > 0 ? demoVersions : [{
                            label: "Version A",
                            scriptVariant: "standard",
                            videoPath: String(assembleFinal.output || ""),
                            thumbnailPath: String(thumbnailOutput[0] || ""),
                            auditReport: asAuditReport(auditOutput),
                            duration: typeof auditRecord.duration_seconds === "number" ? auditRecord.duration_seconds : 0,
                            fileSize: 0,
                          }]);
                          setShowCompare(true);
                          setCurrentGate(0);
                          showToast(t("toast.workflowDone"), "success");
                          return;
                        }
                        const state = await fetchS1State(workflowLabel);
                        const versions = extractVersions(state);
                        setCompareVersions(versions);
                        setShowCompare(true);
                        setCurrentGate(0);
                        showToast(t("toast.workflowDone"), "success");
                      } catch (e: unknown) {
                        showToast(t("toast.execFailed") + `: ${errorMessage(e)}`, "error");
                      }
                    } else {
                      setCurrentGate(currentGate + 1);
                    }
                  }}
                  onBack={() => setStage("recommend")}
                />
              ) : (
                <div className="flex flex-col items-center justify-center h-full gap-6 text-white/80">
                  <div className="animate-spin w-8 h-8 border-2 border-white/30 border-t-white rounded-full" />
                  <p className="text-sm">{t("session.recovering")}</p>
                  <button
                    onClick={() => {
                      localStorage.removeItem("ai_video_expert_session");
                      setWorkflowLabel(null);
                      setCurrentGate(0);
                      setStage("home");
                      setShowWorkflow(false);
                    }}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-sm transition-colors"
                  >
                    {t("session.restart")}
                  </button>
                </div>
              )
            ) : null
          ) : null}

          {stage === "generate" && mode === "smart" && smartCreateLabel !== null ? (
            <StageProgress
              label={smartCreateLabel}
              scenario={sceneToScenarioId(activeScene || "product_direct")}
              onError={handleSmartCreateError}
              onComplete={(result) => {
                setOneshotResult(result);
                setOneshotScenario(activeScene || "product_direct");
                saveToGallery(result as GalleryResult, activeScene || "product_direct");
                setStage("result");
                setShowStageProgress(false);
                clearActivePipeline();
              }}
            />
          ) : null}

          {/* Stage 3: Result — one-shot result view */}
          {stage === "result" && oneshotResult !== null ? (
            <OneShotResultView
              scenario={oneshotScenario}
              result={oneshotResult}
              onReset={() => {
                resetAll();
                setStage("home");
              }}
            />
          ) : null}

          {showStepByStep && stepByStepLabel !== null && stepByStepState !== null ? (
            <StepByStepView
              label={stepByStepLabel}
              state={stepByStepState as Record<string, unknown>}
              onStepComplete={(newState) => setStepByStepState(newState)}
              onResume={(finalState) => {
                setStepByStepState(finalState);
                setShowStepByStep(false);
                setOneshotResult(finalState);
                setOneshotScenario("product_direct");
                showToast(t("toast.stepByStepDone"), "success");
              }}
              onError={(msg) => showToast(msg, "error")}
              loading={loading}
            />
          ) : null}

          {/* Backward-compatible: only show when stage-machine does NOT handle it */}
          {!(stage === "generate" && mode === "expert") && !(stage === "result" && oneshotResult !== null) && showWorkflow && workflowLabel !== null && workflowState !== null ? (
            <VideoWorkflow
              config={workflowConfig}
              label={workflowLabel}
              state={workflowState}
              onStateChange={(newState) => setWorkflowState(newState)}
              onComplete={(finalState) => {
                setShowWorkflow(false);
                setOneshotResult(finalState);
                setOneshotScenario("product_direct");
                showToast(t("toast.workflowDone"), "success");
              }}
              onReset={resetAll}
              loading={loading}
              setLoading={setLoading}
              setLoadingText={setLoadingText}
            />
          ) : null}

          {showCompletion && (
            <div className="grid grid-cols-[320px_1fr] gap-3">
              <div>
                <PipelineMonitor
                  state={reviewState!.state}
                  currentReview={null}
                  threadId={threadId!}
                  pipelineComplete={true}
                  onReset={resetAll}
                />
              </div>
              <div>
                <DistributionView threadId={threadId!} onRestart={resetAll} />
              </div>
            </div>
          )}

          {showReview && (
            <div className="grid grid-cols-[320px_1fr] gap-3">
              <div>
                <PipelineMonitor
                  state={reviewState!.state}
                  currentReview={currentReview}
                  threadId={threadId!}
                  pipelineComplete={false}
                  onReset={resetAll}
                />
              </div>
              <div>
                {disconnected && (
                  <div className="apple-card p-4 mb-4 border-l-4 border-[var(--cinnabar)] bg-[rgba(208,78,90,0.08)]">
                    <p className="text-sm text-[var(--cinnabar)] font-medium">{t("app.backendDisconnected")}</p>
                  </div>
                )}
                {/* P1-2: Review progress indicator */}
                <ReviewProgressIndicator currentReview={currentReview} reviewState={reviewState} />
                {currentReview ? (
                  <ReviewPanel
                    currentReview={currentReview}
                    reviewState={reviewState!}
                    onAction={handleReview}
                    loading={loading}
                  />
                ) : (
                  <div className="apple-card p-6 text-center">
                    <div className="w-12 h-12 rounded-2xl bg-[rgba(215,92,112,0.12)] flex items-center justify-center mx-auto mb-3">
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="var(--fortune-red)" strokeWidth="2" />
                        <path d="M12 6v6l4 2" stroke="var(--fortune-red)" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                    </div>
                    <p className="text-sm text-[var(--text-body)]">{t("app.waitingReview")}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Fallback: if nothing matches, recover to home stage */}
          {!showSelector && !showOneshot && !showStepByStep && !showWorkflow && !showCompletion && !showReview && (
            <div className="apple-card p-8 text-center space-y-3">
              <p className="text-sm text-[var(--text-body)]">{t("app.pageLoading")}</p>
              <button
                onClick={() => { setStage("home"); setThreadId(null); setShowSplash(false); setShowWorkflow(false); }}
                className="apple-btn apple-btn-primary text-xs px-4 py-2"
              >
                {t("app.returnHome")}
              </button>
            </div>
          )}
          </div>
        </main>

        {/* v2.0: Smart Create execution bar */}
        {isGenerating && (
          <ExecutionBar
            label={generatingLabel}
            progress={generatingProgress}
            onCancel={() => abortRef.current?.abort()}
          />
        )}

        {showSettings && (
          <SettingsPanel onClose={() => setShowSettings(false)} />
        )}

        <ConfirmModal
          open={showAbandonConfirm}
          title={t("confirm.abandon.title")}
          body={t("confirm.abandon.body")}
          confirmLabel={t("confirm.abandon.yes")}
          confirmVariant="danger"
          cancelLabel={t("confirm.cancel")}
          closeLabel={t("common.close")}
          onConfirm={confirmAbandon}
          onCancel={() => setShowAbandonConfirm(false)}
        />
      </div>
      </ErrorBoundary>
    </>
  );
}

// P1-12: URL sync — extracted to avoid useSearchParams() SSR bailout
function URLSync({
  activeScene,
  mode,
  pathname,
  router,
  showSplash,
}: {
  activeScene: string;
  mode: string | null;
  pathname: string;
  router: ReturnType<typeof useRouter>;
  showSplash: boolean;
}) {
  const searchParams = useSearchParams();

  useEffect(() => {
    if (showSplash) return;
    const targetPath = sceneToPath(activeScene);
    if (targetPath && pathname !== targetPath) {
      const params = new URLSearchParams(searchParams.toString());
      if (mode) params.set("mode", mode);
      router.replace(`${targetPath}?${params.toString()}`, { scroll: false });
    }
  }, [activeScene, mode, pathname, router, searchParams, showSplash]);

  return null;
}
