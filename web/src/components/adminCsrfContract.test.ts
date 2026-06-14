import { afterEach, describe, expect, it, vi } from "vitest";

async function loadApiWithFetch() {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const api = await import("./api");
  return { api, fetchMock };
}

describe("admin CSRF contract", () => {
  afterEach(() => {
    document.cookie = "admin_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("adds X-CSRF-Token from admin_csrf cookie for mutating admin requests", async () => {
    document.cookie = "admin_csrf=csrf-token-123; path=/";
    const { api, fetchMock } = await loadApiWithFetch();

    await api.adminFetch("/api/admin/tenants", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": "must-not-forward",
      },
      body: JSON.stringify({ tenant_id: "demo-tenant" }),
    });

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = init.headers as Record<string, string>;

    expect(init.credentials).toBe("include");
    expect(headers["X-CSRF-Token"]).toBe("csrf-token-123");
    expect(headers["X-API-Key"]).toBeUndefined();
  });

  it("does not attach X-CSRF-Token to read-only admin requests", async () => {
    document.cookie = "admin_csrf=csrf-token-123; path=/";
    const { api, fetchMock } = await loadApiWithFetch();

    await api.adminFetch("/api/admin/auth/session");

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = init.headers as Record<string, string>;

    expect(init.credentials).toBe("include");
    expect(headers["X-CSRF-Token"]).toBeUndefined();
  });
});
