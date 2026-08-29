import { PlaylistPanel } from "@/components/library/PlaylistPanel";

export function PlaylistsPage() {
  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8 mb-player">
      <h1 className="text-xl font-semibold mb-6">Playlists</h1>
      <PlaylistPanel />
    </div>
  );
}
