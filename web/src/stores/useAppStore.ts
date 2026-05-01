import { create } from "zustand";
import { logStateChange } from "@/components/api";

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
  resetApp: () => void;
}

// 带日志的 setter 包装器 — 只记录关键 state 变化
function loggedSet(set: any, get: any) {
  return (patch: any) => {
    const prev = get();
    set(patch);
    const next = get();
    // 只记录关键字段的变化
    const trackedKeys = ["stage", "activeScene", "mode", "loading", "disconnected", "showSettings"];
    for (const key of trackedKeys) {
      if (key in patch && prev[key] !== next[key]) {
        logStateChange("AppStore", key, prev[key], next[key]);
      }
    }
  };
}

export const useAppStore = create<AppState>((set, get) => {
  const lset = loggedSet(set, get);
  return {
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

    setStage: (stage) => lset({ stage }),
    setActiveScene: (activeScene) => lset({ activeScene }),
    setMode: (mode) => lset({ mode }),
    setPipelineMode: (pipelineMode) => lset({ pipelineMode }),
    setVideoDuration: (videoDuration) => lset({ videoDuration }),
    setLoading: (loading) => lset({ loading }),
    setLoadingText: (loadingText) => lset({ loadingText }),
    showToast: (message, type) => {
      lset({ toast: { message, type } });
      setTimeout(() => set({ toast: null }), 4000);
    },
    clearToast: () => set({ toast: null }),
    setDisconnected: (disconnected) => lset({ disconnected }),
    setShowSettings: (showSettings) => lset({ showSettings }),
    setShowAssetLibrary: (showAssetLibrary) => set({ showAssetLibrary }),
    setShowSplash: (showSplash) => set({ showSplash }),
    resetApp: () =>
      lset({
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
      }),
  };
});
