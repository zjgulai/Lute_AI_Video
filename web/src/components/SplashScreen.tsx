"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import CreationGuide from "./CreationGuide";

interface Props {
  onEnter: () => void;
}

export default function SplashScreen({ onEnter }: Props) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(true);
  const [animating, setAnimating] = useState(true);
  const [showGuide, setShowGuide] = useState(false);
  const [showBlueprint, setShowBlueprint] = useState(false);

  const handleEnter = () => {
    setAnimating(false);
    setTimeout(() => { setVisible(false); onEnter(); }, 600);
  };
  if (!visible) return null;

  const btnBase =
    "px-5 py-2.5 rounded-[24px] text-[14px] font-medium cursor-pointer " +
    "transition-all duration-300 ease-out bg-[var(--bg-hover)] text-[var(--text-h2)] border border-[var(--border-default)] " +
    "hover:bg-[var(--bg-panel)] hover:border-[var(--border-hover-strong)] active:scale-[0.98]";

  return (
    <div
      className={`fixed inset-0 z-[100] flex flex-col items-center justify-center transition-opacity duration-700 ease-in-out ${
        animating ? "opacity-100" : "opacity-0 pointer-events-none"
      }`}
      style={{ background: "radial-gradient(ellipse at 30% 20%, rgba(215,92,112,0.10) 0%, #FDF8F6 55%, #FCF5F2 100%)" }}
    >

      {/* Main */}
      <div className="relative z-10 flex flex-col items-center gap-5 md:gap-7 px-6 text-center">
        <div className="animate-splash-in px-4 py-1.5 rounded-full bg-[rgba(215,92,112,0.12)] border border-[rgba(215,92,112,0.18)]" style={{ animationDelay: "0ms" }}>
          <span className="text-[12px] font-semibold tracking-wider text-[var(--fortune-red)]">{t("app.title")}</span>
        </div>
        <div className="animate-splash-in" style={{ animationDelay: "80ms" }}>
          <h1 className="text-[52px] md:text-[64px] font-medium tracking-[0.02em] text-[var(--text-h1)] leading-none" style={{ fontFamily: "'Montserrat', -apple-system, sans-serif" }}>Momcozy</h1>
        </div>
        <div className="animate-splash-in flex flex-col items-center gap-2" style={{ animationDelay: "160ms" }}>
          <div className="w-10 h-0.5 rounded-full bg-[var(--fortune-red)] opacity-60" />
          <p className="text-[18px] leading-relaxed text-[var(--text-body)] pt-1" style={{ fontFamily: "'Noto Sans SC', 'PingFang SC', -apple-system, sans-serif" }}>{t("splash.sloganZh")}</p>
          <p className="text-[14px] text-[var(--text-muted)]" style={{ fontFamily: "'Inter', -apple-system, sans-serif" }}>Evolving for Mom and Cozy</p>
        </div>
        <p className="animate-splash-in text-[12px] text-[var(--text-placeholder)]" style={{ animationDelay: "200ms" }}>{t("splash.departmentCredit")}</p>
      </div>

      {/* CTA */}
      <div className="animate-splash-in absolute bottom-[12%] flex flex-wrap items-center justify-center gap-3 px-4" style={{ animationDelay: "280ms" }}>
        <button className={btnBase} onClick={() => setShowGuide(true)}>{t("splash.creationGuide")}</button>
        <button onClick={handleEnter} className="px-8 py-3 rounded-[24px] text-[16px] font-medium cursor-pointer transition-all duration-300 ease-out bg-[var(--fortune-red)] text-white border border-[var(--fortune-red)] hover:bg-[var(--fortune-red-600)] hover:border-[var(--fortune-red-600)] hover:scale-[1.02] active:scale-[0.98] shadow-lg">{t("splash.enter")}</button>
        <button className={btnBase} onClick={() => setShowBlueprint(true)}>{t("splash.blueprint")}</button>
      </div>

      {showGuide && (
        <CreationGuide onClose={() => setShowGuide(false)} onEnter={handleEnter} />
      )}

      {showBlueprint && (
        <div className="absolute inset-0 z-50 flex flex-col bg-[var(--cinema-black)]">
          <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border-default)] bg-[var(--cinema-black)]/90 backdrop-blur-md">
            <span className="text-[14px] font-semibold text-[var(--text-h1)]">{t("splash.blueprint")}</span>
            <button onClick={() => setShowBlueprint(false)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[13px] font-medium text-[var(--text-muted)] hover:bg-[rgba(215,92,112,0.10)] hover:text-[var(--fortune-red)] transition-colors cursor-pointer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
              {t("guide.back")}
            </button>
          </div>
          <iframe src="https://vozjd5k2equj6.ok.kimi.link" className="flex-1 w-full border-0" title={t("splash.blueprint")} />
        </div>
      )}

      {/* Animations */}
      <style>{`
        .animate-splash-in { opacity: 0; animation: splashSlideUp 500ms ease-out forwards; }
        @keyframes splashSlideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        .animate-lens-breathe { animation: lensBreathe 3s ease-in-out infinite; }
        @keyframes lensBreathe { 0%,100% { opacity: 0.5; transform: scale(1); } 50% { opacity: 1; transform: scale(1.06); } }
        .animate-timeline-pulse { animation: timelinePulse 2s ease-in-out infinite; }
        @keyframes timelinePulse { 0%,100% { opacity: 0.45; } 50% { opacity: 0.85; } }
      `}</style>
    </div>
  );
}
