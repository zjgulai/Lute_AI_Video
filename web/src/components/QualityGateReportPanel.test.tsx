import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import QualityGateReportPanel, { extractQualityGateReport, type QualityGateReportView } from "./QualityGateReportPanel";

function renderPanel(report: QualityGateReportView) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <QualityGateReportPanel report={report} />
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

describe("QualityGateReportPanel", () => {
  it("renders blocked gate decision with blocking repair actions", () => {
    const { container, cleanup } = renderPanel({
      gate_decision: {
        status: "blocked",
        publish_allowed: false,
        requires_human_review: true,
        reasons: ["missing claim evidence"],
      },
      repair_plan: {
        plan_id: "repair_fixture",
        actions: [
          {
            check: "claim_substantiation_pass",
            severity: "blocker",
            recommendation: "attach claim substantiation evidence",
            required_before: "delivery_acceptance",
          },
        ],
      },
    });

    expect(container.textContent).toMatch(/Quality Gate Report|质量门禁报告/);
    expect(container.textContent).toContain("blocked");
    expect(container.textContent).toMatch(/Publish Locked|发布锁定/);
    expect(container.textContent).toContain("claim_substantiation_pass");
    expect(container.textContent).toContain("delivery_acceptance");
    expect(container.textContent).toContain("missing claim evidence");

    cleanup();
  });

  it("renders review_required gate decision with advisory repair actions", () => {
    const { container, cleanup } = renderPanel({
      gate_decision: {
        status: "review_required",
        publish_allowed: false,
        requires_human_review: true,
        reasons: ["blocking passed; human review required before delivery acceptance"],
      },
      repair_plan: {
        plan_id: "repair_advisory_fixture",
        actions: [
          {
            check: "caption_safe_zone_score",
            severity: "advisory",
            recommendation: "caption_safe_zone_score below threshold 0.80",
            required_before: "next_review",
          },
        ],
      },
    });

    expect(container.textContent).toContain("review_required");
    expect(container.textContent).toMatch(/Human Review|人工复核/);
    expect(container.textContent).toContain("caption_safe_zone_score");
    expect(container.textContent).toContain("next_review");

    cleanup();
  });

  it("renders accepted gate decision without implying publish access", () => {
    const { container, cleanup } = renderPanel({
      gate_decision: {
        status: "accepted",
        publish_allowed: false,
        requires_human_review: false,
        reasons: ["blocking passed; delivery accepted, publish remains disabled by default"],
      },
      repair_plan: null,
    });

    expect(container.textContent).toContain("accepted");
    expect(container.textContent).toMatch(/Publish Locked|发布锁定/);
    expect(container.textContent).toMatch(/No repair actions|无修复动作/);
    expect(container.textContent).not.toMatch(/Human Review|人工复核/);

    cleanup();
  });

  it("extracts quality gate report from step-by-step state variants", () => {
    expect(extractQualityGateReport({})).toBeNull();

    expect(
      extractQualityGateReport({
        quality_gate_report: {
          gate_decision: {
            status: "blocked",
            publish_allowed: false,
            reasons: ["missing timeline"],
          },
          repair_plan: {
            plan_id: "repair_nested",
            actions: [{ check: "timeline_manifest_pass", severity: "blocker" }],
          },
        },
      }),
    ).toEqual({
      gate_decision: {
        status: "blocked",
        publish_allowed: false,
        requires_human_review: undefined,
        blocking_failure_count: undefined,
        advisory_warning_count: undefined,
        reasons: ["missing timeline"],
        repair_plan_id: null,
      },
      repair_plan: {
        plan_id: "repair_nested",
        actions: [{ check: "timeline_manifest_pass", severity: "blocker" }],
      },
    });
  });
});
