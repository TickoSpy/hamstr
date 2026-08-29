import { useQuery } from "@tanstack/react-query";

/**
 * The sanitized reader HTML for an archived page.
 *
 * Fetched as text from /stream/{id}/article rather than through the JSON API so
 * the service worker's existing /stream/* interception caches it for offline
 * reading with no changes.
 */
export function useArticleHtml(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["article-html", id],
    enabled: !!id && enabled,
    staleTime: Infinity, // an archived page never changes
    queryFn: async () => {
      const res = await fetch(`/stream/${id}/article`);
      if (!res.ok) throw new Error(`Failed to load article (${res.status})`);
      return res.text();
    },
  });
}

/** Plain-text content of a downloaded .txt/.md item. */
export function useTextFile(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["text-file", id],
    enabled: !!id && enabled,
    staleTime: Infinity,
    queryFn: async () => {
      const res = await fetch(`/stream/${id}/file`);
      if (!res.ok) throw new Error(`Failed to load file (${res.status})`);
      return res.text();
    },
  });
}
