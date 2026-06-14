import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import StepByStepView from "./StepByStepView";

function renderStepByStepView(state: Record<string, unknown>) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <StepByStepView
          label="s1-commercial-fixture"
          state={state}
          onStepComplete={() => undefined}
          onResume={() => undefined}
          loading={false}
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

describe("StepByStepView commercial injection visibility", () => {
  it("renders step-level commercial injection refs as read-only chips", () => {
    const { container, cleanup } = renderStepByStepView({
      meta: { step_order: ["strategy", "scripts"] },
      steps: {
        strategy: {
          status: "done",
          output: [{ brief_id: "brief-1" }],
          commercial_injection: {
            bundle_refs: ["BrandConstraintBundle"],
            toolbox_refs: ["ImageToolbox"],
            contract_refs: ["QualityContract"],
            gate_checks: ["rights_pass"],
            source_token_ids: ["bat_fixture"],
          },
        },
        scripts: { status: "pending", output: null },
      },
    });

    expect(container.textContent).toMatch(/Commercial Injection|商业注入/);
    expect(container.textContent).toMatch(/Read-only|只读/);
    expect(container.textContent).toContain("BrandConstraintBundle");
    expect(container.textContent).toContain("ImageToolbox");
    expect(container.textContent).toContain("QualityContract");
    expect(container.textContent).toContain("rights_pass");
    expect(container.textContent).toContain("bat_fixture");

    cleanup();
  });

  it("hides the commercial injection panel when step metadata is absent", () => {
    const { container, cleanup } = renderStepByStepView({
      meta: { step_order: ["strategy"] },
      steps: {
        strategy: {
          status: "done",
          output: [{ brief_id: "brief-1" }],
        },
      },
    });

    expect(container.textContent).not.toMatch(/Commercial Injection|商业注入/);
    expect(container.textContent).not.toContain("BrandConstraintBundle");

    cleanup();
  });

  it("renders state-level prompt preview audit bundle without prompt body", () => {
    const { container, cleanup } = renderStepByStepView({
      meta: { step_order: ["video_prompts"] },
      prompt_preview_audit_bundle: promptPreviewAuditBundle(),
      steps: {
        video_prompts: {
          status: "done",
          output: { prompts: [] },
        },
      },
    });

    const text = container.textContent || "";
    expect(text).toMatch(/Prompt Preview Audit|Prompt 预览审计/);
    expect(text).toContain("allowed-with-label");
    expect(text).toContain("poyo");
    expect(text).toContain("seedance-2");
    expect(text).toContain("sha256:1234567890");
    expect(text).toContain("delivery accepted");
    expect(text).not.toContain("prompt body must not leak");

    cleanup();
  });

  it("renders step-output prompt preview audit bundle from completed step output", () => {
    const { container, cleanup } = renderStepByStepView({
      meta: { step_order: ["video_prompts"] },
      steps: {
        video_prompts: {
          status: "done",
          output: {
            prompt_preview_audit: {
              ...promptPreviewAuditBundle(),
              audit_bundle_id: "ppab_step_output_fixture",
              prompt_hash: "sha256:abcdef1234567890abcdef1234567890",
            },
          },
        },
      },
    });

    const text = container.textContent || "";
    expect(text).toMatch(/Prompt Preview Audit|Prompt 预览审计/);
    expect(text).toContain("ppab_step_output_fixture");
    expect(text).toContain("sha256:abcdef123456");
    expect(text).not.toContain("prompt body must not leak");

    cleanup();
  });
});

function promptPreviewAuditBundle() {
  return {
    audit_bundle_id: "ppab_state_fixture",
    compile_id: "pci_state_fixture",
    scenario: "s1",
    step: "video_prompts",
    provider: "poyo",
    model: "seedance-2",
    prompt_hash: "sha256:1234567890abcdef1234567890abcdef",
    preview: {
      prompt: "prompt body must not leak",
      negative_prompt: "prompt body must not leak",
    },
    gate_decision: {
      status: "review_required",
      requires_human_review: true,
      blocking_failure_count: 0,
      advisory_warning_count: 0,
    },
    repair_plan: {
      actions: [],
    },
    evidence_boundary: {
      decision: "allowed-with-label",
      evidence_level: "L2-fixture-or-dry-run",
      forbidden_claims: ["delivery accepted", "provider job submitted"],
    },
    delivery_accepted: false,
    publish_allowed: false,
  };
}
