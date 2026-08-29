import { useState } from "react";
import { Play, Shuffle, Plus, Trash2, ChevronDown, ChevronRight, Music2 } from "lucide-react";
import {
  usePlaylists,
  usePlaylist,
  useCreatePlaylist,
  useDeletePlaylist,
  useRemoveFromPlaylist,
} from "@/hooks/usePlaylists";
import { usePlayer } from "@/lib/playerContext";
import { formatDuration } from "@/lib/utils";
import { isPlayable } from "@/lib/kinds";
import { Thumb } from "./Thumb";

function PlaylistDetail({ playlistId, onDelete }: { playlistId: number; onDelete: () => void }) {
  const { data: playlist, isLoading, isError, error } = usePlaylist(playlistId);
  const removeItem = useRemoveFromPlaylist();
  const deletePlaylist = useDeletePlaylist();
  const { playQueue, playShuffle } = usePlayer();
  // Inline confirm — see QueueList: iOS eats the first tap on confirm().
  const [confirming, setConfirming] = useState(false);

  // Don't sit on "Loading…" forever when the request failed — that hid a 500
  // from a playlist row pointing at a deleted item.
  if (isError)
    return (
      <p className="px-4 py-3 text-xs text-red-400">
        Could not load this playlist{error instanceof Error ? `: ${error.message}` : ""}
      </p>
    );
  if (isLoading || !playlist)
    return <p className="px-4 py-3 text-xs text-gray-600">Loading…</p>;

  const items = playlist.items.map((item) => item.video);
  // A playlist can contain anything the user dragged in; the player can't.
  const videos = items.filter(isPlayable);

  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-800">
        <span className="text-xs text-gray-500 mr-1">{playlist.items.length} videos</span>
        {videos.length > 0 && (
          <>
            <button
              onClick={() => playQueue(videos)}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-red-600 hover:bg-red-500 text-white"
            >
              <Play size={10} fill="currentColor" /> Play
            </button>
            <button
              onClick={() => playShuffle(videos)}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-gray-700 hover:bg-gray-600 text-white"
            >
              <Shuffle size={10} /> Shuffle
            </button>
          </>
        )}
        {confirming ? (
          <div className="ml-auto flex items-center gap-1.5">
            <span className="text-xs text-red-300">Delete playlist?</span>
            <button
              onClick={() => {
                deletePlaylist.mutate(playlistId);
                onDelete();
              }}
              className="px-2 py-1 rounded text-xs font-medium bg-red-600 hover:bg-red-500 text-white transition-colors"
            >
              Delete
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="px-2 py-1 rounded text-xs text-gray-400 hover:text-gray-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            className="ml-auto p-1 text-gray-600 hover:text-red-400 transition-colors"
            title="Delete playlist"
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>

      {playlist.items.length === 0 ? (
        <p className="px-4 py-4 text-xs text-gray-600">
          No videos yet. Add videos from the Library.
        </p>
      ) : (
        playlist.items.map((item) => (
          <div
            key={item.id}
            className="flex items-center gap-3 px-4 py-1.5 hover:bg-gray-800 group"
          >
            <div className="w-12 h-7 rounded overflow-hidden flex-shrink-0 bg-gray-800">
              <Thumb item={item.video} iconSize={12} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-300 truncate">
                {item.video.title ?? item.video_id}
              </p>
              {item.video.duration_seconds && (
                <p className="text-xs text-gray-600">
                  {formatDuration(item.video.duration_seconds)}
                </p>
              )}
            </div>
            <button
              onClick={() =>
                removeItem.mutate({ playlistId, videoId: item.video_id })
              }
              className="opacity-0 group-hover:opacity-100 p-1 text-gray-600 hover:text-red-400 transition-colors"
              title="Remove from playlist"
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))
      )}
    </div>
  );
}

export function PlaylistPanel() {
  const { data: playlists } = usePlaylists();
  const createPlaylist = useCreatePlaylist();
  const [expanded, setExpanded] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    await createPlaylist.mutateAsync(name);
    setNewName("");
    setCreating(false);
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <Music2 size={15} className="text-gray-400" />
          <h2 className="text-sm font-semibold text-gray-200">Playlists</h2>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
        >
          <Plus size={12} /> New
        </button>
      </div>

      {creating && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-800 bg-gray-900">
          <input
            autoFocus
            type="text"
            placeholder="Playlist name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
              if (e.key === "Escape") setCreating(false);
            }}
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs focus:outline-none focus:border-red-500"
          />
          <button
            onClick={handleCreate}
            className="px-2 py-1 rounded text-xs bg-red-600 hover:bg-red-500 text-white"
          >
            Create
          </button>
          <button
            onClick={() => setCreating(false)}
            className="px-2 py-1 rounded text-xs text-gray-400 hover:text-white"
          >
            Cancel
          </button>
        </div>
      )}

      {(!playlists || playlists.length === 0) && !creating && (
        <p className="px-4 py-6 text-sm text-gray-600 text-center">No playlists yet.</p>
      )}

      {playlists?.map((pl) => (
        <div key={pl.id} className="border-b border-gray-800 last:border-0">
          <button
            onClick={() => setExpanded(expanded === pl.id ? null : pl.id)}
            className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-800 transition-colors text-left"
          >
            {expanded === pl.id ? (
              <ChevronDown size={14} className="text-gray-500 flex-shrink-0" />
            ) : (
              <ChevronRight size={14} className="text-gray-500 flex-shrink-0" />
            )}
            <span className="flex-1 text-sm text-gray-200 truncate">{pl.name}</span>
            <span className="text-xs text-gray-600 flex-shrink-0">{pl.item_count}</span>
          </button>
          {expanded === pl.id && (
            <PlaylistDetail playlistId={pl.id} onDelete={() => setExpanded(null)} />
          )}
        </div>
      ))}
    </div>
  );
}
