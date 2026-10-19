import { useEffect, useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import type { StepKind } from "../types/types";

/** Lines that fit any stage of a plan. Playful, with a few planner proverbs mixed in. */
const GENERAL = [
  "Thinking…",
  "Cooking up your plan…",
  "Stirring the ideas together…",
  "Measuring twice, booking once…",
  "Good plans take time.",
  "A well-begun event is half done.",
  "Rome wasn't planned in a day.",
];

/** Lines for the step that is running now, shown first while it runs. */
const BY_STEP: Partial<Record<StepKind, string[]>> = {
  venues: ["Scouting venues…", "Checking who can host this crowd…", "Looking for the right view…"],
  budget: ["Counting every rupee…", "Adding a little contingency…", "Keeping the numbers honest…"],
  itinerary: ["Sketching the agenda…", "Fitting the sessions in…", "Leaving room for the chai break…"],
  availability: ["Checking the calendar…", "Making sure the date works…"],
  requirements: ["Listing what we'll need…", "Making a checklist for the day…"],
  activities: ["Choosing the fun bits…", "Finding something guests will remember…"],
};

interface Props {
  /** The step that is running, if any; its lines come first. */
  context?: StepKind | "thinking";
  intervalMs?: number;
}

/** A status line that rotates through playful phrases while the planner works. */
export default function PlannerLoader({ context, intervalMs = 2200 }: Props) {
  const phrases = useMemo(() => {
    const stepLines = context && context !== "thinking" ? BY_STEP[context] ?? [] : [];
    return [...stepLines, ...GENERAL];
  }, [context]);
  const [i, setI] = useState(0);

  // A new step starts from its own first line.
  useEffect(() => setI(0), [context]);

  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % phrases.length), intervalMs);
    return () => clearInterval(t);
  }, [phrases.length, intervalMs]);

  return (
    <div className="flex items-center gap-2.5 py-1">
      <Sparkles size={15} className="shrink-0 animate-pulse text-accent motion-reduce:animate-none" aria-hidden />
      <p key={phrases[i]} className="shimmer-text animate-fade-in text-[13.5px] font-medium">
        {phrases[i]}
      </p>
    </div>
  );
}
