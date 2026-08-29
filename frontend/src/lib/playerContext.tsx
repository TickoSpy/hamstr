import { createContext, useContext, useRef, useState, useCallback, type ReactNode, type RefObject } from "react";
import type { Video } from "@/lib/api";
import { clearPos } from "@/lib/positions";
import { itemKind } from "@/lib/kinds";

function shuffled<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export interface PlayerCtxValue {
  current: Video | null;
  queue: Video[];
  queueIndex: number;
  isShuffling: boolean;
  isModalOpen: boolean;
  play: (video: Video) => void;
  playQueue: (videos: Video[], startIndex?: number) => void;
  playShuffle: (videos: Video[]) => void;
  next: () => void;
  previous: () => void;
  toggleShuffle: () => void;
  openModal: () => void;
  hideModal: () => void;
  close: () => void;
  restart: () => void;
  removeVideo: (videoId: string) => void;
  audioRef: RefObject<HTMLAudioElement | null>;
  videoRef: RefObject<HTMLVideoElement | null>;
}

const PlayerCtx = createContext<PlayerCtxValue | null>(null);

export function usePlayer(): PlayerCtxValue {
  const v = useContext(PlayerCtx);
  if (!v) throw new Error("usePlayer outside PlayerProvider");
  return v;
}

// A 44-byte silent WAV. Playing it (muted) inside the user gesture that starts
// playback "unlocks" the otherwise-idle <audio> element so iOS will later let us
// start it from the background — that's the element the lock-screen handoff and
// the lock-screen play button drive while the screen is off.
const SILENT_WAV =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";

function primeAudioElement(a: HTMLAudioElement | null) {
  if (!a || a.dataset.iosPrimed) return;
  a.dataset.iosPrimed = "1";
  a.muted = true;
  a.src = SILENT_WAV;
  // The play() promise settles a tick later — by then a real track may already
  // own this element (audio-only items play on it from the start). Only clean
  // up if the silent clip is still what's loaded, otherwise we'd pause the
  // track and tear out its source the instant it started.
  const release = () => {
    a.muted = false;
    if (a.src === SILENT_WAV) {
      a.pause();
      a.removeAttribute("src"); // leave it clean; the handoff sets the real src
    }
  };
  a.play().then(release, release);
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<Video | null>(null);
  const [queue, setQueue] = useState<Video[]>([]);
  const [queueIndex, setQueueIndex] = useState(0);
  const [isShuffling, setIsShuffling] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  // Unshuffled copy so we can restore original order when turning shuffle off.
  const originalQueue = useRef<Video[]>([]);

  // Audio-only items play on the <audio> element throughout — iOS keeps an
  // <audio> playing with the screen off, whereas it suspends a <video> and the
  // handoff has to rescue it. Video items still use <video>, with GlobalPlayer's
  // lock-screen handoff covering the locked case.
  // These callbacks only pause / seek the active element; GlobalPlayer drives
  // src/seek/play through an effect keyed on current.id.
  const activeEl = useCallback(
    (): HTMLMediaElement | null =>
      current && itemKind(current) === "audio" ? audioRef.current : videoRef.current,
    [current],
  );

  const play = useCallback((video: Video) => {
    // We're inside a user gesture — unlock the audio element for the iOS
    // lock-screen handoff later (see primeAudioElement).
    if (itemKind(video) !== "audio") primeAudioElement(audioRef.current);
    // Same item already loaded → just re-open the fullscreen UI. The <video>
    // element keeps playing, so this is a seamless re-expand (no reload/seek).
    if (current?.id === video.id) {
      setIsModalOpen(true);
      return;
    }
    audioRef.current?.pause();
    originalQueue.current = [video];
    setQueue([video]);
    setQueueIndex(0);
    setCurrent(video);
    setIsModalOpen(true);
  }, [current]);

  const playQueue = useCallback((videos: Video[], startIndex = 0) => {
    if (!videos.length) return;
    originalQueue.current = videos;
    const ordered = isShuffling ? shuffled(videos) : videos;
    const target  = ordered[startIndex];
    const isAudio = itemKind(target) === "audio";
    // Audio items need no priming — the <audio> element is their real player,
    // and that play() happens inside this same gesture.
    if (!isAudio) primeAudioElement(audioRef.current);

    // Re-tapping the item that's already loaded: GlobalPlayer's drive effect is
    // keyed on current.id, so it won't re-run — resume the element by hand
    // instead of leaving the tap doing nothing.
    if (current?.id === target.id) {
      const el = isAudio ? audioRef.current : videoRef.current;
      if (el?.paused) el.play().catch(() => {});
      setQueue(ordered);
      setQueueIndex(startIndex);
      return;
    }

    audioRef.current?.pause();
    setQueue(ordered);
    setQueueIndex(startIndex);
    setCurrent(target);
    setIsModalOpen(false);
  }, [isShuffling, current]);

  const playShuffle = useCallback((videos: Video[]) => {
    if (!videos.length) return;
    originalQueue.current = videos;
    const sq = shuffled(videos);
    if (itemKind(sq[0]) !== "audio") primeAudioElement(audioRef.current);
    audioRef.current?.pause();
    setQueue(sq);
    setQueueIndex(0);
    setIsShuffling(true);
    setCurrent(sq[0]);
    setIsModalOpen(false);
  }, []);

  const next = useCallback(() => {
    setQueueIndex((idx) => {
      const nextIdx = idx + 1;
      if (nextIdx >= queue.length) {
        // End of queue — stop the active element and clear.
        const el = activeEl();
        if (el) { el.pause(); el.removeAttribute("src"); el.load(); }
        setCurrent(null);
        setIsModalOpen(false);
        return 0;
      }
      setCurrent(queue[nextIdx]);
      return nextIdx;
    });
  }, [queue, activeEl]);

  const previous = useCallback(() => {
    setQueueIndex((idx) => {
      const el = activeEl();
      // If more than 3s in, restart current track instead of going back.
      if (el && el.currentTime > 3) {
        el.currentTime = 0;
        if (el.paused) el.play().catch(() => {});
        return idx;
      }
      const prevIdx = Math.max(0, idx - 1);
      setCurrent(queue[prevIdx]);
      return prevIdx;
    });
  }, [queue, activeEl]);

  const toggleShuffle = useCallback(() => {
    setIsShuffling((on) => {
      const nextOn = !on;
      if (nextOn) {
        const rest = originalQueue.current.filter((v) => v.id !== current?.id);
        const newQueue = current ? [current, ...shuffled(rest)] : shuffled(originalQueue.current);
        setQueue(newQueue);
        setQueueIndex(0);
      } else {
        const orig = originalQueue.current;
        const idx = current ? orig.findIndex((v) => v.id === current.id) : 0;
        setQueue(orig);
        setQueueIndex(Math.max(0, idx));
      }
      return nextOn;
    });
  }, [current]);

  // Show the fullscreen video UI. The <video> element is already the player, so
  // this just reveals it — no element switch, no gap. Audio-only items have no
  // video to show, so there's nothing to expand.
  const openModal = useCallback(() => {
    if (current && itemKind(current) !== "audio") setIsModalOpen(true);
  }, [current]);

  // Minimize: just hide the fullscreen UI. The <video> element keeps playing.
  const hideModal = useCallback(() => {
    setIsModalOpen(false);
  }, []);

  const close = useCallback(() => {
    for (const el of [audioRef.current, videoRef.current]) {
      if (el) { el.pause(); el.removeAttribute("src"); el.load(); }
    }
    setCurrent(null);
    setQueue([]);
    setQueueIndex(0);
    setIsModalOpen(false);
  }, []);

  const restart = useCallback(() => {
    if (!current) return;
    clearPos(current.id);
    const el = activeEl();
    if (el) { el.currentTime = 0; el.play().catch(() => {}); }
  }, [current, activeEl]);

  const removeVideo = useCallback((videoId: string) => {
    const newQueue = queue.filter((v) => v.id !== videoId);
    originalQueue.current = originalQueue.current.filter((v) => v.id !== videoId);

    if (current?.id === videoId) {
      const el = activeEl();
      if (el) { el.pause(); el.removeAttribute("src"); el.load(); }
      if (newQueue.length === 0) {
        setCurrent(null);
        setQueue([]);
        setQueueIndex(0);
        setIsModalOpen(false);
      } else {
        const nextIdx = Math.min(queueIndex, newQueue.length - 1);
        setQueue(newQueue);
        setQueueIndex(nextIdx);
        setCurrent(newQueue[nextIdx]);
      }
    } else {
      const newIdx = newQueue.findIndex((v) => v.id === current?.id);
      setQueue(newQueue);
      if (newIdx >= 0) setQueueIndex(newIdx);
    }
  }, [queue, queueIndex, current, activeEl]);

  return (
    <PlayerCtx.Provider value={{
      current, queue, queueIndex, isShuffling, isModalOpen,
      play, playQueue, playShuffle, next, previous, toggleShuffle,
      openModal, hideModal, close, restart, removeVideo, audioRef, videoRef,
    }}>
      {children}
    </PlayerCtx.Provider>
  );
}
