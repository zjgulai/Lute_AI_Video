"use client";

import React from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { getMediaUrl } from "./api";
import { Play, Article, Image, ChartBar, DownloadSimple, CaretDown, CaretUp, PaperPlaneRight, Sparkle } from "@phosphor-icons/react";
import PublishFlow from "./PublishFlow";
import InsightReport from "./InsightReport";

interface Props {
  result: any;
  scenario?: string;
}

export default function DirectorPlayback({ result, scenario }: Props) {
  const { t } = useI18n();
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  const videoPath = result.final_video_path || result.clip_paths?.[0] || "";
  const scripts = result.scripts || [];
  const storyboards = result.storyboards || [];
  const audit = result.audit_report;
  const briefs = result.briefs || [];

  const toggleSection = (section: string) => {
    setExpandedSection(expandedSection === section ? null : section);
  };

  return (
    <div className="space-y-8">
      {/* Section 1: Video Player */}
      <PlaybackSection
        icon={<Play size={16} weight="fill" />}
        title={t("playback.title")}
        defaultOpen={true}
      >
        {videoPath ? (
          <video
            src={getMediaUrl(videoPath)}
            controls
            className="w-full rounded-xl"
            style={{ aspectRatio: "9/16", maxHeight: 480 }}
          />
        ) : (
          <div className="apple-card p-8 text-center text-[var(--color-text-tertiary)]">
            <Play size={32} weight="fill" className="mx-auto mb-2 opacity-40" />
            <p className="text-sm">{t("result.empty")}</p>
          </div>
        )}
      </PlaybackSection>

      {/* Section 2: Script Summary */}
      {scripts.length > 0 && (
        <PlaybackSection
          icon={<Article size={16} weight="fill" />}
          title={t("playback.script")}
        >
          <div className="space-y-3">
            {scripts.map((script: any, si: number) => (
              <div key={si} className="apple-card p-4">
                <h4 className="text-xs font-medium text-[var(--color-text-secondary)] mb-2">
                  {script.product_name || script.id}
                </h4>
                <div className="space-y-2">
                  {(script.segments || []).map((seg: any, i: number) => (
                    <div key={i} className="text-sm border-l-2 border-[var(--color-border-light)] pl-3">
                      <span className="text-[10px] uppercase tracking-wider text-[var(--color-accent)] font-medium">
                        {t(`segment.${seg.segment_type}`) || seg.segment_type}
                      </span>
                      <p className="text-[var(--color-text-primary)] mt-0.5">{seg.voiceover}</p>
                      {seg.text_overlay && (
                        <p className="text-xs text-[var(--color-text-tertiary)] mt-1 italic">
                          "{seg.text_overlay}"
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </PlaybackSection>
      )}

      {/* Section 3: Keyframe Gallery */}
      {storyboards.length > 0 && (
        <PlaybackSection
          icon={<Image size={16} weight="fill" />}
          title={t("playback.keyframes")}
        >
          <div className="grid grid-cols-2 gap-3">
            {storyboards.map((sb: any, i: number) => (
              <div key={i} className="apple-card p-3">
                <div className="text-[11px] font-medium text-[var(--color-text-secondary)] mb-1">
                  {sb.scene_title}
                </div>
                <p className="text-xs text-[var(--color-text-tertiary)] line-clamp-3">
                  {sb.visual_description}
                </p>
                <div className="flex gap-2 mt-2 text-[10px] text-[var(--color-text-tertiary)]">
                  <span>{sb.shot_type}</span>
                  <span>·</span>
                  <span>{sb.total_duration}s</span>
                </div>
              </div>
            ))}
          </div>
        </PlaybackSection>
      )}

      {/* Section 4: Quality Report */}
      {audit && (
        <PlaybackSection
          icon={<ChartBar size={16} weight="fill" />}
          title={t("playback.quality")}
        >
          <div className="apple-card p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className={`text-lg font-bold ${audit.overall_status === "PASS" ? "text-[#6B8578]" : "text-[var(--color-warning)]"}`}>
                {Math.round((audit.overall_score || 0) * 100)}%
              </div>
              <div>
                <div className="text-sm font-medium text-[var(--color-text-primary)]">
                  {audit.overall_status === "PASS" ? t("quality.PASS") : t("quality.WARN")}
                </div>
                <p className="text-xs text-[var(--color-text-tertiary)]">{audit.summary}</p>
              </div>
            </div>
            {(audit.criteria || []).map((c: any, i: number) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-t border-[var(--color-border-light)]">
                <span className="text-xs text-[var(--color-text-secondary)]">{c.name}</span>
                <span className={`text-xs font-medium ${c.status === "PASS" ? "text-[#6B8578]" : c.status === "WARN" ? "text-[var(--color-warning)]" : "text-[var(--color-error)]"}`}>
                  {c.status}
                </span>
              </div>
            ))}
          </div>
        </PlaybackSection>
      )}

      {/* Section 5: Publish */}
      <PlaybackSection
        icon={<PaperPlaneRight size={16} weight="fill" />}
        title={t("publish.title")}
      >
        <PublishFlow result={result} />
      </PlaybackSection>

      {/* Section 6: Insight Report */}
      <PlaybackSection
        icon={<Sparkle size={16} weight="fill" />}
        title={t("insight.title")}
      >
        <InsightReport result={result} scenario={scenario || "product_direct"} />
      </PlaybackSection>

      {/* Section 7: Download */}
      <div className="flex justify-center pt-4">
        <button
          className="apple-btn apple-btn-primary gap-2"
          onClick={() => {
            if (videoPath) {
              const a = document.createElement("a");
              a.href = getMediaUrl(videoPath);
              a.download = "video.mp4";
              a.click();
            }
          }}
        >
          <DownloadSimple size={16} weight="fill" />
          {t("playback.download")}
        </button>
      </div>
    </div>
  );
}

// ── Playback Section ──

function PlaybackSection({
  icon,
  title,
  children,
  defaultOpen = false,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [isOpen, setIsOpen] = React.useState(defaultOpen);

  return (
    <div className="border-b border-[var(--color-border-light)] pb-6">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 w-full text-left mb-3"
      >
        <span className="text-[var(--color-accent)]">{icon}</span>
        <span className="text-sm font-semibold text-[var(--color-text-primary)]">{title}</span>
        <span className="ml-auto text-[var(--color-text-tertiary)]">
          {isOpen ? <CaretUp size={14} weight="fill" /> : <CaretDown size={14} weight="fill" />}
        </span>
      </button>
      {isOpen && <div className="animate-fade-in">{children}</div>}
    </div>
  );
}

function useState<T>(initial: T): [T, (v: T | ((prev: T) => T)) => void] {
  return React.useState(initial);
}
