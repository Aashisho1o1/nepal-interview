"use client";

// Step 2: the student checks every fact we extracted, then saves. Only saved,
// confirmed facts reach the interviewer.

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, ApiError, Fact, fmtMinor } from "@/lib/api";
import { factLabel, factNote, factValue, groupFacts } from "@/lib/facts";

type Funding = {
  currency: string;
  required_minor: number;
  scholarships_deducted_minor: number;
  net_required_minor: number;
  identified_funds_minor: number;
  gap_minor: number;
  surplus_minor: number;
  status: string;
  questions: string[];
  error?: string;
};
type Snapshot = { version: number | null; funding?: Funding; missing?: Record<string, string[]> };

export default function Prepare() {
  const router = useRouter();
  const [facts, setFacts] = useState<Fact[]>([]);
  const [snap, setSnap] = useState<Snapshot>({ version: null });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    return Promise.all([api<Fact[]>("/profile/facts"), api<Snapshot>("/profile/snapshot")])
      .then(([f, s]) => {
        setFacts(f);
        setSnap(s);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.push("/");
        else setError("Could not load your facts.");
      });
  }, [router]);

  useEffect(() => {
    load();
  }, [load]);

  async function setStatus(f: Fact, status: "confirmed" | "rejected") {
    if (f.confirmation_status === status) return;
    setFacts((cur) => cur.map((x) => (x.ref === f.ref ? { ...x, confirmation_status: status } : x)));
    try {
      await api(`/profile/facts/${encodeURIComponent(f.ref)}`, { method: "PATCH", json: { status } });
    } catch {
      setError("Could not save that change. Check your connection and try again.");
      await load();
    }
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      await api("/profile/snapshot", { method: "POST" });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  const pending = facts.filter((f) => f.confirmation_status === "proposed").length;
  const checked = facts.length - pending;
  const missing = snap.missing?.uk_pre_cas ?? [];
  const funding = snap.funding && !snap.funding.error ? snap.funding : null;
  const ready = snap.version !== null && missing.length === 0 && funding !== null;

  return (
    <Shell
      step={2}
      title="Check your facts"
      intro="We found these details in your documents. Tap Correct if a detail is right, Wrong if it isn't. Your interviewer only uses details you mark as correct."
    >
      {facts.length > 0 && (
        <div className="progress">
          <div className="caption nums">{checked} of {facts.length} checked</div>
          <div className="bar" aria-hidden="true">
            {facts.map((f) => <i key={f.ref} data-done={f.confirmation_status !== "proposed"} />)}
          </div>
        </div>
      )}

      {groupFacts(facts).map(([group, rows]) => (
        <section key={group}>
          <p className="eyebrow">{group}</p>
          {rows.map((f) => {
            const st = f.confirmation_status;
            const ok = st === "confirmed" || st === "corrected";
            const note = factNote(f);
            return (
              <div className="card fact" key={f.ref}>
                <div className="fact-head">
                  <div>
                    <div className="caption">{factLabel(f)}</div>
                    <div className="fact-value">{factValue(f)}</div>
                    {note && <div className="caption">{note}</div>}
                  </div>
                  {st === "proposed" && <span className="chip chip--outline">Not checked</span>}
                </div>
                <div className="caption">From {f.source_label}</div>
                <div className="quote">“{f.source_snippet}”</div>
                <div className="btn-row">
                  <button type="button" className={`btn ${ok ? "btn-primary" : "btn-secondary"}`} aria-pressed={ok} onClick={() => setStatus(f, "confirmed")}>
                    ✓ Correct
                  </button>
                  <button type="button" className={`btn ${st === "rejected" ? "btn-wrong" : "btn-secondary"}`} aria-pressed={st === "rejected"} onClick={() => setStatus(f, "rejected")}>
                    ✗ Wrong
                  </button>
                </div>
                {st === "rejected" && (
                  <p className="caption" style={{ marginTop: 10 }}>
                    Marked wrong, so the interviewer won&apos;t use it. Ask your counsellor to fix it, then mark it correct.
                  </p>
                )}
              </div>
            );
          })}
        </section>
      ))}

      {funding && (
        <section className="card">
          <h2>Your funding, added up</h2>
          <table>
            <tbody>
              <tr><td>First-year costs</td><td>{fmtMinor(funding.required_minor, funding.currency)}</td></tr>
              <tr><td>Scholarships</td><td>− {fmtMinor(funding.scholarships_deducted_minor, funding.currency)}</td></tr>
              <tr><td>Amount to fund</td><td>{fmtMinor(funding.net_required_minor, funding.currency)}</td></tr>
              <tr><td>Funds in your confirmed facts</td><td>{fmtMinor(funding.identified_funds_minor, funding.currency)}</td></tr>
              <tr>
                <td><strong>Difference</strong></td>
                <td className={funding.gap_minor > 0 ? "bad" : "good"}>
                  <strong>
                    {funding.gap_minor > 0
                      ? `${fmtMinor(funding.gap_minor, funding.currency)} short`
                      : `Covered (+${fmtMinor(funding.surplus_minor, funding.currency)})`}
                  </strong>
                </td>
              </tr>
            </tbody>
          </table>
          {funding.questions.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <p><strong>Be ready to explain these in your interview:</strong></p>
              <ul>{funding.questions.map((q) => <li key={q}>{q}</li>)}</ul>
            </div>
          )}
          <details>
            <summary>Why this estimate may differ</summary>
            <p className="small">
              It is added up from your confirmed figures only. A zero difference does not mean your funding is
              sufficient for a visa; the source of the money, its timing and your documents still need review.
            </p>
          </details>
        </section>
      )}

      {snap.version !== null && missing.length > 0 && (
        <p className="error">Still needed before you can practise: {missing.join(", ")}.</p>
      )}
      {error && <p className="error">{error}</p>}

      <div className="sticky-bar">
        <div className="btn-row">
          <button type="button" className="btn btn-secondary" onClick={save} disabled={busy || pending > 0 || facts.length === 0}>
            {busy ? "Saving…" : "Save my facts"}
          </button>
          <button type="button" className="btn btn-primary" onClick={() => router.push("/interview")} disabled={!ready}>
            Continue →
          </button>
        </div>
        {pending > 0 && <p className="caption center nums" style={{ margin: "8px 0 0" }}>{pending} {pending === 1 ? "fact" : "facts"} still unchecked</p>}
        {pending === 0 && !ready && facts.length > 0 && <p className="caption center" style={{ margin: "8px 0 0" }}>Save your facts to continue</p>}
      </div>
    </Shell>
  );
}
