import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { videoApi, type ListVideosParams, type VideoListResponse } from "@/lib/api";
import { usePlayer } from "@/lib/playerContext";

export function useVideos(params?: ListVideosParams, options?: { refetchInterval?: number | false }) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ["videos", params],
    queryFn: async () => {
      const fresh = await videoApi.list(params);
      const cached = qc.getQueryData<VideoListResponse>(["videos", params]);
      if (!cached) return fresh;
      return {
        ...fresh,
        items: fresh.items.map((item) => {
          const prev = cached.items.find((c) => c.id === item.id);
          if (!prev) return item;
          // Never let a poll reset in-flight transcoding state
          if (prev.codec === "transcoding" && item.codec !== "h264") {
            return { ...item, codec: "transcoding" };
          }
          // Never let polled DB data move download progress backwards
          if (item.status === "downloading") {
            return { ...item, progress: Math.max(prev.progress, item.progress) };
          }
          return item;
        }),
      };
    },
    refetchInterval: options?.refetchInterval ?? 5000,
  });
}

export function useVideo(id: string) {
  return useQuery({
    queryKey: ["video", id],
    queryFn: () => videoApi.get(id),
    enabled: !!id,
  });
}

export function useSubmitUrls() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ urls, audioOnly }: { urls: string[]; audioOnly?: boolean }) =>
      videoApi.submit(urls, audioOnly),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["videos"] }),
  });
}

export function useDeleteVideo() {
  const qc = useQueryClient();
  const player = usePlayer();
  return useMutation({
    mutationFn: videoApi.delete,
    onSuccess: (_data, videoId) => {
      player.removeVideo(videoId);
      qc.invalidateQueries({ queryKey: ["videos"] });
      qc.invalidateQueries({ queryKey: ["tags"] });
    },
  });
}

export function useClearQueue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: videoApi.clearQueue,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["videos"] });
      qc.invalidateQueries({ queryKey: ["tags"] });
    },
  });
}

export function useRetryVideo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: videoApi.retry,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["videos"] }),
  });
}

export function useFixAllCodecs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: videoApi.fixAllCodecs,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["videos"] }),
  });
}

export function useTranscodeVideo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: videoApi.transcode,
    onSuccess: (_data, videoId) => {
      qc.setQueriesData<VideoListResponse>(
        { queryKey: ["videos"] },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map((v) =>
              v.id === videoId && v.codec !== "h264" ? { ...v, codec: "transcoding" } : v
            ),
          };
        }
      );
    },
  });
}

export function useTranscodes() {
  return useQuery({
    queryKey: ["transcodes"],
    queryFn: videoApi.transcodes,
    // Poll as a fallback; WS transcode events invalidate this immediately.
    refetchInterval: 5000,
  });
}

export function useRetagAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: videoApi.retagAll,
    onSuccess: () => {
      // Tagging runs in the background; give it a moment before refetching.
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["videos"] });
        qc.invalidateQueries({ queryKey: ["tags"] });
      }, 1500);
    },
  });
}
