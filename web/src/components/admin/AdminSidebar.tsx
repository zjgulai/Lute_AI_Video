"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/i18n/I18nProvider";
import {
  SquaresFour,
  Users,
  Scroll,
  Heartbeat,
} from "@phosphor-icons/react";

const NAV_ITEMS = [
  { href: "/admin/dashboard", labelKey: "admin.nav.dashboard", icon: SquaresFour },
  { href: "/admin/tenants", labelKey: "admin.nav.tenants", icon: Users },
  { href: "/admin/logs", labelKey: "admin.nav.logs", icon: Scroll },
  { href: "/admin/health", labelKey: "admin.nav.health", icon: Heartbeat },
];

export default function AdminSidebar() {
  const pathname = usePathname();
  const { t } = useI18n();

  return (
    <aside className="w-[220px] shrink-0 bg-[var(--bg-panel)] border-r border-[var(--divider-light)] flex flex-col min-h-screen">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-[var(--divider-light)]">
        <Link href="/admin/dashboard" className="flex items-center gap-2 no-underline">
          <div className="w-7 h-7 rounded-lg bg-[var(--fortune-red)] flex items-center justify-center">
            <SquaresFour size={14} weight="fill" className="text-white" />
          </div>
          <span className="text-sm font-semibold text-[var(--text-h1)]">
            AI Video Admin
          </span>
        </Link>
      </div>

      {/* Nav items */}
      <nav className="flex-1 p-3 space-y-1" aria-label={t("admin.nav.navigation")}>
        {NAV_ITEMS.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/admin/dashboard" &&
              pathname.startsWith(item.href));
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm no-underline transition-colors ${
                isActive
                  ? "bg-[rgba(215,92,112,0.1)] text-[var(--fortune-red)] font-medium"
                  : "text-[var(--text-body)] hover:bg-[var(--bg-layer3)] hover:text-[var(--text-h1)]"
              }`}
              aria-current={isActive ? "page" : undefined}
            >
              <Icon size={18} weight={isActive ? "fill" : "regular"} />
              {t(item.labelKey)}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-[var(--divider-light)]">
        <p className="text-[11px] text-[var(--text-muted)]">
          {t("admin.nav.version")}
        </p>
      </div>
    </aside>
  );
}
