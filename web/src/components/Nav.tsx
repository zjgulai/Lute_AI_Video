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
                ? "bg-[#6A2B3A]/10 text-[#6A2B3A]"
                : "text-[#59585E] hover:text-[#35353B] hover:bg-[#EDD3D1]/50"
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
        className="ml-3 px-2 py-1 rounded-full text-[11px] font-semibold transition-all bg-[#FCE4E2] text-[#59585E] hover:bg-[#EDD3D1] hover:text-[#35353B] cursor-pointer border border-[#EDD3D1] min-w-[36px] text-center"
      >
        {t("locale.toggle")}
      </button>
    </nav>
  );
}
