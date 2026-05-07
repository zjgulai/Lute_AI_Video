"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  SquaresFour,
  Users,
  Scroll,
  Heartbeat,
} from "@phosphor-icons/react";

const NAV_ITEMS = [
  { href: "/admin/dashboard", label: "Dashboard", icon: SquaresFour },
  { href: "/admin/tenants", label: "Tenants", icon: Users },
  { href: "/admin/logs", label: "Logs", icon: Scroll },
  { href: "/admin/health", label: "Health", icon: Heartbeat },
];

export default function AdminSidebar() {
  const pathname = usePathname();

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
      <nav className="flex-1 p-3 space-y-1">
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
            >
              <Icon size={18} weight={isActive ? "fill" : "regular"} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-[var(--divider-light)]">
        <p className="text-[11px] text-[var(--text-muted)]">
          Admin Panel v0.1.0
        </p>
      </div>
    </aside>
  );
}
