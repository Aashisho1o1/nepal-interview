"use client";

// Home. Signed out: what this is, pick an interviewer, sign in. Signed in: a resume
// card and the same choice, no sales page. The pick is remembered so the interview
// page preselects it.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Shell from "@/components/Shell";
import TierCards from "@/components/TierCards";
import { api, ApiError, firstName, fmtSeconds, Fact, Me, SessionSummary } from "@/lib/api";
import { DISCLAIMER, END_REASON, STATUS, TIERS } from "@/lib/copy";
import { saveMode, type Mode } from "@/lib/mode";

type Snapshot = { version: number | null; funding?: { error?: string }; missing?: Record<string, string[]> };
type Home = { me: Me; unchecked: number; ready: boolean; last: SessionSummary | null };

const STEPS: [string, string][] = [
  ["Pick your interviewer", "Video or voice, whichever suits you today."],
  ["Check your facts", "Confirm the details from your documents. Fix anything wrong."],
  ["Have a conversation", "Five minutes, three questions, out loud, like the real day."],
  ["See your feedback", "What went well and what to practise, in your own words."],
];

export default function HomePage() {
  const router = useRouter();
  const [home, setHome] = useState<Home | null | undefined>(undefined); // undefined = loading
  const [mode, setMode] = useState<Mode | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Me>("/me")
      .then(async (me) => {
        const [facts, snap, sessions] = await Promise.all([
          api<Fact[]>("/profile/facts"),
          api<Snapshot>("/profile/snapshot"),
          api<SessionSummary[]>("/sessions"),
        ]);
        const unchecked = facts.filter((f) => f.confirmation_status === "proposed").length;
        const ready = snap.version !== null && (snap.missing?.uk_pre_cas ?? []).length === 0 && !snap.funding?.error;
        setHome({ me, unchecked, ready, last: sessions.find((s) => s.status !== "created" && s.status !== "active") ?? null });
      })
      .catch(() => setHome(null));
  }, []);

  function choose(m: Mode) {
    setMode(m);
    saveMode(m);
    if (home) {
      setBusy(true);
      router.push(home.ready ? "/interview" : "/prepare");
      return;
    }
    document.getElementById("signin")?.scrollIntoView({ block: "center" });
    emailRef.current?.focus({ preventScroll: true });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/login", { method: "POST", json: { email, password } });
      const snap = await api<Snapshot>("/profile/snapshot").catch(() => ({ version: null }) as Snapshot);
      const ready = snap.version !== null && (snap.missing?.uk_pre_cas ?? []).length === 0 && !snap.funding?.error;
      router.push(ready ? "/interview" : "/prepare");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
      setBusy(false);
    }
  }

  const me = home?.me ?? null;
  const tiers = (
    <TierCards
      options={(["avatar", "voice"] as const).map((m) => ({
        id: m,
        modality: m,
        minutesLeft: me ? fmtSeconds(me.balances[m === "avatar" ? "premium_seconds" : "basic_seconds"].available) : null,
        disabled: me ? (m === "avatar" ? !me.video_available : !me.voice_available) : false,
      }))}
      value={mode}
      onChange={(id) => choose(id as Mode)}
    />
  );

  return (
    <Shell width="wide" me={home === undefined ? undefined : me}>
      {home ? (
        <section className="section cards">
          <h1>Welcome back, {firstName(home.me)}.</h1>
          <div className="card card-strong">
            {home.unchecked > 0 || !home.ready ? (
              <>
                <h2>Finish checking your facts{home.unchecked > 0 && <span className="nums"> ({home.unchecked} left)</span>}</h2>
                <p className="small">Your interviewer only uses details you&apos;ve marked as correct.</p>
                <Link href="/prepare" className="btn btn-primary">Continue</Link>
              </>
            ) : (
              <>
                <h2>Ready for another session?</h2>
                <p className="small">Pick an interviewer below, or jump straight back in.</p>
                <Link href="/interview" className="btn btn-primary">Practise again</Link>
              </>
            )}
          </div>
          {tiers}
          {home.last && (
            <p className="small" style={{ marginTop: 16 }}>
              Last session: <span className="nums">{new Date(home.last.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</span> ·{" "}
              {home.last.mode === "avatar" ? "Video" : "Voice"} · {home.last.end_reason === "deadline" ? "Time ran out" : STATUS[home.last.status] ?? END_REASON[home.last.end_reason ?? ""] ?? "Ended"}{" "}
              <Link href={`/sessions/${home.last.id}`}>See feedback →</Link>
            </p>
          )}
        </section>
      ) : (
        <>
          <section className="hero">
            <span className="chip chip--outline">UK pre-CAS interview practice · Early access</span>
            <h1 className="display">Practise your pre-CAS interview before the real one.</h1>
            <p className="lead">Talk with an AI interviewer by voice or video. Built on your own documents, with feedback after every session.</p>
            <div className="card demo" aria-label="Example of a practice exchange">
              <div><span className="bubble q">Why did you choose this course?</span></div>
              <div className="a-wrap"><span className="bubble a">I chose MSc Data Science because its machine learning modules build on my…</span></div>
              <p className="ok">✓ Clear and specific</p>
            </div>
          </section>

          <section className="section cards" id="choose">
            <p className="eyebrow">Choose your interviewer</p>
            <h2>Who would you like to talk to?</h2>
            {tiers}
            <form className="card signin" id="signin" onSubmit={submit}>
              <h2>Sign in to start</h2>
              {mode ? (
                <p className="chips" style={{ marginBottom: 14 }}>
                  <span className="chip">You picked: {TIERS[mode].title}</span>
                  <button type="button" className="btn btn-ghost" onClick={() => setMode(null)}>change</button>
                </p>
              ) : (
                <p className="small">Pick an interviewer above, then sign in.</p>
              )}
              <div className="field">
                <label htmlFor="email">Email</label>
                <input id="email" ref={emailRef} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <div className="field">
                <label htmlFor="password">Password</label>
                <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </div>
              <button type="submit" className="btn btn-primary btn-block" disabled={busy} style={{ marginTop: 16 }}>
                {busy ? "Signing in…" : "Sign in"}
              </button>
              {error && <p className="error" role="alert" style={{ marginTop: 10 }}>{error}</p>}
              <p className="caption" style={{ marginTop: 12 }}>
                Use the email and password from your consultancy. New here? Ask your counsellor for an account. This is a private early preview.
              </p>
            </form>
          </section>
        </>
      )}

      <section className="section" id="how">
        <p className="eyebrow">How it works</p>
        <div className="rows">
          {STEPS.map(([t, d], i) => (
            <div key={t}>
              <span className="n">0{i + 1}</span>
              <div>
                <h2>{t}</h2>
                <span className="small">{d}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <p className="eyebrow">What you get</p>
        <div className="card finding">
          <span className="severity severity--good">Strength</span>
          <div className="caption">Funding explanation</div>
          <div className="quote">“My father will pay the fees from his savings of fifteen thousand pounds, and the deposit is already paid.”</div>
          <p>You named the source and the amount, and both match your confirmed facts.</p>
          <p><strong>Next:</strong> Say when the money will be available, too.</p>
        </div>
        <p className="caption">Example feedback from a practice session.</p>
      </section>

      <footer className="footer">
        <p className="caption">{DISCLAIMER}</p>
      </footer>
    </Shell>
  );
}
