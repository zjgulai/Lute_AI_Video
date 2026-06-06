import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/i18n/I18nProvider";
import MaterialsTab from "./MaterialsTab";

const apiMocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
}));

vi.mock("@/components/api", () => ({
  apiFetch: (...args: unknown[]) => apiMocks.apiFetch(...args),
  getMediaUrl: (path: string) => `/media/${path}`,
  isDemoMode: () => false,
}));

vi.mock("@/components/RuntimeMediaImage", () => ({
  default: ({ src, alt, className }: { src: string; alt: string; className?: string }) => (
    <span data-runtime-media-image data-src={src} className={className}>{alt}</span>
  ),
}));

function mockJsonResponse(body: unknown, init: ResponseInit = {}) {
  return {
    ok: init.status === undefined || init.status < 400,
    status: init.status ?? 200,
    json: async () => body,
  };
}

function renderMaterialsTab() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  act(() => {
    root.render(
      <I18nProvider>
        <MaterialsTab />
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

describe("MaterialsTab pending review assets", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("app-locale", "en");
    apiMocks.apiFetch.mockResolvedValue(
      mockJsonResponse({
        files: [
          {
            id: "pending_review/momcozy_sterilizer_smoke_20260607/main_45.png",
            filename: "main_45.png",
            path: "pending_review/momcozy_sterilizer_smoke_20260607/main_45.png",
            category: "pending_review",
            kind: "creation_intermediate",
            produced_at: "2026-06-07T01:00:00Z",
            size_bytes: 1_435_688,
            mime_type: "image/png",
            thumbnail_path: null,
            review_status: "pending_review",
          },
        ],
      }),
    );
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows pending-review media as read-only library material", async () => {
    const { container, cleanup } = renderMaterialsTab();
    try {
      await flushEffects();
      await flushEffects();

      expect(apiMocks.apiFetch).toHaveBeenCalledWith("/portfolio/?kind=creation_intermediate&limit=500&sort=size_desc");
      const card = container.querySelector("[data-asset-card]");
      expect(card?.getAttribute("data-review-status")).toBe("pending_review");
      expect(container.textContent).toContain("main_45.png");
      expect(container.textContent).toContain("Pending review");
      expect(container.textContent).not.toMatch(/publish|approve|delivery accepted/i);
    } finally {
      cleanup();
    }
  });
});
