import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import AdminLogsPage from "./page";

const adminFetchJson = vi.fn();
vi.mock("@/components/api", async () => {
  const actual = await vi.importActual<typeof import("@/components/api")>("@/components/api");
  return {
    ...actual,
    adminFetchJson: (...args: unknown[]) => adminFetchJson(...args),
  };
});

const SAMPLE = {
  items: [
    {
      id: "log-1",
      tenant_id: "acme",
      scenario: "s1",
      error_code: "TIMEOUT",
      message: "DeepSeek timeout after 30s",
      created_at: "2026-05-17T11:00:00Z",
    },
  ],
  total: 1,
};

function render() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<AdminLogsPage />);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("AdminLogsPage", () => {
  beforeEach(() => {
    adminFetchJson.mockReset();
  });

  it("renders log entries after fetch", async () => {
    adminFetchJson.mockResolvedValueOnce(SAMPLE);
    const { container, cleanup } = render();
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(adminFetchJson).toHaveBeenCalled();
    const callPath = (adminFetchJson.mock.calls[0]?.[0] || "") as string;
    expect(callPath).toContain("/api/admin/logs");
    const text = container.textContent || "";
    expect(text).toMatch(/acme|TIMEOUT|deepseek/i);
    cleanup();
  });

  it("renders error state when fetch fails", async () => {
    adminFetchJson.mockRejectedValueOnce(new Error("backend 500"));
    const { container, cleanup } = render();
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(container.textContent || "").toMatch(/failed/i);
    cleanup();
  });
});
