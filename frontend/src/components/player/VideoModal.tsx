import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X, SkipBack, AlertCircle, Wrench, Minimize2 } from "lucide-react";
import { usePlayer } from "@/lib/playerContext";
import { cn, formatDuration } from "@/lib/utils";
import { Thumb } from "@/components/library/Thumb";
import { useTranscodeVideo } from "@/hooks/useVideos";
import type { Video } from "@/lib/api";

// Chrome overlay for the fullscreen video player. The <video> element itself is the
// persistent one rendered by GlobalPlayer (positioned fullscreen behind this overlay);
// this component only draws the header and the error/transcode UI. The container is
// pointer-events-none except for its controls, so the video's native controls (scrubber,
// play/pause, fullscreen) underneath stay usable.
export function VideoModal({ video, hasError, codecOk }: { video: Video; hasError: boolean; codecOk: boolean }) {
  const { hideModal, restart } = usePlayer();
  const { mutate: transcode, isPending: isTranscoding } = useTranscodeVideo();

  // Auto-hide the title/controls chrome after 5s of no interaction; any tap on
  // the screen brings it back (and restarts the timer). Mirrors how the native
  // video controls fade — a tap surfaces both.
  const [chromeVisible, setChromeVisible] = useState(true);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const poke = useCallback(() => {
    setChromeVisible(true);
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setChromeVisible(false), 5000);
  }, []);

  useEffect(() => {
    poke(); // start visible, begin the countdown
    // pointermove: on desktop, hovering resurfaces the chrome just like the
    // native controls. (Firefox never bubbles pointerdown out of a
    // native-controls <video>, so taps are caught by the layer below instead.)
    document.addEventListener("pointerdown", poke);
    document.addEventListener("pointermove", poke);
    return () => {
      document.removeEventListener("pointerdown", poke);
      document.removeEventListener("pointermove", poke);
      if (hideTimer.current) clearTimeout(hideTimer.current);
    };
  }, [poke]);

  // Lock body scroll while open; close on Escape.
  useEffect(() => {
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") hideModal(); };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey);
    };
  }, [hideModal]);

  return createPortal(
    <div className="fixed inset-0 z-50 pointer-events-none">
      {/* Tap-catcher: while the chrome is hidden, the first tap lands here and
          only resurfaces the chrome (with the minimize button) instead of
          reaching the video. Needed because Firefox swallows clicks on a
          native-controls <video> — they never bubble to the document listener.
          While the chrome is visible it lets everything through, so the native
          controls underneath stay fully usable. */}
      {!hasError && (
        <div
          className={cn(
            "absolute inset-0",
            chromeVisible ? "pointer-events-none" : "pointer-events-auto"
          )}
          onPointerDown={poke}
        />
      )}

      {/* Header bar. Inset from the top and both edges so it clears iOS's native
          video controls (fullscreen top-left, volume top-right) that appear on
          tap. pointer-events-none on the bar itself (only the buttons are
          interactive) so the freed corners let those native controls be tapped. */}
      <div className={cn(
        "pointer-events-none absolute top-0 left-0 right-0 flex items-start justify-between gap-3 px-4 pt-9 pb-3 transition-opacity duration-300",
        chromeVisible ? "opacity-100" : "opacity-0"
      )}>
        <div className="flex items-center gap-3 min-w-0 pt-0.5 [text-shadow:0_1px_4px_rgba(0,0,0,0.9)]">
          <div className="w-8 h-8 rounded overflow-hidden flex-shrink-0 shadow-lg bg-gray-800">
            <Thumb item={video} iconSize={14} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-white truncate">{video.title}</p>
            {video.channel && (
              <p className="text-xs text-gray-300/80 truncate">
                {video.channel}{video.duration_seconds ? ` · ${formatDuration(video.duration_seconds)}` : ""}
              </p>
            )}
          </div>
        </div>
        <div className={cn(
          "flex items-center gap-2 flex-shrink-0",
          chromeVisible ? "pointer-events-auto" : "pointer-events-none"
        )}>
          <button
            onClick={restart}
            title="Play from start"
            aria-label="Play from start"
            className="flex items-center justify-center w-9 h-9 rounded-full bg-black/40 text-gray-100 hover:bg-white/20 hover:text-white transition-colors"
          >
            <SkipBack size={18} fill="currentColor" />
          </button>
          <button
            onClick={hideModal}
            title="Minimize"
            aria-label="Minimize"
            className="flex items-center justify-center w-9 h-9 rounded-full bg-black/40 text-gray-100 hover:bg-white/20 hover:text-white transition-colors"
          >
            <Minimize2 size={18} />
          </button>
        </div>
      </div>

      {/* Error / unsupported-codec overlay (covers the hidden video) */}
      {hasError && (
        <div className="pointer-events-auto absolute inset-0 bg-black flex items-center justify-center">
          <div className="text-center p-6">
            <AlertCircle size={36} className="text-gray-600 mx-auto mb-3" />
            <p className="text-gray-300 text-sm font-medium mb-1">This video cannot be played</p>
            <p className="text-gray-500 text-xs mb-5">
              {!codecOk
                ? `Your browser does not support ${video.codec?.toUpperCase()} video.`
                : "The video file could not be loaded."}
            </p>
            <div className="flex items-center gap-2 justify-center">
              {!video.audio_only && (
                <button
                  onClick={() => { transcode(video.id); hideModal(); }}
                  disabled={isTranscoding}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
                >
                  <Wrench size={14} />
                  {isTranscoding ? "Transcoding…" : "Transcode to H.264"}
                </button>
              )}
              <button
                onClick={hideModal}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 text-sm font-medium transition-colors"
              >
                <X size={14} /> Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>,
    document.body,
  );
}
