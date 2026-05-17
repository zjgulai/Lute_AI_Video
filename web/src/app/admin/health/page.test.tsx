import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import AdminHealthPage from "./page";

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
    root.render(<AdminHealthPage />);
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
});
