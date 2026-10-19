import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { ChevronDown, ListChecks } from "lucide-react";
import type { RunState } from "../types/types";
import { formatDuration } from "../lib/format";
import { useNow } from "../lib/useNow";
import StepItem from "./StepItem";

interface Props {
  msgId: string;
  run: RunState;
  selectedStepId: string | null;
  onOpenStep: (stepId: string) => void;
  onRetryStep: (stepId: string) => void;
  onSkipStep: (stepId: string) => void;
}

export default function StepTimeline({ msgId, run, selectedStepId, onOpenStep, onRetryStep, onSkipStep }: Props) {
  const active = run.status === "executing" || run.status === "thinking" || run.status === "awaiting_retry" || run.status === "answering";
  const now = useNow(active);
  const [open, setOpen] = useState(run.status !== "completed");
  const collapsedOnce = useRef(run.status === "completed");

  // Collapse once when the answer starts streaming — the answer becomes the focus.
  useEffect(() => {
    if (!collapsedOnce.current && run.status === "answering") {
      collapsedOnce.current = true;
      setOpen(false);
    }
  }, [run.status]);

  const steps = run.steps;
  const done = steps.filter((s) => s.status === "completed").length;
  const skipped = steps.filter((s) => s.status === "skipped").length;
  const failed = steps.some((s) => s.status === "failed");
  const pct = steps.length ? (done / steps.length) * 100 : 0;
  const elapsed = (run.endedAt ?? now) - run.startedAt;
  const current = steps.find((s) => s.status === "running" || s.status === "verifying");

  const label = `${done} of ${steps.length} steps${skipped ? ` · ${skipped} skipped` : ""}`;

  return (
    <section aria-label="Plan" className="rounded-2xl border border-border bg-surface shadow-soft">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={`plan-${msgId}`}
        className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left"
      >
        <ListChecks size={16} className="shrink-0 text-muted" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2">
            <span className="text-[13.5px] font-medium">Plan</span>
            <span className="truncate text-[12.5px] text-muted tabular-nums">
              {label} · {formatDuration(elapsed)}
              {!open && current && <> · {current.title}</>}
              {failed && <span className="text-danger"> · needs attention</span>}
            </span>
          </span>
          <span className="mt-2 block h-1 overflow-hidden rounded-full bg-surface-2" aria-hidden>
            <span
              className={clsx("block h-full rounded-full transition-[width] duration-250 ease-out", failed ? "bg-danger" : "bg-accent")}
              style={{ width: `${pct}%` }}
            />
          </span>
        </span>
        <ChevronDown size={16} className={clsx("shrink-0 text-muted transition-transform duration-200", open && "rotate-180")} aria-hidden />
      </button>

      {open && (
        <ol id={`plan-${msgId}`} className="space-y-0.5 px-4 pb-3 pt-0.5 animate-fade-in">
          {steps.map((s, i) => (
            <StepItem
              key={s.id}
              msgId={msgId}
              step={s}
              index={i}
              isLast={i === steps.length - 1}
              now={now}
              selected={selectedStepId === s.id}
              canRetry={run.status === "awaiting_retry"}
              onOpen={() => onOpenStep(s.id)}
              onRetry={() => onRetryStep(s.id)}
              onSkip={() => onSkipStep(s.id)}
            />
          ))}
        </ol>
      )}
    </section>
  );
}
