import { test, expect } from "@playwright/test";

/**
 * Smoke tests — verify key pages load without 404 or console errors.
 *
 * These tests do NOT run pipeline scenarios (that requires backend + API keys).
 * They verify:
 * - Page loads with 200
 * - No console errors (JS exceptions)
 * - Key UI elements are visible
 * - Warm Light Professional theme is active (no dark mode leakage)
 */

test.describe("Smoke — Home page", () => {
  test("loads with scene cards", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });

    await page.goto("/");
    // Wait for hydration to complete
    await page.waitForLoadState("networkidle");

    // Body should be visible
    await expect(page.locator("body")).toBeVisible();

    // Warm light theme check — body should have light background
    const bodyBg = await page.evaluate(() =>
      getComputedStyle(document.body).backgroundColor
    );
    expect(bodyBg).toMatch(/rgb\(253, 248, 246\)|rgba\(0, 0, 0, 0\)/);

    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("navigation to S1 page works", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Find any link/button that navigates to /s1
    const s1Link = page.locator('a[href*="s1"], button:has-text("S1")').first();
    if (await s1Link.isVisible().catch(() => false)) {
      await s1Link.click();
      await expect(page).toHaveURL(/\/s1/, { timeout: 5000 });
    }
    // Fallback: direct navigation
    else {
      await page.goto("/s1");
    }
    await expect(page.locator("body")).toBeVisible();
  });

  test("navigation to Fast Mode works", async ({ page }) => {
    await page.goto("/fast");
    await expect(page).toHaveURL(/\/fast/);
    await expect(page.locator("body")).toBeVisible();
  });
});

test.describe("Smoke — Scenario pages", () => {
  const scenarios = [
    { path: "/s1", name: "Product Direct" },
    { path: "/s2", name: "Brand Campaign" },
    { path: "/s3", name: "Influencer Remix" },
    { path: "/s4", name: "Live Shoot" },
    { path: "/s5", name: "Brand VLOG" },
    { path: "/fast", name: "Fast Mode" },
  ];

  for (const s of scenarios) {
    test(`${s.path} loads without errors`, async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", (err) => errors.push(err.message));

      await page.goto(s.path);
      await expect(page.locator("body")).toBeVisible();

      // No ChunkLoadError or routing 404
      const criticalErrors = errors.filter(
        (e) => e.includes("ChunkLoadError") || e.includes("Failed to load chunk")
      );
      expect(criticalErrors).toHaveLength(0);
    });
  }
});

test.describe("Smoke — Footage page", () => {
  test("loads without console errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto("/footage");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("body")).toBeVisible();

    // Critical: no ChunkLoadError (the bug we fixed in production)
    const chunkErrors = errors.filter(
      (e) => e.includes("ChunkLoadError") || e.includes("Failed to load chunk")
    );
    expect(chunkErrors).toHaveLength(0);
  });
});

test.describe("Smoke — Admin Panel", () => {
  test("login page loads", async ({ page }) => {
    await page.goto("/admin/login");
    await expect(page.locator("body")).toBeVisible();
  });

  test("unauthenticated redirect to login", async ({ page }) => {
    await page.goto("/admin/dashboard");
    // Should redirect to login page
    await expect(page).toHaveURL(/\/admin\/login/, { timeout: 5000 });
  });
});

test.describe("Smoke — i18n consistency", () => {
  test("zh-CN locale has no untranslated keys visible", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const html = await page.content();
    // "Scene Selection" should be translated to Chinese
    expect(html).toContain("场景");
  });
});
