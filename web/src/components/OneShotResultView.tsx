"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { downloadJson, getMediaUrl, publishContent } from "./api";
import React from "react";
import { ShoppingBag, MusicNotes, ChatCircle, VideoCamera, ShoppingCart, ArrowSquareOut, ListDashes, FilmStrip } from "@phosphor-icons/react";
import type { IconProps } from "@phosphor-icons/react";
import { AuditReport } from "./types";
import EditableBrief from "./EditableBrief";
import EditableScript from "./EditableScript";
import QualityDashboard from "./QualityDashboard";
import PerformanceDashboard from "./PerformanceDashboard";
import PublishPanel from "./PublishPanel";
import DirectorPlayback from "./DirectorPlayback";
import RuntimeMediaImage from "./RuntimeMediaImage";

import { errorMessage } from "@/lib/errors";
const PLATFORM_ICON_MAP: Record<string, React.ComponentType<IconProps>> = {
  shopify: ShoppingBag,
  amazon: ShoppingCart,
  tiktok: MusicNotes,
  reddit: ChatCircle,
  facebook: ArrowSquareOut,
  youtube_shorts: VideoCamera,
};

interface Props {
  scenario: string;
  result: unknown;
  onReset: () => void;
  onEdit?: (tab: string, index: number, data: ResultItem) => void;
}

type TabId = "content" | "media" | "quality" | "data";
type ContentSubId = "briefs" | "scripts" | "videos" | "thumbnails";

type ResultItem = Record<string, unknown> & {
  id?: string;
  platform?: string;
  hook_type?: string;
  product_name?: string;
  brand_name?: string;
  description?: string;
  key_message?: string;
  hook?: string;
  tags?: string[];
  usp_priority?: string[];
};

type ScriptSegment = Record<string, unknown> & {
  segment_type?: string;
  start_time?: number;
  end_time?: number;
  description?: string;
  voiceover?: string;
  visual_description?: string;
};

type ScriptItem = ResultItem & {
  segments?: ScriptSegment[];
};

type VideoPromptItem = Record<string, unknown> & {
  script_id?: string;
  prompt?: string | { seedance_prompt?: string };
};

type ThumbnailVariant = Record<string, unknown> & {
  variant_type?: string;
  prompt?: string;
};

type ThumbnailSet = Record<string, unknown> & {
  script_id?: string;
  variants?: ThumbnailVariant[];
};

type PublishRowResult = Record<string, unknown> & {
  success: boolean;
  error?: string;
  url?: string;
};

type OneShotResult = Record<string, unknown> & {
  success?: boolean;
  steps_completed?: number;
  briefs?: ResultItem[];
  scripts?: ScriptItem[];
  storyboards?: ResultItem[];
  video_prompts?: VideoPromptItem[];
  thumbnail_sets?: ThumbnailSet[];
  thumbnails?: ThumbnailSet[];
  final_video_path?: string;
  thumbnail_image_paths?: string[];
  audio_paths?: string[];
  clip_paths?: string[];
  audit_report?: AuditReport | null;
};

function asOneShotResult(value: unknown): OneShotResult {
  return value && typeof value === "object" && !Array.isArray(value) ? value as OneShotResult : {};
}

const SCENARIO_LABELS: Record<string, string> = {
  product_direct: "scene.product_direct.title",
  live_shoot_to_video: "scene.live_shoot_to_video",
  brand_campaign: "scene.brand_campaign.title",
  influencer_remix: "scene.influencer_remix.title",
};



// Placeholder shown when media URL is empty (demo mode — no backend)
function DemoPlaceholder({ label }: { label: string }) {
  return (
    <div className="w-full rounded-xl bg-[var(--bg-panel)] border border-dashed border-[var(--border-default)] flex flex-col items-center justify-center gap-2 text-center"
      style={{ minHeight: 180 }}>
      <div className="w-10 h-10 rounded-full bg-[rgba(215,92,112,0.18)] flex items-center justify-center">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--text-body)" strokeWidth="2">
          <rect x="2" y="2" width="20" height="20" rx="2" />
          <path d="M2 12h20M12 2v20" />
        </svg>
      </div>
      <div>
        <p className="text-xs font-medium text-[var(--text-body)]">Demo Mode</p>
        <p className="text-[12px] text-[var(--text-muted)]">{label}</p>
      </div>
    </div>
  );
}

export default function OneShotResultView({ scenario, result: rawResult, onReset, onEdit }: Props) {
  const { t } = useI18n();
  const result = asOneShotResult(rawResult);
  // UI 2.0: Director Playback is the default narrative view
  const [viewMode, setViewMode] = useState<"director" | "classic">("director");
  // P0-2: Merged tabs — 8→4 with content sub-navigation
  const [tab, setTab] = useState<TabId>("media");
  const [contentSub, setContentSub] = useState<ContentSubId>("briefs");

  const briefs = result?.briefs || [];
  const scripts = result?.scripts || [];
  const videoPrompts = result?.video_prompts || [];
  const thumbnails = result?.thumbnail_sets || result?.thumbnails || [];
  const success: boolean = result?.success !== false;
  const stepsCompleted: number = result?.steps_completed || 0;
  const finalVideo: string = result?.final_video_path || "";
  const thumbImages: string[] = result?.thumbnail_image_paths || [];
  const audioPaths: string[] = result?.audio_paths || [];
  const clipPaths: string[] = result?.clip_paths || [];
  const audit: AuditReport | null = result?.audit_report || null;
  const mediaCount = (finalVideo ? 1 : 0) + thumbImages.length + audioPaths.length + clipPaths.length;

  const TABS: Array<{ id: TabId; label: string; count: number }> = [
    { id: "content", label: t("result.tab.content"), count: briefs.length + scripts.length + videoPrompts.length + thumbnails.length },
    { id: "media", label: t("result.tab.media"), count: mediaCount },
    { id: "quality", label: t("result.tab.quality"), count: audit ? (audit.criteria?.length || 0) : 0 },
    { id: "data", label: t("result.tab.data"), count: 0 },
  ];

  const CONTENT_SUBTABS: Array<{ id: ContentSubId; label: string; count: number }> = [
    { id: "briefs", label: t("result.tab.briefs"), count: briefs.length },
    { id: "scripts", label: t("result.tab.scripts"), count: scripts.length },
    { id: "videos", label: t("result.tab.videos"), count: videoPrompts.length },
    { id: "thumbnails", label: t("result.tab.thumbnails"), count: thumbnails.length },
  ];

  return (
    <div className="space-y-3 animate-slide-up">
      {/* Result header */}
      <div className="apple-card p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 ${success ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]" : "bg-[rgba(196,91,80,0.10)] text-[var(--crimson-mist)]"}`}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                {success
                  ? <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                  : <><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" /></>
                }
              </svg>
            </div>
            <div>
              <h2 className="text-base font-semibold text-[var(--text-h1)]">{t(SCENARIO_LABELS[scenario] || scenario)} {t("result.complete")}</h2>
              <p className="text-xs text-[var(--text-body)] mt-0.5">
                {success ? `${t("result.generated")} ${stepsCompleted || briefs.length + scripts.length + thumbnails.length} ${t("result.items")}` : t("result.error")}
              </p>
            </div>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => downloadJson(result, `${scenario}-${Date.now()}.json`)}
              className="apple-btn px-3 py-1.5 text-xs"
              title={t("result.download")}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              {t("result.download")}
            </button>
            <button onClick={onReset} className="apple-btn apple-btn-primary px-3 py-1.5 text-xs">
              {t("result.newCreation")}
            </button>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-5 gap-2 mt-4 pt-3 border-t border-[rgba(215,92,112,0.18)]">
          <Stat label={t("result.tab.briefs")} value={briefs.length} />
          <Stat label={t("result.tab.scripts")} value={scripts.length} />
          <Stat label={t("result.tab.videos")} value={videoPrompts.length} />
          <Stat label={t("result.tab.thumbnails")} value={thumbnails.length} />
          <Stat label={t("result.tab.media")} value={mediaCount} />
        </div>
      </div>

      {/* View Mode Toggle */}
      <div className="flex items-center gap-2 px-1">
        <button
          onClick={() => setViewMode("director")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
            viewMode === "director"
              ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]"
              : "text-[var(--text-body)] hover:text-[var(--text-h1)]"
          }`}
        >
          <FilmStrip size={14} weight="fill" />
          {t("playback.directorView") || "Director Playback"}
        </button>
        <button
          onClick={() => setViewMode("classic")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
            viewMode === "classic"
              ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]"
              : "text-[var(--text-body)] hover:text-[var(--text-h1)]"
          }`}
        >
          <ListDashes size={14} weight="fill" />
          {t("playback.classicView") || "Classic View"}
        </button>
      </div>

      {/* Director Playback (default) */}
      {viewMode === "director" && (
        <div className="animate-fade-in">
          <DirectorPlayback result={result} scenario={scenario} />
        </div>
      )}

      {/* Classic Tab View (legacy) */}
      {viewMode === "classic" && (
        <div className="apple-card overflow-hidden animate-fade-in">
          <div className="flex border-b border-[rgba(215,92,112,0.18)] bg-[var(--bg-card)]">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex-1 px-3 py-2.5 text-xs font-medium transition-all border-b-2 cursor-pointer ${
                  tab === t.id
                    ? "border-[var(--fortune-red)] text-[var(--fortune-red)] bg-[var(--bg-card)]"
                    : "border-transparent text-[var(--text-body)] hover:text-[var(--text-h1)]"
                }`}
              >
                {t.label}
                {t.count > 0 && (
                  <span className="ml-1.5 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full text-[12px] bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]">
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="p-4 space-y-2 min-h-[200px]">
            {tab === "content" && (
              <div className="space-y-3">
                {/* Sub-navigation pills */}
                <div className="flex gap-1.5 border-b border-[rgba(215,92,112,0.18)] pb-2">
                  {CONTENT_SUBTABS.map((st) => (
                    <button
                      key={st.id}
                      onClick={() => setContentSub(st.id as typeof contentSub)}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
                        contentSub === st.id
                          ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]"
                          : "text-[var(--text-body)] hover:text-[var(--text-h1)] hover:bg-[var(--bg-panel)]"
                      }`}>
                      {st.label}
                      {st.count > 0 && <span className="ml-1 text-[12px] opacity-60">{st.count}</span>}
                    </button>
                  ))}
                </div>
                {/* Sub-content */}
                {contentSub === "briefs" && <BriefsView briefs={briefs} onEdit={(index, data) => onEdit?.("briefs", index, data)} />}
                {contentSub === "scripts" && <ScriptsView scripts={scripts} onEdit={(index, data) => onEdit?.("scripts", index, data)} />}
                {contentSub === "videos" && <VideoPromptsView prompts={videoPrompts} onRegenerate={(index) => onEdit?.("videos", index, { action: "regenerate" })} />}
                {contentSub === "thumbnails" && <ThumbnailsView sets={thumbnails} thumbImages={thumbImages} onRegenerate={(index) => onEdit?.("thumbnails", index, { action: "regenerate" })} />}
              </div>
            )}
            {tab === "media" && <MediaView finalVideo={finalVideo} thumbImages={thumbImages} audioPaths={audioPaths} clipPaths={clipPaths} audit={audit} scenario={scenario} result={result} />}
            {tab === "quality" && <QualityDashboard qualityReport={audit} />}
            {tab === "data" && (
              <div className="space-y-3">
                <PerformanceDashboard scenario={scenario} />
                <RawView data={result} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center">
      <div className="text-lg font-semibold text-[var(--text-h1)]">{value}</div>
      <div className="text-[12px] text-[var(--text-muted)] uppercase tracking-wider">{label}</div>
    </div>
  );
}

function BriefsView({ briefs, onEdit }: { briefs: ResultItem[]; onEdit?: (index: number, data: ResultItem) => void }) {
  const { t } = useI18n();
  if (briefs.length === 0) return <Empty text={t("step.noStrategy")} />;
  return (
    <div className="space-y-2">
      {briefs.map((b, i) => (
        <BriefCard key={i} brief={b} index={i} onEdit={onEdit} />
      ))}
    </div>
  );
}

function BriefCard({ brief, index, onEdit }: { brief: ResultItem; index: number; onEdit?: (index: number, data: ResultItem) => void }) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);

  return (
    <div className="apple-card p-3 bg-[var(--bg-card)]">
      <div className="flex items-start gap-2 mb-1">
        {brief.platform && (
          <span className="text-[12px] font-semibold px-2 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] shrink-0">
            {t("platform." + brief.platform)}
          </span>
        )}
        {brief.hook_type && (
          <span className="text-[12px] font-medium px-2 py-0.5 rounded-full bg-[rgba(89,88,94,0.10)] text-[var(--text-body)]">
            {brief.hook_type}
          </span>
        )}
        <span className="text-[12px] text-[var(--text-muted)] ml-auto">{brief.id || `Brief ${index + 1}`}</span>
        {onEdit && (
          <button
            onClick={() => setEditing(!editing)}
            className="text-[12px] text-[var(--fortune-red)] hover:underline cursor-pointer px-1"
          >
            {editing ? t("step.cancel") : t("step.edit")}
          </button>
        )}
      </div>
      {editing ? (
        <EditableBrief
          brief={brief}
          onChange={(updated) => {
            onEdit?.(index, updated);
            setEditing(false);
          }}
        />
      ) : (
        <>
          <h4 className="text-sm font-semibold text-[var(--text-h1)] mb-1">{brief.product_name || brief.brand_name || "Brief"}</h4>
          {brief.description && <p className="text-xs text-[var(--text-body)] leading-relaxed">{brief.description}</p>}
          {brief.key_message && <p className="text-xs text-[var(--text-body)] leading-relaxed mt-1">💡 {brief.key_message}</p>}
          {brief.usp_priority && brief.usp_priority.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {brief.usp_priority.map((u: string, j: number) => (
                <span key={j} className="text-[12px] px-1.5 py-0.5 rounded bg-[var(--bg-panel)] text-[var(--text-body)]">{u}</span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ScriptsView({ scripts, onEdit }: { scripts: ScriptItem[]; onEdit?: (index: number, data: ScriptItem) => void }) {
  const { t } = useI18n();
  if (scripts.length === 0) return <Empty text={t("step.noScript")} />;
  return (
    <div className="space-y-2">
      {scripts.map((s, i) => (
        <ScriptCard key={i} script={s} index={i} onEdit={onEdit} />
      ))}
    </div>
  );
}

function ScriptCard({ script, index, onEdit }: { script: ScriptItem; index: number; onEdit?: (index: number, data: ScriptItem) => void }) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);

  return (
    <details className="apple-card overflow-hidden">
      <summary className="p-3 cursor-pointer flex items-center gap-2 list-none">
        <span className="text-[12px] font-mono text-[var(--text-muted)]">{script.id || `S${index + 1}`}</span>
        <span className="text-sm font-medium text-[var(--text-h1)] flex-1">
          {script.product_name || script.brand_name || "Script"}
        </span>
        <span className="text-[12px] text-[var(--text-muted)]">{(script.segments || []).length}{t("step.segments")}</span>
        {onEdit && (
          <button
            onClick={(e) => { e.preventDefault(); setEditing(!editing); }}
            className="text-[12px] text-[var(--fortune-red)] hover:underline cursor-pointer px-1"
          >
            {editing ? t("step.cancel") : t("step.edit")}
          </button>
        )}
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M2.5 3.5L5 6.5L7.5 3.5" stroke="var(--text-muted)" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
      </summary>
      <div className="px-3 pb-3 space-y-2 border-t border-[rgba(215,92,112,0.18)] pt-2">
        {editing ? (
          <EditableScript
            script={script}
            onChange={(updated) => {
              onEdit?.(index, updated);
              setEditing(false);
            }}
          />
        ) : (
          (script.segments || []).map((seg, j) => (
            <div key={j} className="pl-3 border-l-2 border-[rgba(215,92,112,0.18)]">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-[12px] font-semibold text-[var(--fortune-red)] uppercase">{seg.segment_type}</span>
                <span className="text-[12px] text-[var(--text-muted)] font-mono">
                  {seg.start_time ?? 0}s — {seg.end_time ?? 0}s
                </span>
              </div>
              <p className="text-xs text-[var(--text-h1)]">{seg.description || seg.voiceover}</p>
              {seg.visual_description && (
                <p className="text-[12px] text-[var(--text-body)] mt-1 italic">📷 {seg.visual_description}</p>
              )}
            </div>
          ))
        )}
      </div>
    </details>
  );
}

function VideoPromptsView({ prompts, onRegenerate }: { prompts: VideoPromptItem[]; onRegenerate?: (index: number) => void }) {
  const { t } = useI18n();
  if (prompts.length === 0) return <Empty text={t("step.noData")} />;
  return (
    <div className="space-y-2">
      {prompts.map((p, i) => {
        const txt = typeof p.prompt === "string" ? p.prompt : (p.prompt?.seedance_prompt || JSON.stringify(p.prompt, null, 2));
        return (
          <div key={i} className="apple-card p-3 bg-[var(--bg-card)]">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[12px] font-mono text-[var(--text-muted)]">{p.script_id || `Prompt ${i + 1}`}</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => navigator.clipboard.writeText(txt)}
                  className="text-[12px] text-[var(--fortune-red)] hover:underline cursor-pointer"
                  title={t("result.copyPrompt")}
                >
                  {t("result.copy")}
                </button>
                {onRegenerate && (
                  <button
                    onClick={() => onRegenerate(i)}
                    className="text-[12px] text-[var(--text-body)] hover:text-[var(--text-h1)] cursor-pointer px-1.5 py-0.5 rounded hover:bg-[rgba(215,92,112,0.18)]"
                  >
                    {t("step.regenerate")}
                  </button>
                )}
              </div>
            </div>
            <p className="text-xs text-[var(--text-h1)] font-mono whitespace-pre-wrap break-words">{txt}</p>
          </div>
        );
      })}
    </div>
  );
}

function ThumbnailsView({ sets, thumbImages, onRegenerate }: { sets: ThumbnailSet[]; thumbImages: string[]; onRegenerate?: (index: number) => void }) {
  const { t } = useI18n();
  // If we have real generated images, show them first
  const hasRealImages = thumbImages.length > 0;

  return (
    <div className="space-y-3">
      {/* Real generated images */}
      {hasRealImages && (
        <div className="apple-card p-3 bg-[var(--bg-card)]">
          <p className="text-[12px] font-mono text-[var(--text-muted)] mb-2">{t("result.thumbnails")} ({thumbImages.length})</p>
          <div className="grid grid-cols-2 gap-2">
            {thumbImages.map((p, i) => (
              <div key={i} className="relative bg-black rounded-lg overflow-hidden aspect-[9/16]">
                {getMediaUrl(p) ? (
                  <RuntimeMediaImage
                    src={getMediaUrl(p)}
                    alt={`thumbnail-${i}`}
                    className="w-full h-full object-cover"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-[var(--bg-panel)]">
                    <span className="text-[12px] text-[var(--text-muted)]">Thumbnail (Demo)</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Prompt variants */}
      {sets.length === 0 && !hasRealImages ? (
        <Empty text={t("result.empty")} />
      ) : (
        sets.map((set, i) => {
          const variants = set.variants || (Array.isArray(set) ? set : [set]);
          return (
            <div key={i} className="apple-card p-3 bg-[var(--bg-card)]">
              <p className="text-[12px] font-mono text-[var(--text-muted)] mb-2">{set.script_id || `Set ${i + 1}`}</p>
              <div className="grid grid-cols-2 gap-2">
                {variants.map((v, j) => (
                  <div key={j} className="apple-card p-3 bg-[var(--bg-card)]">
                    <div className="bg-gradient-to-br from-[var(--bg-panel)] to-[rgba(215,92,112,0.18)] rounded-lg h-24 flex items-center justify-center mb-2">
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="var(--text-muted)">
                        <rect x="3" y="3" width="18" height="18" rx="3" />
                        <circle cx="9" cy="9" r="2" />
                        <path d="M3 15l4-3 5 4 4-3 5 4" />
                      </svg>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="text-[12px] font-semibold text-[var(--text-h1)]">
                        {v.style || v.variant_id || `${t("review.variant")} ${j + 1}`}
                      </div>
                      {onRegenerate && (
                        <button
                          onClick={() => onRegenerate(j)}
                          className="text-[12px] text-[var(--text-body)] hover:text-[var(--text-h1)] cursor-pointer px-1"
                        >
                          {t("step.regenerate")}
                        </button>
                      )}
                    </div>
                    <div className="text-[12px] text-[var(--text-body)] line-clamp-2 mt-0.5">
                      {v.concept || v.prompt || ""}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}

function MediaView({
  finalVideo,
  thumbImages,
  audioPaths,
  clipPaths,
  audit,
  result,
}: {
  finalVideo: string;
  thumbImages: string[];
  audioPaths: string[];
  clipPaths: string[];
  audit: AuditReport | null;
  scenario: string;
  result: OneShotResult;
}) {
  const { t } = useI18n();
  const [showPublish, setShowPublish] = useState(false);
  const hasAny = finalVideo || thumbImages.length > 0 || audioPaths.length > 0 || clipPaths.length > 0;
  if (!hasAny) return <Empty text={t("step.noMedia")} />;

  const briefs = result?.briefs || [];
  const targetPlatforms = briefs.length > 0
    ? Array.from(new Set(briefs.flatMap((b) => typeof b.platform === "string" ? [b.platform] : [])))
    : ["tiktok", "shopify"];

  const firstBrief = briefs[0] || {};

  return (
    <div className="space-y-4">
      {/* Final video */}
      {finalVideo && (
        <div className="apple-card p-3 bg-[var(--bg-card)]">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-[rgba(196,91,80,0.10)] flex items-center justify-center">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--crimson-mist)" strokeWidth="2">
                  <polygon points="23 7 16 12 23 17 23 7" />
                  <rect x="1" y="5" width="15" height="14" rx="2" />
                </svg>
              </div>
              <p className="text-[12px] font-semibold text-[var(--text-h1)]">{t("result.finalVideo")}</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowPublish(true)}
                className="apple-btn apple-btn-primary text-[12px] py-1 px-2 cursor-pointer"
              >
                {t("perf.publishTitle")}
              </button>
              {getMediaUrl(finalVideo) && (
                <a
                  href={getMediaUrl(finalVideo)}
                  download
                  className="text-[12px] text-[var(--fortune-red)] hover:underline cursor-pointer"
                >
                  {t("result.download")}
                </a>
              )}
            </div>
          </div>
          {getMediaUrl(finalVideo) ? (
            <video
              src={getMediaUrl(finalVideo)}
              controls
              className="w-full rounded-xl bg-black"
              style={{ maxHeight: 480, colorScheme: 'dark' }}
              preload="metadata"
            />
          ) : (
            <DemoPlaceholder label="Final Video (Demo)" />
          )}
        </div>
      )}

      {/* Publish Panel */}
      {showPublish && finalVideo && (
        <PublishPanel
          videoPath={finalVideo}
          metadata={{
            hook: firstBrief.hook || firstBrief.key_message || firstBrief.product_name || "",
            hashtags: firstBrief.tags || firstBrief.usp_priority || [],
            productName: firstBrief.product_name || "",
          }}
          onClose={() => setShowPublish(false)}
        />
      )}

      {/* Raw clips */}
      {clipPaths.length > 0 && (
        <div className="apple-card p-3 bg-[var(--bg-card)]">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-6 h-6 rounded-md bg-[rgba(215,92,112,0.10)] flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--fortune-red)" strokeWidth="2">
                <polygon points="23 7 16 12 23 17 23 7" />
                <rect x="1" y="5" width="15" height="14" rx="2" />
              </svg>
            </div>
            <p className="text-[12px] font-semibold text-[var(--text-h1)]">{t("result.mediaClips")} ({clipPaths.length})</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {clipPaths.map((p, i) => (
              <div key={i} className="space-y-1">
                {getMediaUrl(p) ? (
                  <video
                    src={getMediaUrl(p)}
                    controls
                    className="w-full rounded-xl bg-black"
                    style={{ maxHeight: 220, colorScheme: 'dark' }}
                    preload="metadata"
                  />
                ) : (
                  <DemoPlaceholder label={`Clip ${i + 1} (Demo)`} />
                )}
                <p className="text-[12px] text-[var(--text-muted)] truncate px-1">{p.split("/").pop()}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Thumbnail images */}
      {thumbImages.length > 0 && (
        <div className="apple-card p-3 bg-[var(--bg-card)]">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-6 h-6 rounded-md bg-[rgba(215,92,112,0.10)] flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--fortune-red)" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
            <p className="text-[12px] font-semibold text-[var(--text-h1)]">{t("result.thumbnails")} ({thumbImages.length})</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {thumbImages.map((p, i) => (
              <div key={i} className="relative bg-black rounded-xl overflow-hidden aspect-[9/16] group">
                {getMediaUrl(p) ? (
                  <RuntimeMediaImage
                    src={getMediaUrl(p)}
                    alt={`thumbnail-${i}`}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-[var(--bg-panel)]">
                    <span className="text-[12px] text-[var(--text-muted)]">Thumbnail (Demo)</span>
                  </div>
                )}
                <a
                  href={getMediaUrl(p) || "#"}
                  download
                  className="absolute top-2 right-2 w-7 h-7 rounded-lg bg-black/50 backdrop-blur-sm flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                </a>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Audio clips */}
      {audioPaths.length > 0 && (
        <div className="apple-card p-3 bg-[var(--bg-card)]">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-6 h-6 rounded-md bg-[rgba(255,159,10,0.10)] flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--gold-foil)" strokeWidth="2">
                <path d="M9 18V5l12-2v13" />
                <circle cx="6" cy="18" r="3" />
                <circle cx="18" cy="16" r="3" />
              </svg>
            </div>
            <p className="text-[12px] font-semibold text-[var(--text-h1)]">{t("result.audioTracks")} ({audioPaths.length})</p>
          </div>
          <div className="space-y-2">
            {audioPaths.map((p, i) => (
              <div key={i} className="flex items-center gap-2 bg-[var(--bg-card)] rounded-xl p-2 border border-[rgba(215,92,112,0.18)]">
                <div className="w-8 h-8 rounded-lg bg-[rgba(255,159,10,0.10)] flex items-center justify-center shrink-0">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--gold-foil)" strokeWidth="2">
                    <path d="M9 18V5l12-2v13" />
                    <circle cx="6" cy="18" r="3" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[12px] text-[var(--text-h1)] truncate">{p.split("/").pop()}</p>
                  {getMediaUrl(p) ? (
                    <audio src={getMediaUrl(p)} controls preload="metadata" className="w-full h-8" />
                  ) : (
                    <p className="text-[12px] text-[var(--text-muted)] py-1">Audio preview unavailable (demo mode)</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Platform Distribution */}
      <div className="apple-card p-3 bg-[var(--bg-card)]">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-6 h-6 rounded-md bg-[rgba(215,92,112,0.10)] flex items-center justify-center">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--fortune-red)" strokeWidth="2">
              <polyline points="17 1 21 5 17 9" />
              <path d="M3 11V9a4 4 0 0 1 4-4h14" />
              <polyline points="7 23 3 19 7 15" />
              <path d="M21 13v2a4 4 0 0 1-4 4H3" />
            </svg>
          </div>
          <p className="text-[12px] font-semibold text-[var(--text-h1)]">{t("result.platformDistribution")}</p>
        </div>
        <div className="space-y-2">
          {targetPlatforms.map((platform) => (
            <PlatformPublishRow key={platform as string} platform={platform as string} result={result} />
          ))}
        </div>
      </div>

      {/* Audit report */}
      {audit && (
        <div className="apple-card p-3 bg-[var(--bg-card)]">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-[rgba(122,150,187,0.10)] flex items-center justify-center">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cinema-azure)" strokeWidth="2">
                  <path d="M9 11l3 3L22 4" />
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                </svg>
              </div>
              <p className="text-[12px] font-semibold text-[var(--text-h1)]">{t("quality.title")}</p>
            </div>
            <span
              className={`text-[12px] font-semibold px-2 py-0.5 rounded-full ${
                audit.overall_status === "PASS"
                  ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]"
                  : audit.overall_status === "WARN"
                  ? "bg-[rgba(255,159,10,0.10)] text-[var(--gold-foil)]"
                  : "bg-[rgba(196,91,80,0.10)] text-[var(--crimson-mist)]"
              }`}
            >
              {audit.overall_status} · {(audit.overall_score * 100).toFixed(0)}%
            </span>
          </div>
          <p className="text-xs text-[var(--text-body)] mb-2">{audit.summary}</p>
          <div className="space-y-1">
            {audit.criteria?.map((c, i) => (
              <div key={i} className="flex items-center gap-2 text-[12px]">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    c.status === "PASS" ? "bg-[var(--fortune-red)]" : c.status === "WARN" ? "bg-[var(--gold-foil)]" : "bg-[var(--crimson-mist)]"
                  }`}
                />
                <span className="text-[var(--text-h1)] flex-1">{c.name}</span>
                <span className={`font-medium ${
                  c.status === "PASS" ? "text-[var(--fortune-red)]" : c.status === "WARN" ? "text-[var(--gold-foil)]" : "text-[var(--crimson-mist)]"
                }`}>{c.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RawView({ data }: { data: unknown }) {
  return (
    <pre className="text-[12px] font-mono text-[var(--text-body)] bg-[var(--bg-card)] p-3 rounded-lg overflow-auto max-h-[400px] whitespace-pre-wrap break-all">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function PlatformPublishRow({ platform, result }: { platform: string; result: OneShotResult }) {
  const { t } = useI18n();
  const [pubResult, setPubResult] = useState<PublishRowResult | null>(null);
  const [isPublishing, setIsPublishing] = useState(false);

  const handlePublish = async () => {
    setIsPublishing(true);
    try {
      const brief = result?.briefs?.[0] || {};
      const script = result?.scripts?.[0] || {};
      const content = {
        title: brief.product_name || brief.brand_name || script.product_name || "AI Generated Content",
        description: brief.description || script.description || brief.key_message || "",
        video_url: result?.final_video_path || "",
        tags: brief.tags || [],
        thumbnail_url: result?.thumbnail_image_paths?.[0] || "",
      };
      const res = await publishContent(platform, content);
      setPubResult({ success: true, ...res });
    } catch (err: unknown) {
      setPubResult({ success: false, error: errorMessage(err, t("dist.publishFailed")) });
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <div className="flex items-center justify-between p-2 rounded-lg bg-[var(--bg-card)] border border-[rgba(215,92,112,0.18)]">
      <div className="flex items-center gap-2">
        {React.createElement(PLATFORM_ICON_MAP[platform] || ShoppingBag, { size: 16, weight: "fill", className: "text-[var(--text-body)]" })}
        <span className="text-xs font-medium text-[var(--text-h1)]">{t("platform." + platform)}</span>
      </div>
      {!pubResult && (
        <button
          onClick={handlePublish}
          disabled={isPublishing}
          className="apple-btn apple-btn-primary text-[12px] py-1 px-2"
        >
          {isPublishing ? (
            <span className="inline-flex items-center gap-1">
              <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              {t("dist.publishing")}
            </span>
          ) : t("dist.publish")}
        </button>
      )}
      {pubResult?.success && (
        <div className="flex items-center gap-2">
          <span className="text-[12px] px-1.5 py-0.5 rounded bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] font-medium">{t("dist.published")}</span>
          {pubResult.url && (
            <a
              href={pubResult.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[12px] text-[var(--fortune-red)] hover:underline"
            >
              {t("dist.view")}
            </a>
          )}
        </div>
      )}
      {pubResult && !pubResult.success && (
        <div className="flex items-center gap-2">
          <span className="text-[12px] px-1.5 py-0.5 rounded bg-[rgba(196,91,80,0.10)] text-[var(--crimson-mist)] font-medium">{t("dist.failed")}</span>
          <button
            onClick={handlePublish}
            disabled={isPublishing}
            className="text-[12px] text-[var(--text-body)] hover:text-[var(--text-h1)] underline cursor-pointer"
          >
            {isPublishing ? t("dist.retrying") : t("dist.retry")}
          </button>
        </div>
      )}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="text-center py-10">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="rgba(215,92,112,0.18)" strokeWidth="1.5" className="mx-auto mb-2">
        <circle cx="12" cy="12" r="10" />
        <path d="M8 14s1.5 2 4 2 4-2 4-2" />
        <line x1="9" y1="9" x2="9.01" y2="9" />
        <line x1="15" y1="9" x2="15.01" y2="9" />
      </svg>
      <p className="text-xs text-[var(--text-muted)]">{text}</p>
    </div>
  );
}
