import { useEffect, useRef, useState } from "react";
import { useAllTags } from "@/hooks/useTags";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

// Label -> the `kind` query value. "Text" spans both captured articles and
// downloaded documents, which is why the API takes a comma-separated list.
const KIND_FACETS: { label: string; value: string | null }[] = [
  { label: "All", value: null },
  { label: "Video", value: "video" },
  { label: "Audio", value: "audio" },
  { label: "Text", value: "article,document" },
  { label: "Images", value: "image" },
  { label: "Files", value: "file" },
];

interface Props {
  search: string;
  onSearch: (v: string) => void;
  sort: string;
  onSort: (v: string) => void;
  order: "asc" | "desc";
  onOrder: (v: "asc" | "desc") => void;
  activeTag: string | null;
  onTag: (v: string | null) => void;
  activeKind: string | null;
  onKind: (v: string | null) => void;
}

const pill = (active: boolean) =>
  cn(
    "px-3 py-1 rounded-full text-xs font-medium transition-colors",
    active ? "bg-red-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700",
  );

export function LibraryFilters({ search, onSearch, sort, onSort, order, onOrder, activeTag, onTag, activeKind, onKind }: Props) {
  // Only the tags the user typed. The automatic ones (video, mp4, pdf, text,
  // images, article, …) say nothing the kind facets above don't already say.
  const { data: tags } = useAllTags({ custom: true });

  // The tag row is a search affordance, not permanent furniture: it appears
  // when the search field is tapped and stays while a search or a tag is
  // active. Closing is deferred so a tap that lands on a pill isn't undone by
  // the blur that precedes it.
  const [tagsOpen, setTagsOpen] = useState(false);
  const live = useRef({ search, activeTag });
  live.current = { search, activeTag };
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (closeTimer.current) clearTimeout(closeTimer.current); }, []);

  const deferClose = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => {
      if (!live.current.search && !live.current.activeTag) setTagsOpen(false);
    }, 200);
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2 flex-wrap">
        {/* Search — font-size 16px prevents iOS auto-zoom on focus */}
        <div className="relative flex-1 min-w-0">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
          <input
            type="text"
            placeholder="Search titles…"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            onFocus={() => setTagsOpen(true)}
            onBlur={deferClose}
            style={{ fontSize: "16px" }}
            className="w-full pl-9 pr-8 py-2 bg-gray-900 border border-gray-700 rounded-lg text-sm leading-tight focus:outline-none focus:border-red-500"
          />
          {search && (
            <button
              onClick={() => onSearch("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-200 transition-colors"
              aria-label="Clear search"
            >
              <X size={14} />
            </button>
          )}
        </div>

        <select
          value={sort}
          onChange={(e) => onSort(e.target.value)}
          style={{ fontSize: "16px" }}
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-red-500"
        >
          <option value="created_at">Date added</option>
          <option value="title">Title</option>
          <option value="duration_seconds">Duration</option>
          <option value="updated_at">Last updated</option>
        </select>

        <button
          onClick={() => onOrder(order === "desc" ? "asc" : "desc")}
          className="px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-sm hover:border-gray-500"
          title="Toggle sort order"
        >
          {order === "desc" ? "↓" : "↑"}
        </button>
      </div>

      <div className="flex gap-2 flex-wrap">
        {KIND_FACETS.map(({ label, value }) => (
          <button
            key={label}
            onClick={() => onKind(value)}
            className={pill(activeKind === value)}
          >
            {label}
          </button>
        ))}
      </div>

      {tagsOpen && tags && tags.length > 0 && (
        <div className="flex gap-2 flex-wrap border-t border-gray-800/60 pt-3">
          <button onClick={() => onTag(null)} className={pill(activeTag === null)}>
            All tags
          </button>
          {tags.map((tag) => (
            <button
              key={tag}
              onClick={() => onTag(activeTag === tag ? null : tag)}
              className={pill(activeTag === tag)}
            >
              {tag}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
