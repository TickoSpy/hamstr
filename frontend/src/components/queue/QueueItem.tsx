import { useState } from "react";
import { Trash2, RotateCcw } from "lucide-react";
import { type Video } from "@/lib/api";
import { Thumb } from "@/components/library/Thumb";
import { formatLabel } from "@/lib/kinds";
import { useDeleteVideo, useRetryVideo } from "@/hooks/useVideos";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-700 text-gray-300",
  downloading: "bg-blue-900 text-blue-300",
  processing: "bg-yellow-900 text-yellow-300",
  completed: "bg-green-900 text-green-300",
  error: "bg-red-900 text-red-300",
};

export function QueueItem({ video }: { video: Video }) {
  const [hovered, setHovered] = useState(false);
  const del = useDeleteVideo();
  const retry = useRetryVideo();
  const color = STATUS_COLORS[video.status] ?? STATUS_COLORS.pending;
  const title = video.title ?? video.url;
  const showDelete = video.status !== "completed";

  return (
    <div
      className="flex items-center gap-4 p-4 bg-gray-900 rounded-lg border border-gray-800"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="w-20 h-12 rounded overflow-hidden flex-shrink-0 bg-gray-800">
        <Thumb item={video} iconSize={18} />
      </div>

      <div className="flex-1 min-w-0 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${color}`}>
            {video.status}
          </span>
          <span className="bg-gray-800 text-gray-400 text-xs px-2 py-0.5 rounded-full">
            {formatLabel(video)}
          </span>
          {video.channel && (
            <span className="text-xs text-gray-500 truncate">{video.channel}</span>
          )}
        </div>
        <p className="text-sm text-gray-200 truncate" title={title}>
          {title}
        </p>

        {video.status === "pending" && (
          <div className="w-full bg-gray-800 rounded-full h-1.5" />
        )}
        {(video.status === "downloading" || video.status === "processing") && (
          <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
            {video.status === "processing" ? (
              <div className="h-1.5 bg-red-700 animate-pulse w-full" />
            ) : (
              <div
                className="bg-red-500 h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${video.progress}%` }}
              />
            )}
          </div>
        )}

        {video.status === "error" && (
          <p className="text-xs text-red-400 truncate">{video.error_message}</p>
        )}
      </div>

      <div className="flex-shrink-0 flex items-center gap-2">
        {video.status === "downloading" && (
          <span className="text-xs text-gray-500 w-8 text-right tabular-nums">{video.progress.toFixed(0)}%</span>
        )}
        {video.status === "error" && (
          <button
            onClick={() => retry.mutate(video.id)}
            disabled={retry.isPending}
            title="Retry download"
            className="p-1 text-gray-500 hover:text-green-400 disabled:opacity-40 transition-colors"
          >
            <RotateCcw size={14} />
          </button>
        )}
        {showDelete && (hovered || video.status === "error") && (
          <button
            onClick={() => del.mutate(video.id)}
            disabled={del.isPending}
            title="Remove from queue"
            className="p-1 text-gray-600 hover:text-red-400 disabled:opacity-40 transition-colors"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
