"use client";

// Team-only review of every practice session: how it ended, the student's rating
// and comment, the transcript and the automatic feedback. Only the emails in the
// server's TEAM_EMAILS can load the data; everyone else gets "not found".

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, ApiError, fmtSeconds } from "@/lib/api";
import { END_REASON, STATUS } from "@/lib/copy";

type Row = {
  id: string;
  created_at: string;
  mode: "avatar" | "voice";
  status: string;
  end_reason: string | null;
  practice_seconds: number;
  talked_seconds: number | null;
  name: string;
  email: string;
  realism: number | null;
  reply_speed: string | null;
  audio_video_ok: boolean | null;
  would_use_again: boolean | null;
  comment: string | null;
  feedback_status: string | null;
  feedback: { findings?: { severity: string; explanation: string; next_action: string }[]; practice_tasks?: string[] } | null;
  turns: { speaker: "student" | "interviewer"; text: string }[];
};

const MODE = { avatar: "Video", voice: "Voice" } as const;
const SPEED: Record<string, string> = {
  instant: "Instant",
  slight_pause: "Slight pause",
  noticeably_slow: "Noticeably slow",
  frustrating: "Frustrating",
};
const yesNo = (v: boolean | null) => (v === null ? "" : v ? "Yes" : "No");
const when = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const pct = (n: number, d: number) => (d ? `${Math.round((100 * n) / d)}%` : "–");

function summary(rows: Row[]) {
  const rated = rows.filter((r) => r.realism !== null);
  return {
    sessions: rows.length,
    talked: rows.filter((r) => (r.talked_seconds ?? 0) > 0).length,
    rated: rated.length,
    realism: rated.length ? (rated.reduce((a, r) => a + (r.realism ?? 0), 0) / rated.length).toFixed(1) : "–",
    again: pct(rated.filter((r) => r.would_use_again).length, rated.length),
    av: pct(rated.filter((r) => r.audio_video_ok).length, rated.length),
  };
}

function downloadCsv(rows: Row[]) {
  const cols = ["date", "name", "email", "mode", "status", "end", "talked_s", "realism", "reply_speed", "av_ok", "use_again", "comment", "transcript"];
  // A leading = + - @ would run as a spreadsheet formula; a quote makes it text.
  const cell = (v: unknown) => `"${String(v ?? "").replace(/^[=+\-@]/, "'$&").replace(/"/g, '""')}"`;
  const lines = rows.map((r) =>
    [
      r.created_at, r.name, r.email, MODE[r.mode], r.status, r.end_reason, r.talked_seconds, r.realism,
      r.reply_speed, yesNo(r.audio_video_ok), yesNo(r.would_use_again), r.comment,
      r.turns.map((t) => `${t.speaker === "student" ? "Student" : "Interviewer"}: ${t.text}`).join("\n"),
    ].map(cell).join(","),
  );
  const blob = new Blob([[cols.join(","), ...lines].join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `sessions-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function Team() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Row[]>("/team/sessions")
      .then(setRows)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.push("/#signin");
        else setError(e instanceof ApiError && e.status === 404 ? "This page is for the team." : "Could not load sessions.");
      });
  }, [router]);

  return (
    <Shell width="wide" title="Practice sessions" intro="Every session, newest first, with what the student said about it.">
      {error && <p className="error">{error}</p>}
      {rows && (
        <>
          <div className="team-sum">
            {(["avatar", "voice"] as const).map((m) => {
              const s = summary(rows.filter((r) => r.mode === m));
              return (
                <div key={m} className="card">
                  <h2>{MODE[m]}</h2>
                  <p className="small">
                    {s.sessions} sessions · {s.talked} connected · {s.rated} rated
                    <br />
                    Realism {s.realism}/5 · Would use again {s.again} · Heard clearly {s.av}
                  </p>
                </div>
              );
            })}
          </div>
          <button type="button" className="btn btn-secondary" onClick={() => downloadCsv(rows)} disabled={!rows.length} style={{ margin: "0 0 16px" }}>
            Download CSV
          </button>
          {rows.length === 0 && <p className="small">No sessions yet.</p>}
          {rows.map((r) => (
            <div key={r.id} className="card team-row">
              <p className="team-head">
                <strong>{r.name}</strong> <span className="caption">{r.email}</span>
                <span className="chip">{MODE[r.mode]}</span>
              </p>
              <p className="caption">
                {when(r.created_at)} · {r.talked_seconds !== null ? `talked ${fmtSeconds(r.talked_seconds)}` : "never connected"} ·{" "}
                {END_REASON[r.end_reason ?? ""] ?? STATUS[r.status] ?? r.status}
              </p>
              {r.realism !== null ? (
                <p className="small">
                  Realism <strong>{r.realism}/5</strong> · Replies {SPEED[r.reply_speed ?? ""]} · Heard clearly {yesNo(r.audio_video_ok)} · Would use again{" "}
                  <strong>{yesNo(r.would_use_again)}</strong>
                </p>
              ) : (
                <p className="caption">Not rated.</p>
              )}
              {r.comment && <div className="quote">“{r.comment}”</div>}
              {r.turns.length > 0 && (
                <details>
                  <summary>Transcript ({r.turns.length} turns)</summary>
                  {r.turns.map((t, i) => (
                    <p key={i} className="small">
                      <strong>{t.speaker === "student" ? "Student" : "Interviewer"}:</strong> {t.text}
                    </p>
                  ))}
                </details>
              )}
              {r.feedback?.findings && r.feedback.findings.length > 0 && (
                <details>
                  <summary>Feedback the student saw</summary>
                  <ul className="small">
                    {r.feedback.findings.map((f, i) => (
                      <li key={i}>{f.explanation} <em>{f.next_action}</em></li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ))}
        </>
      )}
    </Shell>
  );
}
