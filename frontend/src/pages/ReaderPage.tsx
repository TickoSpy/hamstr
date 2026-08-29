import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Type, AlertTriangle } from "lucide-react";
import { useVideo } from "@/hooks/useVideos";
import { itemKind } from "@/lib/kinds";
import { useArticleHtml } from "@/hooks/useArticleHtml";
import { loadPrefs, savePrefs, SIZES, type ReaderPrefs } from "@/lib/reader/prefs";
import { getProgress, setProgress } from "@/lib/reader/progress";
import { ReaderHeader } from "@/components/reader/ReaderHeader";
import { ReaderView } from "@/components/reader/ReaderView";
import { ReaderControls } from "@/components/reader/ReaderControls";
import { PdfView } from "@/components/reader/PdfView";
import { TextView } from "@/components/reader/TextView";
import { ImageView } from "@/components/reader/ImageView";

function scrollFraction(): number {
  const max = document.documentElement.scrollHeight - window.innerHeight;
  return max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
}

export function ReaderPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: item, isLoading, error } = useVideo(id ?? "");

  const [prefs, setPrefs] = useState<ReaderPrefs>(loadPrefs);
  const [controlsOpen, setControlsOpen] = useState(false);
  // Written straight to the DOM rather than held in state: re-rendering the
  // whole reader on every animation frame of a scroll is what made images
  // flicker on iOS, since the sticky header repaints over them each time.
  const progressBar = useRef<HTMLDivElement>(null);
  const restored = useRef(false);

  const kind = item ? itemKind(item) : "article";
  const isArticle = kind === "article";
  const isPdf = item?.mime_type === "application/pdf";
  const isImage = kind === "image";
  const isPlainText = !isArticle && !isPdf && !isImage;

  const { data: html, isLoading: htmlLoading } = useArticleHtml(
    id,
    isArticle && !!item?.article_html_path,
  );

  const updatePrefs = useCallback((next: ReaderPrefs) => {
    setPrefs(next);
    savePrefs(next);
  }, []);

  // Reading progress: a 2px bar at the top, persisted per item so returning to a
  // long article lands where you left off (mirrors lib/positions.ts for playback).
  useEffect(() => {
    let frame = 0;
    let lastSaved = 0;
    let pending = 0;

    // Persisting on every frame meant a synchronous JSON.parse + stringify +
    // localStorage.setItem ~60x/second while scrolling, which blocks the main
    // thread hard enough to stall image decoding and make the page judder.
    const save = (fraction: number) => {
      if (!id || !restored.current) return;
      pending = fraction;
      const now = Date.now();
      if (now - lastSaved < 1000) return;
      lastSaved = now;
      setProgress(id, fraction);
    };

    const flush = () => {
      if (id && restored.current && pending) setProgress(id, pending);
    };

    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const fraction = scrollFraction();
        if (progressBar.current) {
          progressBar.current.style.width = `${fraction * 100}%`;
        }
        save(fraction);
      });
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    // Leaving mid-article must still record where you got to.
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", flush);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", flush);
      if (frame) cancelAnimationFrame(frame);
      flush();
    };
  }, [id]);

  // Restore the saved position once the content has actually laid out —
  // scrolling before that would land at the wrong place or be clamped to 0.
  useEffect(() => {
    if (!id || restored.current) return;
    if (isArticle && htmlLoading) return;
    if (!item) return;

    const saved = getProgress(id);
    const t = setTimeout(() => {
      if (saved > 0.02 && saved < 0.98) {
        const max = document.documentElement.scrollHeight - window.innerHeight;
        window.scrollTo({ top: max * saved, behavior: "auto" });
      }
      restored.current = true;
    }, 60);
    return () => clearTimeout(t);
  }, [id, item, isArticle, htmlLoading]);

  useEffect(() => {
    restored.current = false;
  }, [id]);

  if (isLoading) {
    return <div className="pt-24 text-center text-sm text-gray-500">Loading…</div>;
  }
  if (error || !item) {
    return (
      <div className="pt-24 text-center space-y-3">
        <p className="text-sm text-gray-400">This item could not be found.</p>
        <button onClick={() => navigate("/")} className="text-sm text-red-400 underline">
          Back to Library
        </button>
      </div>
    );
  }

  const readerUnavailable = isArticle && !item.article_html_path;

  return (
    <div data-reader-theme={prefs.theme} className="min-h-screen">
      {/* Backdrop rather than restyling <body>: animating or repainting body on
          iOS Safari drags the fixed MiniPlayer around (same bug LibraryPage
          works around for its sticky header). */}
      <div
        className="fixed inset-0 -z-10"
        style={{ background: "var(--reader-bg)" }}
      />

      <div className="fixed top-0 left-0 right-0 h-0.5 z-50 bg-transparent">
        <div ref={progressBar} className="h-full bg-red-500 transition-none" style={{ width: 0 }} />
      </div>

      {/* Opaque, not translucent: a backdrop-filter here forces iOS to re-sample
          the article beneath it on every scroll frame, which shows up as the
          images flickering as they pass under the header. */}
      <div className="sticky top-0 z-40" style={{ background: "var(--reader-bg)" }}>
        <div className="max-w-3xl mx-auto px-5 sm:px-6 h-14 flex items-center justify-between gap-3">
          <button
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1.5 text-sm"
            style={{ color: "var(--reader-muted)" }}
          >
            <ArrowLeft size={16} /> Back
          </button>

          <div className="relative">
            <button
              onClick={() => setControlsOpen((o) => !o)}
              className="p-2 rounded-lg"
              style={{ color: "var(--reader-muted)" }}
              aria-label="Reading options"
            >
              <Type size={18} />
            </button>
            {controlsOpen && (
              <ReaderControls
                prefs={prefs}
                onChange={updatePrefs}
                onClose={() => setControlsOpen(false)}
              />
            )}
          </div>
        </div>
      </div>

      <article
        className="mx-auto px-5 sm:px-6 pt-6 pb-24 mb-player"
        style={
          {
            maxWidth: `${prefs.width}ch`,
            "--reader-size": `${SIZES[prefs.size]}px`,
          } as React.CSSProperties
        }
      >
        <ReaderHeader item={item} />

        {readerUnavailable ? (
          <div className="space-y-4">
            <div className="flex items-start gap-2 text-sm p-3 rounded-lg bg-amber-500/10 text-amber-500 border border-amber-500/25">
              <AlertTriangle size={16} className="shrink-0 mt-0.5" />
              <span>
                Reader view unavailable for this page — showing the original saved
                copy instead.
              </span>
            </div>
            {/* Unsanitized bytes, so an empty sandbox (unique origin, no scripts,
                no forms, no top-level navigation) is mandatory here. */}
            <iframe
              sandbox=""
              src={`/stream/${item.id}/article?raw=1`}
              title={item.title ?? "Saved page"}
              className="w-full rounded-xl border bg-white"
              style={{ height: "calc(100vh - 14rem)", borderColor: "var(--reader-rule)" }}
            />
          </div>
        ) : isArticle ? (
          htmlLoading ? (
            <p className="text-sm" style={{ color: "var(--reader-muted)" }}>
              Loading…
            </p>
          ) : html ? (
            <ReaderView html={html} />
          ) : (
            <p className="text-sm text-red-400">Could not load the reader view.</p>
          )
        ) : isPdf ? (
          <PdfView item={item} />
        ) : isImage ? (
          <ImageView item={item} />
        ) : isPlainText ? (
          <TextView item={item} />
        ) : null}
      </article>
    </div>
  );
}
