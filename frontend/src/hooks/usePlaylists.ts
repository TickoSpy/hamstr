import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { playlistApi } from "@/lib/api";
export type { PlaylistSummary, Playlist } from "@/lib/api";

export function usePlaylists() {
  return useQuery({
    queryKey: ["playlists"],
    queryFn: playlistApi.list,
    staleTime: 10_000,
  });
}

export function usePlaylist(id: number | null) {
  return useQuery({
    queryKey: ["playlist", id],
    queryFn: () => playlistApi.get(id!),
    enabled: id !== null,
  });
}

export function useCreatePlaylist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => playlistApi.create(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playlists"] }),
  });
}

export function useDeletePlaylist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => playlistApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playlists"] }),
  });
}

export function useRenamePlaylist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => playlistApi.rename(id, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["playlists"] }),
  });
}

export function useAddToPlaylist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ playlistId, videoId }: { playlistId: number; videoId: string }) =>
      playlistApi.addItem(playlistId, videoId),
    onSuccess: (_, { playlistId }) => {
      qc.invalidateQueries({ queryKey: ["playlists"] });
      qc.invalidateQueries({ queryKey: ["playlist", playlistId] });
    },
  });
}

export function useRemoveFromPlaylist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ playlistId, videoId }: { playlistId: number; videoId: string }) =>
      playlistApi.removeItem(playlistId, videoId),
    onSuccess: (_, { playlistId }) => {
      qc.invalidateQueries({ queryKey: ["playlists"] });
      qc.invalidateQueries({ queryKey: ["playlist", playlistId] });
    },
  });
}
