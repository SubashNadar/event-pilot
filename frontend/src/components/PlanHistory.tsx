import { useMemo } from "react";
import { useAgent } from "../hooks/useAgentStream";

const GROUPS = ["Today", "Yesterday", "Previous 7 days", "Older"];
const groupFor = (value: string) => {
  const date = new Date(value); const today = new Date(); const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const days = Math.floor((start.getTime() - new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()) / 86400000);
  if (days <= 0) return "Today"; if (days === 1) return "Yesterday"; if (days <= 7) return "Previous 7 days"; return "Older";
};

/** Saved plans and conversations, shown inside the main sidebar. */
export default function PlanHistory({ onHistoryOpen }: { onHistoryOpen: (eventId: string | null) => void }) {
  const { state, openSession } = useAgent();
  /* The three most recent conversations and plans, grouped by day. */
  const history = useMemo(() => {
    const sessions = state.sessions.slice(0, 3);
    return GROUPS.map((group) => [group, sessions.filter((item) => groupFor(item.updatedAt) === group)] as const).filter(([, sessions]) => sessions.length);
  }, [state.sessions]);

  return <div className="history-panel">
    <div className="history-head"><span>Recent plans</span></div>
    <div className="history-groups">{history.length ? history.map(([group, sessions]) => <section key={group} aria-label={group}><p>{group}</p>{sessions.map((session) => <button type="button" key={session.id} onClick={() => { onHistoryOpen(session.id); openSession(session.id); }} className={state.sessionId === session.id ? "active" : ""}><strong>{session.title}</strong><small>{session.eventName} · {session.eventDate}</small></button>)}</section>) : <p className="history-empty">{state.sessions.length ? "No plans match your search." : "No plans yet. Describe an event to start your first plan."}</p>}</div>
  </div>;
}
