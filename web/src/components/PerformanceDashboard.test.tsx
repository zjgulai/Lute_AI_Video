import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import PerformanceDashboard from "./PerformanceDashboard";

const fetchDashboardOverview = vi.fn();

vi.mock("./api", () => ({
  fetchDashboardOverview: (...args: unknown[]) => fetchDashboardOverview(...args),
}));

async function flushEffects() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function renderPerformanceDashboard(props: React.ComponentProps<typeof PerformanceDashboard> = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  act(() => {
    root.render(
      <I18nProvider>
        <PerformanceDashboard {...props} />
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

describe("PerformanceDashboard response contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("app-locale", "en");
  });

  it("renders the empty state when dashboard overview provides frontend fields", async () => {
    fetchDashboardOverview.mockResolvedValue({
      data: [],
      videos: [],
      scenarios: [],
      platforms: [],
    });

    const { container, cleanup } = renderPerformanceDashboard();
    await flushEffects();

    expect(container.textContent).toContain("Performance Dashboard");
    expect(container.textContent).toContain("No data yet");
    expect(container.textContent).not.toContain("Failed");
    expect(fetchDashboardOverview).toHaveBeenCalledWith(undefined, undefined, 30);

    cleanup();
  });
});
