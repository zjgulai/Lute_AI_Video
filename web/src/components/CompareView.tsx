"use client";

import { useState, useMemo } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { getMediaUrl } from "./api";
import { AuditReport } from "./types";

export interface Version {
  label: string;
  scriptVariant: string;
  videoPath: string;
  thumbnailPath: string;
  auditReport: AuditReport | null;
  duration: number;
  fileSize: number;
}

interface Props {
  versions: Version[];
  onSelect: (versionLabel: string) => void;
  onDownload: (versionLabel: string) => void;
  onNewCreation: () => void;
  onBack: () => void;
  onPublish: (versionLabel: string) => void;
  selectedVersion: string | null;
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const val = bytes / Math.pow(1024, i);
  return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function getVariantLabelKey(variant: string): string {
  switch (variant) {
    case "standard":
      return "compare.standard";
    case "creative":
      return "compare.creative";
    case "conservative":
      return "compare.conservative";
    default:
      return variant;
  }
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "PASS"
      ? "bg-[#30d158]"
      : status === "WARN"
      ? "bg-[#ff9f0a]"
      : status === "FAIL"
      ? "bg-[#ff453a]"
      : "bg-[#aeaeb2]";
  return <span className={`w-1.5 h-1.5 rounded-full ${color} shrink-0`} />;
}

export default function CompareView({
  versions,
  onSelect,
  onDownload,
  onNewCreation,
  onBack,
  onPublish,
  selectedVersion,
}: Props) {
  const { t } = useI18n();
  const [expandedVersion, setExpandedVersion] = useState<string | null>(null);
  const [publishingVersion, setPublishingVersion] = useState<string | null>(null);

  // Safely derive all unique quality criteria across versions
  const allCriteria = useMemo(() => {
    const nameSet = new Set<string>();
    versions.forEach((v) => {
      v.auditReport?.criteria?.forEach((c: { name: string }) => {
        nameSet.add(c.name);
      });
    });
    return Array.from(nameSet);
  }, [versions]);

  const hasMultipleVersions = versions.length >= 2;

  // Empty state
  if (versions.length === 0) {
    return (
      <div className="space-y-4 animate-slide-up">
        <div className="apple-card p-4">
          <h2 className="text-base font-semibold text-[#1d1d1f]">{t("compare.title")}</h2>
        </div>
        <div className="apple-card p-8 text-center">
          <div className="flex flex-col items-center gap-3 py-6">
            <div className="relative w-8 h-8">
              <svg className="animate-spin w-8 h-8" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="#e8e8ed" strokeWidth="3" />
                <path d="M12 2a10 10 0 0 1 10 10" stroke="#7CB342" strokeWidth="3" strokeLinecap="round" />
              </svg>
            </div>
            <p className="text-sm text-[#86868b]">{t("compare.generating")}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-slide-up">
      {/* Header */}
      <div className="apple-card p-4">
        <h2 className="text-base font-semibold text-[#1d1d1f]">
          {t(hasMultipleVersions ? "compare.title" : "compare.singleVersion")}
        </h2>
        {hasMultipleVersions && (
          <p className="text-xs text-[#86868b] mt-0.5">
            {versions.length} {t("compare.version")}
          </p>
        )}
      </div>

      {/* Version cards grid */}
      <div
        className={
          hasMultipleVersions
            ? "grid grid-cols-1 md:grid-cols-2 gap-4"
            : "grid grid-cols-1 gap-4 max-w-xl mx-auto"
        }
      >
        {versions.map((v) => {
          const isSelected = selectedVersion === v.label;
          const isExpanded = expandedVersion === v.label;
          const isOtherSelected = selectedVersion !== null && !isSelected;
          const audit = v.auditReport;
          const overallScore = audit
            ? Math.round(Math.min(audit.overall_score, 1) * 100)
            : 0;

          return (
            <div
              key={v.label}
              className={`apple-card overflow-hidden transition-all duration-300 ${
                isSelected
                  ? "ring-2 ring-[#7CB342] shadow-md"
                  : isOtherSelected
                  ? "opacity-50"
                  : "hover:shadow-sm"
              }`}
            >
              {/* Version header */}
              <div className="p-3 border-b border-[#e8e8ed] bg-[#fafafc]">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-[#1d1d1f]">
                      {v.label}
                    </h3>
                    {isSelected && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#7CB342]/10 text-[#7CB342]">
                        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                          <path d="M2 5.5L4 7.5L8 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        {t("compare.selected")}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-[#86868b]/10 text-[#86868b]">
                    {t(getVariantLabelKey(v.scriptVariant))}
                  </span>
                </div>
              </div>

              {/* Video preview area */}
              <div className="relative bg-black">
                {isExpanded ? (
                  <>
                    <video
                      src={getMediaUrl(v.videoPath)}
                      controls
                      className="w-full"
                      style={{ maxHeight: 400 }}
                      preload="metadata"
                      poster={v.thumbnailPath ? getMediaUrl(v.thumbnailPath) : undefined}
                      autoPlay
                    />
                    <button
                      onClick={() => setExpandedVersion(null)}
                      className="absolute top-2 right-2 w-7 h-7 rounded-lg bg-black/50 backdrop-blur-sm flex items-center justify-center hover:bg-black/70 transition-colors cursor-pointer"
                      title={t("compare.preview")}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round">
                        <path d="M18 6L6 18M6 6l12 12" />
                      </svg>
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => setExpandedVersion(v.label)}
                    className="w-full aspect-video flex items-center justify-center bg-gradient-to-br from-[#1d1d1f] to-[#2d2d2f] hover:from-[#2d2d2f] hover:to-[#3d3d3f] transition-all duration-200 cursor-pointer group"
                  >
                    <div className="flex flex-col items-center gap-2">
                      <div className="w-14 h-14 rounded-full bg-white/10 backdrop-blur-sm flex items-center justify-center group-hover:bg-white/20 transition-colors">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
                          <polygon points="8,5 19,12 8,19" />
                        </svg>
                      </div>
                      <span className="text-[11px] text-white/60 group-hover:text-white/80 transition-colors">
                        {t("compare.preview")}
                      </span>
                    </div>
                  </button>
                )}
              </div>

              {/* Metadata row */}
              <div className="px-3 pt-3 flex items-center gap-4 text-[11px] text-[#86868b]">
                <span className="flex items-center gap-1">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12 6 12 12 16 14" />
                  </svg>
                  {t("compare.duration")}: {formatDuration(v.duration)}
                </span>
                <span className="flex items-center gap-1">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                  </svg>
                  {t("compare.fileSize")}: {formatFileSize(v.fileSize)}
                </span>
              </div>

              {/* Quality score bar */}
              {audit && (
                <div className="px-3 pt-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-semibold text-[#86868b] uppercase tracking-wider">
                      {t("compare.quality")}
                    </span>
                    <span
                      className={`text-[11px] font-semibold ${
                        audit.overall_status === "PASS"
                          ? "text-[#30d158]"
                          : audit.overall_status === "WARN"
                          ? "text-[#ff9f0a]"
                          : "text-[#ff453a]"
                      }`}
                    >
                      {overallScore}%
                    </span>
                  </div>
                  <div className="h-1.5 w-full bg-[#f5f5f7] rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ease-out ${
                        audit.overall_status === "PASS"
                          ? "bg-[#30d158]"
                          : audit.overall_status === "WARN"
                          ? "bg-[#ff9f0a]"
                          : "bg-[#ff453a]"
                      }`}
                      style={{ width: `${overallScore}%` }}
                    />
                  </div>
                  {/* Mini criteria row */}
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    {audit.criteria?.slice(0, 4).map((c, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full bg-[#f5f5f7]"
                      >
                        <StatusDot status={c.status} />
                        {c.score >= 0 ? `${Math.round(c.score * 100)}%` : ""}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="p-3 space-y-2">
                {isSelected ? (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => onDownload(v.label)}
                      className="flex-1 apple-btn apple-btn-primary text-xs py-2 px-3 cursor-pointer"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                      {t("compare.download")}
                    </button>
                    <button
                      onClick={async () => {
                        setPublishingVersion(v.label);
                        try {
                          await onPublish(v.label);
                        } finally {
                          setPublishingVersion(null);
                        }
                      }}
                      disabled={publishingVersion === v.label}
                      className="flex-1 apple-btn apple-btn-primary text-xs py-2 px-3 cursor-pointer disabled:opacity-50"
                    >
                      {publishingVersion === v.label ? (
                        <span className="inline-flex items-center gap-1">
                          <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                          </svg>
                          {t("compare.publishing")}
                        </span>
                      ) : t("compare.publish")}
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => onSelect(v.label)}
                    className="w-full apple-btn text-xs py-2 px-3 border border-[#e8e8ed] hover:bg-[#f5f5f7] transition-colors cursor-pointer"
                  >
                    {t("compare.selectThis")}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Quality comparison table (2+ versions only) */}
      {hasMultipleVersions && allCriteria.length > 0 && (
        <div className="apple-card p-4">
          <h3 className="text-[11px] font-semibold text-[#86868b] uppercase tracking-wider mb-3">
            {t("compare.qualityComparison")}
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-[#e8e8ed]">
                  <th className="text-left py-2 pr-4 text-[#86868b] font-medium">
                    {t("compare.criteria")}
                  </th>
                  {versions.map((v) => (
                    <th
                      key={v.label}
                      className={`text-center py-2 px-3 font-medium ${
                        selectedVersion === v.label ? "text-[#7CB342]" : "text-[#86868b]"
                      }`}
                    >
                      {v.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allCriteria.map((name, rowIdx) => (
                  <tr
                    key={name}
                    className={rowIdx < allCriteria.length - 1 ? "border-b border-[#e8e8ed]/50" : ""}
                  >
                    <td className="py-2 pr-4 text-[#1d1d1f]">{name}</td>
                    {versions.map((v) => {
                      const criterion = v.auditReport?.criteria?.find(
                        (c: { name: string }) => c.name === name
                      );
                      if (!criterion) {
                        return (
                          <td key={v.label} className="text-center py-2 px-3 text-[#aeaeb2]">
                            —
                          </td>
                        );
                      }
                      const scorePct = Math.round(criterion.score * 100);
                      const isPass = criterion.status === "PASS";
                      const isWarn = criterion.status === "WARN";
                      return (
                        <td
                          key={v.label}
                          className={`text-center py-2 px-3 font-medium ${
                            isPass
                              ? "text-[#30d158]"
                              : isWarn
                              ? "text-[#ff9f0a]"
                              : "text-[#ff453a]"
                          }`}
                        >
                          <div className="flex items-center justify-center gap-1">
                            <span className="tabular-nums">{scorePct}%</span>
                            <StatusDot status={criterion.status} />
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Bottom action bar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <button
          onClick={onBack}
          className="text-xs text-[#86868b] px-4 py-2 rounded-lg hover:bg-[#e8e8ed]/50 transition-colors cursor-pointer"
        >
          <span className="inline-flex items-center gap-1">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
            {t("compare.backToGates")}
          </span>
        </button>
        <div className="flex items-center gap-2">
          {selectedVersion && (
            <button
              onClick={() => onDownload(selectedVersion)}
              className="apple-btn apple-btn-primary text-xs px-5 py-2 cursor-pointer"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              {t("compare.downloadSelected")}
            </button>
          )}
          <button
            onClick={onNewCreation}
            className="apple-btn px-5 py-2 text-xs border border-[#e8e8ed] hover:bg-[#f5f5f7] transition-colors cursor-pointer"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="16" />
              <line x1="8" y1="12" x2="16" y2="12" />
            </svg>
            {t("compare.newCreation")}
          </button>
        </div>
      </div>
    </div>
  );
}
