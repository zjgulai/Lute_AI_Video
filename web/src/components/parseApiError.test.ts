import { describe, it, expect } from "vitest";
import { parseApiError } from "./api";

function mkRes(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "content-type": typeof body === "string" ? "text/plain" : "application/json", ...headers },
  });
}

describe("parseApiError", () => {
  it("extracts FastAPI 422 field-level errors with loc.body stripped", async () => {
    const res = mkRes(422, {
      detail: [
        { loc: ["body", "product_name"], msg: "field required", type: "value_error.missing" },
        { loc: ["body", "video_duration"], msg: "ensure value is at most 60", type: "value_error.number" },
      ],
    });
    const info = await parseApiError(res);
    expect(info.status).toBe(422);
    expect(info.fieldErrors).toEqual({
      product_name: "field required",
      video_duration: "ensure value is at most 60",
    });
    expect(info.message).toContain("product_name");
    expect(info.message).toContain("video_duration");
  });

  it("uses simple string detail when backend returns a plain message", async () => {
    const res = mkRes(422, { detail: "tenant_id is required" });
    const info = await parseApiError(res);
    expect(info.fieldErrors).toEqual({});
    expect(info.message).toBe("tenant_id is required");
  });

  it("extracts retry_after_sec from 429 body", async () => {
    const res = mkRes(429, { detail: "Too many requests. Please slow down.", retry_after_sec: 42 });
    const info = await parseApiError(res);
    expect(info.status).toBe(429);
    expect(info.retryAfterSec).toBe(42);
    expect(info.message).toBe("Too many requests. Please slow down.");
  });

  it("falls back to Retry-After header when body lacks retry_after_sec", async () => {
    const res = mkRes(429, { detail: "rate limited" }, { "Retry-After": "30" });
    const info = await parseApiError(res);
    expect(info.retryAfterSec).toBe(30);
  });

  it("survives non-JSON body and uses text preview", async () => {
    const res = mkRes(500, "Internal Server Error: traceback elided");
    const info = await parseApiError(res);
    expect(info.status).toBe(500);
    expect(info.message).toContain("Internal Server Error");
  });

  it("defaults to statusText when body is empty", async () => {
    const res = new Response("", { status: 504, statusText: "Gateway Timeout" });
    const info = await parseApiError(res);
    expect(info.status).toBe(504);
    expect(info.message).toBe("Gateway Timeout");
  });
});
