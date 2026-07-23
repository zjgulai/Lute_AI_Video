"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import {
  downloadTransparencyPackage,
  getTransparencyDisclosure,
  type TransparencyDisclosure,
  type TransparencyResourceType,
} from "./api";

interface Props {
  resourceType?: TransparencyResourceType;
  resourceId?: string;
}

type StoredInspection =
  | { resourceKey: string; status: "blocked"; disclosure?: never }
  | { resourceKey: string; status: "verified"; disclosure: TransparencyDisclosure };

type InspectionState =
  | { status: "unavailable" | "loading" | "blocked"; disclosure?: never }
  | { status: "verified"; disclosure: TransparencyDisclosure };

function scopeMessage(
  disclosure: TransparencyDisclosure,
  t: (key: string) => string,
): string {
  if (disclosure.verification_scope === "local_reader_only") {
    return t("transparency.localReader");
  }
  if (disclosure.verification_scope === "unsigned_pending_review") {
    return t("transparency.unsignedPending");
  }
  return t("transparency.provenanceOnly");
}

export default function TransparencyStatus({ resourceType, resourceId }: Props) {
  const { t } = useI18n();
  const [inspection, setInspection] = useState<StoredInspection | null>(null);
  const resourceKey = resourceType && resourceId ? `${resourceType}:${resourceId}` : null;
  const state: InspectionState = resourceKey === null
    ? { status: "unavailable" }
    : inspection?.resourceKey === resourceKey
      ? inspection
      : { status: "loading" };

  useEffect(() => {
    if (!resourceType || !resourceId || !resourceKey) return;
    let active = true;
    let controller: AbortController | null = null;
    queueMicrotask(() => {
      if (!active) return;
      controller = new AbortController();
      getTransparencyDisclosure(resourceType, resourceId, { signal: controller.signal })
        .then((disclosure) => {
          if (active && !controller?.signal.aborted) {
            setInspection({ resourceKey, status: "verified", disclosure });
          }
        })
        .catch(() => {
          if (active && !controller?.signal.aborted) {
            setInspection({ resourceKey, status: "blocked" });
          }
        });
    });
    return () => {
      active = false;
      controller?.abort();
    };
  }, [resourceId, resourceKey, resourceType]);

  const handleDownload = async () => {
    if (state.status !== "verified" || !resourceType || !resourceId) return;
    try {
      await downloadTransparencyPackage(resourceType, resourceId);
    } catch {
      if (resourceKey) setInspection({ resourceKey, status: "blocked" });
    }
  };

  return (
    <section
      role="status"
      aria-live="polite"
      className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-panel)] px-3 py-2.5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs font-semibold text-[var(--text-h1)]">
            {t("transparency.aiGenerated")}
          </p>
          <p className="mt-0.5 text-[12px] text-[var(--text-body)]">
            {state.status === "loading"
              ? t("transparency.verifying")
              : state.status === "verified"
                ? scopeMessage(state.disclosure, t)
                : t("transparency.unavailable")}
          </p>
          {state.status === "verified" && (
            <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">
              {t("transparency.notIndependent")}
            </p>
          )}
        </div>
        {state.status === "verified" && state.disclosure.package_available && (
          <button
            type="button"
            data-transparency-package
            onClick={handleDownload}
            className="apple-btn px-3 py-1.5 text-xs"
          >
            {t("transparency.downloadPackage")}
          </button>
        )}
      </div>
    </section>
  );
}
