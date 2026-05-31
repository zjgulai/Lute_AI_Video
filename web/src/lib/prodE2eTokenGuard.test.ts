import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

function readWebFile(path: string): string {
  return readFileSync(join(process.cwd(), path), "utf8");
}

function readRepoFileFromWeb(path: string): string {
  return readFileSync(join(process.cwd(), "..", path), "utf8");
}

describe("Production E2E token smoke guardrails", () => {
  it("skips token-smoke specs by default", () => {
    const config = readWebFile("playwright.prod.config.ts");

    expect(config).toContain("RUN_TOKEN_SMOKE");
    expect(config).toContain("grepInvert: /@token-smoke/");
  });

  it("requires explicit workflow opt-in for token-smoke specs", () => {
    const workflow = readRepoFileFromWeb(".github/workflows/e2e-prod.yml");

    expect(workflow).toContain("run_token_smoke");
    expect(workflow).toContain("RUN_TOKEN_SMOKE");
    expect(workflow).toContain("Verify token smoke opt-in key");
    expect(workflow).toContain("PROD_DEMO_API_KEY");
    expect(workflow).toContain("non-demo production key");
  });

  it("documents production token-smoke secret and manual opt-in", () => {
    const runbook = readRepoFileFromWeb("docs/runbooks/production-e2e-token-smoke.md");
    const demoKey = ["ai", "video", "demo", "2026"].join("_");

    for (const token of [
      "PROD_DEMO_API_KEY",
      "run_token_smoke",
      "RUN_TOKEN_SMOKE=1",
      "@token-smoke",
      demoKey,
      "only after recharge",
    ]) {
      expect(runbook).toContain(token);
    }
  });

  it("tags known production specs that create real backend tasks", () => {
    const expectedTaggedTests: Record<string, string[]> = {
      "e2e/production/fast-mode-submit.prod.spec.ts": [
        "POST /api/fast/submit returns task_id quickly (~2-5s) @token-smoke",
        "submit + status round-trip — task is queryable + has stage field @token-smoke",
      ],
      "e2e/production/user-journey.prod.spec.ts": [
        "step 4: backend submits async task and returns task_id < 5s @token-smoke",
        "step 5: status endpoint reflects progress @token-smoke",
      ],
      "e2e/production/s1-gate.prod.spec.ts": [
        "step 1: start S1 and run strategy step without INTEGRATION-3 regression @token-smoke",
        "step 2: gate exists after strategy and exposes 3 candidates @token-smoke",
      ],
      "e2e/production/s1-step-by-step.prod.spec.ts": [
        "POST /api/scenario/s1/start returns label @token-smoke",
        "POST /api/scenario/s1/step/strategy completes successfully (no missing-name error) @token-smoke",
      ],
    };

    for (const [path, taggedTitles] of Object.entries(expectedTaggedTests)) {
      const spec = readWebFile(path);
      for (const title of taggedTitles) {
        expect(spec).toContain(title);
      }
    }
  });
});
