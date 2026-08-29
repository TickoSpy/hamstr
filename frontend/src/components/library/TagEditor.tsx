import { useState, useRef, useEffect } from "react";
import { X, Plus } from "lucide-react";
import { useAddTag, useRemoveTag, useAllTags } from "@/hooks/useTags";
import type { Video } from "@/lib/api";

/**
 * `hideAuto` drops the automatic category/format tags (video, mp4, pdf, …) from
 * the chips. On a library card they are pure noise — the thumbnail already
 * carries a format badge and the filter row has the same names as facets. The
 * detail sheet still lists them, so they stay removable.
 */
export function TagEditor({ video, hideAuto = false }: { video: Video; hideAuto?: boolean }) {
  const [input, setInput] = useState("");
  const [open, setOpen] = useState(false);
  const addTag = useAddTag();
  const removeTag = useRemoveTag();
  const { data: allTags } = useAllTags();
  const { data: customTags } = useAllTags({ custom: true });
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const currentNames = video.tags.map((t) => t.name);
  const shownTags = hideAuto
    ? video.tags.filter((t) => (customTags ?? []).includes(t.name))
    : video.tags;
  const suggestions = (allTags ?? []).filter(
    (t) => !currentNames.includes(t) && t.includes(input.toLowerCase())
  );

  const add = (name: string) => {
    const n = name.trim().toLowerCase();
    if (!n) return;
    addTag.mutate({ videoId: video.id, name: n });
    setInput("");
  };

  return (
    <div ref={ref} className="relative">
      <div className="flex flex-wrap gap-1 items-center">
        {shownTags.map((tag) => (
          <span
            key={tag.id}
            className="flex items-center gap-1 bg-gray-700 text-gray-300 text-xs px-2 py-0.5 rounded-full"
          >
            {tag.name}
            <button
              onClick={(e) => {
                e.stopPropagation();
                removeTag.mutate({ videoId: video.id, name: tag.name });
              }}
              className="hover:text-white"
            >
              <X size={10} />
            </button>
          </span>
        ))}
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1 bg-gray-800 hover:bg-gray-700 text-gray-400 text-xs px-2 py-0.5 rounded-full"
        >
          <Plus size={10} /> tag
        </button>
      </div>

      {open && (
        <div className="absolute top-full left-0 mt-1 z-20 bg-gray-900 border border-gray-700 rounded-lg p-2 w-52 shadow-xl">
          <input
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") add(input);
              if (e.key === "Escape") setOpen(false);
            }}
            placeholder="Tag name…"
            className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-red-500"
          />
          {suggestions.length > 0 && (
            <div className="mt-1 space-y-0.5">
              {suggestions.slice(0, 8).map((s) => (
                <button
                  key={s}
                  onClick={() => add(s)}
                  className="w-full text-left text-xs px-2 py-1 rounded hover:bg-gray-700 text-gray-300"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
