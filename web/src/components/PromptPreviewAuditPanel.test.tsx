import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import PromptPreviewAuditPanel, { normalizePromptPreviewAuditBundle } from "./PromptPreviewAuditPanel";

function renderPanel(bundle: unknown) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <PromptPreviewAuditPanel bundle={bundle} />
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

describe("PromptPreviewAuditPanel", () => {
  it("renders blocked audits with blocker count, repair actions, and forbidden claims", () => {
    const { container, cleanup } = renderPanel({
      audit_bundle_id: "ppab_blocked_fixture",
      compile_id: "pci_blocked_fixture",
      scenario: "s1",
      step: "video_prompts",
      provider: "poyo",
      model: "seedance-2",
      preview: {
        prompt: "prompt body must not leak",
        negative_prompt: "negative prompt must not leak",
      },
      gate_decision: {
        status: "blocked",
        requires_human_review: true,
        blocking_failure_count: 2,
        advisory_warning_count: 1,
      },
      repair_plan: {
        actions: [
          {
            check: "runtime_prompt_preview_allowed",
            severity: "blocker",
            recommendation: "rerun dry-run prompt preview audit",
            required_before: "human_review",
          },
        ],
      },
      evidence_boundary: {
        decision: "blocked",
        evidence_level: "L2-fixture-or-dry-run",
        forbidden_claims: ["provider job submitted", "commercial production ready"],
      },
      delivery_accepted: false,
      publish_allowed: false,
    });

    const text = container.textContent || "";
    expect(text).toMatch(/Prompt Preview Audit|Prompt 预览审计/);
    expect(text).toContain("blocked");
    expect(text).toContain("2");
    expect(text).toContain("runtime_prompt_preview_allowed");
    expect(text).toContain("provider job submitted");
    expect(text).toContain("commercial production ready");
    expect(text).toMatch(/Publish Locked|发布锁定/);
    expect(text).not.toContain("prompt body must not leak");
    expect(text).not.toContain("negative prompt must not leak");
    expect(container.querySelectorAll("button")).toHaveLength(0);

    cleanup();
  });

  it("renders allowed-with-label audits with hash, provider, model, review requirement, and forbidden claims", () => {
    const { container, cleanup } = renderPanel({
      audit_bundle_id: "ppab_allowed_fixture",
      compile_id: "pci_allowed_fixture",
      scenario: "s1",
      step: "video_prompts",
      provider: "poyo",
      model: "seedance-2",
      prompt_hash: "sha256:1234567890abcdef1234567890abcdef",
      preview: {
        prompt_preview_allowed: true,
        prompt: "allowed prompt body must not leak",
      },
      gate_decision: {
        status: "review_required",
        requires_human_review: true,
        blocking_failure_count: 0,
        advisory_warning_count: 0,
      },
      repair_plan: { actions: [] },
      evidence_boundary: {
        decision: "allowed-with-label",
        evidence_level: "L2-fixture-or-dry-run",
        forbidden_claims: ["delivery accepted", "publish allowed"],
      },
      delivery_accepted: false,
      publish_allowed: false,
    });

    const text = container.textContent || "";
    expect(text).toContain("allowed-with-label");
    expect(text).toContain("review_required");
    expect(text).toContain("poyo");
    expect(text).toContain("seedance-2");
    expect(text).toContain("sha256:1234567890");
    expect(text).toMatch(/Human Review|人工复核/);
    expect(text).toContain("delivery accepted");
    expect(text).toContain("publish allowed");
    expect(text).not.toContain("allowed prompt body must not leak");
    expect(container.querySelectorAll("button")).toHaveLength(0);

    cleanup();
  });

  it("returns null for absent audit bundles and ignores preview prompt fields while normalizing", () => {
    const { container, cleanup } = renderPanel({});
    expect(container.textContent).toBe("");
    cleanup();

    expect(
      normalizePromptPreviewAuditBundle({
        provider: "poyo",
        model: "seedance-2",
        preview: {
          prompt: "must-not-leak",
          negative_prompt: "must-not-leak",
        },
        gate_decision: { status: "review_required" },
        evidence_boundary: {
          decision: "allowed-with-label",
          evidence_level: "L2-fixture-or-dry-run",
          forbidden_claims: [],
        },
      }),
    ).toMatchObject({
      provider: "poyo",
      model: "seedance-2",
      decision: "allowed-with-label",
      gate_status: "review_required",
    });
  });
});
