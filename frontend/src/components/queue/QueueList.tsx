import { useState } from "react";
import { useVideos, useClearQueue } from "@/hooks/useVideos";
import { QueueItem } from "./QueueItem";
import { Loader2, Trash2 } from "lucide-react";

export function QueueList() {
  // Fetch the FRONT of the queue (oldest first) so the item actually downloading
  // is always included, not truncated off the end by the row limit.
  const { data, isLoading } = useVideos({
    status: "pending,downloading,processing,error",
    sort: "created_at",
    order: "asc",
    limit: 500,
  });
  const clearQueue = useClearQueue();

  // Downloads run FIFO, so surface what's happening now: active download(s) at
  // the top, then queued (oldest first = next up), errors last.
  const PRIORITY: Record<string, number> = { downloading: 0, processing: 1, pending: 2, error: 3 };
  const items = [...(data?.items ?? [])].sort(
    (a, b) =>
      (PRIORITY[a.status] ?? 9) - (PRIORITY[b.status] ?? 9) ||
      a.created_at.localeCompare(b.created_at)
  );
  const total = data?.total ?? items.length;

  // Inline confirm, not window.confirm(): iOS drops the native dialog on the
  // first tap of a control, so the button appeared dead until tapped twice.
  const [confirming, setConfirming] = useState(false);

  const handleClear = () => {
    setConfirming(false);
    clearQueue.mutate();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">
          Active
          {total > 0 && <span className="ml-2 text-gray-600 normal-case">{total}</span>}
          {items.length < total && (
            <span className="ml-2 text-gray-600 normal-case lowercase">
              (showing first {items.length})
            </span>
          )}
        </h2>
        {items.length > 0 && !confirming && (
          <button
            onClick={() => setConfirming(true)}
            disabled={clearQueue.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-gray-800 hover:bg-red-900/60 text-gray-400 hover:text-red-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title="Delete every queued download (completed library videos are kept)"
          >
            {clearQueue.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Trash2 size={14} />
            )}
            <span>Clear queue</span>
          </button>
        )}
        {items.length > 0 && confirming && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleClear}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-500 text-white transition-colors"
            >
              <Trash2 size={14} />
              <span>Clear {total}</span>
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="px-3 py-1.5 rounded-lg text-sm text-gray-400 hover:text-gray-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
      {confirming && (
        <p className="-mt-2 mb-4 text-xs text-gray-500">
          Deletes all {total} queued item(s). Completed videos in your library are kept.
        </p>
      )}

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="animate-spin text-gray-500" />
        </div>
      ) : !items.length ? (
        <div className="text-center py-12 text-gray-600">
          <p className="text-4xl mb-3">📥</p>
          <p>Queue is empty. Paste a YouTube URL above to get started.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((video) => (
            <QueueItem key={video.id} video={video} />
          ))}
        </div>
      )}
    </div>
  );
}
