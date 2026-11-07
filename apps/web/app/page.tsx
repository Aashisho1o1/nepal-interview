"use client";

// Home. Signed out: what this is, how it works, then one form at the bottom to create
// an account or sign in.
// Video or voice is chosen later, on the practice page. Signed in: where to pick up.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import Waitlist from "@/components/Waitlist";
import { api, ApiError, firstName, Me, SessionSummary } from "@/lib/api";
import { DISCLAIMER, END_REASON, STATUS } from "@/lib/copy";

type Home = { me: Me; last: SessionSummary | null };

const STEPS: [string, string][] = [
  ["Create your account", "Free: a voice session every day, and a video session on each of your first three days."],
  ["Add your details, if you like", "Optional. Only voice calls use them, so you can go straight to practice."],
  ["Have a conversation", "Video or voice. Three questions, out loud, in two minutes."],
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
        const sessions = await api<SessionSummary[]>("/sessions");
        setHome({ me, last: sessions.find((s) => s.status !== "created" && s.status !== "active") ?? null });
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
        router.push("/interview");
        return;
      }
      await api("/auth/login", { method: "POST", json: { email, password } });
      router.push("/interview");
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
            <h2>Ready to practise?</h2>
            <p className="small">Pick video or voice on the next page.</p>
            <div className="btn-row">
              <Link href="/interview" className="btn btn-primary">Practise now</Link>
              <Link href="/prepare" className="btn btn-secondary">Update my details</Link>
            </div>
          </div>
          {home.last && (
            <p className="small" style={{ marginTop: 16 }}>
              Last session: <span className="nums">{new Date(home.last.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</span> ·{" "}
              {home.last.mode === "avatar" ? "Video" : "Voice"} · {home.last.end_reason === "deadline" ? "Time ran out" : STATUS[home.last.status] ?? END_REASON[home.last.end_reason ?? ""] ?? "Ended"}{" "}
              <Link href={`/sessions/${home.last.id}`}>See session →</Link>
            </p>
          )}
        </section>
      ) : (
        <>
          <section className="hero">
            <span className="chip chip--outline">Visa Interview Practice</span>
            <h1 className="display">Don&apos;t freeze when your UK university asks “Why this course?”</h1>
            <p className="lead">
              Practise speaking out loud with a fictional AI interviewer on a two-minute video or audio call. Get used to
              answering on the spot, in your own words, before your real pre-CAS interview.
            </p>
            <p className="small">
              Early access covers the UK pre-CAS interview. The US, Europe and Australia are coming soon.
            </p>
            <button type="button" className="btn btn-primary" onClick={startFree}>Start practising free</button>
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

      {!home && (
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
              {signup && (
                <p className="caption" style={{ marginTop: 12 }}>
                  By creating an account, you confirm you&apos;re 18 or over and agree to our{" "}
                  <Link href="/terms" target="_blank">Terms</Link> and <Link href="/privacy" target="_blank">Privacy Policy</Link>.
                </p>
              )}
              <p className="caption" style={{ marginTop: 12 }}>
                {signup ? "Free to start. No card needed. Already have an account?" : "New here?"}{" "}
                <button type="button" className="btn btn-ghost" onClick={switchMode}>
                  {signup ? "Sign in" : "Create a free account"}
                </button>
              </p>
            </form>
      )}

      <Waitlist />

      <footer className="footer">
        <p className="caption">{DISCLAIMER}</p>
      </footer>
    </Shell>
  );
}
