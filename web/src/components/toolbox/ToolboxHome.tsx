"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CaretRight,
  CheckCircle,
  ClipboardText,
  LockKey,
  WarningCircle,
} from "@phosphor-icons/react";
import TopHeader from "@/components/TopHeader";
import {
  fetchToolboxAuditSummaries,
  fetchToolboxRuns,
  fetchToolboxTools,
  type ToolboxInjectionAuditSummaryResponse,
  type ToolboxRunResponse,
  type ToolboxToolSummary,
} from "@/components/api";
import { useI18n } from "@/i18n/I18nProvider";
import {
  formatToolboxList,
  TOOL_ORDER,
  TOOL_PRESENTATION,
  type ToolPresentation,
} from "@/components/toolbox/toolboxCatalog";

type ToolCardModel = ToolPresentation & {
  api?: ToolboxToolSummary;
};

function StatPill({ children }: { children: string }) {
  return (
    <span className="inline-flex h-9 items-center rounded-full border border-[rgba(53,20,26,0.08)] bg-white px-4 text-xs font-semibold text-[var(--text-body)] shadow-[0_1px_2px_rgba(53,20,26,0.04)]">
      {children}
    </span>
  );
}

function BoundaryChip({
  icon,
  label,
}: {
  icon: "check" | "lock" | "warn";
  label: string;
}) {
  const Icon = icon === "check" ? CheckCircle : icon === "lock" ? LockKey : WarningCircle;
  const toneClassName =
    icon === "check"
      ? "text-[#1c7d73]"
      : icon === "lock"
        ? "text-[var(--fortune-red)]"
        : "text-[#a66b1f]";

  return (
    <span className="inline-flex h-9 items-center gap-2 rounded-full border border-[rgba(53,20,26,0.08)] bg-white px-4 text-xs font-semibold text-[var(--text-body)] shadow-[0_1px_2px_rgba(53,20,26,0.04)]">
      <Icon size={16} weight="fill" className={toneClassName} />
      {label}
    </span>
  );
}

function statusClassName(status: string): string {
  if (status === "blocked" || status === "failed") return "text-[var(--danger)]";
  if (status === "review_required") return "text-[#a66b1f]";
  return "text-[#1c7d73]";
}

function readinessClassName(summary: ToolboxInjectionAuditSummaryResponse | undefined): string {
  if (!summary) return "text-[var(--text-muted)]";
  if (!summary.ready_for_scenario_injection) return "text-[var(--danger)]";
  if (summary.advisory_reasons?.length) return "text-[#a66b1f]";
  return "text-[#1c7d73]";
}

function readinessLabelKey(summary: ToolboxInjectionAuditSummaryResponse | undefined): string {
  if (!summary) return "toolbox.audit.noSummaryShort";
  if (!summary.ready_for_scenario_injection) return "toolbox.audit.blockedShort";
  if (summary.advisory_reasons?.length) return "toolbox.audit.advisoryShort";
  return "toolbox.audit.readyShort";
}

function passedCheckCount(summary: ToolboxInjectionAuditSummaryResponse | undefined): number {
  return summary?.checks.filter((check) => check.status === "passed").length ?? 0;
}

function deriveAuditSummary(summaries: ToolboxInjectionAuditSummaryResponse[]) {
  return [
    {
      labelKey: "toolbox.audit.blockedRuns",
      value: summaries.filter((summary) => !summary.ready_for_scenario_injection).length,
      className: "text-[var(--danger)]",
    },
    {
      labelKey: "toolbox.audit.advisoryRuns",
      value: summaries.filter((summary) => summary.ready_for_scenario_injection && summary.advisory_reasons?.length).length,
      className: "text-[#a66b1f]",
    },
    {
      labelKey: "toolbox.audit.readyRuns",
      value: summaries.filter((summary) => summary.ready_for_scenario_injection).length,
      className: "text-[#1c7d73]",
    },
  ];
}

function CompactBoundary({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0 rounded-[18px] border border-[rgba(53,20,26,0.08)] bg-white px-4 py-3 shadow-[0_8px_24px_rgba(53,20,26,0.04)]">
      <div className="truncate text-[11px] font-semibold text-[var(--text-muted)]">{label}</div>
      <div className="mt-1 min-w-0 truncate text-sm font-semibold text-[var(--text-h1)]">{value}</div>
    </div>
  );
}

export default function ToolboxHome() {
  const { t } = useI18n();
  const [apiTools, setApiTools] = useState<ToolboxToolSummary[]>([]);
  const [runs, setRuns] = useState<ToolboxRunResponse[]>([]);
  const [auditSummaries, setAuditSummaries] = useState<ToolboxInjectionAuditSummaryResponse[]>([]);
  const [toolsLoaded, setToolsLoaded] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchToolboxTools({ signal: controller.signal })
      .then((data) => {
        setApiTools(data.tools);
        setToolsLoaded(true);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setApiTools([]);
        setToolsLoaded(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchToolboxRuns({ limit: 5, signal: controller.signal })
      .then((data) => setRuns(data.runs))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setRuns([]);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchToolboxAuditSummaries({ limit: 5, signal: controller.signal })
      .then((data) => setAuditSummaries(data.summaries))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setAuditSummaries([]);
      });
    return () => controller.abort();
  }, []);

  const tools = useMemo<ToolCardModel[]>(() => {
    return TOOL_ORDER.map((id) => ({
      ...TOOL_PRESENTATION[id],
      api: apiTools.find((tool) => tool.tool_id === id),
    }));
  }, [apiTools]);
  const summaryByRunId = useMemo(() => {
    return new Map(auditSummaries.map((summary) => [summary.run_id, summary]));
  }, [auditSummaries]);
  const auditSummary = useMemo(() => deriveAuditSummary(auditSummaries), [auditSummaries]);
  const latestRun = runs[0] ?? null;

  return (
    <div
      className="min-h-screen bg-[linear-gradient(180deg,#f8f8f8_0%,var(--bg-page)_42%,#f5f1ef_100%)] text-[var(--text-body)]"
      data-testid="toolbox-home"
    >
      <TopHeader />
      <main className="mx-auto flex w-full max-w-[1440px] flex-col gap-7 px-4 py-6 sm:px-6 lg:py-8">
        <section className="overflow-hidden rounded-[28px] border border-[rgba(53,20,26,0.08)] bg-[linear-gradient(135deg,#ffffff_0%,#fbf7f5_48%,#f3eeeb_100%)] shadow-[0_22px_60px_rgba(53,20,26,0.08)]">
          <div className="grid gap-0 lg:grid-cols-[minmax(0,0.92fr)_minmax(420px,0.58fr)]">
            <div className="flex min-h-[280px] flex-col justify-between p-6 sm:min-h-[320px] sm:p-8 lg:p-10">
              <div>
                <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-[rgba(53,20,26,0.08)] bg-white px-4 py-2 text-xs font-semibold text-[var(--text-muted)] shadow-[0_1px_2px_rgba(53,20,26,0.04)]">
                  <ClipboardText size={15} weight="fill" className="text-[var(--fortune-red)]" />
                  <span>L2-fixture-or-dry-run</span>
                </div>
                <h1 className="max-w-3xl text-3xl font-semibold leading-tight tracking-normal text-[var(--text-h1)] sm:text-5xl">
                  {t("toolbox.title")}
                </h1>
                <p className="mt-4 max-w-2xl text-sm leading-6 text-[var(--text-body)] sm:text-base">
                  {t("toolbox.subtitle")}
                </p>
              </div>
              <div className="mt-8 flex flex-wrap gap-2">
                <BoundaryChip icon="check" label={t("toolbox.dryRunOnly")} />
                <BoundaryChip icon="lock" label={t("toolbox.noToken")} />
                <BoundaryChip icon="warn" label={t("toolbox.approvalRequired")} />
              </div>
            </div>

            <div className="relative border-t border-[rgba(53,20,26,0.07)] bg-[radial-gradient(circle_at_12%_18%,rgba(215,92,112,0.14),transparent_30%),linear-gradient(145deg,#f4f4f4_0%,#ffffff_56%,#eee8e4_100%)] p-6 lg:border-l lg:border-t-0 lg:p-8">
              <div className="grid h-full min-h-[220px] grid-cols-2 gap-3 sm:min-h-[260px]">
                {tools.slice(0, 4).map((tool, index) => {
                  const Icon = tool.icon;
                  return (
                    <Link
                      href={`/toolbox/${tool.id}`}
                      key={tool.id}
                      className={`group flex flex-col justify-between rounded-[24px] border border-[rgba(53,20,26,0.08)] bg-white/90 p-4 text-left shadow-[0_14px_34px_rgba(53,20,26,0.08)] transition duration-300 hover:-translate-y-1 hover:border-[rgba(215,92,112,0.32)] hover:shadow-[0_20px_46px_rgba(53,20,26,0.12)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--fortune-red)] active:translate-y-0 ${
                        index === 0 ? "col-span-2 min-h-[126px]" : "min-h-[118px]"
                      }`}
                    >
                      <span className={`flex h-11 w-11 items-center justify-center rounded-2xl ${tool.accentClassName}`}>
                        <Icon size={23} weight="fill" className="transition duration-300 group-hover:scale-110" />
                      </span>
                      <span className="mt-4 text-sm font-semibold text-[var(--text-h1)]">{t(tool.titleKey)}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          </div>
        </section>

        <section className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-[var(--text-h1)]">{t("toolbox.tools")}</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {toolsLoaded ? t("toolbox.status.ready") : t("toolbox.status.locked")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatPill>{t("toolbox.dryRunOnly")}</StatPill>
            <StatPill>{t("toolbox.noToken")}</StatPill>
          </div>
        </section>

        <section className="grid auto-rows-[minmax(236px,auto)] gap-4 lg:grid-cols-4">
          {tools.map((tool, index) => {
            const Icon = tool.icon;
            const outputTypes = tool.api?.output_types ?? tool.fallbackOutputTypes;
            const scenarios = tool.api?.injectable_scenarios ?? tool.fallbackScenarios;
            const checks = tool.api?.default_checks ?? tool.fallbackChecks;
            const isFeatured = index === 0;
            return (
              <Link
                key={tool.id}
                href={`/toolbox/${tool.id}`}
                data-tool-card={tool.id}
                className={`group relative flex min-w-0 overflow-hidden rounded-[26px] border border-[rgba(53,20,26,0.09)] bg-white p-5 text-left shadow-[0_12px_34px_rgba(53,20,26,0.06)] transition duration-300 hover:-translate-y-1 hover:border-[rgba(215,92,112,0.34)] hover:shadow-[0_24px_54px_rgba(53,20,26,0.12)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--fortune-red)] active:translate-y-0 ${
                  isFeatured ? "lg:col-span-2 lg:row-span-2" : ""
                }`}
              >
                <div className="relative z-[1] flex min-w-0 w-full flex-col justify-between">
                  <div>
                    <div className="flex items-start justify-between gap-4">
                      <span
                        className={`flex shrink-0 items-center justify-center rounded-[22px] transition duration-300 group-hover:scale-105 ${
                          isFeatured ? `h-16 w-16 ${tool.accentClassName}` : `h-12 w-12 ${tool.accentClassName}`
                        }`}
                      >
                        <Icon size={isFeatured ? 34 : 24} weight="fill" />
                      </span>
                      <span className="inline-flex h-8 items-center rounded-full border border-[rgba(53,20,26,0.08)] bg-[rgba(53,20,26,0.03)] px-3 text-[11px] font-semibold text-[var(--text-muted)]">
                        {t("toolbox.dryRunOnly")}
                      </span>
                    </div>

                    <div className={isFeatured ? "mt-8 max-w-lg" : "mt-5"}>
                      <h3 className={isFeatured ? "text-3xl font-semibold leading-tight text-[var(--text-h1)]" : "text-lg font-semibold text-[var(--text-h1)]"}>
                        {t(tool.titleKey)}
                      </h3>
                      <p className={isFeatured ? "mt-3 max-w-md text-base leading-7 text-[var(--text-body)]" : "mt-2 text-sm leading-6 text-[var(--text-muted)]"}>
                        {t(tool.descriptionKey)}
                      </p>
                    </div>

                    <div className={isFeatured ? "mt-8 grid min-w-0 gap-3 sm:grid-cols-3" : "mt-5 grid min-w-0 gap-2"}>
                      <CompactBoundary label={t("toolbox.output")} value={formatToolboxList(outputTypes)} />
                      <CompactBoundary label={t("toolbox.scenarios")} value={formatToolboxList(scenarios)} />
                      <CompactBoundary label={t("toolbox.checks")} value={isFeatured ? formatToolboxList(checks) : checks.length} />
                    </div>
                  </div>

                  <div className="mt-7 flex items-center justify-between gap-3 border-t border-[rgba(53,20,26,0.06)] pt-4">
                    <span className="text-sm font-semibold text-[var(--fortune-red)]">{t("toolbox.open")}</span>
                    <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--fortune-red)] text-white shadow-[0_8px_20px_rgba(215,92,112,0.24)] transition duration-300 group-hover:translate-x-1">
                      {isFeatured ? <ArrowRight size={17} weight="bold" /> : <CaretRight size={17} weight="bold" />}
                    </span>
                  </div>
                </div>
                {isFeatured ? (
                  <div className="pointer-events-none absolute -right-20 -top-20 hidden h-64 w-64 rounded-full bg-[rgba(215,92,112,0.09)] blur-3xl sm:block" />
                ) : null}
              </Link>
            );
          })}
        </section>

        <section className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(300px,0.72fr)_minmax(300px,0.72fr)]">
          <section className="rounded-[26px] border border-[rgba(53,20,26,0.09)] bg-white p-5 shadow-[0_12px_34px_rgba(53,20,26,0.06)]">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-[var(--text-h1)]">{t("toolbox.recentRuns")}</h2>
              <span className="text-xs font-semibold text-[var(--text-muted)]">{runs.length}</span>
            </div>
            {runs.length > 0 ? (
              <ul className="mt-4 grid gap-3">
                {runs.map((run) => {
                  const summary = summaryByRunId.get(run.run_id);
                  return (
                    <li
                      key={run.run_id}
                      className="rounded-[20px] border border-[rgba(53,20,26,0.07)] bg-[var(--bg-layer3)] p-4"
                      data-toolbox-run={run.run_id}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-[var(--text-h1)]">{run.tool_id}</div>
                          <div className="mt-1 break-all text-xs leading-5 text-[var(--text-muted)]">{run.run_id}</div>
                        </div>
                        <span className={`rounded-full bg-white px-3 py-1 text-xs font-semibold ${statusClassName(run.status)}`}>{run.status}</span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <span className={`rounded-full bg-white px-3 py-1 text-[11px] font-semibold ${readinessClassName(summary)}`}>
                          {t(readinessLabelKey(summary))}
                        </span>
                        <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-[var(--text-muted)]">
                          targets={summary?.target_count ?? 0}
                        </span>
                        <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-[var(--text-muted)]">
                          checks={passedCheckCount(summary)}/{summary?.checks.length ?? 0}
                        </span>
                        <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-[var(--text-muted)]">
                          delivery_accepted={String(run.plan.delivery_accepted)}
                        </span>
                        <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-[var(--text-muted)]">
                          publish_allowed={String(run.job_record?.publish_allowed ?? false)}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <div className="mt-4 flex min-h-[132px] items-center justify-center rounded-[22px] border border-dashed border-[rgba(53,20,26,0.12)] bg-[var(--bg-layer3)] px-5 text-center text-sm text-[var(--text-muted)]">
                {t("toolbox.recentRunsEmpty")}
              </div>
            )}
          </section>

          <section className="rounded-[26px] border border-[rgba(53,20,26,0.09)] bg-white p-5 shadow-[0_12px_34px_rgba(53,20,26,0.06)]">
            <h2 className="text-base font-semibold text-[var(--text-h1)]">{t("toolbox.auditQueue")}</h2>
            <div className="mt-4 grid gap-3">
              {auditSummary.map((item) => (
                <div key={item.labelKey} className="flex items-center justify-between rounded-[20px] bg-[var(--bg-layer3)] px-4 py-3">
                  <div className="text-sm font-semibold text-[var(--text-muted)]">{t(item.labelKey)}</div>
                  <div className={`text-2xl font-semibold ${item.className}`}>{item.value}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-[26px] border border-[rgba(53,20,26,0.09)] bg-white p-5 shadow-[0_12px_34px_rgba(53,20,26,0.06)]">
            <div className="flex items-center gap-2">
              <WarningCircle size={18} weight="fill" className="text-[#a66b1f]" />
              <h2 className="text-base font-semibold text-[var(--text-h1)]">{t("toolbox.providerReadiness")}</h2>
            </div>
            <div className="mt-4 space-y-3 text-sm leading-6 text-[var(--text-muted)]">
              <p>{t("toolbox.providerNoToken")}</p>
              <p>{t("toolbox.providerLedger")}</p>
            </div>
            <div className="mt-5">
              <h2 className="text-base font-semibold text-[var(--text-h1)]">{t("toolbox.jobLedger")}</h2>
              {latestRun?.job_record ? (
                <div className="mt-3 grid gap-2 text-xs">
                  <div className="rounded-[18px] bg-[var(--bg-layer3)] p-3">
                    <div className="font-semibold text-[var(--text-h1)]">{latestRun.job_record.job_id}</div>
                    <div className="mt-1 text-[var(--text-muted)]">{latestRun.job_record.status}</div>
                  </div>
                  <div className="break-all rounded-[18px] bg-[var(--bg-layer3)] p-3 text-[var(--text-muted)]">
                    prompt_hash={latestRun.plan.prompt_hash ?? "-"}
                  </div>
                  <div className="rounded-[18px] bg-[var(--bg-layer3)] p-3 text-[var(--text-muted)]">
                    {latestRun.artifacts[0]?.artifact_ref ?? t("toolbox.artifactRefsEmpty")}
                  </div>
                </div>
              ) : (
                <div className="mt-3 rounded-[18px] border border-dashed border-[rgba(53,20,26,0.12)] bg-[var(--bg-layer3)] p-4 text-sm text-[var(--text-muted)]">
                  {t("toolbox.jobLedgerEmpty")}
                </div>
              )}
            </div>
          </section>
        </section>
      </main>
    </div>
  );
}
