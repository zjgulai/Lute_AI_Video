import { expect, test, type Page, type Route } from "@playwright/test";

const IDEMPOTENCY_KEY = "123e4567-e89b-42d3-a456-426614174000";
const FAST_TASK_ID = "fast_ui_recovered";

const fastResult = {
  status: "completed_bounded",
  lifecycle_status: "completed_bounded",
  completion_kind: "no_media",
  request_succeeded: true,
  success: false,
  full_media_success: false,
  pipeline_complete: false,
  publish_allowed: false,
  delivery_accepted: false,
  video_path: "",
  video_url: "",
  filename: "",
  llm_prompt: "fixture prompt",
  scene_description: "fixture scene",
  user_prompt: "fixture input",
  duration_seconds: 15,
  file_size_bytes: 0,
  generation_time_ms: 10,
  timing: { llm_ms: 1, video_ms: 9, tts_ms: 0 },
  model_info: { llm: "fake", video: "fake", tts: null },
  is_stub: true,
  tts_path: null,
};

async function seedBrowserState(page: Page, pending: boolean) {
  await page.addInitScript(({ key, includePending }) => {
    localStorage.clear();
    localStorage.setItem("ai_video_api_key", "ui_only_fake_key");
    localStorage.setItem("ai_video_api_base", "/api");
    localStorage.setItem("ai_video_demo_mode", "false");
    localStorage.setItem("app-locale", "en");
    localStorage.setItem("ai-video-pipeline-store", JSON.stringify({
      state: {
        activePipeline: null,
        dismissedPipelineLabels: [],
        pendingSubmission: includePending
          ? {
              kind: "fast",
              idempotencyKey: key,
              createdAt: Date.now(),
              phase: "unknown",
            }
          : null,
      },
      version: 2,
    }));
  }, { key: IDEMPOTENCY_KEY, includePending: pending });
}

function json(route: Route, status: number, body: unknown) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

test.describe("idempotent submission UI recovery", () => {
  test("reload performs GET readback/status only and never submits", async ({ page }) => {
    let submitCount = 0;
    let readbackCount = 0;
    let statusCount = 0;
    let transparencyCount = 0;
    await seedBrowserState(page, true);
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (request.method() === "POST" && url.pathname.endsWith("/fast/submit")) {
        submitCount += 1;
        return json(route, 500, { detail: { code: "unexpected_submit" } });
      }
      if (request.method() === "GET" && url.pathname.endsWith("/submissions/idempotency")) {
        readbackCount += 1;
        expect(request.headers()["idempotency-key"]).toBe(IDEMPOTENCY_KEY);
        return json(route, 200, {
          resource_type: "fast",
          resource_id: FAST_TASK_ID,
          scenario: "fast",
          status: "queued",
          submit_response: { task_id: FAST_TASK_ID, status: "queued" },
          result_snapshot: null,
        });
      }
      if (request.method() === "GET" && url.pathname.endsWith(`/fast/status/${FAST_TASK_ID}`)) {
        statusCount += 1;
        return json(route, 200, {
          task_id: FAST_TASK_ID,
          status: "done",
          lifecycle_status: "completed_bounded",
          stage: "completed",
          elapsed_sec: 1,
          result: fastResult,
          error: null,
        });
      }
      if (
        request.method() === "GET"
        && url.pathname.endsWith(`/api/transparency/fast/${FAST_TASK_ID}`)
      ) {
        transparencyCount += 1;
        return json(route, 200, {
          schema_version: "transparency-disclosure.v1",
          ai_generated: true,
          label: "AI-generated",
          verification_scope: "unsigned_pending_review",
          independently_validated: false,
          sidecar_path: "tenants/ui/pending_review/fast_mode/task/transparency/sidecar.json",
          sidecar_sha256: "a".repeat(64),
          record_count: 1,
          human_edit_record_count: 0,
          source_reference_count: 0,
          c2pa_signing_mode: "local_draft",
          final_artifact_c2pa_status: "unsigned_pending_review",
          package_available: true,
        });
      }
      return json(route, 200, {});
    });

    await page.goto("/fast");
    await expect(page.getByText("Bounded completion (pending review)")).toBeVisible();
    await expect(page.getByText("AI-generated content")).toBeVisible();
    await expect(page.getByText("Unsigned, pending human review")).toBeVisible();
    await expect(page.getByRole("button", {
      name: "Download transparency evidence package",
    })).toBeVisible();

    expect(submitCount).toBe(0);
    expect(readbackCount).toBeGreaterThanOrEqual(1);
    expect(statusCount).toBeGreaterThanOrEqual(1);
    expect(transparencyCount).toBe(1);
  });

  test("ambiguous submit sends one POST then recovers with GET", async ({ page }) => {
    let submitCount = 0;
    let readbackCount = 0;
    await seedBrowserState(page, false);
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (request.method() === "POST" && url.pathname.endsWith("/fast/submit")) {
        submitCount += 1;
        expect(request.headers()["idempotency-key"]).toMatch(
          /^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/,
        );
        return json(route, 502, { detail: { code: "ambiguous_proxy_failure" } });
      }
      if (request.method() === "GET" && url.pathname.endsWith("/submissions/idempotency")) {
        readbackCount += 1;
        return json(route, 200, {
          resource_type: "fast",
          resource_id: FAST_TASK_ID,
          scenario: "fast",
          status: "queued",
          submit_response: { task_id: FAST_TASK_ID, status: "queued" },
          result_snapshot: null,
        });
      }
      if (request.method() === "GET" && url.pathname.endsWith(`/fast/status/${FAST_TASK_ID}`)) {
        return json(route, 200, {
          task_id: FAST_TASK_ID,
          status: "done",
          lifecycle_status: "completed_bounded",
          stage: "completed",
          elapsed_sec: 1,
          result: fastResult,
          error: null,
        });
      }
      return json(route, 200, {});
    });

    await page.goto("/fast");
    await page.getByRole("textbox", { name: "Fast Mode" }).fill("Safe fixture product shot");
    await page.getByRole("button", { name: "Generate" }).click();
    await expect(page.getByText("Bounded completion (pending review)")).toBeVisible();

    expect(submitCount).toBe(1);
    expect(readbackCount).toBeGreaterThanOrEqual(1);
  });
});
