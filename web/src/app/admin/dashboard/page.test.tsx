import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import AdminDashboardPage from "./page";

const adminFetchJson = vi.fn();
vi.mock("@/components/api", async () => {
  const actual = await vi.importActual<typeof import("@/components/api")>("@/components/api");
  return {
    ...actual,
    adminFetchJson: (...args: unknown[]) => adminFetchJson(...args),
  };
});

const SAMPLE_DATA = {
  tenant_count: 7,
  tenant_count_today: 1,
  pipeline_runs_today: { total: 42, success: 38, failed: 2, running: 2 },
  error_rate_24h: 0.05,
  recent_errors: [
    {
      id: "err-1",
      tenant_id: "acme",
      scenario: "s1",
      error_code: "POYO_REJECTED",
      message: "content moderation failed",
      created_at: "2026-05-17T10:00:00Z",
    },
  ],
};

function render() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<AdminDashboardPage />);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("AdminDashboardPage", () => {
  beforeEach(() => {
    adminFetchJson.mockReset();
  });

  it("renders loading skeleton on mount", () => {
    adminFetchJson.mockReturnValueOnce(new Promise(() => {}));
    const { container, cleanup } = render();
    expect(container.querySelector('[aria-busy="true"]')).toBeTruthy();
    cleanup();
  });

  it("renders dashboard data after successful fetch", async () => {
    adminFetchJson.mockResolvedValueOnce(SAMPLE_DATA);
    const { container, cleanup } = render();
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(adminFetchJson).toHaveBeenCalledWith("/api/admin/dashboard/summary");
    const text = container.textContent || "";
    expect(text).toMatch(/7|tenant/i);
    cleanup();
  });

  it("renders error state when fetch fails", async () => {
    adminFetchJson.mockRejectedValueOnce(new Error("network down"));
    const { container, cleanup } = render();
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(container.textContent || "").toMatch(/failed/i);
    cleanup();
  });
});
