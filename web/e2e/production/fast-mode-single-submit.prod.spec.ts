import { test, expect } from "@playwright/test";
import { delay, productionApiHeaders, productionSubmitHeaders } from "./helpers";

const maxSubmitCount = Number(process.env.PLAYWRIGHT_MAX_SUBMIT_COUNT ?? "1");
const providerMaxRetries = Number(process.env.PLAYWRIGHT_PROVIDER_MAX_RETRIES ?? "0");
const artifactDisposition = process.env.PLAYWRIGHT_ARTIFACT_DISPOSITION ?? "pending_review";

function authHeaders(extra: Record<string, string> = {}) {
  return productionApiHeaders(extra);
}

test.describe("Production smoke — Fast Mode single-submit token smoke", () => {
  test("single Fast Mode submit/status writes pending_review artifact @token-smoke", async ({ request }) => {
    test.setTimeout(12 * 60_000);
    expect(maxSubmitCount, "L4C-1R must be capped to a single submit").toBe(1);
    expect(providerMaxRetries, "L4C-1R provider/backend retries must be disabled").toBe(0);
    expect(["pending_review", "quarantine"]).toContain(artifactDisposition);

    let submitCount = 0;
    submitCount += 1;
    expect(submitCount, "submit count exceeded authorized max_submit_count").toBeLessThanOrEqual(maxSubmitCount);

    const submit = await request.post("/api/fast/submit", {
      headers: productionSubmitHeaders("fast-single-submit", {
        "Content-Type": "application/json",
      }),
      data: {
        user_prompt: "a single red apple on a plain white background, product-safe object shot",
        duration: 10,
        enable_tts: false,
        enable_media_synthesis: true,
        artifact_disposition: artifactDisposition,
        provider_max_retries: providerMaxRetries,
      },
    });

    if ([401, 403, 422, 429].includes(submit.status())) {
      throw new Error(`L4C-1R stop-loss status from submit: ${submit.status()} ${await submit.text()}`);
    }
    expect(submit.status(), "single submit should be accepted").toBe(200);
    const submitBody = await submit.json();
    expect(submitBody.task_id).toMatch(/^fast_\d+_[a-f0-9]+$/);

    let finalSnapshot: Record<string, unknown> | null = null;
    for (let i = 0; i < 150; i += 1) {
      const status = await request.get(`/api/fast/status/${submitBody.task_id}`, {
        headers: authHeaders(),
      });
      if ([401, 403, 422, 429].includes(status.status())) {
        throw new Error(`L4C-1R stop-loss status from status poll: ${status.status()} ${await status.text()}`);
      }
      expect(status.status(), "status endpoint should remain queryable").toBe(200);
      const snapshot = await status.json();
      if (snapshot.status === "failed") {
        throw new Error(`Fast Mode provider task failed: ${JSON.stringify(snapshot).slice(0, 1000)}`);
      }
      if (snapshot.status === "done") {
        finalSnapshot = snapshot;
        break;
      }
      await delay(4_000);
    }

    expect(finalSnapshot, "Fast Mode task must complete before the smoke timeout").not.toBeNull();
    const result = finalSnapshot?.result as Record<string, unknown> | undefined;
    expect(result, "done status must include result").toBeTruthy();
    expect(result?.status).toBe("completed_full");
    expect(result?.lifecycle_status).toBe("completed_full");
    expect(result?.completion_kind).toBe("full_media");
    expect(result?.request_succeeded).toBe(true);
    expect(result?.success).toBe(true);
    expect(result?.full_media_success).toBe(true);
    expect(result?.pipeline_complete).toBe(true);
    expect(result?.publish_allowed).toBe(false);
    expect(result?.delivery_accepted).toBe(false);
    expect(result?.is_stub).toBe(false);
    expect(result?.artifact_disposition).toBe(artifactDisposition);
    if (artifactDisposition === "pending_review") {
      expect(result?.artifact_review_status).toBe("pending_review");
      expect(result?.artifact_storage_scope).toBe("tenant_pending_review");
      expect(String(result?.video_path ?? "")).toContain("/pending_review/");
    }
    expect(Number(result?.file_size_bytes ?? 0), "generated artifact must not be empty").toBeGreaterThan(1024 * 1024);
    expect(submitCount).toBe(1);
  });
});
