import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/i18n/I18nProvider";

vi.mock("./api", () => ({
  fetchDistribution: vi.fn(),
  fetchOutput: vi.fn(),
  downloadJson: vi.fn(),
  publishContent: vi.fn(),
  fetchPublishStatus: vi.fn(),
}));

import DistributionView from "./DistributionView";
import InsightReport from "./InsightReport";
import { fetchDistribution } from "./api";

async function renderView(ui: React.ReactNode) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<I18nProvider>{ui}</I18nProvider>);
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

describe("critical result views i18n", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("app-locale", "en");
  });

  it("renders DistributionView chrome from the English translation map", async () => {
    vi.mocked(fetchDistribution).mockResolvedValue({
      distribution_plans: [
        {
          brief_id: "brief-1",
          script_id: "script-1",
          title: "Momcozy launch",
          posts: [{ platform: "tiktok", post_body: "Launch post" }],
        },
      ],
    } as never);

    const { container, cleanup } = await renderView(
      <DistributionView threadId="thread-i18n" onRestart={vi.fn()} />,
    );
    try {
      expect(container.textContent).toContain("Pipeline Complete");
      expect(container.textContent).toContain("All content generated, ready for platform distribution");
      expect(container.textContent).not.toContain("全流程完成");
    } finally {
      cleanup();
    }
  });

  it("renders InsightReport headings and recommendations in English", async () => {
    const { container, cleanup } = await renderView(
      <InsightReport
        scenario="product_direct"
        result={{
          scenario: "product_direct",
          video_duration: 30,
          briefs: [{ product_name: "Momcozy M9", video_type: "product_seed" }],
          scripts: [{ product_name: "Momcozy M9" }],
          audit_report: { overall_score: 0.9, overall_status: "PASS" },
        }}
      />,
    );
    try {
      expect(container.textContent).toContain("AI Summary");
      expect(container.textContent).toContain("Next Steps");
      expect(container.textContent).toContain("View Detailed Data");
      expect(container.textContent).not.toContain("下一步建议");
    } finally {
      cleanup();
    }
  });
});
