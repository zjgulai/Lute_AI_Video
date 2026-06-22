import { expect, test, type APIResponse } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { productionApiHeaders } from "./helpers";

const liveSpecFileName = "scenario-s2-audit-segment-live.prod.spec.ts";
const auditStopStep = "audit";
const tokenSmokeEnabled = ["1", "true", "yes"].includes(
  String(process.env.RUN_TOKEN_SMOKE ?? "").toLowerCase(),
);
const maxSubmitCount = Number(process.env.PLAYWRIGHT_MAX_SUBMIT_COUNT ?? "1");
const providerMaxRetries = Number(process.env.PLAYWRIGHT_PROVIDER_MAX_RETRIES ?? "0");
const artifactDisposition = process.env.PLAYWRIGHT_ARTIFACT_DISPOSITION ?? "pending_review";
const explicitStopStep = process.env.PLAYWRIGHT_S2_SEGMENTED_MEDIA_STOP_STEP ?? auditStopStep;
const submitTimeoutMs = Number(process.env.PLAYWRIGHT_S2_AUDIT_SUBMIT_TIMEOUT_MS ?? String(10 * 60_000));

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

function requiredEnvPath(name: string): string {
  const value = process.env[name] ?? "";
  expect(value, `${name} must be provided for refs-only audit live smoke`).not.toBe("");
  expect(value).toMatch(/\/(pending_review|quarantine)\//);
  expect(value).toContain("/tenants/");
  expect(value).not.toContain("/final_work/");
  expect(value).not.toContain("/renders/");
  expect(value).not.toContain("/fast_mode/");
  expect(value).not.toContain("/gpt_images/");
  return value;
}

function optionalEnvPath(name: string): string[] {
  const value = process.env[name] ?? "";
  if (!value) {
    return [];
  }
  expect(value).toMatch(/\/(pending_review|quarantine)\//);
  expect(value).toContain("/tenants/");
  expect(value).not.toContain("/final_work/");
  expect(value).not.toContain("/renders/");
  expect(value).not.toContain("/fast_mode/");
  expect(value).not.toContain("/gpt_images/");
  return [value];
}

function buildMediaRefs(): Record<string, unknown> {
  return {
    clip_paths: [requiredEnvPath("PLAYWRIGHT_S2_AUDIT_REF_CLIP_PATH")],
    audio_paths: [requiredEnvPath("PLAYWRIGHT_S2_AUDIT_REF_AUDIO_PATH")],
    thumbnail_image_paths: [requiredEnvPath("PLAYWRIGHT_S2_AUDIT_REF_THUMBNAIL_PATH")],
    video_path: requiredEnvPath("PLAYWRIGHT_S2_AUDIT_REF_VIDEO_PATH"),
    render_json_path: optionalEnvPath("PLAYWRIGHT_S2_AUDIT_REF_RENDER_JSON_PATH"),
    lyrics_paths: optionalEnvPath("PLAYWRIGHT_S2_AUDIT_REF_LYRICS_PATH"),
    clip_details: [{ duration_seconds: 5, is_stub: false, refs_only: true }],
    scripts: [
      {
        id: "refs-only-audit-script",
        segments: [
          {
            voiceover: "Refs-only media quality audit checkpoint.",
            description: "Audit existing reviewed media references.",
            start_time: 0,
            end_time: 5,
          },
        ],
      },
    ],
    storyboards: [],
    thumbnail_prompts: [
      {
        variants: [
          {
            prompt: "Refs-only media quality audit thumbnail checkpoint.",
          },
        ],
      },
    ],
    continuity_storyboard_grid: {
      status: "refs_only",
      micro_shots: [],
      clip_groups: [],
    },
  };
}

function assertPreSubmitBackendControlsReady(): void {
  const requestModel = extractSourceBlock(readRepoFile("src/routers/_state.py"), "class S2BrandCampaignRequest");
  expect(requestModel).toContain("artifact_disposition");
  expect(requestModel).toContain("provider_max_retries");
  expect(requestModel).toContain("output_label");
  expect(requestModel).toContain("media_stop_step");
  expect(requestModel).toContain("media_refs");
  expect(requestModel).toContain('"audit"');

  const router = extractSourceBlock(readRepoFile("src/routers/scenario.py"), "async def run_s2_brand_campaign");
  expect(router).toContain("artifact_disposition=body.artifact_disposition");
  expect(router).toContain("provider_max_retries=body.provider_max_retries");
  expect(router).toContain("output_label=body.output_label");
  expect(router).toContain("media_stop_step=body.media_stop_step");
  expect(router).toContain("media_refs=body.media_refs");

  const pipelineSource = readRepoFile("src/pipeline/s2_brand_pipeline_v2.py");
  expect(pipelineSource).toContain('"audit": [\n        "audit",\n    ]');
  expect(pipelineSource).toContain('"audit": {}');
  expect(pipelineSource).toContain("_normalize_audit_media_refs");
  expect(pipelineSource).toContain("refs_only_media_audit");
  expect(pipelineSource).toContain("_seed_refs_only_audit_inputs");
}

function getStepOutput(statusBody: Record<string, unknown>, stepName: string): unknown {
  const steps = statusBody.steps as Record<string, { output?: unknown; status?: string }> | undefined;
  return steps?.[stepName]?.output;
}

function expectStepDone(
  steps: Record<string, { output?: unknown; status?: string }> | undefined,
  stepName: string,
): void {
  expect(steps?.[stepName]?.status, `${stepName} must be done in audit segment smoke`).toBe("done");
  expect(steps?.[stepName]?.output ?? null, `${stepName} must have output`).not.toBeNull();
}

function expectStepNotExecuted(
  steps: Record<string, { output?: unknown; status?: string }> | undefined,
  stepName: string,
): void {
  const step = steps?.[stepName];
  if (!step) {
    return;
  }
  expect(step.status, `${stepName} must not execute in audit segment smoke`).toBe("pending");
  expect(step.output ?? null, `${stepName} must not produce output`).toBeNull();
}

function expectReviewScopedPath(value: unknown, label: string): string {
  expect(typeof value, `${label} must be a path`).toBe("string");
  const path = value as string;
  expect(path).toMatch(/\/(pending_review|quarantine)\//);
  expect(path).toContain("/tenants/");
  expect(path).not.toContain("/final_work/");
  expect(path).not.toContain("/renders/");
  expect(path).not.toContain("/fast_mode/");
  expect(path).not.toContain("/gpt_images/");
  return path;
}

function expectSegmentedAuditStatusReadback(statusBody: Record<string, unknown>, runLabel: string): void {
  expect(statusBody.label).toBe(runLabel);
  expect(statusBody.scenario).toBe("s2");
  expect(statusBody.status).toBe("completed");
  expect(statusBody.current_step ?? "").toBe("");
  expect(statusBody.pipeline_degraded).toBe(false);

  const steps = statusBody.steps as Record<string, { output?: unknown; status?: string }> | undefined;
  expectStepDone(steps, "scripts");
  expectStepDone(steps, "storyboards");
  expectStepDone(steps, "seedance_clips");
  expectStepDone(steps, "tts_audio");
  expectStepDone(steps, "thumbnail_prompts");
  expectStepDone(steps, "thumbnail_images");
  expectStepDone(steps, "assemble_final");
  expectStepDone(steps, "audit");
  expectStepNotExecuted(steps, "strategy");
  expectStepNotExecuted(steps, "compliance");
  expectStepNotExecuted(steps, "continuity_storyboard_grid");
  expectStepNotExecuted(steps, "keyframe_images");
  expectStepNotExecuted(steps, "video_prompts");

  const assembleOutput = getStepOutput(statusBody, "assemble_final") as Record<string, unknown>;
  expectReviewScopedPath(assembleOutput?.video_path, "assemble video_path");
  expect(assembleOutput?.refs_only).toBe(true);

  const auditOutput = getStepOutput(statusBody, "audit") as Record<string, unknown>;
  expect(auditOutput).toBeTruthy();
  expect(auditOutput?.overall_status ?? auditOutput?.status ?? "").not.toBe("");
}

function buildRunLabel(): string {
  const runId = process.env.PLAYWRIGHT_P15E_AUDIT_RUN_ID
    ?? new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  return `p1_s2_segmented_audit_${runId}`;
}

test.describe("P1-5E S2 segmented media quality audit live smoke", () => {
  test("single S2 segmented audit submit stops after media_quality_audit @token-smoke", async ({ request }) => {
    test.setTimeout(20 * 60_000);

    expect(tokenSmokeEnabled, "RUN_TOKEN_SMOKE=1 is required before any live submit").toBe(true);
    expect(isLiveSpecExplicitlySelected(), "live spec must be selected explicitly by file path").toBe(true);
    expect(maxSubmitCount, "P1-5E audit segment must be capped to one scenario submit").toBe(1);
    expect(providerMaxRetries, "provider/backend retries must be disabled").toBe(0);
    expect(artifactDisposition, "audit segment must read only pending_review artifacts").toBe("pending_review");
    expect(explicitStopStep, "P1-5E audit live smoke must target audit").toBe(auditStopStep);
    assertPreSubmitBackendControlsReady();
    const mediaRefs = buildMediaRefs();
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
            visual_constraints: "refs-only audit, no new media generation",
          },
          target_platforms: ["tiktok"],
          target_languages: ["en"],
          video_duration: 15,
          output_label: runLabel,
          enable_media_synthesis: true,
          artifact_disposition: artifactDisposition,
          provider_max_retries: providerMaxRetries,
          media_stop_step: auditStopStep,
          media_refs: mediaRefs,
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
      expectSegmentedAuditStatusReadback(statusBody, runLabel);
      expect(submitCount).toBe(1);
      return;
    }

    expect(response, "S2 submit response must exist unless transport timeout readback passed").not.toBeNull();

    if ([401, 403, 422, 429].includes(response!.status())) {
      throw new Error(`P1-5E stop-loss status from S2 submit: ${response!.status()} ${await response!.text()}`);
    }

    expect(response!.status(), "single S2 audit segment submit should complete").toBe(200);
    const body = await response!.json();

    expect(body.success).toBe(true);
    expect(body.label).toBe(runLabel);
    expect(body.scenario).toBe("brand_campaign");
    expect(body.artifact_disposition).toBe(artifactDisposition);
    expect(body.artifact_storage_scope).toBe("tenant_pending_review");
    expect(body.provider_max_retries).toBe(providerMaxRetries);
    expect(body.provider_job_caps).toEqual({});
    expect(body.bounded_media_pilot).toBe(true);
    expect(body.bounded_media_stop_step).toBe(auditStopStep);
    expect(body.refs_only_media_audit).toBe(true);
    expect(Array.isArray(body.clip_paths)).toBe(true);
    expect(Array.isArray(body.audio_paths)).toBe(true);
    expect(Array.isArray(body.thumbnail_image_paths)).toBe(true);
    expectReviewScopedPath(body.intermediate_video_path, "intermediate_video_path");
    expect(body.final_video_path ?? "").toBe("");
    expect(body.render_json_path ?? "").toBe("");
    expect(body.audit_report ?? {}).not.toEqual({});
    expect(body.delivery_accepted).toBe(false);
    expect(body.publish_allowed).toBe(false);
    expect(body.approved_brand_token_write).toBe(false);
    expect(submitCount).toBe(1);

    const statusResponse = await request.get(`/api/scenario/s2/status/${runLabel}`, {
      headers: productionApiHeaders(),
      timeout: 60_000,
    });
    expect(statusResponse.status(), "completed S2 audit segment must be readable by explicit output_label").toBe(200);
    const statusBody = await statusResponse.json() as Record<string, unknown>;
    expectSegmentedAuditStatusReadback(statusBody, runLabel);
  });
});
