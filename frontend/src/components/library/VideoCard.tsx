import { useState } from "react";
import { Play, Trash2, ListPlus, RefreshCw, Headphones, Download, WifiOff, Loader2 } from "lucide-react";
import type { Video } from "@/lib/api";
import { formatDuration, formatBytes } from "@/lib/utils";
import { Thumb } from "./Thumb";
import { TagEditor } from "./TagEditor";
import { DownloadButtons } from "./DownloadButtons";
import { VideoDetailSheet } from "./VideoDetailSheet";
import { useDeleteVideo, useTranscodeVideo } from "@/hooks/useVideos";
import { usePlaylists, useAddToPlaylist, useCreatePlaylist } from "@/hooks/usePlaylists";
import { usePlayer } from "@/lib/playerContext";
import { useLongPress } from "@/hooks/useLongPress";
import { useOffline } from "@/lib/offline/context";
import { useNavigate } from "react-router-dom";
import { primaryAction, itemKind, formatLabel, isPlayable, KIND_ICON } from "@/lib/kinds";

// ---------- Playlist menu ----------

function AddToPlaylistMenu({ video }: { video: Video }) {
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const { data: playlists } = usePlaylists();
  const addToPlaylist  = useAddToPlaylist();
  const createPlaylist = useCreatePlaylist();

  const handleAdd = (playlistId: number) => {
    addToPlaylist.mutate({ playlistId, videoId: video.id });
    setOpen(false);
  };

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    const pl = await createPlaylist.mutateAsync(name);
    addToPlaylist.mutate({ playlistId: pl.id, videoId: video.id });
    setNewName("");
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        className="p-1.5 text-gray-600 hover:text-gray-300 transition-colors rounded"
        title="Add to playlist"
      >
        <ListPlus size={14} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute bottom-8 right-0 z-20 w-52 bg-gray-900 border border-gray-700 rounded-lg shadow-xl py-1">
            {playlists && playlists.length > 0 ? (
              playlists.map((pl) => (
                <button
                  key={pl.id}
                  onClick={() => handleAdd(pl.id)}
                  className="w-full px-3 py-1.5 text-xs text-left text-gray-300 hover:bg-gray-800 truncate"
                >
                  {pl.name}
                </button>
              ))
            ) : (
              <p className="px-3 py-1.5 text-xs text-gray-600">No playlists yet</p>
            )}
            <div className="border-t border-gray-800 mt-1 pt-1 px-2 pb-1">
              <div className="flex items-center gap-1">
                <input
                  type="text"
                  placeholder="New playlist…"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => { e.stopPropagation(); if (e.key === "Enter") handleCreate(); }}
                  onClick={(e) => e.stopPropagation()}
                  className="flex-1 bg-gray-800 border border-gray-700 rounded px-1.5 py-0.5 text-xs focus:outline-none focus:border-red-500"
                />
                <button
                  onClick={handleCreate}
                  className="px-1.5 py-0.5 rounded text-xs bg-red-600 hover:bg-red-500 text-white"
                >+</button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ---------- Codec badge ----------

function CodecBadge({ video }: { video: Video }) {
  const transcode = useTranscodeVideo();
  const codec     = video.codec;

  if (codec === "transcoding") {
    return (
      <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-yellow-900/50 text-yellow-400 border border-yellow-800">
        <RefreshCw size={10} className="animate-spin" /> Transcoding…
      </span>
    );
  }

  const isH264 = codec === "h264";
  const label  = codec ? codec.toUpperCase().replace("H264", "H.264").replace("HEVC", "HEVC") : null;

  return (
    <div className="flex items-center gap-1.5">
      {label && (
        <span className={`px-1.5 py-0.5 rounded text-xs border ${
          isH264
            ? "bg-green-900/40 text-green-400 border-green-800"
            : "bg-orange-900/40 text-orange-400 border-orange-800"
        }`}>
          {label}
        </span>
      )}
      {!isH264 && (
        <button
          onClick={(e) => { e.stopPropagation(); transcode.mutate(video.id); }}
          disabled={transcode.isPending}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white border border-gray-700 transition-colors disabled:opacity-50"
          title="Transcode to H.264 for Safari compatibility"
        >
          <RefreshCw size={10} /> {codec ? "Transcode" : "Check & fix"}
        </button>
      )}
    </div>
  );
}

// ---------- Offline pin button ----------

function PinButton({ video }: { video: Video }) {
  const { supported, cachedIds, pinning, pin, unpin } = useOffline();
  if (!supported) return null;

  const isCached  = cachedIds.has(video.id);
  const isPinning = pinning.has(video.id);

  return (
    <button
      onClick={(e) => { e.stopPropagation(); isCached ? unpin(video.id) : pin(video); }}
      disabled={isPinning}
      className={`p-1.5 transition-colors rounded ${
        isCached ? "text-green-400 hover:text-red-400" : "text-gray-600 hover:text-gray-300"
      }`}
      title={isCached ? "Remove offline copy" : "Save offline"}
    >
      {isPinning
        ? <Loader2 size={14} className="animate-spin" />
        : isCached ? <WifiOff size={14} /> : <Download size={14} />}
    </button>
  );
}

// ---------- Card ----------

export function VideoCard({ video }: { video: Video }) {
  const deleteVideo = useDeleteVideo();
  const { play, playQueue } = usePlayer();
  const navigate = useNavigate();
  const kind = itemKind(video);
  const OverlayIcon = KIND_ICON[kind];

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
  // Two-step inline confirm instead of confirm(): iOS never surfaced the
  // native dialog on the first tap of the trash icon — the tap only lit the
  // button — so the item died on the second tap. Same fix as the sheet.
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <div
      className="group bg-gray-900 border border-gray-800 rounded-xl hover:border-gray-600 transition-colors select-none touch-callout-none"
      {...longPress}
    >
      {/* Thumbnail */}
      <div
        className="relative cursor-pointer aspect-video bg-gray-800 overflow-hidden rounded-t-xl"
        onClick={handleOpen}
      >
        <Thumb item={video} />
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
          {isPlayable(video)
            ? (video.audio_only
                ? <Headphones size={32} className="text-white" />
                : <Play size={32} className="text-white" fill="white" />)
            : <OverlayIcon size={32} className="text-white" />}
        </div>
        <span className="absolute top-2 left-2 flex items-center gap-1 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded">
          {video.audio_only && <Headphones size={10} />}
          {formatLabel(video)}
        </span>
        {video.paywalled && (
          <span className="absolute top-2 right-2 bg-amber-900/80 text-amber-200 text-[10px] px-1.5 py-0.5 rounded">
            paywalled
          </span>
        )}
        {video.duration_seconds && (
          <span className="absolute bottom-2 right-2 bg-black/80 text-white text-xs px-1.5 py-0.5 rounded">
            {formatDuration(video.duration_seconds)}
          </span>
        )}
      </div>

      {/* Info & actions */}
      <div className="p-4 space-y-3">
        <div>
          <p
            className="text-sm font-medium text-gray-100 line-clamp-2 cursor-pointer hover:text-red-400"
            onClick={handleOpen}
            title={video.title ?? undefined}
          >
            {video.title ?? video.url}
          </p>
          {video.channel && (
            <p className="text-xs text-gray-500 mt-0.5">{video.channel}</p>
          )}
        </div>

        <TagEditor video={video} hideAuto />
        <DownloadButtons video={video} />
        {kind === "video" && <CodecBadge video={video} />}

        <div className="flex items-center justify-between pt-1">
          <span className="text-xs text-gray-600">{formatBytes(video.file_size_bytes)}</span>
          <div className="flex items-center gap-0.5">
            <PinButton video={video} />
            <AddToPlaylistMenu video={video} />
            {confirmDelete ? (
              <>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="px-2 py-1 text-xs text-gray-400 hover:text-gray-200 transition-colors rounded"
                >
                  Cancel
                </button>
                <button
                  onClick={() => deleteVideo.mutate(video.id)}
                  className="px-2 py-1 text-xs font-medium bg-red-600 hover:bg-red-500 text-white transition-colors rounded"
                >
                  Delete
                </button>
              </>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                className="p-1.5 text-gray-600 hover:text-red-400 transition-colors rounded"
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </div>
      </div>

      {sheetOpen && <VideoDetailSheet video={video} onClose={() => setSheetOpen(false)} />}
    </div>
  );
}
