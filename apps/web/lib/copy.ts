// Approved wording. Change here, not inline.
export const DISCLAIMER =
  "This is practice only. Your interviewer is a fictional AI, not a university officer or UKVI, and not connected to any university or government. Practising here cannot predict or affect any CAS or visa decision.";

// Follows each interviewer's own note about what it receives.
export const DATA_NOTE = "Our small team reads sessions and ratings to improve the practice.";

// Shown on the privacy and terms pages. Set before going public.
export const CONTACT_EMAIL = "aashishsunar.01@gmail.com";

// Google Form for the paid-version waiting list. Empty = the button shows "opening soon".
export const WAITLIST_URL = "https://forms.gle/U4SiZez78g8QS4Fu5";

export const TIERS = {
  avatar: {
    title: "Video interviewer",
    desc: "See your interviewer while you talk. Your camera stays off.",
    chip: "Best on Wi-Fi",
  },
  voice: {
    title: "Voice only",
    desc: "Just talk, no camera. Uses any details you added.",
    chip: "Audio only",
  },
} as const;

// Why the microphone check failed, by the browser's error name.
export function micErrorMessage(e: unknown) {
  switch (e instanceof Error ? e.name : "") {
    case "NotAllowedError":
      return "Your microphone is blocked, so your session hasn't started. Allow it in your browser settings and try again. If you opened this inside Facebook or another app, open it in Chrome or Safari.";
    case "NotFoundError":
      return "We can't find a microphone on this device, so your session hasn't started. Connect one or try another device.";
    case "NotReadableError":
      return "Another app may be using your microphone, so your session hasn't started. Close it and try again.";
    default:
      return "This browser can't use your microphone, so your session hasn't started. Open this page in Chrome or Safari and try again.";
  }
}

export const END_REASON: Record<string, string> = {
  student_ended: "You ended it",
  deadline: "Time ran out",
  page_exit: "The tab was closed",
  connect_failed: "Could not connect",
  disconnected: "Connection lost",
  agent_ended: "The interviewer finished",
  settled_elsewhere: "Ended",
  reconciled_stale: "Connection lost",
  reconciled_startup_timeout: "Could not connect",
};

export const STATUS: Record<string, string> = {
  completed: "Finished",
  failed: "Did not start",
  active: "In progress",
  created: "Starting",
};
