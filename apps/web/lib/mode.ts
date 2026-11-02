// The interviewer style a student picked on the home page ("avatar" = video, "voice" =
// audio only). The interview page uses it to preselect a matching interviewer.
// Storage can be unavailable (private mode, blocked site data), so every access is guarded.

export type Mode = "avatar" | "voice";

const KEY = "ni-mode";

export function saveMode(mode: Mode) {
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    /* storage unavailable: the interview page falls back to the first interviewer */
  }
}

export function readMode(): Mode | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "avatar" || v === "voice" ? v : null;
  } catch {
    return null;
  }
}
