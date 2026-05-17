import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import AdminTenantsPage from "./page";

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
    root.render(<AdminTenantsPage />);
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
});
