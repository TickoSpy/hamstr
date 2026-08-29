import { http } from "./client";

export const tagApi = {
  // custom: drop the automatic category/format tags (video, mp4, pdf, …), which
  // only restate the kind filter the library already shows as facets.
  listAll: (custom = false) =>
    http.get<string[]>("/tags", custom ? { params: { custom: true } } : undefined)
      .then(r => r.data),

  add: (videoId: string, name: string) =>
    http.post<string[]>(`/videos/${videoId}/tags`, { name }).then(r => r.data),

  remove: (videoId: string, name: string) =>
    http.delete(`/videos/${videoId}/tags/${name}`).then(r => r.data),
};
