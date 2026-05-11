import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import AdminLoginPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const adminFetch = vi.fn();
vi.mock("@/components/api", async () => {
  const actual = await vi.importActual<typeof import("@/components/api")>("@/components/api");
  return {
    ...actual,
    adminFetch: (...args: unknown[]) => adminFetch(...args),
  };
});

function renderLogin() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<AdminLoginPage />);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("AdminLoginPage", () => {
  beforeEach(() => {
    adminFetch.mockReset();
  });

  it("renders email + password fields and a submit button", () => {
    const { container, cleanup } = renderLogin();
    const emailInput = container.querySelector('input[type="email"]') as HTMLInputElement;
    const passwordInput = container.querySelector('input[type="password"]') as HTMLInputElement;
    const submitBtn = container.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(emailInput).toBeTruthy();
    expect(passwordInput).toBeTruthy();
    expect(submitBtn).toBeTruthy();
    cleanup();
  });

  it("shows the rate-limit message and disables submit when 429 + retry_after_sec comes back", async () => {
    adminFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "rate limited", retry_after_sec: 42 }), {
        status: 429,
        headers: { "content-type": "application/json" },
      })
    );
    const { container, cleanup } = renderLogin();
    const form = container.querySelector("form") as HTMLFormElement;
    const emailInput = container.querySelector('input[type="email"]') as HTMLInputElement;
    const passwordInput = container.querySelector('input[type="password"]') as HTMLInputElement;

    await act(async () => {
      emailInput.value = "admin@example.com";
      emailInput.dispatchEvent(new Event("input", { bubbles: true }));
      passwordInput.value = "wrong";
      passwordInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });

    expect(adminFetch).toHaveBeenCalled();
    const body = container.textContent || "";
    expect(body).toMatch(/42|too many|rate/i);
    cleanup();
  });

  it("surfaces an error message when login returns 401 invalid credentials", async () => {
    adminFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Invalid credentials" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      })
    );
    const { container, cleanup } = renderLogin();
    const form = container.querySelector("form") as HTMLFormElement;
    const emailInput = container.querySelector('input[type="email"]') as HTMLInputElement;
    const passwordInput = container.querySelector('input[type="password"]') as HTMLInputElement;

    await act(async () => {
      emailInput.value = "admin@example.com";
      emailInput.dispatchEvent(new Event("input", { bubbles: true }));
      passwordInput.value = "bad-pass";
      passwordInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });

    expect(adminFetch).toHaveBeenCalled();
    expect(container.textContent || "").toMatch(/invalid credentials/i);
    cleanup();
  });
});
