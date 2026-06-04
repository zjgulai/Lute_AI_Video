"use client";

import { useI18n } from "@/i18n/I18nProvider";

type UnknownRecord = Record<string, unknown>;
type DiffStatus = "absent" | "scenario_mismatch" | "matching" | "drift";

type RefKey = "bundle_refs" | "toolbox_refs" | "contract_refs" | "gate_checks" | "source_token_ids";

const REF_GROUPS: Array<{ key: RefKey; labelKey: string }> = [
  { key: "bundle_refs", labelKey: "commercialInjection.bundle" },
  { key: "toolbox_refs", labelKey: "commercialInjection.toolbox" },
  { key: "contract_refs", labelKey: "commercialInjection.contract" },
  { key: "gate_checks", labelKey: "commercialInjection.gate" },
  { key: "source_token_ids", labelKey: "commercialInjection.tokens" },
];

export type ScenarioInjectionDiffRow = {
  key: RefKey;
  labelKey: string;
  planned: string[];
  current: string[];
  missing: string[];
  extra: string[];
};

export type ScenarioInjectionDiffView = {
  status: DiffStatus;
  scenario?: string;
  planScenario?: string;
  currentStep?: string;
  rows: ScenarioInjectionDiffRow[];
};

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function extractPlan(state: UnknownRecord): UnknownRecord {
  const config = asRecord(state.config);
  const meta = asRecord(state.meta);
  return asRecord(state.commercial_injection_plan ?? config.commercial_injection_plan ?? meta.commercial_injection_plan);
}

function deriveCurrentStep(state: UnknownRecord, plan: UnknownRecord): string | undefined {
  const explicit = stringValue(state.current_step);
  if (explicit) return explicit;

  const steps = asRecord(state.steps);
  for (const [stepName, stepData] of Object.entries(steps)) {
    if (asRecord(stepData).status !== "done") return stepName;
  }

  const planSteps = Array.isArray(plan.steps) ? plan.steps : [];
  const firstPlannedStep = asRecord(planSteps[0]);
  return stringValue(firstPlannedStep.step);
}

function findPlannedStep(plan: UnknownRecord, currentStep?: string): UnknownRecord {
  const planSteps = Array.isArray(plan.steps) ? plan.steps.map(asRecord) : [];
  return planSteps.find((step) => stringValue(step.step) === currentStep) ?? asRecord(planSteps[0]);
}

function extractCurrentInjection(state: UnknownRecord, currentStep?: string): UnknownRecord {
  const current = asRecord(state.current_step_injection);
  if (Object.keys(current).length > 0) return current;
  if (!currentStep) return {};
  return asRecord(asRecord(asRecord(state.steps)[currentStep]).commercial_injection);
}

function refDiff(planned: string[], current: string[]) {
  const currentSet = new Set(current);
  const plannedSet = new Set(planned);
  return {
    missing: planned.filter((item) => !currentSet.has(item)),
    extra: current.filter((item) => !plannedSet.has(item)),
  };
}

export function buildScenarioInjectionDiff(state: Record<string, unknown>): ScenarioInjectionDiffView {
  const plan = extractPlan(state);
  if (Object.keys(plan).length === 0) {
    return { status: "absent", rows: [] };
  }

  const config = asRecord(state.config);
  const planScenario = stringValue(plan.scenario);
  const scenario = stringValue(state.scenario ?? state.scenario_id ?? config.scenario);
  const currentStep = deriveCurrentStep(state, plan);
  const plannedStep = findPlannedStep(plan, currentStep);
  const currentInjection = extractCurrentInjection(state, currentStep);

  const rows = REF_GROUPS.map((group) => {
    const planned = stringList(plannedStep[group.key]);
    const current = stringList(currentInjection[group.key]);
    const diff = refDiff(planned, current);
    return {
      key: group.key,
      labelKey: group.labelKey,
      planned,
      current,
      missing: diff.missing,
      extra: diff.extra,
    };
  });

  if (planScenario && scenario && planScenario !== scenario) {
    return { status: "scenario_mismatch", scenario, planScenario, currentStep, rows };
  }

  const hasDrift = rows.some((row) => row.missing.length > 0 || row.extra.length > 0);
  return {
    status: hasDrift ? "drift" : "matching",
    scenario,
    planScenario,
    currentStep,
    rows,
  };
}

export function shouldShowScenarioInjectionDiff(state: Record<string, unknown>, diff: ScenarioInjectionDiffView): boolean {
  if (diff.status !== "absent") return true;
  return state.commercial_control_plane === true;
}

function statusLabelKey(status: DiffStatus) {
  switch (status) {
    case "matching":
      return "scenarioInjectionDiff.matching";
    case "scenario_mismatch":
      return "scenarioInjectionDiff.scenarioMismatch";
    case "drift":
      return "scenarioInjectionDiff.drift";
    default:
      return "scenarioInjectionDiff.noPlan";
  }
}

function statusClasses(status: DiffStatus) {
  switch (status) {
    case "matching":
      return "border-[rgba(120,175,140,0.24)] bg-[rgba(120,175,140,0.10)] text-[var(--jade-accent)]";
    case "scenario_mismatch":
    case "drift":
      return "border-[rgba(208,78,90,0.24)] bg-[rgba(208,78,90,0.10)] text-[var(--crimson-mist)]";
    default:
      return "border-[rgba(220,190,120,0.24)] bg-[rgba(220,190,120,0.10)] text-[var(--gold-foil)]";
  }
}

export default function ScenarioInjectionDiffPanel({ diff }: { diff: ScenarioInjectionDiffView }) {
  const { t } = useI18n();

  return (
    <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13px] font-semibold text-[var(--text-h1)]">{t("scenarioInjectionDiff.title")}</h3>
            <span className="rounded-full border border-[rgba(122,150,187,0.24)] bg-[rgba(122,150,187,0.10)] px-2 py-0.5 text-[11px] font-semibold text-[var(--cinema-azure)]">
              {t("commercialInjection.readOnly")}
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
            {t("scenarioInjectionDiff.scenario")}: {diff.scenario || "-"} · {t("scenarioInjectionDiff.currentStep")}: {diff.currentStep || "-"}
          </p>
        </div>
        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${statusClasses(diff.status)}`}>
          {t(statusLabelKey(diff.status))}
        </span>
      </div>

      {diff.status === "absent" ? (
        <p className="mt-3 rounded-lg border border-[var(--border-default)] bg-[var(--bg-card)] p-2 text-[12px] text-[var(--text-muted)]">
          {t("scenarioInjectionDiff.noPlanDetail")}
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          {diff.status === "scenario_mismatch" && (
            <p className="rounded-lg border border-[rgba(208,78,90,0.22)] bg-[rgba(208,78,90,0.07)] p-2 text-[12px] text-[var(--crimson-mist)]">
              {t("scenarioInjectionDiff.planScenario")}: {diff.planScenario || "-"} / {t("scenarioInjectionDiff.scenario")}: {diff.scenario || "-"}
            </p>
          )}
          {diff.rows.map((row) => (
            <DiffRow key={row.key} row={row} />
          ))}
        </div>
      )}
    </section>
  );
}

function DiffRow({ row }: { row: ScenarioInjectionDiffRow }) {
  const { t } = useI18n();
  const hasDelta = row.missing.length > 0 || row.extra.length > 0;
  return (
    <div className={`rounded-lg border p-2 ${hasDelta ? "border-[rgba(208,78,90,0.20)] bg-[rgba(208,78,90,0.05)]" : "border-[var(--border-default)] bg-[var(--bg-card)]"}`}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">{t(row.labelKey)}</p>
      <div className="mt-1 grid gap-2 sm:grid-cols-2">
        <RefList title={t("scenarioInjectionDiff.planned")} values={row.planned} />
        <RefList title={t("scenarioInjectionDiff.current")} values={row.current} />
      </div>
      {hasDelta && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <RefList title={t("scenarioInjectionDiff.missing")} values={row.missing} tone="danger" />
          <RefList title={t("scenarioInjectionDiff.extra")} values={row.extra} tone="danger" />
        </div>
      )}
    </div>
  );
}

function RefList({ title, values, tone = "default" }: { title: string; values: string[]; tone?: "default" | "danger" }) {
  const { t } = useI18n();
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium text-[var(--text-muted)]">{title}</p>
      {values.length === 0 ? (
        <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">{t("scenarioInjectionDiff.noRefs")}</p>
      ) : (
        <div className="mt-0.5 flex flex-wrap gap-1">
          {values.map((value) => (
            <span
              key={value}
              className={`max-w-[180px] truncate rounded-md px-1.5 py-0.5 font-mono text-[11px] ${
                tone === "danger"
                  ? "bg-[rgba(208,78,90,0.10)] text-[var(--crimson-mist)]"
                  : "bg-[var(--bg-panel)] text-[var(--text-body)]"
              }`}
              title={value}
            >
              {value}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
