import clsx from "clsx";

interface MarkProps {
  className?: string;
  size?: number;
}

/**
 * The Event Pilot mark: a terracotta tile with a dashed flight trail that
 * leads from a departure pin to a sparkle, the destination of the plan.
 */
export function EventPilotMark({ className, size = 28 }: MarkProps) {
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} className={clsx("shrink-0", className)} aria-hidden>
      <defs>
        <linearGradient id="ep-mark-bg" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#D0643D" />
          <stop offset="1" stopColor="#7E2C14" />
        </linearGradient>
        <radialGradient id="ep-mark-glow" cx="0.3" cy="0.2" r="0.85">
          <stop offset="0" stopColor="#fff" stopOpacity="0.38" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="48" height="48" rx="13" fill="url(#ep-mark-bg)" />
      <rect width="48" height="48" rx="13" fill="url(#ep-mark-glow)" />
      <path d="M11 34Q22 12 36 15" fill="none" stroke="#fff" strokeOpacity="0.55" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M11 34Q22 12 36 15" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeDasharray="0.1 4" />
      <circle cx="11" cy="34" r="3.2" fill="#fff" />
      <path d="M36 9Q37 14 42 15Q37 16 36 21Q35 16 30 15Q35 14 36 9Z" fill="#fff" />
    </svg>
  );
}

/** Mark plus the wordmark: "Event" in sans, "Pilot" in serif italic, the one warm accent word. */
export function EventPilotLogo({ className, markSize = 28 }: MarkProps & { markSize?: number }) {
  return (
    <span className={clsx("inline-flex min-w-0 items-center gap-2.5", className)}>
      <EventPilotMark size={markSize} />
      <span className="flex min-w-0 items-baseline whitespace-nowrap text-[16px] leading-none tracking-[-0.01em]">
        <span className="font-semibold">Event</span>
        <span className="ml-1 font-serif text-[17px] italic text-accent">Pilot</span>
      </span>
    </span>
  );
}
