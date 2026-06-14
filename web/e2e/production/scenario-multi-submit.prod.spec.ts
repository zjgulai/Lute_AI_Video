/**
 * P4-5 — Production multi-scenario smoke.
 *
 * Covers minimum acceptance for S2/S3/S4/S5 via token-smoke approved paths:
 * - S2 uses direct endpoint to avoid unnecessary media spend
 * - S3/S4/S5 use async submit + status readback for non-blocking smoke
 */
import { test, expect, type APIRequestContext, type APIResponse } from "@playwright/test";
import { productionApiHeaders } from "./helpers";

type ScenarioStatusResponse = {
  label: string;
  scenario: string;
  status: string;
};

type ScenarioStatusEnvelope = {
  status: "queued" | "running" | "completed" | "error" | "paused";
  scenario?: string;
  label?: string;
};

type PollOptions = {
  maxAttempts?: number;
  intervalMs?: number;
};

async function pollScenarioStatus(
  request: APIRequestContext,
  scenario: string,
  label: string,
  options: PollOptions = {},
): Promise<ScenarioStatusResponse> {
  const { maxAttempts = 4, intervalMs = 1500 } = options;
  let lastResponse: APIResponse | null = null;

  for (let i = 0; i < maxAttempts; i += 1) {
    const resp = await request.get(`/api/scenario/${scenario}/status/${label}`, {
      headers: productionApiHeaders(),
      timeout: 10_000,
    });
    lastResponse = resp;

    if (resp.status() === 429) {
      if (i < maxAttempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, intervalMs * (i + 1)));
        continue;
      }
      throw new Error(`/scenario/${scenario}/status/${label} remained 429`);
    }

    expect(resp.status(), `/scenario/${scenario}/status/${label}`).toBe(200);
    const body = (await resp.json()) as ScenarioStatusEnvelope;
    expect(["running", "completed", "error", "paused"].includes(body.status)).toBe(true);
    return {
      label,
      scenario: body.scenario ?? scenario,
      status: body.status,
    };
  }

  if (lastResponse) {
    expect(lastResponse.status(), "scenario status retry exhausted").toBe(200);
  }
  throw new Error(`pollScenarioStatus did not return valid status for ${scenario}/${label}`);
}

test.describe("P4-5 — Multi-scenario production smoke", () => {
  test("POST /api/scenario/s2 with enable_media_synthesis=false returns brand campaign result @token-smoke", async ({ request }) => {
    const payload = {
      brand_package: {
        brand_name: "Momcozy",
        values: ["safety", "comfort", "parent trust"],
        voice_guidelines: "warm, practical, no exaggeration",
      },
      target_platforms: ["tiktok"],
      video_duration: 15,
      enable_media_synthesis: false,
      commercial_injection_plan: null,
    };

    const resp = await request.post("/api/scenario/s2", {
      headers: productionApiHeaders({ "Content-Type": "application/json" }),
      data: payload,
      timeout: 90_000,
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();

    expect(typeof body.success).toBe("boolean");
    expect(body.scenario).toBe("brand_campaign");
    expect(Array.isArray(body.briefs)).toBe(true);
    expect(body.brand_name).toBe("Momcozy");
  });

  test("POST /api/scenario/s3/submit then /api/scenario/s3/status/{label} round-trip @token-smoke", async ({ request }) => {
    const submitResp = await request.post("/api/scenario/s3/submit", {
      headers: productionApiHeaders({ "Content-Type": "application/json" }),
      data: {
        product: {
          name: "Momcozy UV Sterilizer",
          usps: ["quiet operation", "safe heating"],
          category: "maternity",
          target_audience: "new moms",
          brand_name: "Momcozy",
        },
        video_url: "https://www.tiktok.com/@momcozy/video/1000000000",
        influencer_name: "Tester",
        video_duration: 15,
      },
      timeout: 30_000,
    });
    expect(submitResp.status()).toBe(200);
    const submitBody = await submitResp.json();
    const label = submitBody.label;
    expect(label).toMatch(/^s3_\d+/);

    const status = await pollScenarioStatus(request, "s3", label, {
      maxAttempts: 5,
      intervalMs: 1800,
    });
    expect(["running", "error", "completed", "paused"].includes(status.status)).toBe(true);
    expect(status.scenario).toBe("s3");
    expect(status.label).toBe(label);
  });

  test("POST /api/scenario/s4/submit then /api/scenario/s4/status/{label} round-trip @token-smoke", async ({ request }) => {
    const submitResp = await request.post("/api/scenario/s4/submit", {
      headers: productionApiHeaders({ "Content-Type": "application/json" }),
      data: {
        product_info: {
          name: "Momcozy UV Sterilizer",
          brand_name: "Momcozy",
          usps: ["auto UV", "quiet"],
          usage_scenario: "kitchen hygiene",
        },
        footage_assets: [],
        target_platforms: ["tiktok"],
        topic: "15秒品牌功能展示",
      },
      timeout: 30_000,
    });
    expect(submitResp.status()).toBe(200);
    const submitBody = await submitResp.json();
    const label = submitBody.label;
    expect(label).toMatch(/^s4_\d+/);

    const status = await pollScenarioStatus(request, "s4", label, {
      maxAttempts: 5,
      intervalMs: 1800,
    });
    expect(["running", "error", "completed", "paused"].includes(status.status)).toBe(true);
    expect(status.scenario).toBe("s4");
    expect(status.label).toBe(label);
  });

  test("POST /api/scenario/s5/submit then /api/scenario/s5/status/{label} round-trip @token-smoke", async ({ request }) => {
    const submitResp = await request.post("/api/scenario/s5/submit", {
      headers: productionApiHeaders({ "Content-Type": "application/json" }),
      data: {
        brand_id: "momcozy",
        video_duration: 15,
        scene_id: "kitchen",
        selected_models: [
          {
            name: "温馨妈妈",
            role: "解说人",
            description: "语气自然，强调产品安全和效率",
          },
        ],
        story_description: "三十秒内展示消毒、使用、清洁与易收纳场景",
        product_sku: {
          name: "Momcozy UV Sterilizer",
          shortName: "Momcozy",
          views: [
            { label: "主视图", title: "主视图", usage_note: "开箱与产品主体" },
            { label: "45度", title: "45°", usage_note: "细节展示" },
            { label: "生活场景", title: "厨房场景", usage_note: "厨房日常应用" },
          ],
          tags: ["sterilizer", "baby", "home"],
        },
      },
      timeout: 30_000,
    });
    expect(submitResp.status()).toBe(200);
    const submitBody = await submitResp.json();
    const label = submitBody.label;
    expect(label).toMatch(/^vlog_\d+/);

    const status = await pollScenarioStatus(request, "s5", label, {
      maxAttempts: 5,
      intervalMs: 1800,
    });
    expect(["running", "error", "completed", "paused"].includes(status.status)).toBe(true);
    expect(status.scenario).toBe("s5");
    expect(status.label).toBe(label);
  });
});
