import { useState } from "react";
import { Download } from "lucide-react";
import type { Video } from "@/lib/api";
import { Lightbox } from "./Lightbox";
import { formatBytes } from "@/lib/utils";

export function ImageView({ item }: { item: Video }) {
  const [zoomed, setZoomed] = useState(false);
  const src = `/stream/${item.id}/file`;

  return (
    <div className="space-y-4">
      <img
        src={src}
        alt={item.title ?? item.file_name ?? ""}
        className="max-w-full mx-auto rounded-xl cursor-zoom-in"
        onClick={() => setZoomed(true)}
      />
      <div className="flex items-center justify-between gap-3 text-xs" style={{ color: "var(--reader-muted)" }}>
        <span>{[item.file_name, formatBytes(item.file_size_bytes)].filter(Boolean).join(" · ")}</span>
        <a
          href={`${src}?download=1`}
          download
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border"
          style={{ borderColor: "var(--reader-rule)" }}
        >
          <Download size={12} /> Download
        </a>
      </div>
      {zoomed && (
        <Lightbox src={src} alt={item.title ?? ""} onClose={() => setZoomed(false)} />
      )}
    </div>
  );
}
