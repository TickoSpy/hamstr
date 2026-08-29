import { useCallback, useEffect, useRef, type RefObject } from "react";
import type { Video } from "@/lib/api";
import { needsBackgroundAudioHandoff } from "@/lib/platform";

// How long a pause and a blur may be apart and still count as one lock event.
const LOCK_WINDOW_MS = 2500;

interface Options {
  current: Video | null;
  videoRef: RefObject<HTMLVideoElement | null>;
  audioRef: RefObject<HTMLAudioElement | null>;
  /** The element that should currently own the OS media controls. */
  activeMediaRef: RefObject<HTMLMediaElement | null>;
  videoSrc: string | null;
  bgAudioSrc: string | null;
  isAudioItem: boolean;
}

export interface LockScreenHandoff {
  /** True while the <audio> element is standing in for the <video>. */
  handedOff: RefObject<boolean>;
  /** Wire to the <video>'s onPlaying. */
  onVideoPlaying: () => void;
  /** Wire to the <video>'s onPause. */
  onVideoPause: () => void;
  /**
   * The Media Session "play" action, for the case where the screen is off and
   * the video cannot be started. Returns true when it took over; false means
   * the caller should just play the element itself.
   */
  resumeInBackground: (el: HTMLMediaElement) => boolean;
}

/**
 * The iOS/Android lock-screen handoff.
 *
 * A <video> can't keep playing with the screen off, so hand its audio to the
 * <audio> element when the page hides, and hand back when it's visible again.
 *
 * This is mobile-only, and deliberately so: a desktop browser keeps a hidden
 * tab's <video> playing, so there is nothing to rescue there — and the handoff
 * itself is expensive (it drops the video's source and re-buffers it on the way
 * back), which turned every alt-tab into a visible stutter. On a desktop none
 * of the listeners below are ever registered.
 */
export function useLockScreenHandoff({
  current,
  videoRef,
  audioRef,
  activeMediaRef,
  videoSrc,
  bgAudioSrc,
  isAudioItem,
}: Options): LockScreenHandoff {
  const enabled = needsBackgroundAudioHandoff;

  const handedOff = useRef(false);
  // Playback intent, so the handoff can tell "iOS auto-paused the video as the
  // screen locked" (hand off to audio) from "the user paused it" (stay paused).
  // In fullscreen iOS pauses the <video> *before* visibilitychange.
  const videoPlaying = useRef(false);
  const videoPausedAt = useRef(0);
  // When the window last lost focus — on iOS the blur around the lock moment is
  // the only signal that still runs before Safari suspends the page.
  const blurredAt = useRef(0);

  // Reset per-track state when the current item changes.
  useEffect(() => {
    handedOff.current = false;
  }, [current?.id]);

  const onVideoPlaying = useCallback(() => {
    videoPlaying.current = true;
  }, []);

  const onVideoPause = useCallback(() => {
    videoPlaying.current = false;
    videoPausedAt.current = Date.now();
  }, []);

  // iOS refuses to start a <video> while the screen is off, which is why the
  // lock-screen Pause worked but Play did nothing: the handler was aimed at an
  // element the OS wouldn't let us resume. Move to the <audio> element first.
  const resumeInBackground = useCallback(
    (el: HTMLMediaElement): boolean => {
      const a = audioRef.current;
      const v = videoRef.current;
      if (!enabled || !document.hidden || el !== v || !a || !bgAudioSrc) return false;

      const at = el.currentTime;
      if (!a.src.endsWith(bgAudioSrc)) a.src = bgAudioSrc;
      const start = () => {
        // Stale metadata callback — the handback already put the video in charge.
        if (activeMediaRef.current !== a) return;
        try { a.currentTime = at; } catch { /* not seekable yet */ }
        a.play().catch(() => {});
      };
      // Same eviction as the visibility handoff: only one element may exist
      // for the media session while the screen is off.
      if (v) { v.removeAttribute("src"); v.load(); }
      activeMediaRef.current = a;
      handedOff.current = true;
      if (a.readyState >= 1) start();
      else a.addEventListener("loadedmetadata", start, { once: true });
      return true;
    },
    [enabled, audioRef, videoRef, activeMediaRef, bgAudioSrc],
  );

  useEffect(() => {
    if (!enabled) return;

    const handOff = () => {
      const v = videoRef.current;
      const a = audioRef.current;
      if (!v || !a || !current || !bgAudioSrc) return;
      if (handedOff.current) return;
      const t = v.currentTime;
      v.pause();
      // Evict the video from media-session consideration entirely: a paused
      // <video> that still holds a source stays WebKit's "now playing"
      // element, so the lock screen shows a dead Play button for it while
      // the audio element is what's audible — and pausing that dead session
      // hands the lock-screen controls to another app. With the source
      // dropped, the audio element is the only media element and owns the
      // session. The handback below reloads the video (the src-mismatch
      // path), keeping the audio sounding until the video has re-buffered.
      v.removeAttribute("src");
      v.load();
      handedOff.current = true;
      activeMediaRef.current = a;
      // The <audio> element is preloaded at bgAudioSrc, so just sync + play.
      // Guard: if the page became visible again before the metadata arrived,
      // the handback already ran — a stale start here would leave the audio
      // playing at the old handoff position underneath the live video.
      const startAudio = () => {
        if (!handedOff.current) return;
        try { a.currentTime = t; } catch { /* not seekable yet */ }
        a.play().catch(() => {});
      };
      if (a.src.endsWith(bgAudioSrc) && a.readyState >= 1) startAudio();
      else {
        if (!a.src.endsWith(bgAudioSrc)) a.src = bgAudioSrc;
        a.addEventListener("loadedmetadata", startAudio, { once: true });
        a.play().catch(() => {});
      }
    };

    const handBack = () => {
      const v = videoRef.current;
      const a = audioRef.current;
      if (!v || !a || !current || !bgAudioSrc) return;
      if (!handedOff.current) return;
      // Whether sound is still wanted, read now rather than in swapToVideo:
      // that can run a rebuffer later, by which point the audio has been
      // paused as part of the swap. Pausing from the lock screen or media
      // keys while handed off therefore stays paused on return.
      const wantsSound = !a.paused;
      handedOff.current = false;
      // Keep the audio playing (sound stays continuous) while the video seeks
      // and re-buffers to the live position; swap sound to the video only once
      // it's actually ready, so there's no silent gap during the catch-up.
      const swapToVideo = () => {
        // Stale canplay from an interrupted handback: the screen was locked
        // again in the meantime — leave the audio in charge.
        if (handedOff.current) return;
        if (Math.abs(v.currentTime - a.currentTime) > 0.3) v.currentTime = a.currentTime;
        activeMediaRef.current = v;
        if (wantsSound) v.play().catch(() => {});
        a.pause();
      };
      if (videoSrc && !v.src.endsWith(videoSrc)) {
        // The handoff dropped the video's source (or the queue advanced while
        // locked). Reload the current track, seek it live, then swap.
        v.src = videoSrc;
        v.addEventListener("loadedmetadata", () => { v.currentTime = a.currentTime; }, { once: true });
        v.addEventListener("canplay", swapToVideo, { once: true });
      } else {
        v.currentTime = a.currentTime;
        if (v.readyState >= 3) swapToVideo();
        else v.addEventListener("canplay", swapToVideo, { once: true });
      }
    };

    const onVisibility = () => {
      // Audio-only items are already on the <audio> element; it plays through a
      // screen lock by itself and must not be interrupted.
      if (isAudioItem) return;
      if (document.hidden) {
        // Hand off if playback was live — or was auto-paused by the OS as the
        // screen locked shortly before. A deliberate user pause stays put.
        const rescuedFromLock = Date.now() - videoPausedAt.current < LOCK_WINDOW_MS;
        if (videoPlaying.current || rescuedFromLock) handOff();
      } else {
        handBack();
      }
    };

    // Fullscreen lock needs its own triggers. When iOS auto-pauses the
    // fullscreen video at lock, no audio is left playing — so Safari suspends
    // the page right away and only delivers visibilitychange at unlock, long
    // after the handoff could have helped. The events that DO still run are
    // the video's pause and the window blur that surround the lock moment
    // (in either order). Either one alone is ambiguous — a user pause, a
    // notification-shade peek — but pause + blur within a short window means
    // the system took the video down, so hand off while JS is still alive.
    const v = videoRef.current;
    const onPause = () => {
      if (isAudioItem || handedOff.current) return;
      if (document.hidden || Date.now() - blurredAt.current < LOCK_WINDOW_MS) handOff();
    };
    const onBlur = () => {
      blurredAt.current = Date.now();
      const vid = videoRef.current;
      if (isAudioItem || handedOff.current) return;
      if (vid && vid.paused && Date.now() - videoPausedAt.current < LOCK_WINDOW_MS) handOff();
    };
    const onFocus = () => {
      blurredAt.current = 0;
      if (!document.hidden) handBack();
    };
    v?.addEventListener("pause", onPause);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      v?.removeEventListener("pause", onPause);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [enabled, current?.id, current, videoRef, audioRef, activeMediaRef, videoSrc, bgAudioSrc, isAudioItem]);

  return { handedOff, onVideoPlaying, onVideoPause, resumeInBackground };
}
