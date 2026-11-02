// Contract between the session API and the interview page.
//
// The API picks a provider and returns a `launch` describing how to show it. The page
// looks up a "stage" component by `launch.kind` (components/stages). Everything else
// on the page (clock, End button, page-exit beacon, feedback, rating) is shared.
//
// To add a vendor that hands you an iframe URL (LiveAvatar embed, Tavus, D-ID...) you
// change nothing here: it is kind "iframe". A vendor with its own JS SDK (e.g.
// ElevenLabs Agents) gets a new kind + one new stage component.

export type ProviderInfo = {
  id: string;
  label: string;
  modality: "avatar" | "voice";
  data_note: string;
  capabilities: { transcripts?: boolean; student_facts?: boolean; server_can_end?: boolean };
};

export type LiveKitLaunch = {
  kind: "livekit";
  server_url: string;
  participant_token: string;
};

export type IframeLaunch = {
  kind: "iframe";
  url: string;
  origin: string;
  allow: string;
  aspect_ratio: string;
  // When the practice clock starts: when the iframe loads, or when the student first
  // interacts with it (many embeds wait for a click before connecting).
  clock_start: "on_load" | "on_interaction";
  clock_fallback_ms: number;
  title: string;
};

export type Launch = LiveKitLaunch | IframeLaunch;

export type StartResp = {
  session_id: string;
  created: boolean;
  provider_id: string;
  launch: Launch;
  mode: "avatar" | "voice";
  practice_seconds: number;
  disclosure: string;
};

export type Phase =
  | "idle"
  | "starting"
  | "connecting"
  | "waiting_start"
  | "ready"
  | "in_call"
  | "listening"
  | "thinking"
  | "speaking"
  | "interrupted"
  | "reconnecting"
  | "completed"
  | "error";

export const PHASE_TEXT: Record<Phase, string> = {
  idle: "",
  starting: "Reserving your session…",
  connecting: "Connecting to the interviewer…",
  waiting_start: "Tap or click the interviewer window to begin",
  ready: "Ready",
  in_call: "Interview in progress",
  listening: "Listening",
  thinking: "Thinking…",
  speaking: "Interviewer speaking",
  interrupted: "Interrupted — go ahead",
  reconnecting: "Reconnecting…",
  completed: "Session complete",
  error: "",
};

// Every stage gets the same callbacks, so the page never needs to know the vendor.
export type StageProps<L extends Launch> = {
  sessionId: string;
  launch: L;
  mode: "avatar" | "voice";
  onPhase: (p: Phase) => void;
  onClock: (practiceEndsAtMs: number) => void;
  onNotice: (message: string) => void;
  onEnded: (reason: string) => void; // the media ended on its own (agent/vendor/network)
};
