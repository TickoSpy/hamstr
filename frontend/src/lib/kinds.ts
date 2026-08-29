import {
  Film,
  FileText,
  Image as ImageIcon,
  Music,
  File,
  Globe,
  type LucideIcon,
} from "lucide-react";
import type { ItemKind, Video } from "@/lib/api";

export const KIND_LABEL: Record<ItemKind, string> = {
  video: "Video",
  audio: "Audio",
  article: "Article",
  document: "Document",
  image: "Image",
  file: "File",
};

export const KIND_ICON: Record<ItemKind, LucideIcon> = {
  video: Film,
  audio: Music,
  article: Globe,
  document: FileText,
  image: ImageIcon,
  file: File,
};

/** Tailwind classes for the icon tile shown when an item has no thumbnail. */
export const KIND_TINT: Record<ItemKind, string> = {
  video: "text-gray-500",
  audio: "text-purple-400",
  article: "text-sky-400",
  document: "text-amber-400",
  image: "text-emerald-400",
  file: "text-gray-400",
};

export function itemKind(v: Pick<Video, "kind" | "audio_only">): ItemKind {
  return v.kind ?? (v.audio_only ? "audio" : "video");
}

/** Only these can go through GlobalPlayer's <video>/<audio> elements. */
export function isPlayable(v: Pick<Video, "kind" | "audio_only">): boolean {
  const k = itemKind(v);
  return k === "video" || k === "audio";
}

/** Readable in the in-app reader rather than played. */
export function isReadable(v: Pick<Video, "kind" | "audio_only">): boolean {
  const k = itemKind(v);
  return k === "article" || k === "document" || k === "image";
}

export type PrimaryAction =
  | { type: "play" }
  | { type: "read"; to: string }
  | { type: "open"; href: string };

/** What clicking an item's card should do. */
export function primaryAction(v: Video): PrimaryAction {
  if (isPlayable(v)) return { type: "play" };
  if (isReadable(v)) return { type: "read", to: `/read/${v.id}` };
  return { type: "open", href: `/stream/${v.id}/file?download=1` };
}

/** Short uppercase label for the card chip: "PDF", "GIF", "ARTICLE". */
export function formatLabel(v: Video): string {
  const k = itemKind(v);
  if (k === "article") return "ARTICLE";
  if (v.file_name?.includes(".")) {
    return v.file_name.split(".").pop()!.toUpperCase().slice(0, 6);
  }
  const sub = v.mime_type?.split("/")[1];
  return (sub ?? KIND_LABEL[k]).toUpperCase().slice(0, 6);
}

/** Reading time in whole minutes, at ~238 wpm. */
export function readingMinutes(wordCount: number | null): number | null {
  if (!wordCount || wordCount <= 0) return null;
  return Math.max(1, Math.round(wordCount / 238));
}
