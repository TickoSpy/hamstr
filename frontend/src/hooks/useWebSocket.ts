import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { wsClient } from "@/lib/ws";
import type { Video } from "@/lib/api";

export function useWebSocket() {
  const queryClient = useQueryClient();

  useEffect(() => {
    const off = wsClient.on((event) => {
      // Update the specific video in any list/detail caches
      const patch = (prev: Video | undefined): Video | undefined => {
        if (!prev || prev.id !== event.video_id) return prev;
        if (event.type === "progress") {
          return { ...prev, progress: Math.max(prev.progress, event.progress), status: event.status as Video["status"] };
        }
        if (event.type === "completed") {
          return { ...prev, status: "completed", progress: 100 };
        }
        if (event.type === "error") {
          return { ...prev, status: "error", error_message: event.error };
        }
        if (event.type === "status_change") {
          return { ...prev, status: event.status as Video["status"] };
        }
        if (event.type === "transcoding") {
          return { ...prev, codec: "transcoding" };
        }
        if (event.type === "transcoded") {
          return { ...prev, codec: event.codec, file_size_bytes: event.file_size_bytes };
        }
        if (event.type === "transcode_error") {
          return { ...prev, codec: prev.codec === "transcoding" ? null : prev.codec };
        }
        return prev;
      };

      // Track whether this video exists in any cached list
      let seenInList = false;

      // Patch video lists
      queryClient.setQueriesData<{ items: Video[]; total: number }>(
        { queryKey: ["videos"] },
        (old) => {
          if (!old) return old;
          if (old.items.some((v) => v.id === event.video_id)) seenInList = true;
          return { ...old, items: old.items.map((v) => patch(v) ?? v) };
        }
      );

      // Patch individual video
      queryClient.setQueryData<Video>(
        ["video", event.video_id],
        (old) => patch(old) ?? old
      );

      // If the video isn't in any cached list it was submitted externally —
      // invalidate so the queue poll picks it up immediately.
      if (!seenInList || event.type === "completed" || event.type === "error") {
        queryClient.invalidateQueries({ queryKey: ["videos"] });
      }

      // Keep the Queue page's transcode job list in sync
      if (event.type.startsWith("transcod")) {
        queryClient.invalidateQueries({ queryKey: ["transcodes"] });
      }
    });

    return () => { off(); };
  }, [queryClient]);
}
