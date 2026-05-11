"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  onClose: () => void;
  onEnter?: () => void;
}

type TabId = "overview" | "scenes" | "frontend" | "backend" | "ops";

const SCENE_CARDS = [
  { emoji: "📦", nameKey: "guide.scene.s1.name", descKey: "guide.scene.s1.desc" },
  { emoji: "🎬", nameKey: "guide.scene.s2.name", descKey: "guide.scene.s2.desc" },
  { emoji: "📱", nameKey: "guide.scene.s3.name", descKey: "guide.scene.s3.desc" },
  { emoji: "🎥", nameKey: "guide.scene.s4.name", descKey: "guide.scene.s4.desc" },
  { emoji: "📹", nameKey: "guide.scene.s5.name", descKey: "guide.scene.s5.desc" },
  { emoji: "⚡", nameKey: "guide.scene.fast.name", descKey: "guide.scene.fast.desc" },
];

const DESIGN_PHILOSOPHY = [
  { icon: "🎯", titleKey: "guide.philosophy.coach.title", descKey: "guide.philosophy.coach.desc" },
  { icon: "🔄", titleKey: "guide.philosophy.onceOnly.title", descKey: "guide.philosophy.onceOnly.desc" },
  { icon: "📐", titleKey: "guide.philosophy.method.title", descKey: "guide.philosophy.method.desc" },
  { icon: "📊", titleKey: "guide.philosophy.metrics.title", descKey: "guide.philosophy.metrics.desc" },
];

const NOTICES = [
  { titleKey: "guide.notice.api.title", descKey: "guide.notice.api.desc" },
  { titleKey: "guide.notice.abort.title", descKey: "guide.notice.abort.desc" },
  { titleKey: "guide.notice.quality.title", descKey: "guide.notice.quality.desc" },
  { titleKey: "guide.notice.duration.title", descKey: "guide.notice.duration.desc" },
  { titleKey: "guide.notice.copyright.title", descKey: "guide.notice.copyright.desc" },
];

const FRONTEND_PATHS = [
  { path: "/", titleKey: "guide.path.home.title", descKey: "guide.path.home.desc" },
  { path: "/s1 - /s5, /fast", titleKey: "guide.path.scenes.title", descKey: "guide.path.scenes.desc" },
  { path: "/works", titleKey: "guide.path.works.title", descKey: "guide.path.works.desc" },
  { path: "/library", titleKey: "guide.path.library.title", descKey: "guide.path.library.desc" },
  { path: "/settings", titleKey: "guide.path.settings.title", descKey: "guide.path.settings.desc" },
  { path: "/admin/login", titleKey: "guide.path.admin.title", descKey: "guide.path.admin.desc" },
];

const FRONTEND_INTERACTIONS = [
  { titleKey: "guide.fe.gate.title", descKey: "guide.fe.gate.desc" },
  { titleKey: "guide.fe.submit.title", descKey: "guide.fe.submit.desc" },
  { titleKey: "guide.fe.422.title", descKey: "guide.fe.422.desc" },
  { titleKey: "guide.fe.i18n.title", descKey: "guide.fe.i18n.desc" },
  { titleKey: "guide.fe.401.title", descKey: "guide.fe.401.desc" },
  { titleKey: "guide.fe.upload.title", descKey: "guide.fe.upload.desc" },
  { titleKey: "guide.fe.statusBar.title", descKey: "guide.fe.statusBar.desc" },
];

const BACKEND_FEATURES = [
  { titleKey: "guide.be.admin.title", descKey: "guide.be.admin.desc" },
  { titleKey: "guide.be.tenant.title", descKey: "guide.be.tenant.desc" },
  { titleKey: "guide.be.key.title", descKey: "guide.be.key.desc" },
  { titleKey: "guide.be.logs.title", descKey: "guide.be.logs.desc" },
  { titleKey: "guide.be.health.title", descKey: "guide.be.health.desc" },
];

const OPS_RUNBOOKS = [
  { titleKey: "guide.ops.deploy.title", descKey: "guide.ops.deploy.desc" },
  { titleKey: "guide.ops.deepseek.title", descKey: "guide.ops.deepseek.desc" },
  { titleKey: "guide.ops.poyo.title", descKey: "guide.ops.poyo.desc" },
  { titleKey: "guide.ops.stuck.title", descKey: "guide.ops.stuck.desc" },
  { titleKey: "guide.ops.dbpool.title", descKey: "guide.ops.dbpool.desc" },
  { titleKey: "guide.ops.dr.title", descKey: "guide.ops.dr.desc" },
];

export default function CreationGuide({ onClose, onEnter }: Props) {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  const tabs: { id: TabId; labelKey: string; icon: string }[] = [
    { id: "overview", labelKey: "guide.tab.overview", icon: "✨" },
    { id: "scenes", labelKey: "guide.tab.scenes", icon: "🎬" },
    { id: "frontend", labelKey: "guide.tab.frontend", icon: "🖱️" },
    { id: "backend", labelKey: "guide.tab.backend", icon: "🛡️" },
    { id: "ops", labelKey: "guide.tab.ops", icon: "🚨" },
  ];

  const cardClass =
    "p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)] hover:border-[var(--fortune-red)] transition-colors";
  const sectionTitle = "text-[18px] font-semibold text-[var(--text-h1)] mb-4";
  const sectionLead = "text-[12px] text-[var(--text-muted)] leading-relaxed mb-4";

  return (
    <div
      className="absolute inset-0 z-50 overflow-y-auto bg-[var(--cinema-black)]"
      style={{ fontFamily: "'Inter', 'Noto Sans SC', -apple-system, sans-serif" }}
    >
      <div className="sticky top-0 z-20 flex items-center justify-between px-6 md:px-12 py-4 bg-[var(--cinema-black)]/95 backdrop-blur-md border-b border-[var(--border-default)]">
        <h2 className="text-[16px] font-semibold text-[var(--text-h1)]">
          {t("app.title")} · {t("splash.creationGuide")}
        </h2>
        <button
          onClick={onClose}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[13px] font-medium text-[var(--text-muted)] hover:bg-[rgba(215,92,112,0.10)] hover:text-[var(--fortune-red)] transition-colors cursor-pointer"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          {t("guide.back")}
        </button>
      </div>

      <div className="sticky top-[57px] z-10 bg-[var(--cinema-black)]/95 backdrop-blur-md border-b border-[var(--border-default)]">
        <div className="max-w-5xl mx-auto px-6 md:px-12 py-2 flex gap-1 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-lg text-[13px] font-medium whitespace-nowrap transition-all cursor-pointer ${
                activeTab === tab.id
                  ? "bg-[var(--fortune-red)] text-white shadow-sm"
                  : "text-[var(--text-body)] hover:bg-[rgba(215,92,112,0.08)] hover:text-[var(--fortune-red)]"
              }`}
            >
              <span className="mr-1.5">{tab.icon}</span>
              {t(tab.labelKey)}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 md:px-12 py-8 space-y-10 pb-20">
        {activeTab === "overview" && (
          <>
            <div className="text-center space-y-3 py-4">
              <h1 className="text-[28px] md:text-[36px] font-semibold text-[var(--text-h1)] tracking-tight">
                {t("guide.overview.title")}
              </h1>
              <p className="text-[14px] text-[var(--text-body)] max-w-2xl mx-auto leading-relaxed">
                {t("guide.overview.intro")}
              </p>
              <div className="flex flex-wrap justify-center gap-2 pt-2">
                {["DeepSeek V4-Pro", "GPT-4o Image", "Happy Horse · Seedance", "CosyVoice2"].map((m) => (
                  <span
                    key={m}
                    className="px-3 py-1 rounded-full bg-[rgba(215,92,112,0.10)] text-[12px] font-medium text-[var(--fortune-red)] border border-[rgba(215,92,112,0.18)]"
                  >
                    {m}
                  </span>
                ))}
              </div>
            </div>

            <section>
              <h3 className={sectionTitle}>{t("guide.overview.modes")}</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-5 rounded-xl bg-gradient-to-br from-[rgba(215,92,112,0.14)] to-[rgba(215,92,112,0.06)] border border-[rgba(215,92,112,0.20)]">
                  <div className="text-[15px] font-semibold text-[var(--fortune-red)]">
                    {t("guide.mode.smart.title")}
                  </div>
                  <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-2">
                    {t("guide.mode.smart.desc")}
                  </div>
                </div>
                <div className="p-5 rounded-xl bg-gradient-to-br from-[rgba(220,190,120,0.12)] to-[rgba(215,92,112,0.06)] border border-[rgba(220,190,120,0.20)]">
                  <div className="text-[15px] font-semibold text-[var(--gold-foil)]">
                    {t("guide.mode.expert.title")}
                  </div>
                  <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-2">
                    {t("guide.mode.expert.desc")}
                  </div>
                </div>
              </div>
            </section>

            <section>
              <h3 className={sectionTitle}>{t("guide.overview.philosophy")}</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {DESIGN_PHILOSOPHY.map((p) => (
                  <div
                    key={p.titleKey}
                    className="p-4 rounded-xl bg-gradient-to-br from-[var(--film-reel)] to-[rgba(215,92,112,0.04)] border border-[var(--border-default)]"
                  >
                    <div className="text-lg mb-1">{p.icon}</div>
                    <div className="text-[14px] font-semibold text-[var(--text-h1)]">{t(p.titleKey)}</div>
                    <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1">
                      {t(p.descKey)}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h3 className={sectionTitle}>{t("guide.overview.notices")}</h3>
              <div className="space-y-2">
                {NOTICES.map((n) => (
                  <div
                    key={n.titleKey}
                    className="flex gap-3 p-4 rounded-xl bg-[var(--film-reel)] border border-[var(--border-default)]"
                  >
                    <span className="text-[var(--gold-foil)] text-sm shrink-0 mt-0.5">⚠</span>
                    <div>
                      <div className="text-[13px] font-semibold text-[var(--text-h1)]">{t(n.titleKey)}</div>
                      <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-0.5">
                        {t(n.descKey)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}

        {activeTab === "scenes" && (
          <>
            <section>
              <h3 className={sectionTitle}>{t("guide.scenes.title")}</h3>
              <p className={sectionLead}>{t("guide.scenes.lead")}</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {SCENE_CARDS.map((s) => (
                  <div key={s.nameKey} className={cardClass}>
                    <div className="text-lg mb-1">{s.emoji}</div>
                    <div className="text-[14px] font-semibold text-[var(--text-h1)]">{t(s.nameKey)}</div>
                    <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1">
                      {t(s.descKey)}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h3 className={sectionTitle}>{t("guide.examples.title")}</h3>
              <p className={sectionLead}>{t("guide.examples.lead")}</p>
              <div className="space-y-4">
                <SceneExample
                  emoji="📦"
                  nameKey="guide.scene.s1.name"
                  accent="rgba(215,92,112,0.10)"
                  titleColor="var(--fortune-red)"
                  fieldsKey="guide.example.s1.fields"
                  t={t}
                />
                <SceneExample
                  emoji="📹"
                  nameKey="guide.scene.s5.name"
                  accent="rgba(220,190,120,0.10)"
                  titleColor="var(--gold-foil)"
                  fieldsKey="guide.example.s5.fields"
                  t={t}
                />
                <SceneExample
                  emoji="📱"
                  nameKey="guide.scene.s3.name"
                  accent="rgba(215,92,112,0.10)"
                  titleColor="var(--fortune-red)"
                  fieldsKey="guide.example.s3.fields"
                  t={t}
                />
                <SceneExample
                  emoji="⚡"
                  nameKey="guide.scene.fast.name"
                  accent="rgba(220,190,120,0.10)"
                  titleColor="var(--gold-foil)"
                  fieldsKey="guide.example.fast.fields"
                  t={t}
                />
              </div>
            </section>

            <section>
              <h3 className={sectionTitle}>{t("guide.sop.title")}</h3>
              <p className={sectionLead}>{t("guide.sop.lead")}</p>
              <div className="space-y-3">
                <ScenarioSop emoji="📦" nameKey="guide.scene.s1.name" accent="rgba(215,92,112,0.10)" titleColor="var(--fortune-red)" stepsKey="guide.sop.s1" t={t} />
                <ScenarioSop emoji="🎬" nameKey="guide.scene.s2.name" accent="rgba(220,190,120,0.10)" titleColor="var(--gold-foil)" stepsKey="guide.sop.s2" t={t} />
                <ScenarioSop emoji="📱" nameKey="guide.scene.s3.name" accent="rgba(215,92,112,0.10)" titleColor="var(--fortune-red)" stepsKey="guide.sop.s3" t={t} />
                <ScenarioSop emoji="📹" nameKey="guide.scene.s5.name" accent="rgba(220,190,120,0.10)" titleColor="var(--gold-foil)" stepsKey="guide.sop.s5" t={t} />
                <ScenarioSop emoji="🎥" nameKey="guide.scene.s4.name" accent="rgba(215,92,112,0.10)" titleColor="var(--fortune-red)" stepsKey="guide.sop.s4" t={t} />
                <ScenarioSop emoji="⚡" nameKey="guide.scene.fast.name" accent="rgba(220,190,120,0.10)" titleColor="var(--gold-foil)" stepsKey="guide.sop.fast" t={t} />
              </div>
            </section>
          </>
        )}

        {activeTab === "frontend" && (
          <>
            <section>
              <h3 className={sectionTitle}>{t("guide.frontend.paths")}</h3>
              <p className={sectionLead}>{t("guide.frontend.pathsLead")}</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {FRONTEND_PATHS.map((p) => (
                  <div key={p.path} className={cardClass}>
                    <div className="text-[12px] font-mono text-[var(--gold-foil)] mb-1">{p.path}</div>
                    <div className="text-[14px] font-semibold text-[var(--text-h1)]">{t(p.titleKey)}</div>
                    <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1">
                      {t(p.descKey)}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h3 className={sectionTitle}>{t("guide.frontend.interactions")}</h3>
              <p className={sectionLead}>{t("guide.frontend.interactionsLead")}</p>
              <div className="space-y-3">
                {FRONTEND_INTERACTIONS.map((it) => (
                  <div key={it.titleKey} className="p-4 rounded-xl bg-[var(--bg-card)] border-l-2 border-l-[var(--fortune-red)] border border-[var(--border-default)]">
                    <div className="text-[14px] font-semibold text-[var(--text-h1)]">{t(it.titleKey)}</div>
                    <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1 whitespace-pre-line">
                      {t(it.descKey)}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}

        {activeTab === "backend" && (
          <>
            <section>
              <h3 className={sectionTitle}>{t("guide.backend.title")}</h3>
              <p className={sectionLead}>{t("guide.backend.lead")}</p>
              <div className="space-y-3">
                {BACKEND_FEATURES.map((f) => (
                  <div key={f.titleKey} className="p-4 rounded-xl bg-[var(--bg-card)] border-l-2 border-l-[var(--gold-foil)] border border-[var(--border-default)]">
                    <div className="text-[14px] font-semibold text-[var(--text-h1)]">{t(f.titleKey)}</div>
                    <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1 whitespace-pre-line">
                      {t(f.descKey)}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h3 className={sectionTitle}>{t("guide.backend.auth")}</h3>
              <p className={sectionLead}>{t("guide.backend.authLead")}</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)]">
                  <div className="text-[12px] font-mono text-[var(--gold-foil)] mb-1">X-API-Key</div>
                  <div className="text-[14px] font-semibold text-[var(--text-h1)]">{t("guide.backend.auth.api.title")}</div>
                  <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1 whitespace-pre-line">
                    {t("guide.backend.auth.api.desc")}
                  </div>
                </div>
                <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)]">
                  <div className="text-[12px] font-mono text-[var(--gold-foil)] mb-1">admin_session cookie</div>
                  <div className="text-[14px] font-semibold text-[var(--text-h1)]">{t("guide.backend.auth.cookie.title")}</div>
                  <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1 whitespace-pre-line">
                    {t("guide.backend.auth.cookie.desc")}
                  </div>
                </div>
              </div>
            </section>
          </>
        )}

        {activeTab === "ops" && (
          <>
            <section>
              <h3 className={sectionTitle}>{t("guide.ops.title")}</h3>
              <p className={sectionLead}>{t("guide.ops.lead")}</p>
              <div className="space-y-3">
                {OPS_RUNBOOKS.map((r) => (
                  <div key={r.titleKey} className="p-4 rounded-xl bg-[var(--bg-card)] border-l-2 border-l-[var(--crimson-mist)] border border-[var(--border-default)]">
                    <div className="text-[14px] font-semibold text-[var(--text-h1)]">{t(r.titleKey)}</div>
                    <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1 whitespace-pre-line">
                      {t(r.descKey)}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h3 className={sectionTitle}>{t("guide.ops.adr")}</h3>
              <p className={sectionLead}>{t("guide.ops.adrLead")}</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className={cardClass}>
                  <div className="text-[12px] font-mono text-[var(--gold-foil)] mb-1">ADR #001</div>
                  <div className="text-[14px] font-semibold text-[var(--text-h1)]">{t("guide.ops.adr.001.title")}</div>
                  <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1">
                    {t("guide.ops.adr.001.desc")}
                  </div>
                </div>
                <div className={cardClass}>
                  <div className="text-[12px] font-mono text-[var(--gold-foil)] mb-1">ADR #002</div>
                  <div className="text-[14px] font-semibold text-[var(--text-h1)]">{t("guide.ops.adr.002.title")}</div>
                  <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1">
                    {t("guide.ops.adr.002.desc")}
                  </div>
                </div>
                <div className={cardClass}>
                  <div className="text-[12px] font-mono text-[var(--gold-foil)] mb-1">ADR #003</div>
                  <div className="text-[14px] font-semibold text-[var(--text-h1)]">{t("guide.ops.adr.003.title")}</div>
                  <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1">
                    {t("guide.ops.adr.003.desc")}
                  </div>
                </div>
              </div>
            </section>
          </>
        )}

        {onEnter && (
          <div className="text-center pt-4">
            <button
              onClick={() => {
                onClose();
                onEnter();
              }}
              className="px-10 py-3.5 rounded-xl text-[16px] font-semibold text-white bg-[var(--fortune-red)] hover:bg-[var(--neon-red)] active:scale-[0.98] transition-all cursor-pointer shadow-[0_0_24px_rgba(215,92,112,0.35)]"
            >
              {t("splash.enter")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

interface SceneExampleProps {
  emoji: string;
  nameKey: string;
  accent: string;
  titleColor: string;
  fieldsKey: string;
  t: (k: string) => string;
}

function SceneExample({ emoji, nameKey, accent, titleColor, fieldsKey, t }: SceneExampleProps) {
  const body = t(fieldsKey);
  const lines = body
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  return (
    <div className="rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)] overflow-hidden">
      <div
        className="px-5 py-3 text-[13px] font-semibold flex items-center gap-2"
        style={{ background: accent, color: titleColor, borderBottom: "1px solid var(--border-default)" }}
      >
        <span>{emoji}</span>
        <span>{t(nameKey)}</span>
      </div>
      <div className="p-5 space-y-2 text-[12px] text-[var(--text-body)] leading-relaxed">
        {lines.map((line, i) => {
          const splitIdx = line.indexOf(":");
          if (splitIdx > 0) {
            const label = line.slice(0, splitIdx);
            const value = line.slice(splitIdx + 1).trim();
            return (
              <div key={i}>
                <span className="font-semibold text-[var(--text-h1)]">{label}:</span> {value}
              </div>
            );
          }
          return <div key={i}>{line}</div>;
        })}
      </div>
    </div>
  );
}

interface ScenarioSopProps {
  emoji: string;
  nameKey: string;
  accent: string;
  titleColor: string;
  stepsKey: string;
  t: (k: string) => string;
}

function ScenarioSop({ emoji, nameKey, accent, titleColor, stepsKey, t }: ScenarioSopProps) {
  const body = t(stepsKey);
  const steps = body
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  return (
    <div className="rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)] overflow-hidden">
      <div
        className="px-4 py-2.5 flex items-center gap-2"
        style={{ background: accent, borderBottom: "1px solid var(--border-default)" }}
      >
        <span>{emoji}</span>
        <span className="text-[13px] font-semibold" style={{ color: titleColor }}>
          {t(nameKey)}
        </span>
      </div>
      <div className="p-4 space-y-1.5 text-[12px] text-[var(--text-body)] leading-relaxed">
        {steps.map((step, i) => (
          <div key={i}>{step}</div>
        ))}
      </div>
    </div>
  );
}
