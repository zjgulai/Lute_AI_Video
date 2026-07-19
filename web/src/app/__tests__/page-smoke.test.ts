import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import { useAppStore } from "@/stores/useAppStore";
import { useExpertStore } from "@/stores/useExpertStore";
import { usePipelineStore } from "@/stores/usePipelineStore";

const apiMocks = vi.hoisted(() => ({
  hasApiKey: vi.fn(() => false),
  isDemoMode: vi.fn(() => true),
  isApiError: vi.fn(() => false),
  runS1ProductDirect: vi.fn(),
  submitScenario: vi.fn(),
  getSubmissionByIdempotencyKey: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: () => null }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/",
  redirect: vi.fn(),
}));

vi.mock("@/components/api", () => ({
  hasApiKey: apiMocks.hasApiKey,
  isDemoMode: apiMocks.isDemoMode,
  isApiError: apiMocks.isApiError,
  getMediaUrl: (p: string) => p,
  buildAdminUrl: (p: string) => p,
  fetchState: vi.fn(),
  submitReview: vi.fn(),
  runS1ProductDirect: apiMocks.runS1ProductDirect,
  runS5BrandVlog: vi.fn(),
  startS1StepByStep: vi.fn(),
  resumeS1: vi.fn(),
  fetchS1State: vi.fn(),
  submitScenario: apiMocks.submitScenario,
  getSubmissionByIdempotencyKey: apiMocks.getSubmissionByIdempotencyKey,
  logStateChange: vi.fn(),
  fetchToolboxTools: vi.fn(),
  fetchToolboxRuns: vi.fn(),
  fetchToolboxRun: vi.fn(),
  fetchToolboxAuditSummaries: vi.fn(),
  fetchToolboxAuditSummary: vi.fn(),
  previewToolboxInjectionDraft: vi.fn(),
}));

vi.mock("@/components/SceneForm", async () => {
  const { createElement: h } = await import("react");
  return {
    default: ({ onSubmit }: { onSubmit: (config: Record<string, unknown>) => void }) => h(
      "button",
      {
        "data-testid": "scene-submit",
        onClick: () => onSubmit({
          content_scenario: "product_direct",
          mode: "smart",
          product_catalog: { products: [{ name: "Fixture" }] },
          target_platforms: ["tiktok"],
          target_languages: ["en"],
          video_duration: 30,
        }),
      },
      "submit scene",
    ),
  };
});

vi.mock("@/components/RecommendPanel", async () => {
  const { createElement: h } = await import("react");
  return {
    default: ({
      config,
      onStart,
    }: {
      config: Record<string, unknown>;
      onStart: (config: Record<string, unknown>) => void;
    }) => h(
      "button",
      {
        "data-testid": "recommend-start",
        onClick: () => onStart({ ...config, mode: "auto" }),
      },
      "start recommendation",
    ),
  };
});

vi.mock("@/components/StageProgress", async () => {
  const { createElement: h } = await import("react");
  return { default: () => h("div", { "data-testid": "stage-progress" }, "progress") };
});

const PAGE_MODULES = [
  { name: "home", loader: () => import("@/app/page") },
  { name: "s1", loader: () => import("@/app/s1/page") },
  { name: "s2", loader: () => import("@/app/s2/page") },
  { name: "s3", loader: () => import("@/app/s3/page") },
  { name: "s4", loader: () => import("@/app/s4/page") },
  { name: "s5", loader: () => import("@/app/s5/page") },
  { name: "fast", loader: () => import("@/app/fast/page") },
  { name: "result", loader: () => import("@/app/result/page") },
  { name: "settings", loader: () => import("@/app/settings/page") },
  { name: "footage", loader: () => import("@/app/footage/page") },
  { name: "library", loader: () => import("@/app/library/page") },
  { name: "toolbox", loader: () => import("@/app/toolbox/page") },
  { name: "toolbox-detail", loader: () => import("@/app/toolbox/[toolId]/page") },
  { name: "brand-packages", loader: () => import("@/app/brand-packages/page") },
  { name: "influencers", loader: () => import("@/app/influencers/page") },
  { name: "admin", loader: () => import("@/app/admin/page") },
  { name: "works", loader: () => import("@/app/works/page") },
] as const;

const PAGE_MODULE_LOAD_TIMEOUT_MS = 60_000;

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.hasApiKey.mockReturnValue(false);
  apiMocks.isDemoMode.mockReturnValue(true);
  apiMocks.isApiError.mockReturnValue(false);
});

describe("D4 page-module smoke", () => {
  PAGE_MODULES.forEach(({ name, loader }) => {
    it(`${name}/page module loads + exports default function`, async () => {
      const mod = await loader();
      expect(mod).toBeTruthy();
      expect(typeof mod.default).toBe("function");
      expect(mod.default.name.length).toBeGreaterThan(0);
    }, PAGE_MODULE_LOAD_TIMEOUT_MS);
  });

  it("all page modules expose stable default export shape", async () => {
    const all = await Promise.all(PAGE_MODULES.map(async ({ name, loader }) => {
      const mod = await loader();
      return { name, hasDefault: typeof mod.default === "function" };
    }));
    const failures = all.filter(r => !r.hasDefault);
    expect(failures, `pages without default function: ${JSON.stringify(failures)}`).toHaveLength(0);
  }, PAGE_MODULE_LOAD_TIMEOUT_MS);
});

describe("S1 unified submit safety", () => {
  it("recovers the original async job by GET without replaying any mutation", async () => {
    localStorage.clear();
    apiMocks.hasApiKey.mockReturnValue(true);
    apiMocks.isDemoMode.mockReturnValue(false);
    apiMocks.submitScenario.mockRejectedValue(new TypeError("Failed to fetch"));
    apiMocks.getSubmissionByIdempotencyKey.mockResolvedValue({
      resource_type: "scenario",
      resource_id: "s1_original",
      scenario: "s1",
      status: "queued",
      submit_response: {
        label: "s1_original",
        status: "queued",
        trace_id: "trace-safe",
      },
      result_snapshot: null,
    });
    useAppStore.setState({
      stage: "home",
      activeScene: "product_direct",
      mode: "smart",
      pipelineMode: "auto",
      loading: false,
      toast: null,
      disconnected: false,
      showSplash: false,
      showSettings: false,
      showAssetLibrary: false,
    });
    usePipelineStore.getState().clearPendingSubmission();
    usePipelineStore.getState().resetAll();
    useExpertStore.getState().resetExpert();

    const { default: Home } = await import("@/app/page");
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(createElement(I18nProvider, null, createElement(Home)));
    });

    const sceneSubmit = container.querySelector<HTMLButtonElement>("[data-testid='scene-submit']");
    expect(sceneSubmit).not.toBeNull();
    await act(async () => {
      sceneSubmit?.click();
    });
    const start = container.querySelector<HTMLButtonElement>("[data-testid='recommend-start']");
    expect(start).not.toBeNull();
    await act(async () => {
      start?.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(apiMocks.submitScenario).toHaveBeenCalledTimes(1);
    expect(apiMocks.getSubmissionByIdempotencyKey).toHaveBeenCalledTimes(1);
    expect(apiMocks.runS1ProductDirect).not.toHaveBeenCalled();
    const options = apiMocks.submitScenario.mock.calls[0]?.[2] as {
      idempotencyKey?: string;
    };
    expect(options.idempotencyKey).toMatch(/^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/);
    expect(apiMocks.getSubmissionByIdempotencyKey).toHaveBeenCalledWith(
      options.idempotencyKey,
    );
    expect(usePipelineStore.getState().activePipeline).toMatchObject({
      label: "s1_original",
      scenario: "s1",
    });
    expect(usePipelineStore.getState().pendingSubmission).toMatchObject({
      idempotencyKey: options.idempotencyKey,
      phase: "bound",
      resourceId: "s1_original",
    });

    await act(async () => root.unmount());
    document.body.removeChild(container);
  });

  it("restores a visible recovery_required card on reload using GET only", async () => {
    localStorage.clear();
    localStorage.setItem("app-locale", "zh");
    apiMocks.hasApiKey.mockReturnValue(true);
    apiMocks.isDemoMode.mockReturnValue(false);
    apiMocks.getSubmissionByIdempotencyKey.mockResolvedValue({
      resource_type: "scenario",
      resource_id: "s1_recovery_required",
      scenario: "s1",
      status: "recovery_required",
      submit_response: {
        label: "s1_recovery_required",
        status: "recovery_required",
      },
      result_snapshot: null,
    });
    useAppStore.setState({
      stage: "home",
      activeScene: "product_direct",
      mode: "smart",
      pipelineMode: "auto",
      loading: false,
      toast: null,
      disconnected: false,
      showSplash: false,
      showSettings: false,
      showAssetLibrary: false,
    });
    usePipelineStore.getState().resetAll();
    usePipelineStore.getState().setPendingSubmission({
      kind: "scenario",
      scenario: "s1",
      idempotencyKey: "123e4567-e89b-42d3-a456-426614174000",
      createdAt: Date.now(),
      phase: "unknown",
    });
    useExpertStore.getState().resetExpert();

    const { default: Home } = await import("@/app/page");
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(createElement(I18nProvider, null, createElement(Home)));
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(apiMocks.submitScenario).not.toHaveBeenCalled();
    expect(apiMocks.getSubmissionByIdempotencyKey).toHaveBeenCalledTimes(1);
    expect(useAppStore.getState().stage).toBe("generate");
    expect(container.textContent).toContain("原任务需要人工恢复");
    expect(container.textContent).toContain("继续查询");

    await act(async () => root.unmount());
    document.body.removeChild(container);
  });
});
