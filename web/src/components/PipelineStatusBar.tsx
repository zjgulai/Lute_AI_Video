"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle, Spinner, Warning, X, ArrowRight } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import { usePipelineStore } from "@/stores/usePipelineStore";
import { useAppStore } from "@/stores/useAppStore";
import { getScenarioStatus } from "./api";

const POLL_INTERVAL_MS = 5000;
const POLL_FAILURE_THRESHOLD = 5;

const STEP_ESTIMATED_SECONDS: Record<string, number> = {
  strategy: 5,
  scripts: 10,
  compliance: 2,
  storyboards: 5,
  keyframe_images: 190,
  video_prompts: 3,
  thumbnail_prompts: 3,
  seedance_clips: 240,
  tts_audio: 5,
  thumbnail_images: 160,
  assemble_final: 5,
  audit: 2,
  video_analysis: 60,
  character_identity: 30,
  remix_script: 15,
  thumbnails: 30,
  vlog_strategy: 60,
};

type StatusKind = "running" | "paused" | "completed" | "error";

interface StatusSnapshot {
  status: StatusKind;
  currentStep: string | null;
  progress: number;
  totalSteps: number;
  doneSteps: number;
  remainingStepNames: string[];
  errors: string[];
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatRemaining(seconds: number): string {
  if (seconds <= 60) return `~${Math.max(1, Math.round(seconds))}s`;
  const m = Math.round(seconds / 60);
  return `~${m}m`;
}

function estimateRemainingSeconds(remainingSteps: string[]): number {
  return remainingSteps.reduce((acc, name) => acc + (STEP_ESTIMATED_SECONDS[name] ?? 30), 0);
}

function deriveSnapshot(data: Record<string, unknown>): StatusSnapshot {
  const stepsObj = (data?.steps as Record<string, { status?: string }>) || {};
  const stepEntries = Object.entries(stepsObj) as [string, { status?: string }][];
  const totalSteps = stepEntries.length;
  const doneSteps = stepEntries.filter(([, v]) => v?.status === "done").length;
  const progress = totalSteps === 0 ? 0 : Math.round((doneSteps / totalSteps) * 100);
  const remainingStepNames = stepEntries
    .filter(([, v]) => v?.status !== "done")
    .map(([name]) => name);

  const rawStatus = data?.status as string | undefined;
  let status: StatusKind = "running";
  if (rawStatus === "completed") status = "completed";
  else if (rawStatus === "paused") status = "paused";
  else if (rawStatus === "error" || data?.pipeline_degraded) status = "error";

  return {
    status,
    currentStep: (data?.current_step as string | null) ?? null,
    progress,
    totalSteps,
    doneSteps,
    remainingStepNames,
    errors: Array.isArray(data?.errors) ? (data.errors as string[]).slice(0, 3) : [],
  };
}

export default function PipelineStatusBar() {
  const { t } = useI18n();
  const router = useRouter();
  const activePipeline = usePipelineStore((s) => s.activePipeline);
  const clearActivePipeline = usePipelineStore((s) => s.clearActivePipeline);
  const dismissPipeline = usePipelineStore((s) => s.dismissPipeline);
  const dismissedLabels = usePipelineStore((s) => s.dismissedPipelineLabels);
  const showToast = useAppStore((s) => s.showToast);

  const [snapshot, setSnapshot] = useState<StatusSnapshot | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [hidden, setHidden] = useState(false);
  const completionNotifiedRef = useRef(false);
  const pausedNotifiedRef = useRef(false);
  const failureCountRef = useRef(0);

  const isDismissed = activePipeline ? dismissedLabels.includes(activePipeline.label) : false;
  const shouldShow = !!activePipeline && !hidden && !isDismissed;

  useEffect(() => {
    if (!activePipeline) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSnapshot(null);
      setElapsed(0);
      completionNotifiedRef.current = false;
      failureCountRef.current = 0;
      return;
    }

    completionNotifiedRef.current = false;
    pausedNotifiedRef.current = false;
    failureCountRef.current = 0;

    const updateElapsed = () => {
      setElapsed(Math.floor((Date.now() - activePipeline.startedAt) / 1000));
    };
    updateElapsed();
    const elapsedTimer = setInterval(updateElapsed, 1000);

    let cancelled = false;
    let timeoutHandle: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      if (cancelled) return;
      try {
        const data = await getScenarioStatus(activePipeline.scenario, activePipeline.label);
        if (cancelled) return;
        const snap = deriveSnapshot(data);
        setSnapshot(snap);
        failureCountRef.current = 0;

        if (snap.status === "completed" && !completionNotifiedRef.current) {
          completionNotifiedRef.current = true;
          showToast(t("pipeline.completedNotice", "你的作品已生成完成"), "success");
          if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
            try {
              new Notification(t("pipeline.completedTitle", "Short Video Factory"), {
                body: t("pipeline.completedNotice", "你的作品已生成完成"),
                icon: "/favicon.ico",
                tag: activePipeline.label,
              });
            } catch {}
          }
        }

        if (snap.status === "paused" && !pausedNotifiedRef.current) {
          pausedNotifiedRef.current = true;
          showToast(t("pipeline.pausedNotice", "节点已完成，等待你审核"), "info");
          if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
            try {
              new Notification(t("pipeline.pausedTitle", "需要你审核"), {
                body: t("pipeline.pausedNotice", "节点已完成，等待你审核"),
                icon: "/favicon.ico",
                tag: `${activePipeline.label}-paused`,
              });
            } catch {}
          }
        }
        if (snap.status === "running") {
          pausedNotifiedRef.current = false;
        }

        if (snap.status === "completed" || snap.status === "error") {
          return;
        }
      } catch {
        failureCountRef.current += 1;
        if (failureCountRef.current >= POLL_FAILURE_THRESHOLD) {
          return;
        }
      }
      if (!cancelled) {
        timeoutHandle = setTimeout(poll, POLL_INTERVAL_MS);
      }
    };

    poll();

    return () => {
      cancelled = true;
      clearInterval(elapsedTimer);
      if (timeoutHandle) clearTimeout(timeoutHandle);
    };
  }, [activePipeline, showToast, t]);

  useEffect(() => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    if (!activePipeline) return;
    if (Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }
  }, [activePipeline]);

  if (!shouldShow || !activePipeline) return null;

  const status = snapshot?.status ?? "running";
  const progress = snapshot?.progress ?? 0;
  const totalSteps = snapshot?.totalSteps ?? 0;
  const doneSteps = snapshot?.doneSteps ?? 0;
  const remainingSteps = snapshot?.remainingStepNames ?? [];
  const remainingSeconds = status === "running" ? estimateRemainingSeconds(remainingSteps) : 0;

  const tone =
    status === "completed"
      ? "border-l-[var(--jade-accent)] bg-[rgba(120,175,140,0.08)]"
      : status === "error"
        ? "border-l-[var(--crimson-mist)] bg-[rgba(196,91,80,0.08)]"
        : status === "paused"
          ? "border-l-[var(--gold-foil)] bg-[rgba(216,190,120,0.10)]"
          : "border-l-[var(--fortune-red)] bg-[rgba(215,92,112,0.08)]";

  const StatusIcon =
    status === "completed" ? CheckCircle : status === "error" ? Warning : Spinner;
  const iconColor =
    status === "completed"
      ? "text-[var(--jade-accent)]"
      : status === "error"
        ? "text-[var(--crimson-mist)]"
        : status === "paused"
          ? "text-[var(--gold-foil)]"
          : "text-[var(--fortune-red)]";
  const iconClass = status === "running" ? `${iconColor} animate-spin` : iconColor;

  const headlineKey =
    status === "completed"
      ? t("pipeline.completedHeadline", "作品已完成")
      : status === "error"
        ? t("pipeline.errorHeadline", "流水线出错")
        : status === "paused"
          ? t("pipeline.pausedHeadline", "等待你的审核")
          : t("pipeline.runningHeadline", "正在生成视频");

  const detailRoute = "/?label=" + encodeURIComponent(activePipeline.label);
  const completedRoute = "/works";

  const handleDismiss = () => {
    if (status === "completed") {
      clearActivePipeline();
    } else {
      setHidden(true);
      dismissPipeline(activePipeline.label);
    }
  };

  const handleViewDetails = () => {
    if (status === "completed") {
      router.push(completedRoute);
      clearActivePipeline();
    } else {
      router.push(detailRoute);
    }
  };

  return (
    <div
      data-pipeline-status-bar
      data-status={status}
      role="status"
      aria-live="polite"
      className={`border-b border-l-4 ${tone} backdrop-blur-md`}
    >
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 py-2 flex items-center gap-3">
        <StatusIcon size={16} weight="fill" className={`shrink-0 ${iconClass}`} />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-[12px] sm:text-[13px]">
            <span className="font-medium text-[var(--text-h1)] truncate">{headlineKey}</span>
            {snapshot && totalSteps > 0 && status !== "error" && (
              <span className="text-[var(--text-muted)] tabular-nums">
                {doneSteps}/{totalSteps} · {progress}%
              </span>
            )}
            {status === "running" && remainingSeconds > 0 && (
              <span className="text-[var(--text-muted)] tabular-nums" title={t("pipeline.remainingHint")}>
                · {t("pipeline.remaining")} {formatRemaining(remainingSeconds)}
              </span>
            )}
            <span className="hidden sm:inline text-[var(--text-muted)] tabular-nums ml-auto">
              {formatElapsed(elapsed)}
            </span>
          </div>
          {status === "error" && snapshot?.errors && snapshot.errors[0] && (
            <p className="text-[11px] text-[var(--crimson-mist)] mt-0.5 truncate">
              {snapshot.errors[0]}
            </p>
          )}
          {status !== "error" && status !== "completed" && (
            <div
              className="mt-1 h-[2px] w-full bg-[var(--bg-panel)] rounded-full overflow-hidden"
              role="progressbar"
              aria-valuenow={progress}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full bg-[var(--fortune-red)] transition-all duration-700 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={handleViewDetails}
            className="hidden sm:inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[12px] font-medium text-[var(--fortune-red)] hover:bg-[rgba(215,92,112,0.10)] transition-colors cursor-pointer"
          >
            {status === "completed" ? t("pipeline.viewWorks", "查看作品") : t("pipeline.viewDetails", "查看详情")}
            <ArrowRight size={12} weight="bold" />
          </button>
          {status === "completed" && (
            <Link
              href={completedRoute}
              onClick={() => clearActivePipeline()}
              className="sm:hidden text-[12px] font-medium text-[var(--fortune-red)] px-2 py-1"
            >
              {t("pipeline.viewWorks", "查看")}
            </Link>
          )}
          <button
            type="button"
            onClick={handleDismiss}
            aria-label={t("common.close", "关闭")}
            className="p-1 rounded-md text-[var(--text-muted)] hover:text-[var(--text-h1)] hover:bg-[var(--bg-panel)] transition-colors cursor-pointer"
          >
            <X size={14} weight="bold" />
          </button>
        </div>
      </div>
    </div>
  );
}
