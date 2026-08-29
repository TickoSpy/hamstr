import { Loader2 } from "lucide-react";
import { useTranscodes } from "@/hooks/useVideos";
import { Thumb } from "@/components/library/Thumb";
import type { TranscodeJob, Video } from "@/lib/api";

const STATE_COLORS: Record<TranscodeJob["state"], string> = {
  running: "bg-purple-900 text-purple-300",
  queued: "bg-gray-700 text-gray-300",
};

export function TranscodeList() {
  const { data } = useTranscodes();
  const jobs = data ?? [];

  if (!jobs.length) return null;

  return (
    <div>
      <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">
        Transcoding
        <span className="ml-2 text-gray-600 normal-case">{jobs.length}</span>
      </h2>
      <div className="space-y-3">
        {jobs.map((job) => (
          <div
            key={job.id}
            className="flex items-center gap-4 p-4 bg-gray-900 rounded-lg border border-gray-800"
          >
            <div className="w-20 h-12 rounded overflow-hidden flex-shrink-0 bg-gray-800">
              <Thumb item={job as unknown as Video} iconSize={18} />
            </div>

            <div className="flex-1 min-w-0 space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATE_COLORS[job.state]}`}
                >
                  {job.state === "running" ? "transcoding" : "queued"}
                </span>
                {job.channel && (
                  <span className="text-xs text-gray-500 truncate">{job.channel}</span>
                )}
              </div>
              <p className="text-sm text-gray-200 truncate" title={job.title ?? job.id}>
                {job.title ?? job.id}
              </p>
              {job.state === "running" && (
                <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
                  <div className="h-1.5 bg-purple-600 animate-pulse w-full" />
                </div>
              )}
            </div>

            {job.state === "running" && (
              <Loader2 size={16} className="animate-spin text-purple-400 flex-shrink-0" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
