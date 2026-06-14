import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
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

const DETAIL = {
  ...SAMPLE.items[0],
  traceback: "Trace line 1\nTrace line 2",
};

async function flushEffects() {
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

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
    await flushEffects();
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
    await flushEffects();
    expect(container.textContent || "").toMatch(/failed/i);
    cleanup();
  });

  it("includes pagination + 24h time-range params in initial fetch URL", async () => {
    adminFetchJson.mockResolvedValueOnce(SAMPLE);
    const { cleanup } = render();
    await flushEffects();
    const callPath = (adminFetchJson.mock.calls[0]?.[0] || "") as string;
    expect(callPath).toMatch(/page=1/);
    expect(callPath).toMatch(/limit=50/);
    expect(callPath).toMatch(/from=\d{4}-\d{2}-\d{2}T/);
    cleanup();
  });

  it("opens log detail from keyboard and restores focus after Escape closes it", async () => {
    adminFetchJson.mockResolvedValueOnce(SAMPLE);
    adminFetchJson.mockResolvedValueOnce(DETAIL);
    const { container, cleanup } = render();
    await flushEffects();

    const row = container.querySelector(
      'tr[role="button"][aria-label="Open log detail for TIMEOUT"][tabindex="0"]',
    ) as HTMLTableRowElement | null;
    expect(row).toBeTruthy();
    if (!row) throw new Error("Expected keyboard-openable log row");

    row.focus();
    expect(document.activeElement).toBe(row);

    await act(async () => {
      row.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    await flushEffects();

    expect(adminFetchJson).toHaveBeenLastCalledWith("/api/admin/logs/log-1");
    const dialog = container.querySelector('[role="dialog"][aria-modal="true"]');
    expect(dialog?.getAttribute("aria-labelledby")).toBe("admin-log-detail-title");
    expect(dialog?.getAttribute("aria-describedby")).toBe("admin-log-detail-description");
    const closeButton = container.querySelector(
      'button[type="button"][aria-label="Close log detail"]',
    ) as HTMLButtonElement | null;
    expect(closeButton).toBeTruthy();
    expect(document.activeElement).toBe(closeButton);

    await act(async () => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    await flushEffects();

    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(row);

    adminFetchJson.mockResolvedValueOnce(DETAIL);
    await act(async () => {
      row.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
    });
    await flushEffects();

    expect(adminFetchJson).toHaveBeenLastCalledWith("/api/admin/logs/log-1");
    expect(container.querySelector('[role="dialog"][aria-modal="true"]')).toBeTruthy();
    cleanup();
  });

  it("documents the Admin Logs keyboard navigation contract", () => {
    const contract = readFileSync(
      join(process.cwd(), "..", "configs/admin-logs-keyboard-navigation-contract.yaml"),
      "utf8",
    );
    const runbook = readFileSync(
      join(process.cwd(), "..", "docs/runbooks/admin-logs-keyboard-navigation.md"),
      "utf8",
    );

    for (const token of [
      "row_role_button",
      "row_tabindex_zero",
      "enter_space_open_detail",
      "escape_closes_detail",
      "restore_focus_to_row",
    ]) {
      expect(contract).toContain(token);
    }

    for (const token of [
      "npm test -- --run src/app/admin/logs/page.test.tsx",
      "role=\"button\"",
      "Escape",
      "不触发生成接口",
    ]) {
      expect(runbook).toContain(token);
    }
  });
});
