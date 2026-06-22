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

function countMatches(source: string, pattern: RegExp): number {
  return source.match(pattern)?.length ?? 0;
}

test.describe("TODO-P1-5E S2 segmented media quality audit refs-only readiness", () => {
  test("proves audit is refs-only and cannot submit in readiness mode", () => {
    expect(tokenSmokeEnabled, "readiness must run without token smoke").toBe(false);

    const requestModel = extractSourceBlock(
      readRepoFile("src/routers/_state.py"),
      "class S2BrandCampaignRequest",
    );
    expect(requestModel).toContain("media_stop_step");
    expect(requestModel).toContain('"audit"');
    expect(requestModel).toContain("media_refs");

    const routerSource = extractSourceBlock(
      readRepoFile("src/routers/scenario.py"),
      "async def run_s2_brand_campaign",
    );
    expect(routerSource).toContain("media_stop_step=body.media_stop_step");
    expect(routerSource).toContain("media_refs=body.media_refs");

    const pipelineSource = readRepoFile("src/pipeline/s2_brand_pipeline_v2.py");
    expect(pipelineSource).toContain('"audit": [\n        "audit",\n    ]');
    expect(pipelineSource).toContain('"audit": {}');
    expect(pipelineSource).toContain("_normalize_audit_media_refs");
    expect(pipelineSource).toContain("refs_only_media_audit");
    expect(pipelineSource).toContain("_seed_refs_only_audit_inputs");
    expect(pipelineSource).toContain("S2 audit stop point requires media_refs");
    for (const forbidden of ["/final_work/", "/renders/", "/fast_mode/", "/gpt_images/"]) {
      expect(pipelineSource).toContain(forbidden);
    }

    const testsSource = readRepoFile("tests/test_s2_e2e.py");
    expect(testsSource).toContain("test_audit_segment_requires_refs_only_media_refs");
    expect(testsSource).toContain("test_audit_segment_rejects_non_review_scoped_refs");
    expect(testsSource).toContain("refs_only_media_audit");

    const liveSpec = readRepoFile(
      "web/e2e/production/scenario-s2-audit-segment-live.prod.spec.ts",
    );
    expect(liveSpec).toContain(
      "single S2 segmented audit submit stops after media_quality_audit @token-smoke",
    );
    expect(liveSpec).toContain("const auditStopStep = \"audit\"");
    expect(liveSpec).toContain("media_stop_step: auditStopStep");
    expect(liveSpec).toContain("media_refs:");
    expect(liveSpec).toContain("expect(body.provider_job_caps).toEqual({})");
    expect(countMatches(liveSpec, /request\.post\(/g)).toBe(1);
    expect(liveSpec).not.toContain("scenario-s1");
    expect(liveSpec).not.toContain("scenario-s3");
    expect(liveSpec).not.toContain("scenario-s4");
    expect(liveSpec).not.toContain("scenario-s5");
    expect(liveSpec).not.toContain("/api/fast");

    const productionSpecs = readdirSync(join(process.cwd(), "e2e/production")).sort();
    expect(productionSpecs).toContain("scenario-s2-audit-segment-readiness.prod.spec.ts");
    expect(productionSpecs).toContain("scenario-s2-audit-segment-live.prod.spec.ts");
  });
});
