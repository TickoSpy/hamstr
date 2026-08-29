import { useEffect, useState } from "react";
import { extractUrls } from "@/lib/utils";
import { useSubmitUrls } from "@/hooks/useVideos";

export function DropZone() {
  const [active, setActive] = useState(false);
  const submit = useSubmitUrls();

  useEffect(() => {
    const onDragOver = (e: DragEvent) => {
      e.preventDefault();
      setActive(true);
    };
    const onDragLeave = () => setActive(false);
    const onDrop = async (e: DragEvent) => {
      e.preventDefault();
      setActive(false);
      const text = e.dataTransfer?.getData("text/plain") ?? "";
      const urls = extractUrls(text);
      if (urls.length) submit.mutate({ urls });
    };

    window.addEventListener("dragover", onDragOver);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
    };
  }, [submit]);

  if (!active) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/90 border-4 border-dashed border-red-500 pointer-events-none">
      <div className="text-center">
        <p className="text-3xl font-bold text-red-500">Drop link to archive</p>
        <p className="text-gray-400 mt-2">Release to add to queue</p>
      </div>
    </div>
  );
}
