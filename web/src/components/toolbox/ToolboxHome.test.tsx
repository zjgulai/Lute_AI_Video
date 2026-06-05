import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ToolboxHome from "./ToolboxHome";
import { I18nProvider } from "@/i18n/I18nProvider";

const fetchToolboxTools = vi.fn();

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("@/components/TopHeader", () => ({
  default: () => <div data-testid="top-header" />,
}));

vi.mock("@/components/api", () => ({
  fetchToolboxTools: (...args: unknown[]) => fetchToolboxTools(...args),
}));

function renderToolboxHome() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <ToolboxHome />
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

describe("ToolboxHome", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("app-locale", "zh");
    document.cookie = "app-locale=; Max-Age=0; path=/";
    fetchToolboxTools.mockResolvedValue({
      evidence_level: "L2-fixture-or-dry-run",
      tools: [
        {
          tool_id: "product-image",
          label: "Product images",
          output_types: ["product_image_set"],
          injectable_scenarios: ["S1", "S2"],
          default_checks: ["product_facts"],
          evidence_level: "L2-fixture-or-dry-run",
        },
        {
          tool_id: "storyboard",
          label: "Storyboard",
          output_types: ["shot_ledger"],
          injectable_scenarios: ["S1", "S2", "S3", "S4", "S5"],
          default_checks: ["timeline_blocks"],
          evidence_level: "L2-fixture-or-dry-run",
        },
      ],
    });
  });

  it("renders the five planned tools with dry-run evidence boundaries", async () => {
    const { container, cleanup } = renderToolboxHome();
    try {
      await flushEffects();
      await flushEffects();

      expect(container.querySelector("[data-testid='toolbox-home']")).not.toBeNull();
      expect(container.textContent).toContain("AI 视频工具箱");
      expect(container.textContent).toContain("L2-fixture-or-dry-run");
      expect(container.textContent).toContain("No-token");
      expect(container.textContent).toContain("真实生成需授权");
      expect(container.textContent).toContain("电商商品图");
      expect(container.textContent).toContain("产品六视图");
      expect(container.textContent).toContain("电商视觉图");
      expect(container.textContent).toContain("数字人");
      expect(container.textContent).toContain("故事版");
      expect(container.querySelectorAll("[data-tool-card]")).toHaveLength(5);
      expect(fetchToolboxTools).toHaveBeenCalledTimes(1);
    } finally {
      cleanup();
    }
  });

  it("keeps the toolbox home read-only without publish or live generation actions", async () => {
    const { container, cleanup } = renderToolboxHome();
    try {
      await flushEffects();
      const text = container.textContent ?? "";
      expect(text).toContain("当前仅允许 plan、prompt preview 和 dry-run");
      expect(text).toContain("delivery 默认 locked");
      expect(text).not.toContain("发布");
      expect(text).not.toContain("Publish");
      expect(text).not.toContain("Generate live");
    } finally {
      cleanup();
    }
  });
});
