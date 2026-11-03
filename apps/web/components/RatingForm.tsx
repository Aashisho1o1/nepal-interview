"use client";

// Same four questions after every session, whatever the interviewer, so the two
// tiers can be compared on the student's experience.

import { useState } from "react";
import { api, ApiError } from "@/lib/api";

export type Rating = {
  realism: number;
  reply_speed: "instant" | "slight_pause" | "noticeably_slow" | "frustrating";
  audio_video_ok: boolean;
  would_use_again: boolean;
  comment: string | null;
};

const SPEEDS: [Rating["reply_speed"], string][] = [
  ["instant", "Instant"],
  ["slight_pause", "Slight pause"],
  ["noticeably_slow", "Noticeably slow"],
  ["frustrating", "Frustrating"],
];

function Seg<T extends string | number | boolean>({ options, value, onPick, round }: { options: [T, string][]; value: T | undefined; onPick: (v: T) => void; round?: boolean }) {
  return (
    <div className="seg">
      {options.map(([v, label]) => (
        <button key={String(v)} type="button" className={round ? "round" : undefined} aria-pressed={value === v} onClick={() => onPick(v)}>
          {label}
        </button>
      ))}
    </div>
  );
}

export default function RatingForm({ sessionId, initial }: { sessionId: string; initial: Rating | null }) {
  const [r, setR] = useState<Partial<Rating>>(initial ?? {});
  const [saved, setSaved] = useState(Boolean(initial));
  const [showComment, setShowComment] = useState(Boolean(initial?.comment));
  const [error, setError] = useState("");
  const complete =
    r.realism !== undefined && r.reply_speed !== undefined && r.audio_video_ok !== undefined && r.would_use_again !== undefined;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api(`/sessions/${sessionId}/rating`, { method: "POST", json: { ...r, comment: r.comment || null } });
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    }
  }

  const set = (patch: Partial<Rating>) => {
    setR((cur) => ({ ...cur, ...patch }));
    setSaved(false);
  };
  const yesNo: [boolean, string][] = [[true, "Yes"], [false, "No"]];

  return (
    <form className="card" onSubmit={submit} aria-label="Rate this session">
      <h2>How did it feel?</h2>
      <div className="q">
        <p>Did it feel like a real interview? <span className="caption">1 = not at all, 5 = very</span></p>
        <Seg round options={[1, 2, 3, 4, 5].map((n) => [n, String(n)] as [number, string])} value={r.realism} onPick={(v) => set({ realism: v })} />
      </div>
      <div className="q">
        <p>How fast were the replies?</p>
        <Seg options={SPEEDS} value={r.reply_speed} onPick={(v) => set({ reply_speed: v })} />
      </div>
      <div className="q">
        <p>Could you hear the interviewer clearly the whole time?</p>
        <Seg options={yesNo} value={r.audio_video_ok} onPick={(v) => set({ audio_video_ok: v })} />
      </div>
      <div className="q">
        <p>Would you practise with this interviewer again?</p>
        <Seg options={yesNo} value={r.would_use_again} onPick={(v) => set({ would_use_again: v })} />
      </div>
      <div className="q">
        {showComment ? (
          <div className="field">
            <label htmlFor="comment">Anything else?</label>
            <textarea id="comment" maxLength={1000} value={r.comment ?? ""} onChange={(e) => set({ comment: e.target.value })} />
          </div>
        ) : (
          <button type="button" className="btn btn-ghost" onClick={() => setShowComment(true)}>Add a comment (optional)</button>
        )}
      </div>
      <button type="submit" className="btn btn-primary btn-block" disabled={!complete || saved}>
        {saved ? "Thanks, saved" : "Submit rating"}
      </button>
      {!complete && <p className="caption center" style={{ margin: "8px 0 0" }}>Answer the questions above to submit.</p>}
      {error && <p className="error">{error}</p>}
    </form>
  );
}
