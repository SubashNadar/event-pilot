import { useState } from "react";
import clsx from "clsx";
import { BrainCircuit, ChevronDown } from "lucide-react";
import type { Memory } from "../types/types";

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

export default function MemoryRecall({ memories, enabled }: { memories: Memory[]; enabled: boolean }) {
  const [open, setOpen] = useState(false);

  if (!enabled) {
    return (
      <span className="chip">
        <BrainCircuit size={13} aria-hidden /> Memory off for this plan
      </span>
    );
  }
  if (!memories.length) return null;

  return (
    <div className="animate-fade-in">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="chip transition-colors duration-150 hover:bg-surface-2 hover:text-ink"
      >
        <BrainCircuit size={13} className="text-accent" aria-hidden />
        Used {memories.length} memories from past sessions
        <ChevronDown size={13} className={clsx("transition-transform duration-200", open && "rotate-180")} aria-hidden />
      </button>

      {open && (
        <ul className="mt-2 space-y-2 animate-fade-in">
          {memories.map((m) => (
            <li key={m.id} className="rounded-xl border border-border bg-surface px-3.5 py-2.5">
              <p className="text-[13.5px] leading-snug">“{m.snippet}”</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted">
                <span>
                  From <span className="font-medium text-ink">{m.sourceSessionTitle}</span> · {fmtDate(m.sourceDate)}
                </span>
                <span className="inline-flex items-center gap-1.5" title="Relevance score from the retriever">
                  <span className="relative h-1 w-12 overflow-hidden rounded-full bg-surface-2" aria-hidden>
                    <span className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: `${m.relevance * 100}%` }} />
                  </span>
                  <span className="font-mono tabular-nums">{m.relevance.toFixed(2)}</span>
                  <span className="sr-only">relevance</span>
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
