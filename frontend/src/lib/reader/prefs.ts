export type ReaderTheme = "light" | "sepia" | "dark";

export interface ReaderPrefs {
  theme: ReaderTheme;
  /** Index into SIZES. */
  size: number;
  /** Measure in ch units. */
  width: number;
}

/** 16 → 22px, the range iOS Reader spans. */
export const SIZES = [16, 17.5, 19, 20.5, 22] as const;
export const WIDTHS = [58, 68, 80] as const;

const KEY = "yt-reader-prefs";

export const DEFAULT_PREFS: ReaderPrefs = { theme: "dark", size: 1, width: 68 };

export function loadPrefs(): ReaderPrefs {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<ReaderPrefs>;
    return {
      theme: raw.theme === "light" || raw.theme === "sepia" || raw.theme === "dark"
        ? raw.theme
        : DEFAULT_PREFS.theme,
      size:
        typeof raw.size === "number" && raw.size >= 0 && raw.size < SIZES.length
          ? raw.size
          : DEFAULT_PREFS.size,
      width: WIDTHS.includes(raw.width as (typeof WIDTHS)[number])
        ? (raw.width as number)
        : DEFAULT_PREFS.width,
    };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function savePrefs(prefs: ReaderPrefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* private mode / quota — prefs just don't persist */
  }
}
