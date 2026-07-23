import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import GuidedForm from "./GuidedForm";
import { apiFetch } from "./api";

vi.mock("./api", () => ({
  apiFetch: vi.fn(),
}));

function renderGuidedForm(props: React.ComponentProps<typeof GuidedForm>) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <GuidedForm {...props} />
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

function changeInput(container: HTMLElement, selector: string, value: string) {
  const input = container.querySelector(selector) as HTMLInputElement | HTMLTextAreaElement | null;
  expect(input).not.toBeNull();
  act(() => {
    const valueSetter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input!), "value")?.set;
    valueSetter?.call(input, value);
    input!.dispatchEvent(new Event("input", { bubbles: true }));
    input!.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

describe("GuidedForm release-critical scene contracts", () => {
  beforeEach(() => {
    localStorage.setItem("app-locale", "zh-CN");
  });

  it("renders live_shoot as the S4 guided card flow and blocks empty submit", () => {
    const onSubmit = vi.fn();
    const { container, cleanup } = renderGuidedForm({
      scene: "live_shoot",
      onSubmit,
      loading: false,
    });

    try {
      expect(container.querySelector("input[name='footage_assets']")).not.toBeNull();
      expect(container.textContent).toContain("0 / 4");

      const button = container.querySelector("[data-sticky-action-bar] button") as HTMLButtonElement | null;
      expect(button).not.toBeNull();
      expect(button!.disabled).toBe(true);

      act(() => {
        button!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      });
      expect(onSubmit).not.toHaveBeenCalled();
    } finally {
      cleanup();
    }
  });

  it("submits S2 brand_package as a structured object", () => {
    const onSubmit = vi.fn();
    const { container, cleanup } = renderGuidedForm({
      scene: "brand_campaign",
      onSubmit,
      loading: false,
    });

    try {
      changeInput(container, "input[name='campaign_theme']", "Momcozy sleep confidence launch");
      changeInput(container, "textarea[name='brand_values']", "warm support for new moms");

      const button = container.querySelector("[data-sticky-action-bar] button") as HTMLButtonElement | null;
      expect(button).not.toBeNull();
      expect(button!.disabled).toBe(false);

      act(() => {
        button!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      });

      expect(onSubmit).toHaveBeenCalledTimes(1);
      expect(onSubmit.mock.calls[0][0]).toMatchObject({
        content_scenario: "brand_campaign",
        brand_package: {
          brand_name: "Momcozy",
          campaign_theme: "Momcozy sleep confidence launch",
          key_message: "warm support for new moms",
        },
      });
    } finally {
      cleanup();
    }
  });

  it("renders video type labels and descriptions from the English i18n map", () => {
    localStorage.setItem("app-locale", "en");
    const onSubmit = vi.fn();
    const { container, cleanup } = renderGuidedForm({
      scene: "brand_campaign",
      onSubmit,
      loading: false,
    });

    try {
      expect(container.textContent).toContain("Select Video Type");
      expect(container.textContent).toContain("Brand Image Film");
      expect(container.textContent).toContain("Convey brand tone and values");
      expect(container.textContent).not.toContain("传递品牌调性和价值观");
    } finally {
      cleanup();
    }
  });

  it("requires exactly six S5 product views and submits six stable view entries", async () => {
    vi.mocked(apiFetch).mockImplementation(async (_path, options) => {
      const file = (options?.body as FormData).get("file") as File;
      return {
        ok: true,
        json: async () => ({ path: `/uploads/${file.name}` }),
      } as Response;
    });
    const onSubmit = vi.fn();
    const { container, cleanup } = renderGuidedForm({
      scene: "brand_vlog",
      onSubmit,
      loading: false,
    });

    try {
      changeInput(container, "select[name='scene_id']", "office");
      const modelGroup = container.querySelector('[role="group"][aria-label]') as HTMLElement;
      const modelButton = Array.from(modelGroup.querySelectorAll("button")).find(
        (button) => button.textContent?.includes("model-mom"),
      ) as HTMLButtonElement;
      act(() => modelButton.click());

      const input = container.querySelector("input[name='product_views']") as HTMLInputElement;
      const firstFive = Array.from({ length: 5 }, (_, index) => (
        new File([`view-${index + 1}`], `view-${index + 1}.png`, { type: "image/png" })
      ));
      Object.defineProperty(input, "files", { configurable: true, value: firstFive });
      await act(async () => {
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });

      const submitButton = container.querySelector("[data-sticky-action-bar] button") as HTMLButtonElement;
      expect(submitButton.disabled).toBe(true);

      Object.defineProperty(input, "files", {
        configurable: true,
        value: [new File(["view-6"], "view-6.png", { type: "image/png" })],
      });
      await act(async () => {
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
      expect(submitButton.disabled).toBe(false);

      act(() => submitButton.click());
      const payload = onSubmit.mock.calls[0][0] as {
        product_views: string[];
        product_sku: { views: Array<{ path: string }> };
      };
      expect(payload.product_views).toEqual(
        Array.from({ length: 6 }, (_, index) => `/uploads/view-${index + 1}.png`),
      );
      expect(payload.product_sku.views.map((view) => view.path)).toEqual(payload.product_views);
    } finally {
      cleanup();
    }
  });

});
