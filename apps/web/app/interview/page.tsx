"use client";

// Step 3: pick an interviewer, start, talk, end. The page knows nothing about
// vendors: the API returns a launch and the matching stage component renders it.
// Clock, End button, page-exit cleanup and the move to the session page are shared.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ComponentType } from "react";
import Shell from "@/components/Shell";
import { STAGES } from "@/components/stages";
import { checkMicrophone } from "@/components/stages/trackCall";
import TierCards from "@/components/TierCards";
import { api, ApiError, firstName, fmtSeconds, Me } from "@/lib/api";
import CodeBox from "@/components/CodeBox";
import { DATA_NOTE, DISCLAIMER, micErrorMessage } from "@/lib/copy";
import { PHASE_TEXT, type Launch, type Phase, type ProviderInfo, type StageProps, type StartResp } from "@/lib/providers";

const KEY_STORE = "ni-start-key";
const END_TIMEOUT_MS = 8_000;

type Live = { id: string; launch: Launch };

// Whole sessions the student can still start with this interviewer.
function sessionsLeft(me: Me, p: ProviderInfo) {
  const bucket = p.modality === "avatar" ? "premium_seconds" : "basic_seconds";
  const length = me.session_seconds[p.modality];
  return length > 0 ? Math.floor(me.balances[bucket].available / length) : 0;
}

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
  const [ending, setEnding] = useState(false);
  const endedRef = useRef(false);
  const sessionRef = useRef<string | null>(null);

  useEffect(() => {
    Promise.all([api<Me>("/me"), api<ProviderInfo[]>("/providers")])
      .then(([m, ps]) => {
        setMe(m);
        setProviders(ps);
        // Preselect the first interviewer the student has a session left for.
        const usable = ps.find((p) => sessionsLeft(m, p) > 0) ?? ps[0];
        setProviderId((cur) => cur || usable?.id || "");
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.push("/");
        else setError("Could not load interviewers.");
      });
  }, [router]);

  // Leaving the page ends the session server-side (settles credits, stops the vendor).
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

  const finish = useCallback(() => {
    const id = sessionRef.current;
    setLive(null); // unmounts the stage: disconnects the call / removes the iframe
    setEndsAt(null);
    setEnding(false);
    sessionRef.current = null;
    setPhase("completed");
    if (id) router.push(`/sessions/${id}`);
  }, [router]);

  const endNow = useCallback(
    async (reason = "ended") => {
      const id = sessionRef.current;
      // Hang up first: the call must stop even if the server is slow to answer.
      setEnding(true);
      setLive(null);
      setEndsAt(null);
      if (id && !endedRef.current) {
        endedRef.current = true;
        const r = reason === "ended" ? "student_ended" : reason;
        await api(`/sessions/${id}/end?reason=${encodeURIComponent(r)}`, {
          method: "POST",
          signal: AbortSignal.timeout(END_TIMEOUT_MS),
        }).catch(() => undefined); // the reconciler settles it if this never arrives
      }
      finish();
    },
    [finish],
  );

  const remaining = endsAt && now ? (endsAt - now) / 1000 : null;

  // The browser is the only thing that can stop the vendor stream, so the session
  // ends exactly at the server-set time.
  useEffect(() => {
    if (!endsAt || !live) return;
    const t = setInterval(() => {
      const ts = Date.now();
      setNow(ts);
      if (ts >= endsAt) void endNow("deadline");
    }, 250);
    return () => clearInterval(t);
  }, [endsAt, live, endNow]);

  async function start() {
    setError("");
    setNotice("");
    setLiveConflict(null);
    endedRef.current = false;
    setPhase("starting");
    // Before anything is reserved, so a blocked microphone uses no session.
    try {
      await checkMicrophone();
    } catch (e) {
      setPhase("error");
      setError(micErrorMessage(e));
      return;
    }
    // One key per intended start, reused on retry so the server returns the same session.
    let key = sessionStorage.getItem(KEY_STORE);
    if (!key) {
      key = crypto.randomUUID();
      sessionStorage.setItem(KEY_STORE, key);
    }
    try {
      const s = await api<StartResp>("/sessions", {
        method: "POST",
        headers: { "idempotency-key": key },
        json: { track: "uk_pre_cas", provider_id: providerId },
      });
      sessionStorage.removeItem(KEY_STORE);
      sessionRef.current = s.session_id;
      setLive({ id: s.session_id, launch: s.launch });
      setPhase("connecting");
    } catch (e) {
      // Keep the key when the server never answered or is still connecting, so the
      // retry returns the same session instead of hitting "session already live".
      if (e instanceof ApiError && e.code !== "launch_in_progress") sessionStorage.removeItem(KEY_STORE);
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

  const tierOff = (p: ProviderInfo) => (me ? (p.modality === "avatar" ? !me.video_available : !me.voice_available) : false);
  const used = (p: ProviderInfo) => (me ? sessionsLeft(me, p) === 0 : false);
  const leftText = (p: ProviderInfo) => {
    if (!me) return null;
    const n = sessionsLeft(me, p);
    return `${n} ${n === 1 ? "session" : "sessions"} left`;
  };
  const chosen = providers.find((p) => p.id === providerId);
  const Stage = live ? (STAGES[live.launch.kind] as ComponentType<StageProps<Launch>>) : null;

  return (
    <Shell
      step={3}
      width="narrow"
      me={me}
      locked={live !== null}
      title={live ? "Your practice interview" : me ? `Ready when you are, ${firstName(me)}.` : "Ready when you are."}
      intro={
        !live && chosen
          ? "Two minutes, three questions. Keep your answers short and direct."
          : undefined
      }
    >
      {ending && <div className="state" aria-live="polite">Ending your session…</div>}
      {!live && !ending && (
        <>
          <TierCards
            options={providers.map((p) => ({
              id: p.id,
              modality: p.modality,
              label: p.label,
              left: leftText(p),
              disabled: tierOff(p) || used(p),
              note: tierOff(p) ? undefined : p.modality === "avatar" ? "No video sessions left" : "Next free session tomorrow",
            }))}
            value={providerId || null}
            onChange={setProviderId}
          />
          {me && providers.length === 0 && <p className="error" style={{ marginTop: 12 }}>No interviewer is available right now.</p>}
          <CodeBox onRedeemed={() => api<Me>("/me").then(setMe).catch(() => undefined)} />
          {chosen?.capabilities.student_facts && (
            <p className="small" style={{ margin: "16px 0 0" }}>
              <Link href="/prepare">Add your details</Link> for a more realistic interview.
            </p>
          )}
          <p className="caption" style={{ margin: "16px 0 6px" }}>{chosen?.data_note} {DATA_NOTE}</p>
          <p className="caption" style={{ margin: "0 0 6px" }}>{DISCLAIMER}</p>
          <p className="caption" style={{ margin: "0 0 20px" }}>Your browser will ask to use your microphone. Tap Allow.</p>
          <button type="button" className="btn btn-primary btn-block" onClick={start} disabled={phase === "starting" || !me || !providerId || (chosen && (tierOff(chosen) || used(chosen)))}>
            {phase === "starting" ? "Starting…" : "Start practice"}
          </button>
        </>
      )}

      {live && Stage && (
        <>
          <div className="stage-wrap">
            <Stage sessionId={live.id} launch={live.launch} onPhase={setPhase} onClock={setEndsAt} onNotice={setNotice} onEnded={(reason) => void endNow(reason)} />
            <span className="chip left">Fictional AI · Practice</span>
            {remaining !== null && <span className="chip right nums">{fmtSeconds(Math.max(0, remaining))}</span>}
          </div>
          <div className="state" aria-live="polite">{PHASE_TEXT[phase]}</div>
          {notice && <p className="small center" role="status">{notice}</p>}
          <p className="caption center" style={{ margin: "0 0 16px" }}>{DISCLAIMER}</p>
          <button type="button" className="btn btn-danger btn-block" onClick={() => void endNow()}>End session</button>
        </>
      )}
      {error && <p className="error" role="alert" style={{ marginTop: 12 }}>{error}</p>}
      {liveConflict && (
        <button type="button" className="btn btn-secondary" onClick={endOther} style={{ marginTop: 8 }}>End the other session</button>
      )}
    </Shell>
  );
}
