import { ExternalLink, Archive, Lock } from "lucide-react";
import type { Video } from "@/lib/api";
import { readingMinutes } from "@/lib/kinds";

function formatPublished(value: string | null): string | null {
  if (!value) return null;
  // Extracted dates are frequently partial ("2019", "2019-04") — show what we have.
  const m = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?/.exec(value);
  if (!m) return value;
  const [, y, mo, d] = m;
  if (!mo) return y;
  const date = new Date(Number(y), Number(mo) - 1, d ? Number(d) : 1);
  if (Number.isNaN(date.getTime())) return value;
  return d
    ? date.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })
    : date.toLocaleDateString(undefined, { year: "numeric", month: "long" });
}

export function ReaderHeader({ item }: { item: Video }) {
  const minutes = readingMinutes(item.word_count);
  const published = formatPublished(item.published_at);

  const meta = [
    item.source_domain ?? item.channel,
    item.byline,
    published,
    minutes ? `${minutes} min read` : null,
  ].filter(Boolean) as string[];

  return (
    <header className="mb-8">
      <h1
        className="font-serif text-3xl sm:text-4xl leading-tight font-semibold"
        style={{ color: "var(--reader-fg)" }}
      >
        {item.title ?? item.url}
      </h1>

      {meta.length > 0 && (
        <p className="mt-3 text-sm" style={{ color: "var(--reader-muted)" }}>
          {meta.join(" · ")}
        </p>
      )}

      <div className="mt-4 flex items-center gap-2 flex-wrap">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-colors"
          style={{ borderColor: "var(--reader-rule)", color: "var(--reader-muted)" }}
        >
          <ExternalLink size={12} /> Open original
        </a>

        {item.capture_source && item.capture_source !== "direct" && (
          <span
            className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border"
            style={{ borderColor: "var(--reader-rule)", color: "var(--reader-muted)" }}
            title={item.capture_url ?? undefined}
          >
            <Archive size={12} /> via {item.capture_source}
          </span>
        )}

        {item.paywalled && (
          <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-amber-500/15 text-amber-500 border border-amber-500/30">
            <Lock size={12} /> paywalled
          </span>
        )}
      </div>

      <hr className="mt-6" style={{ borderColor: "var(--reader-rule)" }} />
    </header>
  );
}
