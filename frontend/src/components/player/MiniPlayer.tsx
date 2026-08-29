import { useEffect, useRef, useState } from "react";
import { Play, Pause, RotateCcw, Maximize2, X, SkipBack, SkipForward, Shuffle } from "lucide-react";
import { usePlayer } from "@/lib/playerContext";
import { formatDuration, cn } from "@/lib/utils";
import { Thumb } from "@/components/library/Thumb";
import { itemKind } from "@/lib/kinds";

export function MiniPlayer() {
  const { current, queue, queueIndex, isShuffling, videoRef, audioRef, openModal, close, restart, next, previous, toggleShuffle } = usePlayer();
  const [paused, setPaused] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const raf = useRef<number>(0);

  // Audio-only items play on the <audio> element (it survives a screen lock);
  // everything else on the <video>. The controls have to follow the same one.
  const isAudioItem = !!current && itemKind(current) === "audio";
  const mediaEl = () => (isAudioItem ? audioRef.current : videoRef.current);

  useEffect(() => {
    const el = isAudioItem ? audioRef.current : videoRef.current;
    if (!el) return;
    const onPlay = () => setPaused(false);
    const onPause = () => setPaused(true);
    const onDuration = () => setDuration(isFinite(el.duration) ? el.duration : 0);
    const onEnded = () => { setPaused(true); setCurrentTime(0); };
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("durationchange", onDuration);
    el.addEventListener("ended", onEnded);
    setPaused(el.paused);
    setCurrentTime(el.currentTime);
    setDuration(isFinite(el.duration) ? el.duration : 0);
    return () => {
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("durationchange", onDuration);
      el.removeEventListener("ended", onEnded);
    };
  }, [current?.id, isAudioItem, videoRef, audioRef]);

  useEffect(() => {
    const tick = () => {
      const el = isAudioItem ? audioRef.current : videoRef.current;
      if (el && !el.paused) setCurrentTime(el.currentTime);
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [isAudioItem, videoRef, audioRef]);

  if (!current) return null;

  const progress = duration > 0 ? currentTime / duration : 0;
  const inQueue = queue.length > 1;
  const canExpand = !current.audio_only;

  const togglePlay = () => {
    const el = mediaEl();
    if (!el) return;
    if (el.paused) el.play().catch(() => {});
    else el.pause();
  };

  const seek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const el = mediaEl();
    if (!el) return;
    const t = parseFloat(e.target.value) * duration;
    el.currentTime = t;
    setCurrentTime(t);
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 bg-gray-950 border-t border-gray-800 pb-safe transform-gpu">
      {/* Thin progress bar at very top of player */}
      <div className="w-full h-0.5 bg-gray-800">
        <div className="h-full bg-red-500 transition-none" style={{ width: `${progress * 100}%` }} />
      </div>

      <div className="px-3 sm:px-4 py-2 flex items-center gap-2 sm:gap-3">
        {/* Thumbnail — tapping opens modal */}
        <div
          className="w-10 h-10 rounded overflow-hidden flex-shrink-0 cursor-pointer bg-gray-800"
          onClick={openModal}
        >
          <Thumb item={current} iconSize={16} />
        </div>

        {/* Title + time — grow to fill space */}
        <div className="flex-1 min-w-0 cursor-pointer" onClick={openModal}>
          <p className="text-xs font-medium text-gray-100 truncate">
            {current.title ?? current.url}
          </p>
          <p className="text-xs text-gray-500 mt-0.5">
            {formatDuration(Math.floor(currentTime))}
            {duration > 0 && <> / {formatDuration(Math.floor(duration))}</>}
            {inQueue && <span className="ml-2">{queueIndex + 1}/{queue.length}</span>}
          </p>
        </div>

        {/* Seek bar — hidden on mobile, visible from sm */}
        <input
          type="range"
          min={0}
          max={1}
          step={0.001}
          value={progress}
          onChange={seek}
          className="hidden sm:block w-28 md:w-48 h-1 accent-red-500 cursor-pointer flex-shrink-0"
        />

        {/* Controls */}
        <div className="flex items-center gap-0 flex-shrink-0">
          {inQueue && (
            <button onClick={toggleShuffle} className={cn("p-2 hidden sm:block transition-colors", isShuffling ? "text-red-400" : "text-gray-600 hover:text-gray-300")} title="Shuffle">
              <Shuffle size={13} />
            </button>
          )}
          {inQueue && (
            <button onClick={previous} className="p-2 text-gray-500 hover:text-gray-200 transition-colors" title="Previous">
              <SkipBack size={16} fill="currentColor" />
            </button>
          )}
          <button onClick={togglePlay} className="p-2 text-gray-200 hover:text-white transition-colors" title={paused ? "Play" : "Pause"}>
            {paused ? <Play size={18} fill="currentColor" /> : <Pause size={18} fill="currentColor" />}
          </button>
          {inQueue && (
            <button onClick={next} className="p-2 text-gray-500 hover:text-gray-200 transition-colors" title="Next">
              <SkipForward size={16} fill="currentColor" />
            </button>
          )}
          <button onClick={restart} className="p-2 text-gray-600 hover:text-gray-300 transition-colors hidden sm:block" title="Restart">
            <RotateCcw size={14} />
          </button>
          {canExpand && (
            <button onClick={openModal} className="p-2 text-gray-600 hover:text-gray-300 transition-colors hidden sm:block" title="Open video">
              <Maximize2 size={14} />
            </button>
          )}
          <button onClick={close} className="p-2 text-gray-600 hover:text-red-400 transition-colors" title="Stop">
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
