import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import GuidedCard from "./GuidedCard";
import { apiFetch } from "./api";

vi.mock("./api", () => ({
  apiFetch: vi.fn(),
  getMediaUrl: (path: string) => `/media/${path}`,
}));

const productViewsCard = {
  priority: "required" as const,
  stepName: "Product views",
  stepIcon: "image",
  question: "Upload six product views",
  reason: "Required for product identity",
  connectionText: "",
  fieldKey: "product_views",
  inputType: "image-upload" as const,
};

function renderCard(onChange = vi.fn()) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  function Harness() {
    const [value, setValue] = React.useState("");
    return (
      <I18nProvider>
        <GuidedCard
          card={productViewsCard}
          value={value}
          onChange={(fieldKey, nextValue) => {
            onChange(fieldKey, nextValue);
            setValue(nextValue);
          }}
          isFocused
          onFocus={() => {}}
        />
      </I18nProvider>
    );
  }
  act(() => {
    root.render(<Harness />);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

describe("GuidedCard S5 six-view input", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("app-locale", "en");
  });

  it("uploads six selected files in order and exposes the exact count", async () => {
    vi.mocked(apiFetch).mockImplementation(async (_path, options) => {
      const file = (options?.body as FormData).get("file") as File;
      return {
        ok: true,
        json: async () => ({ path: `/uploads/${file.name}` }),
      } as Response;
    });
    const onChange = vi.fn();
    const { container, cleanup } = renderCard(onChange);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const files = Array.from({ length: 6 }, (_, index) => (
      new File([`view-${index + 1}`], `view-${index + 1}.png`, { type: "image/png" })
    ));
    Object.defineProperty(input, "files", { configurable: true, value: files });

    await act(async () => {
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(input.multiple).toBe(true);
    expect(apiFetch).toHaveBeenCalledTimes(6);
    expect(onChange).toHaveBeenLastCalledWith(
      "product_views",
      files.map((file) => `/uploads/${file.name}`).join("\n"),
    );
    expect(container.textContent).toContain("6 / 6");
    cleanup();
  });

  it("supports drop and keyboard activation and shows partial upload failures", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ path: "/uploads/front.png" }) } as Response)
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) } as Response);
    const onChange = vi.fn();
    const { container, cleanup } = renderCard(onChange);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const clickSpy = vi.spyOn(input, "click").mockImplementation(() => {});
    const dropzone = container.querySelector('[data-upload-dropzone="product_views"]') as HTMLElement;

    expect(dropzone?.getAttribute("role")).toBe("button");
    expect(dropzone?.getAttribute("tabindex")).toBe("0");
    act(() => {
      dropzone.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      dropzone.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
    });
    expect(clickSpy).toHaveBeenCalledTimes(2);

    const dropEvent = new Event("drop", { bubbles: true, cancelable: true });
    Object.defineProperty(dropEvent, "dataTransfer", {
      value: {
        files: [
          new File(["front"], "front.png", { type: "image/png" }),
          new File(["bad"], "bad.png", { type: "image/png" }),
        ],
      },
    });
    await act(async () => {
      dropzone.dispatchEvent(dropEvent);
    });

    expect(onChange).toHaveBeenLastCalledWith("product_views", "/uploads/front.png");
    expect(container.querySelector('[role="alert"]')?.textContent).toMatch(/1 file.*failed/);
    cleanup();
  });

  it("accepts six library assets in the user's click order", async () => {
    const files = Array.from({ length: 6 }, (_, index) => ({
      id: `asset-${index + 1}`,
      filename: `library-${index + 1}.png`,
      path: `portfolio/library-${index + 1}.png`,
      label: `Library ${index + 1}`,
      scenario: "s5",
      produced_at: "2026-07-22T00:00:00Z",
      size_bytes: 10,
      mime_type: "image/png",
      thumbnail_path: null,
    }));
    vi.mocked(apiFetch).mockResolvedValue({
      ok: true,
      json: async () => ({ files }),
    } as Response);
    const onChange = vi.fn();
    const { container, cleanup } = renderCard(onChange);

    const libraryButton = Array.from(container.querySelectorAll("button")).find(
      (button) => /Pick from library|资产库/.test(button.textContent || ""),
    ) as HTMLButtonElement;
    await act(async () => {
      libraryButton.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    const clickOrder = [...files].reverse();
    for (const file of clickOrder) {
      const assetButton = Array.from(container.querySelectorAll("button")).find(
        (button) => button.textContent?.includes(file.label),
      ) as HTMLButtonElement;
      act(() => assetButton.click());
    }
    const confirmButton = Array.from(container.querySelectorAll("button")).find(
      (button) => /Add Selected|确认添加/.test(button.textContent || ""),
    ) as HTMLButtonElement;
    act(() => confirmButton.click());

    expect(onChange).toHaveBeenLastCalledWith(
      "product_views",
      clickOrder.map((file) => `/media/${file.path}`).join("\n"),
    );
    cleanup();
  });
});
