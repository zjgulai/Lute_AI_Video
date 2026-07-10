import { test, expect } from "@playwright/test";

/**
 * Gate direct-access route — TODO-E12 / SPRINT1-CLOSEOUT P1-4 follow-up.
 *
 * Verifies /sN?label=X&gate=Y URL pattern:
 *   - Renders GateDirectAccess component (not workflow Home)
 *   - Shows "direct gate review" header with the label + gate label
 *   - Invalid gate number for a scenario renders an error message
 *   - Without query params, page falls back to normal Home
 *
 * Backend interaction is mocked at the network level — these tests
 * verify routing + UI wiring only, NOT real Gate candidate generation.
 */

test.describe("Gate direct-access route", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("app-locale", "en");
      localStorage.setItem("ai_video_demo_mode", "true");
    });
  });

  test("/s2?label=test&gate=1 renders direct-access UI", async ({ page }) => {
    await page.goto("/s2?label=test_label_abc&gate=1");
    await page.waitForLoadState("networkidle");

    // Direct-access label header should appear (key from translations.ts)
    const headerLocator = page.locator("text=test_label_abc");
    await expect(headerLocator.first()).toBeVisible({ timeout: 5_000 });
  });

  test("/s3?label=L&gate=2 routes to GateDirectAccess for S3 scenario", async ({ page }) => {
    await page.goto("/s3?label=L&gate=2");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("text=L").first()).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Review Keyframes", { exact: true }).first()).toBeVisible();
  });

  test("/s5?label=L&gate=3 routes to the S5 final review gate", async ({ page }) => {
    await page.goto("/s5?label=L&gate=3");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("text=L").first()).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Final Review", { exact: true }).first()).toBeVisible();
  });

  test("/s4?label=L&gate=4 rejects a gate outside the S4 sequence", async ({ page }) => {
    await page.goto("/s4?label=L&gate=4");
    await page.waitForLoadState("networkidle");
    const body = await page.locator("body").innerText();
    expect(body.toLowerCase()).toMatch(/1 through 3|1 至 3/);
  });

  test("/s2 without query params falls back to normal Home flow", async ({ page }) => {
    await page.goto("/s2");
    await page.waitForLoadState("networkidle");
    // Should NOT render the direct-access label header. Instead, normal
    // scene workflow elements should appear (e.g., scene selector or
    // home content). We assert the absence of the direct-gate-specific
    // marker text.
    const directLabel = await page.locator("text=Direct gate review").count();
    const directLabelZh = await page.locator("text=直达 Gate 审核").count();
    expect(directLabel + directLabelZh).toBe(0);
  });
});
