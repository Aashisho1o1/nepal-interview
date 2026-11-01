"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, fmtSeconds } from "@/lib/api";

type Turn = { turn_id: string; speaker: "student" | "interviewer"; text: string; start_ms: number; canceled: boolean };
type Finding = {
  category: string;
  severity: "strength" | "needs_practice" | "needs_clarification" | "document_mismatch";
  observed_quote: string;
  turn_id: string;
  start_ms: number;
  document_refs: string[];
  explanation: string;
  next_action: string;
  requires_counselor_review: boolean;
  clearer_phrasing_example?: string | null;
};
type Report = {
  transcript_quality: string;
  findings: Finding[];
  practice_tasks: string[];
  unknowns: string[];
  human_review_status: string;
};
type Resp = {
  session: {
    status: string;
    end_reason: string | null;
    display: string;
    fallback_at: string | null;
    charged_premium_seconds: number | null;
    charged_basic_seconds: number | null;
    waived_seconds: number | null;
  };
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
const SEVERITY: Record<string, string> = {
  strength: "Strength",
  needs_practice: "Practise this",
  needs_clarification: "Needs clarification",
  document_mismatch: "Differs from your documents",
};

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
        const done = r.feedback?.status === "ready" || r.feedback?.status === "failed" || r.session.status === "failed";
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

  if (error) return <main><p className="error">{error}</p></main>;
  if (!data) return <main><p>Loading…</p></main>;

  const { session, turns, feedback } = data;
  const report = feedback?.report;
  return (
    <main>
      <h1>Practice feedback</h1>
      <p className="muted">
        Practice feedback only. It does not predict a visa decision and does not judge honesty or
        emotion. Items marked for counsellor review have not been reviewed yet.
      </p>

      <div className="card">
        <div className="row">
          <span className="pill">{session.status}</span>
          {session.fallback_at && <span className="pill warn">continued in voice</span>}
          {session.end_reason && <span className="pill">{session.end_reason.replaceAll("_", " ")}</span>}
        </div>
        <p className="muted nums">
          Used: {fmtSeconds(session.charged_premium_seconds ?? 0)} video, {fmtSeconds(session.charged_basic_seconds ?? 0)} voice
          {session.waived_seconds ? `, ${fmtSeconds(session.waived_seconds)} not charged` : ""}.
          {session.status === "failed" && " The session did not start; no time was used."}
        </p>
      </div>

      {session.status !== "failed" && (!feedback || feedback.status === "pending") && <p>Preparing feedback…</p>}
      {feedback?.status === "failed" && <p className="error">{feedback.error}</p>}

      {report && (
        <>
          {report.transcript_quality === "insufficient" && (
            <p className="error">Too little of your speech was captured to assess most areas.</p>
          )}
          <h2>What we observed</h2>
          {report.findings.length === 0 && <p className="muted">No specific findings.</p>}
          {report.findings.map((f, i) => (
            <div key={i} className={`finding ${f.severity}`}>
              <div className="row">
                <strong>{CATEGORY[f.category] ?? f.category}</strong>
                <span className="pill">{SEVERITY[f.severity]}</span>
                {f.requires_counselor_review && <span className="pill warn">counsellor review</span>}
              </div>
              <blockquote>
                <a href={`#${f.turn_id}`}>“{f.observed_quote}”</a> <span className="muted nums">at {fmtSeconds(f.start_ms / 1000)}</span>
              </blockquote>
              <p>{f.explanation}</p>
              <p><strong>Next:</strong> {f.next_action}</p>
              {f.clearer_phrasing_example && (
                <p className="muted">Example of clearer phrasing using your real facts: {f.clearer_phrasing_example}</p>
              )}
              {f.document_refs.length > 0 && <p className="muted">Based on: {f.document_refs.join(", ")}</p>}
            </div>
          ))}
          {report.practice_tasks.length > 0 && (
            <>
              <h2>Practise next</h2>
              <ul>{report.practice_tasks.map((t) => <li key={t}>{t}</li>)}</ul>
            </>
          )}
          {report.unknowns.length > 0 && (
            <>
              <h2>Not yet confirmed</h2>
              <ul>{report.unknowns.map((t) => <li key={t}>{t}</li>)}</ul>
            </>
          )}
        </>
      )}

      {turns.length > 0 && (
        <>
          <h2>Transcript</h2>
          <div className="card">
            {turns.map((t) => (
              <div id={t.turn_id} key={t.turn_id} className={`turn ${t.canceled ? "canceled" : ""}`}>
                <div className="who nums">
                  {t.speaker === "student" ? "You" : "Interviewer"} · {fmtSeconds(t.start_ms / 1000)}
                  {t.canceled && " · interrupted"}
                </div>
                <div>{t.text}</div>
              </div>
            ))}
          </div>
        </>
      )}
      <p><Link href="/interview">Practise again</Link> · <Link href="/prepare">Your facts</Link></p>
    </main>
  );
}
