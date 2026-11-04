// Approved wording. Change here, not inline.
export const DISCLAIMER =
  "This is practice only. Your interviewer is a fictional AI, not a university officer or UKVI, and not connected to any university or government. Practising here cannot predict or affect any CAS or visa decision.";

export const DATA_NOTE =
  "Your voice and the details you give are sent to the AI services that run the interviewer. Our small team reads sessions and ratings to improve the practice.";

// Google Form for the paid-version waiting list. Empty = the button shows "opening soon".
export const WAITLIST_URL = "";

export const TIERS = {
  avatar: {
    title: "Video interviewer",
    desc: "See a friendly face while you talk. Feels closest to the real thing.",
    chip: "Best on Wi-Fi",
  },
  voice: {
    title: "Voice only",
    desc: "Just talk, no camera. Works well even on slower connections.",
    chip: "Works on mobile data",
  },
} as const;

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
