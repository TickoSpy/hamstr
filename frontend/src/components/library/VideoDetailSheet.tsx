import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Trash2, ListPlus, X, Download, WifiOff, Loader2, BookOpen, ExternalLink } from "lucide-react";
import type { Video } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import { Thumb } from "./Thumb";
import { TagEditor } from "./TagEditor";
import { useDeleteVideo } from "@/hooks/useVideos";
import { usePlaylists, useAddToPlaylist, useCreatePlaylist } from "@/hooks/usePlaylists";
import { useOffline } from "@/lib/offline/context";
import { useNavigate } from "react-router-dom";
import { isReadable, formatLabel } from "@/lib/kinds";
import { isStandalone } from "@/lib/download";
import { useSaveFile } from "@/hooks/useSaveFile";

// ---------- Playlist picker ----------

function PlaylistSection({ video, onDone }: { video: Video; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const { data: playlists } = usePlaylists();
  const add    = useAddToPlaylist();
  const create = useCreatePlaylist();

  const handleAdd = (id: number) => {
    add.mutate({ playlistId: id, videoId: video.id });
    onDone();
  };

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    const pl = await create.mutateAsync(name);
    add.mutate({ playlistId: pl.id, videoId: video.id });
    onDone();
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-gray-300 hover:bg-gray-800 transition-colors"
      >
        <ListPlus size={18} />
        <span className="text-sm font-medium">Add to playlist</span>
      </button>
    );
  }

  return (
    <div className="rounded-xl bg-gray-800/50 p-3 space-y-0.5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Add to playlist</span>
        <button onClick={() => setOpen(false)} className="text-gray-600 hover:text-gray-300">
          <X size={14} />
        </button>
      </div>
      {playlists && playlists.length > 0 ? playlists.map((pl) => (
        <button
          key={pl.id}
          onClick={() => handleAdd(pl.id)}
          className="w-full text-left px-2 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-700 transition-colors"
        >
          {pl.name}
        </button>
      )) : (
        <p className="px-2 py-1.5 text-xs text-gray-600">No playlists yet</p>
      )}
      <div className="flex items-center gap-2 pt-2">
        <input
          type="text"
          placeholder="New playlist…"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
          style={{ fontSize: "16px" }}
          className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-red-500"
        />
        <button
          onClick={handleCreate}
          className="px-3 py-1.5 rounded-lg text-sm bg-red-600 hover:bg-red-500 text-white"
        >+</button>
      </div>
    </div>
  );
}

// ---------- Offline pin ----------

function OfflineSection({ video }: { video: Video }) {
  const { supported, cachedIds, pinning, pin, unpin } = useOffline();
  if (!supported) return null;

  const isCached  = cachedIds.has(video.id);
  const isPinning = pinning.has(video.id);
  const sizeLabel = video.file_size_bytes ? formatBytes(video.file_size_bytes) : null;

  return (
    <button
      onClick={() => isCached ? unpin(video.id) : pin(video)}
      disabled={isPinning}
      className={`w-full flex items-center gap-3 px-3 py-3 rounded-xl transition-colors ${
        isCached ? "text-green-400 hover:bg-gray-800" : "text-gray-300 hover:bg-gray-800"
      }`}
    >
      {isPinning ? <Loader2 size={18} className="animate-spin" />
       : isCached ? <WifiOff size={18} />
       : <Download size={18} />}
      <span className="text-sm font-medium flex-1 text-left">
        {isPinning ? "Saving offline…" : isCached ? "Saved offline" : "Save offline"}
      </span>
      {sizeLabel && !isPinning && (
        <span className="text-xs text-gray-500">{sizeLabel}</span>
      )}
    </button>
  );
}

// ---------- Sheet ----------

export function VideoDetailSheet({ video, onClose }: { video: Video; onClose: () => void }) {
  const deleteVideo = useDeleteVideo();
  const navigate = useNavigate();

  const { save, savingHref, error: saveError } = useSaveFile();
  const downloadName =
    video.file_name ?? `${(video.title ?? video.id).replace(/[/\\?%*:|"<>]/g, "_")}`;

  // Freeze the page behind the sheet. An earlier attempt at this used
  // overflow:hidden on html/body and was blamed for every button needing two
  // taps — that turned out to be the long-press click guard staying armed
  // (see useLongPress), not the lock. Pin the body at its current offset
  // rather than only hiding overflow: iOS ignores overflow:hidden on body once
  // a touch scroll is already in flight, and pinning keeps the viewport height
  // constant, so the URL bar doesn't expand and shift the sheet.
  useEffect(() => {
    const y = window.scrollY;
    const body = document.body;
    const prev = {
      position: body.style.position,
      top: body.style.top,
      left: body.style.left,
      right: body.style.right,
      width: body.style.width,
      overflow: body.style.overflow,
    };
    body.style.position = "fixed";
    body.style.top = `-${y}px`;
    body.style.left = "0";
    body.style.right = "0";
    body.style.width = "100%";
    body.style.overflow = "hidden";
    return () => {
      Object.assign(body.style, prev);
      window.scrollTo(0, y);
    };
  }, []);

  // Escape closes on desktop.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Confirm inline rather than with confirm(). iOS swallowed the native dialog
  // on the first tap of the delete row — the tap only lit the button up — and
  // the item was deleted only on the second one.
  const [confirming, setConfirming] = useState(false);

  const handleDelete = () => {
    deleteVideo.mutate(video.id);
    onClose();
  };

  // Render through a portal so the fixed overlay is positioned against the
  // viewport regardless of any transformed ancestor. A portal only moves the
  // DOM node — React events still bubble up the *component* tree, i.e. into the
  // card that rendered this sheet, whose onClick plays the item. Tapping
  // "Delete item" therefore deleted it and then opened the player on the
  // now-missing item. Stop the gestures at the sheet's own root.
  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();

  // A backdrop press only dismisses if it began on the backdrop and stayed
  // within a finger's wobble of where it started.
  const press = useRef<{ x: number; y: number } | null>(null);
  const TAP_SLOP = 10; // px
  const wasTap = (x: number, y: number) => {
    const p = press.current;
    press.current = null;
    return !!p && Math.abs(x - p.x) <= TAP_SLOP && Math.abs(y - p.y) <= TAP_SLOP;
  };
  // No text selection / copy / paste inside the sheet: a press that lingers on
  // a title or a row used to raise iOS's selection magnifier and the
  // Copy / Look Up callout instead of hitting the control. Text fields (tags,
  // new playlist) are exempt — they still have to be typed and pasted into.
  const noCopy = (e: { preventDefault: () => void; target: EventTarget | null }) => {
    const t = e.target as HTMLElement | null;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    e.preventDefault();
  };
  return createPortal(
    <div
      className="select-none touch-callout-none [&_input]:select-text [&_textarea]:select-text"
      onClick={stop}
      onPointerDown={stop}
      onPointerUp={stop}
      onTouchStart={stop}
      onContextMenu={(e) => { stop(e); noCopy(e); }}
      onCopy={noCopy}
      onCut={noCopy}
      onPaste={noCopy}
      onSelect={noCopy}
    >
      {/* Backdrop. Closes on a tap — a press that starts *and* ends here
          without travelling. Not on pointerdown: the long-press that opened the
          sheet releases over this backdrop, and a release with no press of its
          own must be ignored, or the sheet shuts the instant the finger lifts.
          Not on a drag either: a swipe over the backdrop should do nothing at
          all, so the screen stays put on the sheet. touch-action + preventing
          touchmove keep the page from panning or rubber-banding underneath. */}
      <div
        className="fixed inset-0 z-50 bg-black/60"
        style={{ touchAction: "none" }}
        onPointerDown={(e) => { press.current = { x: e.clientX, y: e.clientY }; }}
        onPointerUp={(e) => { if (wasTap(e.clientX, e.clientY)) onClose(); }}
        onPointerCancel={() => { press.current = null; }}
        // Touch fallback: iOS can withhold pointerdown on a touch it hasn't
        // classified yet, and then the tap would never register as one.
        onTouchStart={(e) => {
          const t = e.touches[0];
          if (t && !press.current) press.current = { x: t.clientX, y: t.clientY };
        }}
        onTouchEnd={(e) => {
          const t = e.changedTouches[0];
          if (t && wasTap(t.clientX, t.clientY)) onClose();
        }}
        onTouchMove={(e) => e.preventDefault()}
      />
      <div className="fixed bottom-0 left-0 right-0 z-50 bg-gray-900 rounded-t-2xl max-h-[85vh] overflow-y-auto overscroll-contain animate-slide-up">

        {/* Drag handle — the whole row closes the sheet, with an explicit
            button on the right for anyone looking for one. */}
        <div className="sticky top-0 bg-gray-900 flex items-center pt-3 pb-2 px-3">
          <button
            onClick={onClose}
            aria-label="Close"
            className="flex-1 flex justify-center py-1 -my-1"
          >
            <div className="w-10 h-1 bg-gray-700 rounded-full" />
          </button>
          <button
            onClick={onClose}
            aria-label="Close"
            className="absolute right-2 p-2 text-gray-500 hover:text-gray-200 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Video info */}
        <div className="px-4 pb-3 flex items-center gap-3 border-b border-gray-800">
          <div className="w-16 h-10 rounded overflow-hidden flex-shrink-0">
            <Thumb item={video} iconSize={16} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-white leading-snug line-clamp-2">{video.title ?? video.url}</p>
            {video.channel && <p className="text-xs text-gray-500 mt-0.5">{video.channel}</p>}
          </div>
        </div>

        {/* Tags */}
        <div className="px-4 py-3 border-b border-gray-800">
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-2">Tags</p>
          <TagEditor video={video} />
        </div>

        {/* Actions */}
        <div className="px-3 py-2 space-y-0.5">
          {isReadable(video) && (
            <button
              onClick={() => { onClose(); navigate(`/read/${video.id}`); }}
              className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-gray-200 hover:bg-gray-800 transition-colors"
            >
              <BookOpen size={18} />
              <span className="text-sm font-medium">Open in reader</span>
            </button>
          )}
          <a
            href={video.url}
            target="_blank"
            rel="noopener noreferrer"
            className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-gray-200 hover:bg-gray-800 transition-colors"
          >
            <ExternalLink size={18} />
            <span className="text-sm font-medium">Open original</span>
          </a>
          {video.file_path && (
            <a
              href={`/stream/${video.id}/file?download=1`}
              download
              onClick={(e) => {
                // Standalone iOS ignores target=_blank for same-origin URLs and
                // navigates this window to the attachment, stranding the user on
                // the "Open with…" preview with no chrome to escape it. Share
                // the bytes instead — that sheet has a Save to Files and a Done.
                if (isStandalone()) {
                  e.preventDefault();
                  void save(`/stream/${video.id}/file?download=1`, downloadName);
                }
              }}
              className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-gray-200 hover:bg-gray-800 transition-colors"
            >
              <Download size={18} />
              <span className="text-sm font-medium">
                {savingHref ? "Saving…" : `Download ${formatLabel(video)}`}
              </span>
            </a>
          )}
          {saveError && (
            <p className="px-3 py-1 text-xs text-red-400">{saveError}</p>
          )}
          <OfflineSection video={video} />
          <PlaylistSection video={video} onDone={onClose} />
          {confirming ? (
            <div className="px-3 py-3 rounded-xl bg-red-950/40 border border-red-900 space-y-2">
              <p className="text-sm text-red-200">Delete this item and all its files?</p>
              {/* Delete sits first, on the same left edge as the "Delete item"
                  row it replaces, so the finger does not have to travel. */}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleDelete}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-500 text-white transition-colors"
                >
                  <Trash2 size={16} />
                  Delete
                </button>
                <button
                  onClick={() => setConfirming(false)}
                  className="px-3 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-red-400 hover:bg-gray-800 transition-colors"
            >
              <Trash2 size={18} />
              <span className="text-sm font-medium">Delete item</span>
            </button>
          )}
        </div>

        <div className="pb-safe" />
      </div>
    </div>,
    document.body,
  );
}
