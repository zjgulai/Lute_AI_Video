"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FolderOpen, Palette, Users, Camera } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import TopHeader from "@/components/TopHeader";
import MaterialsTab from "./MaterialsTab";
import BrandKitTab from "./BrandKitTab";
import InfluencersTab from "./InfluencersTab";

type TabId = "materials" | "brand_kit" | "influencers";
const DEFAULT_TAB: TabId = "materials";

function isTabId(v: string | null): v is TabId {
  return v === "materials" || v === "brand_kit" || v === "influencers";
}

function LibraryContent() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const paramTab = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState<TabId>(
    isTabId(paramTab) ? paramTab : DEFAULT_TAB,
  );

  useEffect(() => {
    if (isTabId(paramTab) && paramTab !== activeTab) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveTab(paramTab);
    }
  }, [paramTab, activeTab]);

  const handleTabChange = (id: TabId) => {
    setActiveTab(id);
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", id);
    router.replace(`/library?${params.toString()}`, { scroll: false });
  };

  const tabs: { id: TabId; label: string; icon: typeof Camera; subtitle: string }[] = [
    {
      id: "materials",
      label: t("library.tab.materials"),
      icon: Camera,
      subtitle: t("library.materials.subtitle"),
    },
    {
      id: "brand_kit",
      label: t("library.tab.brand_kit"),
      icon: Palette,
      subtitle: t("library.brand_kit.subtitle"),
    },
    {
      id: "influencers",
      label: t("library.tab.influencers"),
      icon: Users,
      subtitle: t("library.influencers.subtitle"),
    },
  ];

  const activeTabDef = tabs.find((x) => x.id === activeTab) ?? tabs[0];

  return (
    <div className="min-h-screen bg-[var(--color-bg)] overflow-x-hidden">
      <TopHeader />
      <div className="max-w-6xl mx-auto px-4 py-6 space-y-5">
        <header className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[rgba(215,92,112,0.10)] flex items-center justify-center">
            <FolderOpen size={20} weight="fill" className="text-[var(--fortune-red)]" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-h1)]">{t("library.title")}</h1>
            <p className="text-[12px] text-[var(--text-body)] mt-0.5">{activeTabDef.subtitle}</p>
          </div>
        </header>

        <nav
          role="tablist"
          aria-label={t("library.title")}
          className="flex gap-1 border-b border-[rgba(215,92,112,0.18)]"
        >
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                aria-controls={`library-panel-${tab.id}`}
                id={`library-tab-${tab.id}`}
                onClick={() => handleTabChange(tab.id)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-all border-b-2 cursor-pointer -mb-px ${
                  isActive
                    ? "border-[var(--fortune-red)] text-[var(--fortune-red)]"
                    : "border-transparent text-[var(--text-body)] hover:text-[var(--text-h1)]"
                }`}
              >
                <Icon size={16} weight="fill" />
                {tab.label}
              </button>
            );
          })}
        </nav>

        <section
          role="tabpanel"
          id={`library-panel-${activeTab}`}
          aria-labelledby={`library-tab-${activeTab}`}
          className="animate-fade-in"
        >
          {activeTab === "materials" && <MaterialsTab />}
          {activeTab === "brand_kit" && <BrandKitTab />}
          {activeTab === "influencers" && <InfluencersTab />}
        </section>
      </div>
    </div>
  );
}

export default function LibraryPage() {
  return (
    <Suspense fallback={null}>
      <LibraryContent />
    </Suspense>
  );
}
