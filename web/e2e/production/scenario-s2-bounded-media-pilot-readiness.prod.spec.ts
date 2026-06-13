import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expectOkJsonWith429Retry } from "./helpers";

const tokenSmokeEnabled = ["1", "true", "yes"].includes(
  String(process.env.RUN_TOKEN_SMOKE ?? "").toLowerCase(),
);
const l4d5ExecuteGate = process.env.PLAYWRIGHT_L4D5_MEDIA_PILOT_EXECUTE === "1";
const maxSubmitCount = Number(process.env.PLAYWRIGHT_MAX_SUBMIT_COUNT ?? "1");
const providerMaxRetries = Number(process.env.PLAYWRIGHT_PROVIDER_MAX_RETRIES ?? "0");
const artifactDisposition = process.env.PLAYWRIGHT_ARTIFACT_DISPOSITION ?? "pending_review";

const s2BoundedMediaPilotPayload = Object.freeze({
  brand_package_id: "momcozy-marketing",
  brand_name: "Momcozy",
  product_name: "Momcozy bottle sterilizer",
  campaign_goal: "Validate a bounded single-scenario media pilot without publishing.",
  target_platforms: ["tiktok"],
  video_duration: 15,
  enable_media_synthesis: true,
  artifact_disposition: artifactDisposition,
  commercial_injection_plan: null,
});

function readRepoFile(path: string): string {
  return readFileSync(join(process.cwd(), "..", path), "utf8");
}

test.describe("L4D-5-fix-prep S2 bounded media pilot readiness", () => {
  test("dry-run readiness keeps S2 media pilot blocked before live submit", async ({ request }) => {
    expect(tokenSmokeEnabled).toBe(false);
    expect(l4d5ExecuteGate).toBe(false);
    expect(maxSubmitCount).toBe(1);
    expect(providerMaxRetries).toBe(0);
    expect(artifactDisposition).toBe("pending_review");

    expect(s2BoundedMediaPilotPayload.enable_media_synthesis).toBe(true);
    expect(s2BoundedMediaPilotPayload.video_duration).toBe(15);
    expect(s2BoundedMediaPilotPayload.artifact_disposition).toBe("pending_review");
    expect(s2BoundedMediaPilotPayload).not.toHaveProperty("api_keys");

    const requestModelSource = readRepoFile("src/routers/_state.py");
    expect(requestModelSource).toContain("artifact_disposition: Literal[\"default\", \"pending_review\", \"quarantine\"]");
    expect(requestModelSource).toContain("output_label: str | None = None");

    const routerSource = readRepoFile("src/routers/scenario.py");
    expect(routerSource).toContain("artifact_disposition=body.artifact_disposition");
    expect(routerSource).toContain("output_label=body.output_label");

    const s2PipelineSource = readRepoFile("src/pipeline/s2_brand_pipeline_v2.py");
    expect(s2PipelineSource).toContain("S2_BOUNDED_MEDIA_STOP_STEP = \"seedance_clips\"");
    expect(s2PipelineSource).toContain("S2_BOUNDED_MEDIA_STEP_ORDER");
    expect(s2PipelineSource).toContain("\"provider_job_caps\": {\"image\": 1, \"video\": 1}");
    expect(s2PipelineSource).toContain("\"seedance_quality_gate_enabled\": False");
    expect(s2PipelineSource).toContain("if artifact_disposition in {\"pending_review\", \"quarantine\"}");
    expect(s2PipelineSource).toContain("final_state[\"current_step\"] = None");
    expect(s2PipelineSource).toContain("result[\"final_video_path\"] = \"\"");
    expect(s2PipelineSource).toContain("result[\"publish_allowed\"] = False");
    expect(s2PipelineSource).toContain("result[\"approved_brand_token_write\"] = False");

    const s1PipelineSource = readRepoFile("src/pipeline/s1_product_pipeline.py");
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
