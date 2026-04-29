"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { ReviewState } from "@/components/types";
import {
  startPipeline,
  fetchState,
  submitReview,
  runS1ProductDirect,
  runS4LiveShoot,
  startS1StepByStep,
  resumeS1,
  fetchS1State,
  getMediaUrl,
} from "@/components/api";
import SceneTabs from "@/components/SceneTabs";
import SceneForm from "@/components/SceneForm";
import SceneSelector from "@/components/SceneSelector";
import PipelineMonitor from "@/components/PipelineMonitor";
import ReviewPanel from "@/components/ReviewPanel";
import DistributionView from "@/components/DistributionView";
import OneShotResultView from "@/components/OneShotResultView";
import CompareView, { Version } from "@/components/CompareView";
import StepByStepView from "@/components/StepByStepView";
import VideoWorkflow from "@/components/VideoWorkflow";
import GatePanel from "@/components/GatePanel";
import StageProgress from "@/components/StageProgress";
import AssetLibrary from "@/components/AssetLibrary";
import SplashScreen from "@/components/SplashScreen";
import RecommendPanel from "@/components/RecommendPanel";
import QualityDashboard from "@/components/QualityDashboard";
import Nav from "@/components/Nav";
import { useI18n } from "@/i18n/I18nProvider";

const STORAGE_KEY = "ai_video_thread_id";

const LANGGRAPH_SCENARIOS = new Set(["influencer_remix", "brand_campaign"]);

function extractVersions(state: any): Version[] {
  const versions: Version[] = [];
  const steps = state?.steps || {};
  const assembleOutput = steps.assemble_final?.output;
  const auditOutput = steps.audit?.output;
  const scripts = steps.scripts?.output || [];
  const seedanceOutput = steps.seedance_clips?.output || [];

  // Extract video path from assemble_final output (string, or object with video_path, or array)
  const videoPath =
    typeof assembleOutput === "string"
      ? assembleOutput
      : assembleOutput?.video_path || (Array.isArray(assembleOutput) ? assembleOutput[0] : "");

  versions.push({
    label: "Version A",
    scriptVariant: scripts[0]?.variant || "standard",
    videoPath,
    thumbnailPath: steps.thumbnail_images?.output?.[0] || "",
    auditReport: auditOutput || null,
    duration: auditOutput?.duration_seconds || 0,
    fileSize: 0,
  });

  // If the user selected 2 scripts in Gate 1, the pipeline may produce 2 assembled videos
  // Try to find a second video if multiple scripts were used
  if (scripts.length >= 2) {
    const secondVideoPath = Array.isArray(assembleOutput)
      ? assembleOutput[1] || ""
      : typeof assembleOutput === "object" && assembleOutput?.video_path_2
        ? assembleOutput.video_path_2
        : "";

    if (secondVideoPath) {
      versions.push({
        label: "Version B",
        scriptVariant: scripts[1]?.variant || "creative",
        videoPath: secondVideoPath,
        thumbnailPath: steps.thumbnail_images?.output?.[1] || steps.thumbnail_images?.output?.[0] || "",
        auditReport: auditOutput || null,
        duration: auditOutput?.duration_seconds || 0,
        fileSize: 0,
      });
    }
  }

  return versions;
}

export default function Home() {
  const [showSplash, setShowSplash] = useState(true);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [reviewState, setReviewState] = useState<ReviewState | null>(null);
  const [oneshotResult, setOneshotResult] = useState<any | null>(null);
  const [oneshotScenario, setOneshotScenario] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState("");
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" | "info" } | null>(null);
  const [disconnected, setDisconnected] = useState(false);
  const [showAssetLibrary, setShowAssetLibrary] = useState(false);
  const [pipelineMode, setPipelineMode] = useState<"auto" | "step_by_step">("step_by_step");
  const [videoDuration, setVideoDuration] = useState(30);
  const [stepByStepLabel, setStepByStepLabel] = useState<string | null>(null);
  const [stepByStepState, setStepByStepState] = useState<any | null>(null);
  const [showStepByStep, setShowStepByStep] = useState(false);

  // Smart Create states
  const [smartCreateLabel, setSmartCreateLabel] = useState<string | null>(null);
  const [showStageProgress, setShowStageProgress] = useState(false);

  // CompareView states for Gate 4 completion
  const [compareVersions, setCompareVersions] = useState<Version[]>([]);
  const [showCompare, setShowCompare] = useState(false);

  // 4-stage state machine
  const [stage, setStage] = useState<"home" | "recommend" | "generate" | "result">("home");
  const [activeScene, setActiveScene] = useState<string>("product_direct");
  const [mode, setMode] = useState<"expert" | "smart">("expert");

  // Workflow mode states
  const [workflowConfig, setWorkflowConfig] = useState<any | null>(null);
  const [workflowLabel, setWorkflowLabel] = useState<string | null>(null);
  const [workflowState, setWorkflowState] = useState<any | null>(null);
  const [showWorkflow, setShowWorkflow] = useState(false);
  const [workflowRerenderKey, setWorkflowRerenderKey] = useState(0);

  const { t } = useI18n();

  // Expert Studio gate progression
  const [currentGate, setCurrentGate] = useState(0); // 0 = not started, 1-4 = gate index
  const GATE_SEQUENCE = [
    { gateId: "gate_1_script", gateLabel: t("gate.selectScript"), maxSelections: 2 },
    { gateId: "gate_2_keyframe", gateLabel: t("gate.reviewKeyframes"), maxSelections: 1 },
    { gateId: "gate_3_clips", gateLabel: t("gate.selectClips"), maxSelections: 1 },
    { gateId: "gate_4_final", gateLabel: t("gate.finalReview"), maxSelections: 1 },
  ];

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // One-shot step progress
  const [currentStepIdx, setCurrentStepIdx] = useState(0);
  const [showSteps, setShowSteps] = useState(false);
  const stepTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
  }, []);

  const showToast = (message: string, type: "success" | "error" | "info") => {
    setToast({ message, type });
  };

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

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
    } catch (e: any) {
      if (
        e instanceof TypeError &&
        (e.message === "Failed to fetch" || e.message.includes("NetworkError"))
      ) {
        setDisconnected(true);
      }
    }
  }, [threadId]);

  useEffect(() => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    if (threadId) {
      pollingRef.current = setInterval(refreshState, 3000);
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [threadId, refreshState]);

  const configRef = useRef<any>(null);

  const handleSceneSubmit = useCallback((config: any) => {
    configRef.current = config;
    // Extract mode from the submitted config if present
    if (config.mode) {
      setMode(config.mode);
    }
    setStage("recommend");
  }, []);

  const startSmartCreate = async (config: any) => {
    setShowStageProgress(true);
    try {
      // Use existing auto pipeline endpoint
      const result = await runS1ProductDirect({
        product_catalog: config.product_catalog,
        brand_guidelines: config.brand_guidelines,
        target_platforms: config.target_platforms,
        target_languages: config.target_languages || ["en"],
        week: config.content_calendar_week || "",
        video_duration: config.video_duration || 30,
      });

      // Store the label from the result for StageProgress polling
      // The auto endpoint returns the full result directly
      // But StageProgress needs a label to poll. Extract from result or use a generated one.
      const label = result?.label || `s1_${Date.now()}`;
      setSmartCreateLabel(label);
    } catch (e: any) {
      // If auto-endpoint fails, fall back to step-by-step init + auto resume
      // Initialize pipeline in step-by-step mode, then resume in auto
      try {
        const initResult = await startS1StepByStep({ ...config, mode: "step_by_step" });
        const label = initResult.label;
        setSmartCreateLabel(label);
        // Resume will auto-execute all remaining steps
        await resumeS1(label);
      } catch (fallbackErr: any) {
        showToast(t("toast.execFailed") + `: ${fallbackErr?.message || String(fallbackErr)}`, "error");
        setShowStageProgress(false);
      }
    }
  };

  const handleStart = async (config: any) => {
    setLoading(true);
    const scenario = config.content_scenario || "product_direct";

    const effectiveMode = config.mode || pipelineMode;
    if (effectiveMode === "auto") {
      // Auto mode: run all steps in one shot
      setLoadingText(t("app.loading"));
      try {
        const result = await runS1ProductDirect({
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
        });

        setOneshotResult(result);
        setOneshotScenario(scenario);
        showToast(t("toast.autoDone"), "success");
      } catch (e: any) {
        const msg = e?.message || String(e);
        if (
          e instanceof TypeError &&
          (msg.includes("Failed to fetch") || msg.includes("NetworkError"))
        ) {
          setDisconnected(true);
          showToast(t("toast.backendDisconnected"), "error");
        } else {
          showToast(t("toast.execFailed") + `: ${msg}`, "error");
        }
      }
      setLoading(false);
      return;
    }

    // Step-by-step mode
    try {
      setLoadingText(t("app.loading"));
      const result = await startS1StepByStep({
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
      });
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
      showToast(t("toast.workflowInit"), "success");
    } catch (e: any) {
      const msg = e?.message || String(e);
      if (
        e instanceof TypeError &&
        (msg.includes("Failed to fetch") || msg.includes("NetworkError"))
      ) {
        setDisconnected(true);
        showToast(t("toast.backendDisconnected"), "error");
      } else {
        showToast(t("toast.initFailed") + `: ${msg}`, "error");
      }
    }
    setLoading(false);
  };

  const handleReview = async (
    action: "approve" | "reject" | "request_changes",
    notes?: string,
  ) => {
    if (!threadId || !reviewState?.current_review) return;
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
          const data = await fetchState(threadId);
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
    } catch (e: any) {
      if (
        e instanceof TypeError &&
        (e.message.includes("Failed to fetch") || e.message.includes("NetworkError"))
      ) {
        setDisconnected(true);
        showToast(t("app.backendDisconnectShort"), "error");
      } else {
        showToast(t("toast.reviewSubmitFailed") + `: ${e.message}`, "error");
      }
    }
    setLoading(false);
  };

  const clearStepTimer = () => {
    if (stepTimerRef.current) {
      clearTimeout(stepTimerRef.current);
      stepTimerRef.current = null;
    }
    setShowSteps(false);
  };

  const startStepProgress = (steps: { label: string; duration: number }[]) => {
    setShowSteps(true);
    setCurrentStepIdx(0);
    clearStepTimer();

    const advance = (idx: number) => {
      if (idx >= steps.length) return;
      setCurrentStepIdx(idx);
      stepTimerRef.current = setTimeout(() => {
        advance(idx + 1);
      }, steps[idx].duration);
    };

    advance(0);
  };

  const resetAll = () => {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem("ai_video_expert_session");
    setThreadId(null);
    setReviewState(null);
    setOneshotResult(null);
    setOneshotScenario("");
    setDisconnected(false);
    setStepByStepLabel(null);
    setStepByStepState(null);
    setShowStepByStep(false);
    setWorkflowConfig(null);
    setWorkflowLabel(null);
    setWorkflowState(null);
    setShowWorkflow(false);
    setCurrentGate(0);
    setSmartCreateLabel(null);
    setShowStageProgress(false);
    setMode("expert");
    setCompareVersions([]);
    setShowCompare(false);
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
      {showSplash && <SplashScreen onEnter={() => setShowSplash(false)} />}
      <div className={`min-h-screen bg-[var(--color-bg)] transition-opacity duration-700 ${showSplash ? 'opacity-0' : 'opacity-100'}`}>
        {/* Toast */}
        {toast && (
          <div
            className={`apple-toast apple-toast-${toast.type}`}
            onClick={() => setToast(null)}
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
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="apple-card px-8 py-8 flex flex-col items-center gap-5 w-full max-w-md mx-4">
              <div className="relative w-10 h-10">
                <svg className="animate-spin w-10 h-10" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="#e8e8ed" strokeWidth="3" />
                  <path d="M12 2a10 10 0 0 1 10 10" stroke="#7CB342" strokeWidth="3" strokeLinecap="round" />
                </svg>
              </div>
              <div className="text-center space-y-1">
                <p className="text-sm text-[#86868b]">{loadingText}</p>
                {showSteps && currentStepIdx < S1_STEPS.length && currentStepIdx >= 0 && (
                  <p className="text-base font-semibold text-[#1d1d1f]">
                    {S1_STEPS[currentStepIdx]?.label}
                  </p>
                )}
              </div>
              {showSteps && (
                <div className="w-full space-y-2">
                  <div className="h-1.5 w-full bg-[#f5f5f7] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#7CB342] rounded-full transition-all duration-700 ease-out"
                      style={{
                        width: `${Math.min(((currentStepIdx + 0.5) / S1_STEPS.length) * 100, 100)}%`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] text-[#aeaeb2]">
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
                        className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-medium transition-all duration-300 ${
                          done
                            ? "bg-[#7CB342]/10 text-[#7CB342]"
                            : active
                            ? "bg-[#7CB342] text-white shadow-sm ring-2 ring-[#7CB342]/20"
                            : "bg-[#f5f5f7] text-[#aeaeb2]"
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
            </div>
          </div>
        )}

        {/* Header */}
        <header className="sticky top-0 z-40 bg-[var(--color-bg)]/80 backdrop-blur-xl border-b border-[var(--color-border-light)]">
          <div className="max-w-5xl mx-auto px-4 h-12 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-lg bg-[#69FF68] flex items-center justify-center">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                  <path d="M8 5v14l11-7z" fill="white" />
                </svg>
              </div>
              <span className="text-sm font-semibold text-[#1d1d1f] tracking-tight">{t("app.title")}</span>
              <Nav />
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowAssetLibrary(true)}
                className="flex items-center gap-1.5 text-xs text-[#86868b] hover:text-[#1d1d1f] transition-colors px-3 py-1.5 rounded-lg hover:bg-[#e8e8ed]/50 cursor-pointer"
                title={t("app.assetLibrary")}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
                {t("app.assetLibrary")}
              </button>
              {(threadId || oneshotResult) && (
                <button
                  onClick={resetAll}
                  className="text-xs text-[#86868b] hover:text-[#1d1d1f] transition-colors px-3 py-1.5 rounded-lg hover:bg-[#e8e8ed]/50 cursor-pointer"
                >
                  {t("app.abandon")}
                </button>
              )}
            </div>
          </div>
        </header>

        <main className="max-w-5xl mx-auto px-4 py-6">
          {/* Stage 0: Home — Scene selection + form */}
          {stage === "home" && showSelector && (
            <div className="space-y-3">
              <SceneTabs
                activeScene={activeScene}
                onChange={setActiveScene}
                videoCounts={{ product_direct: 0, brand_campaign: 0, influencer_remix: 0 }}
              />
              <SceneForm
                scene={activeScene}
                onSubmit={handleSceneSubmit}
                loading={loading}
              />
            </div>
          )}

          {/* Stage 1: Recommend — AI recommendation panel */}
          {stage === "recommend" && configRef.current && (
            <RecommendPanel
              config={configRef.current}
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
          )}

          {/* Stage 2: Generate — pipeline execution view */}
          {stage === "generate" && mode === "expert" && (
            showCompare ? (
              <CompareView
                versions={compareVersions}
                selectedVersion={null}
                onSelect={(label) => {
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
                onPublish={(label) => {
                  // Placeholder for future publish flow
                }}
              />
            ) : showWorkflow && workflowLabel && currentGate >= 1 ? (
              workflowState ? (
                <GatePanel
                  key={`gate-${currentGate}`}
                  label={workflowLabel}
                  gateId={GATE_SEQUENCE[currentGate - 1]?.gateId || "gate_1_script"}
                  gateLabel={GATE_SEQUENCE[currentGate - 1]?.gateLabel || ""}
                  maxSelections={GATE_SEQUENCE[currentGate - 1]?.maxSelections || 1}
                  currentStep={currentGate}
                  totalSteps={GATE_SEQUENCE.length}
                  onApprove={async (selectedIds) => {
                    if (currentGate === GATE_SEQUENCE.length) {
                      // Gate 4 (final) approved — fetch final state and show CompareView
                      if (!workflowLabel) {
                        showToast(t("toast.execFailed"), "error");
                        return;
                      }
                      try {
                        showToast(t("gate.finalReview") + " approved — loading results...", "info");
                        const state = await fetchS1State(workflowLabel);
                        const versions = extractVersions(state);
                        setCompareVersions(versions);
                        setShowCompare(true);
                        setCurrentGate(0);
                        showToast(t("toast.workflowDone"), "success");
                      } catch (e: any) {
                        showToast(t("toast.execFailed") + `: ${e?.message || String(e)}`, "error");
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
          )}

          {stage === "generate" && mode === "smart" && smartCreateLabel && (
            <StageProgress
              label={smartCreateLabel}
              onComplete={(result) => {
                setOneshotResult(result);
                setOneshotScenario(activeScene === "brand_campaign" ? "brand_campaign" : "product_direct");
                setStage("result");
                setShowStageProgress(false);
              }}
            />
          )}

          {/* Stage 3: Result — one-shot result view */}
          {stage === "result" && oneshotResult && (
            <OneShotResultView
              scenario={oneshotScenario}
              result={oneshotResult}
              onReset={() => {
                resetAll();
                setStage("home");
              }}
            />
          )}

          {/* Existing pipeline views (backward-compatible) */}
          {showOneshot && (
            <OneShotResultView
              scenario={oneshotScenario}
              result={oneshotResult}
              onReset={resetAll}
            />
          )}

          {showStepByStep && stepByStepLabel && stepByStepState && (
            <StepByStepView
              label={stepByStepLabel}
              state={stepByStepState}
              onStepComplete={(newState) => setStepByStepState(newState)}
              onResume={(finalState) => {
                setStepByStepState(finalState);
                setShowStepByStep(false);
                setOneshotResult(finalState);
                setOneshotScenario("product_direct");
                showToast(t("toast.stepByStepDone"), "success");
              }}
              loading={loading}
            />
          )}

          {showWorkflow && workflowLabel && workflowState && (
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
          )}

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
                  <div className="apple-card p-4 mb-4 border-l-4 border-[#ff453a] bg-[#fff5f5]">
                    <p className="text-sm text-[#ff453a] font-medium">{t("app.backendDisconnected")}</p>
                  </div>
                )}
                {currentReview ? (
                  <ReviewPanel
                    currentReview={currentReview}
                    reviewState={reviewState!}
                    onAction={handleReview}
                    loading={loading}
                  />
                ) : (
                  <div className="apple-card p-6 text-center">
                    <div className="w-12 h-12 rounded-2xl bg-[#7CB342]/10 flex items-center justify-center mx-auto mb-3">
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="#7CB342" strokeWidth="2" />
                        <path d="M12 6v6l4 2" stroke="#7CB342" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                    </div>
                    <p className="text-sm text-[#86868b]">{t("app.waitingReview")}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Fallback: if nothing matches, recover to home stage */}
          {!showSelector && !showOneshot && !showStepByStep && !showWorkflow && !showCompletion && !showReview && (
            <div className="apple-card p-8 text-center space-y-3">
              <p className="text-sm text-[#86868b]">{t("app.pageLoading")}</p>
              <button
                onClick={() => { setStage("home"); setThreadId(null); setShowSplash(false); setShowWorkflow(false); }}
                className="apple-btn apple-btn-primary text-xs px-4 py-2"
              >
                {t("app.returnHome")}
              </button>
            </div>
          )}
        </main>

        {showAssetLibrary && (
          <AssetLibrary onClose={() => setShowAssetLibrary(false)} />
        )}
      </div>
    </>
  );
}
