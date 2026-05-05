"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { House, Package, SquaresFour } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import { useAppStore } from "@/stores/useAppStore";
import { usePipelineStore } from "@/stores/usePipelineStore";
import { useExpertStore } from "@/stores/useExpertStore";

export default function Nav() {
  const pathname = usePathname();
  const { locale, setLocale, t } = useI18n();
  const resetApp = useAppStore((s) => s.resetApp);
  const resetPipeline = usePipelineStore((s) => s.resetAll);
  const resetExpert = useExpertStore((s) => s.resetExpert);

  const handleHomeClick = () => {
    // N-01 fix: reset all pipeline state when returning home
    localStorage.removeItem("ai_video_thread_id");
    localStorage.removeItem("ai_video_expert_session");
    resetPipeline();
    resetExpert();
    resetApp();
    if (typeof window !== "undefined") {
      // eslint-disable-next-line no-console
      console.log("[HERMES:UI] NAV Home → resetAll stage=home");
    }
  };

  const links = [
    { href: "/", label: t("nav.home"), icon: House, onClick: handleHomeClick },
    { href: "/footage", label: t("nav.gallery"), icon: SquaresFour },
    { href: "/brand-packages", label: t("nav.brandAssets"), icon: Package },
  ];

  return (
    <nav className="flex items-center gap-2">
      {links.map((link) => {
        const isActive = pathname === link.href;
        const Icon = link.icon;
        return (
          <Link
            key={link.href}
            href={link.href}
            onClick={link.onClick}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              isActive
                ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-h1)] hover:bg-[rgba(53,20,26,0.06)]"
            }`}
          >
            <Icon size={18} weight="fill" />
            {link.label}
          </Link>
        );
      })}
      {/* Language toggle */}
      <button
        onClick={() => setLocale(locale === "en" ? "zh" : "en")}
        className="ml-3 px-3 py-1.5 rounded-full text-xs font-semibold transition-all bg-[var(--bg-panel)] text-[var(--text-muted)] hover:bg-[var(--bg-layer3)] hover:text-[var(--text-h1)] cursor-pointer border border-[var(--border-default)] min-w-[44px] text-center"
      >
        {t("locale.toggle")}
      </button>
    </nav>
  );
}
