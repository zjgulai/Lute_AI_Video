import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

async function loadApi() {
  vi.resetModules();
  return import("./api");
}

function clearCookie(name: string) {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
}

function readCookie(name: string): string | undefined {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : undefined;
}

function readRepoFile(path: string): string {
  return readFileSync(join(process.cwd(), "..", path), "utf8");
}

describe("API key storage fallback", () => {
  beforeEach(() => {
    localStorage.clear();
    clearCookie("ai_video_api_key");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    clearCookie("ai_video_api_key");
    localStorage.clear();
  });

  it("stores API keys in localStorage without duplicating into cookies when localStorage works", async () => {
    const api = await loadApi();

    api.setApiKey("tenant-key-local");

    expect(localStorage.getItem("ai_video_api_key")).toBe("tenant-key-local");
    expect(readCookie("ai_video_api_key")).toBeUndefined();
    expect(api.getApiKey()).toBe("tenant-key-local");
  });

  it("falls back to cookie storage when localStorage is unavailable", async () => {
    const setSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    const getSpy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    const api = await loadApi();

    api.setApiKey("tenant-key-cookie");

    expect(setSpy).toHaveBeenCalledWith("ai_video_api_key", "tenant-key-cookie");
    expect(readCookie("ai_video_api_key")).toBe("tenant-key-cookie");
    expect(api.getApiKey()).toBe("tenant-key-cookie");
    getSpy.mockRestore();
  });

  it("clears localStorage and cookie fallback when API key is set to blank", async () => {
    const api = await loadApi();
    api.setApiKey("tenant-key-to-clear");
    document.cookie = "ai_video_api_key=stale-cookie-key; path=/; SameSite=Lax";

    api.setApiKey("   ");

    expect(localStorage.getItem("ai_video_api_key")).toBeNull();
    expect(readCookie("ai_video_api_key")).toBeUndefined();
    expect(api.hasApiKey()).toBe(false);
  });

  it("masks API keys without exposing the full secret", async () => {
    const api = await loadApi();

    expect(api.maskApiKeyForDisplay("")).toBe("Not set");
    expect(api.maskApiKeyForDisplay("short")).toBe("Set");
    expect(api.maskApiKeyForDisplay("poyo_live_1234567890abcdef")).toBe("poyo····def");
    expect(api.maskApiKeyForDisplay("poyo_live_1234567890abcdef")).not.toContain("1234567890abc");
  });

  it("documents the API key storage fallback contract", () => {
    const contract = readRepoFile("configs/api-key-storage-fallback-contract.yaml");
    const runbook = readRepoFile("docs/runbooks/api-key-storage-fallback.md");

    for (const token of [
      "ai_video_api_key",
      "localStorage_primary",
      "cookie_fallback_only",
      "maskApiKeyForDisplay",
      "setApiKey_blank_clears_storage",
    ]) {
      expect(contract).toContain(token);
    }

    for (const token of [
      "npm test -- --run src/components/apiKeyStorage.test.ts",
      "localStorage",
      "cookie fallback",
      "不要记录完整 API key",
    ]) {
      expect(runbook).toContain(token);
    }
  });
});
