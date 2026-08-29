import { UrlInput } from "@/components/queue/UrlInput";
import { DropZone } from "@/components/queue/DropZone";
import { QueueList } from "@/components/queue/QueueList";
import { TranscodeList } from "@/components/queue/TranscodeList";

export function QueuePage() {
  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8 space-y-8 mb-player">
      <DropZone />
      <div>
        <h1 className="text-xl font-semibold mb-1">Archive Queue</h1>
        <p className="text-gray-500 text-sm mb-5">
          Paste links below or drag them onto the page — videos, articles, PDFs, images.
        </p>
        <UrlInput />
      </div>
      <TranscodeList />
      <QueueList />
    </div>
  );
}
