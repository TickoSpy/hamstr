/** Scroll position per article, mirroring lib/positions.ts for playback. */

const KEY = "yt-reader-progress";

type Store = Record<string, number>;

function read(): Store {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Store;
  } catch {
    return {};
  }
}

/** Fraction 0–1 of the way through the article. */
export function getProgress(id: string): number {
  const value = read()[id];
  return typeof value === "number" && value >= 0 && value <= 1 ? value : 0;
}

export function setProgress(id: string, fraction: number): void {
  try {
    const store = read();
    store[id] = Math.min(1, Math.max(0, fraction));
    localStorage.setItem(KEY, JSON.stringify(store));
  } catch {
    /* ignore */
  }
}

export function clearProgress(id: string): void {
  try {
    const store = read();
    delete store[id];
    localStorage.setItem(KEY, JSON.stringify(store));
  } catch {
    /* ignore */
  }
}
