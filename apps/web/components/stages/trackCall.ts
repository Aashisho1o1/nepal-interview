// What a video stage reports to the server, whichever vendor runs the call: the clock
// start, heartbeats and the one way out. A paid call must never run without the clock.

import type { RefObject } from "react";
import { api } from "@/lib/api";
import type { Launch, StageProps } from "@/lib/providers";

const HEARTBEAT_MS = 15_000;
const CLOCK_RETRY_MS = 2_000;

type EventReply = { live: boolean; practice_ends_at: number | null };
export type StageCallbacks = Pick<StageProps<Launch>, "onPhase" | "onClock" | "onNotice" | "onEnded">;

// Throws NotAllowedError if the student refuses. Asked before the vendor session starts,
// so a refused microphone costs nothing.
export async function checkMicrophone() {
  const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
  mic.getTracks().forEach((t) => t.stop());
}

export function connectFailureNotice(e: unknown) {
  return e instanceof Error && e.name === "NotAllowedError" ? "Allow the microphone to practise." : "Could not connect to the interviewer.";
}

export function trackCall(sessionId: string, cb: RefObject<StageCallbacks>) {
  let ended = false;
  let connected = false;
  const mountedAt = performance.now();

  const post = (kind: string, payload: Record<string, unknown> = {}) =>
    api<EventReply>(`/sessions/${sessionId}/client-events`, { method: "POST", json: { kind, payload } });

  const finish = (reason: string) => {
    if (ended) return;
    ended = true;
    cb.current.onEnded(reason);
  };

  const heartbeat = setInterval(async () => {
    if (!connected || ended) return;
    try {
      if (!(await post("heartbeat")).live) finish("settled_elsewhere");
    } catch {
      /* transient; the server tolerates missed heartbeats */
    }
  }, HEARTBEAT_MS);

  return {
    isConnected: () => connected,
    finish,
    // The call is usable: start the server's clock, once. If the server can't be told,
    // end the call (the session is refunded) rather than let it run uncounted.
    async ready(trigger: string) {
      if (connected || ended) return;
      connected = true;
      const payload = { trigger, ready_ms: Math.round(performance.now() - mountedAt) };
      for (const wait of [0, CLOCK_RETRY_MS]) {
        await new Promise((r) => setTimeout(r, wait));
        if (ended) return;
        try {
          const r = await post("media_ready", payload);
          if (ended) return;
          if (r.practice_ends_at) cb.current.onClock(r.practice_ends_at * 1000);
          // Not "Your turn": the interviewer usually speaks first. Turn-taking comes
          // from the stage's own events, when the vendor sends them.
          cb.current.onPhase("in_call");
          if (!r.live) finish("settled_elsewhere");
          return;
        } catch {
          /* try once more */
        }
      }
      finish("connect_failed");
    },
    // The stage is going away: nothing more is reported.
    close() {
      ended = true;
      clearInterval(heartbeat);
    },
  };
}
