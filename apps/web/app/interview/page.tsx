"use client";

import {
  Participant,
  RemoteParticipant,
  RemoteTrack,
  Room,
  RoomEvent,
  Track,
} from "livekit-client";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, fmtSeconds, Me } from "@/lib/api";

type Mode = "avatar" | "voice";
type Phase =
  | "idle"
  | "starting"
  | "connecting"
  | "ready"
  | "listening"
  | "thinking"
  | "speaking"
  | "interrupted"
  | "reconnecting"
  | "completed"
  | "error";

type StartResp = {
  session_id: string;
  server_url: string;
  participant_token: string;
  mode: Mode;
  practice_seconds: number;
  disclosure: string;
};

const PHASE_TEXT: Record<Phase, string> = {
  idle: "",
  starting: "Reserving your session…",
  connecting: "Connecting to the interviewer…",
  ready: "Ready",
  listening: "Listening",
  thinking: "Thinking…",
  speaking: "Interviewer speaking",
  interrupted: "Interrupted — go ahead",
  reconnecting: "Reconnecting…",
  completed: "Session complete",
  error: "",
};

// The avatar publishes on behalf of the agent and carries this attribute.
const ON_BEHALF = "lk.publish_on_behalf";
const KEY_STORE = "ni-start-key";

export default function Interview() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [mode, setMode] = useState<Mode>("avatar");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [display, setDisplay] = useState<"avatar" | "portrait">("portrait");
  const [fallback, setFallback] = useState("");
  const [endsAt, setEndsAt] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const [liveConflict, setLiveConflict] = useState<string | null>(null);
  const [disclosure, setDisclosure] = useState("");

  const roomRef = useRef<Room | null>(null);
  const sessionRef = useRef<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const audioSourceRef = useRef<{ track: RemoteTrack; fromAvatar: boolean } | null>(null);
  const endedRef = useRef(false);
  // Set by the agent when it begins teardown, so a normal end is never mistaken for a failure.
  const endingRef = useRef<string>("");

  useEffect(() => {
    api<Me>("/me")
      .then((m) => {
        setMe(m);
        if (!m.avatar_available) setMode("voice");
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.push("/");
      });
  }, [router]);

  useEffect(() => {
    if (!endsAt) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [endsAt]);

  // Leaving the page ends the session server-side (settles billing, closes the room).
  useEffect(() => {
    const onHide = () => {
      const id = sessionRef.current;
      if (id && !endedRef.current) {
        endedRef.current = true;
        navigator.sendBeacon(`/api/sessions/${id}/end`, new Blob([""], { type: "text/plain" }));
      }
    };
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      void roomRef.current?.disconnect();
    };
  }, []);

  const finish = useCallback(
    (reason: string) => {
      const id = sessionRef.current;
      const room = roomRef.current;
      roomRef.current = null;
      room?.removeAllListeners();
      void room?.disconnect();
      audioSourceRef.current?.track.detach();
      audioSourceRef.current = null;
      setEndsAt(null);
      if (reason === "avatar_lost") {
        setPhase("error");
        setError("The avatar disconnected. Unused time was returned. You can continue with voice practice.");
        setMode("voice");
        sessionRef.current = null;
        return;
      }
      setPhase("completed");
      if (id) router.push(`/sessions/${id}`);
    },
    [router],
  );

  function attachAudio(track: RemoteTrack, participant: RemoteParticipant) {
    // Exactly one interviewer audio stream: the avatar's when present, else the agent's.
    const fromAvatar = Boolean(participant.attributes[ON_BEHALF]);
    const cur = audioSourceRef.current;
    if (cur && cur.fromAvatar && !fromAvatar) return;
    cur?.track.detach();
    if (audioRef.current) track.attach(audioRef.current);
    audioSourceRef.current = { track, fromAvatar };
  }

  function readAgentAttributes(p: Participant) {
    if (!p.isAgent || p.attributes[ON_BEHALF]) return;
    const a = p.attributes;
    if (a["ni.practice_ends_at_ms"]) setEndsAt(Number(a["ni.practice_ends_at_ms"]));
    if (a["ni.display"] === "avatar" || a["ni.display"] === "portrait") setDisplay(a["ni.display"]);
    if (a["ni.fallback"]) setFallback(a["ni.fallback"]);
    if (a["ni.ending"]) endingRef.current = a["ni.ending"];
    const st = a["lk.agent.state"];
    setPhase((prev) => {
      if (["completed", "error", "reconnecting"].includes(prev)) return prev;
      if (st === "speaking" || st === "thinking") return st;
      if (st === "listening") {
        const room = roomRef.current;
        // The student started talking over the interviewer: show the hand-back.
        if (prev === "speaking" && room?.localParticipant.isSpeaking) {
          setTimeout(() => setPhase((p) => (p === "interrupted" ? "listening" : p)), 1200);
          return "interrupted";
        }
        return "listening";
      }
      return prev === "connecting" && a["ni.practice_ends_at_ms"] ? "ready" : prev;
    });
  }

  async function start() {
    setError("");
    setLiveConflict(null);
    setFallback("");
    endedRef.current = false;
    endingRef.current = "";
    setPhase("starting");
    // One key per intended start, reused on retry/double-click so the server
    // returns the same session instead of reserving twice.
    let key = sessionStorage.getItem(KEY_STORE);
    if (!key) {
      key = crypto.randomUUID();
      sessionStorage.setItem(KEY_STORE, key);
    }
    let s: StartResp;
    try {
      s = await api<StartResp>("/sessions", {
        method: "POST",
        headers: { "idempotency-key": key },
        json: { track: "us_f1", format_id: "pressure_drill_3m", mode },
      });
    } catch (e) {
      sessionStorage.removeItem(KEY_STORE);
      setPhase("error");
      if (e instanceof ApiError && e.code === "session_already_live") {
        setLiveConflict(String(e.body.session_id ?? ""));
      }
      setError(e instanceof ApiError ? e.message : "Could not start.");
      return;
    }
    sessionStorage.removeItem(KEY_STORE);
    sessionRef.current = s.session_id;
    setDisclosure(s.disclosure);
    setDisplay(s.mode === "avatar" ? "avatar" : "portrait");
    setPhase("connecting");

    const room = new Room({ adaptiveStream: true, dynacast: true });
    roomRef.current = room;
    room
      .on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
        if (track.kind === Track.Kind.Video && videoRef.current) track.attach(videoRef.current);
        if (track.kind === Track.Kind.Audio) attachAudio(track, participant);
      })
      .on(RoomEvent.TrackUnsubscribed, (track) => {
        track.detach();
        if (audioSourceRef.current?.track === track) audioSourceRef.current = null;
      })
      .on(RoomEvent.ParticipantAttributesChanged, (_changed, p) => readAgentAttributes(p))
      .on(RoomEvent.ParticipantConnected, (p) => readAgentAttributes(p))
      .on(RoomEvent.Reconnecting, () => setPhase("reconnecting"))
      .on(RoomEvent.Reconnected, () => setPhase("listening"))
      .on(RoomEvent.Disconnected, () => {
        if (roomRef.current === room) finish(endingRef.current === "avatar_lost" ? "avatar_lost" : "disconnected");
      })
      .on(RoomEvent.MediaDevicesError, () => {
        setError("Microphone unavailable. Check permissions; the session will end if no answer is heard.");
      });

    try {
      await room.connect(s.server_url, s.participant_token);
      await room.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });
      room.remoteParticipants.forEach((p) => readAgentAttributes(p));
    } catch (e) {
      const blocked = e instanceof Error && e.name === "NotAllowedError";
      setError(blocked ? "Allow the microphone to practise." : "Could not connect.");
      await endNow();
    }
  }

  async function endNow() {
    const id = sessionRef.current;
    if (id && !endedRef.current) {
      endedRef.current = true;
      await api(`/sessions/${id}/end`, { method: "POST" }).catch(() => undefined);
    }
    finish("ended");
  }

  async function endOther() {
    if (!liveConflict) return;
    await api(`/sessions/${liveConflict}/end`, { method: "POST" }).catch(() => undefined);
    setLiveConflict(null);
    setError("");
    setPhase("idle");
  }

  const remaining = endsAt ? Math.max(0, (endsAt - now) / 1000) : null;
  const live = !["idle", "error", "completed"].includes(phase);
  const bal = me?.balances;

  return (
    <main>
      <h1>US F-1 practice drill</h1>
      {!live && (
        <>
          <p className="muted">
            Three minutes with Maya, a fictional AI practice interviewer. She is not a consular officer
            and this does not predict a visa decision. Answer truthfully using your confirmed facts.
          </p>
          <div className="choices">
            <label className="choice">
              <input type="radio" name="mode" checked={mode === "avatar"} disabled={!me?.avatar_available} onChange={() => setMode("avatar")} />
              <span>
                <strong>Video interviewer</strong>
                <br />
                <span className="muted">Uses more data (video). {bal && `${fmtSeconds(bal.premium_seconds.available)} left.`}</span>
                {me && !me.avatar_available && <span className="error"> Unavailable right now.</span>}
              </span>
            </label>
            <label className="choice">
              <input type="radio" name="mode" checked={mode === "voice"} onChange={() => setMode("voice")} />
              <span>
                <strong>Voice only</strong>
                <br />
                <span className="muted">Lower data use, still image. {bal && `${fmtSeconds(bal.basic_seconds.available)} left.`}</span>
              </span>
            </label>
          </div>
          <p className="muted">
            Your microphone audio goes to the voice provider (OpenAI) through LiveKit. In video mode the
            interviewer&apos;s generated speech also goes to Simli to animate the face. Calls are not
            recorded; the transcript is kept for your feedback.
          </p>
          <button onClick={start} disabled={phase === "starting" || !me}>
            Start practice
          </button>
        </>
      )}

      {live && (
        <>
          <div className="stage">
            <video ref={videoRef} autoPlay playsInline muted style={{ display: display === "avatar" ? "block" : "none" }} />
            {display === "portrait" && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src="/interviewer-portrait.svg" alt="Fictional practice interviewer" />
            )}
            <span className="badge">Fictional AI interviewer · practice</span>
            {remaining !== null && <span className="clock">{fmtSeconds(remaining)}</span>}
          </div>
          <div className="state" aria-live="polite">{PHASE_TEXT[phase]}</div>
          {fallback && (
            <p className="muted" role="status">
              The video interviewer could not start, so this session continues in voice. Voice time is
              billed at the voice rate.
            </p>
          )}
          {disclosure && <p className="muted">{disclosure}</p>}
          <button className="danger" onClick={endNow} style={{ width: "100%" }}>
            End session
          </button>
        </>
      )}
      <audio ref={audioRef} autoPlay />
      {error && <p className="error" role="alert">{error}</p>}
      {liveConflict && (
        <button className="secondary" onClick={endOther}>End the other session</button>
      )}
    </main>
  );
}
