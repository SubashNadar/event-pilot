import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { AlertTriangle, ArrowRight, ExternalLink, GitBranch, Image, Info, ListChecks, Play, RotateCcw, Square } from "lucide-react";
import type { PlanRunApi } from "../usePlanRun";
import type { ResolveChoice, StepKind } from "../types";
import { isTerminal } from "../reducer";
import { formatDuration, formatInr, formatNum, formatUsd } from "../lib/format";
import ConnectionBanner from "./ConnectionBanner";
import StepDetailDrawer from "./StepDetailDrawer";
import StepTimeline from "./StepTimeline";
import StreamingMarkdown from "./StreamingMarkdown";
import ThinkingHints from "./ThinkingHints";
import WorkflowGraph from "./WorkflowGraph";
import LangGraphPng from "./LangGraphPng";

interface Props {
  planRun: PlanRunApi;
  eventName: string;
  onReviewPlan: () => void;
  onRestart?: () => void;
}

const OPERATION_LABEL: Record<string, string> = { "plan-generation": "New plan", "budget-revision": "Budget revision" };

/**
 * The live planning run: the agents' steps as they happen, recovery cards for
 * failed steps, the streamed recommendations and the hand-off to the plan.
 */
export default function RunPanel({ planRun, eventName, onReviewPlan, onRestart }: Props) {
  const { run, connection, resolve, cancel, continueRun } = planRun;
  const [selected, setSelected] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [runView, setRunView] = useState<"timeline" | "graph" | "png">("timeline");
  const live = useRef<HTMLParagraphElement>(null);

  const selectedIndex = run ? run.steps.findIndex((s) => s.id === selected) : -1;
  const selectedStep = selectedIndex >= 0 && run ? run.steps[selectedIndex] : null;

  const closeDrawer = useCallback(() => {
    const id = selected;
    setSelected(null);
    if (id) requestAnimationFrame(() => document.getElementById(`step-btn-${id}`)?.focus());
  }, [selected]);

  const onResolve = useCallback((stepId: string, choice: ResolveChoice) => resolve(stepId, choice), [resolve]);

  const status = run?.status;
  const runningKind: StepKind | "thinking" | undefined = useMemo(() => {
    if (!run) return undefined;
    const current = run.steps.find((s) => s.status === "running" || s.status === "verifying");
    return current ? current.kind : run.steps.length ? undefined : "thinking";
  }, [run]);

  // Announce step changes politely for screen readers.
  const announcement = useMemo(() => {
    if (!run) return "";
    const failed = run.steps.filter((s) => s.status === "failed" && !s.chosen);
    if (failed.length) return `${failed.map((s) => s.title).join(", ")} needs your input.`;
    const current = run.steps.find((s) => s.status === "running");
    if (current) return `${current.title} is running.`;
    if (run.status === "completed") return "Your plan is ready.";
    return "";
  }, [run]);
  useEffect(() => {
    if (live.current) live.current.textContent = announcement;
  }, [announcement]);

  if (!run) {
    return (
      <div className="ep-root mx-auto max-w-[768px] py-16 text-center text-[14px] text-muted">
        No planning run yet. Generate a plan from the event brief or the planner chat.
      </div>
    );
  }

  const terminal = isTerminal(run.status);
  const waiting = run.steps.filter((s) => s.status === "failed" && s.recovery && !s.chosen);
  const plan = run.plan;
  const headline =
    status === "completed" ? "Your plan is ready" :
    status === "awaiting_input" ? `Waiting for your decision on ${waiting.length || 1} step${waiting.length === 1 ? "" : "s"}` :
    status === "stopped" ? "You stopped this plan. Continue to pick up where it left off." :
    status === "error" ? "The planning run stopped. Continue to pick up where it left off." :
    status === "answering" ? "Writing your recommendations" :
    "Your planning team is working";

  return (
    <div className={clsx("ep-root py-6 transition-[margin] duration-250", selectedStep && "lg:mr-[440px]")}>
      <p ref={live} aria-live="polite" className="sr-only" />
      <div className="mx-auto max-w-[768px] space-y-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-muted">Planning run · {OPERATION_LABEL[run.operation] ?? run.operation}</p>
            <h1 className="mt-1 truncate text-[24px] font-semibold leading-tight tracking-[-0.01em]">{eventName}</h1>
            <p className={clsx("mt-1 text-[13.5px]", status === "awaiting_input" ? "text-danger" : "text-muted")}>{headline}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {run.traceUrl && (
              <a href={run.traceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-[12.5px] font-medium text-ink no-underline hover:bg-surface-2">
                View trace <ExternalLink size={12} aria-hidden />
              </a>
            )}
            {!terminal && (
              <button
                type="button"
                disabled={stopping}
                onClick={async () => {
                  setStopping(true);
                  try {
                    await cancel();
                  } finally {
                    setStopping(false);
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-[12.5px] font-medium text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-50"
              >
                <Square size={11} aria-hidden /> Stop
              </button>
            )}
            {(status === "error" || status === "stopped") && (
              <button
                type="button"
                disabled={resuming}
                onClick={async () => {
                  setResuming(true);
                  setResumeError(null);
                  try {
                    await continueRun();
                  } catch (error) {
                    setResumeError(error instanceof Error ? error.message : "Couldn't continue this run. Try again.");
                  } finally {
                    setResuming(false);
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-[12.5px] font-medium text-bg hover:opacity-90 disabled:opacity-50"
              >
                <Play size={12} aria-hidden /> Continue
              </button>
            )}
            {(status === "error" || status === "stopped") && onRestart && (
              <button type="button" onClick={onRestart} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-[12.5px] font-medium text-muted hover:bg-surface-2 hover:text-ink">
                <RotateCcw size={12} aria-hidden /> Start over
              </button>
            )}
            {plan && (
              <button type="button" onClick={onReviewPlan} className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[13px] font-medium text-accent-ink transition-transform duration-150 hover:opacity-95 active:scale-95">
                Review the plan <ArrowRight size={14} aria-hidden />
              </button>
            )}
          </div>
          {resumeError && <p role="alert" className="w-full text-[12.5px] text-danger">{resumeError}</p>}
        </header>

        <ConnectionBanner state={connection} />

        {run.notices.map((notice) => (
          <p key={notice} className="flex items-start gap-2 rounded-xl bg-surface-2 px-3.5 py-2.5 text-[13px] text-muted">
            <Info size={14} className="mt-0.5 shrink-0" aria-hidden /> {notice}
          </p>
        ))}

        {(status === "starting" || status === "executing") && <ThinkingHints context={runningKind} showLabel={run.steps.length === 0} />}

        {run.steps.length > 0 && (
          <>
            <div className="inline-flex rounded-lg border border-border bg-surface p-0.5" role="tablist" aria-label="Planning run view">
              <button type="button" role="tab" aria-selected={runView === "timeline"} onClick={() => setRunView("timeline")} className={clsx("inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors", runView === "timeline" ? "bg-surface-2 text-ink" : "text-muted hover:text-ink")}><ListChecks size={13} aria-hidden /> Timeline</button>
              <button type="button" role="tab" aria-selected={runView === "graph"} onClick={() => setRunView("graph")} className={clsx("inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors", runView === "graph" ? "bg-surface-2 text-ink" : "text-muted hover:text-ink")}><GitBranch size={13} aria-hidden /> Workflow graph</button>
              <button type="button" role="tab" aria-selected={runView === "png"} onClick={() => setRunView("png")} className={clsx("inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors", runView === "png" ? "bg-surface-2 text-ink" : "text-muted hover:text-ink")}><Image size={13} aria-hidden /> LangGraph PNG</button>
            </div>
            {runView === "timeline" ? <StepTimeline run={run} selectedStepId={selected} onOpenStep={setSelected} onResolve={onResolve} /> : runView === "graph" ? <WorkflowGraph run={run} selectedStepId={selected} onOpenStep={setSelected} /> : <LangGraphPng />}
          </>
        )}

        {run.answer && (
          <section aria-label="Recommendations" className="rounded-2xl border border-border bg-surface px-5 py-4 shadow-soft">
            <StreamingMarkdown content={run.answer} streaming={status === "answering"} />
          </section>
        )}

        {status === "error" && (
          <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-danger/30 bg-danger/5 px-3.5 py-3 text-[13px]">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-danger" aria-hidden />
            <div>
              <p className="font-medium text-danger">The run ended early</p>
              <p className="mt-0.5 text-muted">{run.error}</p>
            </div>
          </div>
        )}

        {plan && (
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-success/30 bg-success/[0.06] px-4 py-3">
            <div className="text-[13.5px]">
              <p className="font-medium text-ink">
                {plan.venue} · forecast {formatInr(plan.budget_forecast)}
              </p>
              <p className="text-muted">
                {plan.agenda.length} agenda items · {plan.risks.length} risks to decide · confidence {plan.confidence}%
              </p>
            </div>
            <button type="button" onClick={onReviewPlan} className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-[12.5px] font-medium text-bg hover:opacity-90">
              Open the plan <ArrowRight size={13} aria-hidden />
            </button>
          </section>
        )}

        {run.usage && (
          <p className="text-right font-mono text-[11.5px] tabular-nums text-muted">
            {formatDuration(run.usage.durationMs)}
            {run.usage.tokensIn + run.usage.tokensOut > 0 ? ` · ${formatNum(run.usage.tokensIn + run.usage.tokensOut)} tok` : ""}
            {run.usage.costUsd > 0 ? ` · ${formatUsd(run.usage.costUsd)}` : ""} · {run.usage.model === "rules" ? "rule-based" : run.usage.model}
          </p>
        )}
      </div>

      {selectedStep && <StepDetailDrawer run={run} step={selectedStep} index={selectedIndex} onClose={closeDrawer} onResolve={(choice) => onResolve(selectedStep.id, choice)} />}
    </div>
  );
}
