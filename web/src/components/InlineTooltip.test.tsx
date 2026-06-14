import { describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";

import InlineTooltip from "./InlineTooltip";

function renderTooltip(props: React.ComponentProps<typeof InlineTooltip>) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<InlineTooltip {...props} />);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("InlineTooltip", () => {
  it("renders focusable trigger with tooltip content", () => {
    const { container, cleanup } = renderTooltip({
      label: "Short preview…",
      tooltip: "Full tooltip content",
    });

    const trigger = container.querySelector("[aria-label='Full tooltip content']") as HTMLElement | null;
    const tooltip = container.querySelector("[role='tooltip']") as HTMLElement | null;

    expect(trigger).not.toBeNull();
    expect(trigger?.getAttribute("tabindex")).toBe("0");
    expect(trigger?.textContent).toContain("Short preview…");
    expect(tooltip?.textContent).toContain("Full tooltip content");
    cleanup();
  });

  it("supports configurable placement while keeping mobile-safe sizing", () => {
    const { container, cleanup } = renderTooltip({
      label: "Top preview",
      tooltip: "Top tooltip content",
      placement: "top",
    });

    const tooltip = container.querySelector("[role='tooltip']") as HTMLElement | null;
    const className = tooltip?.className || "";

    expect(className).toContain("bottom-full");
    expect(className).toContain("max-w-[calc(100vw-2rem)]");
    expect(className).toContain("group-active:block");
    cleanup();
  });
});
