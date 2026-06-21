import { expect, test, type APIResponse } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { productionApiHeaders } from "./helpers";

const liveSpecFileName = "scenario-s2-thumbnail-segment-live.prod.spec.ts";
const thumbnailStopStep = "thumbnail_images";
const tokenSmokeEnabled = ["1", "true", "yes"].includes(
  String(process.env.RUN_TOKEN_SMOKE ?? "").toLowerCase(),
);
const maxSubmitCount = Number(process.env.PLAYWRIGHT_MAX_SUBMIT_COUNT ?? "1");
const providerMaxRetries = Number(process.env.PLAYWRIGHT_PROVIDER_MAX_RETRIES ?? "0");
const artifactDisposition = process.env.PLAYWRIGHT_ARTIFACT_DISPOSITION ?? "pending_review";
const explicitStopStep = process.env.PLAYWRIGHT_S2_SEGMENTED_MEDIA_STOP_STEP ?? thumbnailStopStep;
const submitTimeoutMs = Number(process.env.PLAYWRIGHT_S2_THUMBNAIL_SUBMIT_TIMEOUT_MS ?? String(10 * 60_000));

function readRepoFile(path: string): string {
  return readFileSync(join(process.cwd(), "..", path), "utf8");
}

function extractSourceBlock(source: string, marker: string): string {
  const start = source.indexOf(marker);
  expect(start, `${marker} must exist before live submit`).toBeGreaterThanOrEqual(0);

  const tail = source.slice(start);
  const nextBlock = tail.slice(marker.length).search(/\n(?:class|async def|def|[A-Z0-9_]+ =) /);
  if (nextBlock === -1) {
    return tail;
  }
  return tail.slice(0, marker.length + nextBlock);
}

function isLiveSpecExplicitlySelected(): boolean {
  const explicitSpec = process.env.PLAYWRIGHT_EXPLICIT_SPEC ?? "";
  return (
    process.argv.some((arg) => arg.includes(liveSpecFileName)) ||
    explicitSpec
      .split(/[,\s]+/)
      .filter(Boolean)
      .some((arg) => arg.includes(liveSpecFileName))
  );
}

function assertPreSubmitBackendControlsReady(): void {
  const requestModel = extractSourceBlock(readRepoFile("src/routers/_state.py"), "class S2BrandCampaignRequest");
  expect(requestModel).toContain("artifact_disposition");
  expect(requestModel).toContain("pending_review");
  expect(requestModel).toContain("provider_max_retries");
  expect(requestModel).toContain("output_label");
  expect(requestModel).toContain("media_stop_step");
  expect(requestModel).toContain('"thumbnail_images"');

  const router = extractSourceBlock(readRepoFile("src/routers/scenario.py"), "async def run_s2");
  expect(router).toContain("artifact_disposition=body.artifact_disposition");
  expect(router).toContain("provider_max_retries=body.provider_max_retries");
  expect(router).toContain("output_label=body.output_label");
  expect(router).toContain("media_stop_step=body.media_stop_step");

  const pipelineSource = readRepoFile("src/pipeline/s2_brand_pipeline_v2.py");
  expect(pipelineSource).toContain("S2_SEGMENTED_MEDIA_STOP_STEPS");
  expect(pipelineSource).toContain("S2_SEGMENTED_MEDIA_STEP_ORDERS");
  expect(pipelineSource).toContain('"thumbnail_images": [');
  expect(pipelineSource).toContain('"thumbnail": 1');
  expect(pipelineSource).toContain("bounded_media_stop_step");
  expect(pipelineSource).toContain('result["thumbnail_image_paths"]');
  expect(pipelineSource).toContain('result["clip_paths"] = []');
  expect(pipelineSource).toContain('result["audio_paths"] = []');

  const s1Pipeline = readRepoFile("src/pipeline/s1_product_pipeline.py");
  expect(s1Pipeline).toContain("thumbnail_job_cap");
  expect(s1Pipeline).toContain("_artifact_media_output_dir(state, config, \"thumbnails\")");
  expect(s1Pipeline).toContain("provider_max_retries=config.get(\"provider_max_retries\")");
}

function getStepOutput(statusBody: Record<string, unknown>, stepName: string): unknown {
  const steps = statusBody.steps as Record<string, { output?: unknown; status?: string }> | undefined;
  return steps?.[stepName]?.output;
}

function expectStepDone(
  steps: Record<string, { output?: unknown; status?: string }> | undefined,
  stepName: string,
): void {
  expect(steps?.[stepName]?.status, `${stepName} must complete in thumbnail segment smoke`).toBe("done");
  expect(steps?.[stepName]?.output ?? null, `${stepName} must produce output in thumbnail segment smoke`).not.toBeNull();
}

function expectStepNotExecuted(
  steps: Record<string, { output?: unknown; status?: string }> | undefined,
  stepName: string,
): void {
  const step = steps?.[stepName];
  if (!step) {
    return;
  }
  expect(step.status, `${stepName} must not execute in thumbnail segment smoke`).toBe("pending");
  expect(step.output ?? null, `${stepName} must not produce output in thumbnail segment smoke`).toBeNull();
}

function expectPendingReviewThumbnailPaths(value: unknown): string[] {
  expect(Array.isArray(value), "thumbnail_images must return generated thumbnail paths").toBe(true);
  const paths = value as string[];
  expect(paths.length, "thumbnail segment must generate one thumbnail image").toBe(1);

  for (const mediaPath of paths) {
    expect(mediaPath).toMatch(/\/(pending_review|quarantine)\//);
    expect(mediaPath).not.toContain("/final_work/");
    expect(mediaPath).not.toContain("/renders/");
    expect(mediaPath).not.toContain("/gpt_images/");
  }
  return paths;
}

function buildRunLabel(): string {
  const runId = process.env.PLAYWRIGHT_P15C_THUMBNAIL_RUN_ID
    ?? new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  return `p1_s2_segmented_thumbnail_${runId}`;
}

function expectSegmentedThumbnailStatusReadback(statusBody: Record<string, unknown>, runLabel: string): string[] {
  expect(statusBody.label).toBe(runLabel);
  expect(statusBody.scenario).toBe("s2");
  expect(statusBody.status).toBe("completed");
  expect(statusBody.current_step ?? "").toBe("");
  expect(statusBody.pipeline_degraded).toBe(false);

  const steps = statusBody.steps as Record<string, { output?: unknown; status?: string }> | undefined;
  expectStepDone(steps, "strategy");
  expectStepDone(steps, "scripts");
  expectStepDone(steps, "thumbnail_prompts");
  expectStepDone(steps, "thumbnail_images");
  expectStepNotExecuted(steps, "compliance");
  expectStepNotExecuted(steps, "storyboards");
  expectStepNotExecuted(steps, "continuity_storyboard_grid");
  expectStepNotExecuted(steps, "keyframe_images");
  expectStepNotExecuted(steps, "video_prompts");
  expectStepNotExecuted(steps, "seedance_clips");
  expectStepNotExecuted(steps, "tts_audio");
  expectStepNotExecuted(steps, "assemble_final");
  expectStepNotExecuted(steps, "audit");

  return expectPendingReviewThumbnailPaths(getStepOutput(statusBody, "thumbnail_images"));
}

test.describe("P1-5C S2 segmented thumbnail live provider smoke", () => {
  test("single S2 segmented thumbnail submit stops after thumbnail_images @token-smoke", async ({ request }) => {
    test.setTimeout(20 * 60_000);

    expect(tokenSmokeEnabled, "RUN_TOKEN_SMOKE=1 is required before any live submit").toBe(true);
    expect(isLiveSpecExplicitlySelected(), "live spec must be selected explicitly by file path").toBe(true);
    expect(maxSubmitCount, "P1-5C thumbnail segment must be capped to one scenario submit").toBe(1);
    expect(providerMaxRetries, "provider/backend retries must be disabled").toBe(0);
    expect(artifactDisposition, "thumbnail segment must write only pending_review artifacts").toBe("pending_review");
    expect(explicitStopStep, "P1-5C thumbnail live smoke must target thumbnail_images").toBe(thumbnailStopStep);
    assertPreSubmitBackendControlsReady();
    const runLabel = buildRunLabel();

    let submitCount = 0;
    submitCount += 1;
    expect(submitCount, "submit count exceeded authorized max_submit_count").toBeLessThanOrEqual(maxSubmitCount);

    let response: APIResponse | null = null;
    let submitTimedOut = false;
    try {
      response = await request.post("/api/scenario/s2", {
        headers: productionApiHeaders({ "Content-Type": "application/json" }),
        timeout: submitTimeoutMs,
        data: {
          brand_package: {
            brand_name: "Momcozy",
            values: ["safety", "comfort", "parent trust"],
            voice_guidelines: "warm, practical, no exaggeration",
            visual_constraints: "clean product thumbnail, vertical short-form framing",
          },
          target_platforms: ["tiktok"],
          target_languages: ["en"],
          video_duration: 15,
          output_label: runLabel,
          enable_media_synthesis: true,
          artifact_disposition: artifactDisposition,
          provider_max_retries: providerMaxRetries,
          media_stop_step: thumbnailStopStep,
          commercial_injection_plan: null,
        },
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (!message.includes("Timeout")) {
        throw error;
      }
      submitTimedOut = true;
    }

    if (submitTimedOut) {
      const statusResponse = await request.get(`/api/scenario/s2/status/${runLabel}`, {
        headers: productionApiHeaders(),
        timeout: 60_000,
      });
      expect(statusResponse.status(), "timed-out S2 submit must be readable by explicit output_label").toBe(200);
      const statusBody = await statusResponse.json() as Record<string, unknown>;
      expectSegmentedThumbnailStatusReadback(statusBody, runLabel);
      expect(submitCount).toBe(1);
      return;
    }

    expect(response, "S2 submit response must exist unless transport timeout readback passed").not.toBeNull();

    if ([401, 403, 422, 429].includes(response!.status())) {
      throw new Error(`P1-5C stop-loss status from S2 submit: ${response!.status()} ${await response!.text()}`);
    }

    expect(response!.status(), "single S2 thumbnail segment submit should complete").toBe(200);
    const body = await response!.json();

    expect(body.success).toBe(true);
    expect(body.label).toBe(runLabel);
    expect(body.scenario).toBe("brand_campaign");
    expect(body.brand_name).toBe("Momcozy");
    expect(body.video_duration).toBe(15);
    expect(body.artifact_disposition).toBe(artifactDisposition);
    expect(body.artifact_storage_scope).toBe("tenant_pending_review");
    expect(body.provider_max_retries).toBe(providerMaxRetries);
    expect(body.provider_job_caps).toEqual({ thumbnail: 1 });
    expect(body.bounded_media_pilot).toBe(true);
    expect(body.bounded_media_stop_step).toBe(thumbnailStopStep);
    expect(body.clip_paths ?? []).toEqual([]);
    expect(body.audio_paths ?? []).toEqual([]);
    expectPendingReviewThumbnailPaths(body.thumbnail_image_paths);
    expect(body.final_video_path ?? "").toBe("");
    expect(body.render_json_path ?? "").toBe("");
    expect(body.audit_report ?? {}).toEqual({});
    expect(body.delivery_accepted).toBe(false);
    expect(body.publish_allowed).toBe(false);
    expect(body.approved_brand_token_write).toBe(false);
    expect(submitCount).toBe(1);

    const statusResponse = await request.get(`/api/scenario/s2/status/${runLabel}`, {
      headers: productionApiHeaders(),
      timeout: 60_000,
    });
    expect(statusResponse.status(), "completed S2 thumbnail segment must be readable by explicit output_label").toBe(200);
    const statusBody = await statusResponse.json() as Record<string, unknown>;
    expectSegmentedThumbnailStatusReadback(statusBody, runLabel);
  });
});
