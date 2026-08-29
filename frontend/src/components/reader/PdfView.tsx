import { ExternalLink, Download, FileText } from "lucide-react";
import type { Video } from "@/lib/api";
import { isIOS } from "@/lib/platform";

export function PdfView({ item }: { item: Video }) {
  const src = `/stream/${item.id}/file`;

  const actions = (
    <div className="flex items-center gap-2 flex-wrap">
      <a
        href={src}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium"
      >
        <ExternalLink size={14} /> Open PDF
      </a>
      <a
        href={`${src}?download=1`}
        download
        className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm"
        style={{ borderColor: "var(--reader-rule)", color: "var(--reader-muted)" }}
      >
        <Download size={14} /> Download
      </a>
    </div>
  );

  // iOS Safari does not render PDFs reliably inside an iframe — it shows a blank
  // frame or only the first page. Offer the native viewer there instead.
  if (isIOS) {
    return (
      <div className="space-y-4">
        <div
          className="flex flex-col items-center gap-3 py-12 rounded-xl border"
          style={{ borderColor: "var(--reader-rule)" }}
        >
          <FileText size={40} style={{ color: "var(--reader-muted)" }} />
          <p className="text-sm" style={{ color: "var(--reader-muted)" }}>
            iOS can't display PDFs inline — open it in a new tab.
          </p>
        </div>
        {actions}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <iframe
        src={`${src}#view=FitH`}
        title={item.title ?? "PDF"}
        className="w-full rounded-xl border bg-white"
        style={{ height: "calc(100vh - 12rem)", borderColor: "var(--reader-rule)" }}
      />
      {actions}
    </div>
  );
}
