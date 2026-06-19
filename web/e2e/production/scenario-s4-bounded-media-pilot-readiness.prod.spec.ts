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

const s4BoundedMediaPilotPayload = Object.freeze({
  footage_assets: [
    {
      filename: "momcozy-countertop-demo.mp4",
      description: "Countertop baby bottle sterilizer live usage reference.",
    },
  ],
  product_info: {
    name: "Momcozy bottle sterilizer",
    brand_name: "Momcozy",
    usps: ["UV sterilizing", "countertop setup"],
  },
  topic: "Countertop sterilizer live shoot demo",
  target_platforms: ["tiktok"],
  video_duration: 15,
  output_label: "s4_bounded_media_readiness_only",
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

test.describe("TODO-P1-3-prep S4 bounded media pilot readiness", () => {
  test("dry-run readiness keeps S4 media pilot blocked before live submit", async ({ request }) => {
    expect(tokenSmokeEnabled).toBe(false);
    expect(maxSubmitCount).toBe(1);
    expect(providerMaxRetries).toBe(0);
    expect(artifactDisposition).toBe("pending_review");
    expect(s4BoundedMediaPilotPayload).not.toHaveProperty("api_keys");
    expect(s4BoundedMediaPilotPayload.enable_media_synthesis).toBe(true);
    expect(s4BoundedMediaPilotPayload.video_duration).toBe(15);

    const requestModelSource = extractSourceBlock(readRepoFile("src/routers/_state.py"), "class S4LiveShootRequest");
    expect(requestModelSource).toContain("artifact_disposition: Literal[\"default\", \"pending_review\", \"quarantine\"]");
    expect(requestModelSource).toContain("provider_max_retries");
    expect(requestModelSource).toContain("output_label: str | None = None");

    const routerSource = readRepoFile("src/routers/scenario.py");
    const directSubmitBlock = extractSourceBlock(routerSource, "async def run_s4_live_shoot");
    expect(directSubmitBlock).toContain("body: S4LiveShootRequest");
    expect(directSubmitBlock).toContain("body.artifact_disposition");
    expect(directSubmitBlock).toContain("body.provider_max_retries");
    expect(directSubmitBlock).toContain("output_label=body.output_label");
    expect(directSubmitBlock).toContain("provider_max_retries=effective_provider_max_retries");

    const s4PipelineSource = readRepoFile("src/pipeline/s4_live_shoot_pipeline.py");
    expect(s4PipelineSource).toContain("S4_BOUNDED_MEDIA_STOP_STEP = \"seedance_clips\"");
    expect(s4PipelineSource).toContain("S4_BOUNDED_MEDIA_STEP_ORDER");
    expect(s4PipelineSource).toContain("\"provider_job_caps\": {\"image\": 1, \"video\": 1}");
    expect(s4PipelineSource).toContain("\"seedance_quality_gate_enabled\": False");
    expect(s4PipelineSource).toContain("if bounded_media_pilot:");
    expect(s4PipelineSource).toContain("\"final_video_path\": \"\"");
    expect(s4PipelineSource).toContain("\"publish_allowed\": False");
    expect(s4PipelineSource).toContain("\"approved_brand_token_write\": False");
    expect(s4PipelineSource).toContain("provider_max_retries=config.get(\"provider_max_retries\")");
    expect(s4PipelineSource).toContain("video_job_cap");
    expect(s4PipelineSource).toContain("OUTPUT_DIR / \"tenants\" / tenant_id / disposition / label / media_kind");

    const health = await expectOkJsonWith429Retry(request, "/api/health", {
      attempts: 2,
      waitMs: 500,
    });
    expect((health as { status?: string }).status).toBe("ok");
  });
});
