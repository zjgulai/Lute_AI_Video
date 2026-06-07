/**
 * P4-6 — Production library / portfolio coverage for pending-review assets.
 *
 * Validates the boundary:
 * - authorized production key required
 * - /api/portfolio kind filters (creation_intermediate / final_work) are respected
 * - Momcozy authorized live pending-review samples are visible on /library Materials
 */
import { expect, type APIRequestContext, test } from "@playwright/test";
import { expectOkJsonWith429Retry, hasNonDemoProductionApiKey, productionApiHeaders } from "./helpers";

type PortfolioItem = {
  id: string;
  category: string;
  kind: "final_work" | "creation_intermediate" | "brand_kit";
  review_status?: "pending_review" | null;
  mime_type: string;
};

type PortfolioResponse = {
  total: number;
  files: PortfolioItem[];
};

async function getPortfolio(request: APIRequestContext, path: string): Promise<PortfolioResponse> {
  const body = await expectOkJsonWith429Retry(request, path, {
    headers: productionApiHeaders(),
    attempts: 4,
    waitMs: 1000,
  });
  const response = body as PortfolioResponse;
  expect(response).toHaveProperty("files");
  expect(Array.isArray(response.files)).toBe(true);
  expect(response).toHaveProperty("total");
  return response;
}

function isLibraryPendingReviewBadgeVisible(page: {
  getByText: (v: RegExp | string) => { count: () => Promise<number> };
}): Promise<number> {
  return page.getByText(/Pending review|待审/i).count();
}

test.describe("P4-6 — Library /portfolio boundary", () => {
  test("creation_intermediate should expose pending_review assets after authorized-live smoke", async ({ request }) => {
    test.skip(
      !hasNonDemoProductionApiKey(),
      "A non-demo PLAYWRIGHT_API_KEY is required for authenticated production API assertions.",
    );

    const intermediate = await getPortfolio(
      request,
      "/api/portfolio/?kind=creation_intermediate&limit=500&sort=size_desc",
    );
    const pending = intermediate.files.filter((item) => item.review_status === "pending_review");
    if (pending.length === 0) {
      test.skip(true, "No pending_review assets found in creation_intermediate; run authorized-live smoke first.");
    }

    expect(intermediate.total).toBeGreaterThanOrEqual(intermediate.files.length);
    expect(new Set(intermediate.files.map((item) => item.kind)).has("creation_intermediate")).toBe(true);
    expect(pending.every((item) => item.kind === "creation_intermediate")).toBe(true);
    expect(pending.every((item) => item.review_status === "pending_review")).toBe(true);
    expect(new Set(pending.map((item) => item.category)).size).toBeGreaterThan(0);

    const finalWork = await getPortfolio(request, "/api/portfolio/?kind=final_work&limit=500&sort=size_desc");
    expect(new Set(finalWork.files.map((item) => item.review_status || "final-work")).has("pending_review")).toBe(false);
  });

  test("library Materials tab renders pending_review media cards as read-only evidence", async ({ page }) => {
    test.skip(
      !hasNonDemoProductionApiKey(),
      "A non-demo PLAYWRIGHT_API_KEY is required for production library browser assertions.",
    );

    const mutatedCalls: string[] = [];
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      if (request.method() !== "GET") {
        mutatedCalls.push(`${request.method()} ${request.url()}`);
      }
      await route.continue();
    });

    await page.addInitScript((apiKey) => {
      localStorage.setItem("ai_video_api_key", apiKey);
      localStorage.setItem("ai_video_demo_mode", "true");
      localStorage.setItem("app-locale", "en");
    }, productionApiHeaders()["X-API-Key"]);

    await page.goto("/library?tab=materials", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 12000 }).catch(() => {});

    const tab = page.getByRole("tab", { name: /Materials|素材|材料/i });
    await expect(tab).toBeVisible();
    await expect(page.getByText(/Materials|素材/i).first()).toBeVisible();
    const pendingCards = page.locator('[data-review-status="pending_review"]');
    await expect(pendingCards).not.toHaveCount(0, { timeout: 18000 });
    const intermediateCards = page.locator('[data-kind="creation_intermediate"]');
    await expect(intermediateCards).not.toHaveCount(0, { timeout: 18000 });

    const badgeCount = await isLibraryPendingReviewBadgeVisible(page);
    expect(badgeCount).toBeGreaterThan(0);
    expect(mutatedCalls).toEqual([]);
  });
});
