"use client";

// "Have a code?": redeems a shared promo code for extra video and voice sessions.

import { useState } from "react";
import { api, ApiError } from "@/lib/api";

type Granted = { video_sessions: number; voice_sessions: number; valid_days: number };

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

export default function CodeBox({ onRedeemed }: { onRedeemed: () => void }) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function apply(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const g = await api<Granted>("/promo/redeem", { method: "POST", json: { code } });
      const parts = [g.video_sessions && plural(g.video_sessions, "video session"), g.voice_sessions && plural(g.voice_sessions, "voice session")].filter(Boolean);
      setMessage({ ok: true, text: `Code applied: ${parts.join(" and ")} added, for ${g.valid_days} days.` });
      setCode("");
      onRedeemed();
    } catch (err) {
      setMessage({ ok: false, text: err instanceof ApiError ? err.message : "Could not apply the code." });
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <p className="small" style={{ margin: "16px 0 0" }}>
        <button type="button" className="btn btn-ghost" onClick={() => setOpen(true)}>Have a code?</button>
      </p>
    );
  }
  return (
    <form className="code-box" onSubmit={apply}>
      <label htmlFor="promo">Your code</label>
      <div className="btn-row">
        <input id="promo" type="text" autoComplete="off" autoCapitalize="characters" maxLength={64} value={code} onChange={(e) => setCode(e.target.value)} required />
        <button type="submit" className="btn btn-secondary" disabled={busy || !code.trim()}>
          {busy ? "Applying…" : "Apply"}
        </button>
      </div>
      {message && <p className={message.ok ? "good small" : "error"} role="status">{message.text}</p>}
    </form>
  );
}
