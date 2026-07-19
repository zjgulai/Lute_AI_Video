export const DEFAULT_READBACK_OFFSETS_MS = [0, 1_000, 2_000, 5_000] as const;

export type SubmissionKind = "scenario" | "fast";
export type SubmissionScenario = "s1" | "s2" | "s3" | "s4" | "s5";
export type PendingSubmissionPhase =
  | "submitting"
  | "recovering"
  | "bound"
  | "unknown";

export interface PendingSubmission {
  kind: SubmissionKind;
  scenario?: SubmissionScenario;
  idempotencyKey: string;
  createdAt: number;
  phase: PendingSubmissionPhase;
  resourceId?: string;
}

export type SubmissionStatus =
  | "reserved"
  | "initializing"
  | "queued"
  | "running"
  | "completed"
  | "completed_bounded"
  | "completed_full"
  | "done"
  | "failed"
  | "error"
  | "recovery_required"
  | string;

export interface SubmissionReadback {
  resource_type: SubmissionKind;
  resource_id: string;
  scenario: SubmissionScenario | "fast";
  status: SubmissionStatus;
  submit_response: Record<string, unknown>;
  result_snapshot?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
}

export type SubmissionFailureClassification =
  | "ambiguous"
  | "conflict"
  | "definitive";

export type SubmissionResolution<TSubmit = SubmitResponseLike> =
  | {
      kind: "bound";
      pending: PendingSubmission;
      resourceId: string;
      status: SubmissionStatus;
      recovered: boolean;
      submitResponse?: TSubmit;
      readback?: SubmissionReadback;
    }
  | {
      kind: "recovery_required";
      pending: PendingSubmission;
      resourceId: string;
      status: "recovery_required";
      recovered: boolean;
      readback: SubmissionReadback;
    }
  | {
      kind: "unknown";
      pending: PendingSubmission;
      recovered: true;
    };

type SubmitResponseLike = {
  status?: unknown;
  label?: unknown;
  task_id?: unknown;
};

type SharedRecoveryOptions = {
  pending: PendingSubmission;
  persist: (pending: PendingSubmission) => void;
  readback: (idempotencyKey: string) => Promise<SubmissionReadback>;
  sleep?: (delayMs: number) => Promise<void>;
  readbackOffsetsMs?: readonly number[];
  signal?: AbortSignal;
};

export type RecoverPendingSubmissionOptions = SharedRecoveryOptions;

export type SubmitIdempotentlyOptions<TSubmit extends SubmitResponseLike> =
  SharedRecoveryOptions & {
    submit: (idempotencyKey: string) => Promise<TSubmit>;
  };

const BINDABLE_STATUSES = new Set<SubmissionStatus>([
  "queued",
  "running",
  "completed",
  "completed_bounded",
  "completed_full",
  "done",
  "failed",
  "error",
]);

function defaultSleep(delayMs: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, delayMs));
}

function getApiErrorInfo(error: unknown): {
  status?: number;
  code?: string | null;
} {
  if (!error || typeof error !== "object") return {};
  const info = (error as { info?: unknown }).info;
  if (!info || typeof info !== "object") return {};
  const rawStatus = (info as { status?: unknown }).status;
  const rawCode = (info as { code?: unknown }).code;
  return {
    ...(typeof rawStatus === "number" ? { status: rawStatus } : {}),
    ...(typeof rawCode === "string" || rawCode === null
      ? { code: rawCode }
      : {}),
  };
}

function getErrorName(error: unknown): string {
  if (!error || typeof error !== "object") return "";
  const name = (error as { name?: unknown }).name;
  return typeof name === "string" ? name : "";
}

function getErrorMessage(error: unknown): string {
  if (!error || typeof error !== "object") return "";
  const message = (error as { message?: unknown }).message;
  return typeof message === "string" ? message : "";
}

export function classifySubmissionFailure(
  error: unknown,
): SubmissionFailureClassification {
  const { status, code } = getApiErrorInfo(error);
  if (status === 409) return "conflict";
  if (status === 503 && code === "idempotency_store_unavailable") {
    return "definitive";
  }
  if (status === 500 || status === 502 || status === 503 || status === 504) {
    return "ambiguous";
  }

  const name = getErrorName(error);
  if (["AbortError", "TimeoutError", "TypeError"].includes(name)) {
    return "ambiguous";
  }
  const message = getErrorMessage(error).toLowerCase();
  if (
    message.includes("failed to fetch")
    || message.includes("networkerror")
    || message.includes("network error")
  ) {
    return "ambiguous";
  }
  return "definitive";
}

export function createPendingSubmission({
  kind,
  scenario,
  now = Date.now,
  keyFactory = () => globalThis.crypto.randomUUID(),
}: {
  kind: SubmissionKind;
  scenario?: SubmissionScenario;
  now?: () => number;
  keyFactory?: () => string;
}): PendingSubmission {
  if (kind === "scenario" && !scenario) {
    throw new Error("Scenario submissions require a scenario");
  }
  return {
    kind,
    ...(kind === "scenario" ? { scenario } : {}),
    idempotencyKey: keyFactory(),
    createdAt: now(),
    phase: "submitting",
  };
}

function getResourceId(value: SubmitResponseLike): string | null {
  if (typeof value.label === "string" && value.label.length > 0) {
    return value.label;
  }
  if (typeof value.task_id === "string" && value.task_id.length > 0) {
    return value.task_id;
  }
  return null;
}

function getSubmissionStatus(value: SubmitResponseLike): SubmissionStatus {
  return typeof value.status === "string" ? value.status : "unknown";
}

function bindPending(
  pending: PendingSubmission,
  resourceId: string,
): PendingSubmission {
  return {
    ...pending,
    phase: "bound",
    resourceId,
  };
}

export async function recoverPendingSubmission({
  pending,
  persist,
  readback,
  sleep = defaultSleep,
  readbackOffsetsMs = DEFAULT_READBACK_OFFSETS_MS,
  signal,
}: RecoverPendingSubmissionOptions): Promise<SubmissionResolution> {
  const recovering: PendingSubmission = {
    ...pending,
    phase: "recovering",
  };
  persist(recovering);

  let previousOffset = 0;
  for (const rawOffset of readbackOffsetsMs) {
    if (signal?.aborted) break;
    const offset = Math.max(previousOffset, rawOffset);
    const delay = offset - previousOffset;
    if (delay > 0) await sleep(delay);
    if (signal?.aborted) break;
    previousOffset = offset;

    let snapshot: SubmissionReadback;
    try {
      snapshot = await readback(recovering.idempotencyKey);
    } catch {
      if (signal?.aborted) break;
      continue;
    }

    if (snapshot.status === "reserved" || snapshot.status === "initializing") {
      continue;
    }
    if (!snapshot.resource_id) continue;

    const bound = bindPending(recovering, snapshot.resource_id);
    if (snapshot.status === "recovery_required") {
      persist(bound);
      return {
        kind: "recovery_required",
        pending: bound,
        resourceId: snapshot.resource_id,
        status: "recovery_required",
        recovered: true,
        readback: snapshot,
      };
    }
    if (BINDABLE_STATUSES.has(snapshot.status)) {
      persist(bound);
      return {
        kind: "bound",
        pending: bound,
        resourceId: snapshot.resource_id,
        status: snapshot.status,
        recovered: true,
        readback: snapshot,
      };
    }
  }

  const unknown: PendingSubmission = {
    ...recovering,
    phase: "unknown",
  };
  persist(unknown);
  return { kind: "unknown", pending: unknown, recovered: true };
}

export async function submitIdempotently<
  TSubmit extends SubmitResponseLike,
>({
  pending,
  persist,
  submit,
  readback,
  sleep,
  readbackOffsetsMs,
  signal,
}: SubmitIdempotentlyOptions<TSubmit>): Promise<SubmissionResolution<TSubmit>> {
  const submitting: PendingSubmission = {
    ...pending,
    phase: "submitting",
  };
  // This call is intentionally synchronous and must complete before fetch starts.
  persist(submitting);

  let response: TSubmit;
  try {
    response = await submit(submitting.idempotencyKey);
  } catch (error) {
    const classification = classifySubmissionFailure(error);
    if (classification === "ambiguous") {
      return recoverPendingSubmission({
        pending: submitting,
        persist,
        readback,
        ...(sleep ? { sleep } : {}),
        ...(readbackOffsetsMs ? { readbackOffsetsMs } : {}),
        ...(signal ? { signal } : {}),
      }) as Promise<SubmissionResolution<TSubmit>>;
    }
    persist({ ...submitting, phase: "unknown" });
    throw error;
  }

  const status = getSubmissionStatus(response);
  const resourceId = getResourceId(response);
  if (
    !resourceId
    || status === "reserved"
    || status === "initializing"
    || (!BINDABLE_STATUSES.has(status) && status !== "recovery_required")
  ) {
    return recoverPendingSubmission({
      pending: submitting,
      persist,
      readback,
      ...(sleep ? { sleep } : {}),
      ...(readbackOffsetsMs ? { readbackOffsetsMs } : {}),
      ...(signal ? { signal } : {}),
    }) as Promise<SubmissionResolution<TSubmit>>;
  }

  const bound = bindPending(submitting, resourceId);
  persist(bound);
  if (status === "recovery_required") {
    return {
      kind: "recovery_required",
      pending: bound,
      resourceId,
      status: "recovery_required",
      recovered: false,
      readback: {
        resource_type: pending.kind,
        resource_id: resourceId,
        scenario: pending.kind === "fast" ? "fast" : pending.scenario ?? "s1",
        status: "recovery_required",
        submit_response: { ...response },
      },
    };
  }
  return {
    kind: "bound",
    pending: bound,
    resourceId,
    status,
    recovered: false,
    submitResponse: response,
  };
}
