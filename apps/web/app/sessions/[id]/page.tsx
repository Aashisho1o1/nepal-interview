"use client";

// Step 4: the rating form. Feedback and the transcript show only if a session has them,
// which none does until transcripts are connected.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import RatingForm, { type Rating } from "@/components/RatingForm";
import Shell from "@/components/Shell";
import { api, ApiError, fmtSeconds } from "@/lib/api";
import { DISCLAIMER, END_REASON, STATUS } from "@/lib/copy";

type Turn = { turn_id: string; speaker: "student" | "interviewer"; text: string; start_ms: number; canceled: boolean };
type Severity = "strength" | "needs_practice" | "needs_clarification" | "document_mismatch";
type Finding = {
  category: string;
  severity: Severity;
  observed_quote: string;
  turn_id: string;
  start_ms: number;
  explanation: string;
  next_action: string;
  requires_counselor_review: boolean;
  clearer_phrasing_example?: string | null;
};
type Report = { transcript_quality: string; findings: Finding[]; practice_tasks: string[]; unknowns: string[] };
type Resp = {
  session: {
    status: string;
    mode: "avatar" | "voice";
    created_at: string;
    end_reason: string | null;
    charged_premium_seconds: number | null;
    charged_basic_seconds: number | null;
    waived_seconds: number | null;
  };
  provider: { transcripts: boolean };
  rating: Rating | null;
  turns: Turn[];
  feedback: null | { status: "pending" | "ready" | "failed"; report: Report | null; error: string | null };
};

const CATEGORY: Record<string, string> = {
  question_relevance: "Answering the question",
  factual_consistency: "Consistency with your facts",
  funding_explanation: "Funding explanation",
  course_understanding: "Course understanding",
  concise_delivery: "Concise delivery",
  task_completion: "Practice task",
};
const SEV: Record<Severity, { label: string; cls: string; section: string }> = {
  strength: { label: "Strength", cls: "severity--good", section: "What went well" },
  needs_practice: { label: "Practise this", cls: "severity--warn", section: "Practise next" },
  needs_clarification: { label: "Check your document", cls: "severity--bad", section: "Check your documents" },
  document_mismatch: { label: "Check your document", cls: "severity--bad", section: "Check your documents" },
};
const SECTIONS = ["What went well", "Practise next", "Check your documents"];

export default function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<Resp | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stop = false;
    let tries = 0;
    async function poll() {
      try {
        const r = await api<Resp>(`/sessions/${id}/feedback`);
        if (stop) return;
        setData(r);
        const done =
          r.feedback?.status === "ready" || r.feedback?.status === "failed" || r.session.status === "failed" || !r.provider.transcripts;
        if (!done && tries++ < 40) setTimeout(poll, 1500);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) router.push("/");
        else setError("Could not load this session.");
      }
    }
    void poll();
    return () => {
      stop = true;
    };
  }, [id, router]);

  if (error) return <Shell step={4} title="Your session"><p className="error">{error}</p></Shell>;
  if (!data) return <Shell step={4} title="Your session"><p className="small">Loading…</p></Shell>;

  const { session, turns, feedback, provider } = data;
  const report = feedback?.report ?? null;
  const timed = turns.some((t) => t.start_ms > 0);
  const ended = session.status !== "created" && session.status !== "active";
  const used = (session.charged_premium_seconds ?? 0) + (session.charged_basic_seconds ?? 0);
  const when = new Date(session.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const tier = session.mode === "avatar" ? "Video" : "Voice";
  const counts = { strength: 0, warn: 0, doc: 0 };
  for (const f of report?.findings ?? []) {
    if (f.severity === "strength") counts.strength += 1;
    else if (f.severity === "needs_practice") counts.warn += 1;
    else counts.doc += 1;
  }
  const status = session.end_reason === "deadline" ? "Time ran out" : STATUS[session.status] ?? "Finished";

  return (
    <Shell step={4} title="Your session" intro={<span className="nums">{when} · {tier} · {fmtSeconds(used)} used · {status}</span>}>
      {session.status === "failed" ? (
        <div className="card">
          <p>This session didn&apos;t start ({(END_REASON[session.end_reason ?? ""] ?? "could not connect").toLowerCase()}), so no time was used.</p>
          <Link href="/interview" className="btn btn-primary btn-block">Try again</Link>
        </div>
      ) : (
        <div className="card card-strong">
          {report ? (
            <>
              <p className="small">Here&apos;s what we noticed in your practice. Every point quotes your own words.</p>
              <div className="counts nums">
                <span className="severity severity--good">{counts.strength} {counts.strength === 1 ? "strength" : "strengths"}</span>
                <span className="severity severity--warn">{counts.warn} to practise</span>
                <span className="severity severity--bad">{counts.doc} to check</span>
              </div>
            </>
          ) : provider.transcripts && (!feedback || feedback.status === "pending") ? (
            <p className="small">Preparing your feedback…</p>
          ) : feedback?.status === "failed" ? (
            <p className="small">{feedback.error}</p>
          ) : (
            <p className="small">Thanks for practising. Telling us how it felt below helps us improve.</p>
          )}
          {report && session.end_reason === "deadline" && <p className="caption">Time ran out. The feedback covers the part you completed.</p>}
          <Link href="/interview" className="btn btn-primary btn-block">Practise again</Link>
        </div>
      )}

      {report && (
        <>
          {report.transcript_quality === "insufficient" && (
            <p className="notice">Too little of your speech was captured to assess most areas.</p>
          )}
          {SECTIONS.map((section) => {
            const rows = report.findings.filter((f) => SEV[f.severity].section === section);
            if (!rows.length) return null;
            return (
              <section key={section}>
                <p className="eyebrow">{section}</p>
                {rows.map((f, i) => (
                  <div key={i} className="card finding">
                    <span className={`severity ${SEV[f.severity].cls}`}>{SEV[f.severity].label}</span>
                    <div className="caption">
                      {CATEGORY[f.category] ?? f.category}
                      {f.requires_counselor_review && " · for your counsellor to review"}
                    </div>
                    <div className="quote">
                      “{f.observed_quote}”
                      {timed && <a href={`#${f.turn_id}`} className="nums"> → {fmtSeconds(f.start_ms / 1000)}</a>}
                    </div>
                    <p>{f.explanation}</p>
                    <p><strong>Next:</strong> {f.next_action}</p>
                    {f.clearer_phrasing_example && <p className="small">Clearer, using your real facts: {f.clearer_phrasing_example}</p>}
                  </div>
                ))}
              </section>
            );
          })}
          {report.practice_tasks.length > 0 && (
            <section>
              <p className="eyebrow">Before next time</p>
              <ul>{report.practice_tasks.map((t) => <li key={t}>{t}</li>)}</ul>
            </section>
          )}
          {report.unknowns.length > 0 && (
            <section>
              <p className="eyebrow">Not yet confirmed</p>
              <ul>{report.unknowns.map((t) => <li key={t}>{t}</li>)}</ul>
            </section>
          )}
        </>
      )}

      {turns.length > 0 && (
        <details className="card">
          <summary>Full transcript</summary>
          <div>
            {turns.map((t) => (
              <div id={t.turn_id} key={t.turn_id} className={`turn ${t.canceled ? "canceled" : ""}`}>
                <div className="who">
                  {t.speaker === "student" ? "You" : "Interviewer"}
                  {timed && <a href={`#${t.turn_id}`} className="nums">{fmtSeconds(t.start_ms / 1000)}</a>}
                  {t.canceled && <span className="caption"> · interrupted</span>}
                </div>
                <div>{t.text}</div>
              </div>
            ))}
          </div>
        </details>
      )}

      {ended && session.status !== "failed" && <RatingForm sessionId={id} initial={data.rating} />}
      <p className="caption center" style={{ marginTop: 20 }}>{DISCLAIMER}</p>
      <p className="center small"><Link href="/interview">Practise again</Link> · <Link href="/prepare">Your details</Link></p>
    </Shell>
  );
}
