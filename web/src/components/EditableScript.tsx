"use client";

import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  script: any;
  onChange: (updated: any) => void;
}

export default function EditableScript({ script, onChange }: Props) {
  const { t } = useI18n();
  const handleSegmentChange = (index: number, field: string, value: string) => {
    const updatedSegments = (script.segments || []).map((seg: any, i: number) =>
      i === index ? { ...seg, [field]: value } : seg
    );
    onChange({ ...script, segments: updatedSegments });
  };

  return (
    <div className="apple-card p-3 bg-[var(--bg-card)] space-y-3">
      {(script.segments || []).map((seg: any, i: number) => (
        <div key={i} className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold text-[var(--fortune-red)] uppercase">{seg.segment_type}</span>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              {seg.start_time ?? 0}s — {seg.end_time ?? 0}s
            </span>
          </div>
          <div>
            <label className="block text-[10px] font-medium text-[var(--text-muted)] mb-0.5">{t("editors.voiceover")}</label>
            <textarea
              value={seg.voiceover || ""}
              onChange={(e) => handleSegmentChange(i, "voiceover", e.target.value)}
              className="apple-input text-xs w-full resize-none"
              rows={2}
              placeholder={t("editors.voiceover")}
            />
          </div>
          <div>
            <label className="block text-[10px] font-medium text-[var(--text-muted)] mb-0.5">{t("editors.visual_desc")}</label>
            <textarea
              value={seg.visual_description || ""}
              onChange={(e) => handleSegmentChange(i, "visual_description", e.target.value)}
              className="apple-input text-xs w-full resize-none"
              rows={2}
              placeholder={t("editors.visual_desc")}
            />
          </div>
          {i < (script.segments || []).length - 1 && (
            <div className="border-t border-[rgba(215,92,112,0.18)] pt-2" />
          )}
        </div>
      ))}
    </div>
  );
}
