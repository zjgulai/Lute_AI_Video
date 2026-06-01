import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import SettingsPanel from "./SettingsPanel";
import { I18nProvider } from "@/i18n/I18nProvider";
import { setApiKey } from "./api";

const apiMocks = vi.hoisted(() => ({
  setApiBase: vi.fn(),
  setApiKey: vi.fn(),
  setDemoMode: vi.fn(),
  resetApiConfig: vi.fn(),
  testConnection: vi.fn(),
}));

// Mock api module
vi.mock("./api", () => ({
  getApiBase: () => "http://localhost:8001",
  getApiKey: () => "test-key",
  isDemoMode: () => false,
  maskApiKeyForDisplay: (value: string) => (value ? "Set" : "Not set"),
  setApiBase: apiMocks.setApiBase,
  setApiKey: apiMocks.setApiKey,
  setDemoMode: apiMocks.setDemoMode,
  resetApiConfig: apiMocks.resetApiConfig,
  testConnection: apiMocks.testConnection,
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

async function flushEffects() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("SettingsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.testConnection.mockResolvedValue({ ok: true, status: 200, data: {} });
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

  it("exposes API key input label, hint, and autocomplete semantics", () => {
    const { container, cleanup } = renderWithProvider(
      <SettingsPanel onClose={() => {}} />
    );
    const label = container.querySelector('label[for="settings-api-key"]');
    const input = container.querySelector("#settings-api-key") as HTMLInputElement | null;
    const hint = container.querySelector("#settings-api-key-hint");

    expect(label?.textContent).toContain("API Key");
    expect(input?.type).toBe("password");
    expect(input?.getAttribute("autocomplete")).toBe("current-password");
    expect(input?.getAttribute("aria-describedby")).toBe("settings-api-key-hint");
    expect(hint?.textContent).toContain("tenant key");
    cleanup();
  });

  it("announces connection test success and failure with accessible live regions", async () => {
    const { container, cleanup } = renderWithProvider(
      <SettingsPanel onClose={() => {}} />
    );
    const testButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Test connection")
    ) as HTMLButtonElement;

    await act(async () => {
      testButton.click();
    });
    await flushEffects();

    const status = container.querySelector('[role="status"]');
    expect(status?.getAttribute("aria-live")).toBe("polite");
    expect(status?.textContent).toContain("Connected");

    apiMocks.testConnection.mockResolvedValueOnce({
      ok: false,
      status: 401,
      error: "Invalid API key",
    });
    await act(async () => {
      testButton.click();
    });
    await flushEffects();

    const alert = container.querySelector('[role="alert"]');
    expect(alert?.getAttribute("aria-live")).toBe("assertive");
    expect(alert?.textContent).toContain("Invalid API key");
    cleanup();
  });

  it("saves the trimmed API key through an explicit button action", () => {
    const onClose = vi.fn();
    const { container, cleanup } = renderWithProvider(
      <SettingsPanel onClose={onClose} />
    );
    const input = container.querySelector("#settings-api-key") as HTMLInputElement;
    const saveButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Save")
    ) as HTMLButtonElement;

    act(() => {
      setInputValue(input, "  tenant-key-123  ");
      saveButton.click();
    });

    expect(saveButton.type).toBe("button");
    expect(vi.mocked(setApiKey)).toHaveBeenCalledWith("tenant-key-123");
    expect(onClose).toHaveBeenCalledTimes(1);
    cleanup();
  });

  it("documents the Settings API key accessibility contract", () => {
    const contract = readFileSync(
      join(process.cwd(), "..", "configs/settings-api-key-accessibility-contract.yaml"),
      "utf8",
    );
    const runbook = readFileSync(
      join(process.cwd(), "..", "docs/runbooks/settings-api-key-accessibility.md"),
      "utf8",
    );

    for (const token of [
      "settings-api-key",
      "settings-api-key-hint",
      "role_status_on_success",
      "role_alert_on_failure",
      "save_button_type_button",
    ]) {
      expect(contract).toContain(token);
    }

    for (const token of [
      "npm test -- --run src/components/SettingsPanel.test.tsx",
      "aria-describedby",
      "role=\"alert\"",
      "不触发生成接口",
    ]) {
      expect(runbook).toContain(token);
    }
  });
});
