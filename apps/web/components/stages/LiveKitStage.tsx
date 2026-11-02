"use client";

// Our own pipeline: a LiveKit room with our interview agent (and optionally an avatar
// that publishes on the agent's behalf). The agent owns the session lifecycle and
// tells us state through participant attributes.

import { Participant, RemoteParticipant, RemoteTrack, Room, RoomEvent, Track } from "livekit-client";
import { useEffect, useRef, useState } from "react";
import type { LiveKitLaunch, StageProps } from "@/lib/providers";

// The avatar publishes on behalf of the agent and carries this attribute.
const ON_BEHALF = "lk.publish_on_behalf";

export default function LiveKitStage({ launch, mode, onPhase, onClock, onNotice, onEnded }: StageProps<LiveKitLaunch>) {
  const [display, setDisplay] = useState<"avatar" | "portrait">(mode === "avatar" ? "avatar" : "portrait");
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const audioSource = useRef<{ track: RemoteTrack; fromAvatar: boolean } | null>(null);
  // Set by the agent when it begins teardown, so a normal end is never mistaken for a failure.
  const ending = useRef("");
  const lastPhase = useRef<string>("connecting");
  const cb = useRef({ onPhase, onClock, onNotice, onEnded });
  useEffect(() => {
    cb.current = { onPhase, onClock, onNotice, onEnded };
  });

  useEffect(() => {
    const room = new Room({ adaptiveStream: true, dynacast: true });
    let closed = false;

    const setPhase = (p: Parameters<typeof onPhase>[0]) => {
      lastPhase.current = p;
      cb.current.onPhase(p);
    };

    function attachAudio(track: RemoteTrack, participant: RemoteParticipant) {
      // Exactly one interviewer audio stream: the avatar's when present, else the agent's.
      const fromAvatar = Boolean(participant.attributes[ON_BEHALF]);
      const cur = audioSource.current;
      if (cur && cur.fromAvatar && !fromAvatar) return;
      cur?.track.detach();
      if (audioRef.current) track.attach(audioRef.current);
      audioSource.current = { track, fromAvatar };
    }

    function readAgent(p: Participant) {
      if (!p.isAgent || p.attributes[ON_BEHALF]) return;
      const a = p.attributes;
      if (a["ni.practice_ends_at_ms"]) cb.current.onClock(Number(a["ni.practice_ends_at_ms"]));
      if (a["ni.display"] === "avatar" || a["ni.display"] === "portrait") setDisplay(a["ni.display"]);
      if (a["ni.fallback"]) {
        cb.current.onNotice("The video interviewer could not start, so this session continues in voice. Voice time is billed at the voice rate.");
      }
      if (a["ni.ending"]) ending.current = a["ni.ending"];
      const st = a["lk.agent.state"];
      if (st === "speaking" || st === "thinking") setPhase(st);
      else if (st === "listening") {
        // The student started talking over the interviewer: show the hand-back.
        if (lastPhase.current === "speaking" && room.localParticipant.isSpeaking) {
          setPhase("interrupted");
          setTimeout(() => lastPhase.current === "interrupted" && setPhase("listening"), 1200);
        } else setPhase("listening");
      } else if (lastPhase.current === "connecting" && a["ni.practice_ends_at_ms"]) setPhase("ready");
    }

    room
      .on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
        if (track.kind === Track.Kind.Video && videoRef.current) track.attach(videoRef.current);
        if (track.kind === Track.Kind.Audio) attachAudio(track, participant);
      })
      .on(RoomEvent.TrackUnsubscribed, (track) => {
        track.detach();
        if (audioSource.current?.track === track) audioSource.current = null;
      })
      .on(RoomEvent.ParticipantAttributesChanged, (_c, p) => readAgent(p))
      .on(RoomEvent.ParticipantConnected, (p) => readAgent(p))
      .on(RoomEvent.Reconnecting, () => setPhase("reconnecting"))
      .on(RoomEvent.Reconnected, () => setPhase("listening"))
      .on(RoomEvent.Disconnected, () => {
        if (!closed) cb.current.onEnded(ending.current === "avatar_lost" ? "avatar_lost" : "disconnected");
      })
      .on(RoomEvent.MediaDevicesError, () =>
        cb.current.onNotice("Microphone unavailable. Check permissions; the session will end if no answer is heard."),
      );

    (async () => {
      try {
        await room.connect(launch.server_url, launch.participant_token);
        await room.localParticipant.setMicrophoneEnabled(true, {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        });
        room.remoteParticipants.forEach((p) => readAgent(p));
      } catch (e) {
        const blocked = e instanceof Error && e.name === "NotAllowedError";
        cb.current.onNotice(blocked ? "Allow the microphone to practise." : "Could not connect.");
        cb.current.onEnded("connect_failed");
      }
    })();

    return () => {
      closed = true;
      room.removeAllListeners();
      audioSource.current?.track.detach();
      void room.disconnect();
    };
  }, [launch.server_url, launch.participant_token]);

  return (
    <div className="stage">
      <video ref={videoRef} autoPlay playsInline muted style={{ display: display === "avatar" ? "block" : "none" }} />
      {display === "portrait" && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src="/interviewer-portrait.svg" alt="Fictional practice interviewer" />
      )}
      <audio ref={audioRef} autoPlay />
    </div>
  );
}
