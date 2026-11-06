// Contract between the session API and the interview page.
//
// The API returns a `launch` describing how to show the chosen provider. The page
// looks up a "stage" component by `launch.kind` (components/stages). Everything else
// on the page (clock, End button, page-exit beacon, feedback, rating) is shared.
//
// A vendor that hands you an iframe URL is kind "iframe" and needs no code. A vendor
// with its own JS SDK gets a new kind + one stage component (see ElevenLabsStage).

export type ProviderInfo = {
  id: string;
  label: string;
  modality: "avatar" | "voice";
  data_note: string;
  capabilities: { transcripts?: boolean; student_facts?: boolean; server_can_end?: boolean };
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

// ElevenLabs agent, run in the browser with the ElevenLabs SDK. Private agents get a
// short-lived conversation token from our server; a public test agent gets only its id.
export type ElevenLabsLaunch = {
  kind: "elevenlabs";
  connection_type: "webrtc";
  conversation_token?: string;
  agent_id?: string;
  dynamic_variables: Record<string, string>;
};

// Video agents: an avatar SDK in the browser, voiced by our ElevenLabs agent.
export type LiveAvatarLaunch = { kind: "liveavatar"; session_token: string };

export type KeyframeLaunch = {
  kind: "keyframe";
  session_details: { server_url: string; participant_token: string; agent_identity: string };
  voice_agent: { type: "elevenlabs"; agent_id: string; signed_url: string };
  dynamic_variables: Record<string, string>;
};

export type Launch = IframeLaunch | ElevenLabsLaunch | LiveAvatarLaunch | KeyframeLaunch;

export type StartResp = {
  session_id: string;
  created: boolean;
  provider_id: string;
  launch: Launch;
  practice_seconds: number;
  disclosure: string;
};

export type Phase =
  | "idle"
  | "starting"
  | "connecting"
  | "waiting_start"
  | "in_call"
  | "listening"
  | "speaking"
  | "completed"
  | "error";

export const PHASE_TEXT: Record<Phase, string> = {
  idle: "",
  starting: "Reserving your session…",
  connecting: "Connecting…",
  waiting_start: "Tap the interviewer window to begin",
  in_call: "Interview in progress",
  listening: "Your turn. Speak now.",
  speaking: "Interviewer speaking…",
  completed: "Session complete",
  error: "",
};

// Every stage gets the same callbacks, so the page never needs to know the vendor.
export type StageProps<L extends Launch> = {
  sessionId: string;
  launch: L;
  onPhase: (p: Phase) => void;
  onClock: (practiceEndsAtMs: number) => void;
  onNotice: (message: string) => void;
  onEnded: (reason: string) => void; // the media ended on its own (agent/vendor/network)
};
