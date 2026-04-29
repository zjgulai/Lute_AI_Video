"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { downloadJson, getMediaUrl, publishContent } from "./api";
import React from "react";
import { ShoppingBag, Music, MessageCircle, Video, ShoppingCart, ExternalLink } from "lucide-react";
import { AuditReport } from "./types";
import EditableBrief from "./EditableBrief";
import EditableScript from "./EditableScript";
import QualityDashboard from "./QualityDashboard";
import PerformanceDashboard from "./PerformanceDashboard";
import PublishPanel from "./PublishPanel";

const PLATFORM_ICON_MAP: Record<string, React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>> = {
  shopify: ShoppingBag,
  amazon: ShoppingCart,
  tiktok: Music,
  reddit: MessageCircle,
  facebook: ExternalLink,
  youtube_shorts: Video,
};

interface Props {
  scenario: string;
  result: any;
  onReset: () => void;
  onEdit?: (tab: string, index: number, data: any) => void;
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
    <div className="w-full rounded-xl bg-[#f5f5f7] border border-dashed border-[#d2d2d7] flex flex-col items-center justify-center gap-2 text-center"
      style={{ minHeight: 180 }}>
      <div className="w-10 h-10 rounded-full bg-[#e8e8ed] flex items-center justify-center">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#86868b" strokeWidth="2">
          <rect x="2" y="2" width="20" height="20" rx="2" />
          <path d="M2 12h20M12 2v20" />
        </svg>
      </div>
      <div>
        <p className="text-xs font-medium text-[#86868b]">Demo Mode</p>
        <p className="text-[10px] text-[#aeaeb2]">{label}</p>
      </div>
    </div>
  );
}

export default function OneShotResultView({ scenario, result, onReset, onEdit }: Props) {
  const { t } = useI18n();
  const [tab, setTab] = useState<"briefs" | "scripts" | "videos" | "thumbnails" | "media" | "quality" | "performance" | "raw">("media");

  const briefs: any[] = result?.briefs || [];
  const scripts: any[] = result?.scripts || [];
  const storyboards: any[] = result?.storyboards || [];
  const videoPrompts: any[] = result?.video_prompts || [];
  const thumbnails: any[] = result?.thumbnail_sets || result?.thumbnails || [];
  const success: boolean = result?.success !== false;
  const stepsCompleted: number = result?.steps_completed || 0;
  const finalVideo: string = result?.final_video_path || "";
  const thumbImages: string[] = result?.thumbnail_image_paths || [];
  const audioPaths: string[] = result?.audio_paths || [];
  const clipPaths: string[] = result?.clip_paths || [];
  const audit: AuditReport | null = result?.audit_report || null;
  const mediaCount = (finalVideo ? 1 : 0) + thumbImages.length + audioPaths.length + clipPaths.length;

  const TABS = [
    { id: "briefs", label: t("result.tab.briefs"), count: briefs.length, icon: "M12 6v6l4 2" },
    { id: "scripts", label: t("result.tab.scripts"), count: scripts.length, icon: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2 14 8 20 8" },
    { id: "videos", label: t("result.tab.videos"), count: videoPrompts.length, icon: "M23 7l-7 5 7 5V7z M1 5h15v14H1z" },
    { id: "thumbnails", label: t("result.tab.thumbnails"), count: thumbnails.length, icon: "M3 3h18v18H3z M8.5 8.5a1.5 1.5 0 1 1 0-3 M21 15l-5-5-11 11" },
    { id: "media", label: t("result.tab.media"), count: mediaCount, icon: "M23 7l-7 5 7 5V7z M1 5h15v14H1z" },
    { id: "quality", label: t("result.tab.quality"), count: audit ? (audit.criteria?.length || 0) : 0, icon: "M9 11l3 3L22 4 M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" },
    { id: "performance", label: t("perf.title"), count: 0, icon: "M9 11l3 3L22 4 M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" },
    { id: "raw", label: t("result.tab.raw"), count: 0, icon: "M9 11l3 3 8-8 M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" },
  ];

  return (
    <div className="space-y-3 animate-slide-up">
      {/* Result header */}
      <div className="apple-card p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 ${success ? "bg-[#7CB342]/10 text-[#7CB342]" : "bg-[#ff453a]/10 text-[#ff453a]"}`}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                {success
                  ? <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                  : <><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" /></>
                }
              </svg>
            </div>
            <div>
              <h2 className="text-base font-semibold text-[#1d1d1f]">{t(SCENARIO_LABELS[scenario] || scenario)} {t("result.complete")}</h2>
              <p className="text-xs text-[#86868b] mt-0.5">
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
        <div className="grid grid-cols-5 gap-2 mt-4 pt-3 border-t border-[#e8e8ed]">
          <Stat label={t("result.tab.briefs")} value={briefs.length} />
          <Stat label={t("result.tab.scripts")} value={scripts.length} />
          <Stat label={t("result.tab.videos")} value={videoPrompts.length} />
          <Stat label={t("result.tab.thumbnails")} value={thumbnails.length} />
          <Stat label={t("result.tab.media")} value={mediaCount} />
        </div>

      </div>

      {/* Tab nav */}
      <div className="apple-card overflow-hidden">
        <div className="flex border-b border-[#e8e8ed] bg-[#fafafc]">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id as any)}
              className={`flex-1 px-3 py-2.5 text-xs font-medium transition-all border-b-2 cursor-pointer ${
                tab === t.id
                  ? "border-[#7CB342] text-[#7CB342] bg-white"
                  : "border-transparent text-[#86868b] hover:text-[#1d1d1f]"
              }`}
            >
              {t.label}
              {t.count > 0 && (
                <span className="ml-1.5 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full text-[9px] bg-[#7CB342]/10 text-[#7CB342]">
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="p-4 space-y-2 min-h-[200px]">
          {tab === "briefs" && <BriefsView briefs={briefs} onEdit={(index, data) => onEdit?.("briefs", index, data)} />}
          {tab === "scripts" && <ScriptsView scripts={scripts} onEdit={(index, data) => onEdit?.("scripts", index, data)} />}
          {tab === "videos" && <VideoPromptsView prompts={videoPrompts} onRegenerate={(index) => onEdit?.("videos", index, { action: "regenerate" })} />}
          {tab === "thumbnails" && <ThumbnailsView sets={thumbnails} thumbImages={thumbImages} onRegenerate={(index) => onEdit?.("thumbnails", index, { action: "regenerate" })} />}
          {tab === "media" && <MediaView finalVideo={finalVideo} thumbImages={thumbImages} audioPaths={audioPaths} clipPaths={clipPaths} audit={audit} scenario={scenario} result={result} />}
          {tab === "quality" && <QualityDashboard qualityReport={audit} />}
          {tab === "performance" && <PerformanceDashboard scenario={scenario} />}
          {tab === "raw" && <RawView data={result} />}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center">
      <div className="text-lg font-semibold text-[#1d1d1f]">{value}</div>
      <div className="text-[10px] text-[#aeaeb2] uppercase tracking-wider">{label}</div>
    </div>
  );
}

function BriefsView({ briefs, onEdit }: { briefs: any[]; onEdit?: (index: number, data: any) => void }) {
  const { t } = useI18n();
  if (briefs.length === 0) return <Empty text={t("step.noStrategy")} />;
  return (
    <div className="space-y-2">
      {briefs.map((b: any, i: number) => (
        <BriefCard key={i} brief={b} index={i} onEdit={onEdit} />
      ))}
    </div>
  );
}

function BriefCard({ brief, index, onEdit }: { brief: any; index: number; onEdit?: (index: number, data: any) => void }) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);

  return (
    <div className="apple-card p-3 bg-[#fafafc]">
      <div className="flex items-start gap-2 mb-1">
        {brief.platform && (
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#7CB342]/10 text-[#7CB342] shrink-0">
            {t("platform." + brief.platform)}
          </span>
        )}
        {brief.hook_type && (
          <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-[#86868b]/10 text-[#86868b]">
            {brief.hook_type}
          </span>
        )}
        <span className="text-[10px] text-[#aeaeb2] ml-auto">{brief.id || `Brief ${index + 1}`}</span>
        {onEdit && (
          <button
            onClick={() => setEditing(!editing)}
            className="text-[10px] text-[#7CB342] hover:underline cursor-pointer px-1"
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
          <h4 className="text-sm font-semibold text-[#1d1d1f] mb-1">{brief.product_name || brief.brand_name || "Brief"}</h4>
          {brief.description && <p className="text-xs text-[#86868b] leading-relaxed">{brief.description}</p>}
          {brief.key_message && <p className="text-xs text-[#86868b] leading-relaxed mt-1">💡 {brief.key_message}</p>}
          {brief.usp_priority && brief.usp_priority.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {brief.usp_priority.map((u: string, j: number) => (
                <span key={j} className="text-[10px] px-1.5 py-0.5 rounded bg-[#f5f5f7] text-[#86868b]">{u}</span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ScriptsView({ scripts, onEdit }: { scripts: any[]; onEdit?: (index: number, data: any) => void }) {
  const { t } = useI18n();
  if (scripts.length === 0) return <Empty text={t("step.noScript")} />;
  return (
    <div className="space-y-2">
      {scripts.map((s: any, i: number) => (
        <ScriptCard key={i} script={s} index={i} onEdit={onEdit} />
      ))}
    </div>
  );
}

function ScriptCard({ script, index, onEdit }: { script: any; index: number; onEdit?: (index: number, data: any) => void }) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);

  return (
    <details className="apple-card overflow-hidden">
      <summary className="p-3 cursor-pointer flex items-center gap-2 list-none">
        <span className="text-[10px] font-mono text-[#aeaeb2]">{script.id || `S${index + 1}`}</span>
        <span className="text-sm font-medium text-[#1d1d1f] flex-1">
          {script.product_name || script.brand_name || "Script"}
        </span>
        <span className="text-[10px] text-[#aeaeb2]">{(script.segments || []).length}{t("step.segments")}</span>
        {onEdit && (
          <button
            onClick={(e) => { e.preventDefault(); setEditing(!editing); }}
            className="text-[10px] text-[#7CB342] hover:underline cursor-pointer px-1"
          >
            {editing ? t("step.cancel") : t("step.edit")}
          </button>
        )}
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <path d="M2.5 3.5L5 6.5L7.5 3.5" stroke="#aeaeb2" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
      </summary>
      <div className="px-3 pb-3 space-y-2 border-t border-[#e8e8ed] pt-2">
        {editing ? (
          <EditableScript
            script={script}
            onChange={(updated) => {
              onEdit?.(index, updated);
              setEditing(false);
            }}
          />
        ) : (
          (script.segments || []).map((seg: any, j: number) => (
            <div key={j} className="pl-3 border-l-2 border-[#e8e8ed]">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-[10px] font-semibold text-[#7CB342] uppercase">{seg.segment_type}</span>
                <span className="text-[10px] text-[#aeaeb2] font-mono">
                  {seg.start_time ?? 0}s — {seg.end_time ?? 0}s
                </span>
              </div>
              <p className="text-xs text-[#1d1d1f]">{seg.description || seg.voiceover}</p>
              {seg.visual_description && (
                <p className="text-[11px] text-[#86868b] mt-1 italic">📷 {seg.visual_description}</p>
              )}
            </div>
          ))
        )}
      </div>
    </details>
  );
}

function VideoPromptsView({ prompts, onRegenerate }: { prompts: any[]; onRegenerate?: (index: number) => void }) {
  const { t } = useI18n();
  if (prompts.length === 0) return <Empty text={t("step.noData")} />;
  return (
    <div className="space-y-2">
      {prompts.map((p: any, i: number) => {
        const txt = typeof p.prompt === "string" ? p.prompt : (p.prompt?.seedance_prompt || JSON.stringify(p.prompt, null, 2));
        return (
          <div key={i} className="apple-card p-3 bg-[#fafafc]">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-mono text-[#aeaeb2]">{p.script_id || `Prompt ${i + 1}`}</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => navigator.clipboard.writeText(txt)}
                  className="text-[10px] text-[#7CB342] hover:underline cursor-pointer"
                  title={t("result.copyPrompt")}
                >
                  {t("result.copy")}
                </button>
                {onRegenerate && (
                  <button
                    onClick={() => onRegenerate(i)}
                    className="text-[10px] text-[#86868b] hover:text-[#1d1d1f] cursor-pointer px-1.5 py-0.5 rounded hover:bg-[#e8e8ed]/50"
                  >
                    {t("step.regenerate")}
                  </button>
                )}
              </div>
            </div>
            <p className="text-xs text-[#1d1d1f] font-mono whitespace-pre-wrap break-words">{txt}</p>
          </div>
        );
      })}
    </div>
  );
}

function ThumbnailsView({ sets, thumbImages, onRegenerate }: { sets: any[]; thumbImages: string[]; onRegenerate?: (index: number) => void }) {
  const { t } = useI18n();
  // If we have real generated images, show them first
  const hasRealImages = thumbImages.length > 0;

  return (
    <div className="space-y-3">
      {/* Real generated images */}
      {hasRealImages && (
        <div className="apple-card p-3 bg-[#fafafc]">
          <p className="text-[10px] font-mono text-[#aeaeb2] mb-2">{t("result.thumbnails")} ({thumbImages.length})</p>
          <div className="grid grid-cols-2 gap-2">
            {thumbImages.map((p, i) => (
              <div key={i} className="relative bg-black rounded-lg overflow-hidden aspect-[9/16]">
                {getMediaUrl(p) ? (
                  <img
                    src={getMediaUrl(p)}
                    alt={`thumbnail-${i}`}
                    className="w-full h-full object-cover"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-[#f5f5f7]">
                    <span className="text-[10px] text-[#aeaeb2]">Thumbnail (Demo)</span>
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
        sets.map((set: any, i: number) => {
          const variants = set.variants || (Array.isArray(set) ? set : [set]);
          return (
            <div key={i} className="apple-card p-3 bg-[#fafafc]">
              <p className="text-[10px] font-mono text-[#aeaeb2] mb-2">{set.script_id || `Set ${i + 1}`}</p>
              <div className="grid grid-cols-2 gap-2">
                {variants.map((v: any, j: number) => (
                  <div key={j} className="apple-card p-3 bg-white">
                    <div className="bg-gradient-to-br from-[#f5f5f7] to-[#e8e8ed] rounded-lg h-24 flex items-center justify-center mb-2">
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="#aeaeb2">
                        <rect x="3" y="3" width="18" height="18" rx="3" />
                        <circle cx="9" cy="9" r="2" />
                        <path d="M3 15l4-3 5 4 4-3 5 4" />
                      </svg>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="text-[11px] font-semibold text-[#1d1d1f]">
                        {v.style || v.variant_id || `${t("review.variant")} ${j + 1}`}
                      </div>
                      {onRegenerate && (
                        <button
                          onClick={() => onRegenerate(j)}
                          className="text-[10px] text-[#86868b] hover:text-[#1d1d1f] cursor-pointer px-1"
                        >
                          {t("step.regenerate")}
                        </button>
                      )}
                    </div>
                    <div className="text-[10px] text-[#86868b] line-clamp-2 mt-0.5">
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
  scenario,
  result,
}: {
  finalVideo: string;
  thumbImages: string[];
  audioPaths: string[];
  clipPaths: string[];
  audit: AuditReport | null;
  scenario: string;
  result: any;
}) {
  const { t } = useI18n();
  const [showPublish, setShowPublish] = useState(false);
  const hasAny = finalVideo || thumbImages.length > 0 || audioPaths.length > 0 || clipPaths.length > 0;
  if (!hasAny) return <Empty text={t("step.noMedia")} />;

  const briefs = result?.briefs || [];
  const targetPlatforms = briefs.length > 0
    ? Array.from(new Set(briefs.flatMap((b: any) => b.platform ? [b.platform] : [])))
    : ["tiktok", "shopify"];

  const firstBrief = briefs[0] || {};

  return (
    <div className="space-y-4">
      {/* Final video */}
      {finalVideo && (
        <div className="apple-card p-3 bg-[#fafafc]">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-[#ff453a]/10 flex items-center justify-center">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ff453a" strokeWidth="2">
                  <polygon points="23 7 16 12 23 17 23 7" />
                  <rect x="1" y="5" width="15" height="14" rx="2" />
                </svg>
              </div>
              <p className="text-[11px] font-semibold text-[#1d1d1f]">{t("result.finalVideo")}</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowPublish(true)}
                className="apple-btn apple-btn-primary text-[10px] py-1 px-2 cursor-pointer"
              >
                {t("perf.publishTitle")}
              </button>
              {getMediaUrl(finalVideo) && (
                <a
                  href={getMediaUrl(finalVideo)}
                  download
                  className="text-[10px] text-[#7CB342] hover:underline cursor-pointer"
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
              style={{ maxHeight: 480 }}
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
        <div className="apple-card p-3 bg-[#fafafc]">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-6 h-6 rounded-md bg-[#007aff]/10 flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#007aff" strokeWidth="2">
                <polygon points="23 7 16 12 23 17 23 7" />
                <rect x="1" y="5" width="15" height="14" rx="2" />
              </svg>
            </div>
            <p className="text-[11px] font-semibold text-[#1d1d1f]">{t("result.mediaClips")} ({clipPaths.length})</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {clipPaths.map((p, i) => (
              <div key={i} className="space-y-1">
                {getMediaUrl(p) ? (
                  <video
                    src={getMediaUrl(p)}
                    controls
                    className="w-full rounded-xl bg-black"
                    style={{ maxHeight: 220 }}
                    preload="metadata"
                  />
                ) : (
                  <DemoPlaceholder label={`Clip ${i + 1} (Demo)`} />
                )}
                <p className="text-[9px] text-[#aeaeb2] truncate px-1">{p.split("/").pop()}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Thumbnail images */}
      {thumbImages.length > 0 && (
        <div className="apple-card p-3 bg-[#fafafc]">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-6 h-6 rounded-md bg-[#7CB342]/10 flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#7CB342" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
            <p className="text-[11px] font-semibold text-[#1d1d1f]">{t("result.thumbnails")} ({thumbImages.length})</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {thumbImages.map((p, i) => (
              <div key={i} className="relative bg-black rounded-xl overflow-hidden aspect-[9/16] group">
                {getMediaUrl(p) ? (
                  <img
                    src={getMediaUrl(p)}
                    alt={`thumbnail-${i}`}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-[#f5f5f7]">
                    <span className="text-[10px] text-[#aeaeb2]">Thumbnail (Demo)</span>
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
        <div className="apple-card p-3 bg-[#fafafc]">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-6 h-6 rounded-md bg-[#ff9500]/10 flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ff9500" strokeWidth="2">
                <path d="M9 18V5l12-2v13" />
                <circle cx="6" cy="18" r="3" />
                <circle cx="18" cy="16" r="3" />
              </svg>
            </div>
            <p className="text-[11px] font-semibold text-[#1d1d1f]">{t("result.audioTracks")} ({audioPaths.length})</p>
          </div>
          <div className="space-y-2">
            {audioPaths.map((p, i) => (
              <div key={i} className="flex items-center gap-2 bg-white rounded-xl p-2 border border-[#e8e8ed]">
                <div className="w-8 h-8 rounded-lg bg-[#ff9500]/10 flex items-center justify-center shrink-0">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ff9500" strokeWidth="2">
                    <path d="M9 18V5l12-2v13" />
                    <circle cx="6" cy="18" r="3" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] text-[#1d1d1f] truncate">{p.split("/").pop()}</p>
                  {getMediaUrl(p) ? (
                    <audio src={getMediaUrl(p)} controls className="w-full h-8" />
                  ) : (
                    <p className="text-[10px] text-[#aeaeb2] py-1">Audio preview unavailable (demo mode)</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Platform Distribution */}
      <div className="apple-card p-3 bg-[#fafafc]">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-6 h-6 rounded-md bg-[#7CB342]/10 flex items-center justify-center">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#7CB342" strokeWidth="2">
              <polyline points="17 1 21 5 17 9" />
              <path d="M3 11V9a4 4 0 0 1 4-4h14" />
              <polyline points="7 23 3 19 7 15" />
              <path d="M21 13v2a4 4 0 0 1-4 4H3" />
            </svg>
          </div>
          <p className="text-[11px] font-semibold text-[#1d1d1f]">{t("result.platformDistribution")}</p>
        </div>
        <div className="space-y-2">
          {targetPlatforms.map((platform) => (
            <PlatformPublishRow key={platform as string} platform={platform as string} result={result} />
          ))}
        </div>
      </div>

      {/* Audit report */}
      {audit && (
        <div className="apple-card p-3 bg-[#fafafc]">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-[#5856d6]/10 flex items-center justify-center">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#5856d6" strokeWidth="2">
                  <path d="M9 11l3 3L22 4" />
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                </svg>
              </div>
              <p className="text-[11px] font-semibold text-[#1d1d1f]">{t("quality.title")}</p>
            </div>
            <span
              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                audit.overall_status === "PASS"
                  ? "bg-[#7CB342]/10 text-[#7CB342]"
                  : audit.overall_status === "WARN"
                  ? "bg-[#ff9500]/10 text-[#ff9500]"
                  : "bg-[#ff453a]/10 text-[#ff453a]"
              }`}
            >
              {audit.overall_status} · {(audit.overall_score * 100).toFixed(0)}%
            </span>
          </div>
          <p className="text-xs text-[#86868b] mb-2">{audit.summary}</p>
          <div className="space-y-1">
            {audit.criteria?.map((c, i) => (
              <div key={i} className="flex items-center gap-2 text-[11px]">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    c.status === "PASS" ? "bg-[#7CB342]" : c.status === "WARN" ? "bg-[#ff9500]" : "bg-[#ff453a]"
                  }`}
                />
                <span className="text-[#1d1d1f] flex-1">{c.name}</span>
                <span className={`font-medium ${
                  c.status === "PASS" ? "text-[#7CB342]" : c.status === "WARN" ? "text-[#ff9500]" : "text-[#ff453a]"
                }`}>{c.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RawView({ data }: { data: any }) {
  return (
    <pre className="text-[10px] font-mono text-[#86868b] bg-[#fafafc] p-3 rounded-lg overflow-auto max-h-[400px] whitespace-pre-wrap break-all">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function PlatformPublishRow({ platform, result }: { platform: string; result: any }) {
  const { t } = useI18n();
  const [pubResult, setPubResult] = useState<any>(null);
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
    } catch (err: any) {
      setPubResult({ success: false, error: err.message || t("dist.publishFailed") });
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <div className="flex items-center justify-between p-2 rounded-lg bg-white border border-[#e8e8ed]">
      <div className="flex items-center gap-2">
        {React.createElement(PLATFORM_ICON_MAP[platform] || ShoppingBag, { size: 16, strokeWidth: 1.5, className: "text-[#86868b]" })}
        <span className="text-xs font-medium text-[#1d1d1f]">{t("platform." + platform)}</span>
      </div>
      {!pubResult && (
        <button
          onClick={handlePublish}
          disabled={isPublishing}
          className="apple-btn apple-btn-primary text-[10px] py-1 px-2"
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
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#7CB342]/10 text-[#7CB342] font-medium">{t("dist.published")}</span>
          {pubResult.url && (
            <a
              href={pubResult.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] text-[#007aff] hover:underline"
            >
              {t("dist.view")}
            </a>
          )}
        </div>
      )}
      {pubResult && !pubResult.success && (
        <div className="flex items-center gap-2">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#ff453a]/10 text-[#ff453a] font-medium">{t("dist.failed")}</span>
          <button
            onClick={handlePublish}
            disabled={isPublishing}
            className="text-[10px] text-[#86868b] hover:text-[#1d1d1f] underline cursor-pointer"
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
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#e8e8ed" strokeWidth="1.5" className="mx-auto mb-2">
        <circle cx="12" cy="12" r="10" />
        <path d="M8 14s1.5 2 4 2 4-2 4-2" />
        <line x1="9" y1="9" x2="9.01" y2="9" />
        <line x1="15" y1="9" x2="15.01" y2="9" />
      </svg>
      <p className="text-xs text-[#aeaeb2]">{text}</p>
    </div>
  );
}
