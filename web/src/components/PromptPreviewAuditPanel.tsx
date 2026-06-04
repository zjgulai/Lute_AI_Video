"use client";

import { useI18n } from "@/i18n/I18nProvider";

type UnknownRecord = Record<string, unknown>;

type RepairActionView = {
  check: string;
  severity: string;
  evidence_ref?: string | null;
  recommendation?: string;
  required_before?: string;
};

export type PromptPreviewAuditView = {
  audit_bundle_id?: string;
  compile_id?: string;
  scenario?: string;
  step?: string;
  provider: string;
  model: string;
  prompt_hash?: string | null;
  decision: string;
  evidence_level: string;
  gate_status: string;
  requires_human_review: boolean;
  blocking_failure_count: number;
  advisory_warning_count: number;
  forbidden_claims: string[];
  repair_actions: RepairActionView[];
  delivery_accepted: boolean;
  publish_allowed: boolean;
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

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function boolValue(value: unknown): boolean {
  return value === true;
}

function repairActions(value: unknown): RepairActionView[] {
  const repairPlan = asRecord(value);
  const actions = Array.isArray(repairPlan.actions) ? repairPlan.actions : [];
  return actions
    .map((item) => asRecord(item))
    .filter((item) => typeof item.check === "string")
    .map((item) => ({
      check: String(item.check),
      severity: stringValue(item.severity, "blocker"),
      evidence_ref: typeof item.evidence_ref === "string" ? item.evidence_ref : null,
      recommendation: stringValue(item.recommendation),
      required_before: stringValue(item.required_before, "human_review"),
    }));
}

export function normalizePromptPreviewAuditBundle(value: unknown): PromptPreviewAuditView | null {
  const record = asRecord(value);
  const boundary = asRecord(record.evidence_boundary);
  const gate = asRecord(record.gate_decision);
  if (Object.keys(boundary).length === 0 && Object.keys(gate).length === 0) return null;

  const preview = asRecord(record.preview);
  const actions = repairActions(record.repair_plan);
  const blockerCount =
    numberValue(gate.blocking_failure_count) ?? actions.filter((action) => action.severity !== "advisory").length;
  const advisoryCount =
    numberValue(gate.advisory_warning_count) ?? actions.filter((action) => action.severity === "advisory").length;
  const decision = stringValue(boundary.decision, "blocked");

  return {
    audit_bundle_id: stringValue(record.audit_bundle_id),
    compile_id: stringValue(record.compile_id || preview.compile_id),
    scenario: stringValue(record.scenario || preview.scenario),
    step: stringValue(record.step || preview.step),
    provider: stringValue(record.provider || preview.provider, "unknown"),
    model: stringValue(record.model || preview.model, "unknown"),
    prompt_hash: typeof record.prompt_hash === "string" ? record.prompt_hash : null,
    decision,
    evidence_level: stringValue(boundary.evidence_level, "L2-fixture-or-dry-run"),
    gate_status: stringValue(gate.status, decision === "allowed-with-label" ? "review_required" : "blocked"),
    requires_human_review: gate.requires_human_review !== false,
    blocking_failure_count: blockerCount,
    advisory_warning_count: advisoryCount,
    forbidden_claims: stringList(boundary.forbidden_claims),
    repair_actions: actions,
    delivery_accepted: boolValue(record.delivery_accepted),
    publish_allowed: boolValue(record.publish_allowed),
  };
}

function statusClasses(status: string) {
  switch (status) {
    case "allowed-with-label":
    case "accepted":
    case "review_required":
      return "border-[rgba(220,190,120,0.24)] bg-[rgba(220,190,120,0.10)] text-[var(--gold-foil)]";
    default:
      return "border-[rgba(208,78,90,0.24)] bg-[rgba(208,78,90,0.10)] text-[var(--crimson-mist)]";
  }
}

function shortHash(value?: string | null) {
  if (!value) return "";
  return value.length > 34 ? `${value.slice(0, 20)}...${value.slice(-10)}` : value;
}

export default function PromptPreviewAuditPanel({ bundle }: { bundle: unknown }) {
  const { t } = useI18n();
  const audit = normalizePromptPreviewAuditBundle(bundle);
  if (!audit) return null;

  const blocked = audit.decision === "blocked" || audit.gate_status === "blocked";
  const publishActuallyAllowed = audit.publish_allowed && audit.delivery_accepted;

  return (
    <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13px] font-semibold text-[var(--text-h1)]">{t("promptPreviewAudit.title")}</h3>
            <span className="rounded-full border border-[rgba(122,150,187,0.24)] bg-[rgba(122,150,187,0.10)] px-2 py-0.5 text-[11px] font-semibold text-[var(--cinema-azure)]">
              {t("promptPreviewAudit.readOnly")}
            </span>
            <span className="rounded-full border border-[var(--border-default)] bg-[var(--bg-card)] px-2 py-0.5 font-mono text-[11px] text-[var(--text-muted)]">
              {audit.evidence_level}
            </span>
          </div>
          {audit.audit_bundle_id && (
            <p className="mt-0.5 truncate font-mono text-[11px] text-[var(--text-muted)]" title={audit.audit_bundle_id}>
              {audit.audit_bundle_id}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusClasses(audit.decision)}`}>
            {audit.decision}
          </span>
          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusClasses(audit.gate_status)}`}>
            {audit.gate_status}
          </span>
        </div>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-4">
        <Metric label={t("promptPreviewAudit.provider")} value={audit.provider} />
        <Metric label={t("promptPreviewAudit.model")} value={audit.model} />
        <Metric label={t("promptPreviewAudit.step")} value={audit.step || "-"} />
        <Metric
          label={t("promptPreviewAudit.promptHash")}
          value={shortHash(audit.prompt_hash) || "-"}
          title={audit.prompt_hash || undefined}
        />
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {audit.requires_human_review && (
          <span className="rounded-full border border-[rgba(220,190,120,0.24)] bg-[rgba(220,190,120,0.08)] px-2 py-0.5 text-[11px] font-semibold text-[var(--gold-foil)]">
            {t("promptPreviewAudit.humanReview")}
          </span>
        )}
        <span className="rounded-full border border-[var(--border-default)] bg-[var(--bg-card)] px-2 py-0.5 text-[11px] font-semibold text-[var(--text-muted)]">
          {audit.delivery_accepted ? t("promptPreviewAudit.deliveryAccepted") : t("promptPreviewAudit.deliveryLocked")}
        </span>
        <span className="rounded-full border border-[var(--border-default)] bg-[var(--bg-card)] px-2 py-0.5 text-[11px] font-semibold text-[var(--text-muted)]">
          {publishActuallyAllowed ? t("promptPreviewAudit.publishAllowed") : t("promptPreviewAudit.publishLocked")}
        </span>
      </div>

      {blocked && (
        <div className="mt-3 grid gap-2 md:grid-cols-[160px_1fr]">
          <div className="rounded-lg border border-[rgba(208,78,90,0.22)] bg-[rgba(208,78,90,0.06)] p-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">
              {t("promptPreviewAudit.blockers")}
            </p>
            <p className="mt-1 text-[20px] font-semibold text-[var(--crimson-mist)]">{audit.blocking_failure_count}</p>
            <p className="text-[11px] text-[var(--text-muted)]">
              {t("promptPreviewAudit.advisory")}: {audit.advisory_warning_count}
            </p>
          </div>
          <RepairActionList actions={audit.repair_actions} />
        </div>
      )}

      <ForbiddenClaimList claims={audit.forbidden_claims} />
    </section>
  );
}

function Metric({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="min-w-0 rounded-md border border-[var(--border-default)] bg-[var(--bg-card)] px-2 py-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">{label}</p>
      <p className="truncate font-mono text-[12px] font-medium text-[var(--text-h1)]" title={title || value}>
        {value}
      </p>
    </div>
  );
}

function RepairActionList({ actions }: { actions: RepairActionView[] }) {
  const { t } = useI18n();
  return (
    <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-card)] p-2">
      <p className="text-[11px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">
        {t("promptPreviewAudit.repairActions")}
      </p>
      {actions.length === 0 ? (
        <p className="mt-1 text-[12px] text-[var(--text-muted)]">{t("promptPreviewAudit.noRepairActions")}</p>
      ) : (
        <div className="mt-1 space-y-1.5">
          {actions.map((action, index) => (
            <div
              key={`${action.check}-${index}`}
              className="rounded-md border border-[rgba(208,78,90,0.18)] bg-[rgba(208,78,90,0.05)] p-2"
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-mono text-[11px] font-semibold text-[var(--text-h1)]">{action.check}</span>
                <span className="text-[11px] text-[var(--text-muted)]">{action.required_before}</span>
              </div>
              {action.recommendation && (
                <p className="mt-1 text-[12px] leading-relaxed text-[var(--text-body)]">{action.recommendation}</p>
              )}
              {action.evidence_ref && (
                <p className="mt-1 truncate font-mono text-[11px] text-[var(--text-muted)]" title={action.evidence_ref}>
                  {action.evidence_ref}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ForbiddenClaimList({ claims }: { claims: string[] }) {
  const { t } = useI18n();
  return (
    <div className="mt-3 rounded-lg border border-[var(--border-default)] bg-[var(--bg-card)] p-2">
      <p className="text-[11px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">
        {t("promptPreviewAudit.forbiddenClaims")}
      </p>
      {claims.length === 0 ? (
        <p className="mt-1 text-[12px] text-[var(--text-muted)]">{t("promptPreviewAudit.noForbiddenClaims")}</p>
      ) : (
        <div className="mt-1 flex flex-wrap gap-1">
          {claims.map((claim) => (
            <span
              key={claim}
              className="max-w-[220px] truncate rounded-md bg-[var(--bg-panel)] px-1.5 py-0.5 text-[11px] text-[var(--text-body)]"
              title={claim}
            >
              {claim}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
