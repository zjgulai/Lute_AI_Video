import { afterEach, describe, expect, it, vi } from "vitest";

async function loadApi() {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ url: "/api/media/renders/signed.mp4" })));
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

    expect(api.getMediaUrl("renders/s1_1700000000.mp4")).toBe("/api/media/renders/s1_1700000000.mp4");
    expect(api.getMediaUrl("/api/media/thumbnails/portfolio_posters/s1.jpg")).toBe(
      "/api/media/thumbnails/portfolio_posters/s1.jpg",
    );
  });
});
