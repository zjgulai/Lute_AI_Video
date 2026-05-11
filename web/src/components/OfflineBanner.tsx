"use client";

import { WifiSlash } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import { useNetworkHealth } from "@/hooks/useNetworkHealth";

export default function OfflineBanner() {
  const { t } = useI18n();
  const { online, ping } = useNetworkHealth();

  if (online) return null;

  return (
    <div
      role="status"
      aria-live="assertive"
      className="fixed top-0 inset-x-0 z-[110] bg-[var(--neon-red)] text-white text-sm py-2 px-4 flex items-center justify-center gap-3 shadow-md"
    >
      <WifiSlash size={16} weight="fill" aria-hidden="true" />
      <span>{t("app.offline", "网络已断开，请检查连接")}</span>
      <button
        type="button"
        onClick={() => { void ping(); }}
        className="px-2 py-0.5 rounded border border-white/40 hover:bg-white/10 text-xs font-medium transition-colors"
      >
        {t("app.retry", "重试")}
      </button>
    </div>
  );
}
