"use client";

// ElevenLabs agent, run in the browser with the ElevenLabs SDK (WebRTC). The agent's
// prompt, voice and turn-taking live in the ElevenLabs dashboard; we pass this
// student's confirmed facts as dynamic variables. trackCall reports the clock start
// and heartbeats; the page ends the call at the server-set deadline by unmounting it.

import { Conversation } from "@elevenlabs/react";
import { useEffect, useRef, useState } from "react";
import type { ElevenLabsLaunch, StageProps } from "@/lib/providers";
import { connectFailureNotice, trackCall } from "./trackCall";

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
    const call = trackCall(sessionId, cb);
    let conv: Session | null = null;
    let gone = false;

    async function begin() {
      cb.current.onPhase("connecting");
      const base = {
        connectionType: "webrtc" as const,
        dynamicVariables: launch.dynamic_variables,
        onConnect: () => {
          setMode("listening");
          void call.ready("call_connected");
        },
        onModeChange: ({ mode: m }: { mode: "speaking" | "listening" }) => {
          setMode(m);
          cb.current.onPhase(m);
        },
        onError: () => {
          cb.current.onNotice("The interviewer had a problem. If the call stops, please try again.");
        },
        onDisconnect: (d: { reason: "error" | "agent" | "user" }) => {
          call.finish(d.reason === "agent" ? "agent_ended" : call.isConnected() ? "disconnected" : "connect_failed");
        },
      };
      try {
        const started = launch.conversation_token
          ? Conversation.startSession({ ...base, conversationToken: launch.conversation_token })
          : Conversation.startSession({ ...base, agentId: launch.agent_id ?? "" });
        conv = await started;
        if (gone) await conv.endSession(); // unmounted while connecting
      } catch (e) {
        if (gone) return;
        cb.current.onNotice(connectFailureNotice(e));
        call.finish("connect_failed");
      }
    }

    // Deferred so React's dev-mode double mount never starts two calls.
    const startTimer = setTimeout(() => void begin(), 0);
    return () => {
      gone = true;
      clearTimeout(startTimer);
      call.close();
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
