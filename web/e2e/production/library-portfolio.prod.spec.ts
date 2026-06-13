/**
 * P4-6 — Production library / portfolio coverage for pending-review assets.
 *
 * Validates the boundary:
 * - authorized production key required
 * - /api/portfolio kind filters (creation_intermediate / final_work) are respected
 * - Momcozy authorized live pending-review samples are visible on /library Materials when L4A evidence exists
 */
import { expect, type APIRequestContext, test } from "@playwright/test";
import { expectOkJsonWith429Retry, hasNonDemoProductionApiKey, productionApiHeaders } from "./helpers";

type PortfolioItem = {
  id: string;
  filename?: string;
  path: string;
  category: string;
  kind: "final_work" | "creation_intermediate" | "brand_kit";
  review_status?: "pending_review" | null;
  mime_type: string;
  size_bytes: number;
  thumbnail_path?: string | null;
  tenant_id?: string | null;
};

type PortfolioResponse = {
  total: number;
  files: PortfolioItem[];
};

type ExpectedPendingReviewTarget = {
  name: string;
  path: string;
  mimeType: string;
  sizeBytes?: number;
  thumbnailPath?: string;
};

const L4D5T_RUN_LABEL = "l4d5s_s2_bounded_transport_20260613035940";
const L4D5T_VIDEO_FILENAME = "seedance_MPWSA7M7_f054.mp4";
const L4D5T_KEYFRAME_FILENAME = "poyo_img_keyframe_script-BRIEF-001-en_000_d8ce.png";
const L4D5T_POSTER_CACHE_FILENAME =
  `tenants__momcozy-marketing__pending_review__${L4D5T_RUN_LABEL}__clips__seedance_MPWSA7M7_f054.jpg`;
const L4D5T_POSTER_CACHE_PATH =
  `thumbnails/portfolio_posters/${L4D5T_POSTER_CACHE_FILENAME}`;

const boundedRunLabel = process.env.PLAYWRIGHT_LIBRARY_BOUNDED_RUN_LABEL ?? L4D5T_RUN_LABEL;
const boundedVideoFilename = process.env.PLAYWRIGHT_LIBRARY_BOUNDED_VIDEO_FILENAME ?? L4D5T_VIDEO_FILENAME;
const boundedKeyframeFilename = process.env.PLAYWRIGHT_LIBRARY_BOUNDED_KEYFRAME_FILENAME
  ?? L4D5T_KEYFRAME_FILENAME;
const boundedVideoPath = `tenants/momcozy-marketing/pending_review/${boundedRunLabel}/clips/${boundedVideoFilename}`;
const boundedKeyframePath =
  `tenants/momcozy-marketing/pending_review/${boundedRunLabel}/keyframes/${boundedKeyframeFilename}`;
const boundedPosterCacheFilename = process.env.PLAYWRIGHT_LIBRARY_BOUNDED_POSTER_CACHE_FILENAME
  ?? (boundedRunLabel === L4D5T_RUN_LABEL
    ? L4D5T_POSTER_CACHE_FILENAME
    : `tenants__momcozy-marketing__pending_review__${boundedRunLabel}__clips__${boundedVideoFilename.replace(/\.mp4$/i, ".jpg")}`);
const boundedPosterCachePath = process.env.PLAYWRIGHT_LIBRARY_BOUNDED_POSTER_CACHE_PATH
  ?? (boundedRunLabel === L4D5T_RUN_LABEL
    ? L4D5T_POSTER_CACHE_PATH
    : `thumbnails/portfolio_posters/${boundedPosterCacheFilename}`);
const boundedThumbnailRequired =
  boundedRunLabel === L4D5T_RUN_LABEL || process.env.PLAYWRIGHT_LIBRARY_BOUNDED_REQUIRE_THUMBNAIL === "1";
const boundedThumbnailPath = process.env.PLAYWRIGHT_LIBRARY_BOUNDED_THUMBNAIL_PATH
  ?? (boundedThumbnailRequired ? boundedPosterCachePath : undefined);

const FRONTEND_PRODUCTION_API_ALLOWLIST = new Set(["/api/portfolio"]);
const FRONTEND_STUBBED_JSON_ENDPOINTS = new Set(["/api/admin/auth/session", "/api/health", "/health"]);
const FRONTEND_STUBBED_MEDIA_PREFIX = "/api/media/";
const TRANSPARENT_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lwWZLwAAAABJRU5ErkJggg==";
const FRONTEND_FORBIDDEN_PATH_PATTERNS = [
  /^\/api\/scenario(?:\/|$)/,
  /^\/api\/fast(?:\/|$)/,
  /^\/api\/generate(?:\/|$)/,
  /^\/api\/pipeline(?:\/|$)/,
  /^\/api\/distribution(?:\/|$)/,
  /^\/api\/publish(?:\/|$)/,
  /^\/api\/assets\/upload(?:\/|$)/,
  /^\/api\/upload(?:\/|$)/,
  /^\/api\/files\/upload(?:\/|$)/,
  /provider|poyo|seedance|tts|assemble|media_quality_audit|gate|delivery|approved_brand_token/i,
];

const L4D_PENDING_REVIEW_TARGETS: ExpectedPendingReviewTarget[] = [
  {
    name: "L4D-2 video-only Seedance output",
    path: "tenants/momcozy-marketing/pending_review/l4d_video_only_20260612160601/seedance_video.mp4",
    mimeType: "video/mp4",
    sizeBytes: 2474327,
  },
  {
    name: "L4D-3 paired image output",
    path: "tenants/momcozy-marketing/pending_review/l4d_paired_20260612162837/paired_image.png",
    mimeType: "image/png",
    sizeBytes: 1667434,
  },
  {
    name: "L4D-3 paired video output",
    path: "tenants/momcozy-marketing/pending_review/l4d_paired_20260612162837/paired_video.mp4",
    mimeType: "video/mp4",
    sizeBytes: 2298916,
  },
  {
    name: `bounded media Seedance clip (${boundedRunLabel})`,
    path: boundedVideoPath,
    mimeType: "video/mp4",
    thumbnailPath: boundedThumbnailPath,
  },
  {
    name: `bounded media keyframe (${boundedRunLabel})`,
    path: boundedKeyframePath,
    mimeType: "image/png",
  },
];

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

function findPortfolioMatches(files: PortfolioItem[], path: string): PortfolioItem[] {
  return files.filter((item) => item.path === path);
}

function normalizeEndpointPath(pathname: string): string {
  return pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
}

function isFrontendApiEndpoint(pathname: string): boolean {
  return pathname.startsWith("/api/") || pathname === "/health";
}

function isStubbedFrontendEndpoint(pathname: string): boolean {
  return FRONTEND_STUBBED_JSON_ENDPOINTS.has(pathname) || pathname.startsWith(FRONTEND_STUBBED_MEDIA_PREFIX);
}

function isForbiddenFrontendEndpoint(pathname: string): boolean {
  return FRONTEND_FORBIDDEN_PATH_PATTERNS.some((pattern) => pattern.test(pathname));
}

async function getPendingReviewIntermediates(request: APIRequestContext): Promise<PortfolioItem[]> {
  const intermediate = await getPortfolio(
    request,
    "/api/portfolio/?kind=creation_intermediate&limit=500&sort=size_desc",
  );
  return intermediate.files.filter((item) => item.review_status === "pending_review");
}

test.describe("P4-6 — Library /portfolio boundary", () => {
  test("L4D pending_review assets are visible and absent from final_work", async ({ request }) => {
    test.skip(
      !hasNonDemoProductionApiKey(),
      "A non-demo PLAYWRIGHT_API_KEY is required for authenticated production API assertions.",
    );

    const pending = await getPortfolio(
      request,
      "/api/portfolio/?category=pending_review&kind=creation_intermediate&limit=500&sort=recent",
    );
    const intermediate = await getPortfolio(
      request,
      "/api/portfolio/?kind=creation_intermediate&limit=500&sort=size_desc",
    );
    const finalWork = await getPortfolio(request, "/api/portfolio/?kind=final_work&limit=500&sort=recent");

    for (const target of L4D_PENDING_REVIEW_TARGETS) {
      const matches = findPortfolioMatches(pending.files, target.path);
      expect(matches, `${target.name} should appear once in pending_review`).toHaveLength(1);
      const match = matches[0];
      expect(match.category, `${target.name} category`).toBe("pending_review");
      expect(match.kind, `${target.name} kind`).toBe("creation_intermediate");
      expect(match.review_status, `${target.name} review_status`).toBe("pending_review");
      expect(match.tenant_id, `${target.name} tenant_id`).toBe("momcozy-marketing");
      expect(match.mime_type, `${target.name} mime_type`).toBe(target.mimeType);
      if (target.sizeBytes !== undefined) {
        expect(match.size_bytes, `${target.name} size_bytes`).toBe(target.sizeBytes);
      } else {
        expect(match.size_bytes, `${target.name} size_bytes`).toBeGreaterThan(0);
      }
      if (target.thumbnailPath) {
        expect(match.thumbnail_path, `${target.name} thumbnail_path`).toBe(target.thumbnailPath);
      }

      const finalMatches = findPortfolioMatches(finalWork.files, target.path);
      expect(finalMatches, `${target.name} must not appear in final_work`).toHaveLength(0);
    }

    expect(
      findPortfolioMatches(intermediate.files, L4D5T_POSTER_CACHE_PATH),
      "L4D-5T poster cache must not appear as an independent creation_intermediate asset",
    ).toHaveLength(0);
    expect(
      findPortfolioMatches(finalWork.files, L4D5T_POSTER_CACHE_PATH),
      "L4D-5T poster cache must not appear as a final_work asset",
    ).toHaveLength(0);
  });

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

  test("library Materials tab renders pending_review media cards as read-only evidence", async ({ page, request }) => {
    test.skip(
      !hasNonDemoProductionApiKey(),
      "A non-demo PLAYWRIGHT_API_KEY is required for production library browser assertions.",
    );

    const pending = await getPendingReviewIntermediates(request);
    if (pending.length === 0) {
      test.skip(true, "No pending_review assets found in creation_intermediate; run authorized-live smoke first.");
    }
    for (const path of [boundedVideoPath, boundedKeyframePath]) {
      expect(findPortfolioMatches(pending, path), `${path} must be available before UI readback`).toHaveLength(1);
    }

    const observedFrontendApiCalls: string[] = [];
    const disallowedFrontendApiCalls: string[] = [];
    await page.route("**/*", async (route) => {
      const routeRequest = route.request();
      const url = new URL(routeRequest.url());
      const pathname = normalizeEndpointPath(url.pathname);
      if (!isFrontendApiEndpoint(pathname)) {
        await route.continue();
        return;
      }

      const signature = `${routeRequest.method()} ${pathname}${url.search}`;
      observedFrontendApiCalls.push(signature);

      if (routeRequest.method() !== "GET") {
        disallowedFrontendApiCalls.push(signature);
        await route.abort("blockedbyclient");
        return;
      } else if (isStubbedFrontendEndpoint(pathname)) {
        if (pathname.startsWith(FRONTEND_STUBBED_MEDIA_PREFIX)) {
          await route.fulfill({
            status: 200,
            contentType: "image/png",
            body: Buffer.from(TRANSPARENT_PNG_BASE64, "base64"),
          });
          return;
        }
        await route.fulfill({
          status: pathname === "/api/admin/auth/session" ? 401 : 200,
          contentType: "application/json",
          body: pathname === "/api/admin/auth/session"
            ? '{"detail":"not authenticated"}'
            : '{"status":"ok","source":"playwright-stub"}',
        });
        return;
      } else if (isForbiddenFrontendEndpoint(pathname)) {
        disallowedFrontendApiCalls.push(signature);
        await route.abort("blockedbyclient");
        return;
      } else if (!FRONTEND_PRODUCTION_API_ALLOWLIST.has(pathname)) {
        disallowedFrontendApiCalls.push(signature);
        await route.abort("blockedbyclient");
        return;
      }

      await route.continue();
    });

    await page.addInitScript((apiKey) => {
      localStorage.setItem("ai_video_api_key", apiKey);
      localStorage.setItem("ai_video_api_base", "/api");
      localStorage.setItem("ai_video_demo_mode", "false");
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

    const search = page.locator("#materials-search");
    for (const filename of [boundedVideoFilename, boundedKeyframeFilename]) {
      await search.fill(filename);
      await expect(page.getByText(filename).first()).toBeVisible({ timeout: 12000 });
      await expect(page.locator('[data-review-status="pending_review"]')).not.toHaveCount(0);
    }

    await search.fill(boundedPosterCacheFilename);
    await expect(page.locator("[data-asset-card]")).toHaveCount(0);

    expect(observedFrontendApiCalls.some((call) => call.startsWith("GET /api/portfolio"))).toBe(true);
    expect(disallowedFrontendApiCalls).toEqual([]);
  });
});
