"use client";

// Home. Signed out: what this is, then one form to create an account or sign in.
// Video or voice is chosen later, on the practice page. Signed in: where to pick up.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, ApiError, firstName, Fact, Me, SessionSummary } from "@/lib/api";
import { DISCLAIMER, END_REASON, STATUS } from "@/lib/copy";

type Snapshot = { version: number | null; funding?: { error?: string }; missing?: Record<string, string[]> };
type Home = { me: Me; unchecked: number; ready: boolean; last: SessionSummary | null };

const isReady = (snap: Snapshot) =>
  snap.version !== null && (snap.missing?.uk_pre_cas ?? []).length === 0 && !snap.funding?.error;

const STEPS: [string, string][] = [
  ["Create your account", "Free to start. No card needed."],
  ["Check your facts", "Confirm the details your interviewer will use."],
  ["Have a conversation", "Video or voice. Five minutes, three questions, out loud, like the real day."],
  ["See your feedback", "What went well and what to practise, in your own words."],
];

export default function HomePage() {
  const router = useRouter();
  const [home, setHome] = useState<Home | null | undefined>(undefined); // undefined = loading
  const [account, setAccount] = useState<"signup" | "signin">("signup");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const signup = account === "signup";

  useEffect(() => {
    api<Me>("/me")
      .then(async (me) => {
        const [facts, snap, sessions] = await Promise.all([
          api<Fact[]>("/profile/facts"),
          api<Snapshot>("/profile/snapshot"),
          api<SessionSummary[]>("/sessions"),
        ]);
        const unchecked = facts.filter((f) => f.confirmation_status === "proposed").length;
        setHome({ me, unchecked, ready: isReady(snap), last: sessions.find((s) => s.status !== "created" && s.status !== "active") ?? null });
      })
      .catch(() => setHome(null));
  }, []);

  // The header's "Sign in" link (/#signin) opens the form in sign-in mode.
  useEffect(() => {
    const sync = () => {
      if (window.location.hash === "#signin") setAccount("signin");
    };
    window.addEventListener("hashchange", sync);
    const t = setTimeout(sync, 0);
    return () => {
      clearTimeout(t);
      window.removeEventListener("hashchange", sync);
    };
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (signup) {
        await api("/auth/signup", { method: "POST", json: { name, email, password } });
        router.push("/prepare"); // a new account always checks its facts first
        return;
      }
      await api("/auth/login", { method: "POST", json: { email, password } });
      const snap = await api<Snapshot>("/profile/snapshot").catch(() => ({ version: null }) as Snapshot);
      router.push(isReady(snap) ? "/interview" : "/prepare");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : signup ? "Could not create your account." : "Could not sign in.");
      setBusy(false);
    }
  }

  // Scrolls to the form in sign-up mode. Not a "#signin" link: that hash means sign in.
  function startFree() {
    setAccount("signup");
    setError("");
    document.getElementById("signin")?.scrollIntoView({ block: "start" });
    setTimeout(() => document.getElementById("name")?.focus({ preventScroll: true }), 0);
  }

  function switchMode() {
    setAccount(signup ? "signin" : "signup");
    setError("");
  }

  return (
    <Shell width="wide" me={home === undefined ? undefined : (home?.me ?? null)}>
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
                <p className="small">Pick video or voice on the next page.</p>
                <Link href="/interview" className="btn btn-primary">Practise again</Link>
              </>
            )}
          </div>
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
            <p className="lead">Talk with an AI interviewer by voice or video, and get feedback after every session.</p>
            <button type="button" className="btn btn-primary" onClick={startFree}>Start practising free</button>
            <div className="card demo" aria-label="Example of a practice exchange" style={{ marginTop: 28 }}>
              <div><span className="bubble q">Why did you choose this course?</span></div>
              <div className="a-wrap"><span className="bubble a">I chose MSc Data Science because its machine learning modules build on my…</span></div>
              <p className="ok">✓ Clear and specific</p>
            </div>
          </section>

          <form className="card signin" id="signin" onSubmit={submit}>
            <h2>{signup ? "Create your free account" : "Welcome back"}</h2>
            {signup && (
              <div className="field">
                <label htmlFor="name">Your name</label>
                <input id="name" type="text" autoComplete="name" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
            )}
            <div className="field">
              <label htmlFor="email">Email</label>
              <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete={signup ? "new-password" : "current-password"}
                minLength={signup ? 8 : undefined}
                aria-describedby={signup ? "pw-hint" : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              {signup && <p id="pw-hint" className="caption" style={{ margin: "6px 0 0" }}>At least 8 characters.</p>}
            </div>
            <button type="submit" className="btn btn-primary btn-block" disabled={busy} style={{ marginTop: 16 }}>
              {busy ? (signup ? "Creating your account…" : "Signing in…") : signup ? "Create account" : "Sign in"}
            </button>
            {error && <p className="error" role="alert" style={{ marginTop: 10 }}>{error}</p>}
            <p className="caption" style={{ marginTop: 12 }}>
              {signup ? "Free practice time to start. No card needed. Already have an account?" : "New here?"}{" "}
              <button type="button" className="btn btn-ghost" onClick={switchMode}>
                {signup ? "Sign in" : "Create a free account"}
              </button>
            </p>
          </form>
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
