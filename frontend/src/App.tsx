import { useEffect } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
} from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NavBar } from "@/components/layout/NavBar";
import { QueuePage } from "@/pages/QueuePage";
import { LibraryPage } from "@/pages/LibraryPage";
import { PlaylistsPage } from "@/pages/PlaylistsPage";
import { ReaderPage } from "@/pages/ReaderPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { wsClient } from "@/lib/ws";
import { useWebSocket } from "@/hooks/useWebSocket";
import { PlayerProvider } from "@/lib/playerContext";
import { GlobalPlayer } from "@/components/player/GlobalPlayer";
import { OfflineProvider } from "@/lib/offline/context";
import { UpdateBanner } from "@/components/layout/UpdateBanner";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10_000, retry: 1 },
  },
});

function AppInner() {
  useWebSocket();
  // The reader owns the full viewport and renders its own back button, so the
  // app chrome (and the padding reserved for it) is dropped there.
  const isReader = useLocation().pathname.startsWith("/read/");

  return (
    <div className={isReader ? "min-h-screen" : "min-h-screen pt-14"}>
      {!isReader && <NavBar />}
      <Routes>
        <Route path="/" element={<LibraryPage />} />
        <Route path="/queue" element={<QueuePage />} />
        <Route path="/playlists" element={<PlaylistsPage />} />
        <Route path="/read/:id" element={<ReaderPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        {/* The library used to live here; keep old links and bookmarks working. */}
        <Route path="/library" element={<Navigate to="/" replace />} />
      </Routes>
      <GlobalPlayer />
      <UpdateBanner />
    </div>
  );
}

export default function App() {
  useEffect(() => {
    wsClient.connect();
    return () => wsClient.disconnect();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <PlayerProvider>
        <OfflineProvider>
          <BrowserRouter>
            <AppInner />
          </BrowserRouter>
        </OfflineProvider>
      </PlayerProvider>
    </QueryClientProvider>
  );
}
