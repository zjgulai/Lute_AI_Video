import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Nav from "./Nav";
import { I18nProvider } from "@/i18n/I18nProvider";

vi.mock("next/navigation", () => ({
  usePathname: () => "/toolbox",
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

function renderNav() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <Nav />
      </I18nProvider>,
    );
  });

  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

describe("Nav", () => {
  beforeEach(() => {
    localStorage.setItem("app-locale", "en");
    sessionStorage.setItem("hermes_admin_visible", "0");
  });

  it("exposes the toolbox as a top-level navigation destination", () => {
    const { container, cleanup } = renderNav();
    try {
      const toolboxLink = Array.from(container.querySelectorAll("a")).find(
        (link) => link.getAttribute("href") === "/toolbox",
      );
      expect(toolboxLink).toBeTruthy();
      expect(toolboxLink?.textContent).toContain("Toolbox");
      expect(toolboxLink?.getAttribute("aria-label")).toBe("Toolbox");
    } finally {
      cleanup();
    }
  });

  it("keeps the locale switch compact on mobile navigation", () => {
    const { container, cleanup } = renderNav();
    try {
      const localeButton = container.querySelector("button[aria-label='切换到中文']");
      expect(localeButton).not.toBeNull();
      expect(localeButton?.className).toContain("min-w-[42px]");
      const slash = Array.from(localeButton?.querySelectorAll("span") ?? []).find(
        (span) => span.textContent === "/",
      );
      expect(slash?.className).toContain("hidden sm:inline");
    } finally {
      cleanup();
    }
  });
});
