/** Where "View trace" / "Open in Langfuse" links point. Set via env in production. */
export const LANGFUSE_HOST = import.meta.env.VITE_LANGFUSE_HOST ?? "https://us.cloud.langfuse.com";
export const LANGFUSE_PROJECT = import.meta.env.VITE_LANGFUSE_PROJECT ?? "";

export function traceUrl(traceId: string, observationId?: string): string {
  if (!LANGFUSE_PROJECT) return LANGFUSE_HOST;
  const base = `${LANGFUSE_HOST}/project/${LANGFUSE_PROJECT}/traces/${traceId}`;
  return observationId ? `${base}?observation=${observationId}` : base;
}
