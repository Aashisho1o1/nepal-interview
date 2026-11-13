"use client";

// LiveAvatar in LITE mode: the SDK starts the session from our token, publishes the
// microphone and plays the avatar. Our ElevenLabs agent does the talking through the
// vendor's connector, so no ElevenLabs code runs here. The SDK loads only for this call.

import { useEffect, useRef } from "react";
import type { LiveAvatarSession } from "@heygen/liveavatar-web-sdk";
import type { LiveAvatarLaunch, StageProps } from "@/lib/providers";
import { checkMicrophone, connectFailureNotice, trackCall } from "./trackCall";

export default function LiveAvatarStage({ sessionId, launch, onPhase, onClock, onNotice, onEnded }: StageProps<LiveAvatarLaunch>) {
  const video = useRef<HTMLVideoElement>(null);
  // Keep the latest callbacks without re-running the effect (and restarting the call).
  const cb = useRef({ onPhase, onClock, onNotice, onEnded });
  useEffect(() => {
    cb.current = { onPhase, onClock, onNotice, onEnded };
  });

  useEffect(() => {
    const call = trackCall(sessionId, cb);
    let session: LiveAvatarSession | null = null;
    let gone = false;

    async function begin() {
      cb.current.onPhase("connecting");
      try {
        await checkMicrophone(); // the SDK itself only logs a refusal, and the call runs on
        const sdk = await import("@heygen/liveavatar-web-sdk");
        if (gone) return;
        const s = new sdk.LiveAvatarSession(launch.session_token);
        session = s;
        s.on(sdk.SessionEvent.SESSION_STREAM_READY, () => {
          if (video.current) s.attach(video.current);
          void call.ready("stream_ready");
        });
        s.on(sdk.AgentEventsEnum.AVATAR_SPEAK_STARTED, () => cb.current.onPhase("speaking"));
        s.on(sdk.AgentEventsEnum.AVATAR_SPEAK_ENDED, () => cb.current.onPhase("listening"));
        s.on(sdk.AgentEventsEnum.USER_SPEAK_STARTED, () => cb.current.onPhase("listening"));
        s.on(sdk.AgentEventsEnum.SESSION_STOPPED, (e) => call.finish(e.stop_reason === "AGENT_HANG_UP" ? "agent_ended" : "disconnected"));
        s.on(sdk.SessionEvent.SESSION_DISCONNECTED, () => call.finish(call.isConnected() ? "disconnected" : "connect_failed"));
        await s.start();
        if (gone) return void (await s.stop()); // left while connecting: stop() does nothing until now
        // The microphone can still fail here, and the SDK would only log it.
        if (s.voiceChat.state !== sdk.VoiceChatState.ACTIVE) throw new Error("microphone not publishing");
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
      void session?.stop().catch(() => undefined);
    };
    // The launch for a session never changes; run once per mounted call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A tap restarts playback where the browser blocked sound (Safari).
  return <video ref={video} className="stage-frame" style={{ aspectRatio: "16 / 9" }} autoPlay playsInline onClick={() => void video.current?.play()} />;
}
