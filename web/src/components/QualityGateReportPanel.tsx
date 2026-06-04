"use client";

import { useI18n } from "@/i18n/I18nProvider";

type UnknownRecord = Record<string, unknown>;

export type GateDecisionView = {
  status?: string;
  publish_allowed?: boolean;
  requires_human_review?: boolean;
  blocking_failure_count?: number;
  advisory_warning_count?: number;
  reasons?: unknown;
  repair_plan_id?: string | null;
};

export type RepairActionView = {
  check?: string;
  severity?: string;
  evidence_ref?: string | null;
  recommendation?: string;
  required_before?: string;
};

export type RepairPlanView = {
  plan_id?: string;
  actions?: unknown;
};

export type QualityGateReportView = {
  gate_decision: GateDecisionView;
  repair_plan?: RepairPlanView | null;
};

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function repairActions(plan: RepairPlanView | null | undefined): RepairActionView[] {
  const actions = Array.isArray(plan?.actions) ? plan.actions : [];
  return actions
    .map((item) => asRecord(item))
    .filter((item) => typeof item.check === "string")
    .map((item) => ({
      check: String(item.check),
      severity: typeof item.severity === "string" ? item.severity : "blocker",
      evidence_ref: typeof item.evidence_ref === "string" ? item.evidence_ref : null,
      recommendation: typeof item.recommendation === "string" ? item.recommendation : "",
      required_before: typeof item.required_before === "string" ? item.required_before : "delivery_acceptance",
    }));
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function normalizeGateDecision(value: UnknownRecord): GateDecisionView {
  return {
    status: typeof value.status === "string" ? value.status : undefined,
    publish_allowed: typeof value.publish_allowed === "boolean" ? value.publish_allowed : undefined,
    requires_human_review:
      typeof value.requires_human_review === "boolean" ? value.requires_human_review : undefined,
    blocking_failure_count: numberValue(value.blocking_failure_count),
    advisory_warning_count: numberValue(value.advisory_warning_count),
    reasons: Array.isArray(value.reasons) ? value.reasons : undefined,
    repair_plan_id: typeof value.repair_plan_id === "string" ? value.repair_plan_id : null,
  };
}

function normalizeRepairPlan(value: UnknownRecord): RepairPlanView | null {
  if (Object.keys(value).length === 0) return null;
  return {
    plan_id: typeof value.plan_id === "string" ? value.plan_id : undefined,
    actions: Array.isArray(value.actions) ? value.actions : undefined,
  };
}

export function extractQualityGateReport(state: Record<string, unknown>): QualityGateReportView | null {
  const directGate = asRecord(state.gate_decision);
  const directRepair = asRecord(state.repair_plan);
  const report = asRecord(state.quality_gate_report ?? state.commercial_quality_gate ?? state.quality_gate);
  const gateDecision = Object.keys(directGate).length > 0 ? directGate : asRecord(report.gate_decision);

  if (Object.keys(gateDecision).length === 0) return null;

  const repairPlan = Object.keys(directRepair).length > 0 ? directRepair : asRecord(report.repair_plan);
  return {
    gate_decision: normalizeGateDecision(gateDecision),
    repair_plan: normalizeRepairPlan(repairPlan),
  };
}

function statusClasses(status: string) {
  switch (status) {
    case "accepted":
      return "border-[rgba(120,175,140,0.24)] bg-[rgba(120,175,140,0.10)] text-[var(--jade-accent)]";
    case "review_required":
      return "border-[rgba(220,190,120,0.26)] bg-[rgba(220,190,120,0.10)] text-[var(--gold-foil)]";
    default:
      return "border-[rgba(208,78,90,0.24)] bg-[rgba(208,78,90,0.10)] text-[var(--crimson-mist)]";
  }
}

function severityClasses(severity: string) {
  return severity === "advisory"
    ? "border-[rgba(220,190,120,0.22)] bg-[rgba(220,190,120,0.07)]"
    : "border-[rgba(208,78,90,0.22)] bg-[rgba(208,78,90,0.07)]";
}

export default function QualityGateReportPanel({ report }: { report: QualityGateReportView }) {
  const { t } = useI18n();
  const decision = report.gate_decision;
  const status = typeof decision.status === "string" ? decision.status : "blocked";
  const actions = repairActions(report.repair_plan);
  const blockers = actions.filter((action) => action.severity !== "advisory");
  const advisories = actions.filter((action) => action.severity === "advisory");
  const reasons = stringList(decision.reasons);
  const publishAllowed = decision.publish_allowed === true;
  const requiresReview = decision.requires_human_review !== false;

  return (
    <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13px] font-semibold text-[var(--text-h1)]">{t("qualityGate.title")}</h3>
            <span className="rounded-full border border-[rgba(122,150,187,0.24)] bg-[rgba(122,150,187,0.10)] px-2 py-0.5 text-[11px] font-semibold text-[var(--cinema-azure)]">
              {t("qualityGate.readOnly")}
            </span>
          </div>
          {report.repair_plan?.plan_id && (
            <p className="mt-0.5 font-mono text-[11px] text-[var(--text-muted)]">{report.repair_plan.plan_id}</p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusClasses(status)}`}>
            {status}
          </span>
          <span className="rounded-full border border-[var(--border-default)] bg-[var(--bg-card)] px-2 py-0.5 text-[11px] font-semibold text-[var(--text-muted)]">
            {publishAllowed ? t("qualityGate.publishAllowed") : t("qualityGate.publishLocked")}
          </span>
          {requiresReview && (
            <span className="rounded-full border border-[rgba(220,190,120,0.24)] bg-[rgba(220,190,120,0.08)] px-2 py-0.5 text-[11px] font-semibold text-[var(--gold-foil)]">
              {t("qualityGate.humanReview")}
            </span>
          )}
        </div>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-2">
        <ActionGroup title={t("qualityGate.blocking")} actions={blockers} emptyText={t("qualityGate.noRepairActions")} />
        <ActionGroup title={t("qualityGate.advisory")} actions={advisories} emptyText={t("qualityGate.noRepairActions")} />
      </div>

      {reasons.length > 0 && (
        <div className="mt-3 rounded-lg border border-[var(--border-default)] bg-[var(--bg-card)] p-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">
            {t("qualityGate.reasons")}
          </p>
          <ul className="mt-1 space-y-1">
            {reasons.map((reason) => (
              <li key={reason} className="text-[12px] text-[var(--text-body)]">
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function ActionGroup({ title, actions, emptyText }: { title: string; actions: RepairActionView[]; emptyText: string }) {
  const { t } = useI18n();
  return (
    <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-card)] p-2">
      <p className="text-[11px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">{title}</p>
      {actions.length === 0 ? (
        <p className="mt-1 text-[12px] text-[var(--text-muted)]">{emptyText}</p>
      ) : (
        <div className="mt-1 space-y-1.5">
          {actions.map((action) => (
            <div key={`${action.check}-${action.evidence_ref ?? ""}`} className={`rounded-md border p-2 ${severityClasses(action.severity ?? "blocker")}`}>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-mono text-[11px] font-semibold text-[var(--text-h1)]">{action.check}</span>
                <span className="text-[11px] text-[var(--text-muted)]">
                  {t("qualityGate.requiredBefore")}: {action.required_before}
                </span>
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
