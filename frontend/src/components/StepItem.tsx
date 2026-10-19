import clsx from "clsx";
import { Check, Circle, Loader2, Minus, RotateCcw, ShieldCheck, SkipForward, X } from "lucide-react";
import type { StepState, StepStatus } from "../types/types";
import { formatDuration } from "../lib/format";

export const STATUS_LABEL: Record<StepStatus, string> = {
  pending: "Pending",
  running: "Running",
  verifying: "Verifying",
  completed: "Completed",
  failed: "Failed",
  skipped: "Skipped",
};

export function StatusIcon({ status, size = "md" }: { status: StepStatus; size?: "sm" | "md" }) {
  const box = size === "sm" ? "h-4 w-4" : "h-5 w-5";
  const icon = size === "sm" ? 10 : 12;
  switch (status) {
    case "pending":
      return <Circle className={clsx(box, "text-border")} strokeWidth={2} aria-hidden />;
    case "running":
      return <Loader2 className={clsx(box, "animate-spin text-accent")} strokeWidth={2.25} aria-hidden />;
    case "verifying":
      return (
        <span className={clsx(box, "relative inline-flex items-center justify-center rounded-full bg-info/15 text-info")} aria-hidden>
          <ShieldCheck size={icon + 1} strokeWidth={2.25} />
          <span className="absolute inset-0 animate-ping rounded-full bg-info/20 motion-reduce:hidden" />
        </span>
      );
    case "completed":
      return (
        <span className={clsx(box, "inline-flex items-center justify-center rounded-full bg-success text-surface")} aria-hidden>
          <Check size={icon} strokeWidth={3} />
        </span>
      );
    case "failed":
      return (
        <span className={clsx(box, "inline-flex items-center justify-center rounded-full bg-danger text-surface")} aria-hidden>
          <X size={icon} strokeWidth={3} />
        </span>
      );
    case "skipped":
      return (
        <span className={clsx(box, "inline-flex items-center justify-center rounded-full border border-dashed border-muted/60 text-muted")} aria-hidden>
          <Minus size={icon} strokeWidth={2.5} />
        </span>
      );
  }
}

interface Props {
  msgId: string;
  step: StepState;
  index: number;
  isLast: boolean;
  now: number;
  selected: boolean;
  /** Retry/Skip only make sense while the run is paused on this failure. */
  canRetry: boolean;
  onOpen: () => void;
  onRetry: () => void;
  onSkip: () => void;
}

export default function StepItem({ msgId, step, index, isLast, now, selected, canRetry, onOpen, onRetry, onSkip }: Props) {
  const live = step.status === "running" || step.status === "verifying";
  const elapsed = step.startedAt ? (step.endedAt ?? now) - step.startedAt : undefined;
  const runningTool = [...step.tools].reverse().find((t) => t.status === "running");

  let sub: React.ReactNode = null;
  if (step.status === "running") {
    sub = runningTool ? (
      <span className="shimmer-text">
        Calling <code className="font-mono text-[12px]">{runningTool.name}</code>…
      </span>
    ) : (
      <span className="shimmer-text">{step.goal}</span>
    );
  } else if (step.status === "verifying") {
    sub = <span className="text-info">{step.verifyingCheck}</span>;
  } else if (step.status === "completed" && step.summary) {
    sub = (
      <span>
        <span className="font-medium text-success">✓ Verified</span>
        <span className="mx-1.5 text-border">·</span>
        {step.summary.verification.reason}
      </span>
    );
  } else if (step.status === "failed") {
    sub = <span className="text-danger">{step.error}</span>;
  } else if (step.status === "skipped") {
    sub = <span>{step.error ?? "Skipped — the plan continued without this step."}</span>;
  }

  return (
    <li className="relative pl-8">
      {/* connector */}
      {!isLast && (
        <span
          aria-hidden
          className={clsx(
            "absolute left-[9.5px] top-7 bottom-[-6px] w-px transition-colors duration-250",
            step.status === "completed" ? "bg-success/40" : "bg-border",
          )}
        />
      )}
      <span className="absolute left-0 top-[9px] flex h-5 w-5 items-center justify-center">
        <StatusIcon status={step.status} />
      </span>

      <button
        id={`step-btn-${msgId}-${step.id}`}
        type="button"
        onClick={onOpen}
        aria-haspopup="dialog"
        aria-label={`Step ${index + 1}: ${step.title} — ${STATUS_LABEL[step.status]}. Open details.`}
        className={clsx(
          "group -mx-2 flex w-[calc(100%+1rem)] items-start gap-3 rounded-lg px-2 py-2 text-left transition-colors duration-150",
          selected ? "bg-surface-2" : "hover:bg-surface-2/70",
        )}
      >
        <span className="min-w-0 flex-1">
          <span
            className={clsx(
              "block text-[14px] font-medium leading-snug transition-colors duration-200",
              step.status === "pending" || step.status === "skipped" ? "text-muted" : "text-ink",
            )}
          >
            {step.title}
            {step.attempts > 1 && step.status !== "failed" && (
              <span className="ml-2 rounded bg-surface-2 px-1.5 py-px align-middle text-[11px] font-normal text-muted">
                attempt {step.attempts}
              </span>
            )}
          </span>
          {sub && <span className="mt-0.5 block text-[12.5px] leading-snug text-muted line-clamp-2">{sub}</span>}
        </span>
        <span className={clsx("shrink-0 pt-px font-mono text-[11.5px] tabular-nums", live ? "text-ink" : "text-muted")}>
          {elapsed !== undefined ? formatDuration(elapsed) : ""}
        </span>
      </button>

      {step.status === "failed" && canRetry && (
        <div className="mb-1 mt-1 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-[12.5px] font-medium text-bg transition-opacity duration-150 hover:opacity-90"
          >
            <RotateCcw size={13} /> Retry step
          </button>
          <button
            type="button"
            onClick={onSkip}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[12.5px] text-muted transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
          >
            <SkipForward size={13} /> Skip
          </button>
        </div>
      )}
    </li>
  );
}
