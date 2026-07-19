import { afterEach, describe, expect, it, vi } from "vitest";

async function loadApi() {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        url: "/api/media/renders/signed.mp4?token=abc&expires=2000000000&tenant=default&purpose=view",
        expires_in: 900,
      }),
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
  const api = await import("./api");
  api.resetApiConfig();
  api.setApiBase("/api");
  api.setDemoMode(false);
  return { api, fetchMock };
}

describe("media URL sanitizer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
    localStorage.clear();
    document.cookie = "ai_video_api_base=; Max-Age=0; path=/";
    document.cookie = "ai_video_demo_mode=; Max-Age=0; path=/";
  });

  it("rejects absolute URLs and dangerous schemes before building media src values", async () => {
    const { api } = await loadApi();

    expect(api.getMediaUrl("https://evil.example/clip.mp4")).toBe("");
    expect(api.getMediaUrl("//evil.example/clip.mp4")).toBe("");
    expect(api.getMediaUrl("javascript:alert(1)")).toBe("");
    expect(api.getMediaUrl("data:image/svg+xml,<svg></svg>")).toBe("");
    expect(api.getMediaUrl("blob:https://evil.example/id")).toBe("");
  });

  it("classifies only internal protected media paths for signing", async () => {
    const { api } = await loadApi();

    expect(api.isProtectedMediaPath("tenants/tenant-a/a.mp4")).toBe(true);
    expect(api.isProtectedMediaPath("renders/a.mp4")).toBe(true);
    expect(api.isProtectedMediaPath("/api/media/renders/a.mp4")).toBe(true);
    expect(api.isProtectedMediaPath("/api/media/brand_assets/momcozy/a.png")).toBe(false);
    expect(api.isProtectedMediaPath("/api/media/demo/a.mp4")).toBe(false);
    expect(api.isProtectedMediaPath("/portfolio/demo.mp4")).toBe(false);
    expect(api.isProtectedMediaPath("https://provider.example/preview.mp4")).toBe(false);
    expect(api.isProtectedMediaPath("//provider.example/preview.mp4")).toBe(false);
  });

  it("rejects traversal attempts before signing media URLs", async () => {
    const { api, fetchMock } = await loadApi();

    expect(api.getMediaUrl("../secret.mp4")).toBe("");
    expect(api.getMediaUrl("renders/%2e%2e/secret.mp4")).toBe("");
    expect(api.getMediaUrl("renders/%252e%252e/secret.mp4")).toBe("");
    expect(await api.getSignedMediaUrl("../secret.mp4")).toBe("");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps relative portfolio and existing media paths usable", async () => {
    const { api } = await loadApi();

    expect(api.getMediaUrl("/portfolio/demo.jpg")).toBe("/portfolio/demo.jpg");
    expect(api.getMediaUrl("/brand/momcozy-logo.svg")).toBe("/brand/momcozy-logo.svg");
    expect(api.getMediaUrl("/brand/../secret.svg")).toBe("");
    expect(api.getMediaUrl("/brand/%252e%252e/secret.svg")).toBe("");
    expect(api.getMediaUrl("/portfolio/%2e%2e/secret.jpg")).toBe("");
    expect(api.getMediaUrl("renders/s1_1700000000.mp4")).toBe("/api/media/renders/s1_1700000000.mp4");
    expect(api.getMediaUrl("/api/media/thumbnails/portfolio_posters/s1.jpg")).toBe(
      "/api/media/thumbnails/portfolio_posters/s1.jpg",
    );
  });

  it("preserves an allowed same-origin signed media URL", async () => {
    const { api } = await loadApi();
    const signed =
      "/api/media/tenants/tenant-a/pending_review/a.png?token=abc&expires=2000000000&tenant=tenant-a&purpose=view";

    expect(api.getMediaUrl(signed)).toBe(signed);
  });

  it("accepts strict browser-origin signed URLs when the API base is relative", async () => {
    const { api } = await loadApi();
    const relative =
      "/api/media/tenants/tenant-a/a.png?token=abc&expires=2000000000&tenant=tenant-a&purpose=view";
    const signed = `${window.location.origin}${relative}`;

    expect(api.getMediaUrl(signed)).toBe(signed);
    expect(api.getMediaUrl(`${signed}&unknown=1`)).toBe("");
    expect(api.getMediaUrl(signed.replace("token=abc", "token=abc&token=def"))).toBe("");
    expect(api.getMediaUrl(`${signed}#fragment`)).toBe("");
    expect(api.getMediaUrl(`http://user:pass@${window.location.host}${relative}`)).toBe("");
    expect(api.getMediaUrl(`https://evil.example${relative}`)).toBe("");
  });

  it("classifies runtime, safe external, and invalid preview URLs without fallback", async () => {
    const { api } = await loadApi();
    const validSigned =
      `${window.location.origin}/api/media/tenants/tenant-a/a.mp4?token=abc&expires=2000000000&tenant=tenant-a&purpose=view`;
    const invalidSigned = `${validSigned}&redirect=https://evil.example`;

    expect(api.resolveMediaPreview("renders/a.mp4")).toEqual({
      kind: "runtime",
      url: "/api/media/renders/a.mp4",
    });
    expect(api.resolveMediaPreview("/portfolio/demo.mp4")).toEqual({
      kind: "runtime",
      url: "/portfolio/demo.mp4",
    });
    expect(api.resolveMediaPreview("/brand/demo.mp4")).toEqual({
      kind: "runtime",
      url: "/brand/demo.mp4",
    });
    expect(api.resolveMediaPreview(validSigned)).toEqual({ kind: "runtime", url: validSigned });
    expect(api.resolveMediaPreview("https://provider.example/preview.mp4?job=1")).toEqual({
      kind: "external",
      url: "https://provider.example/preview.mp4?job=1",
    });
    for (const invalid of [
      invalidSigned,
      validSigned.replace("token=abc", "token=abc&token=def"),
      `${validSigned}#fragment`,
      "http://user:pass@provider.example/preview.mp4",
      "//provider.example/preview.mp4",
      "javascript:alert(1)",
      "data:video/mp4;base64,AAAA",
      "/unknown/preview.mp4",
    ]) {
      expect(api.resolveMediaPreview(invalid), invalid).toEqual({ kind: "invalid", url: "" });
    }
  });

  it("never downgrades rejected browser or configured-origin URLs to external previews", async () => {
    const { api } = await loadApi();
    const query = "?token=abc&expires=2000000000&tenant=tenant-a&purpose=view";
    const browserOrigin = window.location.origin;
    const browserOriginVariants = [
      `${browserOrigin}/api/%6dedia/tenants/tenant-a/a.mp4${query}`,
      `${browserOrigin}/api/media%2Ftenants%2Ftenant-a%2Fa.mp4${query}`,
      `${browserOrigin}//api/media/tenants/tenant-a/a.mp4${query}`,
      `${browserOrigin}/noncanonical/preview.mp4`,
    ];

    for (const value of browserOriginVariants) {
      expect(api.resolveMediaPreview(value), value).toEqual({ kind: "invalid", url: "" });
    }

    api.setApiBase("http://localhost:8001");
    for (const value of [
      ...browserOriginVariants,
      `http://localhost:8001/api/%6dedia/tenants/tenant-a/a.mp4${query}`,
      `http://localhost:8001/api/media%2Ftenants%2Ftenant-a%2Fa.mp4${query}`,
      `http://localhost:8001//api/media/tenants/tenant-a/a.mp4${query}`,
      "http://localhost:8001/noncanonical/preview.mp4",
    ]) {
      expect(api.resolveMediaPreview(value), value).toEqual({ kind: "invalid", url: "" });
    }

    expect(api.resolveMediaPreview("https://provider.example/api/%6dedia/preview.mp4")).toEqual({
      kind: "external",
      url: "https://provider.example/api/%6dedia/preview.mp4",
    });
  });

  it("rejects signed media URLs with unknown or duplicate query parameters", async () => {
    const { api } = await loadApi();

    expect(
      api.getMediaUrl(
        "/api/media/a.png?token=abc&expires=2000000000&tenant=default&purpose=view&redirect=https://evil.example",
      ),
    ).toBe("");
    expect(
      api.getMediaUrl(
        "/api/media/a.png?token=abc&token=def&expires=2000000000&tenant=default&purpose=view",
      ),
    ).toBe("");
  });

  it("does not fall back to an unsigned protected URL when signing fails", async () => {
    const { api } = await loadApi();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 403 }));

    expect(await api.getSignedMediaUrl("tenants/tenant-a/a.png")).toBe("");
  });

  it("requests and validates a purpose-bound signed media URL", async () => {
    const { api, fetchMock } = await loadApi();
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          url: "/api/media/tenants/tenant-a/a.mp4?token=abc&expires=2000000000&tenant=tenant-a&purpose=download",
          expires_in: 900,
        }),
      ),
    );

    await expect(api.getSignedMediaUrl("tenants/tenant-a/a.mp4", "download")).resolves.toContain(
      "purpose=download",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/media/sign?path=tenants%2Ftenant-a%2Fa.mp4&purpose=download"),
      expect.objectContaining({ headers: expect.objectContaining({ "X-API-Key": expect.any(String) }) }),
    );
  });

  it("keeps configured absolute API media URLs internal and signed", async () => {
    const { api, fetchMock } = await loadApi();
    api.setApiBase("http://localhost:8001");
    const relativeSigned =
      "/api/media/tenants/tenant-a/a.mp4?token=abc&expires=2000000000&tenant=tenant-a&purpose=view";
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ url: relativeSigned, expires_in: 900 })),
    );

    const signed = await api.getSignedMediaUrl("tenants/tenant-a/a.mp4");
    expect(signed).toBe(`http://localhost:8001${relativeSigned}`);
    expect(api.getMediaUrl(signed)).toBe(signed);
    expect(api.isProtectedMediaPath("tenants/tenant-a/a.mp4")).toBe(true);
    expect(
      api.getMediaUrl(
        "https://evil.example/api/media/a.mp4?token=abc&expires=2000000000&tenant=tenant-a&purpose=view",
      ),
    ).toBe("");
  });

  it("rejects malformed signing responses", async () => {
    const { api, fetchMock } = await loadApi();
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          url: "/api/media/tenants/tenant-a/a.png?token=abc&expires=2000000000&tenant=tenant-a&purpose=view&extra=1",
        }),
      ),
    );
    await expect(api.getSignedMediaUrl("tenants/tenant-a/a.png")).resolves.toBe("");

    fetchMock.mockResolvedValueOnce(new Response("not-json"));
    await expect(api.getSignedMediaUrl("tenants/tenant-a/a.png")).resolves.toBe("");
  });
});
