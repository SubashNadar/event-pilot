/**
 * Backend calls for the Eventa chat. Paths and payloads match backend/app/api/routes.
 * Snake_case is the wire format for events and briefs; run events arrive camelCase.
 */
import { API_BASE_URL } from "./config";
import type { BriefQuestion, BriefWarning } from "../types/types";

export interface ApiEvent {
  id: string;
  name: string;
  event_date: string;
  location: string;
  attendees: number;
  budget: number;
  objective: string;
  created_at: string;
}

export interface BriefTurn {
  answers: Record<string, string>;
  brief: { field: string; label: string; value: string; display: string }[];
  ready: boolean;
  reply: string;
  next: BriefQuestion | null;
  warnings: BriefWarning[];
  missing: string[];
  session_id: string | null;
}

export interface NewEvent {
  name: string;
  event_date: string;
  location: string;
  attendees: number;
  budget: number;
  objective: string;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail;
    throw new Error(typeof detail === "string" ? detail : "Unable to reach the planning API.");
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const listEvents = () => request<ApiEvent[]>("/events");

export const createEvent = (event: NewEvent) => request<ApiEvent>("/events", { method: "POST", body: JSON.stringify(event) });

export interface BriefTurnBody {
  message?: string;
  /** A clicked option: the field it answers and its value, sent instead of free text. */
  field?: string;
  value?: string;
  /** A warning's fix: the brief fields it changes. */
  patch?: Record<string, string>;
  /** Warnings the user chose to keep as they are. */
  dismissed?: string[];
  answers: Record<string, string>;
  session_id?: string;
  display_text?: string;
}

export const briefTurn = (body: BriefTurnBody) =>
  request<BriefTurn>("/chat/brief", { method: "POST", body: JSON.stringify(body) });

export const linkChatSession = (sessionId: string, eventId: string) =>
  request(`/chat/sessions/${encodeURIComponent(sessionId)}/event`, { method: "POST", body: JSON.stringify({ event_id: eventId }) });

export const startRun = (eventId: string, sessionId?: string) =>
  request<{ run_id: string; status: string }>(`/events/${eventId}/runs`, {
    method: "POST",
    body: JSON.stringify({ operation: "plan-generation", session_id: sessionId }),
  });

export const latestRun = (eventId: string) => request<{ id: string; status: string }>(`/events/${eventId}/runs/latest`);

export const retryStep = (runId: string, stepId: string) => request(`/runs/${runId}/steps/${stepId}/retry`, { method: "POST" });

export const skipStep = (runId: string, stepId: string) => request(`/runs/${runId}/steps/${stepId}/skip`, { method: "POST" });

export const cancelRun = (runId: string) => request<void>(`/runs/${runId}/cancel`, { method: "POST" });

export interface ResolveResult {
  status: "resumed" | "queued" | "needs_clarification";
  question?: string | null;
}

/** Answers a failed step: one of its suggested options, or the user's own words. */
export const resolveStep = (runId: string, stepId: string, choice: { optionId?: string; customText?: string }) =>
  request<ResolveResult>(`/runs/${runId}/steps/${stepId}/resolve`, {
    method: "POST",
    body: JSON.stringify(choice.optionId ? { option_id: choice.optionId } : { custom_text: choice.customText }),
  });

export const streamUrl = (runId: string) => `${API_BASE_URL}/runs/${runId}/stream`;
