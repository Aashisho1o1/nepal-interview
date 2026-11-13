"use client";

// A Keyframe avatar: the SDK talks to our ElevenLabs agent (signed URL from our server),
// sending the student's voice and details only there, and gives the avatar the agent's
// audio. The video goes in the box below. The SDK loads only for this call.

import { useEffect, useRef } from "react";
import type { PersonaView } from "@keyframelabs/elements";
import type { KeyframeLaunch, StageProps } from "@/lib/providers";
import { checkMicrophone, connectFailureNotice, trackCall } from "./trackCall";

export default function KeyframeStage({ sessionId, launch, onPhase, onClock, onNotice, onEnded }: StageProps<KeyframeLaunch>) {
  const box = useRef<HTMLDivElement>(null);
  const view = useRef<PersonaView | null>(null);
  // Keep the latest callbacks without re-running the effect (and restarting the call).
  const cb = useRef({ onPhase, onClock, onNotice, onEnded });
  useEffect(() => {
    cb.current = { onPhase, onClock, onNotice, onEnded };
  });

  useEffect(() => {
    const call = trackCall(sessionId, cb);
    let gone = false;
    let up = false;
    let playing = false;
    let agentHungUp = false;
    // Count time only once the microphone, the agent and the avatar's video are all up.
    const maybeReady = () => {
      if (up && playing) void call.ready("video_ready");
    };

    async function begin() {
      cb.current.onPhase("connecting");
      try {
        await checkMicrophone();
        const { PersonaView } = await import("@keyframelabs/elements");
        if (gone || !box.current) return;
        const v = new PersonaView({
          container: box.current,
          sessionDetails: launch.session_details,
          voiceAgentDetails: launch.voice_agent,
          dynamicVariables: launch.dynamic_variables,
          videoFit: "cover",
          onStateChange: (status) => {
            up = up || status === "connected";
            maybeReady();
          },
          onVideoReady: () => {
            playing = true;
            maybeReady();
          },
          onAgentStateChange: (state) => cb.current.onPhase(state),
          // Deferred: the SDK reports "closed" to us just after this callback.
          onDisconnect: () => {
            setTimeout(() => call.finish(agentHungUp ? "agent_ended" : call.isConnected() ? "disconnected" : "connect_failed"), 0);
          },
          onError: (e) => {
            if (call.isConnected()) return cb.current.onNotice("The connection had a problem.");
            cb.current.onNotice(connectFailureNotice(e));
            call.finish("connect_failed");
          },
        });
        v.on("closed", (c) => {
          agentHungUp = c.code === 1000; // a clean close: the agent ended the call
        });
        view.current = v;
        await v.connect(); // reports failures through onError
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
      view.current?.disconnect();
    };
    // The launch for a session never changes; run once per mounted call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A tap restarts playback where the browser blocked sound (Safari).
  return <div ref={box} className="stage-frame" style={{ aspectRatio: "1 / 1", overflow: "hidden" }} onClick={() => view.current?.unmuteAudio()} />;
}
