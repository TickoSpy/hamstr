import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

// Matches any HTTP/HTTPS URL in pasted text
const URL_RE = /https?:\/\/[^\s<>"'()[\]{}|\\^`]+/g;

function cleanUrl(raw: string): string | null {
  const cleaned = raw.replace(/[.,;:!?]+$/, "");
  try {
    const url = new URL(cleaned);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return cleaned;
  } catch {
    return null;
  }
}

// A bare host must look like a host: at least one dot and a real TLD, so that
// `example.com/watch?v=x` is picked up but `notes/todo.txt` isn't.
const BARE_HOST_RE =
  /(?<![/:@.\w-])([a-zA-Z0-9][\w-]*(?:\.[a-zA-Z0-9][\w-]*)*\.[a-zA-Z]{2,}(?::\d+)?\/[^\s<>"'()[\]{}|\\^`]*)/g;

export function extractUrls(text: string): string[] {
  const found: string[] = [];

  // Take explicit http(s) URLs out first and blank them, so the bare-host pass
  // below cannot rewrite something *inside* a URL that already has a scheme.
  // Without this, a path segment containing a hyphen was enough to corrupt the
  // link: `/tech-policy/2026/...` became `/tech-https://policy/2026/...`.
  const remainder = text.replace(URL_RE, (match) => {
    found.push(match);
    return " ".repeat(match.length);
  });

  // Prepend https:// to bare host/path URLs like `example.com/watch?v=...`
  const prepared = remainder.replace(BARE_HOST_RE, "https://$1");
  found.push(...(prepared.match(URL_RE) ?? []));

  const cleaned = found.map(cleanUrl).filter((u): u is string => u !== null);
  return [...new Set(cleaned)];
}

// A YouTube video ID is exactly 11 chars from this alphabet. Anything else — an
// archived article (`web_…`), a downloaded file (`dl_…`) — has no ytimg fallback,
// so return null rather than requesting a guaranteed-404 image from Google.
const YT_ID_RE = /^[A-Za-z0-9_-]{11}$/;

export function thumbnailUrl(video: {
  id: string;
  thumbnail_path?: string | null;
  kind?: string | null;
}): string | null {
  if (video.thumbnail_path) return `/stream/${video.id}/thumbnail`;
  const kind = video.kind ?? "video";
  if ((kind === "video" || kind === "audio") && YT_ID_RE.test(video.id)) {
    return `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`;
  }
  return null;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.round((seconds % 60) * 100) / 100;
  const sFmt = Number.isInteger(s)
    ? String(s).padStart(2, "0")
    : s.toFixed(2).padStart(5, "0");
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${sFmt}`;
  return `${m}:${sFmt}`;
}
