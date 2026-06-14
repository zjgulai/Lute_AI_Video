"use client";

import { useI18n } from "@/i18n/I18nProvider";

type UnknownRecord = Record<string, unknown>;

export type ProductionJobRecordView = {
  job_id: string;
  provider: string;
  model: string;
  scenario?: string;
  step_name?: string;
  prompt_hash?: string;
  status: string;
  artifact_paths: Record<string, string>;
  delivery_accepted: boolean;
  publish_allowed: boolean;
  failure_reason?: string;
  blocked_reasons: string[];
};

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function stringMap(value: unknown): Record<string, string> {
  const record = asRecord(value);
  return Object.fromEntries(
    Object.entries(record).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  );
}

function normalizeJob(value: unknown): ProductionJobRecordView | null {
  const record = asRecord(value);
  const spec = asRecord(record.spec);
  const jobId = stringValue(record.job_id || spec.job_id);
  if (!jobId) return null;

  return {
    job_id: jobId,
    provider: stringValue(spec.provider || record.provider, "unknown"),
    model: stringValue(spec.model || record.model, "unknown"),
    scenario: stringValue(spec.scenario || record.scenario),
    step_name: stringValue(spec.step_name || record.step_name),
    prompt_hash: stringValue(spec.prompt_hash || record.prompt_hash),
    status: stringValue(record.status, "prepared"),
    artifact_paths: stringMap(record.artifact_paths),
    delivery_accepted: record.delivery_accepted === true,
    publish_allowed: record.publish_allowed === true,
    failure_reason: stringValue(record.failure_reason),
    blocked_reasons: stringList(record.blocked_reasons),
  };
}

export function extractProductionJobRecords(state: Record<string, unknown>): ProductionJobRecordView[] {
  const ledger = asRecord(state.production_job_ledger ?? state.job_ledger);
  const candidates = [
    ledger.records,
    ledger.jobs,
    state.production_jobs,
    state.media_jobs,
    state.production_job_records,
  ];

  for (const candidate of candidates) {
    if (!Array.isArray(candidate)) continue;
    return candidate.map(normalizeJob).filter((job): job is ProductionJobRecordView => job !== null);
  }

  return [];
}

function statusClasses(status: string) {
  switch (status) {
    case "succeeded":
      return "border-[rgba(120,175,140,0.24)] bg-[rgba(120,175,140,0.10)] text-[var(--jade-accent)]";
    case "failed":
    case "blocked":
      return "border-[rgba(208,78,90,0.24)] bg-[rgba(208,78,90,0.10)] text-[var(--crimson-mist)]";
    case "submitted":
      return "border-[rgba(122,150,187,0.24)] bg-[rgba(122,150,187,0.10)] text-[var(--cinema-azure)]";
    default:
      return "border-[rgba(220,190,120,0.24)] bg-[rgba(220,190,120,0.10)] text-[var(--gold-foil)]";
  }
}

function shortHash(value?: string) {
  if (!value) return "";
  return value.length > 28 ? `${value.slice(0, 18)}...${value.slice(-8)}` : value;
}

export default function ProductionJobLedgerViewer({ records }: { records: ProductionJobRecordView[] }) {
  const { t } = useI18n();
  if (records.length === 0) return null;

  return (
    <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13px] font-semibold text-[var(--text-h1)]">{t("jobLedger.title")}</h3>
            <span className="rounded-full border border-[rgba(122,150,187,0.24)] bg-[rgba(122,150,187,0.10)] px-2 py-0.5 text-[11px] font-semibold text-[var(--cinema-azure)]">
              {t("jobLedger.readOnly")}
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
            {records.length} {t("jobLedger.jobs")}
          </p>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        {records.map((record) => {
          const publishActuallyAllowed = record.publish_allowed && record.delivery_accepted;
          return (
            <article key={record.job_id} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-card)] p-2.5">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-mono text-[12px] font-semibold text-[var(--text-h1)]" title={record.job_id}>
                    {record.job_id}
                  </p>
                  <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                    {record.scenario || "-"} / {record.step_name || "-"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusClasses(record.status)}`}>
                    {record.status}
                  </span>
                  <span className="rounded-full border border-[var(--border-default)] bg-[var(--bg-panel)] px-2 py-0.5 text-[11px] font-semibold text-[var(--text-muted)]">
                    {publishActuallyAllowed ? t("jobLedger.publishAllowed") : t("jobLedger.publishLocked")}
                  </span>
                </div>
              </div>

              <dl className="mt-2 grid gap-1.5 text-[12px] sm:grid-cols-2">
                <Field label={t("jobLedger.provider")} value={record.provider} />
                <Field label={t("jobLedger.model")} value={record.model} />
                {record.prompt_hash && (
                  <Field label={t("jobLedger.promptHash")} value={shortHash(record.prompt_hash)} title={record.prompt_hash} />
                )}
                <Field
                  label={t("jobLedger.delivery")}
                  value={record.delivery_accepted ? t("jobLedger.deliveryAccepted") : t("jobLedger.deliveryPending")}
                />
              </dl>

              {record.status === "succeeded" && !record.delivery_accepted && (
                <p className="mt-2 rounded-md border border-[rgba(220,190,120,0.22)] bg-[rgba(220,190,120,0.07)] px-2 py-1 text-[12px] text-[var(--gold-foil)]">
                  {t("jobLedger.generationBoundary")}
                </p>
              )}

              <ArtifactList artifacts={record.artifact_paths} />

              {(record.failure_reason || record.blocked_reasons.length > 0) && (
                <div className="mt-2 rounded-md border border-[rgba(208,78,90,0.20)] bg-[rgba(208,78,90,0.06)] px-2 py-1">
                  {[record.failure_reason, ...record.blocked_reasons].filter(Boolean).map((reason) => (
                    <p key={reason} className="text-[12px] text-[var(--crimson-mist)]">
                      {reason}
                    </p>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function Field({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">{label}</dt>
      <dd className="truncate text-[12px] font-medium text-[var(--text-h1)]" title={title || value}>
        {value}
      </dd>
    </div>
  );
}

function ArtifactList({ artifacts }: { artifacts: Record<string, string> }) {
  const { t } = useI18n();
  const entries = Object.entries(artifacts);

  return (
    <div className="mt-2 rounded-md border border-[var(--border-default)] bg-[var(--bg-panel)] px-2 py-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">
        {t("jobLedger.artifacts")}
      </p>
      {entries.length === 0 ? (
        <p className="mt-1 text-[12px] text-[var(--text-muted)]">{t("jobLedger.noArtifacts")}</p>
      ) : (
        <div className="mt-1 flex flex-wrap gap-1">
          {entries.map(([kind, ref]) => (
            <span
              key={`${kind}-${ref}`}
              className="max-w-[220px] truncate rounded-md bg-[var(--bg-card)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-body)]"
              title={`${kind}: ${ref}`}
            >
              {kind}: {ref}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
