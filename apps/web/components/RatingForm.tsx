"use client";

// Same four questions after every session, whatever the provider, so interviewers
// can be compared on the student's experience (see scripts/provider_comparison.py).

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
  ["slight_pause", "Slight pause, felt natural"],
  ["noticeably_slow", "Noticeably slow"],
  ["frustrating", "Frustratingly slow"],
];

export default function RatingForm({ sessionId, initial }: { sessionId: string; initial: Rating | null }) {
  const [r, setR] = useState<Partial<Rating>>(initial ?? {});
  const [saved, setSaved] = useState(Boolean(initial));
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

  return (
    <form className="card stack" onSubmit={submit} aria-label="Rate this session">
      <h2 style={{ marginTop: 0 }}>How did this interviewer feel?</h2>
      <fieldset className="rating-row">
        <legend>How much did it feel like a real interview? (1 = not at all, 5 = very)</legend>
        <div className="row">
          {[1, 2, 3, 4, 5].map((n) => (
            <label key={n} className="pill-choice">
              <input type="radio" name="realism" checked={r.realism === n} onChange={() => set({ realism: n })} /> {n}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="rating-row">
        <legend>How quickly did the interviewer reply?</legend>
        {SPEEDS.map(([v, label]) => (
          <label key={v} className="pill-choice">
            <input type="radio" name="speed" checked={r.reply_speed === v} onChange={() => set({ reply_speed: v })} /> {label}
          </label>
        ))}
      </fieldset>
      <fieldset className="rating-row">
        <legend>Could you clearly hear (and see) the interviewer the whole time?</legend>
        <div className="row">
          <label className="pill-choice">
            <input type="radio" name="av" checked={r.audio_video_ok === true} onChange={() => set({ audio_video_ok: true })} /> Yes
          </label>
          <label className="pill-choice">
            <input type="radio" name="av" checked={r.audio_video_ok === false} onChange={() => set({ audio_video_ok: false })} /> No
          </label>
        </div>
      </fieldset>
      <fieldset className="rating-row">
        <legend>Would you practise with this interviewer again before your real interview?</legend>
        <div className="row">
          <label className="pill-choice">
            <input type="radio" name="again" checked={r.would_use_again === true} onChange={() => set({ would_use_again: true })} /> Yes
          </label>
          <label className="pill-choice">
            <input type="radio" name="again" checked={r.would_use_again === false} onChange={() => set({ would_use_again: false })} /> No
          </label>
        </div>
      </fieldset>
      <div>
        <label htmlFor="comment">Anything else? (optional)</label>
        <input id="comment" maxLength={1000} value={r.comment ?? ""} onChange={(e) => set({ comment: e.target.value })} />
      </div>
      <button type="submit" disabled={!complete}>{saved ? "Saved — thank you" : "Submit rating"}</button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
