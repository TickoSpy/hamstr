import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { tagApi } from "@/lib/api";

export function useAllTags({ custom = false }: { custom?: boolean } = {}) {
  return useQuery({
    queryKey: ["tags", { custom }],
    queryFn: () => tagApi.listAll(custom),
    staleTime: 30_000,
  });
}

export function useAddTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ videoId, name }: { videoId: string; name: string }) =>
      tagApi.add(videoId, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["videos"] });
      qc.invalidateQueries({ queryKey: ["tags"] });
    },
  });
}

export function useRemoveTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ videoId, name }: { videoId: string; name: string }) =>
      tagApi.remove(videoId, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["videos"] });
      qc.invalidateQueries({ queryKey: ["tags"] });
    },
  });
}
