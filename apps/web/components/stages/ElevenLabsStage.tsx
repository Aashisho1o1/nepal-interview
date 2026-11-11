"use client";

// ElevenLabs agent, run in the browser with the ElevenLabs SDK (WebRTC). The agent's
// prompt, voice and turn-taking live in the ElevenLabs dashboard; we pass this
// student's confirmed facts as dynamic variables. Like the iframe stage, this stage
// reports the lifecycle the server needs (clock start on connect, heartbeats), and the
// page ends the call at the server-set deadline by unmounting it.

import { Conversation } from "@elevenlabs/react";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ElevenLabsLaunch, StageProps } from "@/lib/providers";

const HEARTBEAT_MS = 15_000;
const CLOCK_RETRY_MS = 2_000;

type EventReply = { live: boolean; practice_ends_at: number | null };
type Session = Awaited<ReturnType<typeof Conversation.startSession>>;
type Mode = "connecting" | "listening" | "speaking";

export default function ElevenLabsStage({ sessionId, launch, onPhase, onClock, onNotice, onEnded }: StageProps<ElevenLabsLaunch>) {
  const [mode, setMode] = useState<Mode>("connecting");
  // Keep the latest callbacks without re-running the effect (and restarting the call).
  const cb = useRef({ onPhase, onClock, onNotice, onEnded });
  useEffect(() => {
    cb.current = { onPhase, onClock, onNotice, onEnded };
  });

  useEffect(() => {
    let conv: Session | null = null;
    let closing = false; // we are ending it (unmount): ignore the resulting disconnect
    let connected = false;
    const mountedAt = performance.now();

    const post = (kind: string, payload: Record<string, unknown> = {}) =>
      api<EventReply>(`/sessions/${sessionId}/client-events`, { method: "POST", json: { kind, payload } });

    const finish = (reason: string) => {
      if (closing) return;
      closing = true;
      cb.current.onEnded(reason);
    };

    async function begin() {
      cb.current.onPhase("connecting");
      const base = {
        connectionType: "webrtc" as const,
        dynamicVariables: launch.dynamic_variables,
        onConnect: async () => {
          connected = true;
          setMode("listening");
          // Start the server's clock. If the server can't be told, end the call (the
          // session is refunded) rather than let it run uncounted.
          const payload = { trigger: "call_connected", ready_ms: Math.round(performance.now() - mountedAt) };
          for (const wait of [0, CLOCK_RETRY_MS]) {
            await new Promise((resolve) => setTimeout(resolve, wait));
            if (closing) return;
            try {
              const r = await post("media_ready", payload);
              if (closing) return;
              if (r.practice_ends_at) cb.current.onClock(r.practice_ends_at * 1000);
              cb.current.onPhase("listening");
              if (!r.live) finish("settled_elsewhere");
              return;
            } catch {
              /* try once more */
            }
          }
          finish("connect_failed");
        },
        onModeChange: ({ mode: m }: { mode: "speaking" | "listening" }) => {
          setMode(m);
          cb.current.onPhase(m);
        },
        onError: () => {
          cb.current.onNotice("The interviewer had a problem. If the call stops, please try again.");
        },
        onDisconnect: (d: { reason: "error" | "agent" | "user" }) => {
          if (closing) return;
          if (d.reason === "agent") return finish("agent_ended");
          finish(connected ? "disconnected" : "connect_failed");
        },
      };
      try {
        const started = launch.conversation_token
          ? Conversation.startSession({ ...base, conversationToken: launch.conversation_token })
          : Conversation.startSession({ ...base, agentId: launch.agent_id ?? "" });
        conv = await started;
        if (closing) await conv.endSession(); // unmounted while connecting
      } catch (e) {
        const blocked = e instanceof Error && e.name === "NotAllowedError";
        cb.current.onNotice(blocked ? "Allow the microphone to practise." : "Could not connect to the interviewer.");
        finish("connect_failed");
      }
    }

    // Deferred so React's dev-mode double mount (mount, unmount, mount) never starts two
    // calls: the first mount's timer is cleared before it fires.
    const startTimer = setTimeout(() => void begin(), 0);

    const heartbeat = setInterval(async () => {
      if (!connected || closing) return;
      try {
        const r = await post("heartbeat");
        if (!r.live) finish("settled_elsewhere");
      } catch {
        /* transient; the server tolerates missed heartbeats */
      }
    }, HEARTBEAT_MS);

    return () => {
      closing = true;
      clearTimeout(startTimer);
      clearInterval(heartbeat);
      void conv?.endSession().catch(() => undefined);
    };
    // The launch for a session never changes; run once per mounted call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="voice-stage" role="img" aria-label="Voice interviewer">
      <div className="orb" data-mode={mode} />
    </div>
  );
}
