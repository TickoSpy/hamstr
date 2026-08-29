import { useState, useDeferredValue } from "react";
import { Shuffle, LayoutGrid, LayoutList, Wrench, Tags } from "lucide-react";
import { LibraryFilters } from "@/components/library/LibraryFilters";
import { VideoGrid } from "@/components/library/VideoGrid";
import { useVideos, useFixAllCodecs, useRetagAll } from "@/hooks/useVideos";
import { usePlayer } from "@/lib/playerContext";
import { useNavScroll } from "@/hooks/useNavScroll";
import { isPlayable } from "@/lib/kinds";

function useCompactPref() {
  const [compact, setCompact] = useState<boolean>(() => {
    return localStorage.getItem("library-view") !== "detailed";
  });
  const toggle = () =>
    setCompact((prev) => {
      const next = !prev;
      localStorage.setItem("library-view", next ? "compact" : "detailed");
      return next;
    });
  return [compact, toggle] as const;
}

export function LibraryPage() {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("created_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [activeKind, setActiveKind] = useState<string | null>(null);
  const [compact, toggleCompact] = useCompactPref();
  const navVisible = useNavScroll();

  const deferredSearch = useDeferredValue(search);
  const { playShuffle } = usePlayer();
  const { mutate: fixAll, isPending: isFixing } = useFixAllCodecs();
  const { mutate: retagAll, isPending: isRetagging } = useRetagAll();

  const { data, isLoading } = useVideos({
    status: "completed",
    q: deferredSearch || undefined,
    tag: activeTag ?? undefined,
    kind: activeKind ?? undefined,
    sort,
    order,
    limit: 500,
  }, { refetchInterval: false });

  // Shuffle only makes sense for things the player can actually play — a PDF in
  // the queue would stall it.
  const playableItems = (data?.items ?? []).filter(isPlayable);

  return (
    <div>
      {/* Sticky header — snaps instantly between top-14 (NavBar visible) and top-0
          (NavBar hidden). No CSS transition: animating `top` on a sticky element
          causes iOS Safari to misrender fixed elements (MiniPlayer drift) and to
          clip the sticky element's content during the animation. */}
      <div className={`sticky relative z-30 bg-gray-950 border-b border-gray-800/60 ${navVisible ? "top-14" : "top-0"}`}>
        <div className="absolute inset-x-0 -top-14 h-14 bg-gray-950 pointer-events-none" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-4 pb-3 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h1 className="text-xl font-semibold shrink-0">Library</h1>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => playShuffle(playableItems)}
                disabled={!playableItems.length}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Shuffle size={14} />
                <span className="hidden sm:inline">Shuffle</span>
              </button>
              <button
                onClick={() => fixAll()}
                disabled={isFixing}
                className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                title="Detect and transcode all non-H.264 videos to H.264 (fixes Firefox playback)"
              >
                <Wrench size={16} />
              </button>
              <button
                onClick={() => retagAll()}
                disabled={isRetagging}
                className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                title="Re-apply the automatic category and format tags to every item"
              >
                <Tags size={16} />
              </button>
              <button
                onClick={toggleCompact}
                className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
                title={compact ? "Switch to detailed view" : "Switch to compact view"}
              >
                {compact ? <LayoutList size={16} /> : <LayoutGrid size={16} />}
              </button>
            </div>
          </div>

          <LibraryFilters
            search={search}
            onSearch={setSearch}
            sort={sort}
            onSort={setSort}
            order={order}
            onOrder={setOrder}
            activeTag={activeTag}
            onTag={setActiveTag}
            activeKind={activeKind}
            onKind={setActiveKind}
          />
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-5 mb-player">
        <VideoGrid
          videos={data?.items}
          isLoading={isLoading}
          total={data?.total ?? 0}
          compact={compact}
        />
      </div>
    </div>
  );
}
