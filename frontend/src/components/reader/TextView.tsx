import type { Video } from "@/lib/api";
import { useTextFile } from "@/hooks/useArticleHtml";

export function TextView({ item }: { item: Video }) {
  const { data, isLoading, error } = useTextFile(item.id);

  if (isLoading) {
    return (
      <p className="text-sm" style={{ color: "var(--reader-muted)" }}>
        Loading…
      </p>
    );
  }
  if (error || data === undefined) {
    return (
      <p className="text-sm text-red-400">
        Could not load this file. <a href={`/stream/${item.id}/file?download=1`} className="underline">Download it instead</a>.
      </p>
    );
  }

  return (
    <pre
      className="reader-content whitespace-pre-wrap break-words"
      style={{ fontFamily: "inherit" }}
    >
      {data}
    </pre>
  );
}
