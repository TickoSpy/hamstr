import { SiteLogins } from "@/components/settings/SiteLogins";

export function SettingsPage() {
  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8 mb-player">
      <h1 className="text-xl font-semibold mb-6">Settings</h1>
      <SiteLogins />
    </div>
  );
}
