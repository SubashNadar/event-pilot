import { useState } from "react";
import clsx from "clsx";
import { AlertTriangle, Check, Copy, ExternalLink, RefreshCw, Square, ThumbsDown, ThumbsUp } from "lucide-react";
import type { AgentMessage as AgentMessageT, BriefQuestion, BriefWarning, StepKind, StepState } from "../types/types";
import type { ResolveResult } from "../lib/api";
import { useAgent } from "../hooks/useAgentStream";
import { copyText, formatDuration, formatUsd } from "../lib/format";
import { traceUrl } from "../lib/langfuse";
import { API_BASE_URL } from "../lib/config";
import MemoryRecall from "./MemoryRecall";
import PlannerLoader from "./PlannerLoader";
import StepTimeline from "./StepTimeline";
import StreamingMarkdown from "./StreamingMarkdown";
import { STATUS_LABEL } from "./StepItem";
import { EventPilotMark } from "./Logo";

interface Props {
  message: AgentMessageT;
  selectedStepId: string | null;
  onOpenStep: (msgId: string, stepId: string) => void;
}

/** Download links for the finished plan: a PPTX brochure and a PDF blueprint. */
function PlanExports({ eventId }: { eventId: string }) {
  const base = `${API_BASE_URL}/events/${eventId}/exports`;
  const link = "inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-[13px] font-medium transition-colors duration-150 hover:border-accent/50 hover:text-accent";
  return (
    <div role="group" aria-label="Download the final plan" className="flex flex-wrap items-center gap-2 pt-1">
      <span className="text-[12.5px] text-muted">Download the final plan</span>
      <a href={`${base}/pptx`} download className={link}>Brochure (PPTX)</a>
      <a href={`${base}/pdf`} download className={link}>Blueprint (PDF)</a>
    </div>
  );
}

/** Doubts about the brief, each with fixes to pick from or a "keep as is". */
function WarningCards({ warnings, onApply, onKeep }: { warnings: BriefWarning[]; onApply: (label: string, patch: Record<string, string>) => void; onKeep: (id: string) => void }) {
  return (
    <div className="space-y-2">
      {warnings.map((warning) => (
        <div key={warning.id} role="group" aria-label="Something to check" className="rounded-xl border border-warn/30 bg-warn/5 px-3.5 py-3">
          <p className="flex items-start gap-2 text-[13.5px]">
            <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warn" aria-hidden />
            <span>{warning.message}</span>
          </p>
          <div className="mt-2.5 flex flex-wrap gap-2">
            {warning.options.map((option) => (
              <button
                key={option.label}
                type="button"
                onClick={() => onApply(option.label, option.patch)}
                className="rounded-full border border-border bg-surface px-3 py-1.5 text-[13px] text-ink transition-colors duration-150 hover:border-accent/50 hover:text-accent"
              >
                {option.label}
              </button>
            ))}
            <button type="button" onClick={() => onKeep(warning.id)} className="rounded-full px-3 py-1.5 text-[13px] text-muted hover:text-ink">
              Keep as is
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

/** A failed step: what went wrong, the planner's options, and a box for the owner's own change. */
function RecoveryCard({
  msgId,
  step,
  onResolve,
}: {
  msgId: string;
  step: StepState;
  onResolve: (msgId: string, stepId: string, choice: { optionId?: string; customText?: string }) => Promise<ResolveResult>;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const proposal = step.recovery;

  const send = async (choice: { optionId?: string; customText?: string }) => {
    setBusy(true);
    setQuestion(null);
    setProblem(null);
    try {
      const result = await onResolve(msgId, step.id, choice);
      if (result.status === "needs_clarification") setQuestion(result.question ?? "Could you say that another way?");
      else setText("");
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "That didn't go through. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const inputId = `recovery-${msgId}-${step.id}`;
  return (
    <div role="group" aria-label="What would you like to do?" className="space-y-3 rounded-xl border border-warn/30 bg-warn/5 px-3.5 py-3">
      <div className="flex items-start gap-2.5 text-[13.5px]">
        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warn" aria-hidden />
        <div className="min-w-0">
          <p className="font-medium">{proposal?.summary ?? `I'm stuck on “${step.title}”.`}</p>
          <p className="mt-1 text-muted">Pick one of these, or tell me what you'd like instead. Everything else in the plan is kept.</p>
        </div>
      </div>
      {proposal && proposal.options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {proposal.options.map((option) => (
            <button
              key={option.id}
              type="button"
              disabled={busy}
              title={option.description || undefined}
              onClick={() => send({ optionId: option.id })}
              className="rounded-full border border-border bg-surface px-3 py-1.5 text-[13px] text-ink transition-colors duration-150 hover:border-accent/50 hover:text-accent disabled:opacity-40"
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (text.trim() && !busy) void send({ customText: text.trim() });
        }}
      >
        <label htmlFor={inputId} className="sr-only">
          Your own change
        </label>
        <input
          id={inputId}
          value={text}
          onChange={(event) => setText(event.target.value)}
          disabled={busy}
          placeholder={proposal?.customPrompt || "Tell me what to change"}
          className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-[13px] focus:outline-none focus:ring-2 focus:ring-accent/30"
        />
        <button type="submit" disabled={busy || !text.trim()} className="rounded-lg bg-accent px-3.5 py-2 text-[13px] font-medium text-accent-ink disabled:opacity-40">
          Send
        </button>
      </form>
      {question && (
        <p role="status" className="text-[13px] text-ink">
          {question}
        </p>
      )}
      {problem && (
        <p role="alert" className="text-[13px] text-danger">
          {problem}
        </p>
      )}
    </div>
  );
}

/** One-click answers for the brief question the planner is asking. */
function QuestionChips({ question, onPick }: { question: BriefQuestion; onPick: (field: string, value: string, label: string) => void }) {
  if (!question.options.length) return null;
  return (
    <div role="group" aria-label={question.prompt} className="flex flex-wrap gap-2 pt-1">
      {question.options.map((option) => (
        <button
          key={option.value}
          type="button"
          title={option.hint || undefined}
          onClick={() => onPick(question.field, option.value, option.label)}
          className="rounded-full border border-border bg-surface px-3 py-1.5 text-[13px] text-ink transition-colors duration-150 hover:border-accent/50 hover:text-accent"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export default function AgentMessage({ message, selectedStepId, onOpenStep }: Props) {
  const { run } = message;
  const { retryStep, skipStep, regenerate, sendFeedback, answerOption, answerPatch, keepWarning, resolveStep, isStreaming } = useAgent();
  const [copied, setCopied] = useState(false);

  const current = run.steps.find((s) => s.status === "running" || s.status === "verifying");
  const failed = run.steps.find((s) => s.status === "failed");
  const preAnswer = run.status === "starting" || run.status === "thinking" || run.status === "executing";
  const terminal = run.status === "completed" || run.status === "stopped" || run.status === "error";
  const hintContext: StepKind | "thinking" | undefined = current?.kind ?? (run.steps.length ? (run.hintContext as StepKind) : "thinking");

  // Polite live-region text for screen readers.
  const liveText = (() => {
    if (run.status === "thinking" && !run.steps.length) return "Event Pilot is thinking.";
    if (failed && run.status === "awaiting_retry") return `Step failed: ${failed.title}. Retry or skip.`;
    if (current) return `${current.title}: ${STATUS_LABEL[current.status]}.`;
    if (run.status === "answering") return "Writing the answer.";
    if (run.status === "completed") return "Plan complete.";
    if (run.status === "stopped") return "Stopped. Partial result kept.";
    if (run.status === "error") return `Error: ${run.error}`;
    return "";
  })();

  const doCopy = async () => {
    if (await copyText(run.answer)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    }
  };

  return (
    <article className="flex gap-3 sm:gap-4" aria-label="Event Pilot response">
      <EventPilotMark size={28} className="mt-0.5 hidden sm:block" />
      <div className="min-w-0 flex-1 space-y-3">
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          {liveText}
        </div>

        {(run.memories.length > 0 || !run.memoryEnabled) && <MemoryRecall memories={run.memories} enabled={run.memoryEnabled} />}

        {run.status === "starting" && <PlannerLoader />}

        {preAnswer && run.status !== "starting" && (
          <PlannerLoader context={hintContext} />
        )}

        {run.steps.length > 0 && (
          <StepTimeline
            msgId={message.id}
            run={run}
            selectedStepId={selectedStepId}
            onOpenStep={(id) => onOpenStep(message.id, id)}
            onRetryStep={(id) => retryStep(message.id, id)}
            onSkipStep={(id) => skipStep(message.id, id)}
          />
        )}

        {run.status === "awaiting_retry" && failed && <RecoveryCard msgId={message.id} step={failed} onResolve={resolveStep} />}

        {(run.answer || run.status === "answering") && (
          <StreamingMarkdown content={run.answer} streaming={run.status === "answering"} reveal={message.question !== undefined} />
        )}

        {run.status === "completed" && run.eventId && <PlanExports eventId={run.eventId} />}
        {message.warnings && message.warnings.length > 0 && !isStreaming && <WarningCards warnings={message.warnings} onApply={answerPatch} onKeep={keepWarning} />}
        {message.question && !isStreaming && <QuestionChips question={message.question} onPick={answerOption} />}

        {run.status === "stopped" && (
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-surface-2/60 px-3.5 py-2.5 text-[13px] text-muted">
            <Square size={12} className="fill-current" aria-hidden />
            <span className="flex-1">
              You stopped this run. {run.answer ? "The answer above is partial." : "Completed steps are kept above."}
            </span>
            <button type="button" onClick={() => regenerate(message.id)} disabled={isStreaming} className="inline-flex items-center gap-1.5 font-medium text-ink hover:underline disabled:opacity-40">
              <RefreshCw size={13} /> Run again
            </button>
          </div>
        )}

        {run.status === "error" && (
          <div role="alert" className="flex flex-wrap items-start gap-2.5 rounded-xl border border-danger/30 bg-danger/5 px-3.5 py-3 text-[13.5px]">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-danger" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-danger">The run stopped unexpectedly</p>
              <p className="mt-0.5 text-muted">{run.error}</p>
            </div>
            <button
              type="button"
              onClick={() => regenerate(message.id)}
              disabled={isStreaming}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-[12.5px] font-medium hover:bg-surface-2 disabled:opacity-40"
            >
              <RefreshCw size={13} /> Try again
            </button>
          </div>
        )}

        {terminal && (
          <div className="flex flex-wrap items-center gap-0.5 pt-1 text-muted animate-fade-in">
            <button type="button" className="icon-btn" onClick={doCopy} disabled={!run.answer} aria-label={copied ? "Copied" : "Copy answer"} title="Copy">
              {copied ? <Check size={15} className="text-success" /> : <Copy size={15} />}
            </button>
            <button type="button" className="icon-btn" onClick={() => regenerate(message.id)} disabled={isStreaming} aria-label="Regenerate" title="Regenerate">
              <RefreshCw size={15} />
            </button>
            <button
              type="button"
              className={clsx("icon-btn", run.feedback === "up" && "bg-surface-2 text-success")}
              onClick={() => sendFeedback(message.id, "up")}
              aria-pressed={run.feedback === "up"}
              aria-label="Good response"
              title="Good response — sends a Langfuse score"
            >
              <ThumbsUp size={15} />
            </button>
            <button
              type="button"
              className={clsx("icon-btn", run.feedback === "down" && "bg-surface-2 text-danger")}
              onClick={() => sendFeedback(message.id, "down")}
              aria-pressed={run.feedback === "down"}
              aria-label="Bad response"
              title="Bad response — sends a Langfuse score"
            >
              <ThumbsDown size={15} />
            </button>
            {run.traceId && (
              <a
                href={traceUrl(run.traceId)}
                target="_blank"
                rel="noreferrer"
                className="ml-1 inline-flex h-8 items-center gap-1 rounded-lg px-2 text-[12.5px] transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
              >
                View trace <ExternalLink size={12} aria-hidden />
              </a>
            )}
            {run.usage && (
              <span className="ml-auto hidden font-mono text-[11.5px] tabular-nums sm:inline">
                {run.steps.length} steps · {formatDuration(run.usage.durationMs)} · {(run.usage.tokensIn + run.usage.tokensOut).toLocaleString("en-IN")} tok · {formatUsd(run.usage.costUsd)}
              </span>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
