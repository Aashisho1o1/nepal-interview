"use client";

// The interview page knows nothing about vendors. It lets the student pick an
// interviewer (provider), asks the API to start a session, and renders whichever
// stage matches the returned launch.kind. Clock, End, page-exit cleanup, and the move
// to feedback are shared by every provider.

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ComponentType } from "react";
import { CLIENT_DRIVEN, STAGES } from "@/components/stages";
import { api, ApiError, fmtSeconds, Me } from "@/lib/api";
import { PHASE_TEXT, type Launch, type Phase, type ProviderInfo, type StageProps, type StartResp } from "@/lib/providers";

const KEY_STORE = "ni-start-key";
// Our agent ends LiveKit sessions itself; this is only a safety net after its closing line.
const AGENT_END_GRACE_S = 20;

type Live = { id: string; launch: Launch; mode: "avatar" | "voice"; disclosure: string };

export default function Interview() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [providerId, setProviderId] = useState<string>("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [live, setLive] = useState<Live | null>(null);
  const [endsAt, setEndsAt] = useState<number | null>(null);
  const [now, setNow] = useState(0);
  const [liveConflict, setLiveConflict] = useState<string | null>(null);
  const endedRef = useRef(false);
  const sessionRef = useRef<string | null>(null);

  useEffect(() => {
    Promise.all([api<Me>("/me"), api<ProviderInfo[]>("/providers")])
      .then(([m, ps]) => {
        setMe(m);
        setProviders(ps);
        setProviderId((cur) => cur || ps[0]?.id || "");
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.push("/");
        else setError("Could not load interviewers.");
      });
  }, [router]);

  // Leaving the page ends the session server-side (settles billing, closes vendor media).
  useEffect(() => {
    const onHide = () => {
      const id = sessionRef.current;
      if (id && !endedRef.current) {
        endedRef.current = true;
        navigator.sendBeacon(`/api/sessions/${id}/end?reason=page_exit`, new Blob([""], { type: "text/plain" }));
      }
    };
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, []);

  const finish = useCallback(
    (reason: string) => {
      const id = sessionRef.current;
      setLive(null); // unmounts the stage: disconnects LiveKit / removes the vendor iframe
      setEndsAt(null);
      sessionRef.current = null;
      if (reason === "avatar_lost") {
        setPhase("error");
        setError("The video interviewer disconnected. Unused time was returned. You can continue with voice only.");
        const voice = providers.find((p) => p.modality === "voice");
        if (voice) setProviderId(voice.id);
        return;
      }
      setPhase("completed");
      if (id) router.push(`/sessions/${id}`);
    },
    [providers, router],
  );

  const endNow = useCallback(
    async (reason = "ended") => {
      const id = sessionRef.current;
      if (id && !endedRef.current) {
        endedRef.current = true;
        const r = reason === "ended" ? "student_ended" : reason;
        await api(`/sessions/${id}/end?reason=${encodeURIComponent(r)}`, { method: "POST" }).catch(() => undefined);
      }
      finish(reason);
    },
    [finish],
  );

  const remaining = endsAt && now ? (endsAt - now) / 1000 : null;

  // Clock tick + deadline. For embeds/hosted vendors the browser is the only thing that
  // can stop the vendor stream, so it ends exactly at the server-set time. For our own
  // agent (which ends the call itself) it is only a backstop.
  useEffect(() => {
    if (!endsAt || !live) return;
    const graceMs = CLIENT_DRIVEN.has(live.launch.kind) ? 0 : AGENT_END_GRACE_S * 1000;
    const t = setInterval(() => {
      const ts = Date.now();
      setNow(ts);
      if (ts >= endsAt + graceMs) void endNow("deadline");
    }, 250);
    return () => clearInterval(t);
  }, [endsAt, live, endNow]);

  async function start() {
    setError("");
    setNotice("");
    setLiveConflict(null);
    endedRef.current = false;
    setPhase("starting");
    // One key per intended start, reused on retry/double-click so the server returns the
    // same session (and the same vendor conversation) instead of reserving twice.
    let key = sessionStorage.getItem(KEY_STORE);
    if (!key) {
      key = crypto.randomUUID();
      sessionStorage.setItem(KEY_STORE, key);
    }
    try {
      const s = await api<StartResp>("/sessions", {
        method: "POST",
        headers: { "idempotency-key": key },
        json: { track: "us_f1", format_id: "pressure_drill_3m", provider_id: providerId },
      });
      sessionStorage.removeItem(KEY_STORE);
      sessionRef.current = s.session_id;
      setLive({ id: s.session_id, launch: s.launch, mode: s.mode, disclosure: s.disclosure });
      setPhase("connecting");
    } catch (e) {
      sessionStorage.removeItem(KEY_STORE);
      setPhase("error");
      if (e instanceof ApiError && e.code === "session_already_live") setLiveConflict(String(e.body.session_id ?? ""));
      setError(e instanceof ApiError ? e.message : "Could not start.");
    }
  }

  async function endOther() {
    if (!liveConflict) return;
    await api(`/sessions/${liveConflict}/end`, { method: "POST" }).catch(() => undefined);
    setLiveConflict(null);
    setError("");
    setPhase("idle");
  }

  const balanceFor = (p: ProviderInfo) =>
    me ? fmtSeconds(me.balances[p.modality === "avatar" ? "premium_seconds" : "basic_seconds"].available) : "";
  const Stage = live ? (STAGES[live.launch.kind] as ComponentType<StageProps<Launch>>) : null;

  return (
    <main>
      <h1>US F-1 practice drill</h1>
      {!live && (
        <>
          <p className="muted">
            Three minutes with a fictional AI practice interviewer. The interviewer is not a consular officer and this
            does not predict a visa decision. Answer truthfully using your confirmed facts.
          </p>
          <div className="choices" role="radiogroup" aria-label="Interviewer">
            {providers.map((p) => (
              <label className="choice" key={p.id}>
                <input type="radio" name="provider" checked={providerId === p.id} onChange={() => setProviderId(p.id)} />
                <span>
                  <strong>{p.label}</strong>
                  <br />
                  <span className="muted">
                    {p.data_note} {me && `${balanceFor(p)} left.`}
                    {p.capabilities.transcripts === false && " No scorecard for this one yet; you'll rate it instead."}
                  </span>
                </span>
              </label>
            ))}
            {me && providers.length === 0 && <p className="error">No interviewer is available right now.</p>}
          </div>
          <button onClick={start} disabled={phase === "starting" || !me || !providerId} style={{ marginTop: 12 }}>
            Start practice
          </button>
        </>
      )}

      {live && Stage && (
        <>
          <div className="stage-wrap">
            <Stage
              sessionId={live.id}
              launch={live.launch}
              mode={live.mode}
              onPhase={setPhase}
              onClock={setEndsAt}
              onNotice={setNotice}
              onEnded={(reason) => void endNow(reason)}
            />
            <span className="badge">Fictional AI interviewer · practice</span>
            {remaining !== null && <span className="clock">{fmtSeconds(Math.max(0, remaining))}</span>}
          </div>
          <div className="state" aria-live="polite">{PHASE_TEXT[phase]}</div>
          {notice && <p className="muted" role="status">{notice}</p>}
          {live.disclosure && <p className="muted">{live.disclosure}</p>}
          <button className="danger" onClick={() => void endNow()} style={{ width: "100%" }}>
            End session
          </button>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {liveConflict && (
        <button className="secondary" onClick={endOther}>End the other session</button>
      )}
    </main>
  );
}
