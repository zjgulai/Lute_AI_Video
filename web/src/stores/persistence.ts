import type { PersistStorage, StateStorage, StorageValue } from "zustand/middleware";

export const APP_STORE_PERSIST_VERSION = 1;
export const PIPELINE_STORE_PERSIST_VERSION = 1;
const MAX_DISMISSED_PIPELINE_LABELS = 10;

export interface PersistedAppState {
  mode: "expert" | "smart";
  pipelineMode: "auto" | "step_by_step";
  videoDuration: number;
}

export interface PersistedActivePipeline {
  label: string;
  scenario: string;
  startedAt: number;
  scene?: string;
}

export interface PersistedPipelineState {
  activePipeline: PersistedActivePipeline | null;
  dismissedPipelineLabels: string[];
}

const DEFAULT_APP_STATE: PersistedAppState = {
  mode: "expert",
  pipelineMode: "step_by_step",
  videoDuration: 30,
};

const DEFAULT_PIPELINE_STATE: PersistedPipelineState = {
  activePipeline: null,
  dismissedPipelineLabels: [],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function unwrapPersistedState(value: unknown): unknown {
  if (isRecord(value) && isRecord(value.state)) return value.state;
  return value;
}

function sanitizeVideoDuration(value: unknown): number {
  if (!Number.isFinite(value) || typeof value !== "number") return DEFAULT_APP_STATE.videoDuration;
  if (value <= 0 || value > 300) return DEFAULT_APP_STATE.videoDuration;
  return Math.round(value);
}

function sanitizeDismissedLabels(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const labels: string[] = [];
  const seen = new Set<string>();
  for (const item of value) {
    if (typeof item !== "string" || item.length === 0 || seen.has(item)) continue;
    labels.push(item);
    seen.add(item);
  }
  return labels.slice(-MAX_DISMISSED_PIPELINE_LABELS);
}

function sanitizeActivePipeline(value: unknown): PersistedActivePipeline | null {
  if (!isRecord(value)) return null;
  const { label, scenario, startedAt, scene } = value;
  if (typeof label !== "string" || label.length === 0) return null;
  if (typeof scenario !== "string" || scenario.length === 0) return null;
  if (typeof startedAt !== "number" || !Number.isFinite(startedAt) || startedAt <= 0) return null;

  return {
    label,
    scenario,
    startedAt,
    ...(typeof scene === "string" && scene.length > 0 ? { scene } : {}),
  };
}

export function migrateAppStorePersistence(persistedState: unknown, version: number): PersistedAppState {
  void version;
  const state = unwrapPersistedState(persistedState);
  if (!isRecord(state)) return { ...DEFAULT_APP_STATE };

  return {
    mode: state.mode === "smart" || state.mode === "expert" ? state.mode : DEFAULT_APP_STATE.mode,
    pipelineMode:
      state.pipelineMode === "auto" || state.pipelineMode === "step_by_step"
        ? state.pipelineMode
        : DEFAULT_APP_STATE.pipelineMode,
    videoDuration: sanitizeVideoDuration(state.videoDuration),
  };
}

export function migratePipelineStorePersistence(
  persistedState: unknown,
  version: number,
): PersistedPipelineState {
  void version;
  const state = unwrapPersistedState(persistedState);
  if (!isRecord(state)) return { ...DEFAULT_PIPELINE_STATE };

  return {
    activePipeline: sanitizeActivePipeline(state.activePipeline),
    dismissedPipelineLabels: sanitizeDismissedLabels(state.dismissedPipelineLabels),
  };
}

export function partializeAppStorePersistence(state: {
  mode: unknown;
  pipelineMode: unknown;
  videoDuration: unknown;
}): PersistedAppState {
  return migrateAppStorePersistence(state, APP_STORE_PERSIST_VERSION);
}

export function partializePipelineStorePersistence(state: {
  activePipeline: unknown;
  dismissedPipelineLabels: unknown;
}): PersistedPipelineState {
  return migratePipelineStorePersistence(state, PIPELINE_STORE_PERSIST_VERSION);
}

export function createSafeJSONStorage<S>(
  getStorage: () => StateStorage,
): PersistStorage<S> | undefined {
  let storage: StateStorage;
  try {
    storage = getStorage();
  } catch {
    return undefined;
  }

  const parse = (name: string, raw: string | null): StorageValue<S> | null => {
    if (raw === null) return null;
    try {
      return JSON.parse(raw) as StorageValue<S>;
    } catch {
      storage.removeItem(name);
      return null;
    }
  };

  return {
    getItem: (name) => {
      const raw = storage.getItem(name);
      if (raw instanceof Promise) {
        return raw.then((value) => parse(name, value)).catch(() => {
          storage.removeItem(name);
          return null;
        });
      }
      return parse(name, raw);
    },
    setItem: (name, value) => storage.setItem(name, JSON.stringify(value)),
    removeItem: (name) => storage.removeItem(name),
  };
}
