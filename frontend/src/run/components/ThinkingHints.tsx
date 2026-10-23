import { useEffect, useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import type { StepKind } from "../types";
import { HINT_META, hintsFor } from "../hints";

interface Props {
  context?: StepKind | "thinking";
  showLabel?: boolean;
  intervalMs?: number;
}

/** One line of guidance that changes every 3 s while agents work. */
export default function ThinkingHints({ context, showLabel = false, intervalMs = 3000 }: Props) {
  const hints = useMemo(() => hintsFor(context), [context]);
  const [i, setI] = useState(0);

  useEffect(() => setI(0), [context]);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % hints.length), intervalMs);
    return () => clearInterval(t);
  }, [hints.length, intervalMs]);

  const hint = hints[i % hints.length];
  const meta = HINT_META[hint.kind];

  return (
    <div className="flex items-start gap-3 py-1" aria-live="off">
      {showLabel && (
        <span className="mt-0.5 inline-flex shrink-0 items-center gap-1.5 text-[13.5px] font-medium">
          <Sparkles size={15} className="animate-pulse text-accent motion-reduce:animate-none" aria-hidden />
          <span className="ep-shimmer">Thinking</span>
        </span>
      )}
      <p key={hint.id} className="min-w-0 animate-fade-in text-[13px] leading-snug text-muted">
        <span className="mr-2 inline-flex items-center gap-1 rounded-md bg-surface-2 px-1.5 py-px text-[11px] font-medium text-muted">
          <span aria-hidden>{meta.emoji}</span>
          {meta.label}
        </span>
        {hint.text}
      </p>
    </div>
  );
}
