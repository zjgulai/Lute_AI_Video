import { create } from "zustand";
import type { ReviewState } from "@/components/types";

interface PipelineState {
  threadId: string | null;
  reviewState: ReviewState | null;
  oneshotResult: any | null;
  oneshotScenario: string;
  stepByStepLabel: string | null;
  stepByStepState: any | null;
  showStepByStep: boolean;
  smartCreateLabel: string | null;
  workflowConfig: any | null;
  workflowLabel: string | null;
  workflowState: any | null;
  showWorkflow: boolean;
  workflowRerenderKey: number;
  currentStepIdx: number;
  showSteps: boolean;

  setThreadId: (id: string | null) => void;
  setReviewState: (state: ReviewState | null) => void;
  setOneshotResult: (result: any | null) => void;
  setOneshotScenario: (scenario: string) => void;
  setStepByStepLabel: (label: string | null) => void;
  setStepByStepState: (state: any | null) => void;
  setShowStepByStep: (v: boolean) => void;
  setSmartCreateLabel: (label: string | null) => void;
  setWorkflowConfig: (config: any | null) => void;
  setWorkflowLabel: (label: string | null) => void;
  setWorkflowState: (state: any | null) => void;
  setShowWorkflow: (v: boolean) => void;
  setWorkflowRerenderKey: (key: number) => void;
  setCurrentStepIdx: (idx: number) => void;
  setShowSteps: (v: boolean) => void;
  resetWorkflow: () => void;
  resetAll: () => void;
}

export const usePipelineStore = create<PipelineState>((set) => ({
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
    }),
}));
