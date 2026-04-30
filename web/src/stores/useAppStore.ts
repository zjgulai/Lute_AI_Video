import { create } from "zustand";

export type Stage = "home" | "recommend" | "generate" | "result";
export type Mode = "expert" | "smart";
export type PipelineMode = "auto" | "step_by_step";

interface Toast {
  message: string;
  type: "success" | "error" | "info";
}

interface AppState {
  // Navigation
  stage: Stage;
  activeScene: string;
  mode: Mode;
  pipelineMode: PipelineMode;
  videoDuration: number;

  // UI
  loading: boolean;
  loadingText: string;
  toast: Toast | null;
  disconnected: boolean;
  showSettings: boolean;
  showAssetLibrary: boolean;
  showSplash: boolean;

  // Actions
  setStage: (stage: Stage) => void;
  setActiveScene: (scene: string) => void;
  setMode: (mode: Mode) => void;
  setPipelineMode: (mode: PipelineMode) => void;
  setVideoDuration: (d: number) => void;
  setLoading: (v: boolean) => void;
  setLoadingText: (t: string) => void;
  showToast: (message: string, type: Toast["type"]) => void;
  clearToast: () => void;
  setDisconnected: (v: boolean) => void;
  setShowSettings: (v: boolean) => void;
  setShowAssetLibrary: (v: boolean) => void;
  setShowSplash: (v: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  stage: "home",
  activeScene: "product_direct",
  mode: "expert",
  pipelineMode: "step_by_step",
  videoDuration: 30,

  loading: false,
  loadingText: "",
  toast: null,
  disconnected: false,
  showSettings: false,
  showAssetLibrary: false,
  showSplash: true,

  setStage: (stage) => set({ stage }),
  setActiveScene: (activeScene) => set({ activeScene }),
  setMode: (mode) => set({ mode }),
  setPipelineMode: (pipelineMode) => set({ pipelineMode }),
  setVideoDuration: (videoDuration) => set({ videoDuration }),
  setLoading: (loading) => set({ loading }),
  setLoadingText: (loadingText) => set({ loadingText }),
  showToast: (message, type) => {
    set({ toast: { message, type } });
    setTimeout(() => set({ toast: null }), 4000);
  },
  clearToast: () => set({ toast: null }),
  setDisconnected: (disconnected) => set({ disconnected }),
  setShowSettings: (showSettings) => set({ showSettings }),
  setShowAssetLibrary: (showAssetLibrary) => set({ showAssetLibrary }),
  setShowSplash: (showSplash) => set({ showSplash }),
}));
