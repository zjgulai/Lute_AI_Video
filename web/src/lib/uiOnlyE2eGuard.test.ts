import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

function readProjectFile(path: string): string {
  return readFileSync(join(process.cwd(), path), "utf8");
}

describe("UI-only Playwright guardrails", () => {
  it("keeps the e2e:ui script isolated from production smoke", () => {
    const packageJson = JSON.parse(readProjectFile("package.json")) as {
      scripts?: Record<string, string>;
    };
    const uiConfig = readProjectFile("playwright.ui.config.ts");

    expect(packageJson.scripts?.["e2e:ui"]).toBe("playwright test --config=playwright.ui.config.ts");
    expect(uiConfig).toContain('testDir: "./e2e/ui-only"');
    expect(uiConfig).toContain('baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000"');
    expect(uiConfig).not.toContain("PLAYWRIGHT_PROD_URL");
    expect(uiConfig).not.toContain("PLAYWRIGHT_API_KEY");
  });

  it("blocks token-consuming or mutating endpoints inside UI-only specs", () => {
    const spec = readProjectFile("e2e/ui-only/site-ui.visual.spec.ts");

    for (const token of [
      "GENERATION_ENDPOINT_PATTERNS",
      String.raw`/\/fast\/`,
      String.raw`/\/scenario\/`,
      String.raw`/\/pipeline\/`,
      String.raw`/\/distribution\/publish`,
      String.raw`/\/publish\/`,
      String.raw`/\/api\/upload`,
      "status: 451",
      "ui_only_fake_key",
      "ai_video_demo_mode",
    ]) {
      expect(spec).toContain(token);
    }
  });

  it("runs UI-only CI without production secrets", () => {
    const workflow = readFileSync(join(process.cwd(), "../.github/workflows/e2e-ui.yml"), "utf8");

    expect(workflow).toContain("runs-on: macos-latest");
    expect(workflow).toContain('NEXT_PUBLIC_IS_DEMO: "true"');
    expect(workflow).toContain("npm run e2e:ui -- --reporter=list,html");
    expect(workflow).not.toContain("secrets.");
    expect(workflow).not.toContain("PLAYWRIGHT_API_KEY");
    expect(workflow).not.toContain("PLAYWRIGHT_PROD_URL");
    expect(workflow).not.toContain("e2e:prod");
  });
});
