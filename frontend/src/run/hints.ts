import type { StepKind } from "./types";

export type HintKind = "tip" | "behind" | "didyouknow";

export interface Hint {
  id: string;
  kind: HintKind;
  text: string;
  context?: StepKind | "thinking";
}

export const HINT_META: Record<HintKind, { emoji: string; label: string }> = {
  tip: { emoji: "💡", label: "Tip" },
  behind: { emoji: "🔍", label: "Behind the scenes" },
  didyouknow: { emoji: "🧠", label: "Did you know" },
};

/** One plain sentence each, about a real planning concern. No jokes, no exclamation marks. */
export const HINTS: Hint[] = [
  { id: "t1", kind: "behind", context: "thinking", text: "The Event Manager is handing your brief to six specialists who work in parallel." },
  { id: "l1", kind: "behind", context: "logistics", text: "Logistics is matching venues to your guest count and a venue budget of about 30% of the total." },
  { id: "l2", kind: "tip", context: "logistics", text: "If no venue fits, you can widen the area, raise the venue share or plan for fewer guests." },
  { id: "f1", kind: "behind", context: "finance", text: "Finance is drafting six budget lines and keeping a contingency reserve." },
  { id: "f2", kind: "tip", context: "finance", text: "A 5–10% contingency usually covers late headcount changes and vendor surcharges." },
  { id: "s1", kind: "behind", context: "schedule", text: "Schedule is checking every agenda slot for overlaps and 12-hour times." },
  { id: "s2", kind: "tip", context: "schedule", text: "Leave 15 minutes between sessions so guests can move rooms without delays." },
  { id: "r1", kind: "behind", context: "requirements", text: "Requirements is listing what this event type needs to run on the day." },
  { id: "m1", kind: "behind", context: "marketing", text: "Marketing is choosing channels; nothing is sent without your approval." },
  { id: "m2", kind: "tip", context: "marketing", text: "A WhatsApp reminder 48 hours before the event noticeably cuts no-shows." },
  { id: "k1", kind: "behind", context: "risk", text: "Risk & Operations is making sure every high risk has a fallback." },
  { id: "k2", kind: "tip", context: "risk", text: "Outdoor events between June and September need a covered backup in most Indian cities." },
  { id: "g1", kind: "behind", context: "manager", text: "The Event Manager is merging the specialists' work into one plan within budget." },
  { id: "v1", kind: "behind", context: "review", text: "The review checks that budget lines add up and the agenda uses valid times." },
  { id: "x1", kind: "behind", context: "reflection", text: "The review found issues, so the Event Manager is revising the plan once." },
  { id: "c1", kind: "behind", context: "recommend", text: "Writing your summary and the next steps to act on." },
  { id: "d1", kind: "didyouknow", text: "Click any step to see the tools it called, what it found and how it was checked." },
  { id: "d2", kind: "didyouknow", text: "If a step fails, you choose what happens next: pick an option or type your own." },
  { id: "d3", kind: "didyouknow", text: "You can close this page; the plan keeps going and picks up where you left off." },
];

export function hintsFor(context?: StepKind | "thinking"): Hint[] {
  const specific = HINTS.filter((h) => h.context === context);
  const general = HINTS.filter((h) => !h.context);
  return [...specific, ...general];
}
