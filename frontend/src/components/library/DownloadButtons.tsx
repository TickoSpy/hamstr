import type { Video } from "@/lib/api";
import { formatLabel, itemKind } from "@/lib/kinds";
import { isStandalone } from "@/lib/download";
import { useSaveFile } from "@/hooks/useSaveFile";

export function DownloadButtons({ video }: { video: Video }) {
  const { save, savingHref, error } = useSaveFile();
  // Falls back to the title when the item has no stored filename of its own.
  const nameFor = (ext: string) =>
    video.file_name ?? `${(video.title ?? video.id).replace(/[/\\?%*:|"<>]/g, "_")}.${ext}`;

  const btn = (href: string, label: string, ext: string) => (
    <a
      href={href}
      download
      onClick={(e) => {
        e.stopPropagation();
        // In a standalone PWA iOS would navigate this window to the file and
        // strand the user there — hand it to the share sheet instead.
        if (isStandalone()) {
          e.preventDefault();
          void save(href, nameFor(ext));
        }
      }}
      className="px-3 py-1 bg-gray-800 hover:bg-gray-700 rounded text-xs font-medium text-gray-300 transition-colors"
    >
      {savingHref === href ? "Saving…" : label}
    </a>
  );

  return (
    <div className="flex gap-2 flex-wrap">
      {video.video_path && btn(`/stream/${video.id}/video`, "MP4", "mp4")}
      {video.audio_mp3_path && btn(`/stream/${video.id}/audio/mp3`, "MP3", "mp3")}
      {video.audio_ogg_path && btn(`/stream/${video.id}/audio/ogg`, "OGG", "ogg")}
      {/* Non-media kinds have no video_path — offer the raw artifact instead. */}
      {video.file_path && itemKind(video) !== "video" && !video.audio_mp3_path &&
        btn(`/stream/${video.id}/file?download=1`, formatLabel(video), "bin")}
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  );
}
