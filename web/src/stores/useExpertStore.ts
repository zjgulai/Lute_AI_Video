import { create } from "zustand";
import type { Version } from "@/components/CompareView";

interface ExpertState {
  currentGate: number;
  showStageProgress: boolean;
  compareVersions: Version[];
  showCompare: boolean;

  setCurrentGate: (gate: number) => void;
  setShowStageProgress: (v: boolean) => void;
  setCompareVersions: (versions: Version[]) => void;
  setShowCompare: (v: boolean) => void;
  resetExpert: () => void;
}

export const useExpertStore = create<ExpertState>((set) => ({
  currentGate: 0,
  showStageProgress: false,
  compareVersions: [],
  showCompare: false,

  setCurrentGate: (currentGate) => set({ currentGate }),
  setShowStageProgress: (showStageProgress) => set({ showStageProgress }),
  setCompareVersions: (compareVersions) => set({ compareVersions }),
  setShowCompare: (showCompare) => set({ showCompare }),
  resetExpert: () =>
    set({
      currentGate: 0,
      showStageProgress: false,
      compareVersions: [],
      showCompare: false,
    }),
}));
