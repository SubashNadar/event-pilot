import type { SessionSummary } from "../types/types";

export type SessionGroup = "Today" | "Yesterday" | "Previous 7 days" | "Older";

const DAY = 86_400_000;

/** Buckets sidebar sessions by how recently they were updated. Empty groups are dropped. */
export function groupSessions(list: SessionSummary[]): [SessionGroup, SessionSummary[]][] {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const t0 = startOfToday.getTime();
  const groups: Record<SessionGroup, SessionSummary[]> = { Today: [], Yesterday: [], "Previous 7 days": [], Older: [] };
  for (const s of list) {
    const t = new Date(s.updatedAt).getTime();
    if (t >= t0) groups.Today.push(s);
    else if (t >= t0 - DAY) groups.Yesterday.push(s);
    else if (t >= t0 - 7 * DAY) groups["Previous 7 days"].push(s);
    else groups.Older.push(s);
  }
  return (Object.entries(groups) as [SessionGroup, SessionSummary[]][]).filter(([, v]) => v.length);
}
