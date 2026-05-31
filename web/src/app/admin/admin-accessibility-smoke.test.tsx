import { describe, expect, it, vi, beforeEach } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import type React from "react";

import AdminDashboardPage from "./dashboard/page";
import AdminHealthPage from "./health/page";
import AdminLayout from "./layout";
import AdminLoginPage from "./login/page";
import AdminLogsPage from "./logs/page";
import AdminTenantsPage from "./tenants/page";
import AdminSidebar from "@/components/admin/AdminSidebar";

const navigationState = vi.hoisted(() => ({
  pathname: "/admin/dashboard",
  router: {
    push: vi.fn(),
  },
}));

const adminFetch = vi.hoisted(() => vi.fn());
const adminFetchJson = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  usePathname: () => navigationState.pathname,
  useRouter: () => navigationState.router,
  redirect: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, className, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={String(href)} className={className} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/components/api", async () => {
  const actual = await vi.importActual<typeof import("@/components/api")>("@/components/api");
  return {
    ...actual,
    adminFetch: (...args: unknown[]) => adminFetch(...args),
    adminFetchJson: (...args: unknown[]) => adminFetchJson(...args),
  };
});

function render(node: React.ReactElement) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(node);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

async function flushEffects() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

const dashboardSummary = {
  tenant_count: 2,
  tenant_count_today: 1,
  pipeline_runs_today: { total: 12, success: 10, failed: 1, running: 1 },
  error_rate_24h: 0.08,
  recent_errors: [
    {
      id: "err-1",
      tenant_id: "acme",
      scenario: "s1",
      error_code: "TIMEOUT",
      message: "DeepSeek timeout",
      created_at: "2026-05-31T00:00:00Z",
    },
  ],
};

const healthStatus = {
  checked_at: "2026-05-31T00:00:00Z",
  services: {
    postgres: { status: "healthy", latency_ms: 5 },
    deepseek: { status: "degraded", latency_ms: 650, available: true },
  },
};

const logsResponse = {
  items: [
    {
      id: "log-1",
      tenant_id: "acme",
      scenario: "s1",
      error_code: "TIMEOUT",
      message: "DeepSeek timeout",
      created_at: "2026-05-31T00:00:00Z",
    },
  ],
  total: 1,
};

const tenantsResponse = {
  items: [
    {
      id: "tenant-1",
      tenant_id: "acme",
      display_name: "ACME Corp",
      contact_email: "ops@acme.test",
      status: "active",
      key_count: 2,
      created_at: "2026-05-01T00:00:00Z",
      last_active: "2026-05-31T00:00:00Z",
    },
  ],
  total: 1,
};

function installAdminMocks() {
  adminFetchJson.mockImplementation((path: string) => {
    if (path === "/api/admin/auth/session") {
      return Promise.resolve({ authenticated: true, admin_id: "admin-1", email: "admin@example.com" });
    }
    if (path === "/api/admin/dashboard/summary") return Promise.resolve(dashboardSummary);
    if (path === "/api/admin/health/status") return Promise.resolve(healthStatus);
    if (path === "/api/admin/health/history?hours=24") return Promise.resolve({ checks: [] });
    if (path.startsWith("/api/admin/logs")) return Promise.resolve(logsResponse);
    if (path.startsWith("/api/admin/tenants")) return Promise.resolve(tenantsResponse);
    return Promise.resolve({});
  });
}

describe("admin accessibility smoke", () => {
  beforeEach(() => {
    navigationState.pathname = "/admin/dashboard";
    navigationState.router.push.mockReset();
    adminFetch.mockReset();
    adminFetchJson.mockReset();
    installAdminMocks();
  });

  it("renders login with labeled fields and alert semantics without backend", async () => {
    adminFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Invalid credentials" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );
    const { container, cleanup } = render(<AdminLoginPage />);

    expect(container.querySelector('label[for="admin-email"]')?.textContent).toContain("Admin email");
    expect(container.querySelector('label[for="admin-password"]')?.textContent).toContain("Admin password");

    const emailInput = container.querySelector("#admin-email") as HTMLInputElement;
    const passwordInput = container.querySelector("#admin-password") as HTMLInputElement;
    const form = container.querySelector("form") as HTMLFormElement;

    await act(async () => {
      emailInput.value = "admin@example.com";
      emailInput.dispatchEvent(new Event("input", { bubbles: true }));
      passwordInput.value = "wrong";
      passwordInput.dispatchEvent(new Event("input", { bubbles: true }));
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    await flushEffects();

    expect(container.querySelector('[role="alert"]')?.textContent).toMatch(/invalid credentials/i);
    expect(container.querySelector('button[type="submit"]')?.getAttribute("aria-describedby")).toBe("admin-login-error");
    cleanup();
  });

  it("renders sidebar navigation with active page semantics", () => {
    navigationState.pathname = "/admin/logs";
    const { container, cleanup } = render(<AdminSidebar />);

    expect(container.querySelector('nav[aria-label="Admin navigation"]')).toBeTruthy();
    const activeLink = container.querySelector('a[aria-current="page"]');
    expect(activeLink?.textContent).toContain("Logs");
    cleanup();
  });

  it("renders authenticated admin layout landmark and logout control", async () => {
    const { container, cleanup } = render(
      <AdminLayout>
        <h1>Admin child page</h1>
      </AdminLayout>,
    );
    expect(container.querySelector('[role="status"][aria-label="Loading admin session"]')).toBeTruthy();
    await flushEffects();

    expect(container.querySelector("main")?.textContent).toContain("Admin child page");
    expect(container.querySelector('button[aria-label="Logout admin session"]')).toBeTruthy();
    cleanup();
  });

  it("renders key admin pages with headings and labeled controls from mocked data", async () => {
    const cases: Array<{ name: string; node: React.ReactElement; expected: string[] }> = [
      { name: "dashboard", node: <AdminDashboardPage />, expected: ["Dashboard", "Refresh"] },
      { name: "logs", node: <AdminLogsPage />, expected: ["System Logs", "Filter logs by scenario", "Filter logs by tenant ID"] },
      { name: "health", node: <AdminHealthPage />, expected: ["System Health", "Check Now"] },
      { name: "tenants", node: <AdminTenantsPage />, expected: ["Tenants", "Search tenants", "New Tenant"] },
    ];

    for (const testCase of cases) {
      const { container, cleanup } = render(testCase.node);
      await flushEffects();

      const text = container.textContent || "";
      expect(text, `${testCase.name} should render content`).toContain(testCase.expected[0]);
      for (const expected of testCase.expected.slice(1)) {
        expect(
          container.querySelector(`[aria-label="${expected}"]`) || text.includes(expected),
          `${testCase.name} should expose ${expected}`,
        ).toBeTruthy();
      }
      cleanup();
    }
  });

  it("renders tenant creation dialog with dialog semantics and labeled fields", async () => {
    const { container, cleanup } = render(<AdminTenantsPage />);
    await flushEffects();

    const newTenantButton = Array.from(container.querySelectorAll("button")).find((button) =>
      /new tenant/i.test(button.textContent || ""),
    ) as HTMLButtonElement;
    await act(async () => {
      newTenantButton.click();
    });

    expect(container.querySelector('[role="dialog"][aria-modal="true"]')).toBeTruthy();
    expect(container.querySelector('label[for="admin-new-tenant-id"]')?.textContent).toContain("Tenant ID");
    expect(container.querySelector('label[for="admin-new-display-name"]')?.textContent).toContain("Display name");
    expect(container.querySelector('label[for="admin-new-contact-email"]')?.textContent).toContain("Contact email");
    expect(container.querySelector('button[aria-label="Close new tenant dialog"]')).toBeTruthy();
    cleanup();
  });
});
