import { afterEach, describe, expect, it, vi } from "vitest";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    statusText: status === 401 ? "Unauthorized" : status === 429 ? "Too Many Requests" : "Unprocessable Entity",
    headers: { "content-type": "application/json", ...headers },
  });
}

async function loadApiWithResponse(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  const api = await import("./api");
  api.setApiLogging(false);
  return { api, fetchMock };
}

function storedApiKey(): string | null {
  return localStorage.getItem("ai_video_api_key");
}

describe("apiFetch error normalization", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.resetModules();
    localStorage.clear();
  });

  it("surfaces 401 from S1 step-by-step start as ApiError", async () => {
    window.history.pushState({}, "", "/admin/probe");
    const { api } = await loadApiWithResponse(jsonResponse(401, { detail: "Invalid API key" }));

    await expect(api.startS1StepByStep({ product_name: "Pump" })).rejects.toMatchObject({
      name: "ApiError",
      message: "Invalid API key",
      info: {
        status: 401,
        message: "Invalid API key",
        fieldErrors: {},
        retryAfterSec: null,
      },
    });
  });

  it("clears the configured key for normal non-auth-probe 401 responses", async () => {
    window.history.pushState({}, "", "/?session_expired=1");
    const { api } = await loadApiWithResponse(jsonResponse(401, { detail: "Invalid API key" }));
    api.setApiKey("prod_key_for_test");

    const res = await api.apiFetch("/scenario/s1", { method: "POST" });

    expect(res.status).toBe(401);
    expect(storedApiKey()).toBeNull();
  });

  it("does not clear the configured key for toolbox read-only 401 responses", async () => {
    window.history.pushState({}, "", "/toolbox/product-image");
    const { api } = await loadApiWithResponse(jsonResponse(401, { detail: "Invalid API key" }));
    api.setApiKey("prod_key_for_test");

    await expect(api.fetchToolboxRuns({ toolId: "product-image", limit: 5 })).rejects.toMatchObject({
      name: "ApiError",
      info: {
        status: 401,
      },
    });

    expect(storedApiKey()).toBe("prod_key_for_test");
  });

  it("preserves 422 field errors from S1 step execution", async () => {
    const { api } = await loadApiWithResponse(
      jsonResponse(422, {
        detail: [
          { loc: ["body", "label"], msg: "field required", type: "value_error.missing" },
          { loc: ["body", "step_name"], msg: "unknown step", type: "value_error" },
        ],
      }),
    );

    await expect(api.runS1Step("", "unknown")).rejects.toMatchObject({
      name: "ApiError",
      info: {
        status: 422,
        fieldErrors: {
          label: "field required",
          step_name: "unknown step",
        },
      },
    });
  });

  it("preserves 429 retry metadata from S1 resume", async () => {
    const { api } = await loadApiWithResponse(
      jsonResponse(429, { detail: "Too many requests", retry_after_sec: 42 }),
    );

    await expect(api.resumeS1("s1-demo")).rejects.toMatchObject({
      name: "ApiError",
      message: "Too many requests",
      info: {
        status: 429,
        retryAfterSec: 42,
      },
    });
  });

  it.each(["POST", "PUT", "PATCH", "DELETE"])(
    "does not retry mutation method %s after a 500 response",
    async (method) => {
      vi.useFakeTimers();
      const { api, fetchMock } = await loadApiWithResponse(
        jsonResponse(500, { detail: "ambiguous server failure" }),
      );

      const request = api.apiFetch("/scenario/s1", { method });
      await vi.runAllTimersAsync();
      const response = await request;

      expect(response.status).toBe(500);
      expect(fetchMock).toHaveBeenCalledTimes(1);
    },
  );

  it("cannot opt a mutation into retries through the internal maxRetries override", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(500, { detail: "ambiguous server failure" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setApiLogging(false);

    const request = api.apiFetch("/fast/submit", {
      method: "POST",
      maxRetries: 5,
    });
    await vi.runAllTimersAsync();

    expect((await request).status).toBe(500);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("retains one retry for idempotent GET after a 500 response", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(500, { detail: "temporary" }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setApiLogging(false);

    const request = api.apiFetch("/scenario/s1/status/example", { method: "GET" });
    await vi.runAllTimersAsync();
    const response = await request;

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("gives the retried GET attempt a fresh timeout after an initial 500", async () => {
    vi.useFakeTimers();
    let retrySignal: AbortSignal | undefined;
    let rejection: unknown;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(500, { detail: "temporary" }))
      .mockImplementationOnce((_input: RequestInfo | URL, init?: RequestInit) => {
        retrySignal = init?.signal ?? undefined;
        return new Promise<Response>((_resolve, reject) => {
          const rejectOnAbort = () => reject(
            retrySignal?.reason ?? new DOMException("Request timeout", "TimeoutError"),
          );
          if (retrySignal?.aborted) {
            rejectOnAbort();
          } else {
            retrySignal?.addEventListener("abort", rejectOnAbort, { once: true });
          }
        });
      });
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setApiLogging(false);

    const request = api.apiFetch("/assets/example", { method: "GET" });
    void request.catch((error: unknown) => {
      rejection = error;
    });

    await vi.advanceTimersByTimeAsync(1_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(retrySignal?.aborted).toBe(false);

    await vi.advanceTimersByTimeAsync(30_001);

    expect(retrySignal?.aborted).toBe(true);
    expect(rejection).toMatchObject({ name: "TimeoutError" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry a caller AbortError even for GET", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError"));
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setApiLogging(false);

    const controller = new AbortController();
    await expect(
      api.apiFetch("/scenario/s1/status/example", {
        method: "GET",
        signal: controller.signal,
      }),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not retry a GET response when the caller owns the abort signal", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(500, { detail: "temporary" }));
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setApiLogging(false);

    const controller = new AbortController();
    const request = api.apiFetch("/assets/example", {
      method: "GET",
      signal: controller.signal,
    });
    await vi.runAllTimersAsync();

    expect((await request).status).toBe(500);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("retains the default timeout when a caller signal is present", async () => {
    vi.useFakeTimers();
    let fetchSignal: AbortSignal | undefined;
    let rejection: unknown;
    const fetchMock = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) => {
        fetchSignal = init?.signal ?? undefined;
        return new Promise<Response>((_resolve, reject) => {
          const rejectOnAbort = () => reject(
            fetchSignal?.reason ?? new DOMException("Request timeout", "TimeoutError"),
          );
          if (fetchSignal?.aborted) {
            rejectOnAbort();
          } else {
            fetchSignal?.addEventListener("abort", rejectOnAbort, { once: true });
          }
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setApiLogging(false);

    const callerController = new AbortController();
    const request = api.apiFetch("/assets/example", {
      method: "GET",
      signal: callerController.signal,
    });
    void request.catch((error: unknown) => {
      rejection = error;
    });

    await vi.advanceTimersByTimeAsync(30_001);

    expect(callerController.signal.aborted).toBe(false);
    expect(fetchSignal?.aborted).toBe(true);
    expect(rejection).toMatchObject({ name: "TimeoutError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("relays a caller abort immediately without waiting for the timeout", async () => {
    vi.useFakeTimers();
    let fetchSignal: AbortSignal | undefined;
    const fetchMock = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) => {
        fetchSignal = init?.signal ?? undefined;
        return new Promise<Response>((_resolve, reject) => {
          const rejectOnAbort = () => reject(
            fetchSignal?.reason ?? new DOMException("Aborted", "AbortError"),
          );
          fetchSignal?.addEventListener("abort", rejectOnAbort, { once: true });
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setApiLogging(false);

    const callerController = new AbortController();
    const request = api.apiFetch("/assets/example", {
      method: "GET",
      signal: callerController.signal,
    });
    callerController.abort(new DOMException("Cancelled by caller", "AbortError"));

    await expect(request).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchSignal?.aborted).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends Idempotency-Key on scenario submit and never retries the POST", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(500, { detail: { code: "ambiguous_gateway_failure" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setApiLogging(false);

    await expect(
      api.submitScenario("s1", { product_catalog: { name: "fixture" } }, {
        idempotencyKey: "123e4567-e89b-42d3-a456-426614174000",
      }),
    ).rejects.toMatchObject({ info: { status: 500 } });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Idempotency-Key")).toBe(
      "123e4567-e89b-42d3-a456-426614174000",
    );
  });

  it("uses authenticated GET readback with the key in a header, never in the URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        resource_type: "scenario",
        resource_id: "s1_original",
        scenario: "s1",
        status: "running",
        submit_response: { label: "s1_original", status: "queued" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setApiLogging(false);
    const key = "123e4567-e89b-42d3-a456-426614174000";

    const result = await api.getSubmissionByIdempotencyKey(key);

    expect(result.resource_id).toBe("s1_original");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/submissions/idempotency");
    expect(url).not.toContain(key);
    expect((init.method || "GET").toUpperCase()).toBe("GET");
    expect(new Headers(init.headers).get("Idempotency-Key")).toBe(key);
  });

  it("uses the short async-submit timeout without retrying the mutation", async () => {
    vi.useFakeTimers();
    let requestSignal: AbortSignal | undefined;
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      requestSignal = init?.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        const rejectOnAbort = () => reject(
          requestSignal?.reason ?? new DOMException("Request timeout", "TimeoutError"),
        );
        requestSignal?.addEventListener("abort", rejectOnAbort, { once: true });
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setApiLogging(false);

    const request = api.submitScenario("s1", { product_catalog: { name: "fixture" } }, {
      idempotencyKey: "123e4567-e89b-42d3-a456-426614174000",
    });
    let rejection: unknown;
    void request.catch((error: unknown) => {
      rejection = error;
    });

    await vi.advanceTimersByTimeAsync(15_001);

    expect(requestSignal?.aborted).toBe(true);
    expect(rejection).toMatchObject({ name: "TimeoutError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("extracts a stable nested detail code for ambiguity classification", async () => {
    const { api } = await loadApiWithResponse(
      jsonResponse(503, {
        detail: {
          code: "idempotency_store_unavailable",
          message: "Durable submission store unavailable",
        },
      }),
    );

    const info = await api.parseApiError(
      jsonResponse(503, {
        detail: {
          code: "idempotency_store_unavailable",
          message: "Durable submission store unavailable",
        },
      }),
    );

    expect(info).toMatchObject({
      status: 503,
      code: "idempotency_store_unavailable",
      message: "Durable submission store unavailable",
    });
  });

  it("does not add an inner apiFetch retry to a scheduled idempotency readback", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(503, { detail: { code: "temporary_proxy_failure" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = await import("./api");
    api.setApiLogging(false);

    const request = api.getSubmissionByIdempotencyKey(
      "123e4567-e89b-42d3-a456-426614174000",
    );
    const assertion = expect(request).rejects.toMatchObject({ info: { status: 503 } });
    await vi.runAllTimersAsync();

    await assertion;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
