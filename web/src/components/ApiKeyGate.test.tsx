import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import ApiKeyGate from "./ApiKeyGate";
import { I18nProvider } from "@/i18n/I18nProvider";

vi.mock("./api", () => ({
  getApiKey: () => "prefilled-key",
  setApiKey: vi.fn(),
  apiFetch: vi.fn().mockResolvedValue(new Response("{}", { status: 200 })),
}));

function renderWithProvider(ui: React.ReactElement) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(<I18nProvider>{ui}</I18nProvider>);
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("ApiKeyGate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("app-locale", "en");
  });

  it("prefills the key input from configured API key", () => {
    const { container, cleanup } = renderWithProvider(<ApiKeyGate onUnlock={() => {}} />);
    const input = container.querySelector("#apikey-input") as HTMLInputElement | null;
    expect(input?.value).toBe("prefilled-key");
    cleanup();
  });
});
