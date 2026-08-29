import { Link, useLocation } from "react-router-dom";
import { Download, Library, ListMusic, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { useNavScroll } from "@/hooks/useNavScroll";
import { usePlayer } from "@/lib/playerContext";

export function NavBar() {
  const { pathname } = useLocation();
  const { isModalOpen, current } = usePlayer();
  // Fullscreen video owns the whole screen — slide the nav out so it isn't
  // painted over the video's top edge.
  const fullscreenVideo = isModalOpen && !!current && !current.audio_only;
  const visible = useNavScroll() && !fullscreenVideo;

  const link = (to: string, icon: React.ReactNode, label: React.ReactNode) => (
    <Link
      to={to}
      className={cn(
        "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
        pathname === to
          ? "bg-red-600 text-white"
          : "text-gray-400 hover:text-white hover:bg-gray-800"
      )}
    >
      {icon}
      {label}
    </Link>
  );

  return (
    <nav className={cn(
      "fixed top-0 left-0 right-0 z-50 h-14 border-b border-gray-800 bg-gray-950 px-4 sm:px-6 flex items-center gap-1 sm:gap-2 transition-transform duration-200 ease-in-out",
      visible ? "translate-y-0" : "-translate-y-full"
    )}>
      <span className="text-red-500 font-bold text-lg mr-4">▶ YT</span>
      {link("/", <Library size={16} />, "Library")}
      {link("/queue", <Download size={16} />, "Queue")}
      {link("/playlists", <ListMusic size={16} />, "Playlists")}
      <div className="ml-auto">
        {/* Label hidden on phones: four labelled links overflow a narrow nav. */}
        {link(
          "/settings",
          <Settings size={16} />,
          <span className="sr-only sm:not-sr-only">Settings</span>
        )}
      </div>
    </nav>
  );
}
