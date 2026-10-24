/**
 * Eventa — shared types.
 *
 * The first half of this file is the WIRE CONTRACT: what the LangGraph backend
 * streams (SSE / WebSocket). The second half is UI-only state that
 * `useAgentStream` reduces those events into. Components only ever read the
 * UI state; they never see raw events.
 */

/* ------------------------------------------------------------------ */
/* Wire contract                                                       */
/* ------------------------------------------------------------------ */

/** Lifecycle of a single plan step. */
export type StepStatus =
  | "pending"
  | "running"
  | "verifying"
  | "completed"
  | "failed"
  | "skipped";

/** Used to pick context-aware thinking hints and step icons. */
export type StepKind =
  | "requirements"
  | "memory"
  | "venues"
  | "availability"
  | "budget"
  | "activities"
  | "itinerary";

/** A step as announced by the planner node in `plan_created`. */
export interface Step {
  id: string;
  title: string;
  /** One line on why the step exists. */
  goal: string;
  kind: StepKind;
  /** Langfuse observation (span) id for this step. */
  observationId: string;
}

export type ToolStatus = "running" | "success" | "error";

export interface ToolCall {
  id: string;
  /** e.g. `venue_search`, `weather_api`, `budget_calculator`, `rag_retrieve` */
  name: string;
  /** Full input as sent to the tool (shown truncated in the UI). */
  input: Record<string, unknown>;
  /** Plain-English summary of what came back. */
  resultSummary: string;
  latencyMs: number;
  status: ToolStatus;
}

export interface SourceRef {
  id: string;
  label: string;
  kind: "memory" | "web" | "tool" | "document";
  href?: string;
}

export interface Verification {
  check: string;
  passed: boolean;
  reason: string;
}

export interface StepMetrics {
  tokensIn: number;
  tokensOut: number;
  costUsd: number;
  model: string;
}

/** Emitted by the verifier node when a step finishes. */
export interface StepSummary {
  did: string[];
  sources: SourceRef[];
  verification: Verification;
  metrics: StepMetrics;
}

export interface Memory {
  id: string;
  snippet: string;
  sourceSessionId: string;
  sourceSessionTitle: string;
  sourceDate: string; // ISO date
  /** Cosine similarity / reranker score, 0..1 */
  relevance: number;
}

export interface Usage {
  tokensIn: number;
  tokensOut: number;
  costUsd: number;
  durationMs: number;
  model: string;
}

export type AgentEvent =
  | { type: "run_started"; runId: string; traceId: string; eventId?: string }
  | { type: "memory_retrieved"; memories: Memory[] }
  | { type: "thinking"; hintContext?: string }
  | { type: "plan_created"; steps: Step[] }
  | { type: "step_started"; stepId: string; attempt?: number }
  | { type: "tool_call"; stepId: string; tool: ToolCall }
  | { type: "step_verifying"; stepId: string; check: string }
  | { type: "step_completed"; stepId: string; summary: StepSummary }
  | { type: "step_failed"; stepId: string; error: string; attempt?: number; recovery?: RecoveryProposal }
  | { type: "step_skipped"; stepId: string; reason: string }
  | { type: "run_paused"; pendingStepIds: string[] }
  | { type: "run_resumed"; stepId: string; action: string; label: string }
  | { type: "recovery_chosen"; stepId: string; action: string; label: string }
  | { type: "plan_ready"; plan: unknown }
  | { type: "run_cancelled"; message: string }
  | { type: "notice"; message: string }
  | { type: "token"; content: string }
  | { type: "run_completed"; usage: Usage }
  | { type: "error"; message: string };

/* ------------------------------------------------------------------ */
/* UI state (derived by the reducer in useAgentStream)                 */
/* ------------------------------------------------------------------ */

export interface StepState extends Step {
  status: StepStatus;
  startedAt?: number;
  endedAt?: number;
  tools: ToolCall[];
  /** The check text while `verifying`. */
  verifyingCheck?: string;
  summary?: StepSummary;
  error?: string;
  attempts: number;
  recovery?: RecoveryProposal;
}

export type RunStatus =
  | "starting"
  | "thinking"
  | "executing"
  | "awaiting_retry" // a step failed; waiting for the user to retry or skip
  | "answering"
  | "completed"
  | "stopped"
  | "error";

export type Feedback = "up" | "down" | null;

export interface RunState {
  runId: string;
  traceId: string;
  status: RunStatus;
  startedAt: number;
  endedAt?: number;
  memories: Memory[];
  memoryEnabled: boolean;
  hintContext?: string;
  steps: StepState[];
  answer: string;
  usage?: Usage;
  error?: string;
  feedback: Feedback;
  /** The saved event this run plans; set once the run starts, used for the plan downloads. */
  eventId?: string;
}

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
  createdAt: number;
}

export interface RecoveryOption {
  id: string;
  label: string;
  description: string;
  action: "retry" | "retry_with" | "skip";
  patch: Record<string, unknown>;
}

import type { PlanPreview } from "../run/types";

/** What went wrong with a failed step, and the ways forward the planner suggests. */
export interface RecoveryProposal {
  summary: string;
  cause: string;
  options: RecoveryOption[];
  customPrompt: string;
  source: "llm" | "rules";
  /** For the approval step: the generated plan, so the owner can review it before deciding. */
  preview?: PlanPreview | null;
}

/** A doubt about the brief (budget too low, short notice, unknown city), with fixes to choose from. */
export interface BriefWarning {
  id: string;
  message: string;
  options: { label: string; patch: Record<string, string> }[];
}

/** The next brief question, with the options the planner offers as one-click answers. */
export interface BriefQuestion {
  field: string;
  prompt: string;
  placeholder: string;
  options: { label: string; value: string; hint: string }[];
}

export interface AgentMessage {
  id: string;
  role: "agent";
  createdAt: number;
  run: RunState;
  /** Set while the brief is waiting for an answer; cleared when the user replies. */
  question?: BriefQuestion | null;
  warnings?: BriefWarning[];
}

export type ChatMessage = UserMessage | AgentMessage;

export type ConnectionState = "connected" | "reconnecting" | "reconnected";

export interface SessionSummary {
  id: string;
  title: string;
  eventName: string;
  eventDate: string; // human readable, e.g. "14–15 Feb 2027"
  updatedAt: string; // ISO
}

export type HintKind = "tip" | "behind" | "didyouknow";

export interface Hint {
  id: string;
  kind: HintKind;
  text: string;
  /** Show preferentially while a step of this kind is running. */
  context?: StepKind | "thinking";
}
