"use client";

import { useState } from "react";
import ApiKeyGate from "@/components/ApiKeyGate";
import PerformanceDashboard from "@/components/PerformanceDashboard";
import { hasApiKey } from "@/components/api";
import { useI18n } from "@/i18n/I18nProvider";

export default function DashboardPage() {
  const { t } = useI18n();
  const [unlocked, setUnlocked] = useState(() => hasApiKey());

  if (!unlocked) {
    return <ApiKeyGate onUnlock={() => setUnlocked(true)} />;
  }

  return (
    <main className="min-h-screen bg-[var(--bg-page)] px-4 py-6 text-[var(--text-body)] md:px-8">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
        <header className="flex items-center justify-between border-b border-[var(--divider-subtle)] pb-3">
          <h1 className="text-lg font-semibold text-[var(--text-h1)]">{t("perf.title")}</h1>
        </header>
        <section className="apple-card p-4 md:p-5">
          <PerformanceDashboard />
        </section>
      </div>
    </main>
  );
}
