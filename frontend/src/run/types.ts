/**
 * EventPilot planning-run types.
 *
 * The first half is the WIRE CONTRACT streamed by the backend over SSE
 * (backend/app/graphs/event_workflow.py and app/runs/manager.py). It started as
 * the Eventa mock's `AgentEvent` union and adds recovery, pause and plan events.
 * The second half is the UI state `reduceRun` builds from those events.
 */

export type StepStatus = "pending" | "running" | "verifying" | "completed" | "failed" | "skipped";

export type StepKind =
  | "logistics"
  | "finance"
  | "schedule"
  | "requirements"
  | "marketing"
  | "risk"
  | "manager"
  | "review"
  | "reflection"
  | "recommend";

/** Where a step sits in the team's flow: reception -> split (manager) -> specialists -> review (manager) -> owner. */
export type StepLane = "reception" | "split" | "specialists" | "review" | "owner";

export interface Step {
  id: string;
  title: string;
  goal: string;
  kind: StepKind;
  agent: string;
  group: "parallel" | "sequential";
  lane?: StepLane;
}

export interface ToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
  resultSummary: string;
  latencyMs: number;
  status: "running" | "success" | "error";
}

export interface SourceRef {
  id: string;
  label: string;
  kind: "memory" | "web" | "tool" | "document";
}

export interface Verification {
  check: string;
  passed: boolean;
  reason: string;
}

export interface StepSummary {
  did: string[];
  sources: SourceRef[];
  verification: Verification;
  metrics: { tokensIn: number; tokensOut: number; costUsd: number; model: string };
}

export interface RecoveryOption {
  id: string;
  label: string;
  description: string;
  action: "retry" | "retry_with" | "skip";
  patch: Record<string, unknown>;
}

export interface RecoveryProposal {
  summary: string;
  cause: string;
  options: RecoveryOption[];
  customPrompt: string;
  source: "llm" | "rules";
}

export interface Usage {
  tokensIn: number;
  tokensOut: number;
  costUsd: number;
  durationMs: number;
  model: string;
}

/** The saved plan as the API returns it (snake_case, see backend EventPlan). */
export interface ApiPlan {
  event_id: string;
  plan_type: string;
  venue: string;
  venue_detail: string;
  budget_forecast: number;
  budget_lines: { category: string; amount: number; share_percent: number }[];
  agenda: { time: string; activity: string; owner: string }[];
  risks: { level: string; title: string; detail: string; recommended_action: string }[];
  activity: { agent: string; detail: string; timestamp: string }[];
  confidence: number;
  source: string;
  recommendations?: string | null;
  run_id?: string | null;
  generated_at: string;
}

type Stamped = { at?: string };

export type AgentEvent = Stamped &
  (
    | { type: "run_started"; runId: string; traceId: string; traceUrl?: string | null; operation: string; eventId: string }
    | { type: "plan_created"; steps: Step[] }
    | { type: "notice"; message: string }
    | { type: "step_started"; stepId: string; attempt: number }
    | { type: "tool_call"; stepId: string; tool: ToolCall }
    | { type: "step_verifying"; stepId: string; check: string }
    | { type: "step_completed"; stepId: string; summary: StepSummary }
    | { type: "step_failed"; stepId: string; error: string; attempt: number; retryable: boolean; recovery: RecoveryProposal }
    | { type: "step_skipped"; stepId: string; reason: string }
    | { type: "run_paused"; pendingStepIds: string[] }
    | { type: "recovery_chosen"; stepId: string; action: RecoveryOption["action"]; label: string }
    | { type: "run_resumed"; stepId: string; action: RecoveryOption["action"]; label: string }
    | { type: "token"; content: string }
    | { type: "plan_ready"; plan: ApiPlan }
    | { type: "run_completed"; usage: Usage }
    | { type: "run_cancelled"; message: string }
    | { type: "error"; message: string }
  );

/* ------------------------------------------------------------------ UI state */

export interface StepState extends Step {
  status: StepStatus;
  startedAt?: number;
  endedAt?: number;
  tools: ToolCall[];
  verifyingCheck?: string;
  summary?: StepSummary;
  error?: string;
  attempts: number;
  recovery?: RecoveryProposal;
  /** The user's choice while other paused steps still need answers. */
  chosen?: { action: RecoveryOption["action"]; label: string };
  /** Label of the choice that started the current attempt ("attempt 2 · …"). */
  choiceLabel?: string;
}

export type RunStatus = "starting" | "executing" | "awaiting_input" | "answering" | "completed" | "stopped" | "error";

export interface RunState {
  runId: string;
  traceId: string;
  traceUrl?: string | null;
  operation: string;
  eventId?: string;
  status: RunStatus;
  startedAt: number;
  endedAt?: number;
  steps: StepState[];
  answer: string;
  notices: string[];
  pendingStepIds: string[];
  plan?: ApiPlan;
  usage?: Usage;
  error?: string;
  lastSeq: number;
}

export type ConnectionState = "idle" | "connected" | "reconnecting" | "reconnected";

export type ResolveChoice = { option_id: string } | { custom_text: string };

export interface ResolveResult {
  status: "resumed" | "queued" | "needs_clarification";
  question?: string | null;
}
