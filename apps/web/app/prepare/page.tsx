"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, describeValue, Fact, fmtMinor } from "@/lib/api";

type Funding = {
  currency: string;
  required_minor: number;
  scholarships_deducted_minor: number;
  net_required_minor: number;
  identified_funds_minor: number;
  gap_minor: number;
  status: string;
  flags: string[];
  questions: string[];
  error?: string;
};
type Snapshot = { version: number | null; funding?: Funding; missing?: Record<string, string[]> };

const STATUS_LABEL: Record<string, string> = {
  covered_on_paper: "Arithmetic gap is zero (on paper)",
  gap: "Arithmetic gap",
  incomplete: "Incomplete: some amounts could not be counted",
};

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

  async function setStatus(ref: string, status: "confirmed" | "rejected") {
    await api(`/profile/facts/${encodeURIComponent(ref)}`, { method: "PATCH", json: { status } });
    await load();
  }

  async function confirmSnapshot() {
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
  const missing = snap.missing?.uk_pre_cas ?? [];
  const ready = snap.version !== null && missing.length === 0 && !snap.funding?.error;

  return (
    <main>
      <h1>Confirm your facts</h1>
      <p className="muted">
        The interviewer only uses facts you confirm here. Check each one against its source. If a value
        is wrong, reject it; never confirm a figure you cannot document.
      </p>

      <h2>Facts from your documents {pending > 0 && <span className="pill warn">{pending} to review</span>}</h2>
      <div className="card">
        {facts.map((f) => (
          <div className="fact" key={f.ref}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span className="muted">{f.field_name}</span>
              <span className={`pill ${f.confirmation_status === "rejected" ? "bad" : f.confirmation_status === "proposed" ? "warn" : "good"}`}>
                {f.confirmation_status}
              </span>
            </div>
            <div className="value">{describeValue(f.value_json)}</div>
            <div className="source">
              Source: {f.source_label} — “{f.source_snippet}”
            </div>
            {f.confirmation_status === "proposed" && (
              <div className="row">
                <button onClick={() => setStatus(f.ref, "confirmed")}>Confirm</button>
                <button className="secondary" onClick={() => setStatus(f.ref, "rejected")}>Reject</button>
              </div>
            )}
          </div>
        ))}
      </div>

      <button onClick={confirmSnapshot} disabled={busy || pending > 0}>
        {pending > 0 ? "Review every fact first" : snap.version ? "Save a new version" : "Save confirmed facts"}
      </button>
      {error && <p className="error">{error}</p>}

      {snap.funding && !snap.funding.error && (
        <>
          <h2>Funding arithmetic (version {snap.version})</h2>
          <div className="card">
            <table className="nums">
              <tbody>
                <tr><td>First-year costs</td><td>{fmtMinor(snap.funding.required_minor, snap.funding.currency)}</td></tr>
                <tr><td>Scholarships subtracted</td><td>{fmtMinor(snap.funding.scholarships_deducted_minor, snap.funding.currency)}</td></tr>
                <tr><td>Amount to fund</td><td>{fmtMinor(snap.funding.net_required_minor, snap.funding.currency)}</td></tr>
                <tr><td>Funds in confirmed facts</td><td>{fmtMinor(snap.funding.identified_funds_minor, snap.funding.currency)}</td></tr>
                <tr><td><strong>{STATUS_LABEL[snap.funding.status] ?? snap.funding.status}</strong></td><td><strong>{fmtMinor(snap.funding.gap_minor, snap.funding.currency)}</strong></td></tr>
              </tbody>
            </table>
            <p className="muted">
              Calculated from your confirmed figures only. A zero gap does not mean your funding is
              sufficient for a visa; source, timing and documents still need review.
            </p>
            {snap.funding.questions.length > 0 && (
              <>
                <p><strong>Be ready to explain:</strong></p>
                <ul>{snap.funding.questions.map((q) => <li key={q}>{q}</li>)}</ul>
              </>
            )}
          </div>
        </>
      )}
      {snap.version !== null && missing.length > 0 && (
        <p className="error">Still needed before you can practise: {missing.join(", ")}</p>
      )}
      {ready && (
        <p><Link href="/interview"><button>Continue to practice</button></Link></p>
      )}
    </main>
  );
}
