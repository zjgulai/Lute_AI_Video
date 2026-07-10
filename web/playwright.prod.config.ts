import { defineConfig, devices } from "@playwright/test";

const runTokenSmoke = ["1", "true", "yes"].includes((process.env.RUN_TOKEN_SMOKE || "").toLowerCase());
const workers = runTokenSmoke ? 1 : Number(process.env.PLAYWRIGHT_PROD_WORKERS || 1);
const chromiumExecutablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;

export default defineConfig({
  testDir: "./e2e/production",
  ...(runTokenSmoke ? {} : { grepInvert: /@token-smoke/ }),
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 1,
  workers,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_PROD_URL || "https://video.lute-tlz-dddd.top",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ignoreHTTPSErrors: true,
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
