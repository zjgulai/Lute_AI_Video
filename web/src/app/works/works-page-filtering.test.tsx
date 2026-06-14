import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/i18n/I18nProvider";
import WorksPage from "./page";

const apiFetch = vi.fn();

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("@/components/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  getMediaUrl: (path: string) => `/media/${path}`,
  isDemoMode: () => false,
}));

vi.mock("@/components/TopHeader", () => ({
  default: () => <div data-testid="top-header" />,
}));

function renderWorksPage() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <WorksPage />
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

describe("WorksPage scene filtering", () => {
  beforeEach(() => {
    localStorage.clear();
    document.cookie = "app-locale=; Max-Age=0; path=/";
    apiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        files: [
          {
            id: "live-shoot-direct",
            filename: "live_shoot_1700000000.mp4",
            path: "renders/live_shoot_1700000000.mp4",
            scenario: null,
            label: null,
            produced_at: "2026-06-01T00:00:00Z",
            size_bytes: 2_000_000,
            mime_type: "video/mp4",
            thumbnail_path: null,
          },
          {
            id: "live-shoot-to-video",
            filename: "live_shoot_to_video_1700000001.mp4",
            path: "renders/live_shoot_to_video_1700000001.mp4",
            scenario: null,
            label: null,
            produced_at: "2026-06-01T00:00:01Z",
            size_bytes: 2_000_000,
            mime_type: "video/mp4",
            thumbnail_path: null,
          },
          {
            id: "brand-vlog",
            filename: "s5_1700000002.mp4",
            path: "renders/s5_1700000002.mp4",
            scenario: "s5",
            label: null,
            produced_at: "2026-06-01T00:00:02Z",
            size_bytes: 2_000_000,
            mime_type: "video/mp4",
            thumbnail_path: null,
          },
        ],
      }),
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("keeps live_shoot filename aliases visible under the Live Shoot filter", async () => {
    const { container, cleanup } = renderWorksPage();
    try {
      await flushEffects();
      await flushEffects();

      const liveShootButton = Array.from(container.querySelectorAll("button"))
        .find((button) => {
          const text = button.textContent ?? "";
          return text.includes("实拍素材生成") || text.includes("Live Shoot");
        });
      expect(liveShootButton).toBeTruthy();

      await act(async () => {
        liveShootButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      });

      const cards = Array.from(container.querySelectorAll("[data-asset-card]"));
      expect(cards).toHaveLength(2);
      expect(cards.map((card) => card.textContent).join("\n")).toContain("live shoot 1700000000");
      expect(cards.map((card) => card.textContent).join("\n")).toContain("live shoot to video 1700000001");
      expect(cards.map((card) => card.textContent).join("\n")).not.toContain("s5 1700000002");
    } finally {
      cleanup();
    }
  });
});
