export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.max(0, Math.round(ms))}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s % 60)}s`;
}

export function formatClock(t: number): string {
  return new Date(t).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

export function formatTimeShort(t: number): string {
  return new Date(t).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

export function formatUsd(n: number): string {
  return `$${n < 0.01 ? n.toFixed(4) : n.toFixed(3)}`;
}

export function formatNum(n: number): string {
  return n.toLocaleString("en-IN");
}

export function truncate(s: string, n = 60): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
