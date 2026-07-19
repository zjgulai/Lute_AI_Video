import { afterEach, describe, expect, it, vi } from "vitest";
import type { components } from "@/types/api.generated";

type GeneratedPublishMetadata = components["schemas"]["PublishMetadata"];

const GENERATED_METADATA_COMPILE_CASES: GeneratedPublishMetadata[] = [
  {},
  { title: "Reviewed" },
];
const GENERATED_METADATA_NULL_MUST_NOT_COMPILE: GeneratedPublishMetadata = {
  // @ts-expect-error Explicit null is not a strict optional string.
  title: null,
  description: "Reviewed",
  hook: "Reviewed",
  product_name: "Reviewed",
};
void GENERATED_METADATA_COMPILE_CASES;
void GENERATED_METADATA_NULL_MUST_NOT_COMPILE;

const ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f";
const PUBLISH_ATTEMPT_ID = "91ec3593-cc3c-42bf-99ee-c98655c5826b";
const POST_ID = "7512345678901234567";
const POST_URL = `https://www.tiktok.com/@fixture/video/${POST_ID}`;
const TIKTOK_PLATFORM_OPTIONS = {
  platform: "tiktok" as const,
  privacy_level: "SELF_ONLY" as const,
  disable_comment: true,
  disable_duet: true,
  disable_stitch: true,
  brand_content_toggle: false,
  brand_organic_toggle: false,
};
const SHOPIFY_PLATFORM_OPTIONS = {
  platform: "shopify" as const,
  product_id: "gid://shopify/Product/123456789",
};

function tiktokRequestOptions() {
  return {
    acceptanceId: ACCEPTANCE_ID,
    platformOptions: TIKTOK_PLATFORM_OPTIONS,
  };
}

function successResponse(): Response {
  return new Response(
    JSON.stringify({
      publish_attempt_id: PUBLISH_ATTEMPT_ID,
      acceptance_id: ACCEPTANCE_ID,
      platform: "tiktok",
      status: "published",
      success: true,
      post_id: POST_ID,
      post_url: POST_URL,
      receipt: {
        schema_version: "publish-receipt.v1",
        platform: "tiktok",
        protocol_version: "tiktok-content-posting-v2",
        completion_scope: "tiktok_direct_post",
        provider_operation_id: "v_pub_file_frontend_fixture",
        provider_resource_id: POST_ID,
        target_id: null,
        provider_status: "PUBLISH_COMPLETE",
        post_id: POST_ID,
        post_url: POST_URL,
        public_visibility_verified: true,
        observed_at: "2026-07-14T08:00:00Z",
        verified_by: "video_query",
        simulated: false,
      },
      acceptance_consumed: true,
      retry_allowed: false,
    }),
    {
      status: 200,
      headers: { "content-type": "application/json" },
    },
  );
}

async function loadApi(response: Response | (() => Response) = successResponse) {
  const fetchMock = vi.fn().mockImplementation(async () => (
    typeof response === "function" ? response() : response
  ));
  vi.stubGlobal("fetch", fetchMock);
  const api = await import("./api");
  api.setApiLogging(false);
  return { api, fetchMock, response };
}

describe("publish acceptance helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.resetModules();
    localStorage.clear();
  });

  it("makes zero requests without explicit valid acceptance authority", async () => {
    localStorage.setItem("acceptance_id", ACCEPTANCE_ID);
    localStorage.setItem("ai_video_acceptance_id", ACCEPTANCE_ID);
    const { api, fetchMock } = await loadApi();

    const attempts = [
      () => api.publishContent("tiktok", { title: "Reviewed" }),
      () => api.publishContent("tiktok", {}, { acceptanceId: "" }),
      () => api.publishContent("tiktok", {}, { acceptanceId: ACCEPTANCE_ID.toUpperCase() }),
      () => api.publishContent(
        "tiktok",
        {},
        { acceptanceId: "7f947625-2898-1e9e-9e71-dce4309e5f4f" },
      ),
      () => api.publishContent(
        "tiktok",
        {},
        { acceptanceId: "7f947625-2898-4e9e-7e71-dce4309e5f4f" },
      ),
      () => api.publishContent("tiktok", {}, { acceptanceId: ` ${ACCEPTANCE_ID}` }),
      () => api.publishVideo(ACCEPTANCE_ID, ["tiktok"], {}),
    ];

    for (const attempt of attempts) {
      await expect(attempt()).rejects.toThrow("Publish acceptance is required");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects zero, multiple, or unsupported platforms before network", async () => {
    const { api, fetchMock } = await loadApi();
    const options = tiktokRequestOptions();

    await expect(
      api.publishVideo("client-video", [], {}, options),
    ).rejects.toThrow("Exactly one publish platform is required");
    await expect(
      api.publishVideo(
        "client-video",
        ["tiktok", "shopify"],
        {},
        options,
      ),
    ).rejects.toThrow("Exactly one publish platform is required");
    await expect(
      api.publishVideo("client-video", ["instagram"], {}, options),
    ).rejects.toThrow("Unsupported publish platform");
    await expect(
      api.publishContent("TikTok", {}, options),
    ).rejects.toThrow("Unsupported publish platform");

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("requires exact platform-specific publish options before network", async () => {
    const { api, fetchMock } = await loadApi();
    const invalidTikTokOptions: unknown[] = [
      undefined,
      { ...TIKTOK_PLATFORM_OPTIONS, platform: "shopify" },
      { ...TIKTOK_PLATFORM_OPTIONS, disable_comment: 1 },
      { ...TIKTOK_PLATFORM_OPTIONS, privacy_level: "FRIENDS" },
      { ...TIKTOK_PLATFORM_OPTIONS, unknown: true },
    ];
    for (const platformOptions of invalidTikTokOptions) {
      await expect(
        api.publishContent("tiktok", {}, {
          acceptanceId: ACCEPTANCE_ID,
          platformOptions: platformOptions as never,
        }),
      ).rejects.toThrow(/publish options|platform options/i);
    }

    const invalidShopifyOptions: unknown[] = [
      TIKTOK_PLATFORM_OPTIONS,
      { platform: "shopify", product_id: "gid://shopify/Product/0" },
      { ...SHOPIFY_PLATFORM_OPTIONS, product_name: "must-not-authorize" },
    ];
    for (const platformOptions of invalidShopifyOptions) {
      await expect(
        api.publishContent("shopify", {}, {
          acceptanceId: ACCEPTANCE_ID,
          platformOptions: platformOptions as never,
        }),
      ).rejects.toThrow("Shopify publish options are invalid");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects legacy video IDs outside the exact backend path grammar before network", async () => {
    const { api, fetchMock } = await loadApi();
    const options = tiktokRequestOptions();
    const invalidVideoIds = [
      "",
      "a".repeat(129),
      "client/video",
      "client?video=1",
      "client%2Fvideo",
      "视频",
    ];

    for (const videoId of invalidVideoIds) {
      await expect(
        api.publishVideo(videoId, ["tiktok"], {}, options),
      ).rejects.toThrow("Legacy publish video ID is invalid");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("accepts one-character, 128-character, and ordinary safe legacy video IDs", async () => {
    const { api, fetchMock } = await loadApi();
    const options = tiktokRequestOptions();
    const validVideoIds = ["a", "a".repeat(128), "client_video-2026"];

    for (const videoId of validVideoIds) {
      await api.publishVideo(videoId, ["tiktok"], {}, options);
    }

    expect(fetchMock).toHaveBeenCalledTimes(validVideoIds.length);
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual(
      validVideoIds.map((videoId) => `http://localhost:8001/publish/${videoId}`),
    );
  });

  it("rejects unsafe metadata shape, types, and unknown fields before network", async () => {
    const { api, fetchMock } = await loadApi();
    const options = tiktokRequestOptions();
    const invalidMetadata: unknown[] = [
      null,
      [],
      "title=Reviewed",
      1,
      { title: "Reviewed", video_path: "/tmp/client.mp4" },
      { title: "Reviewed", credential: "not-allowed" },
      { title: 1 },
      { description: false },
      { hook: {} },
      { product_name: [] },
      { hashtags: "momlife,reviewed" },
      { tags: ["momlife", 2] },
    ];

    for (const metadata of invalidMetadata) {
      await expect(
        api.publishContent("tiktok", metadata, options),
      ).rejects.toThrow("Publish metadata is invalid");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects blank, control, overlong, prefixed, duplicate, and oversized metadata", async () => {
    const { api, fetchMock } = await loadApi();
    const options = tiktokRequestOptions();
    const invalidMetadata: unknown[] = [
      { title: "   " },
      { description: "bad\ntitle" },
      { hook: "bad\u0000hook" },
      { product_name: "bad\u007fname" },
      { title: "x".repeat(301) },
      { description: "x".repeat(5001) },
      { hook: "x".repeat(1001) },
      { product_name: "x".repeat(301) },
      { hashtags: ["#momlife"] },
      { tags: ["momlife", " momlife "] },
      { hashtags: ["x".repeat(101)] },
      { tags: [" "] },
      { tags: ["bad\ttag"] },
      { tags: Array.from({ length: 31 }, (_, index) => `tag-${index}`) },
      { description: "界".repeat(5000), hook: "界".repeat(1000) },
    ];

    for (const metadata of invalidMetadata) {
      await expect(
        api.publishContent("tiktok", metadata, options),
      ).rejects.toThrow("Publish metadata is invalid");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uses the backend canonical six-field projection for the UTF-8 16 KiB cap", async () => {
    const { api, fetchMock } = await loadApi();
    const options = tiktokRequestOptions();
    const oversized = {
      title: `界${"x".repeat(299)}`,
      description: "界".repeat(5000),
      hook: "x".repeat(1000),
    };
    const exactBoundary = {
      ...oversized,
      hook: "x".repeat(999),
    };
    const canonicalBytes = (metadata: typeof oversized) => new TextEncoder().encode(
      JSON.stringify({
        title: metadata.title,
        description: metadata.description,
        hook: metadata.hook,
        product_name: null,
        hashtags: [],
        tags: [],
      }),
    ).byteLength;

    expect(canonicalBytes(oversized)).toBe(16_385);
    expect(canonicalBytes(exactBoundary)).toBe(16_384);
    await expect(
      api.publishContent("tiktok", oversized, options),
    ).rejects.toThrow("Publish metadata is invalid");
    expect(fetchMock).not.toHaveBeenCalled();

    await api.publishContent("tiktok", exactBoundary, options);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.metadata).toEqual(exactBoundary);
    expect(body.metadata).not.toHaveProperty("product_name");
    expect(body.metadata).not.toHaveProperty("hashtags");
    expect(body.metadata).not.toHaveProperty("tags");
  });

  it("counts Unicode code points and rejects unpaired surrogates before network", async () => {
    const { api, fetchMock } = await loadApi();
    const options = tiktokRequestOptions();
    const emoji = "😀";
    const validMetadata = {
      title: emoji.repeat(300),
      description: emoji.repeat(300),
      hook: emoji.repeat(300),
      product_name: emoji.repeat(300),
      hashtags: [emoji.repeat(100)],
      tags: [emoji.repeat(100)],
    };

    await api.publishContent("tiktok", validMetadata, options);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(
      JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).metadata,
    ).toEqual(validMetadata);

    const invalidMetadata = [
      { title: emoji.repeat(301) },
      { tags: [emoji.repeat(101)] },
      { title: "\ud800" },
      { description: "\udc00" },
      { hook: "safe\ud800unsafe" },
      { product_name: "safe\udc00unsafe" },
      { hashtags: ["\ud800"] },
      { tags: ["\udc00"] },
    ];
    fetchMock.mockClear();
    for (const metadata of invalidMetadata) {
      await expect(
        api.publishContent("tiktok", metadata, options),
      ).rejects.toThrow("Publish metadata is invalid");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("matches backend compact UTF-8 bytes for quotes, backslashes, and emoji", async () => {
    const { api, fetchMock } = await loadApi();
    const options = tiktokRequestOptions();
    const exactBoundary = {
      title: `"\\😀${"x".repeat(297)}`,
      description: "界".repeat(5000),
      hook: "x".repeat(996),
    };
    const oversized = { ...exactBoundary, hook: "x".repeat(997) };
    const canonicalBytes = (metadata: typeof exactBoundary) => new TextEncoder().encode(
      JSON.stringify({
        title: metadata.title,
        description: metadata.description,
        hook: metadata.hook,
        product_name: null,
        hashtags: [],
        tags: [],
      }),
    ).byteLength;

    expect(Array.from(exactBoundary.title)).toHaveLength(300);
    expect(canonicalBytes(exactBoundary)).toBe(16_384);
    expect(canonicalBytes(oversized)).toBe(16_385);
    await api.publishContent("tiktok", exactBoundary, options);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fetchMock.mockClear();
    await expect(
      api.publishContent("tiktok", oversized, options),
    ).rejects.toThrow("Publish metadata is invalid");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends exactly one canonical strict normalized request", async () => {
    const { api, fetchMock } = await loadApi();

    await api.publishContent(
      "tiktok",
      {
        title: "  Reviewed  ",
        description: " Approved campaign. ",
        hashtags: [" momlife ", "wearablepump"],
      },
      tiktokRequestOptions(),
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/distribution/publish");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      acceptance_id: ACCEPTANCE_ID,
      platform: "tiktok",
      metadata: {
        title: "Reviewed",
        description: "Approved campaign.",
        hashtags: ["momlife", "wearablepump"],
      },
      platform_options: TIKTOK_PLATFORM_OPTIONS,
    });
  });

  it("legacy helper sends one strict request and treats its path as non-authority", async () => {
    const { api, fetchMock } = await loadApi();
    const videoId = "client_video-2026";

    await api.publishVideo(
      videoId,
      ["shopify"],
      {
        title: " Reviewed ",
        product_name: " Wearable Breast Pump ",
        tags: [" shopify ", "campaign"],
      },
      {
        acceptanceId: ACCEPTANCE_ID,
        platformOptions: SHOPIFY_PLATFORM_OPTIONS,
      },
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/publish/client_video-2026");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      acceptance_id: ACCEPTANCE_ID,
      platform: "shopify",
      metadata: {
        title: "Reviewed",
        product_name: "Wearable Breast Pump",
        tags: ["shopify", "campaign"],
      },
      platform_options: SHOPIFY_PLATFORM_OPTIONS,
    });
    const serialized = String(init?.body);
    expect(serialized).not.toContain(videoId);
    expect(serialized).not.toContain("video_path");
    expect(serialized).not.toContain("platforms");
  });

  it("reads one canonical publish attempt by UUID without a provider helper", async () => {
    const readback = {
      publish_attempt_id: PUBLISH_ATTEMPT_ID,
      acceptance_id: ACCEPTANCE_ID,
      platform: "tiktok",
      status: "published",
      error_code: null,
      post_id: POST_ID,
      post_url: POST_URL,
      receipt: JSON.parse(await successResponse().text()).receipt,
      acceptance_consumed: true,
      retry_allowed: false,
      created_at: "2026-07-14T07:59:00Z",
      updated_at: "2026-07-14T08:00:00Z",
    };
    const response = new Response(JSON.stringify(readback), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
    const { api, fetchMock } = await loadApi(response);

    await expect(api.fetchPublishAttempt("not-an-attempt")).rejects.toThrow(
      "Publish attempt ID is invalid",
    );
    expect(fetchMock).not.toHaveBeenCalled();

    await expect(api.fetchPublishAttempt(PUBLISH_ATTEMPT_ID)).resolves.toEqual(
      readback,
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      `http://localhost:8001/distribution/publish-attempts/${PUBLISH_ATTEMPT_ID}`,
    );
    expect(fetchMock.mock.calls[0][1]?.method).toBeUndefined();
  });

  it("does not retry a publish POST after a network error", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { api, fetchMock } = await loadApi();
    const rawMessage = `fixture network failure ${ACCEPTANCE_ID} private-campaign`;
    fetchMock.mockRejectedValueOnce(new TypeError(rawMessage));
    api.setApiLogging(true);

    await expect(
      api.publishContent("tiktok", {}, tiktokRequestOptions()),
    ).rejects.toThrow(rawMessage);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const requestLogs = JSON.stringify(logSpy.mock.calls);
    const errorLogs = JSON.stringify(errorSpy.mock.calls);
    expect(requestLogs).toContain("[body omitted]");
    expect(errorLogs).toContain("[body omitted]");
    expect(errorLogs).not.toContain(rawMessage);
    expect(errorLogs).not.toContain(ACCEPTANCE_ID);
    expect(errorLogs).not.toContain("private-campaign");
  });

  it("omits publish request and success bodies from debug logs without cloning", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const response = successResponse();
    const cloneSpy = vi.spyOn(response, "clone");
    const { api } = await loadApi(response);
    api.setApiLogging(true);

    await api.publishContent(
      "tiktok",
      { title: "Reviewed private campaign" },
      tiktokRequestOptions(),
    );

    const logs = JSON.stringify(logSpy.mock.calls);
    expect(logs.match(/\[body omitted\]/g)).toHaveLength(2);
    expect(logs).not.toContain(ACCEPTANCE_ID);
    expect(logs).not.toContain(PUBLISH_ATTEMPT_ID);
    expect(logs).not.toContain("Reviewed private campaign");
    expect(cloneSpy).not.toHaveBeenCalled();
  });

  it("omits publish error bodies from debug logs without reading or cloning", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const response = new Response(
      JSON.stringify({
        detail: {
          code: "publish_outcome_ambiguous",
          private_value: "fixture-sensitive-error",
        },
      }),
      {
        status: 502,
        statusText: "Bad Gateway",
        headers: { "content-type": "application/json" },
      },
    );
    const cloneSpy = vi.spyOn(response, "clone");
    const textSpy = vi.spyOn(response, "text");
    const { api } = await loadApi(response);
    api.setApiLogging(true);

    await expect(
      api.publishContent("tiktok", {}, tiktokRequestOptions()),
    ).rejects.toThrow("Publish failed (502)");

    const logs = JSON.stringify(errorSpy.mock.calls);
    expect(logs).toContain("[body omitted]");
    expect(logs).not.toContain("publish_outcome_ambiguous");
    expect(logs).not.toContain("fixture-sensitive-error");
    expect(cloneSpy).not.toHaveBeenCalled();
    expect(textSpy).not.toHaveBeenCalled();
  });

  it("omits custom-base canonical request and success bodies with query and trailing slash", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const response = successResponse();
    const cloneSpy = vi.spyOn(response, "clone");
    const textSpy = vi.spyOn(response, "text");
    const { api } = await loadApi(response);
    api.setApiLogging(true);
    const privateBody = JSON.stringify({ campaign: "custom-base-private-success" });

    await api.apiFetch(
      "https://backend.invalid/gateway/api/distribution/publish/?trace=fixture",
      { method: "POST", body: privateBody },
    );

    const logs = JSON.stringify(logSpy.mock.calls);
    expect(logs.match(/\[body omitted\]/g)).toHaveLength(2);
    expect(logs).not.toContain("custom-base-private-success");
    expect(logs).not.toContain(ACCEPTANCE_ID);
    expect(logs).not.toContain(PUBLISH_ATTEMPT_ID);
    expect(cloneSpy).not.toHaveBeenCalled();
    expect(textSpy).not.toHaveBeenCalled();
  });

  it("omits custom-base legacy request and HTTP error bodies without reading", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const response = new Response(
      JSON.stringify({ private_value: "custom-base-private-http-error" }),
      {
        status: 502,
        statusText: "Bad Gateway",
        headers: { "content-type": "application/json" },
      },
    );
    const cloneSpy = vi.spyOn(response, "clone");
    const textSpy = vi.spyOn(response, "text");
    const { api } = await loadApi(response);
    api.setApiLogging(true);

    const result = await api.apiFetch(
      "https://backend.invalid/gateway/api/publish/client_video-2026/?trace=fixture",
      {
        method: "POST",
        body: JSON.stringify({ campaign: "custom-base-private-request" }),
      },
    );

    expect(result.status).toBe(502);
    const logs = JSON.stringify([logSpy.mock.calls, errorSpy.mock.calls]);
    expect(logs.match(/\[body omitted\]/g)).toHaveLength(2);
    expect(logs).not.toContain("custom-base-private-request");
    expect(logs).not.toContain("custom-base-private-http-error");
    expect(cloneSpy).not.toHaveBeenCalled();
    expect(textSpy).not.toHaveBeenCalled();
  });

  it("omits custom-base legacy network errors and still makes one POST", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { api, fetchMock } = await loadApi();
    const rawMessage = `custom-base-network ${ACCEPTANCE_ID} private-network-value`;
    fetchMock.mockRejectedValueOnce(new TypeError(rawMessage));
    api.setApiLogging(true);

    await expect(
      api.apiFetch(
        "https://backend.invalid/gateway/api/publish/client_video-2026/?trace=fixture",
        {
          method: "POST",
          body: JSON.stringify({ campaign: "custom-base-private-network-request" }),
        },
      ),
    ).rejects.toThrow(rawMessage);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const logs = JSON.stringify([logSpy.mock.calls, errorSpy.mock.calls]);
    expect(logs.match(/\[body omitted\]/g)).toHaveLength(2);
    expect(logs).not.toContain("custom-base-private-network-request");
    expect(logs).not.toContain(rawMessage);
    expect(logs).not.toContain(ACCEPTANCE_ID);
  });

  it("does not classify unrelated publish-like route segments as mutations", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const { api, fetchMock } = await loadApi(() => new Response(
      JSON.stringify({ result: "ordinary-fixture-response" }),
      { status: 200, headers: { "content-type": "application/json" } },
    ));
    api.setApiLogging(true);
    const urls = [
      "https://backend.invalid/gateway/api/distribution/publish-preview/",
      "https://backend.invalid/gateway/api/publish/status/extra/",
      "https://backend.invalid/api/publisher/status/",
    ];

    for (const url of urls) {
      await api.apiFetch(url, {
        method: "POST",
        body: JSON.stringify({ marker: "ordinary-fixture-request" }),
      });
    }

    expect(fetchMock).toHaveBeenCalledTimes(3);
    const logs = JSON.stringify(logSpy.mock.calls);
    expect(logs).not.toContain("[body omitted]");
    expect(logs).toContain("ordinary-fixture-request");
    expect(logs).toContain("ordinary-fixture-response");
  });

  it("preserves the media logging label without reading or cloning media", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const response = new Response("fixture-binary", {
      status: 200,
      headers: { "content-type": "video/mp4" },
    });
    const cloneSpy = vi.spyOn(response, "clone");
    const textSpy = vi.spyOn(response, "text");
    const { api } = await loadApi(response);
    api.setApiLogging(true);

    await api.apiFetch("/api/media/final.mp4");

    const logs = JSON.stringify(logSpy.mock.calls);
    expect(logs).toContain("[media/binary]");
    expect(cloneSpy).not.toHaveBeenCalled();
    expect(textSpy).not.toHaveBeenCalled();
  });
});
