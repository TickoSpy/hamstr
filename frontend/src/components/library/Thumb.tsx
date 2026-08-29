import type { Video } from "@/lib/api";
import { thumbnailUrl, cn } from "@/lib/utils";
import { KIND_ICON, KIND_TINT, itemKind } from "@/lib/kinds";

/**
 * Thumbnail for any archived item. Falls back to a kind icon (plus the source
 * domain's initials for articles) when there is no image — articles, PDFs and
 * generic files usually have none.
 */
export function Thumb({
  item,
  className,
  iconSize = 32,
}: {
  item: Video;
  className?: string;
  iconSize?: number;
}) {
  const src = thumbnailUrl(item);
  const kind = itemKind(item);

  if (src) {
    return (
      <img
        src={src}
        alt={item.title ?? ""}
        className={cn(
          "w-full h-full object-cover touch-callout-none select-none",
          className,
        )}
        loading="lazy"
        draggable={false}
      />
    );
  }

  const Icon = KIND_ICON[kind];
  const initials = (item.source_domain ?? item.channel ?? "")
    .replace(/^www\./, "")
    .slice(0, 18);

  return (
    <div
      className={cn(
        "w-full h-full flex flex-col items-center justify-center gap-1.5 bg-gray-800",
        className,
      )}
    >
      <Icon size={iconSize} className={KIND_TINT[kind]} />
      {initials && (
        <span className="text-[10px] text-gray-500 px-2 truncate max-w-full">
          {initials}
        </span>
      )}
    </div>
  );
}
