import { useCallback, useEffect, useRef, useState } from "react";
import { cancelRun, resolveStep, startRun, streamUrl, type StartRunOptions } from "./api";
import { emptyRun, isTerminal, reduceRun } from "./reducer";
import type { AgentEvent, ConnectionState, ResolveChoice, ResolveResult, RunState } from "./types";

const TERMINAL_EVENTS = new Set(["run_completed", "run_cancelled", "error"]);

/**
 * Owns one planning run: starts it, streams its events over SSE and exposes the
 * recovery actions. The server replays every event from the start, so attaching
 * to an existing run (after a refresh, or from a saved event) rebuilds the same
 * timeline. EventSource reconnects on its own and sends Last-Event-ID, so a
 * dropped connection resumes where it left off.
 */
export function usePlanRun() {
  const [run, setRun] = useState<RunState | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const source = useRef<EventSource | null>(null);
  const lastSeq = useRef(0);
  const reconnectedTimer = useRef<number | undefined>(undefined);

  const close = useCallback(() => {
    source.current?.close();
    source.current = null;
    window.clearTimeout(reconnectedTimer.current);
    setConnection("idle");
  }, []);

  const attach = useCallback(
    (runId: string) => {
      close();
      lastSeq.current = 0;
      setRun(emptyRun(runId));
      const es = new EventSource(streamUrl(runId));
      source.current = es;
      let dropped = false;
      es.onopen = () => {
        if (dropped) {
          setConnection("reconnected");
          reconnectedTimer.current = window.setTimeout(() => setConnection("connected"), 2000);
        } else {
          setConnection("connected");
        }
        dropped = false;
      };
      es.onmessage = (message) => {
        const seq = Number(message.lastEventId || 0);
        if (seq && seq <= lastSeq.current) return; // already applied before a reconnect
        lastSeq.current = seq || lastSeq.current;
        const event = JSON.parse(message.data) as AgentEvent;
        setRun((current) => (current ? { ...reduceRun(current, event), lastSeq: lastSeq.current } : current));
        if (TERMINAL_EVENTS.has(event.type)) {
          es.close(); // finished: stop EventSource from reconnecting
          if (source.current === es) source.current = null;
          setConnection("idle");
        }
      };
      es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) return;
        dropped = true;
        setConnection("reconnecting");
      };
    },
    [close],
  );

  useEffect(() => close, [close]);

  const start = useCallback(
    async (eventId: string, options: StartRunOptions = {}) => {
      const { run_id } = await startRun(eventId, options);
      attach(run_id);
      return run_id;
    },
    [attach],
  );

  const resolve = useCallback(
    async (stepId: string, choice: ResolveChoice): Promise<ResolveResult> => {
      if (!run) throw new Error("No active run");
      return resolveStep(run.runId, stepId, choice);
    },
    [run],
  );

  const cancel = useCallback(async () => {
    if (run && !isTerminal(run.status)) await cancelRun(run.runId);
  }, [run]);

  const reset = useCallback(() => {
    close();
    setRun(null);
  }, [close]);

  return { run, connection, start, attach, resolve, cancel, reset };
}

export type PlanRunApi = ReturnType<typeof usePlanRun>;
