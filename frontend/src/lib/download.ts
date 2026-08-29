// Saving a file out of the app on iOS.
//
// A plain `<a download>` — with or without target="_blank", which iOS ignores
// for same-origin URLs in a standalone (home-screen) PWA — navigates the app's
// only window to the attachment. Standalone mode has no browser chrome, so
// there is no back button: the user is stranded on the black "Open with…"
// preview and has to force-quit the app to get out.
//
// Hand the bytes to the share sheet instead. It offers "Save to Files" and
// dismisses straight back into the app. Everywhere else, the anchor is still
// the right thing and downloads without leaving the page.
//
// NB: the share path buffers the whole file in memory. That is fine for
// articles, PDFs and audio; a multi-GB video would be better fetched from a
// real browser tab.

export function isStandalone(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches === true ||
    (navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

function filenameFrom(res: Response, fallback: string): string {
  const cd = res.headers.get("content-disposition") ?? "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  if (star) return decodeURIComponent(star[1]);
  const plain = /filename="?([^";]+)"?/i.exec(cd);
  return plain ? plain[1] : fallback;
}

function anchorDownload(href: string, filename: string): void {
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/**
 * Resolves once the file has been handed to the share sheet (or downloaded
 * directly outside standalone mode). Rejects if the bytes could not be
 * fetched; a dismissed share sheet is not an error.
 */
export async function saveFile(href: string, fallbackName: string): Promise<void> {
  const canShareFiles =
    isStandalone() && typeof navigator.canShare === "function" && typeof navigator.share === "function";
  if (!canShareFiles) {
    anchorDownload(href, fallbackName);
    return;
  }

  const res = await fetch(href);
  if (!res.ok) throw new Error(`Download failed: HTTP ${res.status}`);
  const blob = await res.blob();
  const file = new File([blob], filenameFrom(res, fallbackName), {
    type: blob.type || "application/octet-stream",
  });

  if (!navigator.canShare({ files: [file] })) {
    // No file sharing on this device — a blob URL at least keeps the app
    // window intact, unlike navigating to the attachment.
    const url = URL.createObjectURL(blob);
    anchorDownload(url, file.name);
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
    return;
  }

  try {
    await navigator.share({ files: [file] });
  } catch (err) {
    // The user dismissed the sheet. Nothing went wrong.
    if (err instanceof DOMException && err.name === "AbortError") return;
    throw err;
  }
}
