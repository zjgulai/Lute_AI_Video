"use client";

import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({ page, pageSize, total, onPageChange }: Props) {
  const { t } = useI18n();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const canPrev = safePage > 1;
  const canNext = safePage < totalPages;

  if (total <= pageSize) return null;

  const startIdx = (safePage - 1) * pageSize + 1;
  const endIdx = Math.min(safePage * pageSize, total);

  return (
    <div className="flex items-center justify-between gap-3 py-3">
      <span className="text-[12px] text-[var(--text-muted)] tabular-nums">
        {t("pagination.range")
          .replace("{start}", String(startIdx))
          .replace("{end}", String(endIdx))
          .replace("{total}", String(total))}
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => canPrev && onPageChange(safePage - 1)}
          disabled={!canPrev}
          aria-label={t("pagination.prev")}
          className="flex items-center justify-center w-8 h-8 rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-h1)] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <CaretLeft size={14} weight="bold" />
        </button>
        <span className="text-[12px] font-medium text-[var(--text-h1)] min-w-[5rem] text-center tabular-nums">
          {t("pagination.page")
            .replace("{page}", String(safePage))
            .replace("{totalPages}", String(totalPages))}
        </span>
        <button
          type="button"
          onClick={() => canNext && onPageChange(safePage + 1)}
          disabled={!canNext}
          aria-label={t("pagination.next")}
          className="flex items-center justify-center w-8 h-8 rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-h1)] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <CaretRight size={14} weight="bold" />
        </button>
      </div>
    </div>
  );
}
