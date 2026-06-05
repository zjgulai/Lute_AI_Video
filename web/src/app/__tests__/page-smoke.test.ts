import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: () => null }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/",
  redirect: vi.fn(),
}));

vi.mock("@/components/api", () => ({
  hasApiKey: () => false,
  isDemoMode: () => true,
  isApiError: () => false,
  getMediaUrl: (p: string) => p,
  fetchState: vi.fn(),
  submitReview: vi.fn(),
  runS1ProductDirect: vi.fn(),
  runS5BrandVlog: vi.fn(),
  startS1StepByStep: vi.fn(),
  resumeS1: vi.fn(),
  fetchS1State: vi.fn(),
  submitScenario: vi.fn(),
  logStateChange: vi.fn(),
  fetchToolboxTools: vi.fn(),
  fetchToolboxRuns: vi.fn(),
}));

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

describe("D4 page-module smoke", () => {
  PAGE_MODULES.forEach(({ name, loader }) => {
    it(`${name}/page module loads + exports default function`, async () => {
      const mod = await loader();
      expect(mod).toBeTruthy();
      expect(typeof mod.default).toBe("function");
      expect(mod.default.name.length).toBeGreaterThan(0);
    });
  });

  it("all page modules expose stable default export shape", async () => {
    const all = await Promise.all(PAGE_MODULES.map(async ({ name, loader }) => {
      const mod = await loader();
      return { name, hasDefault: typeof mod.default === "function" };
    }));
    const failures = all.filter(r => !r.hasDefault);
    expect(failures, `pages without default function: ${JSON.stringify(failures)}`).toHaveLength(0);
  });
});
