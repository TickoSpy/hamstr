import { useState } from "react";
import { Lightbox } from "./Lightbox";

/**
 * Renders the archived article body.
 *
 * The HTML is injected directly rather than sandboxed in an iframe so it can
 * share the reader's typography, measure its own height, and hand clicks to the
 * lightbox. That is safe because the bytes on disk are literally the output of
 * the server-side nh3 sanitizer (see services/ingest/sanitize.py) — no scripts,
 * no event handlers, no external URLs — and /stream serves them under a strict
 * CSP as defence in depth.
 */
export function ReaderView({ html }: { html: string }) {
  const [zoomed, setZoomed] = useState<{ src: string; alt: string } | null>(null);

  return (
    <>
      <div
        className="reader-content"
        // Delegated: the injected markup is never hydrated, so one listener on
        // the container is the only way to make its images interactive.
        onClick={(e) => {
          const target = e.target;
          if (target instanceof HTMLImageElement && target.src) {
            setZoomed({ src: target.src, alt: target.alt });
          }
        }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
      {zoomed && (
        <Lightbox src={zoomed.src} alt={zoomed.alt} onClose={() => setZoomed(null)} />
      )}
    </>
  );
}
