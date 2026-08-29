import { useEffect, useRef, useState } from "react";
import { usePlayer } from "@/lib/playerContext";
import { needsBackgroundAudioHandoff } from "@/lib/platform";
import { useLockScreenHandoff } from "@/hooks/useLockScreenHandoff";
import { getPos, setPos, clearPos } from "@/lib/positions";
import { thumbnailUrl } from "@/lib/utils";
import { itemKind } from "@/lib/kinds";
import { MiniPlayer } from "./MiniPlayer";
import { VideoModal } from "./VideoModal";

export function codecSupported(codec: string | null | undefined): boolean {
  if (!codec || codec === "h264" || codec === "transcoding") return true;
  const el = document.createElement("video");
  if (codec === "av1") return el.canPlayType('video/mp4; codecs="av01"') !== "";
  if (codec === "hevc") {
    return (
      el.canPlayType('video/mp4; codecs="hvc1"') !== "" ||
      el.canPlayType('video/mp4; codecs="hev1"') !== ""
    );
  }
  return true; // unknown codec: try playing, rely on the error handler
}

export function GlobalPlayer() {
  const { current, isModalOpen, audioRef, videoRef, queue, next, previous } = usePlayer();
  const [videoError, setVideoError] = useState(false);

  // The element that should currently receive OS media controls. Normally the
  // <video> element (the sole on-screen player); the lock-screen handoff flips it
  // to the <audio> element while the screen is off (a <video> can't play then).
  const activeMediaRef = useRef<HTMLMediaElement | null>(null);
  const lastSave = useRef(0);

  // Audio-only items play on the <audio> element from the start. iOS keeps an
  // <audio> playing with the screen off but suspends a <video>, so routing them
  // through <video> meant every lock depended on useLockScreenHandoff rescuing
  // them — and when it didn't, playback simply stopped.
  // Keyed on kind, not audio_only: a .flac or .opus fetched by the file handler
  // is kind="audio" with audio_only=false, and would otherwise be sent to the
  // <video> element to request a /video stream that doesn't exist.
  const isAudioItem = !!current && itemKind(current) === "audio";
  const hasVideo = !!current && !isAudioItem;
  const codecOk = codecSupported(current?.codec);
  const showVideo = hasVideo && isModalOpen && !videoError && codecOk;

  // Source for the persistent <video> element — the single on-screen player for
  // both video items and audio-only items (a <video> plays audio fine).
  const videoSrc = current
    ? current.audio_only
      ? `/stream/${current.id}/audio/mp3`
      : `/stream/${current.id}/video`
    : null;
  // Source the <audio> element takes over with while the screen is off. Prefer
  // the lighter mp3 when we have one.
  const bgAudioSrc = current
    ? current.audio_mp3_path
      ? `/stream/${current.id}/audio/mp3`
      : current.file_path && isAudioItem
        // flac/opus/wav have no mp3 rendition; play the file itself.
        ? `/stream/${current.id}/file`
        : `/stream/${current.id}/video`
    : null;

  // Background/lock-screen playback is a mobile-only concern; on a desktop this
  // hook registers nothing at all.
  const { handedOff, onVideoPlaying, onVideoPause, resumeInBackground } =
    useLockScreenHandoff({
      current, videoRef, audioRef, activeMediaRef, videoSrc, bgAudioSrc, isAudioItem,
    });

  // Reset per-track state when the current item changes.
  useEffect(() => {
    setVideoError(false);
  }, [current?.id]);

  // Whichever element owns this item is the media-controls target.
  useEffect(() => {
    activeMediaRef.current = isAudioItem ? audioRef.current : videoRef.current;
  }, [current?.id, isAudioItem, videoRef, audioRef]);

  // ---- Drive playback when the track changes ----
  // The <video> element plays. The one exception is a phone with the screen off
  // or the browser backgrounded: a <video> can't play there, so the next queue
  // track starts on the <audio> element instead of going silent.
  useEffect(() => {
    const v = videoRef.current;
    const a = audioRef.current;
    if (!current) { v?.pause(); a?.pause(); return; }

    if (isAudioItem && a && bgAudioSrc) {
      v?.pause();
      // A leftover source from a previous video track would keep the idle
      // <video> in the running for media-session ownership — evict it.
      if (v?.getAttribute("src")) { v.removeAttribute("src"); v.load(); }
      if (!a.src.endsWith(bgAudioSrc)) a.src = bgAudioSrc;
      const pos = getPos(current.id);
      // Seeking before metadata arrives is ignored, so onLoadedMetadata repeats it.
      if (pos > 0 && a.readyState >= 1) { try { a.currentTime = pos; } catch { /* not seekable yet */ } }
      a.play().catch(() => {});
      activeMediaRef.current = a;
      return;
    }

    // Only where a hidden page can't run a <video> at all. A desktop browser
    // plays one fine in a background tab, so the queue advances on the <video>
    // there and nothing has to be swapped back later.
    if (needsBackgroundAudioHandoff && document.hidden && bgAudioSrc && a) {
      if (!a.src.endsWith(bgAudioSrc)) a.src = bgAudioSrc;
      const pos = getPos(current.id);
      if (pos > 0) a.currentTime = pos;
      a.play().catch(() => {});
      activeMediaRef.current = a;
      handedOff.current = true;
      v?.pause();
      if (v?.getAttribute("src")) { v.removeAttribute("src"); v.load(); }
      return;
    }

    if (!v || !videoSrc) return;
    if (!current.audio_only && !codecSupported(current.codec)) { setVideoError(true); return; }
    a?.pause(); // keep the lock-screen shadow element idle while visible
    if (!v.src.endsWith(videoSrc)) {
      v.src = videoSrc; // initial seek happens in onLoadedMetadata
    }
    v.play().catch(() => {});
    activeMediaRef.current = v;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id]);

  // ---- Keep the lock-screen <audio> element preloaded at the current source ----
  // so the handoff can start it instantly instead of kicking off a fresh network
  // load in the background (which iOS may refuse — the cause of silent locks).
  useEffect(() => {
    const a = audioRef.current;
    if (!a || !bgAudioSrc) return;
    if (!a.src.endsWith(bgAudioSrc)) {
      a.preload = "auto";
      a.src = bgAudioSrc;
      a.load();
    }
  }, [current?.id, bgAudioSrc, audioRef]);

  // ---- Persistent <video> element event handlers ----
  const handleVideoLoadedMetadata = () => {
    const v = videoRef.current;
    if (!v || !current) return;
    const pos = getPos(current.id);
    if (pos > 0) v.currentTime = pos;
  };

  const handleVideoTimeUpdate = () => {
    const v = videoRef.current;
    if (!v || !current) return;
    const now = Date.now();
    if (now - lastSave.current > 4000 && v.currentTime > 2) {
      setPos(current.id, v.currentTime);
      lastSave.current = now;
    }
  };

  const handleVideoEnded = () => {
    if (current) clearPos(current.id);
    next();
  };

  const handleVideoError = () => {
    const v = videoRef.current;
    if (!v) return;
    // No source: the element was deliberately evicted for the lock-screen
    // handoff — not a playback failure.
    if (!v.getAttribute("src")) return;
    if (v.duration > 0 && v.currentTime >= v.duration - 2) { handleVideoEnded(); return; }
    setVideoError(true);
  };

  // ---- Audio element auto-advance (fires only while it's the one playing, i.e.
  //      during the lock-screen handoff) ----
  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onEnded = () => {
      if (current) clearPos(current.id);
      next();
    };
    a.addEventListener("ended", onEnded);
    return () => a.removeEventListener("ended", onEnded);
  }, [next, current, audioRef]);

  // ---- Single-player invariant ----
  // Exactly one element (activeMediaRef) may produce sound at any moment. Every
  // handoff path above sets activeMediaRef before calling play(), so anything
  // else that starts playing — a stale once-listener from an interrupted
  // handoff, a race between play() promises — is paused on the spot. This is
  // the backstop that makes "audio from one position under video from another"
  // structurally impossible.
  useEffect(() => {
    const els = [audioRef.current, videoRef.current].filter(
      Boolean
    ) as HTMLMediaElement[];
    const onPlaying = (e: Event) => {
      const el = e.target as HTMLMediaElement;
      if (activeMediaRef.current && el !== activeMediaRef.current) el.pause();
    };
    for (const el of els) el.addEventListener("playing", onPlaying);
    return () => {
      for (const el of els) el.removeEventListener("playing", onPlaying);
    };
  }, [audioRef, videoRef]);

  // ---- Save position every 5s while playing ----
  useEffect(() => {
    if (!current) return;
    const id = setInterval(() => {
      const el = activeMediaRef.current;
      if (el && !el.paused && el.currentTime > 2) {
        setPos(current.id, el.currentTime);
      }
    }, 5000);
    return () => clearInterval(id);
  }, [current?.id, current]);

  // ---- Media Session (OS lock-screen / notification controls) ----
  useEffect(() => {
    if (!current || !("mediaSession" in navigator)) return;
    const ms = navigator.mediaSession;
    const a = audioRef.current;
    const v = videoRef.current;
    const applyMetadata = () => {
      // Items with no thumbnail (archived pages, loose files) get no artwork at
      // all rather than a broken one — MediaMetadata accepts an empty list.
      const thumb = thumbnailUrl(current);
      const artwork = thumb
        ? [{
            src: thumb.startsWith("http") ? thumb : window.location.origin + thumb,
            sizes: "512x512",
            type: "image/jpeg",
          }]
        : [];
      ms.metadata = new MediaMetadata({
        title: current.title ?? "Unknown",
        artist: current.channel ?? "",
        artwork,
      });
    };
    applyMetadata();
    // Re-assert our metadata once the resource loads / playback starts, so embedded
    // ID3/cover-art metadata in the files can't override it on the lock screen.
    for (const el of [a, v]) {
      el?.addEventListener("loadedmetadata", applyMetadata);
      el?.addEventListener("playing", applyMetadata);
    }
    const media = () => activeMediaRef.current;

    // On a locked phone the target element may be one the OS won't let us
    // start; resumeInBackground moves to the <audio> element and reports that
    // it took over. Everywhere else this is a plain play().
    const resume = () => {
      const el = media();
      if (!el) return;
      if (resumeInBackground(el)) return;
      el.play().catch(() => {});
    };

    ms.setActionHandler("play", resume);
    ms.setActionHandler("pause", () => media()?.pause());
    ms.setActionHandler("nexttrack", next);
    ms.setActionHandler("previoustrack", previous);
    ms.setActionHandler("seekto", (d) => { const el = media(); if (el && d.seekTime != null) el.currentTime = d.seekTime; });
    ms.setActionHandler("seekbackward", (d) => { const el = media(); if (el) el.currentTime = Math.max(0, el.currentTime - (d.seekOffset ?? 10)); });
    ms.setActionHandler("seekforward", (d) => { const el = media(); if (el) el.currentTime = Math.min(el.duration, el.currentTime + (d.seekOffset ?? 10)); });
    return () => {
      for (const el of [a, v]) {
        el?.removeEventListener("loadedmetadata", applyMetadata);
        el?.removeEventListener("playing", applyMetadata);
      }
      ["play","pause","nexttrack","previoustrack","seekto","seekbackward","seekforward"].forEach(
        (a2) => ms.setActionHandler(a2 as MediaSessionAction, null)
      );
    };
  }, [current?.id, current, next, previous, audioRef, videoRef, resumeInBackground]);

  // ---- Sync Media Session playbackState + scrubber from whichever element plays ----
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    const els = [audioRef.current, videoRef.current].filter(Boolean) as HTMLMediaElement[];
    // Read from the active element rather than trusting whichever event fired
    // last: handing back to video runs v.play() then a.pause(), so the stale
    // "pause" would otherwise leave the lock screen showing a Play button while
    // sound was coming out.
    const sync = () => {
      const el = activeMediaRef.current;
      navigator.mediaSession.playbackState = el && !el.paused ? "playing" : "paused";
    };
    const onTime = (e: Event) => {
      const el = e.target as HTMLMediaElement;
      // Only the active element speaks for the session — and since WebKit can
      // re-evaluate the session from the paused <video> after the lock-screen
      // handoff (leaving the lock screen showing Play while audio runs),
      // re-assert the playback state on every tick, not just on play/pause.
      if (el !== activeMediaRef.current) return;
      sync();
      if (isFinite(el.duration) && el.duration > 0) {
        try {
          navigator.mediaSession.setPositionState({ duration: el.duration, playbackRate: el.playbackRate, position: el.currentTime });
        } catch { /* ignore */ }
      }
    };
    for (const el of els) {
      el.addEventListener("play", sync);
      el.addEventListener("playing", sync);
      el.addEventListener("pause", sync);
      el.addEventListener("timeupdate", onTime);
    }
    return () => {
      for (const el of els) {
        el.removeEventListener("play", sync);
        el.removeEventListener("playing", sync);
        el.removeEventListener("pause", sync);
        el.removeEventListener("timeupdate", onTime);
      }
    };
  }, [current?.id, audioRef, videoRef]);

  // ---- Save position on page unload ----
  useEffect(() => {
    const save = () => {
      const el = activeMediaRef.current;
      if (el && current && el.currentTime > 2) setPos(current.id, el.currentTime);
    };
    window.addEventListener("beforeunload", save);
    return () => window.removeEventListener("beforeunload", save);
  }, [current?.id, current]);

  return (
    <>
      {/* Off-screen background-audio element — takes over during the iOS
          lock-screen handoff only. x-webkit-airplay enables AirPlay. */}
      <audio
        ref={audioRef}
        {...{ "x-webkit-airplay": "allow" }}
        onLoadedMetadata={() => {
          const a2 = audioRef.current;
          if (!a2 || !current || !isAudioItem) return;
          const pos = getPos(current.id);
          if (pos > 0 && Math.abs(a2.currentTime - pos) > 1) a2.currentTime = pos;
        }}
      />

      {/* The single persistent player — plays every item (video or audio-only),
          fullscreen or minimized. Hidden (but still playing) when not fullscreen
          so nothing ever switches elements or interrupts playback. */}
      <video
        ref={videoRef}
        playsInline
        controls={showVideo}
        className={
          showVideo
            ? "fixed inset-0 z-40 w-full h-full bg-black object-contain"
            : "fixed bottom-0 left-0 w-px h-px opacity-0 pointer-events-none -z-10"
        }
        onLoadedMetadata={handleVideoLoadedMetadata}
        onPlaying={onVideoPlaying}
        onPause={onVideoPause}
        onTimeUpdate={handleVideoTimeUpdate}
        onEnded={handleVideoEnded}
        onError={handleVideoError}
      />

      {current && !(hasVideo && isModalOpen) && <MiniPlayer />}
      {current && hasVideo && isModalOpen && (
        <VideoModal video={current} hasError={videoError || !codecOk} codecOk={codecOk} />
      )}
    </>
  );
}
