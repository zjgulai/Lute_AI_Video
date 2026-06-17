import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import DashboardPage from "./page";

const fetchDashboardOverview = vi.fn();
const hasApiKey = vi.fn();

vi.mock("@/components/api", () => ({
  hasApiKey: () => hasApiKey(),
  getApiKey: () => "",
  setApiKey: vi.fn(),
  apiFetch: vi.fn(),
  fetchDashboardOverview: (...args: unknown[]) => fetchDashboardOverview(...args),
}));

async function flushEffects() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function renderDashboardPage() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  act(() => {
    root.render(
      <I18nProvider>
        <DashboardPage />
      </I18nProvider>,
    );
  });

  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("app-locale", "en");
    hasApiKey.mockReturnValue(true);
    fetchDashboardOverview.mockResolvedValue({
      data: [],
      videos: [],
      scenarios: [],
      platforms: [],
    });
  });

  it("renders PerformanceDashboard through a direct read-only route", async () => {
    const { container, cleanup } = renderDashboardPage();
    await flushEffects();

    expect(container.textContent).toContain("Performance Dashboard");
    expect(container.textContent).toContain("No data yet");
    expect(fetchDashboardOverview).toHaveBeenCalledWith(undefined, undefined, 30);

    cleanup();
  });
});
