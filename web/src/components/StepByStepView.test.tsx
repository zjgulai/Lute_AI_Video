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
});
