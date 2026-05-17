/**
 * P4-3 — i18n full-page walkthrough.
 * Sets localStorage["app-locale"] + app-locale cookie, then asserts CJK leak counts.
 * EN suite is regression-tracking (hard cap 50 CJK runs per page); ZH suite asserts crash-free.
 * Run: PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top npm run e2e:prod -- i18n
 */
import { test, expect, type Page } from "@playwright/test";

const PAGES_TO_AUDIT = ["/", "/s1", "/s2", "/s3", "/s4", "/s5", "/fast", "/works", "/library", "/settings"];

const CJK_RANGE = /[\u4e00-\u9fff]/;

async function setLocale(page: Page, locale: "zh" | "en") {
  const baseUrl = process.env.PLAYWRIGHT_PROD_URL || "https://video.lute-tlz-dddd.top";
  const url = new URL(baseUrl);
  await page.context().addCookies([
    { name: "app-locale", value: locale, domain: url.hostname, path: "/" },
  ]);
  await page.addInitScript((loc) => {
    try {
      localStorage.setItem("app-locale", loc);
    } catch {
      void 0;
    }
  }, locale);
}

async function getBodyText(page: Page): Promise<string> {
  return (await page.locator("body").textContent()) || "";
}

test.describe("P4-3 — i18n EN walkthrough (CJK leak audit)", () => {
  test.beforeEach(async ({ page }) => {
    await setLocale(page, "en");
  });

  for (const path of PAGES_TO_AUDIT) {
    test(`EN ${path} html.lang = en + leak count under hard cap`, async ({ page }) => {
      const resp = await page.goto(path, { waitUntil: "domcontentloaded" });
      expect(resp?.status()).toBeLessThan(400);
      await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => { void 0; });

      const htmlLang = await page.locator("html").getAttribute("lang");
      expect(htmlLang, `html.lang on ${path}`).toBe("en");

      const text = await getBodyText(page);
      const hits = (text.match(/[\u4e00-\u9fff]+/g) || []).filter((s) => s.trim().length > 0);

      const ALLOWED_LEAK_HARD_CAP = 50;
      expect(
        hits.length,
        `${path} leaked >=${ALLOWED_LEAK_HARD_CAP} CJK runs in EN (regression vs cardCopyEn baseline). Top 5: ${hits.slice(0, 5).join(" | ")}`,
      ).toBeLessThan(ALLOWED_LEAK_HARD_CAP);
    });
  }
});

test.describe("P4-3 — i18n ZH walkthrough renders without crash", () => {
  test.beforeEach(async ({ page }) => {
    await setLocale(page, "zh");
  });

  for (const path of PAGES_TO_AUDIT) {
    test(`ZH ${path} renders successfully`, async ({ page }) => {
      const resp = await page.goto(path, { waitUntil: "domcontentloaded" });
      expect(resp?.status()).toBeLessThan(400);
      await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => { void 0; });

      const htmlLang = await page.locator("html").getAttribute("lang");
      expect(htmlLang).toBe("zh-CN");

      const text = await getBodyText(page);
      expect(text.length, `${path} body must have content`).toBeGreaterThan(50);
      expect(CJK_RANGE.test(text), `${path} in ZH must contain Chinese`).toBe(true);
    });
  }
});
