import { useState } from "react";
import { Plus, Loader2, Music, Globe } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { extractUrls } from "@/lib/utils";
import { videoApi, type IngestMode } from "@/lib/api";

const BATCH_SIZE = 10;

type Summary = { added: number; skipped: number; mode: IngestMode };

export function UrlInput() {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number } | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const qc = useQueryClient();

  const urlCount = extractUrls(text).length;

  const handleSubmit = async (mode: IngestMode = "auto") => {
    setError(null);
    setSummary(null);
    const urls = extractUrls(text);
    if (!urls.length) {
      setError("No valid URLs found.");
      return;
    }

    setSubmitting(true);
    setBatchProgress({ done: 0, total: urls.length });

    let totalAdded = 0;
    let totalSkipped = 0;

    for (let i = 0; i < urls.length; i += BATCH_SIZE) {
      const batch = urls.slice(i, i + BATCH_SIZE);
      try {
        const result = await videoApi.submit(batch, mode === "audio", mode);
        totalAdded += result.submitted.length;
        totalSkipped += result.skipped.length;
      } catch {
        totalSkipped += batch.length;
      }
      setBatchProgress({ done: Math.min(i + BATCH_SIZE, urls.length), total: urls.length });
      qc.invalidateQueries({ queryKey: ["videos"] });
    }

    setSubmitting(false);
    setBatchProgress(null);
    setSummary({ added: totalAdded, skipped: totalSkipped, mode });
    if (totalAdded > 0) setText("");
  };

  return (
    <div className="space-y-3">
      <div className="relative">
        <textarea
          className="w-full h-28 bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-red-500 resize-none"
          placeholder="Paste any links — videos, articles, PDFs, images…"
          value={text}
          onChange={(e) => { setText(e.target.value); setSummary(null); }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleSubmit("auto");
          }}
          disabled={submitting}
        />
        {text.length > 0 && urlCount > 0 && !submitting && (
          <span className="absolute bottom-2 right-3 text-xs text-gray-500">
            {urlCount} link{urlCount !== 1 ? "s" : ""} found
          </span>
        )}
      </div>

      {error && <p className="text-red-400 text-xs">{error}</p>}

      {batchProgress && (
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-gray-400">
            <span>Adding {batchProgress.done}/{batchProgress.total}…</span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-1">
            <div
              className="bg-red-500 h-1 rounded-full transition-all duration-200"
              style={{ width: `${(batchProgress.done / batchProgress.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {summary && !submitting && (
        <p className="text-xs text-gray-400">
          <span className="text-green-400">
            {summary.added} added
            {summary.mode === "audio" ? " (audio only)" : summary.mode === "article" ? " (as pages)" : ""}
          </span>
          {summary.skipped > 0 && (
            <span className="text-gray-500"> · {summary.skipped} already in queue</span>
          )}
        </p>
      )}

      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => handleSubmit("auto")}
          disabled={submitting}
          className="flex items-center gap-2 px-5 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          {submitting ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
          Add to Archive
        </button>
        <button
          onClick={() => handleSubmit("audio")}
          disabled={submitting}
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 rounded-lg text-sm font-medium text-gray-300 transition-colors"
        >
          <Music size={15} />
          Audio Only
        </button>
        <button
          onClick={() => handleSubmit("article")}
          disabled={submitting}
          title="Save the page itself in reader view, even if it holds an embedded video"
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 rounded-lg text-sm font-medium text-gray-300 transition-colors"
        >
          <Globe size={15} />
          Archive Page
        </button>
      </div>
    </div>
  );
}
