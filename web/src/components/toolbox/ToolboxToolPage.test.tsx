import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ToolboxToolPage from "./ToolboxToolPage";
import { I18nProvider } from "@/i18n/I18nProvider";

const planToolboxRun = vi.fn();
const previewToolboxPrompt = vi.fn();
const runToolboxDryRun = vi.fn();
const fetchToolboxRuns = vi.fn();
const fetchToolboxRun = vi.fn();

type CapturedToolboxRequest = {
  tool_id: string;
  brand_bundle_ref: string;
  asset_refs: Array<{ asset_ref: string }>;
  tool_input: { tool_id: string };
};

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("@/components/TopHeader", () => ({
  default: () => <div data-testid="top-header" />,
}));

vi.mock("@/components/api", () => ({
  fetchToolboxRun: (...args: unknown[]) => fetchToolboxRun(...args),
  fetchToolboxRuns: (...args: unknown[]) => fetchToolboxRuns(...args),
  planToolboxRun: (...args: unknown[]) => planToolboxRun(...args),
  previewToolboxPrompt: (...args: unknown[]) => previewToolboxPrompt(...args),
  runToolboxDryRun: (...args: unknown[]) => runToolboxDryRun(...args),
}));

function renderToolPage(toolId = "product-image") {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <ToolboxToolPage toolId={toolId} />
      </I18nProvider>,
    );
  });

  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

async function flushEffects() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

function findButton(container: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll("button")).find((candidate) =>
    candidate.textContent?.includes(text)
  );
  expect(button).toBeTruthy();
  return button as HTMLButtonElement;
}

describe("ToolboxToolPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("app-locale", "zh");
    document.cookie = "app-locale=; Max-Age=0; path=/";

    const plan = {
      plan_id: "tbx_plan_product_image_001",
      request_id: "tbx_req_product_image_001",
      tool_id: "product-image",
      mode: "dry_run",
      evidence_level: "L2-fixture-or-dry-run",
      provider_call: false,
      delivery_accepted: false,
      provider_profile_id: "provider://mock/no-token",
      prompt_hash: "sha256:toolbox-preview",
      required_checks: ["product_truth", "brand_rights"],
      artifact_manifest_id: "manifest://toolbox/product-image/001",
      injection_target_refs: [
        "artifact://toolbox/product-image/001/inject/s1",
        "artifact://toolbox/product-image/001/inject/s2",
      ],
    };
    const promptPreview = {
      preview_id: "tbx_preview_product_image_001",
      request_id: "tbx_req_product_image_001",
      tool_id: "product-image",
      prompt_hash: "sha256:toolbox-preview",
      prompt_preview_allowed: true,
      sanitized_prompt_blocks: ["bundle_ref=bundle_momcozy_candidate", "asset_refs=1"],
      compile_warnings: [],
      blocked_reasons: [],
    };
    const runState = {
      run_id: "tbx_run_product_image_001",
      request_id: "tbx_req_product_image_001",
      tool_id: "product-image",
      brand_id: "momcozy",
      brand_bundle_ref: "bundle_momcozy_candidate",
      target_scenario: null,
      asset_refs: [],
      status: "accepted_dry_run",
      plan,
      prompt_preview: promptPreview,
      job_record: {
        job_id: "tbx_job_product_image_001",
        status: "prepared",
        delivery_accepted: false,
        publish_allowed: false,
        blocked_reasons: [],
        artifact_paths: {},
        spec: {},
      },
      artifacts: [
        {
          artifact_id: "artifact_product_image_001",
          tool_id: "product-image",
          artifact_type: "product_image_set",
          artifact_ref: "artifact://toolbox/product-image/001",
          source_job_id: "tbx_job_product_image_001",
          manifest_ref: "manifest://toolbox/product-image/001",
          delivery_accepted: false,
          publish_allowed: false,
        },
      ],
      injection_targets: [
        {
          target_ref: "artifact://toolbox/product-image/001/inject/s1",
          scenario: "s1",
          step_name: "product_assets",
          artifact_refs: ["artifact://toolbox/product-image/001"],
          contract_refs: ["manifest://toolbox/product-image/001", "job://toolbox/tbx_req_product_image_001"],
          bundle_refs: ["bundle_momcozy_candidate"],
        },
      ],
    };

    planToolboxRun.mockResolvedValue(plan);
    previewToolboxPrompt.mockResolvedValue(promptPreview);
    runToolboxDryRun.mockResolvedValue(runState);
    fetchToolboxRun.mockResolvedValue({
      ...runState,
      run_id: "tbx_run_product_image_loaded",
      job_record: {
        ...runState.job_record,
        job_id: "tbx_job_product_image_loaded",
      },
      artifacts: [
        {
          ...runState.artifacts[0],
          artifact_id: "artifact_product_image_loaded",
          artifact_ref: "artifact://toolbox/product-image/loaded",
        },
      ],
      injection_targets: [
        {
          target_ref: "artifact://toolbox/product-image/loaded/inject/s1",
          scenario: "s1",
          step_name: "product_assets",
          artifact_refs: ["artifact://toolbox/product-image/loaded"],
          contract_refs: ["manifest://toolbox/product-image/loaded", "job://toolbox/tbx_req_product_image_loaded"],
          bundle_refs: ["bundle_momcozy_candidate"],
        },
      ],
    });
    fetchToolboxRuns.mockResolvedValue({
      evidence_level: "L2-fixture-or-dry-run",
      runs: [runState],
    });
  });

  it("renders the single-tool dry-run workbench without publish actions", async () => {
    const { container, cleanup } = renderToolPage("product-image");
    try {
      await flushEffects();

      expect(container.querySelector("[data-testid='toolbox-tool-page']")).not.toBeNull();
      expect(container.textContent).toContain("电商商品图");
      expect(container.textContent).toContain("工具输入");
      expect(container.textContent).toContain("计划与预览");
      expect(container.textContent).toContain("质量门禁");
      expect(container.textContent).toContain("任务账本");
      expect(container.textContent).toContain("产物清单");
      expect(container.textContent).toContain("真实生成锁定");
      expect(container.textContent).toContain("当前 Run");
      const buttonText = Array.from(container.querySelectorAll("button")).map((button) => button.textContent ?? "").join(" ");
      expect(buttonText).not.toContain("发布");
      expect(buttonText).not.toContain("Publish");
      expect(fetchToolboxRuns).toHaveBeenCalledWith(expect.objectContaining({ toolId: "product-image", limit: 5 }));
    } finally {
      cleanup();
    }
  });

  it("loads current-tool recent runs and can rehydrate a selected run state", async () => {
    const { container, cleanup } = renderToolPage("product-image");
    try {
      await flushEffects();
      await flushEffects();

      expect(container.textContent).toContain("tbx_run_product_image_001");
      const loadButton = container.querySelector("[data-toolbox-run-select='tbx_run_product_image_001']") as HTMLButtonElement | null;
      expect(loadButton).not.toBeNull();

      await act(async () => {
        loadButton?.click();
      });
      await flushEffects();

      expect(fetchToolboxRun).toHaveBeenCalledWith("tbx_run_product_image_001");
      expect(container.textContent).toContain("tbx_job_product_image_loaded");
      expect(container.textContent).toContain("artifact://toolbox/product-image/loaded");
      expect(container.textContent).toContain("manifest://toolbox/product-image/loaded");
    } finally {
      cleanup();
    }
  });

  it("sends a dry-run plan request with matching path and body tool ids", async () => {
    const { container, cleanup } = renderToolPage("product-image");
    try {
      await flushEffects();

      await act(async () => {
        findButton(container, "准备计划").click();
      });
      await flushEffects();

      expect(planToolboxRun).toHaveBeenCalledTimes(1);
      const [toolId, body] = planToolboxRun.mock.calls[0] as [string, CapturedToolboxRequest];
      expect(toolId).toBe("product-image");
      expect(body.tool_id).toBe("product-image");
      expect(body.tool_input.tool_id).toBe("product-image");
      expect(body.brand_bundle_ref).toBe("bundle_momcozy_candidate");
      expect(body.asset_refs[0].asset_ref).toBe("asset://brand/momcozy/product/reference-001");
      expect(JSON.stringify(body)).not.toContain("prompt_payload");
      expect(container.textContent).toContain("tbx_plan_product_image_001");
      expect(container.textContent).toContain("sha256:toolbox-preview");
    } finally {
      cleanup();
    }
  });

  it("runs only the dry-run endpoint and renders refs-only artifacts", async () => {
    const { container, cleanup } = renderToolPage("product-image");
    try {
      await flushEffects();

      await act(async () => {
        findButton(container, "运行 Dry-run").click();
      });
      await flushEffects();

      expect(runToolboxDryRun).toHaveBeenCalledTimes(1);
      expect(previewToolboxPrompt).not.toHaveBeenCalled();
      expect(container.textContent).toContain("tbx_job_product_image_001");
      expect(container.textContent).toContain("prepared");
      expect(container.textContent).toContain("artifact://toolbox/product-image/001");
      expect(container.textContent).toContain("Contract refs");
      expect(container.textContent).toContain("manifest://toolbox/product-image/001");
      expect(container.textContent).toContain("bundle_momcozy_candidate");
      expect(container.textContent).toContain("仅允许 artifact refs、contract refs、bundle ids 回注 S1-S5。");
    } finally {
      cleanup();
    }
  });

  it("renders a fail-closed view for unknown tool ids", async () => {
    const { container, cleanup } = renderToolPage("unknown-tool");
    try {
      await flushEffects();

      expect(container.textContent).toContain("未知工具");
      expect(planToolboxRun).not.toHaveBeenCalled();
      expect(previewToolboxPrompt).not.toHaveBeenCalled();
      expect(runToolboxDryRun).not.toHaveBeenCalled();
    } finally {
      cleanup();
    }
  });
});
