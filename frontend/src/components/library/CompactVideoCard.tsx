import { useState } from "react";
import { Play, Headphones, WifiOff } from "lucide-react";
import type { Video } from "@/lib/api";
import { formatDuration } from "@/lib/utils";
import { Thumb } from "./Thumb";
import { usePlayer } from "@/lib/playerContext";
import { useLongPress } from "@/hooks/useLongPress";
import { useOffline } from "@/lib/offline/context";
import { useNavigate } from "react-router-dom";
import { primaryAction, isPlayable, itemKind, KIND_ICON } from "@/lib/kinds";
import { VideoDetailSheet } from "./VideoDetailSheet";

export function CompactVideoCard({ video }: { video: Video }) {
  const { play, playQueue } = usePlayer();
  const navigate = useNavigate();
  const OverlayIcon = KIND_ICON[itemKind(video)];

  const handleOpen = () => {
    const action = primaryAction(video);
    if (action.type === "play") {
      itemKind(video) === "audio" ? playQueue([video]) : play(video);
    } else if (action.type === "read") {
      navigate(action.to);
    } else {
      window.open(action.href, "_blank", "noopener");
    }
  };
  const [sheetOpen, setSheetOpen] = useState(false);
  const longPress   = useLongPress(() => setSheetOpen(true));
  const { cachedIds } = useOffline();
  const isCached    = cachedIds.has(video.id);

  return (
    <div
      className="group cursor-pointer select-none touch-callout-none"
      onClick={handleOpen}
      {...longPress}
    >
      <div className="relative aspect-video bg-gray-800 overflow-hidden rounded-lg">
        <Thumb item={video} iconSize={24} />
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 group-active:opacity-100 transition-opacity flex items-center justify-center">
          {isPlayable(video)
            ? (video.audio_only
                ? <Headphones size={24} className="text-white" />
                : <Play size={24} className="text-white" fill="white" />)
            : <OverlayIcon size={24} className="text-white" />}
        </div>
        {video.audio_only && (
          <span className="absolute top-1.5 left-1.5 flex items-center gap-0.5 bg-black/70 text-white text-[10px] px-1 py-0.5 rounded">
            <Headphones size={9} /> Audio
          </span>
        )}
        {video.duration_seconds && (
          <span className="absolute bottom-1.5 right-1.5 bg-black/80 text-white text-[10px] px-1 py-0.5 rounded">
            {formatDuration(video.duration_seconds)}
          </span>
        )}
        {isCached && (
          <span className="absolute bottom-1.5 left-1.5 flex items-center gap-0.5 bg-green-900/80 text-green-300 text-[10px] px-1 py-0.5 rounded">
            <WifiOff size={8} /> offline
          </span>
        )}
      </div>
      <p className="mt-1.5 text-xs text-gray-200 line-clamp-2 leading-tight px-0.5">
        {video.title ?? video.url}
      </p>
      {sheetOpen && <VideoDetailSheet video={video} onClose={() => setSheetOpen(false)} />}
    </div>
  );
}
