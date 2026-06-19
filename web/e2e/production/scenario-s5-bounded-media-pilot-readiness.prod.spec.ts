import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expectOkJsonWith429Retry } from "./helpers";

const tokenSmokeEnabled = ["1", "true", "yes"].includes(
  String(process.env.RUN_TOKEN_SMOKE ?? "").toLowerCase(),
);
const maxSubmitCount = Number(process.env.PLAYWRIGHT_MAX_SUBMIT_COUNT ?? "1");
const providerMaxRetries = Number(process.env.PLAYWRIGHT_PROVIDER_MAX_RETRIES ?? "0");
const artifactDisposition = process.env.PLAYWRIGHT_ARTIFACT_DISPOSITION ?? "pending_review";

const s5BoundedMediaPilotPayload = Object.freeze({
  brand_id: "momcozy",
  product_sku: {
    name: "Momcozy bottle sterilizer",
    shortName: "Sterilizer",
    views: [
      {
        label: "主视图",
        title: "Front View",
        imagePath: "tenants/momcozy-marketing/pending_review/l4d_image_only_20260612043209/main_45.png",
      },
    ],
  },
  scene_id: "living-room",
  selected_models: [
    {
      name: "Sarah",
      role: "new mom",
      description: "Warm lifestyle product demonstrator.",
    },
  ],
  story_description: "A calm day-in-the-life product vlog.",
  video_duration: 15,
  output_label: "s5_bounded_media_readiness_only",
  enable_media_synthesis: true,
  artifact_disposition: artifactDisposition,
  provider_max_retries: providerMaxRetries,
  commercial_injection_plan: null,
});

function readRepoFile(path: string): string {
  return readFileSync(join(process.cwd(), "..", path), "utf8");
}

function extractSourceBlock(source: string, marker: string): string {
  const start = source.indexOf(marker);
  expect(start, `${marker} must exist`).toBeGreaterThanOrEqual(0);

  const tail = source.slice(start);
  const nextBlock = tail.slice(marker.length).search(/\n(?:class|async def|def) /);
  if (nextBlock === -1) {
    return tail;
  }
  return tail.slice(0, marker.length + nextBlock);
}

test.describe("TODO-P1-4-prep S5 bounded media pilot readiness", () => {
  test("dry-run readiness keeps S5 media pilot blocked before live submit", async ({ request }) => {
    expect(tokenSmokeEnabled).toBe(false);
    expect(maxSubmitCount).toBe(1);
    expect(providerMaxRetries).toBe(0);
    expect(artifactDisposition).toBe("pending_review");
    expect(s5BoundedMediaPilotPayload).not.toHaveProperty("api_keys");
    expect(s5BoundedMediaPilotPayload.enable_media_synthesis).toBe(true);
    expect(s5BoundedMediaPilotPayload.video_duration).toBe(15);

    const requestModelSource = extractSourceBlock(readRepoFile("src/routers/_state.py"), "class S5BrandVlogRequest");
    expect(requestModelSource).toContain("artifact_disposition: Literal[\"default\", \"pending_review\", \"quarantine\"]");
    expect(requestModelSource).toContain("provider_max_retries");
    expect(requestModelSource).toContain("output_label: str | None = None");

    const routerSource = readRepoFile("src/routers/scenario.py");
    const directSubmitBlock = extractSourceBlock(routerSource, "async def run_s5_brand_vlog");
    expect(directSubmitBlock).toContain("body: S5BrandVlogRequest");
    expect(directSubmitBlock).toContain("body.artifact_disposition");
    expect(directSubmitBlock).toContain("body.provider_max_retries");
    expect(directSubmitBlock).toContain("output_label=body.output_label");
    expect(directSubmitBlock).toContain("provider_max_retries=effective_provider_max_retries");

    const s5PipelineSource = readRepoFile("src/pipeline/s5_brand_vlog_pipeline.py");
    expect(s5PipelineSource).toContain("S5_BOUNDED_MEDIA_STOP_STEP = \"seedance_clips\"");
    expect(s5PipelineSource).toContain("S5_BOUNDED_MEDIA_STEP_ORDER");
    expect(s5PipelineSource).toContain("\"provider_job_caps\": {\"image\": 1, \"video\": 1}");
    expect(s5PipelineSource).toContain("\"seedance_quality_gate_enabled\": False");
    expect(s5PipelineSource).toContain("if bounded_media_pilot:");
    expect(s5PipelineSource).toContain("\"final_video_path\": \"\"");
    expect(s5PipelineSource).toContain("\"publish_allowed\": False");
    expect(s5PipelineSource).toContain("\"approved_brand_token_write\": False");
    expect(s5PipelineSource).toContain("provider_max_retries=config.get(\"provider_max_retries\")");
    expect(s5PipelineSource).toContain("video_job_cap");
    expect(s5PipelineSource).toContain("OUTPUT_DIR / \"tenants\" / tenant_id / disposition / label / media_kind");

    const health = await expectOkJsonWith429Retry(request, "/api/health", {
      attempts: 2,
      waitMs: 500,
    });
    expect((health as { status?: string }).status).toBe("ok");
  });
});
