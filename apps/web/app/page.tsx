"use client";

// Home page: welcome, what the practice offers, how it works, then the student picks a
// video or voice interviewer and signs in. Their pick is remembered so the interview
// page can preselect a matching interviewer.

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, fmtSeconds, Me } from "@/lib/api";
import { saveMode, type Mode } from "@/lib/mode";

type Snapshot = { version: number | null; funding?: { error?: string }; missing?: Record<string, string[]> };

const MODE_LABEL: Record<Mode, string> = { avatar: "Video interviewer", voice: "Voice only" };

export default function Home() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [mode, setMode] = useState<Mode | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Me>("/me")
      .then(setMe)
      .catch(() => undefined); // not signed in: the page shows the sign-in card
  }, []);

  // Facts must be confirmed before an interview can start, so only go straight to the
  // interview when the saved snapshot is complete.
  async function goNext() {
    try {
      const snap = await api<Snapshot>("/profile/snapshot");
      const ready = snap.version !== null && (snap.missing?.us_f1 ?? []).length === 0 && !snap.funding?.error;
      router.push(ready ? "/interview" : "/prepare");
    } catch {
      router.push("/prepare");
    }
  }

  function choose(m: Mode) {
    setMode(m);
    saveMode(m);
    if (me) {
      setBusy(true);
      void goNext();
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
      await goNext();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
      setBusy(false);
    }
  }

  const firstName = me?.display_name.split(" ")[0];
  const videoOff = me !== null && !me.video_available;
  const voiceOff = me !== null && !me.voice_available;

  return (
    <main className="landing" id="top">
      <div className="hero">
        <div className="wrap">
          <nav className="nav" aria-label="Main">
            <a className="brand" href="#top">
              <BrandMark />
              Interview Practice
            </a>
            {me ? (
              <a className="nav-link" href="#choose">Hi, {firstName}</a>
            ) : (
              <a className="nav-link" href="#signin">Sign in</a>
            )}
          </nav>

          <div className="hero-grid">
            <div>
              <span className="eyebrow">Namaste, and welcome!</span>
              <h1>
                Walk into your visa interview <span className="hl">feeling ready</span>.
              </h1>
              <p className="lead">
                Practise with a friendly AI interviewer that knows your study plans and funding. Answer in your own
                words, get kind and clear feedback, and try again whenever you like.
              </p>
              <div className="cta-row">
                <a className="btn" href="#choose">Start practising</a>
                <a className="btn ghost" href="#how">How it works</a>
              </div>
              <ul className="trust">
                <li>Uses only facts you confirm</li>
                <li>Short sessions</li>
                <li>Video or voice</li>
              </ul>
            </div>
            <HeroScene />
          </div>
        </div>
      </div>

      <section className="section alt" aria-labelledby="features-title">
        <div className="wrap">
          <div className="section-head">
            <span className="kicker">Why students like it</span>
            <h2 id="features-title">Everything you need to practise with confidence</h2>
            <p>Simple, honest practice built around your own story.</p>
          </div>
          <div className="features">
            <Feature tint="tint-coral" icon={<IconDoc />} title="Built from your documents">
              We pull the key facts from your papers. You mark what&apos;s right and what&apos;s wrong, and the
              interviewer only uses what you confirmed.
            </Feature>
            <Feature tint="tint-sun" icon={<IconClock />} title="Short, focused sessions">
              A few minutes and a few questions with a patient interviewer. Easy to fit in between classes.
            </Feature>
            <Feature tint="tint-mint" icon={<IconChat />} title="Feedback in your own words">
              Your scorecard quotes exactly what you said, shows what went well, and what to practise next.
            </Feature>
            <Feature tint="tint-sky" icon={<IconCalc />} title="Your funding, made clear">
              See your costs, scholarships and funds added up, so you can explain them calmly.
            </Feature>
          </div>
        </div>
      </section>

      <section className="section" id="how" aria-labelledby="how-title">
        <div className="wrap">
          <div className="section-head">
            <span className="kicker">How it works</span>
            <h2 id="how-title">Four easy steps</h2>
          </div>
          <ol className="steps">
            <li><strong>Pick your interviewer</strong><span>Video or voice, whichever suits you today.</span></li>
            <li><strong>Check your facts</strong><span>Confirm the details from your documents, fix anything wrong.</span></li>
            <li><strong>Have a conversation</strong><span>Answer questions out loud, just like the real day.</span></li>
            <li><strong>See your scorecard</strong><span>Celebrate what went well and know what to polish.</span></li>
          </ol>
        </div>
      </section>

      <section className="section alt" id="choose" aria-labelledby="choose-title">
        <div className="wrap">
          <div className="section-head">
            <span className="kicker">Let&apos;s begin</span>
            <h2 id="choose-title">
              {firstName ? `Welcome back, ${firstName}! Who would you like to talk to?` : "Who would you like to talk to?"}
            </h2>
            <p>You can switch any time. Both interviewers ask the same kind of questions.</p>
          </div>

          <div className="modes">
            <button
              type="button"
              className="mode-card video"
              aria-pressed={mode === "avatar"}
              disabled={busy || videoOff}
              onClick={() => choose("avatar")}
            >
              <span className="mode-art"><ArtVideo /></span>
              <span className="mode-title">Video interviewer</span>
              <span className="mode-desc">Talk face to face with an animated interviewer. It feels the most like the real thing.</span>
              <span className="tags">
                <span className="tag">Best on Wi-Fi</span>
                {me && !videoOff && <span className="tag">{fmtSeconds(me.balances.premium_seconds.available)} left</span>}
                {videoOff && <span className="tag">Not available right now</span>}
              </span>
              <span className="mode-go">Practise with video →</span>
            </button>

            <button
              type="button"
              className="mode-card voice"
              aria-pressed={mode === "voice"}
              disabled={busy || voiceOff}
              onClick={() => choose("voice")}
            >
              <span className="mode-art"><ArtVoice /></span>
              <span className="mode-title">Voice only</span>
              <span className="mode-desc">Just your voice and theirs. Light on data and great for practising on your phone.</span>
              <span className="tags">
                <span className="tag">Works on mobile data</span>
                {me && !voiceOff && <span className="tag">{fmtSeconds(me.balances.basic_seconds.available)} left</span>}
                {voiceOff && <span className="tag">Not available right now</span>}
              </span>
              <span className="mode-go">Practise with voice →</span>
            </button>
          </div>

          {!me && (
            <form className="signin stack" id="signin" onSubmit={submit}>
              <div>
                <h3>Sign in to start</h3>
                {mode ? (
                  <span className="picked">
                    You picked: {MODE_LABEL[mode]}
                    <button type="button" className="link-btn" onClick={() => setMode(null)}>change</button>
                  </span>
                ) : (
                  <p className="muted">Pick an interviewer above, then sign in.</p>
                )}
              </div>
              <div>
                <label htmlFor="email">Email</label>
                <input
                  id="email"
                  ref={emailRef}
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div>
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in and continue"}</button>
              {error && <p className="error" role="alert">{error}</p>}
              <p className="muted">Accounts are set up for you during this early preview.</p>
            </form>
          )}

          <p className="fine">Your interviewer is a fictional AI, not a consular officer.</p>
        </div>
      </section>

      <footer className="footer">
        <div className="wrap">
          <p>
            Practice only. This is not a government service, and nothing here predicts any visa decision. Always
            answer truthfully.
          </p>
        </div>
      </footer>
    </main>
  );
}

function Feature({ tint, icon, title, children }: { tint: string; icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="feature">
      <span className={`icon ${tint}`}>{icon}</span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

// ---------------------------------------------------------------- illustrations

function BrandMark() {
  return (
    <svg viewBox="0 0 34 34" aria-hidden="true">
      <circle cx="17" cy="17" r="17" fill="#ffede5" />
      <circle cx="23" cy="11.5" r="4.5" fill="#ffc94d" />
      <path d="M5 26 12.5 16l4.5 5.5 3.5-3.5L29 26z" fill="#cf3f25" />
    </svg>
  );
}

function HeroScene() {
  return (
    <div className="scene" aria-hidden="true">
      <svg viewBox="0 0 500 400" preserveAspectRatio="xMidYMax slice">
        <circle cx="365" cy="62" r="26" fill="#ffd36b" />
        <path d="M0 310 80 235l60 40 90-115 70 80 60-40 80 60 60-40v180H0z" fill="#b8d2f4" />
        <path d="M230 160 205.5 190l12.5-4 12 10 13-11 13 4z" fill="#fff" />
        <path d="M0 350 110 285l80 45 100-70 90 55 120-40v125H0z" fill="#9fd8b5" />
        <path d="M0 375c90-30 180-30 260-8s170 20 240-4v37H0z" fill="#86cba0" />
      </svg>
      <div className="bubble q">
        <span className="who">Interviewer</span>
        Why did you choose this university?
      </div>
      <div className="bubble a">
        <span className="who">You</span>
        Its computer science programme has a strong AI lab, and that fits my plan to work in health tech back home.
      </div>
      <div className="cheer">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="m5 12 5 5L20 7" />
        </svg>
        Clear and specific!
      </div>
    </div>
  );
}

function ArtVideo() {
  return (
    <svg viewBox="0 0 160 100" aria-hidden="true">
      <rect x="18" y="8" width="124" height="80" rx="14" fill="#fff" />
      <circle cx="80" cy="42" r="17" fill="#ffc94d" />
      <circle cx="74" cy="39" r="2.2" fill="#1f2430" />
      <circle cx="86" cy="39" r="2.2" fill="#1f2430" />
      <path d="M73 47q7 6 14 0" stroke="#1f2430" strokeWidth="2.4" fill="none" strokeLinecap="round" />
      <path d="M54 88c3-15 14-23 26-23s23 8 26 23z" fill="#cf3f25" />
      <circle cx="32" cy="21" r="4" fill="#1d7f5b" />
    </svg>
  );
}

function ArtVoice() {
  const bars = [
    [22, 20], [34, 38], [46, 26],
    [114, 26], [126, 38], [138, 20],
  ];
  return (
    <svg viewBox="0 0 160 100" aria-hidden="true">
      {bars.map(([x, h]) => (
        <rect key={x} x={x - 4} y={50 - h / 2} width="8" height={h} rx="4" fill="#2f6fde" opacity="0.55" />
      ))}
      <circle cx="80" cy="50" r="30" fill="#fff" />
      <rect x="73" y="33" width="14" height="24" rx="7" fill="#2f6fde" />
      <path d="M66 50a14 14 0 0 0 28 0M80 64v6" stroke="#2f6fde" strokeWidth="3" fill="none" strokeLinecap="round" />
    </svg>
  );
}

const iconProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function IconDoc() {
  return (
    <svg {...iconProps}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="m9 14 2 2 4-4" />
    </svg>
  );
}

function IconClock() {
  return (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function IconChat() {
  return (
    <svg {...iconProps}>
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1.1-4.4A8 8 0 1 1 21 12z" />
      <path d="M9 11h6M9 14.5h4" />
    </svg>
  );
}

function IconCalc() {
  return (
    <svg {...iconProps}>
      <rect x="5" y="3" width="14" height="18" rx="2" />
      <path d="M8 7h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01" />
    </svg>
  );
}
