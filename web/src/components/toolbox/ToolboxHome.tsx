"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  CaretRight,
  ClipboardText,
  WarningCircle,
} from "@phosphor-icons/react";
import TopHeader from "@/components/TopHeader";
import {
  fetchToolboxRuns,
  fetchToolboxTools,
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
    <span className="inline-flex h-7 items-center rounded-full border border-[var(--border-default)] bg-[var(--bg-panel)] px-3 text-xs font-semibold text-[var(--text-muted)]">
      {children}
    </span>
  );
}

function statusClassName(status: string): string {
  if (status === "blocked" || status === "failed") return "text-[var(--danger)]";
  if (status === "review_required") return "text-[#a66b1f]";
  return "text-[#1c7d73]";
}

function deriveAuditSummary(runs: ToolboxRunResponse[]) {
  return [
    {
      labelKey: "toolbox.blocked",
      value: runs.filter((run) => run.status === "blocked" || run.status === "failed").length,
      className: "text-[var(--danger)]",
    },
    {
      labelKey: "toolbox.reviewRequired",
      value: runs.filter((run) => run.status === "review_required").length,
      className: "text-[#a66b1f]",
    },
    {
      labelKey: "toolbox.acceptedDryRun",
      value: runs.filter((run) => run.status === "accepted_dry_run").length,
      className: "text-[#1c7d73]",
    },
  ];
}

export default function ToolboxHome() {
  const { t } = useI18n();
  const [apiTools, setApiTools] = useState<ToolboxToolSummary[]>([]);
  const [runs, setRuns] = useState<ToolboxRunResponse[]>([]);
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

  const tools = useMemo<ToolCardModel[]>(() => {
    return TOOL_ORDER.map((id) => ({
      ...TOOL_PRESENTATION[id],
      api: apiTools.find((tool) => tool.tool_id === id),
    }));
  }, [apiTools]);
  const auditSummary = useMemo(() => deriveAuditSummary(runs), [runs]);
  const latestRun = runs[0] ?? null;

  return (
    <div className="min-h-screen bg-[var(--bg-page)] text-[var(--text-body)]" data-testid="toolbox-home">
      <TopHeader />
      <main className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-4 py-6 sm:px-6 lg:py-8">
        <section className="grid gap-5 border-b border-[var(--divider-subtle)] pb-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--bg-panel)] px-3 py-1 text-xs font-semibold text-[var(--text-muted)]">
              <ClipboardText size={15} weight="fill" />
              <span>L2-fixture-or-dry-run</span>
            </div>
            <h1 className="text-3xl font-semibold tracking-normal text-[var(--text-h1)] sm:text-4xl">
              {t("toolbox.title")}
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--text-muted)] sm:text-base">
              {t("toolbox.subtitle")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <StatPill>{t("toolbox.dryRunOnly")}</StatPill>
            <StatPill>{t("toolbox.noToken")}</StatPill>
            <StatPill>{t("toolbox.approvalRequired")}</StatPill>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-[var(--text-h1)]">{t("toolbox.tools")}</h2>
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                {toolsLoaded ? t("toolbox.status.ready") : t("toolbox.status.locked")}
              </span>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {tools.map((tool) => {
                const Icon = tool.icon;
                const outputTypes = tool.api?.output_types ?? tool.fallbackOutputTypes;
                const scenarios = tool.api?.injectable_scenarios ?? tool.fallbackScenarios;
                const checks = tool.api?.default_checks ?? tool.fallbackChecks;
                return (
                  <article
                    key={tool.id}
                    data-tool-card={tool.id}
                    className="flex min-h-[256px] flex-col justify-between rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4 shadow-[var(--shadow-card)]"
                  >
                    <div className="space-y-4">
                      <div className="flex items-start justify-between gap-3">
                        <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${tool.accentClassName}`}>
                          <Icon size={22} weight="fill" />
                        </span>
                        <span className="rounded-full bg-[rgba(36,37,42,0.06)] px-2 py-1 text-[11px] font-semibold text-[var(--text-muted)]">
                          {t("toolbox.dryRunOnly")}
                        </span>
                      </div>
                      <div>
                        <h3 className="text-base font-semibold text-[var(--text-h1)]">{t(tool.titleKey)}</h3>
                        <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">{t(tool.descriptionKey)}</p>
                      </div>
                      <dl className="space-y-2 text-xs text-[var(--text-muted)]">
                        <div>
                          <dt className="font-semibold text-[var(--text-body)]">{t("toolbox.output")}</dt>
                          <dd className="mt-1 leading-5">{formatToolboxList(outputTypes)}</dd>
                        </div>
                        <div>
                          <dt className="font-semibold text-[var(--text-body)]">{t("toolbox.scenarios")}</dt>
                          <dd className="mt-1 leading-5">{formatToolboxList(scenarios)}</dd>
                        </div>
                        <div>
                          <dt className="font-semibold text-[var(--text-body)]">{t("toolbox.checks")}</dt>
                          <dd className="mt-1 leading-5">{formatToolboxList(checks)}</dd>
                        </div>
                      </dl>
                    </div>
                    <Link
                      href={`/toolbox/${tool.id}`}
                      className="mt-5 inline-flex h-9 items-center justify-between rounded-lg border border-[var(--border-default)] px-3 text-sm font-semibold text-[var(--text-h1)] transition hover:border-[var(--fortune-red)] hover:text-[var(--fortune-red)]"
                    >
                      <span>{t("toolbox.open")}</span>
                      <CaretRight size={16} weight="bold" />
                    </Link>
                  </article>
                );
              })}
            </div>
          </div>

          <aside className="grid gap-4">
            <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.recentRuns")}</h2>
              {runs.length > 0 ? (
                <ul className="mt-4 space-y-2">
                  {runs.map((run) => (
                    <li key={run.run_id} className="rounded-lg bg-[var(--bg-layer2)] p-3" data-toolbox-run={run.run_id}>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-xs font-semibold text-[var(--text-h1)]">{run.tool_id}</span>
                        <span className={`text-[11px] font-semibold ${statusClassName(run.status)}`}>{run.status}</span>
                      </div>
                      <div className="mt-2 break-all text-[11px] leading-5 text-[var(--text-muted)]">{run.run_id}</div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <span className="rounded-full bg-[var(--bg-panel)] px-2 py-1 text-[11px] font-semibold text-[var(--text-muted)]">
                          delivery_accepted={String(run.plan.delivery_accepted)}
                        </span>
                        <span className="rounded-full bg-[var(--bg-panel)] px-2 py-1 text-[11px] font-semibold text-[var(--text-muted)]">
                          publish_allowed={String(run.job_record?.publish_allowed ?? false)}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="mt-4 flex min-h-[104px] items-center justify-center rounded-lg border border-dashed border-[var(--border-default)] bg-[var(--bg-layer2)] px-4 text-center text-sm text-[var(--text-muted)]">
                  {t("toolbox.recentRunsEmpty")}
                </div>
              )}
            </section>

            <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.auditQueue")}</h2>
              <div className="mt-4 grid grid-cols-3 gap-2">
                {auditSummary.map((item) => (
                  <div key={item.labelKey} className="rounded-lg bg-[var(--bg-layer2)] p-3 text-center">
                    <div className={`text-2xl font-semibold ${item.className}`}>{item.value}</div>
                    <div className="mt-1 text-[11px] font-semibold text-[var(--text-muted)]">{t(item.labelKey)}</div>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.jobLedger")}</h2>
              {latestRun?.job_record ? (
                <div className="mt-4 space-y-2 text-xs">
                  <div className="rounded-lg bg-[var(--bg-layer2)] p-3">
                    <div className="font-semibold text-[var(--text-h1)]">{latestRun.job_record.job_id}</div>
                    <div className="mt-1 text-[var(--text-muted)]">{latestRun.job_record.status}</div>
                  </div>
                  <div className="break-all rounded-lg bg-[var(--bg-layer2)] p-3 text-[var(--text-muted)]">
                    prompt_hash={latestRun.plan.prompt_hash ?? "-"}
                  </div>
                  <div className="rounded-lg bg-[var(--bg-layer2)] p-3 text-[var(--text-muted)]">
                    {latestRun.artifacts[0]?.artifact_ref ?? t("toolbox.artifactRefsEmpty")}
                  </div>
                </div>
              ) : (
                <div className="mt-4 rounded-lg border border-dashed border-[var(--border-default)] bg-[var(--bg-layer2)] p-4 text-sm text-[var(--text-muted)]">
                  {t("toolbox.jobLedgerEmpty")}
                </div>
              )}
            </section>

            <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-panel)] p-4">
              <div className="flex items-center gap-2">
                <WarningCircle size={18} weight="fill" className="text-[#a66b1f]" />
                <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("toolbox.providerReadiness")}</h2>
              </div>
              <div className="mt-4 space-y-3 text-sm leading-6 text-[var(--text-muted)]">
                <p>{t("toolbox.providerNoToken")}</p>
                <p>{t("toolbox.providerLedger")}</p>
              </div>
            </section>
          </aside>
        </section>
      </main>
    </div>
  );
}
