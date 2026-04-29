"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Package } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

export default function Nav() {
  const pathname = usePathname();
  const { locale, setLocale, t } = useI18n();

  const links = [
    { href: "/", label: t("nav.home"), icon: Home },
    { href: "/brand-packages", label: t("nav.brandAssets"), icon: Package },
  ];

  return (
    <nav className="flex items-center gap-1">
      {links.map((link) => {
        const isActive = pathname === link.href;
        const Icon = link.icon;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              isActive
                ? "bg-[#7CB342]/10 text-[#7CB342]"
                : "text-[#86868b] hover:text-[#1d1d1f] hover:bg-[#e8e8ed]/50"
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {link.label}
          </Link>
        );
      })}
      {/* Language toggle */}
      <button
        onClick={() => setLocale(locale === "en" ? "zh" : "en")}
        className="ml-3 px-2 py-1 rounded-full text-[10px] font-semibold transition-all bg-[#f5f5f7] text-[#86868b] hover:bg-[#e8e8ed] hover:text-[#1d1d1f] cursor-pointer border border-[#e8e8ed] min-w-[36px] text-center"
      >
        {t("locale.toggle")}
      </button>
    </nav>
  );
}
