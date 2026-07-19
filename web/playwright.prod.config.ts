import { defineConfig, devices } from "@playwright/test";

const runTokenSmoke = ["1", "true", "yes"].includes((process.env.RUN_TOKEN_SMOKE || "").toLowerCase());
const chromiumExecutablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
const tokenSmokeSpec = (process.env.PLAYWRIGHT_TOKEN_SMOKE_SPEC || "").trim();
const tokenSmokeSpecs = new Set([
  "e2e/production/fast-mode-single-submit.prod.spec.ts",
  "e2e/production/scenario-s1-no-media-single-submit.prod.spec.ts",
  "e2e/production/scenario-s2-no-media-single-submit.prod.spec.ts",
  "e2e/production/scenario-s3-no-media-single-submit.prod.spec.ts",
  "e2e/production/scenario-s4-no-media-single-submit.prod.spec.ts",
  "e2e/production/scenario-s5-no-media-single-submit.prod.spec.ts",
]);

if (runTokenSmoke && !tokenSmokeSpecs.has(tokenSmokeSpec)) {
  throw new Error(
    "RUN_TOKEN_SMOKE requires one validated PLAYWRIGHT_TOKEN_SMOKE_SPEC from the single-submit allowlist",
  );
}

const tokenSmokeTestMatch = tokenSmokeSpec.replace("e2e/production/", "");

export default defineConfig({
  testDir: "./e2e/production",
  ...(runTokenSmoke ? { testMatch: tokenSmokeTestMatch } : { grepInvert: /@token-smoke/ }),
  fullyParallel: !runTokenSmoke,
  forbidOnly: !!process.env.CI,
  retries: runTokenSmoke ? 0 : 1,
  workers: runTokenSmoke ? 1 : Number(process.env.PLAYWRIGHT_PROD_WORKERS || 1),
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_PROD_URL || "https://video.lute-tlz-dddd.top",
    trace: runTokenSmoke ? "off" : "retain-on-failure",
    screenshot: runTokenSmoke ? "off" : "only-on-failure",
    ignoreHTTPSErrors: !runTokenSmoke,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(chromiumExecutablePath
          ? { launchOptions: { executablePath: chromiumExecutablePath } }
          : {}),
      },
    },
  ],
});
