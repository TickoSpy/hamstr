import { http } from "./client";

export type ItemKind =
  | "video"
  | "audio"
  | "article"
  | "document"
  | "image"
  | "file";

export type IngestMode = "auto" | "video" | "audio" | "article" | "file";

export interface Video {
  id: string;
  url: string;
  title: string | null;
  channel: string | null;
  duration_seconds: number | null;
  file_size_bytes: number | null;
  thumbnail_path: string | null;
  video_path: string | null;
  audio_mp3_path: string | null;
  audio_ogg_path: string | null;
  status: "pending" | "downloading" | "processing" | "completed" | "error";
  progress: number;
  error_message: string | null;
  codec: string | null;
  audio_only: boolean;
  created_at: string;
  updated_at: string;
  tags: { id: number; name: string }[];

  // Archive fields — present on every item, only meaningful for some kinds.
  kind: ItemKind;
  file_path: string | null;
  mime_type: string | null;
  file_name: string | null;
  source_domain: string | null;
  byline: string | null;
  published_at: string | null;
  word_count: number | null;
  excerpt: string | null;
  article_html_path: string | null;
  raw_html_path: string | null;
  capture_source: string | null;
  capture_url: string | null;
  paywalled: boolean;
  extra: Record<string, unknown> | null;
}

/** The table is still called `videos`, but it holds every archived kind now. */
export type Item = Video;

export interface VideoListResponse {
  items: Video[];
  total: number;
}

export interface ListVideosParams {
  status?: string;
  kind?: string;
  tag?: string;
  q?: string;
  sort?: string;
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface TranscodeJob {
  id: string;
  state: "queued" | "running";
  title: string | null;
  channel: string | null;
  thumbnail_path: string | null;
  kind: ItemKind | null;
}

export interface SubmitResponse {
  submitted: { id: string; url: string; status: string }[];
  skipped:   { id: string; url: string; status: string }[];
}

export const videoApi = {
  submit:       (urls: string[], audioOnly = false, mode: IngestMode = "auto") =>
    http.post<SubmitResponse>("/videos", { urls, audio_only: audioOnly, mode }).then(r => r.data),

  list:         (params?: ListVideosParams) =>
    http.get<VideoListResponse>("/videos", { params }).then(r => r.data),

  get:          (id: string) =>
    http.get<Video>(`/videos/${id}`).then(r => r.data),

  delete:       (id: string) =>
    http.delete(`/videos/${id}`).then(r => r.data),

  clearQueue:   () =>
    http.delete<{ deleted: number }>("/videos/queue").then(r => r.data),

  retry:        (id: string) =>
    http.post<Video>(`/videos/${id}/retry`).then(r => r.data),

  transcode:    (id: string) =>
    http.post<{ status: string }>(`/videos/${id}/transcode`).then(r => r.data),

  transcodes:   () =>
    http.get<TranscodeJob[]>("/videos/transcodes").then(r => r.data),

  fixAllCodecs: () =>
    http.post<{ status: string; count: number }>("/videos/fix-all-codecs").then(r => r.data),

  retagAll:     () =>
    http.post<{ status: string; count: number }>("/videos/retag-all").then(r => r.data),

  kindCounts:   () =>
    http.get<Record<string, number>>("/videos/kinds").then(r => r.data),
};
