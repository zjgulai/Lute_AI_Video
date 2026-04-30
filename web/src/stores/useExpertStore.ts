import { create } from "zustand";
import type { Version } from "@/components/CompareView";

interface ExpertState {
  currentGate: number;
  currentStepIdx: number;
  showSteps: boolean;
  showStageProgress: boolean;
  compareVersions: Version[];
  showCompare: boolean;

  setCurrentGate: (gate: number) => void;
  setCurrentStepIdx: (idx: number) => void;
  setShowSteps: (v: boolean) => void;
  setShowStageProgress: (v: boolean) => void;
  setCompareVersions: (versions: Version[]) => void;
  setShowCompare: (v: boolean) => void;
  resetExpert: () => void;
}

export const useExpertStore = create<ExpertState>((set) => ({
  currentGate: 0,
  currentStepIdx: 0,
  showSteps: false,
  showStageProgress: false,
  compareVersions: [],
  showCompare: false,

  setCurrentGate: (currentGate) => set({ currentGate }),
  setCurrentStepIdx: (currentStepIdx) => set({ currentStepIdx }),
  setShowSteps: (showSteps) => set({ showSteps }),
  setShowStageProgress: (showStageProgress) => set({ showStageProgress }),
  setCompareVersions: (compareVersions) => set({ compareVersions }),
  setShowCompare: (showCompare) => set({ showCompare }),
  resetExpert: () =>
    set({
      currentGate: 0,
      currentStepIdx: 0,
      showSteps: false,
      showStageProgress: false,
      compareVersions: [],
      showCompare: false,
    }),
}));
