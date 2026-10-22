import { useEffect, useMemo, useRef, useState } from "react";
import ChatWindow from "./ChatWindow";
import StepDetailDrawer from "./StepDetailDrawer";
import { useAgent } from "../hooks/useAgentStream";

type Selected = { msgId: string; stepId: string } | null;
const GROUPS = ["Today", "Yesterday", "Previous 7 days", "Older"];
const groupFor = (value: string) => {
  const date = new Date(value); const today = new Date(); const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const days = Math.floor((start.getTime() - new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()) / 86400000);
  if (days <= 0) return "Today"; if (days === 1) return "Yesterday"; if (days <= 7) return "Previous 7 days"; return "Older";
};

export default function LatestPlanWithAI({ onPlanReady, onHistoryOpen, selectedHistoryEventId }: { onPlanReady: (eventId: string) => void; onHistoryOpen: (eventId: string | null) => void; selectedHistoryEventId: string | null }) {
  const { state, newSession, openSession, retryStep } = useAgent();
  const [selected, setSelected] = useState<Selected>(null);
  const [query, setQuery] = useState("");
  const handedOff = useRef<string | null>(null);
  const openedFromHistory = useRef<string | null>(null);
  const message = selected ? state.messages.find((item) => item.id === selected.msgId) : undefined;
  const run = message?.role === "agent" ? message.run : undefined;
  const step = run && selected ? run.steps.find((item) => item.id === selected.stepId) : undefined;
  const latest = [...state.messages].reverse().find((item) => item.role === "agent");
  const history = useMemo(() => {
    const term = query.trim().toLowerCase();
    const sessions = term ? state.sessions.filter((item) => `${item.title} ${item.eventName}`.toLowerCase().includes(term)) : state.sessions;
    return GROUPS.map((group) => [group, sessions.filter((item) => groupFor(item.updatedAt) === group)] as const).filter(([, sessions]) => sessions.length);
  }, [query, state.sessions]);

  useEffect(() => {
    if (!state.sessionId || latest?.role !== "agent" || latest.run.status !== "completed" || handedOff.current === state.sessionId || openedFromHistory.current === state.sessionId || selectedHistoryEventId === state.sessionId) return;
    handedOff.current = state.sessionId;
    onPlanReady(state.sessionId);
  }, [latest, onPlanReady, selectedHistoryEventId, state.sessionId]);

  return <section className="latest-plan-ai"><aside className="chat-history-rail" aria-label="Conversation history"><button className="history-new" type="button" onClick={() => { openedFromHistory.current = null; onHistoryOpen(null); newSession(); }}><span>+</span> New plan</button><label className="history-search"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search plans" /></label><div className="history-groups">{history.length ? history.map(([group, sessions]) => <section key={group}><p>{group}</p>{sessions.map((session) => <button type="button" key={session.id} onClick={() => { openedFromHistory.current = session.id; onHistoryOpen(session.id); openSession(session.id); }} className={state.sessionId === session.id ? "active" : ""}><strong>{session.title}</strong><small>{session.eventName} · {session.eventDate}</small></button>)}</section>) : <p className="history-empty">No matching plans.</p>}</div></aside><div className="latest-chat-main"><ChatWindow selected={selected} onOpenStep={(msgId, stepId) => setSelected({ msgId, stepId})} /></div>{run && step && selected && <StepDetailDrawer run={run} step={step} index={run.steps.findIndex((item) => item.id === step.id)} onClose={() => setSelected(null)} onRetry={() => retryStep(selected.msgId, step.id)} />}</section>;
}
