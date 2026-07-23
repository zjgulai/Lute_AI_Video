import { expect, test } from "@playwright/test";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const tokenSmokeEnabled = ["1", "true", "yes"].includes(
  String(process.env.RUN_TOKEN_SMOKE ?? "").toLowerCase(),
);

function readRepoFile(path: string): string {
  return readFileSync(join(process.cwd(), "..", path), "utf8");
}

function extractSourceBlock(source: string, marker: string): string {
  const start = source.indexOf(marker);
  expect(start, `${marker} must exist`).toBeGreaterThanOrEqual(0);

  const tail = source.slice(start);
  const nextBlock = tail.slice(marker.length).search(/\n(?:class|async def|def|[A-Z0-9_]+ =) /);
  if (nextBlock === -1) {
    return tail;
  }
  return tail.slice(0, marker.length + nextBlock);
}

function productionSpecFiles(): string[] {
  return readdirSync(join(process.cwd(), "e2e/production")).sort();
}

test.describe("TODO-P1-5 S2 full-media segmented readiness", () => {
  test("proves S2 segmented stop-point contract exists without live submit", () => {
    expect(tokenSmokeEnabled, "readiness must run without token smoke").toBe(false);

    const requestModel = extractSourceBlock(
      readRepoFile("src/routers/_state.py"),
      "class S2BrandCampaignRequest",
    );
    const safetyModel = extractSourceBlock(
      readRepoFile("src/routers/_state.py"),
      "class GenerationSafetyRequest",
    );
    expect(requestModel).toContain("class S2BrandCampaignRequest(GenerationSafetyRequest)");
    expect(safetyModel).toContain(
      'artifact_disposition: ArtifactDisposition = "pending_review"',
    );
    expect(safetyModel).toContain(
      "provider_max_retries: Annotated[int, Field(strict=True, ge=0, le=0)] = 0",
    );
    expect(requestModel).toContain("output_label");
    expect(requestModel).toContain("media_stop_step");
    for (const stopStep of [
      "seedance_clips",
      "tts_audio",
      "thumbnail_prompts",
      "thumbnail_images",
      "assemble_final",
      "audit",
    ]) {
      expect(requestModel).toContain(`"${stopStep}"`);
    }

    const routerSource = extractSourceBlock(
      readRepoFile("src/routers/scenario.py"),
      "async def run_s2_brand_campaign",
    );
    expect(routerSource).toContain("media_stop_step=body.media_stop_step");

    const pipelineSource = readRepoFile("src/pipeline/s2_brand_pipeline_v2.py");
    expect(pipelineSource).toContain("S2_BOUNDED_MEDIA_STOP_STEP = \"seedance_clips\"");
    expect(pipelineSource).toContain("S2_BOUNDED_MEDIA_STEP_ORDER");
    expect(pipelineSource).toContain("S2_SEGMENTED_MEDIA_STOP_STEPS");
    expect(pipelineSource).toContain("S2_SEGMENTED_MEDIA_STEP_ORDERS");
    expect(pipelineSource).toContain("S2_SEGMENTED_MEDIA_PROVIDER_JOB_CAPS");
    expect(pipelineSource).toContain("_resolve_media_stop_step");
    expect(pipelineSource).toContain("bounded_media_stop_step");
    const policySource = readRepoFile("src/pipeline/generation_policy.py");
    expect(policySource).toContain('"tts_audio": MappingProxyType({"tts": 1})');
    expect(policySource).toContain('"thumbnail_images": MappingProxyType({"thumbnail": 1})');

    const scenarioOrder = readRepoFile("src/pipeline/scenario_config.py");
    for (const step of [
      "thumbnail_prompts",
      "seedance_clips",
      "tts_audio",
      "thumbnail_images",
      "assemble_final",
      "audit",
    ]) {
      expect(scenarioOrder, `S2 full order must include ${step}`).toContain(`"${step}"`);
    }

    const s1Pipeline = readRepoFile("src/pipeline/s1_product_pipeline.py");
    expect(s1Pipeline).toContain("tts_job_cap");
    expect(s1Pipeline).toContain("thumbnail_job_cap");
    expect(s1Pipeline).toContain("_artifact_media_output_dir(state, config, \"audio\")");
    expect(s1Pipeline).toContain("_artifact_media_output_dir(state, config, \"thumbnails\")");

    const boundedLiveSpec = readRepoFile(
      "web/e2e/production/scenario-s2-bounded-media-pilot-live.prod.spec.ts",
    );
    for (const forbiddenStep of [
      "thumbnail_prompts",
      "thumbnail_images",
      "tts_audio",
      "assemble_final",
      "audit",
    ]) {
      expect(boundedLiveSpec).toContain(`expectStepNotExecuted(steps, "${forbiddenStep}")`);
    }

    const thumbnailLiveSpec = readRepoFile(
      "web/e2e/production/scenario-s2-thumbnail-segment-live.prod.spec.ts",
    );
    expect(thumbnailLiveSpec).toContain(
      "single S2 segmented thumbnail submit stops after thumbnail_images @token-smoke",
    );
    expect(thumbnailLiveSpec).toContain("const thumbnailStopStep = \"thumbnail_images\"");
    expect(thumbnailLiveSpec).toContain("media_stop_step: thumbnailStopStep");
    expect(thumbnailLiveSpec).toContain("expect(body.provider_job_caps).toEqual({ thumbnail: 1 })");
    expect(thumbnailLiveSpec).toContain("expectPendingReviewThumbnailPaths(body.thumbnail_image_paths)");
    expect(thumbnailLiveSpec).toContain("request.get(`/api/scenario/s2/status/${runLabel}`");
    for (const forbiddenStep of [
      "keyframe_images",
      "seedance_clips",
      "tts_audio",
      "assemble_final",
      "audit",
    ]) {
      expect(thumbnailLiveSpec).toContain(`expectStepNotExecuted(steps, "${forbiddenStep}")`);
    }

    const thisSpec = readRepoFile(
      "web/e2e/production/scenario-s2-full-media-segmented-readiness.prod.spec.ts",
    );
    expect(thisSpec).not.toMatch(/request\.post\(/);

    const fullMediaLiveSpecs = productionSpecFiles().filter((fileName) =>
      fileName.includes("scenario-s2-full-media") && fileName.includes("live"),
    );
    expect(fullMediaLiveSpecs, "P1-5A must not add an S2 full-media live submit spec").toEqual([]);
  });
});
