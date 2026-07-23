import { afterEach, describe, expect, it, vi } from "vitest";

const DISCLOSURE = {
  schema_version: "transparency-disclosure.v1",
  ai_generated: true,
  label: "AI-generated",
  verification_scope: "local_reader_only",
  independently_validated: false,
  sidecar_path: "tenants/tenant-a/pending_review/run/transparency/sidecar.json",
  sidecar_sha256: "a".repeat(64),
  record_count: 3,
  human_edit_record_count: 1,
  source_reference_count: 2,
  c2pa_signing_mode: "required",
  final_artifact_c2pa_status: "signed_local_readback",
  package_available: true,
};

async function loadApi(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  const api = await import("./api");
  api.setApiLogging(false);
  return { api, fetchMock };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.resetModules();
  localStorage.clear();
});

describe("transparency API helpers", () => {
  it("performs one authenticated read-only inspection for the exact resource", async () => {
    const { api, fetchMock } = await loadApi(new Response(JSON.stringify(DISCLOSURE), {
      status: 200,
      headers: { "content-type": "application/json" },
    }));

    await expect(api.getTransparencyDisclosure("scenario", "run-1")).resolves.toEqual(DISCLOSURE);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/api\/transparency\/scenario\/run-1$/);
    expect(fetchMock.mock.calls[0]?.[1]).not.toHaveProperty("method");
  });

  it("downloads only the server-built evidence package", async () => {
    const { api, fetchMock } = await loadApi(new Response("fixture-zip", {
      status: 200,
      headers: { "content-type": "application/zip" },
    }));
    const createObjectURL = vi.fn().mockReturnValue("blob:transparency-fixture");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    await api.downloadTransparencyPackage("fast", "task-1");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/api\/transparency\/fast\/task-1\/package$/);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:transparency-fixture");
  });
});
