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

function extractMethodBlock(source: string, marker: string): string {
  const start = source.indexOf(marker);
  expect(start, `${marker} must exist`).toBeGreaterThanOrEqual(0);

  const tail = source.slice(start);
  const nextBlock = tail.slice(marker.length).search(/\n    (?:async def|def) /);
  if (nextBlock === -1) {
    return tail;
  }
  return tail.slice(0, marker.length + nextBlock);
}

function countMatches(source: string, pattern: RegExp): number {
  return source.match(pattern)?.length ?? 0;
}

test.describe("TODO-P1-5D S2 segmented assemble refs-only readiness", () => {
  test("proves assemble_final is refs-only and cannot submit in readiness mode", () => {
    expect(tokenSmokeEnabled, "readiness must run without token smoke").toBe(false);

    const requestModel = extractSourceBlock(
      readRepoFile("src/routers/_state.py"),
      "class S2BrandCampaignRequest",
    );
    expect(requestModel).toContain("media_stop_step");
    expect(requestModel).toContain('"assemble_final"');
    expect(requestModel).toContain("media_refs");

    const routerSource = extractSourceBlock(
      readRepoFile("src/routers/scenario.py"),
      "async def run_s2_brand_campaign",
    );
    expect(routerSource).toContain("media_stop_step=body.media_stop_step");
    expect(routerSource).toContain("media_refs=body.media_refs");

    const pipelineSource = readRepoFile("src/pipeline/s2_brand_pipeline_v2.py");
    const policySource = readRepoFile("src/pipeline/generation_policy.py");
    const stepProfiles = extractSourceBlock(
      policySource,
      "S2_SEGMENTED_MEDIA_STEP_PROFILES:",
    );
    const providerCaps = extractSourceBlock(
      policySource,
      "S2_SEGMENTED_MEDIA_PROVIDER_JOB_CAPS:",
    );
    expect(stepProfiles).toContain('"assemble_final": ("assemble_final",)');
    expect(providerCaps).toContain('"assemble_final": MappingProxyType({})');
    expect(pipelineSource).toContain(
      "S2_SEGMENTED_MEDIA_STEP_PROFILES as POLICY_S2_STEP_PROFILES",
    );
    expect(pipelineSource).toContain(
      "S2_SEGMENTED_MEDIA_PROVIDER_JOB_CAPS as POLICY_S2_PROVIDER_JOB_CAPS",
    );
    const normalizeRefs = extractSourceBlock(
      pipelineSource,
      "def _normalize_assemble_media_refs",
    );
    const seedRefs = extractMethodBlock(
      pipelineSource,
      "    async def _seed_refs_only_assemble_inputs",
    );
    const scopeOutput = extractMethodBlock(
      pipelineSource,
      "    def _scope_refs_only_assemble_output",
    );
    expect(normalizeRefs).toContain("S2 assemble_final stop point requires media_refs");
    expect(normalizeRefs).toContain("_assert_review_scoped_ref(");
    expect(seedRefs).toContain("_normalize_assemble_media_refs(");
    expect(seedRefs).toContain('state["refs_only_media_assembly"] = True');
    expect(scopeOutput).toContain("_move_path_into_review_scope(");
    const reviewRefValidator = extractSourceBlock(
      policySource,
      "def assert_review_scoped_media_ref",
    );
    for (const forbidden of ["final_work", "renders", "fast_mode", "gpt_images"]) {
      expect(reviewRefValidator).toContain(`"${forbidden}"`);
    }
    expect(reviewRefValidator).toContain(
      "review-scoped media path uses a forbidden artifact root",
    );

    const testsSource = readRepoFile("tests/test_s2_e2e.py");
    expect(testsSource).toContain("test_assemble_segment_requires_refs_only_media_refs");
    expect(testsSource).toContain("test_assemble_segment_rejects_non_review_scoped_refs");
    expect(testsSource).toContain("refs_only_media_assembly");

    const liveSpec = readRepoFile(
      "web/e2e/production/scenario-s2-assemble-segment-live.prod.spec.ts",
    );
    expect(liveSpec).toContain(
      "single S2 segmented assemble submit stops after assemble_final @token-smoke",
    );
    expect(liveSpec).toContain("const assembleStopStep = \"assemble_final\"");
    expect(liveSpec).toContain("media_stop_step: assembleStopStep");
    expect(liveSpec).toContain("media_refs:");
    expect(liveSpec).toContain("expect(body.provider_job_caps).toEqual({})");
    expect(countMatches(liveSpec, /request\.post\(/g)).toBe(1);
    expect(liveSpec).not.toContain("scenario-s1");
    expect(liveSpec).not.toContain("scenario-s3");
    expect(liveSpec).not.toContain("scenario-s4");
    expect(liveSpec).not.toContain("scenario-s5");
    expect(liveSpec).not.toContain("/api/fast");

    const productionSpecs = readdirSync(join(process.cwd(), "e2e/production")).sort();
    expect(productionSpecs).toContain("scenario-s2-assemble-segment-readiness.prod.spec.ts");
    expect(productionSpecs).toContain("scenario-s2-assemble-segment-live.prod.spec.ts");
  });
});
