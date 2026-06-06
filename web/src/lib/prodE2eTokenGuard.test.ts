import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

function readWebFile(path: string): string {
  return readFileSync(join(process.cwd(), path), "utf8");
}

function readRepoFileFromWeb(path: string): string {
  return readFileSync(join(process.cwd(), "..", path), "utf8");
}

const MUTATING_ENDPOINT_PATTERNS = [
  "/api/fast/submit",
  "/api/scenario/",
  "/api/pipeline/",
  "/api/distribution/",
  "/api/assets/upload",
  "/api/upload",
  "/api/files/upload",
  "/api/publish",
];

const SAFE_NEGATIVE_MUTATION_TEST_TITLES = new Set([
  "invalid video_duration string returns 422 with field-level detail",
  "fast/submit missing user_prompt returns 422",
  "fast/submit invalid duration type returns 422",
  "missing X-API-Key returns 401",
  "invalid X-API-Key returns 401",
  "malformed JSON body returns 422",
]);

function getProductionSpecFiles(): string[] {
  const productionDir = join(process.cwd(), "e2e/production");
  return readdirSync(productionDir)
    .filter((fileName) => fileName.endsWith(".prod.spec.ts"))
    .sort()
    .map((fileName) => `e2e/production/${fileName}`);
}

function extractTestBlocks(source: string): Array<{ title: string; body: string }> {
  const testPattern = /(?:^|\n)\s*test\(\s*(["'`])([^"'`]+)\1\s*,/g;
  const matches = Array.from(source.matchAll(testPattern));

  return matches.map((match, index) => {
    const nextMatch = matches[index + 1];
    return {
      title: match[2],
      body: source.slice(match.index ?? 0, nextMatch?.index ?? source.length),
    };
  });
}

function findRiskyMutatingRequests(body: string): string[] {
  const requestPattern = /request\.(post|put|patch|delete)\(\s*([`'"])([\s\S]*?)\2/g;
  return Array.from(body.matchAll(requestPattern))
    .map((match) => `${match[1].toUpperCase()} ${match[3]}`)
    .filter((requestCall) =>
      MUTATING_ENDPOINT_PATTERNS.some((endpointPattern) => requestCall.includes(endpointPattern)),
    );
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

  it("does not use demo key fallbacks inside production specs", () => {
    const forbiddenFallbacks = [
      "|| \"ai_video_demo_2026\"",
      "|| 'ai_video_demo_2026'",
      "?? \"ai_video_demo_2026\"",
      "?? 'ai_video_demo_2026'",
    ];

    for (const specPath of getProductionSpecFiles()) {
      const source = readWebFile(specPath);
      for (const fallback of forbiddenFallbacks) {
        expect(source, `${specPath} must use production helpers instead of demo key fallback`).not.toContain(fallback);
      }
    }
  });

  it("skips authenticated production checks when only the demo key is present", () => {
    const helper = readWebFile("e2e/production/helpers.ts");

    expect(helper).toContain("const DEMO_API_KEY = \"ai_video_demo_2026\"");
    expect(helper).toContain("hasNonDemoProductionApiKey");
    expect(helper).toContain("PRODUCTION_API_KEY !== DEMO_API_KEY");
    expect(helper).toContain("A non-demo PLAYWRIGHT_API_KEY is required");
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

  it("requires risky production mutations to be token-smoke or explicit negative tests", () => {
    const failures: string[] = [];
    const seenSafeNegativeTitles = new Set<string>();

    for (const specPath of getProductionSpecFiles()) {
      const source = readWebFile(specPath);

      for (const block of extractTestBlocks(source)) {
        const riskyRequests = findRiskyMutatingRequests(block.body);
        if (riskyRequests.length === 0 || block.title.includes("@token-smoke")) {
          continue;
        }

        if (SAFE_NEGATIVE_MUTATION_TEST_TITLES.has(block.title)) {
          seenSafeNegativeTitles.add(block.title);
          continue;
        }

        failures.push(`${specPath} :: "${block.title}" :: ${riskyRequests.join(", ")}`);
      }
    }

    expect(failures).toEqual([]);
    expect(
      Array.from(SAFE_NEGATIVE_MUTATION_TEST_TITLES).filter((title) => !seenSafeNegativeTitles.has(title)),
    ).toEqual([]);
  });
});
