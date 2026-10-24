import { request } from '../lib/http';
import type { ResolveChoice, ResolveResult } from "./types";

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001/api/v1";


export interface StartRunOptions {
  operation?: "plan-generation" | "budget-revision";
  budget?: number;
}

export const startRun = (eventId: string, options: StartRunOptions = {}) =>
  request<{ run_id: string; status: string }>(`/events/${eventId}/runs`, { method: "POST", body: JSON.stringify(options) });

export const latestRun = (eventId: string) => request<{ id: string; status: string }>(`/events/${eventId}/runs/latest`);

export const resolveStep = (runId: string, stepId: string, choice: ResolveChoice) =>
  request<ResolveResult>(`/runs/${runId}/steps/${stepId}/resolve`, { method: "POST", body: JSON.stringify(choice) });

export const cancelRun = (runId: string) => request<void>(`/runs/${runId}/cancel`, { method: "POST" });

/** Resume a stopped, errored or interrupted run from its checkpoint. */
export const continueRun = (runId: string) => request<{ status: string }>(`/runs/${runId}/continue`, { method: "POST" });

export const streamUrl = (runId: string) => `${API_BASE_URL}/runs/${runId}/stream`;

/** Static PNG rendered from the backend's compiled LangGraph definition. */
export const workflowGraphPngUrl = () => `${API_BASE_URL}/workflow/graph.png`;
