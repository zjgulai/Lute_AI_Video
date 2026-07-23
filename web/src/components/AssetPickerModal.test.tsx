import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import AssetPickerModal from "./AssetPickerModal";
import { I18nProvider } from "@/i18n/I18nProvider";

const apiMocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  getMediaUrl: vi.fn((path: string) => `/media/${path}`),
}));

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    apiFetch: apiMocks.apiFetch,
    getMediaUrl: apiMocks.getMediaUrl,
  };
});

const PORTFOLIO_RESPONSE = {
  files: [
    {
      id: "image-1",
      filename: "hero.png",
      path: "portfolio/images/hero.png",
      label: "Hero image",
      scenario: "s1",
      produced_at: "2026-06-01T00:00:00Z",
      size_bytes: 2048,
      mime_type: "image/png",
      thumbnail_path: null,
    },
    {
      id: "video-1",
      filename: "clip.mp4",
      path: "portfolio/videos/clip.mp4",
      label: "Clip video",
      scenario: "s4",
      produced_at: "2026-06-01T00:00:00Z",
      size_bytes: 4096,
      mime_type: "video/mp4",
      thumbnail_path: "portfolio/thumbs/clip.jpg",
    },
  ],
};

function mockJsonResponse(body: unknown, init: ResponseInit = {}) {
  return {
    ok: init.status === undefined || init.status < 400,
    status: init.status ?? 200,
    json: async () => body,
  };
}

function renderPicker(options: {
  acceptKind?: "image" | "video" | "audio" | "all";
  multiple?: boolean;
  onPick?: (urls: string[]) => void;
  onClose?: () => void;
} = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const onPick = options.onPick ?? vi.fn();
  const onClose = options.onClose ?? vi.fn();

  act(() => {
    root.render(
      <I18nProvider>
        <AssetPickerModal
          acceptKind={options.acceptKind ?? "image"}
          multiple={options.multiple}
          onPick={onPick}
          onClose={onClose}
        />
      </I18nProvider>,
    );
  });

  return {
    container,
    onPick,
    onClose,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

async function flushEffects() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("AssetPickerModal request boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("app-locale", "en");
    apiMocks.apiFetch.mockResolvedValue(mockJsonResponse(PORTFOLIO_RESPONSE));
  });

  it("loads selectable assets through the read-only portfolio listing only", async () => {
    const { container, cleanup } = renderPicker({ acceptKind: "image" });
    await flushEffects();

    expect(apiMocks.apiFetch).toHaveBeenCalledTimes(1);
    expect(apiMocks.apiFetch).toHaveBeenCalledWith("/portfolio/?limit=200&sort=recent");
    const requestedPaths = apiMocks.apiFetch.mock.calls.map((call) => String(call[0]));
    for (const forbidden of [
      "/api/upload",
      "/api/assets/upload",
      "/api/files/upload",
      "/fast/generate",
      "/fast/submit",
      "/scenario/",
      "/pipeline/",
      "/gate/",
    ]) {
      expect(requestedPaths.join("\n")).not.toContain(forbidden);
    }

    expect(container.textContent).toContain("Hero image");
    expect(container.textContent).not.toContain("Clip video");
    cleanup();
  });

  it("confirms selected portfolio media without issuing upload or generation requests", async () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    const { container, cleanup } = renderPicker({ acceptKind: "image", onPick, onClose });
    await flushEffects();

    const itemButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("Hero image"),
    ) as HTMLButtonElement | undefined;
    expect(itemButton).toBeTruthy();

    await act(async () => {
      itemButton?.click();
    });
    const confirmButton = Array.from(container.querySelectorAll("button")).find((button) =>
      /add selected|确认添加/i.test(button.textContent || ""),
    ) as HTMLButtonElement | undefined;
    expect(confirmButton).toBeTruthy();

    await act(async () => {
      confirmButton?.click();
    });

    expect(apiMocks.apiFetch).toHaveBeenCalledTimes(1);
    expect(onPick).toHaveBeenCalledWith(["/media/portfolio/images/hero.png"]);
    expect(onClose).toHaveBeenCalledTimes(1);
    cleanup();
  });

  it("preserves click order and hidden selections when a multiple selection is filtered", async () => {
    const files = Array.from({ length: 6 }, (_, index) => ({
      id: `image-${index + 1}`,
      filename: `view-${index + 1}.png`,
      path: `portfolio/images/view-${index + 1}.png`,
      label: `View ${index + 1}`,
      scenario: "s5",
      produced_at: "2026-07-22T00:00:00Z",
      size_bytes: 2048,
      mime_type: "image/png",
      thumbnail_path: null,
    }));
    apiMocks.apiFetch.mockResolvedValueOnce(mockJsonResponse({ files }));
    const onPick = vi.fn();
    const { container, cleanup } = renderPicker({ multiple: true, onPick });
    await flushEffects();

    const clickOrder = [...files].reverse();
    for (const file of clickOrder) {
      const button = Array.from(container.querySelectorAll("button")).find((candidate) =>
        candidate.textContent?.includes(file.label),
      ) as HTMLButtonElement;
      await act(async () => button.click());
    }

    const search = container.querySelector('input[type="search"]') as HTMLInputElement;
    await act(async () => {
      const setValue = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set;
      setValue?.call(search, "View 1");
      search.dispatchEvent(new Event("input", { bubbles: true }));
      search.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(container.textContent).not.toContain("View 6");

    const confirmButton = Array.from(container.querySelectorAll("button")).find((button) =>
      /add selected|确认添加/i.test(button.textContent || ""),
    ) as HTMLButtonElement;
    await act(async () => confirmButton.click());

    expect(onPick).toHaveBeenCalledWith(
      clickOrder.map((file) => `/media/${file.path}`),
    );
    cleanup();
  });

  it("documents the AssetPicker request boundary contract", () => {
    const source = readFileSync(
      join(process.cwd(), "src/components/AssetPickerModal.tsx"),
      "utf8",
    );
    const contract = readFileSync(
      join(process.cwd(), "..", "configs/asset-picker-request-boundary-contract.yaml"),
      "utf8",
    );
    const runbook = readFileSync(
      join(process.cwd(), "..", "docs/runbooks/asset-picker-request-boundary.md"),
      "utf8",
    );

    expect(source).toContain('apiFetch("/portfolio/?limit=200&sort=recent")');
    for (const forbidden of [
      "/api/upload",
      "/api/assets/upload",
      "/api/files/upload",
      "/fast/generate",
      "/fast/submit",
      "/scenario/",
      "/pipeline/",
      "/gate/",
    ]) {
      expect(source).not.toContain(forbidden);
    }

    for (const token of [
      "portfolio_listing_only",
      "forbidden_upload_endpoints",
      "forbidden_generation_endpoints",
      "mocked_api_fetch_only",
    ]) {
      expect(contract).toContain(token);
    }

    for (const token of [
      "npm test -- --run src/components/AssetPickerModal.test.tsx",
      "/portfolio/?limit=200&sort=recent",
      "不触发生成接口",
    ]) {
      expect(runbook).toContain(token);
    }
  });
});
