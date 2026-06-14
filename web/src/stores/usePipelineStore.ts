import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ReviewState } from "@/components/types";
import {
  PIPELINE_STORE_PERSIST_VERSION,
  createSafeJSONStorage,
  migratePipelineStorePersistence,
  partializePipelineStorePersistence,
} from "./persistence";
import type { PersistedPipelineState } from "./persistence";

export interface ActivePipeline {
  label: string;
  scenario: string;
  startedAt: number;
  scene?: string;
}

/** Shape of a pipeline oneshot/fast-mode result. */
export interface PipelineResult {
  video_path?: string;
  poster_path?: string;
  duration_ms?: number;
  model_info?: Record<string, string>;
  timing?: Record<string, number>;
  error?: string;
  [key: string]: unknown;
}

/** Shape of step-by-step execution state. */
export interface StepByStepState {
  label?: string;
  scenario?: string;
  steps?: Record<string, unknown>;
  current_step?: string | null;
  mode?: string;
  gates?: Record<string, unknown>;
  pipeline_degraded?: boolean;
  degraded_reason?: string | null;
  [key: string]: unknown;
}

/** Per-scenario workflow configuration. */
export interface WorkflowConfig {
  scene?: string;
  scenario?: string;
  brand_mode?: boolean;
  product_catalog?: Record<string, unknown>;
  brand_package?: Record<string, unknown>;
  video_duration?: number;
  continuity_mode?: boolean | string;
  continuity_required?: boolean;
  reference_image_url?: string;
  source_video_url?: string;
  character_reference_url?: string;
  target_platforms?: string[];
  enable_media_synthesis?: boolean;
  [key: string]: unknown;
}

/** Running workflow execution state. */
export interface WorkflowState {
  label?: string;
  scenario?: string;
  steps?: Record<string, unknown>;
  current_step?: string | null;
  status?: string;
  pipeline_degraded?: boolean;
  degraded_reason?: string | null;
  soft_degraded_reasons?: Record<string, unknown>[];
  errors?: string[];
  [key: string]: unknown;
}

interface PipelineState {
  threadId: string | null;
  reviewState: ReviewState | null;
  oneshotResult: PipelineResult | null;
  oneshotScenario: string;
  stepByStepLabel: string | null;
  stepByStepState: StepByStepState | null;
  showStepByStep: boolean;
  smartCreateLabel: string | null;
  workflowConfig: WorkflowConfig | null;
  workflowLabel: string | null;
  workflowState: WorkflowState | null;
  showWorkflow: boolean;
  workflowRerenderKey: number;
  currentStepIdx: number;
  showSteps: boolean;
  activePipeline: ActivePipeline | null;
  dismissedPipelineLabels: string[];

  setThreadId: (id: string | null) => void;
  setReviewState: (state: ReviewState | null) => void;
  setOneshotResult: (result: PipelineResult | null) => void;
  setOneshotScenario: (scenario: string) => void;
  setStepByStepLabel: (label: string | null) => void;
  setStepByStepState: (state: StepByStepState | null) => void;
  setShowStepByStep: (v: boolean) => void;
  setSmartCreateLabel: (label: string | null) => void;
  setWorkflowConfig: (config: WorkflowConfig | null) => void;
  setWorkflowLabel: (label: string | null) => void;
  setWorkflowState: (state: WorkflowState | null) => void;
  setShowWorkflow: (v: boolean) => void;
  setWorkflowRerenderKey: (key: number) => void;
  setCurrentStepIdx: (idx: number) => void;
  setShowSteps: (v: boolean) => void;
  startActivePipeline: (p: ActivePipeline) => void;
  clearActivePipeline: () => void;
  dismissPipeline: (label: string) => void;
  resetWorkflow: () => void;
  resetAll: () => void;
}

export const usePipelineStore = create<PipelineState>()(
  persist<PipelineState, [], [], PersistedPipelineState>(
    (set) => ({
      threadId: null,
      reviewState: null,
      oneshotResult: null,
      oneshotScenario: "",
      stepByStepLabel: null,
      stepByStepState: null,
      showStepByStep: false,
      smartCreateLabel: null,
      workflowConfig: null,
      workflowLabel: null,
      workflowState: null,
      showWorkflow: false,
      workflowRerenderKey: 0,
      currentStepIdx: 0,
      showSteps: false,
      activePipeline: null,
      dismissedPipelineLabels: [],

      setThreadId: (threadId) => set({ threadId }),
      setReviewState: (reviewState) => set({ reviewState }),
      setOneshotResult: (oneshotResult) => set({ oneshotResult }),
      setOneshotScenario: (oneshotScenario) => set({ oneshotScenario }),
      setStepByStepLabel: (stepByStepLabel) => set({ stepByStepLabel }),
      setStepByStepState: (stepByStepState) => set({ stepByStepState }),
      setShowStepByStep: (showStepByStep) => set({ showStepByStep }),
      setSmartCreateLabel: (smartCreateLabel) => set({ smartCreateLabel }),
      setWorkflowConfig: (workflowConfig) => set({ workflowConfig }),
      setWorkflowLabel: (workflowLabel) => set({ workflowLabel }),
      setWorkflowState: (workflowState) => set({ workflowState }),
      setShowWorkflow: (showWorkflow) => set({ showWorkflow }),
      setWorkflowRerenderKey: (workflowRerenderKey) => set({ workflowRerenderKey }),
      setCurrentStepIdx: (currentStepIdx) => set({ currentStepIdx }),
      setShowSteps: (showSteps) => set({ showSteps }),
      startActivePipeline: (p) => set({ activePipeline: p }),
      clearActivePipeline: () => set({ activePipeline: null }),
      dismissPipeline: (label) =>
        set((s) => ({
          dismissedPipelineLabels: s.dismissedPipelineLabels.includes(label)
            ? s.dismissedPipelineLabels
            : [...s.dismissedPipelineLabels.slice(-9), label],
        })),
      resetWorkflow: () =>
        set({
          workflowConfig: null,
          workflowLabel: null,
          workflowState: null,
          showWorkflow: false,
        }),
      resetAll: () =>
        set({
          threadId: null,
          reviewState: null,
          oneshotResult: null,
          oneshotScenario: "",
          stepByStepLabel: null,
          stepByStepState: null,
          showStepByStep: false,
          smartCreateLabel: null,
          workflowConfig: null,
          workflowLabel: null,
          workflowState: null,
          showWorkflow: false,
          workflowRerenderKey: 0,
          currentStepIdx: 0,
          showSteps: false,
          activePipeline: null,
        }),
    }),
    {
      name: "ai-video-pipeline-store",
      storage: createSafeJSONStorage<PersistedPipelineState>(() => localStorage),
      version: PIPELINE_STORE_PERSIST_VERSION,
      migrate: migratePipelineStorePersistence,
      partialize: partializePipelineStorePersistence,
    },
  ),
);
