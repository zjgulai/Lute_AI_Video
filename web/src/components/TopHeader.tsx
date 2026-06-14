"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import Nav from "./Nav";
import PipelineStatusBar from "./PipelineStatusBar";
import { useI18n } from "@/i18n/I18nProvider";

interface TopHeaderProps {
  actions?: ReactNode;
}

export default function TopHeader({ actions }: TopHeaderProps) {
  const { t } = useI18n();
  return (
    <header className="sticky top-0 z-40 bg-[var(--bg-page)]/85 backdrop-blur-xl border-b border-[var(--divider-subtle)]">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <Link href="/" className="flex items-center gap-2 sm:gap-3 group shrink-0" aria-label={t("app.title")}>
            <div className="w-7 h-7 rounded-lg bg-[var(--fortune-red)] flex items-center justify-center group-hover:scale-105 transition-transform">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path d="M8 5v14l11-7z" fill="white" />
              </svg>
            </div>
            <span className="hidden lg:inline text-sm font-semibold text-[var(--text-h1)] tracking-tight">
              {t("app.title")}
            </span>
          </Link>
          <Nav />
        </div>
        {actions ? (
          <div className="flex items-center gap-1 sm:gap-2 shrink-0">
            {actions}
          </div>
        ) : null}
      </div>
      <PipelineStatusBar />
    </header>
  );
}
