import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import OneShotResultView from "./OneShotResultView";

vi.mock("./DirectorPlayback", () => ({
  default: () => <div data-testid="director-playback" />,
}));

function renderResult(result: Record<string, unknown>) {
  localStorage.setItem("app-locale", "zh");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <OneShotResultView
          scenario="product_direct"
          result={result}
          onReset={() => undefined}
        />
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

describe("OneShotResultView lifecycle presentation", () => {
  it("renders completed_bounded as a distinct non-publishable state", () => {
    const { container, cleanup } = renderResult({
      status: "completed_bounded",
      lifecycle_status: "completed_bounded",
      completion_kind: "no_media",
      request_succeeded: true,
      success: false,
      full_media_success: false,
      pipeline_complete: false,
      publish_allowed: false,
      delivery_accepted: false,
      briefs: [],
      scripts: [],
    });

    expect(container.textContent).toContain("有界完成");
    expect(container.textContent).toContain("不可发布或交付");
    expect(container.textContent).not.toContain("生成出错");
    cleanup();
  });

  it("renders full pending-review output without publish or delivery action", () => {
    const { container, cleanup } = renderResult({
      status: "completed_full",
      lifecycle_status: "completed_full",
      completion_kind: "full_media",
      request_succeeded: true,
      success: true,
      full_media_success: true,
      pipeline_complete: true,
      publish_allowed: false,
      delivery_accepted: false,
      artifact_review_status: "pending_review",
      final_video_path: "tenants/a/pending_review/run/final.mp4",
      briefs: [],
      scripts: [],
    });

    expect(container.textContent).toContain("完整生成（待人工验收）");
    const classicButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("经典视图"),
    );
    act(() => classicButton?.click());
    expect(container.textContent).not.toContain("发布视频");
    cleanup();
  });
});
