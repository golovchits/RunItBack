export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "0s";
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  if (m === 0) return `${s}s`;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

export function formatDurationShort(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "0s";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m${String(s % 60).padStart(2, "0")}s`;
}

export function formatIsoTimeUTC(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toISOString().replace("T", " ").slice(0, 16) + "Z";
  } catch {
    return iso;
  }
}

export function formatRelativeTime(iso: string, now = Date.now()): string {
  try {
    const t = new Date(iso).getTime();
    const delta = Math.max(0, now - t);
    const s = Math.floor(delta / 1000);
    if (s < 2) return "just now";
    if (s < 60) return `${s}s ago`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    return `${d}d ago`;
  } catch {
    return "";
  }
}

export function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}
