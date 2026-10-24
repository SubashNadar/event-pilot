import { useEffect, useRef, useState } from "react";
import ChatWindow from "./ChatWindow";
import StepDetailDrawer from "./StepDetailDrawer";
import { useAgent } from "../hooks/useAgentStream";

type Selected = { msgId: string; stepId: string } | null;
export default function LatestPlanWithAI({ onPlanReady, selectedHistoryEventId }: { onPlanReady: (eventId: string) => void; selectedHistoryEventId: string | null }) {
  const { state, retryStep } = useAgent();
  const [selected, setSelected] = useState<Selected>(null);
  const handedOff = useRef<string | null>(null);
  const message = selected ? state.messages.find((item) => item.id === selected.msgId) : undefined;
  const run = message?.role === "agent" ? message.run : undefined;
  const step = run && selected ? run.steps.find((item) => item.id === selected.stepId) : undefined;
  const latest = [...state.messages].reverse().find((item) => item.role === "agent");

  useEffect(() => {
    if (!state.sessionId || latest?.role !== "agent" || latest.run.status !== "completed" || handedOff.current === state.sessionId || selectedHistoryEventId === state.sessionId) return;
    handedOff.current = state.sessionId;
    onPlanReady(state.sessionId);
  }, [latest, onPlanReady, selectedHistoryEventId, state.sessionId]);

  return <section className="latest-plan-ai"><div className="latest-chat-main"><ChatWindow selected={selected} onOpenStep={(msgId, stepId) => setSelected({ msgId, stepId})} /></div>{run && step && selected && <StepDetailDrawer run={run} step={step} index={run.steps.findIndex((item) => item.id === step.id)} onClose={() => setSelected(null)} onRetry={() => retryStep(selected.msgId, step.id)} />}</section>;
}
