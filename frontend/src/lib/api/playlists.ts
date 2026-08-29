import { http } from "./client";
import type { Video } from "./videos";

export interface PlaylistItem {
  id: number;
  video_id: string;
  position: number;
  video: Video;
}

export interface Playlist {
  id: number;
  name: string;
  created_at: string;
  items: PlaylistItem[];
}

export interface PlaylistSummary {
  id: number;
  name: string;
  created_at: string;
  item_count: number;
}

export const playlistApi = {
  list: () =>
    http.get<PlaylistSummary[]>("/playlists").then(r => r.data),

  create: (name: string) =>
    http.post<PlaylistSummary>("/playlists", { name }).then(r => r.data),

  get: (id: number) =>
    http.get<Playlist>(`/playlists/${id}`).then(r => r.data),

  delete: (id: number) =>
    http.delete(`/playlists/${id}`).then(r => r.data),

  rename: (id: number, name: string) =>
    http.patch<PlaylistSummary>(`/playlists/${id}`, { name }).then(r => r.data),

  addItem: (playlistId: number, videoId: string) =>
    http.post<Playlist>(`/playlists/${playlistId}/items`, { video_id: videoId }).then(r => r.data),

  removeItem: (playlistId: number, videoId: string) =>
    http.delete(`/playlists/${playlistId}/items/${videoId}`).then(r => r.data),
};
