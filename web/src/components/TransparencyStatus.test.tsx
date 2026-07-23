import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import TransparencyStatus from "./TransparencyStatus";

const inspect = vi.fn();
const download = vi.fn();

vi.mock("./api", () => ({
  getTransparencyDisclosure: (...args: unknown[]) => inspect(...args),
  downloadTransparencyPackage: (...args: unknown[]) => download(...args),
}));

function renderStatus(resourceType?: "fast" | "scenario", resourceId?: string) {
  localStorage.setItem("app-locale", "zh");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <TransparencyStatus resourceType={resourceType} resourceId={resourceId} />
      </I18nProvider>,
    );
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

afterEach(() => {
  inspect.mockReset();
  download.mockReset();
  document.body.innerHTML = "";
});

describe("TransparencyStatus", () => {
  it("always labels generated output and blocks package when identity is missing", () => {
    const { container, cleanup } = renderStatus();

    expect(container.textContent).toContain("AI 生成内容");
    expect(container.textContent).toContain("透明度完整性不可验证");
    expect(container.querySelector("[data-transparency-package]")).toBeNull();
    expect(inspect).not.toHaveBeenCalled();
    cleanup();
  });

  it("shows local Reader scope without implying independent validation", async () => {
    inspect.mockResolvedValue({
      schema_version: "transparency-disclosure.v1",
      ai_generated: true,
      label: "AI-generated",
      verification_scope: "local_reader_only",
      independently_validated: false,
      sidecar_path: "tenants/a/pending_review/run/transparency/sidecar.json",
      sidecar_sha256: "a".repeat(64),
      record_count: 3,
      human_edit_record_count: 1,
      source_reference_count: 2,
      c2pa_signing_mode: "required",
      final_artifact_c2pa_status: "signed_local_readback",
      package_available: true,
    });
    const { container, cleanup } = renderStatus("scenario", "run-1");
    await flush();

    expect(inspect).toHaveBeenCalledTimes(1);
    expect(inspect).toHaveBeenCalledWith(
      "scenario",
      "run-1",
      expect.objectContaining({ signal: expect.any(Object) }),
    );
    expect(container.textContent).toContain("已签名并由本地 Reader 回读");
    expect(container.textContent).toContain("不代表独立验证或法律合规");
    const button = container.querySelector<HTMLButtonElement>("[data-transparency-package]");
    expect(button).not.toBeNull();
    await act(async () => button?.click());
    expect(download).toHaveBeenCalledWith("scenario", "run-1");
    cleanup();
  });

  it("shows unsigned pending-review truth and blocks on integrity failure", async () => {
    inspect.mockRejectedValue(new Error("integrity"));
    const failed = renderStatus("fast", "task-1");
    await flush();
    expect(failed.container.textContent).toContain("透明度完整性不可验证");
    expect(failed.container.querySelector("[data-transparency-package]")).toBeNull();
    failed.cleanup();

    inspect.mockResolvedValue({
      schema_version: "transparency-disclosure.v1",
      ai_generated: true,
      label: "AI-generated",
      verification_scope: "unsigned_pending_review",
      independently_validated: false,
      sidecar_path: "tenants/a/pending_review/fast_mode/task/transparency/sidecar.json",
      sidecar_sha256: "b".repeat(64),
      record_count: 1,
      human_edit_record_count: 0,
      source_reference_count: 0,
      c2pa_signing_mode: "local_draft",
      final_artifact_c2pa_status: "unsigned_pending_review",
      package_available: true,
    });
    const unsigned = renderStatus("fast", "task-2");
    await flush();
    expect(unsigned.container.textContent).toContain("未签名，待人工审核");
    unsigned.cleanup();
  });
});
