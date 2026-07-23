import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/i18n/I18nProvider";

import AdminTenantDetailClient from "./AdminTenantDetailClient";

const adminFetchJson = vi.fn();
vi.mock("@/components/api", async () => {
  const actual = await vi.importActual<typeof import("@/components/api")>("@/components/api");
  return {
    ...actual,
    adminFetchJson: (...args: unknown[]) => adminFetchJson(...args),
  };
});

vi.mock("next/link", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const TENANT = {
  id: "tenant-uuid",
  tenant_id: "momcozy-marketing",
  display_name: "Marketing",
  contact_email: "",
  status: "active",
  keys: [
    {
      id: "key-uuid",
      key_preview: "abcdef...",
      label: "rotation replacement",
      status: "active",
      created_at: "2026-07-10T00:00:00Z",
      expires_at: "2026-10-08T23:59:59Z",
      last_used_at: null,
    },
  ],
};

function renderDetail() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(
    <I18nProvider>
      <AdminTenantDetailClient tenantId="momcozy-marketing" />
    </I18nProvider>,
  ));
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

describe("AdminTenantDetailClient key expiry", () => {
  beforeEach(() => {
    localStorage.setItem("app-locale", "en");
    adminFetchJson.mockReset();
  });

  it("shows expiry and sends an explicit expiry when creating a key", async () => {
    adminFetchJson.mockResolvedValueOnce(TENANT);
    const { container, cleanup } = renderDetail();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

    expect(container.textContent).toContain("expires");
    const newKeyButton = Array.from(container.querySelectorAll("button"))
      .find((button) => /new key/i.test(button.textContent || ""));
    await act(async () => { newKeyButton?.click(); });

    const form = container.querySelector("form");
    const expiryInput = form?.querySelector('input[type="date"]') as HTMLInputElement | null;
    expect(expiryInput?.value).toMatch(/^\d{4}-\d{2}-\d{2}$/);

    adminFetchJson.mockResolvedValueOnce({ id: "new-key", api_key: "one-time-key" });
    await act(async () => {
      form?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    const postCall = adminFetchJson.mock.calls.find(
      (call: unknown[]) => (call[1] as { method?: string })?.method === "POST"
    );
    const body = JSON.parse((postCall?.[1] as { body: string }).body) as {
      expires_at?: string;
    };
    expect(body.expires_at).toMatch(/^\d{4}-\d{2}-\d{2}T23:59:59Z$/);
    cleanup();
  });

  it("renders critical tenant-detail controls in Chinese", async () => {
    localStorage.setItem("app-locale", "zh");
    adminFetchJson.mockResolvedValueOnce(TENANT);
    const { container, cleanup } = renderDetail();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

    expect(container.textContent).toContain("返回租户列表");
    expect(container.textContent).toContain("API 密钥");
    expect(container.textContent).toContain("停用租户");
    expect(container.textContent).toContain("租户 ID");
    expect(container.textContent).toContain("到期日");
    expect(container.querySelector('button[aria-label="撤销密钥 abcdef..."]')).toBeTruthy();

    const newKeyButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("新建密钥"),
    ) as HTMLButtonElement;
    await act(async () => newKeyButton.click());
    expect(container.querySelector('[role="dialog"][aria-modal="true"]')).toBeTruthy();
    expect(container.querySelector('button[aria-label="关闭 API 密钥对话框"]')).toBeTruthy();
    expect(container.querySelector('input[aria-label="API 密钥标签"]')).toBeTruthy();
    cleanup();
  });
});
