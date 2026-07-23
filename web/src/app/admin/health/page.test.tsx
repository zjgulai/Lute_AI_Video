import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import AdminHealthPage from "./page";
import { I18nProvider } from "@/i18n/I18nProvider";

const adminFetchJson = vi.fn();
vi.mock("@/components/api", async () => {
  const actual = await vi.importActual<typeof import("@/components/api")>("@/components/api");
  return {
    ...actual,
    adminFetchJson: (...args: unknown[]) => adminFetchJson(...args),
  };
});

const SAMPLE_STATUS = {
  checked_at: "2026-05-17T12:00:00Z",
  services: {
    postgres: { status: "healthy", latency_ms: 4 },
    deepseek: { status: "healthy", latency_ms: 250, available: true },
  },
};

const SAMPLE_HISTORY = { checks: [] };

function render() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<I18nProvider><AdminHealthPage /></I18nProvider>);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("AdminHealthPage", () => {
  beforeEach(() => {
    localStorage.setItem("app-locale", "en");
    adminFetchJson.mockReset();
  });

  it("renders data after successful fetches", async () => {
    adminFetchJson
      .mockResolvedValueOnce(SAMPLE_STATUS)
      .mockResolvedValueOnce(SAMPLE_HISTORY);
    const { container, cleanup } = render();
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(adminFetchJson).toHaveBeenCalledWith("/api/admin/health/status");
    expect(adminFetchJson).toHaveBeenCalledWith("/api/admin/health/history?hours=24");
    const text = container.textContent || "";
    expect(text).toMatch(/postgres|healthy/i);
    cleanup();
  });

  it("renders error state when fetch fails", async () => {
    adminFetchJson.mockRejectedValueOnce(new Error("backend down"));
    const { container, cleanup } = render();
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(container.textContent || "").toMatch(/failed/i);
    cleanup();
  });

  it("localizes status, checked time, and history labels in Chinese", async () => {
    localStorage.setItem("app-locale", "zh");
    adminFetchJson
      .mockResolvedValueOnce({
        ...SAMPLE_STATUS,
        services: { postgres: { status: "degraded", latency_ms: 4 } },
      })
      .mockResolvedValueOnce({
        checks: [{
          checked_at: "2026-05-17T11:00:00Z",
          services: { postgres: { status: "healthy", latency_ms: 4 } },
        }],
      });
    const { container, cleanup } = render();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

    expect(container.textContent).toContain("降级");
    expect(container.textContent).toContain("上次检查");
    expect(container.textContent).toContain("健康检查历史（24 小时）");
    expect(container.textContent).toContain("时间");
    expect(container.querySelector('[aria-label="PostgreSQL: 健康"]')).toBeTruthy();
    cleanup();
  });
});
