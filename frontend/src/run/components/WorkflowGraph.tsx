import clsx from "clsx";
import { ArrowDown, GitFork, Network, Sparkles } from "lucide-react";
import type { RunState, StepState } from "../types";
import { StatusIcon, STATUS_LABEL } from "./StepItem";

interface Props {
  run: RunState;
  selectedStepId: string | null;
  onOpenStep: (stepId: string) => void;
}

const stepTone = (step: StepState, selected: boolean) => clsx(
  "group relative flex min-h-[94px] w-full flex-col rounded-xl border p-3 text-left transition-all duration-200",
  selected ? "border-accent bg-accent-soft shadow-soft" : "border-border bg-surface hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-soft",
  step.status === "pending" || step.status === "skipped" ? "opacity-75" : "",
  step.status === "failed" ? "border-danger/50" : "",
);

function GraphStep({ step, selected, onOpen }: { step: StepState; selected: boolean; onOpen: () => void }) {
  const statusText = STATUS_LABEL[step.status];
  return (
    <button type="button" onClick={onOpen} className={stepTone(step, selected)} aria-haspopup="dialog" aria-label={`${step.title}: ${statusText}. Open step details.`}>
      <span className="flex items-start justify-between gap-2">
        <span className="text-[12.5px] font-semibold leading-snug text-ink">{step.title}</span>
        <StatusIcon status={step.status} size="sm" />
      </span>
      <span className="mt-1 block text-[11px] leading-snug text-muted">{step.agent}</span>
      <span className={clsx("mt-auto pt-2 text-[10.5px] font-medium", step.status === "failed" ? "text-danger" : step.status === "verifying" ? "text-info" : "text-muted")}>{statusText}</span>
    </button>
  );
}

function Connector({ label }: { label?: string }) {
  return <div className="flex flex-col items-center py-2 text-muted" aria-hidden><ArrowDown size={17} strokeWidth={1.8} />{label && <span className="mt-0.5 text-[10px] font-medium">{label}</span>}</div>;
}

/** A visual representation of the real LangGraph workflow. It shares state with the timeline. */
export default function WorkflowGraph({ run, selectedStepId, onOpenStep }: Props) {
  const specialists = run.steps.filter((step) => step.group === "parallel");
  const managerSteps = run.steps.filter((step) => step.group !== "parallel");
  const active = run.steps.find((step) => step.status === "running" || step.status === "verifying");

  return (
    <section aria-label="LangGraph workflow graph" className="rounded-2xl border border-border bg-surface p-4 shadow-soft sm:p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-muted"><Network size={13} aria-hidden /> LangGraph workflow</p>
          <h2 className="mt-1 text-[16px] font-semibold leading-snug">How the planning team is coordinated</h2>
          <p className="mt-1 text-[12.5px] text-muted">Click a node to inspect its tools, verification, recovery choices, and trace context.</p>
        </div>
        {active && <span className="ep-chip"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> {active.title}</span>}
      </header>

      <div className="mx-auto mt-5 max-w-[820px]">
        <div className="mx-auto flex max-w-[220px] items-center gap-2 rounded-xl border border-success/30 bg-success/[0.06] px-3 py-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-success text-surface"><Sparkles size={14} aria-hidden /></span>
          <span><strong className="block text-[12.5px]">Event brief</strong><small className="block text-[10.5px] text-muted">Shared graph state</small></span>
        </div>
        <Connector label="delegate" />

        <div className="rounded-2xl border border-border bg-surface-2/60 p-3 sm:p-4">
          <p className="mb-3 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-muted"><GitFork size={13} aria-hidden /> Specialist agents run in parallel</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {specialists.map((step) => <GraphStep key={step.id} step={step} selected={selectedStepId === step.id} onOpen={() => onOpenStep(step.id)} />)}
          </div>
        </div>

        <Connector label="combine and check" />

        <div className="rounded-2xl border border-border bg-surface-2/40 p-3 sm:p-4">
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">Event Manager and review loop</p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {managerSteps.map((step) => <GraphStep key={step.id} step={step} selected={selectedStepId === step.id} onOpen={() => onOpenStep(step.id)} />)}
          </div>
        </div>

        <Connector />
        <div className="mx-auto flex max-w-[250px] items-center gap-2 rounded-xl border border-accent/30 bg-accent-soft px-3 py-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-accent-ink"><Network size={14} aria-hidden /></span>
          <span><strong className="block text-[12.5px]">Human review</strong><small className="block text-[10.5px] text-muted">Approve decisions and export the plan</small></span>
        </div>
      </div>
    </section>
  );
}
