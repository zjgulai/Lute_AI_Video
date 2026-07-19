import type { PersistStorage, StateStorage, StorageValue } from "zustand/middleware";
import type { PendingSubmission } from "@/lib/idempotentSubmission";

export const APP_STORE_PERSIST_VERSION = 1;
export const PIPELINE_STORE_PERSIST_VERSION = 2;
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
  pendingSubmission: PendingSubmission | null;
}

const DEFAULT_APP_STATE: PersistedAppState = {
  mode: "expert",
  pipelineMode: "step_by_step",
  videoDuration: 30,
};

const DEFAULT_PIPELINE_STATE: PersistedPipelineState = {
  activePipeline: null,
  dismissedPipelineLabels: [],
  pendingSubmission: null,
};

const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/;
const PENDING_PHASES = new Set(["submitting", "recovering", "bound", "unknown"]);
const SCENARIOS = new Set(["s1", "s2", "s3", "s4", "s5"]);

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

function sanitizePendingSubmission(value: unknown): PendingSubmission | null {
  if (!isRecord(value)) return null;
  const {
    kind,
    scenario,
    idempotencyKey,
    createdAt,
    phase,
    resourceId,
  } = value;
  if (kind !== "scenario" && kind !== "fast") return null;
  if (kind === "scenario" && (typeof scenario !== "string" || !SCENARIOS.has(scenario))) {
    return null;
  }
  if (typeof idempotencyKey !== "string" || !IDEMPOTENCY_KEY_PATTERN.test(idempotencyKey)) {
    return null;
  }
  if (typeof createdAt !== "number" || !Number.isFinite(createdAt) || createdAt <= 0) {
    return null;
  }
  if (typeof phase !== "string" || !PENDING_PHASES.has(phase)) return null;
  if (resourceId !== undefined && (typeof resourceId !== "string" || resourceId.length === 0)) {
    return null;
  }
  if (phase === "bound" && typeof resourceId !== "string") return null;

  return {
    kind,
    ...(kind === "scenario" ? { scenario: scenario as PendingSubmission["scenario"] } : {}),
    idempotencyKey,
    createdAt,
    phase: phase as PendingSubmission["phase"],
    ...(typeof resourceId === "string" ? { resourceId } : {}),
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
    pendingSubmission: sanitizePendingSubmission(state.pendingSubmission),
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
  pendingSubmission: unknown;
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
