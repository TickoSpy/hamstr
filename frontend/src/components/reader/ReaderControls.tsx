import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  SIZES,
  WIDTHS,
  type ReaderPrefs,
  type ReaderTheme,
} from "@/lib/reader/prefs";

const THEMES: { value: ReaderTheme; label: string; swatch: string }[] = [
  { value: "light", label: "Light", swatch: "bg-white text-gray-900" },
  { value: "sepia", label: "Sepia", swatch: "bg-[#f8f1e3] text-[#3b3226]" },
  { value: "dark", label: "Dark", swatch: "bg-[#0b0b0d] text-gray-100" },
];

export function ReaderControls({
  prefs,
  onChange,
  onClose,
}: {
  prefs: ReaderPrefs;
  onChange: (next: ReaderPrefs) => void;
  onClose: () => void;
}) {
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="absolute right-0 top-full mt-2 z-50 w-64 rounded-xl border border-gray-700 bg-gray-900 p-3 shadow-2xl space-y-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1.5">
            Text size
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onChange({ ...prefs, size: Math.max(0, prefs.size - 1) })}
              disabled={prefs.size === 0}
              className="flex-1 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm disabled:opacity-40"
              aria-label="Smaller text"
            >
              A<span className="text-[10px]">−</span>
            </button>
            <span className="text-xs text-gray-500 w-10 text-center tabular-nums">
              {SIZES[prefs.size]}px
            </span>
            <button
              onClick={() =>
                onChange({ ...prefs, size: Math.min(SIZES.length - 1, prefs.size + 1) })
              }
              disabled={prefs.size === SIZES.length - 1}
              className="flex-1 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-base disabled:opacity-40"
              aria-label="Larger text"
            >
              A<span className="text-xs">+</span>
            </button>
          </div>
        </div>

        <div>
          <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1.5">
            Theme
          </p>
          <div className="flex gap-2">
            {THEMES.map((t) => (
              <button
                key={t.value}
                onClick={() => onChange({ ...prefs, theme: t.value })}
                className={cn(
                  "flex-1 py-2 rounded-lg text-xs font-medium border transition-colors relative",
                  t.swatch,
                  prefs.theme === t.value
                    ? "border-red-500"
                    : "border-gray-700 hover:border-gray-500",
                )}
              >
                {t.label}
                {prefs.theme === t.value && (
                  <Check size={11} className="absolute top-1 right-1 text-red-500" />
                )}
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1.5">
            Line width
          </p>
          <div className="flex gap-2">
            {WIDTHS.map((w, i) => (
              <button
                key={w}
                onClick={() => onChange({ ...prefs, width: w })}
                className={cn(
                  "flex-1 py-1.5 rounded-lg text-xs transition-colors",
                  prefs.width === w
                    ? "bg-red-600 text-white"
                    : "bg-gray-800 text-gray-400 hover:bg-gray-700",
                )}
              >
                {["Narrow", "Normal", "Wide"][i]}
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
