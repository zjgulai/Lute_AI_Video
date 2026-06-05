"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { House, FilmSlate, FolderOpen, Gear, ShieldCheck, Toolbox } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import { useAppStore } from "@/stores/useAppStore";
import { usePipelineStore } from "@/stores/usePipelineStore";
import { useExpertStore } from "@/stores/useExpertStore";
import { buildAdminUrl } from "./api";

export default function Nav() {
  const pathname = usePathname();
  const { locale, setLocale, t } = useI18n();
  const resetApp = useAppStore((s) => s.resetApp);
  const resetPipeline = usePipelineStore((s) => s.resetAll);
  const resetExpert = useExpertStore((s) => s.resetExpert);
  const [adminVisible, setAdminVisible] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return sessionStorage.getItem("hermes_admin_visible") === "1";
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    const CACHE_KEY = "hermes_admin_visible";
    if (sessionStorage.getItem(CACHE_KEY) !== null) return;

    let cancelled = false;
    fetch(buildAdminUrl("/api/admin/auth/session"), { credentials: "include" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const visible = Boolean(data?.authenticated);
        if (!cancelled) {
          sessionStorage.setItem(CACHE_KEY, visible ? "1" : "0");
          if (visible) setAdminVisible(true);
        }
      })
      .catch(() => {
        if (!cancelled) sessionStorage.setItem(CACHE_KEY, "0");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleHomeClick = () => {
    const hasActiveRun = !!usePipelineStore.getState().activePipeline;
    if (!hasActiveRun) {
      localStorage.removeItem("ai_video_thread_id");
      localStorage.removeItem("ai_video_expert_session");
      resetPipeline();
      resetExpert();
      resetApp();
    }
    if (typeof window !== "undefined") {
      console.log("[HERMES:UI] NAV Home", hasActiveRun ? "preserve activeRun" : "→ resetAll stage=home");
    }
  };

  const links = [
    { href: "/", label: t("nav.home"), icon: House, onClick: handleHomeClick, match: (p: string) => p === "/" || p.startsWith("/s") || p === "/fast" || p === "/result" },
    { href: "/works", label: t("nav.works"), icon: FilmSlate, match: (p: string) => p === "/works" || p.startsWith("/works/") },
    { href: "/library", label: t("nav.library"), icon: FolderOpen, match: (p: string) => p === "/library" || p.startsWith("/library/") },
    { href: "/toolbox", label: t("nav.toolbox"), icon: Toolbox, match: (p: string) => p === "/toolbox" || p.startsWith("/toolbox/") },
    ...(adminVisible ? [{ href: "/admin/dashboard", label: t("nav.admin"), icon: ShieldCheck, match: (p: string) => p.startsWith("/admin") }] : []),
    { href: "/settings", label: t("nav.settings"), icon: Gear, match: (p: string) => p === "/settings" },
  ];

  return (
    <nav className="flex items-center gap-1 sm:gap-2 min-w-0">
      {links.map((link) => {
        const isActive = link.match(pathname);
        const Icon = link.icon;
        return (
          <Link
            key={link.href}
            href={link.href}
            onClick={link.onClick}
            aria-label={link.label}
            title={link.label}
            className={`flex items-center gap-2 px-2.5 sm:px-4 py-2 rounded-lg text-sm font-medium transition-all shrink-0 ${
              isActive
                ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-h1)] hover:bg-[rgba(53,20,26,0.06)]"
            }`}
          >
            <Icon size={18} weight="fill" />
            <span className="hidden lg:inline">{link.label}</span>
          </Link>
        );
      })}
      <button
        onClick={() => setLocale(locale === "en" ? "zh" : "en")}
        aria-label={locale === "zh" ? "Switch to English" : "切换到中文"}
        className="ml-1 sm:ml-3 px-2.5 sm:px-3 py-1.5 rounded-full text-xs font-semibold transition-all bg-[var(--bg-panel)] text-[var(--text-muted)] hover:bg-[var(--bg-layer3)] hover:text-[var(--text-h1)] cursor-pointer border border-[var(--border-default)] min-w-[48px] sm:min-w-[56px] text-center shrink-0"
      >
        <span className={locale === "zh" ? "text-[var(--fortune-red)]" : ""}>中</span>
        <span className="mx-1 opacity-40">/</span>
        <span className={locale === "en" ? "text-[var(--fortune-red)]" : ""}>EN</span>
      </button>
    </nav>
  );
}
