"use client";

// Every page shares this header; inner pages add the four-step navigation and a title.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, firstName, type Me } from "@/lib/api";

// [label, where the step lives]. Feedback belongs to a session, so it's only shown.
const STEPS: [string, string | null][] = [
  ["Your account", "/"],
  ["About you", "/prepare"],
  ["Practise", "/interview"],
  ["Feedback", null],
];

type Props = {
  step?: 1 | 2 | 3 | 4;
  title?: React.ReactNode;
  intro?: React.ReactNode;
  width?: "wide" | "page" | "narrow";
  me?: Me | null; // pass it when the page already fetched it
  locked?: boolean; // during a live call: no leaving by the step links
  children: React.ReactNode;
};

export default function Shell({ step, title, intro, width = "page", me: given, locked = false, children }: Props) {
  const router = useRouter();
  const [fetched, setFetched] = useState<Me | null>(null);
  const me = given === undefined ? fetched : given;
  useEffect(() => {
    if (given === undefined) api<Me>("/me").then(setFetched).catch(() => setFetched(null));
  }, [given]);

  async function signOut() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    router.push("/");
    router.refresh();
  }

  return (
    <>
      <header className="header">
        <div className="header-in">
          <Link className="brand" href="/">
            <Logo />
            Interview Practice
          </Link>
          <div className="header-right">
            {me ? (
              <>
                <span>Hi, {firstName(me)}</span>
                <button type="button" className="btn btn-ghost" onClick={signOut}>Sign out</button>
              </>
            ) : (
              // A plain link fires "hashchange", so the home page opens its form in sign-in mode.
              // eslint-disable-next-line @next/next/no-html-link-for-pages
              <a href="/#signin">Sign in</a>
            )}
          </div>
        </div>
      </header>
      <main className={width === "page" ? undefined : width}>
        {step && (
          <nav className="stepper" aria-label="Steps">
            <div className="stepper-top">
              {step > 1 && !locked ? (
                <Link href={STEPS[step - 2][1] ?? "/"} className="back">← {STEPS[step - 2][0]}</Link>
              ) : (
                <span />
              )}
              <span>Step {step} of 4</span>
            </div>
            <ol className="steps">
              {STEPS.map(([label, href], i) => {
                const props = { "data-done": i < step, "aria-current": i === step - 1 ? ("step" as const) : undefined };
                return (
                  <li key={label}>
                    {href && !locked && i !== step - 1 ? <Link href={href} {...props}>{label}</Link> : <span {...props}>{label}</span>}
                  </li>
                );
              })}
            </ol>
          </nav>
        )}
        {title && <h1>{title}</h1>}
        {intro && <p className="intro">{intro}</p>}
        {children}
      </main>
    </>
  );
}

export function Logo() {
  return (
    <svg viewBox="0 0 28 28" aria-hidden="true">
      <circle cx="14" cy="14" r="14" fill="#e4573d" />
      <path d="M6 20l5.5-7 3 3.5 2.5-2.5L22 20z" fill="none" stroke="#fff" strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx="19" cy="9" r="2" fill="#ffc94d" />
    </svg>
  );
}
