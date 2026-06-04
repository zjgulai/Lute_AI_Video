import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import ScenarioInjectionDiffPanel, {
  buildScenarioInjectionDiff,
  shouldShowScenarioInjectionDiff,
  type ScenarioInjectionDiffView,
} from "./ScenarioInjectionDiffPanel";

function renderPanel(diff: ScenarioInjectionDiffView) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <ScenarioInjectionDiffPanel diff={diff} />
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

function planPayload(scenario = "s1") {
  return {
    scenario,
    brand_id: "momcozy",
    steps: [
      {
        scenario,
        step: "strategy",
        bundle_refs: ["BrandConstraintBundle"],
        toolbox_refs: ["ImageToolbox"],
        contract_refs: ["QualityContract"],
        gate_checks: ["rights_pass"],
        source_token_ids: ["bat_fixture"],
      },
    ],
  };
}

describe("ScenarioInjectionDiffPanel", () => {
  it("renders an absent plan state without showing in default step view surface", () => {
    const state = {};
    const diff = buildScenarioInjectionDiff(state);
    const { container, cleanup } = renderPanel(diff);

    expect(diff.status).toBe("absent");
    expect(shouldShowScenarioInjectionDiff(state, diff)).toBe(false);
    expect(container.textContent).toMatch(/Scenario Injection Diff|场景注入差异/);
    expect(container.textContent).toMatch(/No Plan|未接入计划/);

    cleanup();
  });

  it("marks matching plan refs against current step visibility", () => {
    const state = {
      scenario: "s1",
      current_step: "strategy",
      config: { commercial_injection_plan: planPayload("s1") },
      current_step_injection: {
        bundle_refs: ["BrandConstraintBundle"],
        toolbox_refs: ["ImageToolbox"],
        contract_refs: ["QualityContract"],
        gate_checks: ["rights_pass"],
        source_token_ids: ["bat_fixture"],
      },
    };
    const diff = buildScenarioInjectionDiff(state);
    const { container, cleanup } = renderPanel(diff);

    expect(diff.status).toBe("matching");
    expect(shouldShowScenarioInjectionDiff(state, diff)).toBe(true);
    expect(container.textContent).toMatch(/Matching|已匹配/);
    expect(container.textContent).toContain("BrandConstraintBundle");
    expect(container.textContent).toContain("rights_pass");
    expect(container.textContent).not.toMatch(/Missing|缺失/);

    cleanup();
  });

  it("fails closed on scenario mismatch", () => {
    const state = {
      scenario: "s2",
      current_step: "strategy",
      config: { commercial_injection_plan: planPayload("s1") },
      current_step_injection: {
        bundle_refs: ["BrandConstraintBundle"],
      },
    };
    const diff = buildScenarioInjectionDiff(state);
    const { container, cleanup } = renderPanel(diff);

    expect(diff.status).toBe("scenario_mismatch");
    expect(container.textContent).toMatch(/Scenario Mismatch|场景不匹配/);
    expect(container.textContent).toContain("s1");
    expect(container.textContent).toContain("s2");

    cleanup();
  });
});
