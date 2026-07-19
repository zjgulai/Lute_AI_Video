import { describe, expect, it, vi } from "vitest";

import {
  DEFAULT_READBACK_OFFSETS_MS,
  classifySubmissionFailure,
  createPendingSubmission,
  recoverPendingSubmission,
  submitIdempotently,
  type PendingSubmission,
  type SubmissionReadback,
} from "./idempotentSubmission";

const KEY = "123e4567-e89b-42d3-a456-426614174000";

function scenarioPending(
  overrides: Partial<PendingSubmission> = {},
): PendingSubmission {
  return {
    kind: "scenario",
    scenario: "s1",
    idempotencyKey: KEY,
    createdAt: 1_700_000_000_000,
    phase: "submitting",
    ...overrides,
  };
}

function readback(
  status: SubmissionReadback["status"],
  resourceId = "s1_original",
): SubmissionReadback {
  return {
    resource_type: "scenario",
    resource_id: resourceId,
    scenario: "s1",
    status,
    submit_response: {
      label: resourceId,
      status,
      trace_id: "trace-safe",
    },
    result_snapshot: null,
    created_at: "2026-07-12T00:00:00Z",
    updated_at: "2026-07-12T00:00:01Z",
  };
}

describe("idempotent submission", () => {
  it("creates one opaque UUID key without retaining payload or credentials", () => {
    const pending = createPendingSubmission({
      kind: "scenario",
      scenario: "s3",
      now: () => 1234,
      keyFactory: () => KEY,
    });

    expect(pending).toEqual({
      kind: "scenario",
      scenario: "s3",
      idempotencyKey: KEY,
      createdAt: 1234,
      phase: "submitting",
    });
    expect(JSON.stringify(pending)).not.toContain("api_keys");
    expect(JSON.stringify(pending)).not.toContain("user_prompt");
  });

  it("persists the stable key synchronously before the only mutation POST", async () => {
    const events: string[] = [];
    const pending = scenarioPending();
    const persist = vi.fn((next: PendingSubmission) => {
      events.push(`persist:${next.phase}:${next.idempotencyKey}`);
    });
    const submit = vi.fn(async (key: string) => {
      events.push(`post:${key}`);
      return { label: "s1_original", status: "queued", trace_id: "trace-safe" };
    });

    const result = await submitIdempotently({
      pending,
      persist,
      submit,
      readback: vi.fn(),
    });

    expect(events[0]).toBe(`persist:submitting:${KEY}`);
    expect(events[1]).toBe(`post:${KEY}`);
    expect(submit).toHaveBeenCalledTimes(1);
    expect(result).toMatchObject({
      kind: "bound",
      resourceId: "s1_original",
      status: "queued",
      recovered: false,
    });
    expect(persist).toHaveBeenLastCalledWith(
      expect.objectContaining({
        idempotencyKey: KEY,
        phase: "bound",
        resourceId: "s1_original",
      }),
    );
  });

  it("uses GET readback at 0/1/2/5 seconds after an ambiguous network error and never posts twice", async () => {
    const submit = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    const get = vi
      .fn()
      .mockRejectedValueOnce(new Error("not visible yet"))
      .mockResolvedValueOnce(readback("initializing"))
      .mockResolvedValueOnce(readback("queued"));
    const sleep = vi.fn().mockResolvedValue(undefined);

    const result = await submitIdempotently({
      pending: scenarioPending(),
      persist: vi.fn(),
      submit,
      readback: get,
      sleep,
    });

    expect(DEFAULT_READBACK_OFFSETS_MS).toEqual([0, 1000, 2000, 5000]);
    expect(submit).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledTimes(3);
    expect(get).toHaveBeenNthCalledWith(1, KEY);
    expect(get).toHaveBeenNthCalledWith(2, KEY);
    expect(get).toHaveBeenNthCalledWith(3, KEY);
    expect(sleep.mock.calls.map(([delay]) => delay)).toEqual([1000, 1000]);
    expect(result).toMatchObject({
      kind: "bound",
      resourceId: "s1_original",
      status: "queued",
      recovered: true,
    });
  });

  it("keeps reserved and initializing records on idempotency readback", async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(readback("reserved"))
      .mockResolvedValueOnce(readback("initializing"))
      .mockResolvedValueOnce(readback("running"));

    const result = await recoverPendingSubmission({
      pending: scenarioPending({ phase: "recovering" }),
      persist: vi.fn(),
      readback: get,
      sleep: vi.fn().mockResolvedValue(undefined),
    });

    expect(get).toHaveBeenCalledTimes(3);
    expect(result).toMatchObject({
      kind: "bound",
      status: "running",
      resourceId: "s1_original",
    });
  });

  it("preserves an unknown pending record after bounded readback exhaustion", async () => {
    const submit = vi.fn().mockRejectedValue(new DOMException("timeout", "TimeoutError"));
    const get = vi.fn().mockRejectedValue(new Error("not found"));
    const persist = vi.fn();
    const sleep = vi.fn().mockResolvedValue(undefined);

    const result = await submitIdempotently({
      pending: scenarioPending(),
      persist,
      submit,
      readback: get,
      sleep,
    });

    expect(submit).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledTimes(4);
    expect(sleep.mock.calls.map(([delay]) => delay)).toEqual([1000, 1000, 3000]);
    expect(result).toMatchObject({ kind: "unknown" });
    expect(persist).toHaveBeenLastCalledWith(
      expect.objectContaining({
        idempotencyKey: KEY,
        phase: "unknown",
      }),
    );
  });

  it("reload recovery is GET-only and binds the original Fast job", async () => {
    const pending: PendingSubmission = {
      kind: "fast",
      idempotencyKey: KEY,
      createdAt: 1_700_000_000_000,
      phase: "unknown",
    };
    const get = vi.fn().mockResolvedValue({
      ...readback("completed_full", "fast_original"),
      resource_type: "fast",
      scenario: "fast",
      result_snapshot: { status: "completed_full", success: true },
    });

    const result = await recoverPendingSubmission({
      pending,
      persist: vi.fn(),
      readback: get,
      sleep: vi.fn().mockResolvedValue(undefined),
    });

    expect(get).toHaveBeenCalledTimes(1);
    expect(result).toMatchObject({
      kind: "bound",
      resourceId: "fast_original",
      status: "completed_full",
      recovered: true,
    });
  });

  it("returns recovery_required without probing a potentially missing resource status", async () => {
    const get = vi.fn().mockResolvedValue(readback("recovery_required"));

    const result = await recoverPendingSubmission({
      pending: scenarioPending({ phase: "unknown" }),
      persist: vi.fn(),
      readback: get,
      sleep: vi.fn().mockResolvedValue(undefined),
    });

    expect(result).toMatchObject({
      kind: "recovery_required",
      resourceId: "s1_original",
      status: "recovery_required",
    });
  });

  it("treats conflict and fail-before-claim store unavailability as definitive", async () => {
    const conflict = {
      name: "ApiError",
      info: { status: 409, code: "idempotency_payload_conflict" },
    };
    const storeUnavailable = {
      name: "ApiError",
      info: { status: 503, code: "idempotency_store_unavailable" },
    };
    const proxyUnavailable = {
      name: "ApiError",
      info: { status: 503, code: null },
    };

    expect(classifySubmissionFailure(conflict)).toBe("conflict");
    expect(classifySubmissionFailure(storeUnavailable)).toBe("definitive");
    expect(classifySubmissionFailure(proxyUnavailable)).toBe("ambiguous");
    expect(classifySubmissionFailure(new TypeError("Failed to fetch"))).toBe("ambiguous");
    expect(classifySubmissionFailure(new DOMException("aborted", "AbortError"))).toBe("ambiguous");
  });

  it("does not perform readback or replace the key after a 409 conflict", async () => {
    const conflict = Object.assign(new Error("payload conflict"), {
      name: "ApiError",
      info: { status: 409, code: "idempotency_payload_conflict" },
    });
    const get = vi.fn();
    const persist = vi.fn();

    await expect(
      submitIdempotently({
        pending: scenarioPending(),
        persist,
        submit: vi.fn().mockRejectedValue(conflict),
        readback: get,
      }),
    ).rejects.toBe(conflict);

    expect(get).not.toHaveBeenCalled();
    expect(persist).toHaveBeenLastCalledWith(
      expect.objectContaining({
        idempotencyKey: KEY,
        phase: "unknown",
      }),
    );
  });

  it("preserves the pending key when readback is unauthorized for the current account", async () => {
    const unauthorized = Object.assign(new Error("Unauthorized"), {
      name: "ApiError",
      info: { status: 401, code: null },
    });
    const persist = vi.fn();

    const result = await recoverPendingSubmission({
      pending: scenarioPending({ phase: "bound", resourceId: "s1_original" }),
      persist,
      readback: vi.fn().mockRejectedValue(unauthorized),
      sleep: vi.fn().mockResolvedValue(undefined),
    });

    expect(result).toMatchObject({ kind: "unknown" });
    expect(persist).toHaveBeenLastCalledWith(expect.objectContaining({
      idempotencyKey: KEY,
      phase: "unknown",
      resourceId: "s1_original",
    }));
  });
});
