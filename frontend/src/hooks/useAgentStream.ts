/**
 * useAgentStream — the ONLY place that talks to the EventPilot backend.
 *
 * A chat turn works in two stages:
 *   1. Brief intake: `/chat/brief` extracts the event details from the message
 *      and asks for what is missing. Until the brief is ready, the reply is
 *      plain text and no run starts.
 *   2. Planning run: once the brief is ready, the event is saved, a run starts,
 *      and `/runs/:id/stream` (SSE) feeds the agent message. Retry, skip and
 *      stop call the run endpoints.
 * The reducer and every component stay independent of the transport.
 */
import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from "react";
import type {
  AgentEvent,
  AgentMessage,
  BriefQuestion,
  BriefWarning,
  ChatMessage,
  ConnectionState,
  Feedback,
  RunState,
  SessionSummary,
  StepKind,
  StepState,
} from "../types/types";
import * as api from "../lib/api";
import type { ResolveResult } from "../lib/api";

/* ------------------------------------------------------------------ */
/* State                                                                */
/* ------------------------------------------------------------------ */

export interface ChatState {
  /** The saved event this conversation is showing, or null while a brief is in progress. */
  sessionId: string | null;
  title: string;
  sessions: SessionSummary[];
  messages: ChatMessage[];
  activeMessageId: string | null;
  connection: ConnectionState;
}

type Action =
  | { type: "user_sent"; user: ChatMessage; agent: AgentMessage; title?: string }
  | { type: "event"; msgId: string; event: AgentEvent; at: number }
  | { type: "reply"; msgId: string; text: string; question?: BriefQuestion | null; warnings?: BriefWarning[] }
  | { type: "reset_run"; msgId: string; runId: string }
  | { type: "stopped"; msgId: string; at: number }
  | { type: "step_skipped"; msgId: string; stepId: string; at: number }
  | { type: "closed"; msgId: string }
  | { type: "connection"; state: ConnectionState }
  | { type: "feedback"; msgId: string; value: Feedback }
  | { type: "load_session"; session: SessionSummary; messages: ChatMessage[]; activeMessageId: string }
  | { type: "set_event"; id: string; title: string }
  | { type: "sessions"; list: SessionSummary[] }
  | { type: "new_session" }
  | { type: "rename"; title: string }
  | { type: "truncate_from"; msgId: string };

const initialState: ChatState = {
  sessionId: null,
  title: "New plan",
  sessions: [],
  messages: [],
  activeMessageId: null,
  connection: "connected",
};

/** Event types after which the server sends nothing more on the stream. */
const TERMINAL_EVENTS = new Set(["run_completed", "run_cancelled", "error"]);

/** Backend step kinds (event_workflow.STEPS) mapped onto the Eventa kinds used for icons and hints. */
const STEP_KIND: Record<string, StepKind> = {
  logistics: "venues",
  finance: "budget",
  schedule: "itinerary",
  requirements: "requirements",
  marketing: "activities",
  risk: "availability",
  manager: "itinerary",
  review: "availability",
  reflection: "budget",
  recommend: "activities",
  coordinate: "availability",
  intake: "itinerary",
};

const emptyRun = (runId = "", now = Date.now()): RunState => ({
  runId,
  traceId: "",
  status: "starting",
  startedAt: now,
  memories: [],
  memoryEnabled: true,
  steps: [],
  answer: "",
  feedback: null,
});

const patchStep = (run: RunState, stepId: string, fn: (s: StepState) => StepState): RunState => ({
  ...run,
  steps: run.steps.map((s) => (s.id === stepId ? fn(s) : s)),
});

/** Marks unfinished work as stopped, keeping completed steps as they were. */
function stopRun(run: RunState, at: number): RunState {
  return {
    ...run,
    status: "stopped",
    endedAt: at,
    steps: run.steps.map((s) =>
      s.status === "running" || s.status === "verifying" || s.status === "pending" || s.status === "failed"
        ? { ...s, status: "skipped", endedAt: s.startedAt ? at : undefined, error: s.startedAt ? "Stopped by you mid-step." : "Not run — you stopped the plan." }
        : s,
    ),
  };
}

/** Pure: apply one wire event to a run. */
export function reduceRun(run: RunState, e: AgentEvent, at: number): RunState {
  switch (e.type) {
    case "run_started":
      return { ...run, runId: e.runId, traceId: e.traceId, status: "thinking", startedAt: at, eventId: e.eventId };
    case "memory_retrieved":
      return { ...run, memories: e.memories };
    case "thinking":
      return { ...run, hintContext: e.hintContext, status: run.status === "starting" ? "thinking" : run.status };
    case "plan_created":
      return {
        ...run,
        status: "executing",
        steps: e.steps.map((s) => ({
          ...s,
          kind: STEP_KIND[String(s.kind)] ?? "requirements",
          observationId: s.observationId ?? "",
          status: "pending",
          tools: [],
          attempts: 0,
        })),
      };
    case "step_started":
      return {
        ...patchStep(run, e.stepId, (s) => ({
          ...s,
          status: "running",
          startedAt: at,
          endedAt: undefined,
          error: undefined,
          verifyingCheck: undefined,
          recovery: undefined,
          attempts: e.attempt ?? s.attempts + 1,
        })),
        status: "executing",
      };
    case "tool_call":
      return patchStep(run, e.stepId, (s) => {
        const i = s.tools.findIndex((t) => t.id === e.tool.id);
        const tools = i === -1 ? [...s.tools, e.tool] : s.tools.map((t, j) => (j === i ? e.tool : t));
        return { ...s, tools };
      });
    case "step_verifying":
      return patchStep(run, e.stepId, (s) => ({ ...s, status: "verifying", verifyingCheck: e.check }));
    case "step_completed":
      return patchStep(run, e.stepId, (s) => ({ ...s, status: "completed", summary: e.summary, endedAt: at }));
    case "step_failed":
      return {
        ...patchStep(run, e.stepId, (s) => ({ ...s, status: "failed", error: e.error, endedAt: at, attempts: e.attempt ?? s.attempts, recovery: e.recovery })),
        status: "awaiting_retry",
      };
    case "step_skipped":
      return {
        ...patchStep(run, e.stepId, (s) => ({ ...s, status: "skipped", error: e.reason, endedAt: s.endedAt ?? at })),
        status: "executing",
      };
    case "run_paused":
      return { ...run, status: "awaiting_retry" };
    case "run_resumed":
      return { ...run, status: "executing" };
    case "token":
      return { ...run, status: "answering", answer: run.answer + e.content };
    case "run_completed":
      return { ...run, status: "completed", usage: e.usage, endedAt: at };
    case "run_cancelled":
      return stopRun(run, at);
    case "error":
      return {
        ...run,
        status: "error",
        error: e.message,
        endedAt: at,
        steps: run.steps.map((s) =>
          s.status === "running" || s.status === "verifying"
            ? { ...s, status: "failed", error: "Interrupted by a server error.", endedAt: at }
            : s.status === "pending"
              ? { ...s, status: "skipped", error: "Not run — the run ended early." }
              : s,
        ),
      };
    // Informational only: the plan itself is shown through the answer text.
    case "plan_ready":
    case "recovery_chosen":
    case "notice":
      return run;
    default:
      return run;
  }
}

const mapRun = (state: ChatState, msgId: string, fn: (r: RunState) => RunState): ChatState => ({
  ...state,
  messages: state.messages.map((m) => (m.id === msgId && m.role === "agent" ? { ...m, run: fn(m.run) } : m)),
});

function reducer(state: ChatState, a: Action): ChatState {
  switch (a.type) {
    case "user_sent":
      return {
        ...state,
        title: a.title ?? state.title,
        // A reply supersedes the question on screen, so its option chips go away.
        messages: [...state.messages.map((m) => (m.role === "agent" && (m.question || m.warnings?.length) ? { ...m, question: null, warnings: [] } : m)), a.user, a.agent],
        activeMessageId: a.agent.id,
      };
    case "event":
      return mapRun(state, a.msgId, (r) => reduceRun(r, a.event, a.at));
    case "reply": {
      const next = mapRun(state, a.msgId, (r) => ({ ...r, status: "completed", answer: a.text }));
      return { ...next, messages: next.messages.map((m) => (m.id === a.msgId && m.role === "agent" ? { ...m, question: a.question ?? null, warnings: a.warnings ?? [] } : m)) };
    }
    case "reset_run":
      return mapRun(state, a.msgId, (r) => emptyRun(a.runId, r.startedAt));
    case "stopped":
      return mapRun(state, a.msgId, (r) => (["completed", "stopped", "error"].includes(r.status) ? r : stopRun(r, a.at)));
    case "step_skipped":
      return mapRun(state, a.msgId, (r) => ({
        ...patchStep(r, a.stepId, (s) => ({ ...s, status: "skipped", endedAt: s.endedAt ?? a.at })),
        status: "executing",
      }));
    case "closed":
      return { ...state, activeMessageId: state.activeMessageId === a.msgId ? null : state.activeMessageId, connection: "connected" };
    case "connection":
      return { ...state, connection: a.state };
    case "feedback":
      return mapRun(state, a.msgId, (r) => ({ ...r, feedback: a.value }));
    case "load_session":
      return { ...state, sessionId: a.session.id, title: a.session.title, messages: a.messages, activeMessageId: a.activeMessageId };
    case "set_event":
      return { ...state, sessionId: a.id, title: a.title };
    case "sessions":
      return { ...state, sessions: a.list };
    case "new_session":
      return { ...state, sessionId: null, title: "New plan", messages: [], activeMessageId: null, connection: "connected" };
    case "rename":
      return {
        ...state,
        title: a.title,
        sessions: state.sessions.map((s) => (s.id === state.sessionId ? { ...s, title: a.title } : s)),
      };
    case "truncate_from": {
      const i = state.messages.findIndex((m) => m.id === a.msgId);
      return i === -1 ? state : { ...state, messages: state.messages.slice(0, i) };
    }
  }
}

/* ------------------------------------------------------------------ */
/* Hook + context                                                       */
/* ------------------------------------------------------------------ */

let idSeq = 0;
const uid = (p: string) => `${p}_${Date.now().toString(36)}${(++idSeq).toString(36)}`;

const titleFrom = (prompt: string) => {
  const clean = prompt.replace(/\s+/g, " ").trim();
  if (clean.length <= 44) return clean;
  return clean.slice(0, 44).replace(/\s+\S*$/, "") + "…";
};

const toSummary = (event: api.ApiEvent): SessionSummary => ({
  id: event.id,
  title: event.name,
  eventName: event.location,
  eventDate: new Date(`${event.event_date}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }),
  updatedAt: event.created_at,
});

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "Something went wrong. Check that the backend is running.";

/** What a brief turn carries: free text, a clicked option, a warning's fix, or "keep as is". */
type TurnKind =
  | { kind: "text" }
  | { kind: "pick"; field: string; value: string }
  | { kind: "patch"; patch: Record<string, string> }
  | { kind: "keep"; warningId: string };

export interface AgentApi {
  state: ChatState;
  isStreaming: boolean;
  send: (prompt: string, displayText?: string) => void;
  /** Answers the open brief question with one of its option chips. */
  answerOption: (field: string, value: string, label: string) => void;
  /** Applies a warning's fix to the brief. */
  answerPatch: (label: string, patch: Record<string, string>) => void;
  /** Keeps a warning as it is and carries on. */
  keepWarning: (warningId: string) => void;
  /** Starts a planning run for a saved event and shows its steps in the chat. */
  replan: (eventId: string, label: string) => void;
  /** Answers a failed step with an option or the user's own words. */
  resolveStep: (msgId: string, stepId: string, choice: { optionId?: string; customText?: string }) => Promise<ResolveResult>;
  stop: () => void;
  retryStep: (msgId: string, stepId: string) => void;
  skipStep: (msgId: string, stepId: string) => void;
  regenerate: (msgId: string) => void;
  editAndResend: (userMsgId: string, content: string) => void;
  sendFeedback: (msgId: string, value: Feedback) => void;
  openSession: (id: string) => void;
  newSession: () => void;
  rename: (title: string) => void;
}

export function useAgentStream(): AgentApi {
  const [state, dispatch] = useReducer(reducer, initialState);
  const stateRef = useRef(state);
  stateRef.current = state;

  /** Brief conversation in progress (before an event exists). */
  const briefRef = useRef<{ sessionId: string | null; answers: Record<string, string>; dismissed: string[] }>({ sessionId: null, answers: {}, dismissed: [] });
  const esRef = useRef<EventSource | null>(null);

  const closeStream = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  const refreshSessions = useCallback(() => {
    api
      .listEvents()
      .then((events) => dispatch({ type: "sessions", list: events.map(toSummary) }))
      .catch(() => dispatch({ type: "sessions", list: [] }));
  }, []);

  /** Streams one run's events into a message. The server replays from the start, so this also restores a finished run. */
  const attachStream = useCallback((msgId: string, runId: string) => {
    closeStream();
    const es = new EventSource(api.streamUrl(runId));
    esRef.current = es;
    let dropped = false;

    es.onopen = () => {
      if (dropped) {
        dispatch({ type: "connection", state: "reconnected" });
        window.setTimeout(() => dispatch({ type: "connection", state: "connected" }), 2000);
      } else {
        dispatch({ type: "connection", state: "connected" });
      }
      dropped = false;
    };
    es.onmessage = (message) => {
      const event = JSON.parse(message.data) as AgentEvent;
      // The server stamps each event; replaying a finished run must keep its real timings.
      const stamped = (event as { at?: string }).at;
      dispatch({ type: "event", msgId, event, at: stamped ? Date.parse(stamped) : Date.now() });
      if (TERMINAL_EVENTS.has(event.type)) {
        es.close();
        if (esRef.current === es) esRef.current = null;
        dispatch({ type: "closed", msgId });
        refreshSessions();
      }
    };
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        if (esRef.current === es) esRef.current = null;
        dispatch({ type: "event", msgId, event: { type: "error", message: "Lost the connection to the planner." }, at: Date.now() });
        dispatch({ type: "closed", msgId });
        return;
      }
      dropped = true;
      dispatch({ type: "connection", state: "reconnecting" });
    };
  }, [closeStream, refreshSessions]);

  /** One chat turn: brief intake, then a planning run once the brief is ready. */
  const runTurn = useCallback(
    async (prompt: string, how: TurnKind = { kind: "text" }, displayText?: string) => {
      const before = stateRef.current;
      if (before.sessionId) {
        // A saved event is open: a new message starts a new plan.
        briefRef.current = { sessionId: null, answers: {}, dismissed: [] };
        dispatch({ type: "new_session" });
      }
      const now = Date.now();
      const shownPrompt = displayText || prompt;
      const user: ChatMessage = { id: uid("u"), role: "user", content: shownPrompt, createdAt: now };
      const agent: AgentMessage = { id: uid("a"), role: "agent", createdAt: now, run: emptyRun("", now) };
      dispatch({ type: "user_sent", user, agent, title: briefRef.current.sessionId ? undefined : titleFrom(shownPrompt) });

      try {
        if (how.kind === "keep") briefRef.current.dismissed = [...briefRef.current.dismissed, how.warningId];
        const turn = await api.briefTurn({
          ...(how.kind === "pick" ? { field: how.field, value: how.value } : how.kind === "patch" ? { patch: how.patch } : how.kind === "keep" ? {} : { message: prompt }),
          answers: briefRef.current.answers,
          dismissed: briefRef.current.dismissed,
          session_id: briefRef.current.sessionId ?? undefined,
          display_text: shownPrompt,
        });
        briefRef.current = { ...briefRef.current, sessionId: turn.session_id ?? briefRef.current.sessionId, answers: turn.answers };

        if (!turn.ready) {
          const text = [turn.reply, turn.next?.prompt].filter(Boolean).join("\n\n");
          dispatch({ type: "reply", msgId: agent.id, text, question: turn.next, warnings: turn.warnings });
          dispatch({ type: "closed", msgId: agent.id });
          return;
        }

        const a = turn.answers;
        const event = await api.createEvent({
          name: a.name,
          event_date: a.date,
          location: a.location,
          attendees: Number(a.attendees),
          budget: Number(a.budget),
          objective: `${a.eventType}: ${a.objective}`,
        });
        const chatSessionId = briefRef.current.sessionId;
        if (chatSessionId) api.linkChatSession(chatSessionId, event.id).catch(() => undefined);
        briefRef.current = { sessionId: null, answers: {}, dismissed: [] };
        dispatch({ type: "set_event", id: event.id, title: event.name });
        dispatch({ type: "reset_run", msgId: agent.id, runId: "" });
        refreshSessions();

        const { run_id } = await api.startRun(event.id, chatSessionId ?? undefined);
        dispatch({ type: "reset_run", msgId: agent.id, runId: run_id });
        attachStream(agent.id, run_id);
      } catch (error) {
        dispatch({ type: "event", msgId: agent.id, event: { type: "error", message: errorMessage(error) }, at: Date.now() });
        dispatch({ type: "closed", msgId: agent.id });
      }
    },
    [attachStream, refreshSessions],
  );

  const send = useCallback(
    (prompt: string, displayText?: string) => {
      if (!prompt.trim() || stateRef.current.activeMessageId) return;
      void runTurn(prompt.trim(), { kind: "text" }, displayText?.trim());
    },
    [runTurn],
  );

  const answerOption = useCallback(
    (field: string, value: string, label: string) => {
      if (stateRef.current.activeMessageId) return;
      void runTurn(label, { kind: "pick", field, value });
    },
    [runTurn],
  );

  const answerPatch = useCallback(
    (label: string, patch: Record<string, string>) => {
      if (stateRef.current.activeMessageId) return;
      void runTurn(label, { kind: "patch", patch });
    },
    [runTurn],
  );

  const keepWarning = useCallback(
    (warningId: string) => {
      if (stateRef.current.activeMessageId) return;
      void runTurn("Keep as is", { kind: "keep", warningId });
    },
    [runTurn],
  );

  const replan = useCallback(
    async (eventId: string, label: string) => {
      if (stateRef.current.activeMessageId) return;
      const now = Date.now();
      const user: ChatMessage = { id: uid("u"), role: "user", content: label, createdAt: now };
      const agent: AgentMessage = { id: uid("a"), role: "agent", createdAt: now, run: emptyRun("", now) };
      dispatch({ type: "user_sent", user, agent, title: label });
      dispatch({ type: "set_event", id: eventId, title: label });
      try {
        const { run_id } = await api.startRun(eventId);
        dispatch({ type: "reset_run", msgId: agent.id, runId: run_id });
        attachStream(agent.id, run_id);
      } catch (error) {
        dispatch({ type: "event", msgId: agent.id, event: { type: "error", message: errorMessage(error) }, at: Date.now() });
        dispatch({ type: "closed", msgId: agent.id });
      }
    },
    [attachStream],
  );

  const stop = useCallback(() => {
    const id = stateRef.current.activeMessageId;
    if (!id) return;
    const msg = stateRef.current.messages.find((m) => m.id === id);
    const runId = msg?.role === "agent" ? msg.run.runId : "";
    closeStream();
    if (runId) api.cancelRun(runId).catch(() => undefined);
    dispatch({ type: "stopped", msgId: id, at: Date.now() });
    dispatch({ type: "closed", msgId: id });
  }, [closeStream]);

  const runIdOf = (msgId: string) => {
    const msg = stateRef.current.messages.find((m) => m.id === msgId);
    return msg?.role === "agent" ? msg.run.runId : "";
  };

  const resolveStep = (msgId: string, stepId: string, choice: { optionId?: string; customText?: string }) => {
    // The approval step is the owner's decision on the plan, not a recovery choice.
    if (stepId === "approval") {
      const decision = choice.optionId === "approve" ? "approve" : "revise";
      return api.decidePlan(runIdOf(msgId), decision, choice.customText ?? "");
    }
    return api.resolveStep(runIdOf(msgId), stepId, choice);
  };

  const openSession = useCallback(
    async (id: string) => {
      const session = stateRef.current.sessions.find((s) => s.id === id);
      if (!session) return;
      if (stateRef.current.activeMessageId) dispatch({ type: "closed", msgId: stateRef.current.activeMessageId });
      closeStream();
      briefRef.current = { sessionId: null, answers: {}, dismissed: [] };

      const now = Date.now();
      const user: ChatMessage = { id: uid("u"), role: "user", content: session.title, createdAt: now };
      const agent: AgentMessage = { id: uid("a"), role: "agent", createdAt: now, run: emptyRun("", now) };
      dispatch({ type: "load_session", session, messages: [user, agent], activeMessageId: agent.id });

      try {
        const latest = await api.latestRun(id);
        if (stateRef.current.sessionId !== id) return; // the user moved on while this loaded
        dispatch({ type: "reset_run", msgId: agent.id, runId: latest.id });
        attachStream(agent.id, latest.id);
      } catch {
        if (stateRef.current.sessionId !== id) return;
        dispatch({ type: "reply", msgId: agent.id, text: "No plan has been generated for this event yet." });
        dispatch({ type: "closed", msgId: agent.id });
      }
    },
    [attachStream, closeStream],
  );

  useEffect(() => {
    refreshSessions();
    return () => closeStream();
  }, [closeStream, refreshSessions]);

  const api_: AgentApi = useMemo(
    () => ({
      state,
      isStreaming: state.activeMessageId !== null,
      send,
      answerOption,
      answerPatch,
      replan: (eventId, label) => replan(eventId, label),
      keepWarning,
      resolveStep,
      stop,
      retryStep: (msgId, stepId) => {
        if (stepId === "approval") return; // retrying the approval would approve the plan; use the decision card
        // A 409 means the step was already resumed; the stream shows its real state.
        api.retryStep(runIdOf(msgId), stepId).catch(() => undefined);
      },
      skipStep: (msgId, stepId) => {
        if (stepId === "approval") return; // the plan needs the owner's decision
        dispatch({ type: "step_skipped", msgId, stepId, at: Date.now() });
        api.skipStep(runIdOf(msgId), stepId).catch(() => undefined);
      },
      regenerate: (msgId) => {
        const msgs = stateRef.current.messages;
        const i = msgs.findIndex((m) => m.id === msgId);
        const prev = msgs[i - 1];
        if (i < 1 || prev.role !== "user") return;
        stop();
        dispatch({ type: "truncate_from", msgId: prev.id });
        void runTurn(prev.content);
      },
      editAndResend: (userMsgId, content) => {
        if (!content.trim()) return;
        stop();
        dispatch({ type: "truncate_from", msgId: userMsgId });
        void runTurn(content.trim());
      },
      sendFeedback: (msgId, value) => {
        const m = stateRef.current.messages.find((x) => x.id === msgId);
        if (m?.role !== "agent") return;
        dispatch({ type: "feedback", msgId, value: m.run.feedback === value ? null : value });
      },
      openSession: (id) => void openSession(id),
      newSession: () => {
        stop();
        closeStream();
        briefRef.current = { sessionId: null, answers: {}, dismissed: [] };
        dispatch({ type: "new_session" });
      },
      rename: (title) => title.trim() && dispatch({ type: "rename", title: title.trim() }),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [state, send, answerOption, stop, runTurn, openSession, closeStream],
  );

  return api_;
}

const AgentContext = createContext<AgentApi | null>(null);

export function AgentProvider({ children }: { children: ReactNode }) {
  const api = useAgentStream();
  return createElement(AgentContext.Provider, { value: api }, children);
}

export function useAgent(): AgentApi {
  const ctx = useContext(AgentContext);
  if (!ctx) throw new Error("useAgent must be used inside <AgentProvider>");
  return ctx;
}
