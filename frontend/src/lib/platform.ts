// Single source of truth for the platform decisions playback depends on.
// Touch support is not one of them: a touchscreen laptop is a desktop browser,
// and treating it as a phone is what put the lock-screen handoff in the way of
// an ordinary tab switch.

const ua = navigator.userAgent;

// iPadOS 13+ reports a desktop user agent; MacIntel plus real touch points is
// the only tell left.
export const isIOS =
  /iP(hone|ad|od)/.test(ua) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

export const isAndroid = /Android/.test(ua);

/**
 * True on platforms that suspend a playing <video> when the app is backgrounded
 * or the screen locks — iOS always, Android whenever the browser leaves the
 * foreground. Only there does playback hand over to the <audio> element. A
 * desktop browser keeps a hidden tab's <video> playing and must be left alone.
 */
export const needsBackgroundAudioHandoff = isIOS || isAndroid;
