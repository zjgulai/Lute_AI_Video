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

const s1BoundedMediaPilotPayload = Object.freeze({
  product_catalog: {
    product_name: "Momcozy bottle sterilizer",
    category: "baby appliance",
  },
  brand_guidelines: {
    brand_name: "Momcozy",
  },
  target_platforms: ["tiktok"],
  video_duration: 15,
  enable_media_synthesis: true,
  artifact_disposition: artifactDisposition,
  provider_max_retries: providerMaxRetries,
  output_label: "s1_bounded_media_readiness_only",
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

test.describe("TODO-P1-1-prep S1 bounded media pilot readiness", () => {
  test("dry-run readiness keeps S1 media pilot blocked before live submit", async ({ request }) => {
    expect(tokenSmokeEnabled).toBe(false);
    expect(maxSubmitCount).toBe(1);
    expect(providerMaxRetries).toBe(0);
    expect(artifactDisposition).toBe("pending_review");
    expect(s1BoundedMediaPilotPayload).not.toHaveProperty("api_keys");
    expect(s1BoundedMediaPilotPayload.enable_media_synthesis).toBe(true);
    expect(s1BoundedMediaPilotPayload.video_duration).toBe(15);

    const stateModelSource = readRepoFile("src/routers/_state.py");
    const safetyModelSource = extractSourceBlock(
      stateModelSource,
      "class GenerationSafetyRequest",
    );
    const requestModelSource = extractSourceBlock(stateModelSource, "class S1StartRequest");
    expect(requestModelSource).toContain("class S1StartRequest(GenerationSafetyRequest)");
    expect(safetyModelSource).toContain(
      'artifact_disposition: ArtifactDisposition = "pending_review"',
    );
    expect(safetyModelSource).toContain(
      "provider_max_retries: Annotated[int, Field(strict=True, ge=0, le=0)] = 0",
    );
    expect(requestModelSource).toContain("output_label: str | None = None");
    expect(readRepoFile("src/pipeline/generation_policy.py")).toContain(
      'ArtifactDisposition = Literal["pending_review", "quarantine"]',
    );

    const routerSource = readRepoFile("src/routers/scenario.py");
    const directSubmitBlock = extractSourceBlock(routerSource, "async def run_s1_product_direct");
    expect(directSubmitBlock).toContain("body: S1StartRequest");
    expect(directSubmitBlock).toContain(
      '_resolve_request_generation_policy(body, scenario="s1")',
    );
    expect(directSubmitBlock).toContain('"artifact_disposition": policy.artifact_disposition');
    expect(directSubmitBlock).toContain(
      "effective_provider_max_retries = policy.provider_max_retries",
    );
    expect(directSubmitBlock).toContain("label = body.output_label");
    expect(directSubmitBlock).toContain("label=label");
    expect(directSubmitBlock).toContain("_resume_s1_bounded_media_pilot");
    expect(routerSource).toContain("S1_BOUNDED_MEDIA_STOP_STEP = \"seedance_clips\"");
    expect(routerSource).toContain("S1_BOUNDED_MEDIA_STEP_ORDER");
    expect(routerSource).toContain("\"provider_job_caps\": {\"image\": 1, \"video\": 1}");
    expect(routerSource).toContain("\"seedance_quality_gate_enabled\": False");
    expect(routerSource).toContain("result[\"final_video_path\"] = \"\"");
    expect(routerSource).toContain("result[\"publish_allowed\"] = False");
    expect(routerSource).toContain("result[\"approved_brand_token_write\"] = False");

    const s1PipelineSource = readRepoFile("src/pipeline/s1_product_pipeline.py");
    expect(s1PipelineSource).toContain("S1_BOUNDED_MEDIA_STOP_STEP = \"seedance_clips\"");
    expect(s1PipelineSource).toContain("S1_BOUNDED_MEDIA_STEP_ORDER");
    expect(s1PipelineSource).toContain("\"provider_job_caps\": {\"image\": 1, \"video\": 1}");
    expect(s1PipelineSource).toContain("\"seedance_quality_gate_enabled\": False");
    expect(s1PipelineSource).toContain("if bounded_media_pilot:");
    expect(s1PipelineSource).toContain("result[\"final_video_path\"] = \"\"");
    expect(s1PipelineSource).toContain("result[\"publish_allowed\"] = False");
    expect(s1PipelineSource).toContain("result[\"approved_brand_token_write\"] = False");
    expect(s1PipelineSource).toContain("provider_max_retries=config.get(\"provider_max_retries\")");
    expect(s1PipelineSource).toContain("image_job_cap");
    expect(s1PipelineSource).toContain("video_job_cap");
    expect(s1PipelineSource).toContain("quality_gate_enabled");

    const health = await expectOkJsonWith429Retry(request, "/api/health", {
      attempts: 2,
      waitMs: 500,
    });
    expect((health as { status?: string }).status).toBe("ok");
  });
});
