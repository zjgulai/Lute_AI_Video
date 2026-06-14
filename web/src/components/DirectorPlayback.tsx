"use client";

import React from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { getMediaUrl } from "./api";
import InlineTooltip from "./InlineTooltip";
import {
  extractContinuityDiagnosticsFromAuditReport,
  getContinuityDiagnosticsSummary,
  hasContinuityDiagnostics,
  normalizeContinuityDiagnostics,
} from "@/lib/continuityDiagnostics";
import { truncateDiagnosticText } from "@/lib/diagnosticText";
import { Play, Article, Image as ImageIcon, ChartBar, DownloadSimple, CaretDown, CaretUp, PaperPlaneRight, Sparkle } from "@phosphor-icons/react";
import PublishFlow from "./PublishFlow";
import InsightReport from "./InsightReport";

interface Props {
  result: Record<string, unknown>;
  scenario?: string;
}

export default function DirectorPlayback({ result, scenario }: Props) {
  const { t } = useI18n();

  const videoPath = (result.final_video_path as string) || (result.clip_paths as string[] | undefined)?.[0] || "";
  const scripts = (result.scripts as Record<string, unknown>[]) || [];
  const storyboards = (result.storyboards as Record<string, unknown>[]) || [];
  const audit = result.audit_report as Record<string, unknown> | undefined;
  const continuityDiagnostics = normalizeContinuityDiagnostics(
    extractContinuityDiagnosticsFromAuditReport(audit),
  );
  const continuitySummary = getContinuityDiagnosticsSummary(continuityDiagnostics, t);
  const showContinuityDiagnostics = hasContinuityDiagnostics(continuityDiagnostics);

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
            style={{ aspectRatio: "9/16", maxHeight: 480, colorScheme: 'dark' }}
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
            {scripts.map((script: Record<string, unknown>, si: number) => (
              <div key={si} className="apple-card p-4">
                <h4 className="text-xs font-medium text-[var(--color-text-secondary)] mb-2">
                  {(script.product_name as string) || (script.id as string)}
                </h4>
                <div className="space-y-2">
                  {((script.segments as Record<string, unknown>[]) || []).map((seg: Record<string, unknown>, i: number) => (
                    <div key={i} className="text-sm border-l-2 border-[var(--color-border-light)] pl-3">
                      <span className="text-[12px] uppercase tracking-wider text-[var(--color-accent)] font-medium">
                        {t(`segment.${seg.segment_type as string}`) || (seg.segment_type as string)}
                      </span>
                      <p className="text-[var(--color-text-primary)] mt-0.5">{seg.voiceover as string}</p>
                      {Boolean(seg.text_overlay) && (
                        <p className="text-xs text-[var(--color-text-tertiary)] mt-1 italic">
                          &quot;{seg.text_overlay as string}&quot;
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
          icon={<ImageIcon size={16} weight="fill" />}
          title={t("playback.keyframes")}
        >
          <div className="grid grid-cols-2 gap-3">
            {storyboards.map((sb: Record<string, unknown>, i: number) => (
              <div key={i} className="apple-card p-3">
                <div className="text-[12px] font-medium text-[var(--color-text-secondary)] mb-1">
                  {sb.scene_title as string}
                </div>
                <p className="text-xs text-[var(--color-text-tertiary)] line-clamp-3">
                  {sb.visual_description as string}
                </p>
                <div className="flex gap-2 mt-2 text-[12px] text-[var(--color-text-tertiary)]">
                  <span>{sb.shot_type as string}</span>
                  <span>·</span>
                  <span>{sb.total_duration as number}s</span>
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
              <div className={`text-lg font-bold ${audit.overall_status === "PASS" ? "text-[var(--jade-accent)]" : "text-[var(--color-warning)]"}`}>
                {Math.round(((audit.overall_score as number) || 0) * 100)}%
              </div>
              <div>
                <div className="text-sm font-medium text-[var(--color-text-primary)]">
                  {audit.overall_status === "PASS" ? t("quality.PASS") : t("quality.WARN")}
                </div>
                <p className="text-xs text-[var(--color-text-tertiary)]">{audit.summary as string}</p>
              </div>
            </div>
            {((audit.criteria as Record<string, unknown>[]) || []).map((c: Record<string, unknown>, i: number) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-t border-[var(--color-border-light)]">
                <span className="text-xs text-[var(--color-text-secondary)]">{c.name as string}</span>
                <span className={`text-xs font-medium ${c.status === "PASS" ? "text-[var(--jade-accent)]" : c.status === "WARN" ? "text-[var(--color-warning)]" : "text-[var(--color-error)]"}`}>
                  {c.status as string}
                </span>
              </div>
            ))}
            {showContinuityDiagnostics && (
              <div className="mt-3 rounded-lg border border-[rgba(122,150,187,0.28)] bg-[rgba(122,150,187,0.10)] p-3">
                <p className="text-[11px] font-medium text-[var(--cinema-azure)]">
                  {t("continuity.diagnosticsTitle")}
                </p>
                {continuitySummary && (
                  <p className="mt-1 text-[11px] text-[var(--color-text-secondary)]">
                    {continuitySummary}
                  </p>
                )}
                {continuityDiagnostics.clipDirections.slice(0, 1).map((direction, index) => (
                  <div key={`${direction.sceneBeat}-${index}`} className="mt-2 text-[11px] text-[var(--color-text-secondary)]">
                    <div>{t("continuity.sceneBeatLabel")} {direction.sceneBeat || t("continuity.unknown")}</div>
                    {direction.transitionIntent && (
                      <div>
                        {t("continuity.transitionIntentLabel")}{" "}
                        <InlineTooltip
                          label={truncateDiagnosticText(direction.transitionIntent)}
                          tooltip={direction.transitionIntent}
                          className="max-w-[280px] align-top"
                          tooltipClassName="w-72"
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
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
