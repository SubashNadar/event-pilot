import { useState } from "react";
import clsx from "clsx";
import { ChevronDown, CornerDownLeft, Loader2, MessageCircleQuestion, RotateCcw, SkipForward, Sparkles } from "lucide-react";
import type { ResolveChoice, ResolveResult, StepState } from "../types";
import PlanPreview from "./PlanPreview";

interface Props {
  step: StepState;
  /** True while the run is paused on this step. */
  canResolve: boolean;
  onResolve: (choice: ResolveChoice) => Promise<ResolveResult>;
  compact?: boolean;
}

/**
 * What a failed step shows: what went wrong in plain words, a few ways forward
 * as chips, a free-text box for anything else, and Skip. The LLM writes the
 * summary and options; the backend validates every option before it runs.
 */
export default function RecoveryCard({ step, canResolve, onResolve, compact = false }: Props) {
  const proposal = step.recovery;
  const [busy, setBusy] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [question, setQuestion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCause, setShowCause] = useState(false);

  if (!proposal) return null;

  if (step.chosen) {
    return (
      <p className="mt-1.5 flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2 text-[12.5px] text-muted" role="status">
        <Loader2 size={13} className="animate-spin text-accent" aria-hidden />
        <span>
          <span className="font-medium text-ink">{step.chosen.label}</span> — waiting for your other decisions before continuing.
        </span>
      </p>
    );
  }

  const send = async (key: string, choice: ResolveChoice) => {
    setBusy(key);
    setError(null);
    try {
      const result = await onResolve(choice);
      if (result.status === "needs_clarification") {
        setQuestion(result.question ?? "Could you say what to change?");
      } else {
        setQuestion(null);
        setText("");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send your choice. Try again.");
    } finally {
      setBusy(null);
    }
  };

  const review = Boolean(proposal.preview);  // an approval to review, not an error to fix
  const options = proposal.options.filter((o) => o.action !== "skip");
  const skip = proposal.options.find((o) => o.action === "skip");
  const disabled = !canResolve || busy !== null;

  return (
    <div role="group" aria-label={`Recovery options for ${step.title}`} className={clsx("rounded-xl border", review ? "border-accent/30 bg-accent-soft/40" : "border-danger/25 bg-danger/[0.04]", compact ? "mt-2 px-3 py-2.5" : "px-3.5 py-3")}>
      <p className="flex items-start gap-1.5 text-[13.5px] font-medium leading-snug text-ink">
        {proposal.source === "llm" && <Sparkles size={14} className="mt-0.5 shrink-0 text-accent" aria-label="Explained by EventPilot" />}
        {proposal.summary}
      </p>
      {proposal.preview && <PlanPreview preview={proposal.preview} compact={compact} />}
      {proposal.cause && (
        <button type="button" onClick={() => setShowCause((s) => !s)} aria-expanded={showCause} className="mt-1 inline-flex items-center gap-1 text-[12px] text-muted hover:text-ink">
          <ChevronDown size={12} className={clsx("transition-transform duration-150", showCause && "rotate-180")} aria-hidden />
          {showCause ? "Hide error" : "Show error"}
        </button>
      )}
      {showCause && <p className="mt-1 break-words rounded-md bg-surface-2 px-2 py-1.5 font-mono text-[11.5px] text-muted">{proposal.cause}</p>}

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            disabled={disabled}
            title={option.description}
            onClick={() => send(option.id, { option_id: option.id })}
            className={clsx(
              "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition-colors duration-150 disabled:opacity-50",
              option.action === "retry" ? "border-border bg-surface text-ink hover:bg-surface-2" : "border-ink/15 bg-surface text-ink hover:border-accent hover:text-accent",
            )}
          >
            {busy === option.id ? <Loader2 size={12} className="animate-spin" aria-hidden /> : option.action === "retry" ? <RotateCcw size={12} aria-hidden /> : null}
            {option.label}
            <span className="sr-only">. {option.description}</span>
          </button>
        ))}
      </div>

      <form
        className="mt-2 flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) send("custom", { custom_text: text.trim() });
        }}
      >
        <label className="sr-only" htmlFor={`recovery-${step.id}`}>
          Something else for {step.title}
        </label>
        <input
          id={`recovery-${step.id}`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
          maxLength={500}
          placeholder={`Something else… ${proposal.customPrompt ? `(${proposal.customPrompt.toLowerCase()})` : ""}`}
          className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-1.5 text-[13px] text-ink outline-none placeholder:text-muted focus:border-accent disabled:opacity-50"
        />
        <button type="submit" disabled={disabled || !text.trim()} className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-[12.5px] font-medium text-bg transition-opacity duration-150 hover:opacity-90 disabled:opacity-40">
          {busy === "custom" ? <Loader2 size={13} className="animate-spin" aria-hidden /> : <CornerDownLeft size={13} aria-hidden />}
          Send
        </button>
        {skip && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => send("skip", { option_id: skip.id })}
            title={skip.description}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[12.5px] text-muted transition-colors duration-150 hover:bg-surface-2 hover:text-ink disabled:opacity-50"
          >
            {busy === "skip" ? <Loader2 size={13} className="animate-spin" aria-hidden /> : <SkipForward size={13} aria-hidden />}
            <span className="hidden sm:inline">{skip.label}</span>
            <span className="sm:hidden">Skip</span>
          </button>
        )}
      </form>

      {question && (
        <p className="mt-2 flex items-start gap-1.5 text-[12.5px] text-info" role="status">
          <MessageCircleQuestion size={14} className="mt-px shrink-0" aria-hidden /> {question}
        </p>
      )}
      {error && (
        <p className="mt-2 text-[12.5px] text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
