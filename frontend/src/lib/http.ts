import { API_BASE_URL } from './config';

export class ApiError extends Error {
  constructor(message: string, public status = 0, public fieldErrors: Record<string, string> = {}, public retryAfter?: number) {
    super(message);
    this.name = 'ApiError';
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.';
}

export async function request<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
      signal: options.signal ?? controller.signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const detail = body?.detail;
      const fieldErrors: Record<string, string> = {};
      if (Array.isArray(detail)) {
        for (const issue of detail) {
          const field = (issue.loc ?? []).filter((part: unknown) => part !== 'body').join('.');
          fieldErrors[field || 'request'] = typeof issue.msg === 'string' ? issue.msg : 'Invalid value';
        }
      }
      const retryHeader = response.headers.get('Retry-After');
      const retrySeconds = retryHeader ? (/^\d+$/.test(retryHeader) ? Number(retryHeader) : Math.max(0, Math.ceil((Date.parse(retryHeader) - Date.now()) / 1000))) : undefined;
      const retryAfter = Number.isFinite(retrySeconds) ? retrySeconds : undefined;
      let message = typeof detail === 'string' ? detail : Object.entries(fieldErrors).map(([field, value]) => `${field.replace(/_/g, ' ')}: ${value}`).join('; ');
      if (response.status >= 500) message = 'The planning service could not complete this request. Please try again shortly.';
      if (response.status === 429) message = retryAfter !== undefined ? `Too many planning requests. Try again in ${retryAfter} seconds.` : 'Too many planning requests. Please wait and try again.';
      throw new ApiError(message || 'This request could not be completed. Please try again.', response.status, fieldErrors, retryAfter);
    }
    return response.status === 204 ? undefined as T : await response.json();
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) throw new ApiError('The request took too long. Check your event or run status before trying again.');
    if (options.signal?.aborted) throw new ApiError('The request was cancelled.');
    throw new ApiError('Could not connect to the planning service. Check your connection and try again.');
  } finally {
    window.clearTimeout(timer);
  }
}
