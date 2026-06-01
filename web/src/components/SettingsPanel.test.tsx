import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import SettingsPanel from "./SettingsPanel";
import { I18nProvider } from "@/i18n/I18nProvider";

// Mock api module
vi.mock("./api", () => ({
  getApiBase: () => "http://localhost:8001",
  getApiKey: () => "test-key",
  isDemoMode: () => false,
  maskApiKeyForDisplay: (value: string) => (value ? "Set" : "Not set"),
  setApiBase: vi.fn(),
  setApiKey: vi.fn(),
  setDemoMode: vi.fn(),
  resetApiConfig: vi.fn(),
  testConnection: vi.fn().mockResolvedValue({ ok: true, status: 200, data: {} }),
}));

function renderWithProvider(ui: React.ReactElement) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<I18nProvider>{ui}</I18nProvider>);
  });
  return { container, root, cleanup: () => {
    act(() => root.unmount());
    document.body.removeChild(container);
  }};
}

describe("SettingsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("app-locale", "en");
  });

  it("renders API configuration inputs", () => {
    const { container, cleanup } = renderWithProvider(
      <SettingsPanel onClose={() => {}} />
    );
    expect(container.textContent).toContain("Settings");
    expect(container.textContent).toContain("Backend access");
    expect(container.textContent).toContain("Target host");
    expect(container.querySelector('input[type="text"]')).not.toBeNull();
    expect(container.querySelector('input[type="password"]')).not.toBeNull();
    cleanup();
  });

  it("switches between settings tabs", () => {
    const { container, cleanup } = renderWithProvider(
      <SettingsPanel onClose={() => {}} />
    );
    const providersTab = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent?.includes("Providers")
    );
    expect(providersTab).toBeTruthy();
    act(() => providersTab?.click());
    expect(container.textContent).toContain("Provider stack");
    expect(container.textContent).toContain("DeepSeek");
    expect(container.textContent).toContain("poyo.ai Seedance");
    cleanup();
  });

  it("calls onClose when cancel button is clicked", () => {
    const onClose = vi.fn();
    const { container, cleanup } = renderWithProvider(
      <SettingsPanel onClose={onClose} />
    );
    const cancelBtn = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent?.includes("Cancel")
    );
    expect(cancelBtn).toBeTruthy();
    act(() => cancelBtn?.click());
    expect(onClose).toHaveBeenCalledTimes(1);
    cleanup();
  });
});
