import { expect, test, type APIResponse } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { productionApiHeaders } from "./helpers";

const liveSpecFileName = "scenario-s1-bounded-media-pilot-live.prod.spec.ts";
const tokenSmokeEnabled = ["1", "true", "yes"].includes(
  String(process.env.RUN_TOKEN_SMOKE ?? "").toLowerCase(),
);
const maxSubmitCount = Number(process.env.PLAYWRIGHT_MAX_SUBMIT_COUNT ?? "1");
const providerMaxRetries = Number(process.env.PLAYWRIGHT_PROVIDER_MAX_RETRIES ?? "0");
const artifactDisposition = process.env.PLAYWRIGHT_ARTIFACT_DISPOSITION ?? "pending_review";
const submitTimeoutMs = Number(process.env.PLAYWRIGHT_S1_BOUNDED_SUBMIT_TIMEOUT_MS ?? String(10 * 60_000));

function readRepoFile(path: string): string {
  return readFileSync(join(process.cwd(), "..", path), "utf8");
}

function extractSourceBlock(source: string, marker: string): string {
  const start = source.indexOf(marker);
  expect(start, `${marker} must exist before live submit`).toBeGreaterThanOrEqual(0);

  const tail = source.slice(start);
  const nextBlock = tail.slice(marker.length).search(/\n(?:class|async def|def) /);
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
  const requestModel = extractSourceBlock(readRepoFile("src/routers/_state.py"), "class S1StartRequest");
  expect(requestModel).toContain("artifact_disposition");
  expect(requestModel).toContain("pending_review");
  expect(requestModel).toContain("provider_max_retries");
  expect(requestModel).toContain("output_label");

  const routerSource = readRepoFile("src/routers/scenario.py");
  const router = extractSourceBlock(routerSource, "async def run_s1_product_direct");
  expect(router).toContain("body: S1StartRequest");
  expect(router).toContain("body.artifact_disposition");
  expect(router).toContain("effective_provider_max_retries");
  expect(router).toContain("label=body.output_label");
  expect(router).toContain("_resume_s1_bounded_media_pilot");
  expect(router).toContain("result[\"final_video_path\"] = \"\"");
  expect(router).toContain("result[\"publish_allowed\"] = False");
  expect(router).toContain("result[\"approved_brand_token_write\"] = False");
  expect(routerSource).toContain("S1_BOUNDED_MEDIA_STOP_STEP = \"seedance_clips\"");
  expect(routerSource).toContain("\"provider_job_caps\": {\"image\": 1, \"video\": 1}");
  expect(routerSource).toContain("\"seedance_quality_gate_enabled\": False");

  const pipelineSource = readRepoFile("src/pipeline/s1_product_pipeline.py");
  expect(pipelineSource).toContain("S1_BOUNDED_MEDIA_STOP_STEP = \"seedance_clips\"");
  expect(pipelineSource).toContain("S1_BOUNDED_MEDIA_STEP_ORDER");
  expect(pipelineSource).toContain("\"provider_job_caps\": {\"image\": 1, \"video\": 1}");
  expect(pipelineSource).toContain("\"seedance_quality_gate_enabled\": False");
  expect(pipelineSource).toContain("result[\"final_video_path\"] = \"\"");
  expect(pipelineSource).toContain("result[\"publish_allowed\"] = False");
  expect(pipelineSource).toContain("result[\"approved_brand_token_write\"] = False");
  expect(pipelineSource).toContain("provider_max_retries=config.get(\"provider_max_retries\")");
  expect(pipelineSource).toContain("image_job_cap");
  expect(pipelineSource).toContain("video_job_cap");
  expect(pipelineSource).toContain("quality_gate_enabled");

  const keyframeSkill = readRepoFile("src/skills/keyframe_images.py");
  expect(keyframeSkill).toContain("generate_params[\"provider_max_retries\"] = provider_max_retries");

  const seedanceSkill = readRepoFile("src/skills/seedance_video_generate.py");
  expect(seedanceSkill).toContain("output_dir=output_dir");
  expect(seedanceSkill).toContain("max_retries=provider_max_retries");
}

function expectPendingReviewMediaPaths(value: unknown): string[] {
  expect(Array.isArray(value), "seedance_clips must return generated clip paths").toBe(true);
  const paths = value as string[];
  expect(paths.length, "bounded media pilot must generate at least one clip").toBeGreaterThan(0);

  for (const mediaPath of paths) {
    expect(mediaPath).toMatch(/\/(pending_review|quarantine)\//);
    expect(mediaPath).not.toContain("/final_work/");
    expect(mediaPath).not.toContain("/renders/");
    expect(mediaPath).not.toContain("/seedance/");
  }
  return paths;
}

function buildRunLabel(): string {
  const runId = process.env.PLAYWRIGHT_P1_S1_RUN_ID
    ?? new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  return `p1_s1_bounded_${runId}`;
}

function getStepOutput(statusBody: Record<string, unknown>, stepName: string): unknown {
  const steps = statusBody.steps as Record<string, { output?: unknown; status?: string }> | undefined;
  return steps?.[stepName]?.output;
}

function expectStepNotExecuted(
  steps: Record<string, { output?: unknown; status?: string }> | undefined,
  stepName: string,
): void {
  const step = steps?.[stepName];
  if (!step) {
    return;
  }
  expect(step.status, `${stepName} must not execute in bounded media smoke`).toBe("pending");
  expect(step.output ?? null, `${stepName} must not produce output in bounded media smoke`).toBeNull();
}

function expectBoundedStatusReadback(statusBody: Record<string, unknown>, runLabel: string): string[] {
  expect(statusBody.label).toBe(runLabel);
  expect(statusBody.scenario).toBe("s1");
  expect(statusBody.status).toBe("completed");
  expect(statusBody.current_step ?? "").toBe("");
  expect(statusBody.pipeline_degraded).toBe(false);

  const steps = statusBody.steps as Record<string, { output?: unknown; status?: string }> | undefined;
  expect(steps?.seedance_clips?.status).toBe("done");
  expectStepNotExecuted(steps, "thumbnail_prompts");
  expectStepNotExecuted(steps, "thumbnail_images");
  expectStepNotExecuted(steps, "tts_audio");
  expectStepNotExecuted(steps, "assemble_final");
  expectStepNotExecuted(steps, "audit");

  const seedanceOutput = getStepOutput(statusBody, "seedance_clips");
  const clipPaths = (seedanceOutput && typeof seedanceOutput === "object" && "clip_paths" in seedanceOutput)
    ? (seedanceOutput as { clip_paths?: unknown }).clip_paths
    : seedanceOutput;
  return expectPendingReviewMediaPaths(clipPaths);
}

test.describe("TODO-P1-1 S1 bounded media live provider smoke", () => {
  test("single S1 bounded media submit stops after seedance_clips @token-smoke", async ({ request }) => {
    test.setTimeout(20 * 60_000);

    expect(tokenSmokeEnabled, "RUN_TOKEN_SMOKE=1 is required before any live submit").toBe(true);
    expect(isLiveSpecExplicitlySelected(), "live spec must be selected explicitly by file path").toBe(true);
    expect(maxSubmitCount, "P1-1 must be capped to one scenario submit").toBe(1);
    expect(providerMaxRetries, "provider/backend retries must be disabled").toBe(0);
    expect(artifactDisposition, "live media smoke must write only pending_review artifacts").toBe("pending_review");
    assertPreSubmitBackendControlsReady();
    const runLabel = buildRunLabel();

    let submitCount = 0;
    submitCount += 1;
    expect(submitCount, "submit count exceeded authorized max_submit_count").toBeLessThanOrEqual(maxSubmitCount);

    let response: APIResponse | null = null;
    let submitTimedOut = false;
    try {
      response = await request.post("/api/scenario/s1", {
        headers: productionApiHeaders({ "Content-Type": "application/json" }),
        timeout: submitTimeoutMs,
        data: {
          product_catalog: {
            product_name: "Momcozy bottle sterilizer",
            category: "baby appliance",
            key_selling_points: ["steam sterilization", "compact counter footprint"],
          },
          brand_guidelines: {
            brand_name: "Momcozy",
            voice_guidelines: "warm, practical, no exaggeration",
            visual_constraints: "clean vertical product demo",
          },
          target_platforms: ["tiktok"],
          video_duration: 15,
          output_label: runLabel,
          enable_media_synthesis: true,
          artifact_disposition: artifactDisposition,
          provider_max_retries: providerMaxRetries,
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
      const statusResponse = await request.get(`/api/scenario/s1/status/${runLabel}`, {
        headers: productionApiHeaders(),
        timeout: 60_000,
      });
      expect(statusResponse.status(), "timed-out S1 submit must be readable by explicit output_label").toBe(200);
      const statusBody = await statusResponse.json() as Record<string, unknown>;
      expectBoundedStatusReadback(statusBody, runLabel);
      expect(submitCount).toBe(1);
      return;
    }

    expect(response, "S1 submit response must exist unless transport timeout readback passed").not.toBeNull();

    if ([401, 403, 422, 429].includes(response!.status())) {
      throw new Error(`P1-1 stop-loss status from S1 submit: ${response!.status()} ${await response!.text()}`);
    }

    expect(response!.status(), "single S1 bounded media submit should complete").toBe(200);
    const body = await response!.json();

    expect(body.success).toBe(true);
    expect(body.label).toBe(runLabel);
    expect(body.scenario).toBe("s1");
    expect(body.video_duration).toBe(15);
    expect(body.artifact_disposition).toBe(artifactDisposition);
    expect(body.artifact_storage_scope).toBe("tenant_pending_review");
    expect(body.provider_max_retries).toBe(0);
    expect(body.provider_job_caps).toEqual({ image: 1, video: 1 });
    expect(body.bounded_media_pilot).toBe(true);
    expect(body.bounded_media_stop_step).toBe("seedance_clips");
    expectPendingReviewMediaPaths(body.clip_paths);
    expect(body.audio_paths ?? []).toEqual([]);
    expect(body.thumbnail_image_paths ?? []).toEqual([]);
    expect(body.final_video_path ?? "").toBe("");
    expect(body.render_json_path ?? "").toBe("");
    expect(body.audit_report ?? {}).toEqual({});
    expect(body.delivery_accepted).toBe(false);
    expect(body.publish_allowed).toBe(false);
    expect(body.approved_brand_token_write).toBe(false);
    expect(submitCount).toBe(1);
  });
});
