import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import ProductionJobLedgerViewer, {
  extractProductionJobRecords,
  type ProductionJobRecordView,
} from "./ProductionJobLedgerViewer";

function renderViewer(records: ProductionJobRecordView[]) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <ProductionJobLedgerViewer records={records} />
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

describe("ProductionJobLedgerViewer", () => {
  it("shows provider, model, prompt hash, status, and artifact refs", () => {
    const { container, cleanup } = renderViewer([
      {
        job_id: "job_fixture_001",
        provider: "poyo",
        model: "seedance-2",
        scenario: "s1",
        step_name: "seedance_clips",
        prompt_hash: "sha256:1234567890abcdef1234567890abcdef",
        status: "submitted",
        artifact_paths: { final_video: "fixture://video.mp4" },
        delivery_accepted: false,
        publish_allowed: false,
        blocked_reasons: [],
      },
    ]);

    expect(container.textContent).toMatch(/Production Job Ledger|生产任务账本/);
    expect(container.textContent).toContain("poyo");
    expect(container.textContent).toContain("seedance-2");
    expect(container.textContent).toContain("submitted");
    expect(container.textContent).toContain("sha256:1234567890");
    expect(container.textContent).toContain("final_video");
    expect(container.textContent).toContain("fixture://video.mp4");

    cleanup();
  });

  it("keeps publish locked for succeeded jobs without delivery acceptance", () => {
    const { container, cleanup } = renderViewer([
      {
        job_id: "job_succeeded_without_acceptance",
        provider: "poyo",
        model: "seedance-2",
        scenario: "s2",
        step_name: "video_generate",
        prompt_hash: "sha256:fixture",
        status: "succeeded",
        artifact_paths: { final_video: "fixture://final.mp4" },
        delivery_accepted: false,
        publish_allowed: true,
        blocked_reasons: [],
      },
    ]);

    expect(container.textContent).toContain("succeeded");
    expect(container.textContent).toMatch(/Publish Locked|发布锁定/);
    expect(container.textContent).toMatch(/Generation success is not delivery acceptance|生成成功不等于交付验收/);
    expect(container.textContent).not.toMatch(/Publish Allowed|允许发布/);

    cleanup();
  });

  it("shows publish allowed only when delivery is accepted", () => {
    const { container, cleanup } = renderViewer([
      {
        job_id: "job_delivery_accepted",
        provider: "poyo",
        model: "seedance-2",
        scenario: "s2",
        step_name: "video_generate",
        status: "succeeded",
        artifact_paths: { final_video: "fixture://final.mp4" },
        delivery_accepted: true,
        publish_allowed: true,
        blocked_reasons: [],
      },
    ]);

    expect(container.textContent).toMatch(/Publish Allowed|允许发布/);
    expect(container.textContent).toMatch(/Accepted|已验收/);

    cleanup();
  });

  it("extracts ledger records from state variants", () => {
    expect(extractProductionJobRecords({})).toEqual([]);

    expect(
      extractProductionJobRecords({
        production_job_ledger: {
          records: [
            {
              job_id: "job_nested",
              spec: {
                provider: "poyo",
                model: "seedance-2",
                scenario: "s3",
                step_name: "remix_video",
                prompt_hash: "sha256:nested",
              },
              status: "prepared",
              artifact_paths: {},
              delivery_accepted: false,
              publish_allowed: false,
            },
          ],
        },
      }),
    ).toEqual([
      {
        job_id: "job_nested",
        provider: "poyo",
        model: "seedance-2",
        scenario: "s3",
        step_name: "remix_video",
        prompt_hash: "sha256:nested",
        status: "prepared",
        artifact_paths: {},
        delivery_accepted: false,
        publish_allowed: false,
        failure_reason: "",
        blocked_reasons: [],
      },
    ]);
  });
});
