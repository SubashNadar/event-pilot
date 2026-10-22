import type { AgentEvent, RunState, StepState } from "./types";

/** Pure reducer: applies one streamed event to the run. Ported from Eventa's `reduceRun`. */

export const isTerminal = (status: RunState["status"]) => status === "completed" || status === "stopped" || status === "error";

export function emptyRun(runId: string): RunState {
  return { runId, traceId: "", operation: "plan-generation", status: "starting", startedAt: Date.now(), steps: [], answer: "", notices: [], pendingStepIds: [], lastSeq: 0 };
}

const time = (e: { at?: string }) => (e.at ? Date.parse(e.at) : Date.now());

const patch = (run: RunState, stepId: string, fn: (s: StepState) => StepState): RunState => ({
  ...run,
  steps: run.steps.map((s) => (s.id === stepId ? fn(s) : s)),
});

export function reduceRun(run: RunState, e: AgentEvent): RunState {
  const at = time(e);
  switch (e.type) {
    case "run_started":
      return { ...run, runId: e.runId, traceId: e.traceId, traceUrl: e.traceUrl, operation: e.operation, eventId: e.eventId, startedAt: at, status: "starting" };
    case "plan_created":
      return { ...run, status: "executing", steps: e.steps.map((s) => ({ ...s, status: "pending", tools: [], attempts: 0 })) };
    case "notice":
      return run.notices.includes(e.message) ? run : { ...run, notices: [...run.notices, e.message] };
    case "step_started":
      return {
        ...patch(run, e.stepId, (s) => ({ ...s, status: "running", startedAt: s.startedAt ?? at, endedAt: undefined, error: undefined, verifyingCheck: undefined, recovery: undefined, chosen: undefined, attempts: Math.max(s.attempts, e.attempt ?? s.attempts + 1) })),
        status: run.status === "awaiting_input" && run.pendingStepIds.some((id) => id !== e.stepId) ? run.status : "executing",
      };
    case "tool_call":
      return patch(run, e.stepId, (s) => {
        const i = s.tools.findIndex((t) => t.id === e.tool.id);
        return { ...s, tools: i === -1 ? [...s.tools, e.tool] : s.tools.map((t, j) => (j === i ? e.tool : t)) };
      });
    case "step_verifying":
      return patch(run, e.stepId, (s) => ({ ...s, status: "verifying", verifyingCheck: e.check }));
    case "step_completed":
      return patch(run, e.stepId, (s) => ({ ...s, status: "completed", summary: e.summary, endedAt: at }));
    case "step_failed":
      return patch(run, e.stepId, (s) => ({ ...s, status: "failed", error: e.error, recovery: e.recovery, attempts: e.attempt, endedAt: at, chosen: undefined }));
    case "step_skipped":
      return patch(run, e.stepId, (s) => ({ ...s, status: "skipped", error: e.reason, recovery: undefined, endedAt: s.startedAt ? at : undefined }));
    case "run_paused":
      return { ...run, status: "awaiting_input", pendingStepIds: e.pendingStepIds };
    case "recovery_chosen":
      return patch(run, e.stepId, (s) => ({ ...s, chosen: { action: e.action, label: e.label } }));
    case "run_resumed":
      return { ...patch(run, e.stepId, (s) => ({ ...s, choiceLabel: e.action === "skip" ? undefined : e.label })), status: "executing", pendingStepIds: [] };
    case "token":
      return { ...run, status: "answering", answer: run.answer + e.content };
    case "plan_ready":
      return { ...run, plan: e.plan };
    case "run_completed":
      return { ...run, status: "completed", usage: e.usage, endedAt: at };
    case "run_cancelled":
      return {
        ...run,
        status: "stopped",
        endedAt: at,
        steps: run.steps.map((s) =>
          s.status === "completed" || s.status === "skipped" ? s : { ...s, status: "skipped", recovery: undefined, error: s.startedAt ? "Stopped by you mid-step." : "Not run — you stopped the plan.", endedAt: s.startedAt ? at : undefined },
        ),
      };
    case "error":
      return {
        ...run,
        status: "error",
        error: e.message,
        endedAt: at,
        steps: run.steps.map((s) =>
          s.status === "running" || s.status === "verifying"
            ? { ...s, status: "failed", error: "Interrupted by a server error.", recovery: undefined, endedAt: at }
            : s.status === "pending"
              ? { ...s, status: "skipped", error: "Not run — the run ended early." }
              : s,
        ),
      };
  }
}
