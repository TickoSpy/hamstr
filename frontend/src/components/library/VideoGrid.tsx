import type { Video } from "@/lib/api";
import { VideoCard } from "./VideoCard";
import { CompactVideoCard } from "./CompactVideoCard";
import { Loader2 } from "lucide-react";

interface Props {
  videos: Video[] | undefined;
  isLoading: boolean;
  total: number;
  compact?: boolean;
}

export function VideoGrid({ videos, isLoading, total, compact = false }: Props) {
  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="animate-spin text-gray-500" size={28} />
      </div>
    );
  }

  if (!videos?.length) {
    return (
      <div className="text-center py-20 text-gray-600">
        <p className="text-4xl mb-3">🎬</p>
        <p>Nothing archived yet. Add a link from the Queue page.</p>
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs text-gray-600 mb-4">{total} video{total !== 1 ? "s" : ""}</p>
      {compact ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          {videos.map((video) => (
            <CompactVideoCard key={video.id} video={video} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
          {videos.map((video) => (
            <VideoCard key={video.id} video={video} />
          ))}
        </div>
      )}
    </div>
  );
}
