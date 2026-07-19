import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getMediaUrl, getSignedMediaUrl } from "@/components/api";
import { useSignedMediaUrl, type SignedMediaState } from "./useSignedMediaUrl";

vi.mock("@/components/api", () => ({
  getMediaUrl: vi.fn(),
  getSignedMediaUrl: vi.fn(),
}));

const signer = vi.mocked(getSignedMediaUrl);
const sanitizer = vi.mocked(getMediaUrl);

type HookHarnessProps = {
  filePath: string;
  purpose?: "view" | "download";
  onState: (state: SignedMediaState) => void;
};

function HookHarness({ filePath, purpose, onState }: HookHarnessProps) {
  onState(useSignedMediaUrl(filePath, purpose));
  return null;
}

function renderSignedMediaHook(filePath: string, purpose?: "view" | "download") {
  const container = document.createElement("div");
  const root = createRoot(container);
  let current: SignedMediaState = { url: "", loading: true, error: null };

  const render = (nextPath: string, nextPurpose = purpose) => {
    act(() => {
      root.render(createElement(HookHarness, {
        filePath: nextPath,
        purpose: nextPurpose,
        onState: (state) => {
          current = state;
        },
      }));
    });
  };

  render(filePath, purpose);
  return {
    get result() {
      return current;
    },
    rerender: render,
    unmount() {
      act(() => root.unmount());
    },
  };
}

async function flushPromises() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("useSignedMediaUrl", () => {
  beforeEach(() => {
    signer.mockReset();
    sanitizer.mockReset();
    sanitizer.mockImplementation((path: string) => {
      if (path.startsWith("/portfolio/")) return path;
      if (path.startsWith("/api/media/")) return path;
      return path ? `/api/media/${path}` : "";
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps protected media absent until a signed URL is returned", async () => {
    let resolveSigner!: (url: string) => void;
    signer.mockReturnValue(
      new Promise((resolve) => {
        resolveSigner = resolve;
      }),
    );
    const hook = renderSignedMediaHook("tenants/tenant-a/a.png");

    expect(hook.result).toEqual({ url: "", loading: true, error: null });

    await act(async () => {
      resolveSigner(
        "/api/media/tenants/tenant-a/a.png?token=t&expires=2000000000&tenant=tenant-a&purpose=view",
      );
    });

    expect(hook.result.loading).toBe(false);
    expect(hook.result.url).toContain("token=t");
    hook.unmount();
  });

  it("stays fail-closed when the signer rejects", async () => {
    signer.mockResolvedValue("");
    const hook = renderSignedMediaHook("tenants/tenant-a/a.png");

    await flushPromises();

    expect(hook.result.url).toBe("");
    expect(hook.result.loading).toBe(false);
    expect(hook.result.error).toBeTruthy();
    hook.unmount();
  });

  it("refreshes a signed URL thirty seconds before expiry", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2030-01-01T00:00:00Z"));
    const firstExpiry = Math.floor(Date.now() / 1000) + 31;
    signer
      .mockResolvedValueOnce(
        `/api/media/tenants/tenant-a/a.png?token=first&expires=${firstExpiry}&tenant=tenant-a&purpose=view`,
      )
      .mockResolvedValueOnce(
        "/api/media/tenants/tenant-a/a.png?token=second&expires=2000000000&tenant=tenant-a&purpose=view",
      );
    const hook = renderSignedMediaHook("tenants/tenant-a/a.png");
    await flushPromises();

    expect(hook.result.url).toContain("token=first");
    expect(signer).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });

    expect(signer).toHaveBeenCalledTimes(2);
    expect(hook.result.url).toContain("token=second");
    hook.unmount();
  });

  it("immediately refreshes an existing signed URL with less than thirty seconds remaining", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2030-01-01T00:00:00Z"));
    const oldExpiry = Math.floor(Date.now() / 1000) + 20;
    const oldUrl =
      `/api/media/tenants/tenant-a/a.png?token=old&expires=${oldExpiry}&tenant=tenant-a&purpose=view`;
    const refreshedUrl =
      "/api/media/tenants/tenant-a/a.png?token=new&expires=2000000000&tenant=tenant-a&purpose=view";
    signer.mockResolvedValue(refreshedUrl);

    const hook = renderSignedMediaHook(oldUrl);
    expect(hook.result.url).toBe(oldUrl);
    expect(hook.result.loading).toBe(true);
    await flushPromises();

    expect(signer).toHaveBeenCalledWith("/api/media/tenants/tenant-a/a.png", "view");
    expect(hook.result.url).toBe(refreshedUrl);
    hook.unmount();
  });

  it("keeps hard expiry while an immediate refresh remains pending", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2030-01-01T00:00:00Z"));
    const oldExpiry = Math.floor(Date.now() / 1000) + 20;
    const oldUrl =
      `/api/media/tenants/tenant-a/a.png?token=old&expires=${oldExpiry}&tenant=tenant-a&purpose=view`;
    signer.mockReturnValue(new Promise(() => undefined));

    const hook = renderSignedMediaHook(oldUrl);
    expect(hook.result.url).toBe(oldUrl);
    expect(signer).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_001);
    });

    expect(hook.result.url).toBe("");
    expect(hook.result.error).toBeTruthy();
    hook.unmount();
  });

  it("does not loop when the signer returns a valid short-lived URL", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2030-01-01T00:00:00Z"));
    const shortExpiry = Math.floor(Date.now() / 1000) + 20;
    const shortUrl =
      `/api/media/tenants/tenant-a/a.png?token=short&expires=${shortExpiry}&tenant=tenant-a&purpose=view`;
    signer.mockResolvedValue(shortUrl);

    const hook = renderSignedMediaHook("tenants/tenant-a/a.png");
    await flushPromises();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(signer).toHaveBeenCalledTimes(1);
    expect(hook.result.url).toBe(shortUrl);
    expect(hook.result.loading).toBe(false);
    hook.unmount();
  });

  it("removes the old URL if a refresh is still pending at expiry", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2030-01-01T00:00:00Z"));
    const firstExpiry = Math.floor(Date.now() / 1000) + 31;
    signer
      .mockResolvedValueOnce(
        `/api/media/tenants/tenant-a/a.png?token=first&expires=${firstExpiry}&tenant=tenant-a&purpose=view`,
      )
      .mockReturnValueOnce(new Promise(() => undefined));
    const hook = renderSignedMediaHook("tenants/tenant-a/a.png");
    await flushPromises();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(signer).toHaveBeenCalledTimes(2);
    expect(hook.result.url).toContain("token=first");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_001);
    });

    expect(hook.result.url).toBe("");
    expect(hook.result.error).toBeTruthy();
    hook.unmount();
  });

  it("ignores stale signing results after the path changes", async () => {
    let resolveFirst!: (url: string) => void;
    signer
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
      )
      .mockResolvedValueOnce(
        "/api/media/tenants/tenant-a/b.png?token=b&expires=2000000000&tenant=tenant-a&purpose=view",
      );
    const hook = renderSignedMediaHook("tenants/tenant-a/a.png");

    hook.rerender("tenants/tenant-a/b.png");
    await flushPromises();
    expect(hook.result.url).toContain("token=b");

    await act(async () => {
      resolveFirst(
        "/api/media/tenants/tenant-a/a.png?token=a&expires=2000000000&tenant=tenant-a&purpose=view",
      );
    });

    expect(hook.result.url).toContain("token=b");
    hook.unmount();
  });

  it("bypasses signing for static portfolio assets", () => {
    const hook = renderSignedMediaHook("/portfolio/demo.jpg");

    expect(hook.result).toEqual({ url: "/portfolio/demo.jpg", loading: false, error: null });
    expect(signer).not.toHaveBeenCalled();
    hook.unmount();
  });

  it("forwards download purpose to the signer", async () => {
    signer.mockResolvedValue(
      "/api/media/tenants/tenant-a/a.mp4?token=t&expires=2000000000&tenant=tenant-a&purpose=download",
    );
    const hook = renderSignedMediaHook("tenants/tenant-a/a.mp4", "download");

    await flushPromises();

    expect(signer).toHaveBeenCalledWith("tenants/tenant-a/a.mp4", "download");
    hook.unmount();
  });

  it("supports protected media served from the configured absolute API origin", async () => {
    const signed =
      "http://localhost:8001/api/media/tenants/tenant-a/a.mp4?token=t&expires=2000000000&tenant=tenant-a&purpose=view";
    sanitizer.mockImplementation((path: string) => {
      if (path.startsWith("http://localhost:8001/api/media/")) return path;
      return path ? `http://localhost:8001/api/media/${path}` : "";
    });
    signer.mockResolvedValue(signed);
    const hook = renderSignedMediaHook("tenants/tenant-a/a.mp4");

    await flushPromises();

    expect(signer).toHaveBeenCalledWith("tenants/tenant-a/a.mp4", "view");
    expect(hook.result.url).toBe(signed);
    hook.unmount();
  });
});
