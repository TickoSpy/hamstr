const KEY = 'yt-positions';

export function getPos(id: string): number {
  try {
    return (JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, number>)[id] ?? 0;
  } catch { return 0; }
}

export function setPos(id: string, seconds: number): void {
  try {
    const d: Record<string, number> = JSON.parse(localStorage.getItem(KEY) ?? '{}');
    // Kept to a tenth of a second: rounding down to whole seconds lost up to a
    // second every time playback resumed from a saved position.
    d[id] = Math.round(seconds * 10) / 10;
    localStorage.setItem(KEY, JSON.stringify(d));
  } catch {}
}

export function clearPos(id: string): void {
  try {
    const d: Record<string, number> = JSON.parse(localStorage.getItem(KEY) ?? '{}');
    delete d[id];
    localStorage.setItem(KEY, JSON.stringify(d));
  } catch {}
}
