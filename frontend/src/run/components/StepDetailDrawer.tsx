import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import {
  AlertTriangle,
  BrainCircuit,
  Check,
  Code2,
  Copy,
  ExternalLink,
  FileText,
  Globe,
  Loader2,
  ShieldCheck,
  ShieldX,
  Wrench,
  X,
} from "lucide-react";
import type { ResolveChoice, ResolveResult, RunState, SourceRef, StepState, ToolCall } from "../types";
import { copyText, formatClock, formatDuration, formatNum, formatUsd, truncate } from "../lib/format";
import { useNow } from "../lib/useNow";
import RecoveryCard from "./RecoveryCard";
import { STATUS_LABEL, StatusIcon } from "./StepItem";

interface Props {
  run: RunState;
  step: StepState;
  index: number;
  onClose: () => void;
  onResolve: (choice: ResolveChoice) => Promise<ResolveResult>;
}

const SOURCE_ICON: Record<SourceRef["kind"], typeof Globe> = {
  memory: BrainCircuit,
  web: Globe,
  tool: Wrench,
  document: FileText,
};

const STATUS_PILL: Record<StepState["status"], string> = {
  pending: "bg-surface-2 text-muted",
  running: "bg-accent-soft text-accent",
  verifying: "bg-info/10 text-info",
  completed: "bg-success/10 text-success",
  failed: "bg-danger/10 text-danger",
  skipped: "bg-surface-2 text-muted",
};

function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="border-t border-border px-5 py-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-muted">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function ToolRow({ t }: { t: ToolCall }) {
  const input = JSON.stringify(t.input);
  return (
    <li className="rounded-xl border border-border bg-surface px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span
          className={clsx(
            "h-1.5 w-1.5 shrink-0 rounded-full",
            t.status === "success" && "bg-success",
            t.status === "error" && "bg-danger",
            t.status === "running" && "animate-pulse bg-accent",
          )}
          aria-hidden
        />
        <code className="font-mono text-[12.5px] font-medium">{t.name}</code>
        <span className="sr-only">{t.status}</span>
        <span className="ml-auto font-mono text-[11.5px] tabular-nums text-muted">
          {t.status === "running" ? <Loader2 size={12} className="animate-spin" aria-label="running" /> : formatDuration(t.latencyMs)}
        </span>
      </div>
      <p className="mt-1 truncate font-mono text-[11.5px] text-muted" title={input}>
        {truncate(input, 72)}
      </p>
      <p className={clsx("mt-1 text-[13px] leading-snug", t.status === "error" ? "text-danger" : "text-ink")}>
        {t.status === "running" ? <span className="ep-shimmer">Waiting for result…</span> : t.resultSummary}
      </p>
    </li>
  );
}

export default function StepDetailDrawer({ run, step, index, onClose, onResolve }: Props) {
  const closeBtn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [raw, setRaw] = useState(false);
  const [copied, setCopied] = useState(false);
  const live = step.status === "running" || step.status === "verifying";
  const now = useNow(live);

  useEffect(() => {
    closeBtn.current?.focus();
  }, [step.id]);

  // Esc closes; Tab stays inside the panel on mobile (modal) and desktop.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
      if (e.key === "Tab" && panel.current) {
        const f = panel.current.querySelectorAll<HTMLElement>('button, a[href], [tabindex]:not([tabindex="-1"])');
        if (!f.length) return;
        const first = f[0];
        const last = f[f.length - 1];
        if (!panel.current.contains(document.activeElement)) return;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const duration = step.startedAt ? (step.endedAt ?? now) - step.startedAt : undefined;
  const s = step.summary;

  const copyTrace = async () => {
    if (await copyText(run.traceId)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    }
  };

  return (
    <>
      <button type="button" aria-label="Close step details" tabIndex={-1} className="fixed inset-0 z-40 bg-black/30 animate-fade-in lg:hidden" onClick={onClose} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="step-detail-title"
        className={clsx(
          "ep-root fixed z-50 flex flex-col bg-bg shadow-lift",
          "inset-x-0 bottom-0 max-h-[88vh] rounded-t-3xl animate-slide-in-up",
          "lg:inset-y-0 lg:left-auto lg:right-0 lg:max-h-none lg:w-[440px] lg:rounded-none lg:border-l lg:border-border lg:shadow-none lg:animate-slide-in-right",
        )}
      >
        <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-border lg:hidden" aria-hidden />

        <header className="flex items-start gap-3 px-5 pb-4 pt-4">
          <span className="mt-0.5">
            <StatusIcon status={step.status} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[12px] text-muted">Step {index + 1} of {run.steps.length} · {step.agent}</p>
            <h2 id="step-detail-title" className="text-[17px] font-semibold leading-snug tracking-[-0.01em]">
              {step.title}
            </h2>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted">
              <span className={clsx("rounded-full px-2 py-0.5 font-medium", STATUS_PILL[step.status])}>{STATUS_LABEL[step.status]}</span>
              {step.startedAt && <span>Start {formatClock(step.startedAt)}</span>}
              {step.endedAt && <span>End {formatClock(step.endedAt)}</span>}
              {duration !== undefined && <span className="font-mono tabular-nums">{formatDuration(duration)}</span>}
              {step.attempts > 1 && <span>Attempt {step.attempts}</span>}
            </div>
          </div>
          <button ref={closeBtn} type="button" className="ep-icon-btn" onClick={onClose} aria-label="Close step details (Esc)">
            <X size={17} />
          </button>
        </header>

        <div className="ep-scroll-thin min-h-0 flex-1 overflow-y-auto pb-6">
          <Section title="Goal">
            <p className="text-[14px] leading-relaxed">{step.goal}</p>
          </Section>

          {step.status === "failed" && (
            <div className="mx-5 mb-4" role="alert">
              {step.recovery ? (
                <RecoveryCard step={step} canResolve={run.status === "awaiting_input"} onResolve={onResolve} />
              ) : (
                <div className="flex items-start gap-2.5 rounded-xl border border-danger/30 bg-danger/5 px-3.5 py-3">
                  <AlertTriangle size={16} className="mt-0.5 shrink-0 text-danger" aria-hidden />
                  <div className="min-w-0 flex-1 text-[13px]">
                    <p className="font-medium text-danger">This step failed</p>
                    <p className="mt-0.5 text-muted">{step.error}</p>
                  </div>
                </div>
              )}
            </div>
          )}

          <Section title="What I did">
            {s ? (
              <ul className="space-y-1.5 text-[14px] leading-relaxed">
                {s.did.map((d) => (
                  <li key={d} className="flex gap-2.5">
                    <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-muted" aria-hidden />
                    {d}
                  </li>
                ))}
              </ul>
            ) : step.status === "pending" ? (
              <p className="text-[13.5px] text-muted">Waiting for earlier steps to finish.</p>
            ) : step.status === "failed" || step.status === "skipped" ? (
              <p className="text-[13.5px] text-muted">{step.status === "skipped" ? step.error ?? "Skipped." : "No summary — the step didn’t complete."}</p>
            ) : (
              <div className="space-y-2 pt-1" aria-label="Working">
                <div className="ep-skeleton h-3 w-11/12" />
                <div className="ep-skeleton h-3 w-4/5" />
                <div className="ep-skeleton h-3 w-3/5" />
              </div>
            )}
          </Section>

          <Section title="Tools used" aside={<span className="text-[12px] text-muted">{step.tools.length}</span>}>
            {step.tools.length ? (
              <ul className="space-y-2">
                {step.tools.map((t) => (
                  <ToolRow key={t.id} t={t} />
                ))}
              </ul>
            ) : (
              <p className="text-[13.5px] text-muted">No tool calls yet.</p>
            )}
          </Section>

          {s && s.sources.length > 0 && (
            <Section title="Sources & memories">
              <ul className="flex flex-wrap gap-1.5">
                {s.sources.map((src) => {
                  const Icon = SOURCE_ICON[src.kind];
                  return (
                    <li key={src.id} className="ep-chip text-ink">
                      <Icon size={12} className={src.kind === "memory" ? "text-accent" : "text-muted"} aria-hidden />
                      {src.label}
                    </li>
                  );
                })}
              </ul>
            </Section>
          )}

          <Section title="Verification">
            {s ? (
              <div className={clsx("flex items-start gap-2.5 rounded-xl px-3.5 py-3", s.verification.passed ? "bg-success/10" : "bg-danger/10")}>
                {s.verification.passed ? (
                  <ShieldCheck size={17} className="mt-0.5 shrink-0 text-success" aria-hidden />
                ) : (
                  <ShieldX size={17} className="mt-0.5 shrink-0 text-danger" aria-hidden />
                )}
                <div className="text-[13.5px]">
                  <p className="font-medium">
                    <span className={s.verification.passed ? "text-success" : "text-danger"}>{s.verification.passed ? "Passed" : "Failed"}</span>
                    <span className="text-muted"> · {s.verification.check}</span>
                  </p>
                  <p className="mt-0.5 text-muted">{s.verification.reason}</p>
                </div>
              </div>
            ) : step.status === "verifying" ? (
              <p className="flex items-center gap-2 text-[13.5px] text-info">
                <Loader2 size={14} className="animate-spin" aria-hidden /> {step.verifyingCheck}
              </p>
            ) : (
              <p className="text-[13.5px] text-muted">Runs after the step executes.</p>
            )}
          </Section>

          {s && (
            <Section title="Metrics">
              <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-2">
                {[
                  ["Tokens in", formatNum(s.metrics.tokensIn)],
                  ["Tokens out", formatNum(s.metrics.tokensOut)],
                  ["Cost", s.metrics.costUsd > 0 ? formatUsd(s.metrics.costUsd) : "—"],
                  ["Model", s.metrics.model],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-xl bg-surface-2 px-3 py-2">
                    <dt className="text-[11.5px] text-muted">{k}</dt>
                    <dd className="truncate font-mono text-[12.5px] tabular-nums" title={v}>
                      {v}
                    </dd>
                  </div>
                ))}
              </dl>
            </Section>
          )}

          <Section title="Langfuse">
            <div className="space-y-2 text-[12.5px]">
              <div className="flex items-center gap-2">
                <span className="w-20 shrink-0 text-muted">Trace</span>
                <code className="min-w-0 flex-1 truncate font-mono">{run.traceId || "—"}</code>
                <button type="button" className="ep-icon-btn h-7 w-7" onClick={copyTrace} disabled={!run.traceId} aria-label={copied ? "Copied trace ID" : "Copy trace ID"}>
                  {copied ? <Check size={13} className="text-success" /> : <Copy size={13} />}
                </button>
              </div>
              {!run.traceId && <p className="text-muted">Langfuse tracing is off for this run (set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY).</p>}
              {run.traceUrl && (
                <a
                  href={run.traceUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 font-medium transition-colors duration-150 hover:bg-surface-2"
                >
                  Open in Langfuse <ExternalLink size={12} aria-hidden />
                </a>
              )}
            </div>
          </Section>

          <Section
            title="Raw"
            aside={
              <button
                type="button"
                onClick={() => setRaw((r) => !r)}
                aria-expanded={raw}
                className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px] text-muted hover:bg-surface-2 hover:text-ink"
              >
                <Code2 size={13} aria-hidden /> {raw ? "Hide raw" : "Show raw"}
              </button>
            }
          >
            {raw ? (
              <pre className="ep-scroll-thin max-h-80 overflow-auto rounded-xl bg-surface-2 p-3 font-mono text-[11.5px] leading-relaxed">
                {JSON.stringify(step, null, 2)}
              </pre>
            ) : (
              <p className="text-[12.5px] text-muted">The step object exactly as the reducer holds it — for developers.</p>
            )}
          </Section>
        </div>
      </div>
    </>
  );
}
