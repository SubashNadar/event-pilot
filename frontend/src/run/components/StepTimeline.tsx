import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { ChevronDown, ListChecks, Users } from "lucide-react";
import type { ResolveChoice, ResolveResult, RunState } from "../types";
import { formatDuration } from "../lib/format";
import { useNow } from "../lib/useNow";
import StepItem from "./StepItem";

interface Props {
  run: RunState;
  selectedStepId: string | null;
  onOpenStep: (stepId: string) => void;
  onResolve: (stepId: string, choice: ResolveChoice) => Promise<ResolveResult>;
}

/** The plan card: progress header, the six parallel specialists, then the Event Manager's steps. */
export default function StepTimeline({ run, selectedStepId, onOpenStep, onResolve }: Props) {
  const active = run.status === "executing" || run.status === "starting" || run.status === "awaiting_input" || run.status === "answering";
  const now = useNow(active);
  const [open, setOpen] = useState(run.status !== "completed");
  const collapsedOnce = useRef(run.status === "completed");

  // Collapse once when the recommendations start streaming: they become the focus.
  useEffect(() => {
    if (!collapsedOnce.current && run.status === "answering") {
      collapsedOnce.current = true;
      setOpen(false);
    }
  }, [run.status]);

  // A step that needs input always reopens the card.
  const needsInput = run.steps.some((s) => s.status === "failed" && s.recovery && !s.chosen);
  useEffect(() => {
    if (needsInput) setOpen(true);
  }, [needsInput]);

  const steps = run.steps;
  const done = steps.filter((s) => s.status === "completed").length;
  const skipped = steps.filter((s) => s.status === "skipped").length;
  const pct = steps.length ? ((done + skipped) / steps.length) * 100 : 0;
  const elapsed = (run.endedAt ?? now) - run.startedAt;
  const current = steps.find((s) => s.status === "running" || s.status === "verifying");
  const parallel = steps.filter((s) => s.group === "parallel");
  const sequential = steps.filter((s) => s.group !== "parallel");
  const canResolve = run.status === "awaiting_input";

  const renderList = (list: typeof steps, offset: number, showAgent: boolean) =>
    list.map((s, i) => (
      <StepItem
        key={s.id}
        step={s}
        index={offset + i}
        isLast={i === list.length - 1}
        now={now}
        selected={selectedStepId === s.id}
        canResolve={canResolve}
        showAgent={showAgent}
        onOpen={() => onOpenStep(s.id)}
        onResolve={(choice) => onResolve(s.id, choice)}
      />
    ));

  return (
    <section aria-label="Planning steps" className="rounded-2xl border border-border bg-surface shadow-soft">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="plan-steps" className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left">
        <ListChecks size={16} className="shrink-0 text-muted" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2">
            <span className="text-[13.5px] font-medium">Plan</span>
            <span className="truncate text-[12.5px] tabular-nums text-muted">
              {done} of {steps.length} steps{skipped ? ` · ${skipped} skipped` : ""} · {formatDuration(elapsed)}
              {!open && current && <> · {current.title}</>}
              {needsInput && <span className="text-danger"> · needs your input</span>}
            </span>
          </span>
          <span className="mt-2 block h-1 overflow-hidden rounded-full bg-surface-2" aria-hidden>
            <span className={clsx("block h-full rounded-full transition-[width] duration-250 ease-out", needsInput ? "bg-danger" : "bg-accent")} style={{ width: `${pct}%` }} />
          </span>
        </span>
        <ChevronDown size={16} className={clsx("shrink-0 text-muted transition-transform duration-200", open && "rotate-180")} aria-hidden />
      </button>

      {open && (
        <div id="plan-steps" className="animate-fade-in px-4 pb-3">
          {parallel.length > 0 && (
            <div className="mb-2 rounded-xl bg-surface-2/60 px-3 pb-1 pt-2">
              <p className="mb-1 flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-muted">
                <Users size={12} aria-hidden /> Delegated by the Event Manager · {parallel.length} specialists in parallel
              </p>
              <ol className="space-y-0.5">{renderList(parallel, 0, true)}</ol>
            </div>
          )}
          <ol className="space-y-0.5 pt-0.5">{renderList(sequential, parallel.length, false)}</ol>
        </div>
      )}
    </section>
  );
}
