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

describe("apiFetch error normalization", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
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
});
