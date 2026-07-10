import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/i18n/I18nProvider";
import { useAppStore } from "@/stores/useAppStore";
import { usePipelineStore } from "@/stores/usePipelineStore";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("./api", () => ({
  getScenarioStatus: vi.fn(),
  logStateChange: vi.fn(),
}));

import PipelineStatusBar from "./PipelineStatusBar";
import { getScenarioStatus } from "./api";

const notificationInstances = vi.fn();

class MockNotification {
  static permission: NotificationPermission = "default";

  static requestPermission = vi.fn(async (): Promise<NotificationPermission> => {
    MockNotification.permission = "granted";
    return "granted";
  });

  constructor(title: string, options?: NotificationOptions) {
    notificationInstances({ title, options });
  }
}

const originalNotification = Object.getOwnPropertyDescriptor(globalThis, "Notification");

function installNotification(permission: NotificationPermission) {
  MockNotification.permission = permission;
  MockNotification.requestPermission.mockClear();
  notificationInstances.mockClear();
  Object.defineProperty(globalThis, "Notification", {
    configurable: true,
    value: MockNotification,
  });
}

async function renderStatusBar() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <I18nProvider>
        <PipelineStatusBar />
      </I18nProvider>,
    );
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

describe("PipelineStatusBar notifications", () => {
  beforeAll(() => {
    Object.defineProperty(globalThis, "Notification", {
      configurable: true,
      value: MockNotification,
    });
  });

  afterAll(() => {
    if (originalNotification) {
      Object.defineProperty(globalThis, "Notification", originalNotification);
    } else {
      Reflect.deleteProperty(globalThis, "Notification");
    }
  });

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("app-locale", "en");
    usePipelineStore.setState({
      activePipeline: null,
      dismissedPipelineLabels: [],
    });
    useAppStore.setState({ toast: null });
    vi.clearAllMocks();
  });

  it("requests permission only after the user clicks the notification control", async () => {
    installNotification("default");
    vi.mocked(getScenarioStatus).mockResolvedValue({
      status: "running",
      current_step: "scripts",
      steps: {
        strategy: { status: "done" },
        scripts: { status: "running" },
      },
      errors: [],
    } as never);
    usePipelineStore.getState().startActivePipeline({
      label: "s1_notification_permission",
      scenario: "s1",
      startedAt: Date.now(),
    });

    const { container, cleanup } = await renderStatusBar();
    try {
      expect(MockNotification.requestPermission).not.toHaveBeenCalled();
      const button = container.querySelector(
        "button[aria-label='Enable desktop notifications']",
      ) as HTMLButtonElement | null;
      expect(button).not.toBeNull();

      await act(async () => {
        button?.click();
        await Promise.resolve();
      });

      expect(MockNotification.requestPermission).toHaveBeenCalledTimes(1);
      expect(useAppStore.getState().toast?.message).toBe("Desktop notifications enabled");
    } finally {
      cleanup();
    }
  });

  it("sends an English desktop notification when a pipeline pauses", async () => {
    installNotification("granted");
    vi.mocked(getScenarioStatus).mockResolvedValue({
      status: "paused",
      current_step: "scripts",
      steps: {
        strategy: { status: "done" },
        scripts: { status: "done" },
        keyframe_images: { status: "pending" },
      },
      errors: [],
    } as never);
    usePipelineStore.getState().startActivePipeline({
      label: "s1_notification_paused",
      scenario: "s1",
      startedAt: Date.now(),
    });

    const { cleanup } = await renderStatusBar();
    try {
      expect(notificationInstances).toHaveBeenCalledTimes(1);
      expect(notificationInstances).toHaveBeenCalledWith({
        title: "Review needed",
        options: expect.objectContaining({
          body: "A step completed — your review is needed",
          tag: "s1_notification_paused-paused",
        }),
      });
    } finally {
      cleanup();
    }
  });
});
