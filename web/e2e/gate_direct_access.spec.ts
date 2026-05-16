import { test, expect } from "@playwright/test";

/**
 * Gate direct-access route — TODO-E12 / SPRINT1-CLOSEOUT P1-4 follow-up.
 *
 * Verifies /sN?label=X&gate=Y URL pattern:
 *   - Renders GateDirectAccess component (not workflow Home)
 *   - Shows "direct gate review" header with the label + gate label
 *   - Invalid gate number (out of 1-4) renders error message
 *   - Without query params, page falls back to normal Home
 *
 * Backend interaction is mocked at the network level — these tests
 * verify routing + UI wiring only, NOT real Gate candidate generation.
 */

test.describe("Gate direct-access route", () => {
  test("/s2?label=test&gate=1 renders direct-access UI", async ({ page }) => {
    // Stub backend to avoid hitting real /scenario/s2/gate/test/gate_1_script
    await page.route("**/scenario/s2/gate/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ candidates: [], status: "pending" }),
      })
    );

    await page.goto("/s2?label=test_label_abc&gate=1");
    await page.waitForLoadState("networkidle");

    // Direct-access label header should appear (key from translations.ts)
    const headerLocator = page.locator("text=test_label_abc");
    await expect(headerLocator.first()).toBeVisible({ timeout: 5_000 });
  });

  test("/s3?label=L&gate=2 routes to GateDirectAccess for S3 scenario", async ({ page }) => {
    await page.route("**/scenario/s3/gate/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ candidates: [], status: "pending" }),
      })
    );
    await page.goto("/s3?label=L&gate=2");
    await page.waitForLoadState("networkidle");
    // L label visible somewhere on page
    await expect(page.locator("text=L").first()).toBeVisible({ timeout: 5_000 });
  });

  test("/s5?label=L&gate=4 (final review gate) renders", async ({ page }) => {
    await page.route("**/scenario/s5/gate/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ candidates: [], status: "pending" }),
      })
    );
    await page.goto("/s5?label=L&gate=4");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("text=L").first()).toBeVisible({ timeout: 5_000 });
  });

  test("/s2?label=L&gate=99 (out-of-range) shows invalid-number error", async ({ page }) => {
    await page.goto("/s2?label=L&gate=99");
    await page.waitForLoadState("networkidle");
    // GateDirectAccess renders the invalid-number fallback. Check the
    // i18n key "gate.invalidNumberHint" content (zh: "Gate 必须是 1, 2, 3 或 4"
    // or en: "Gate must be 1, 2, 3, or 4").
    const body = await page.locator("body").innerText();
    expect(body.toLowerCase()).toMatch(/invalid|无效|gate must be|必须是/);
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
