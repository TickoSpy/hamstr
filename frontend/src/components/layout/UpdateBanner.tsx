import { RefreshCw } from "lucide-react";
import { useAppUpdate } from "@/hooks/useAppUpdate";

export function UpdateBanner() {
  const { updateReady, reload } = useAppUpdate();
  if (!updateReady) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-[60] flex justify-center px-4 pb-safe pointer-events-none">
      <div className="pointer-events-auto mb-4 flex items-center gap-3 rounded-full bg-gray-800 border border-gray-700 pl-4 pr-2 py-2 shadow-2xl animate-slide-up">
        <span className="text-sm text-gray-200">A new version is available</span>
        <button
          onClick={reload}
          className="flex items-center gap-1.5 rounded-full bg-red-600 hover:bg-red-500 px-3 py-1.5 text-sm font-medium text-white transition-colors"
        >
          <RefreshCw size={14} /> Reload
        </button>
      </div>
    </div>
  );
}
