import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import AdminTenantsPage from "./page";
import { I18nProvider } from "@/i18n/I18nProvider";

const adminFetchJson = vi.fn();
vi.mock("@/components/api", async () => {
  const actual = await vi.importActual<typeof import("@/components/api")>("@/components/api");
  return {
    ...actual,
    adminFetchJson: (...args: unknown[]) => adminFetchJson(...args),
  };
});

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) =>
    `<a href="${href}">${children}</a>` as unknown as React.ReactElement,
}));

const SAMPLE = {
  items: [
    {
      id: "uuid-1",
      tenant_id: "acme",
      display_name: "ACME Corp",
      contact_email: "ops@acme.test",
      status: "active",
      key_count: 3,
      created_at: "2026-05-01T00:00:00Z",
      last_active: "2026-05-17T10:00:00Z",
    },
  ],
  total: 1,
};

function render() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<I18nProvider><AdminTenantsPage /></I18nProvider>);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("AdminTenantsPage", () => {
  beforeEach(() => {
    localStorage.setItem("app-locale", "en");
    adminFetchJson.mockReset();
  });

  it("renders tenant rows after fetch", async () => {
    adminFetchJson.mockResolvedValueOnce(SAMPLE);
    const { container, cleanup } = render();
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(adminFetchJson).toHaveBeenCalled();
    const callPath = (adminFetchJson.mock.calls[0]?.[0] || "") as string;
    expect(callPath).toContain("/api/admin/tenants");
    const text = container.textContent || "";
    expect(text).toMatch(/acme|ACME/i);
    cleanup();
  });

  it("renders error state when fetch fails", async () => {
    adminFetchJson.mockRejectedValueOnce(new Error("DB down"));
    const { container, cleanup } = render();
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(container.textContent || "").toMatch(/failed/i);
    cleanup();
  });

  it("localizes table headers, status, and empty state in Chinese", async () => {
    localStorage.setItem("app-locale", "zh");
    adminFetchJson.mockResolvedValueOnce(SAMPLE);
    const first = render();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(first.container.textContent).toContain("租户");
    expect(first.container.textContent).toContain("状态");
    expect(first.container.textContent).toContain("密钥数");
    expect(first.container.textContent).toContain("启用");
    first.cleanup();

    adminFetchJson.mockResolvedValueOnce({ items: [], total: 0 });
    const empty = render();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(empty.container.textContent).toContain("暂无租户");
    empty.cleanup();
  });

  it("issues POST /api/admin/tenants when create form is submitted", async () => {
    adminFetchJson.mockResolvedValueOnce(SAMPLE);
    const { container, cleanup } = render();
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });

    const newTenantBtn = Array.from(container.querySelectorAll("button"))
      .find((b) => /new tenant/i.test(b.textContent || "")) as HTMLButtonElement | undefined;
    expect(newTenantBtn).toBeTruthy();
    await act(async () => { newTenantBtn?.click(); });

    const form = container.querySelector("form") as HTMLFormElement | null;
    expect(form).toBeTruthy();
    const tenantIdInput = container.querySelector('input[placeholder*="tenant" i]') as HTMLInputElement | null
      || (form?.querySelectorAll("input")[0] as HTMLInputElement);
    const displayInput = (form?.querySelectorAll("input")[1] as HTMLInputElement);
    const emailInput = container.querySelector('input[type="email"]') as HTMLInputElement
      || (form?.querySelectorAll("input")[2] as HTMLInputElement);

    await act(async () => {
      tenantIdInput.value = "newtenant";
      tenantIdInput.dispatchEvent(new Event("input", { bubbles: true }));
      displayInput.value = "New Co";
      displayInput.dispatchEvent(new Event("input", { bubbles: true }));
      emailInput.value = "ops@new.test";
      emailInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    adminFetchJson.mockResolvedValueOnce({});
    adminFetchJson.mockResolvedValueOnce(SAMPLE);
    await act(async () => {
      form?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });

    const postCall = adminFetchJson.mock.calls.find(
      (c: unknown[]) => (c[1] as { method?: string })?.method === "POST"
    );
    expect(postCall).toBeTruthy();
    expect(postCall?.[0]).toBe("/api/admin/tenants");
    cleanup();
  });
});
